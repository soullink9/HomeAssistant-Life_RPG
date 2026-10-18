"""The art studio: paints the game's portraits, gear, guardians and characters with your own ComfyUI.

One studio serves every adventurer. Paintings are made once, saved under /config/life_rpg/art and
served at /life_rpg_art/<hash>.webp; until one is ready the panel shows the pixel-art fallback.
Jobs run one at a time, most important first (your portrait and this week's guardian before
the backlog of inventory items), and wait politely while ComfyUI is offline or busy.

With an image-edit model (Flux Kontext or Qwen Image Edit), the adventurer, the goddess and the
merchant get one base painting each, and every mood, outfit and backdrop is an edit of it, so
their faces stay the same from picture to picture.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import hashlib
import io
import json
import logging
from pathlib import Path
import time
from typing import Any
import uuid

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import ART_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

MAX_FILES = 1500  # least-recently-used paintings are deleted past this...
MAX_TOTAL = 1024 * 1024 * 1024  # ...or once the folder passes 1 GB
HARD_TOTAL = MAX_TOTAL * 3 // 2  # past this even recently shown paintings go (oldest first)
WEBP_QUALITY = 88  # paintings are kept as WebP (a fraction of the PNG's size); PNG if Pillow isn't there
MAX_BYTES = 32 * 1024 * 1024  # a single painting may not be larger than this
KEEP_RECENT = 3 * 24 * 3600  # paintings shown in the last three days are never pruned
STALE_JOB = 24 * 3600  # queued paintings nobody has asked for in a day are dropped (sold items, old portraits)
IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")
POLL, JOB_TIMEOUT = 2.0, 900
RETRY_OFFLINE, RETRY_FAILED = 120, 6 * 3600
FAMILIES = {  # sampler settings that suit each model family
    "sdxl": {"steps": 28, "cfg": 5.5, "sampler": "dpmpp_2m", "scheduler": "karras"},
    "flux": {"steps": 22, "cfg": 1.0, "sampler": "euler", "scheduler": "simple", "guidance": 3.5},
    "flux_unet": {"steps": 22, "cfg": 1.0, "sampler": "euler", "scheduler": "simple", "guidance": 3.5},
}
FAST_MODEL = {  # Lightning / Turbo / Hyper (SDXL) and Schnell (Flux): a handful of steps, low guidance
    "sdxl": {"steps": 6, "cfg": 1.5, "sampler": "euler", "scheduler": "sgm_uniform"},
    "flux": {"steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple", "guidance": 3.5},
}
FAST_MODEL["flux_unet"] = FAST_MODEL["flux"]
SPEED = {  # painting speed: (scale for small things, scale for everything else, share of the usual steps)
    "quality": (1.0, 1.0, 1.0),
    "balanced": (0.75, 1.0, 1.0),
    "fast": (0.75, 0.875, 0.65),
}
SMALL_KINDS = ("item",)  # shown as small icons: painting them smaller costs little


def _size(n: int, scale: float) -> int:
    """Scale a painting size and round it to a multiple of 64 (what the models want), never below 512."""
    return max(512, int(round(n * scale / 64)) * 64)


# where each model type's model file lives in ComfyUI: (loader node, its file field)
MODEL_LOADER = {"flux_unet": ("UNETLoader", "unet_name")}
DEFAULT_LOADER = ("CheckpointLoaderSimple", "ckpt_name")
EDIT_SETTINGS = {  # image-edit models
    "kontext": {"steps": 20, "cfg": 1.0, "sampler": "euler", "scheduler": "simple", "guidance": 2.5},
    "qwen": {"steps": 20, "cfg": 2.5, "sampler": "euler", "scheduler": "simple", "shift": 3.0},
}
UPLOAD_FOLDER = "life_rpg"  # base paintings are uploaded to ComfyUI's input/life_rpg folder


def edit_kind(model: str) -> str:
    """Which edit model a file is: Qwen Image Edit, or Flux Kontext (anything else)."""
    return "qwen" if "qwen" in str(model).lower() else "kontext"


def art_key(spec: dict[str, Any], variant: Any = "") -> str:
    """Stable id for a painting: same prompt, same picture."""
    raw = f"{spec['kind']}|{spec['prompt']}|{spec['w']}x{spec['h']}|{variant}"
    return f"{spec['kind']}-{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


# The built-in workflows below follow the node layouts of ComfyUI's example workflows for each model
# (https://comfyanonymous.github.io/ComfyUI_examples/).
def build_workflow(spec: dict[str, Any], cfg: dict[str, Any], seed: int, custom: dict | None = None) -> dict[str, Any]:
    """A ComfyUI API-format workflow for one painting."""
    prefix = f"life_rpg/{spec['kind']}"
    if custom is not None:
        values = {
            "%PROMPT%": spec["prompt"],
            "%NEGATIVE%": spec["negative"],
            "%PREFIX%": prefix,
            "%SEED%": seed,
            "%WIDTH%": spec["w"],
            "%HEIGHT%": spec["h"],
            "%OUT_WIDTH%": spec["out_w"],
            "%OUT_HEIGHT%": spec["out_h"],
        }

        def fill(node: Any) -> Any:
            """Recursively swap the workflow's {placeholders} for this job's values."""
            if isinstance(node, dict):
                return {k: fill(v) for k, v in node.items()}
            if isinstance(node, list):
                return [fill(v) for v in node]
            if isinstance(node, str):
                if node in values:
                    return values[node]
                for k, v in values.items():
                    node = node.replace(k, str(v))
            return node

        return fill(custom)
    family = cfg.get("family", "sdxl")
    s = dict((FAST_MODEL if cfg.get("fast_model") else FAMILIES).get(family, FAMILIES["sdxl"]))
    hq = bool(spec.get("hq"))  # a base painting: full size and a quarter more steps, whatever the painting speed
    small, big, steps = SPEED["quality"] if hq else SPEED.get(cfg.get("speed") or "quality", SPEED["quality"])
    scale = small if spec["kind"] in SMALL_KINDS else big
    w, h = _size(spec["w"], scale), _size(spec["h"], scale)
    if not cfg.get("fast_model"):
        s["steps"] = max(8, round(s["steps"] * steps * (1.25 if hq else 1)))
    flux = family in ("flux", "flux_unet")
    split = family == "flux_unet"  # model, text encoders and VAE as separate files
    clip, vae = (["10", 0], ["11", 0]) if split else (["1", 1], ["1", 2])
    wf: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": cfg["checkpoint"]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["prompt"], "clip": clip}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "" if flux else spec["negative"], "clip": clip}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": s["steps"],
                "cfg": s["cfg"],
                "sampler_name": s["sampler"],
                "scheduler": s["scheduler"],
                "positive": ["9", 0] if flux else ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "denoise": 1.0,
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": vae}},
        "7": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["6", 0],
                "upscale_method": "area",
                "width": spec["out_w"],
                "height": spec["out_h"],
                "crop": "disabled",
            },
        },
        # PreviewImage: ComfyUI keeps it in its temp folder (cleared on restart), so its output folder doesn't fill up
        "8": {"class_type": "PreviewImage", "inputs": {"images": ["7", 0]}},
    }
    if flux:
        wf["9"] = {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": s["guidance"]}}
    if split:
        parts = cfg.get("parts") or {}
        # Fast: load a full-size Flux at half the memory, so it fits beside Ollama instead of reloading every time
        dtype = (
            "fp8_e4m3fn" if cfg.get("speed") == "fast" and "fp8" not in str(cfg["checkpoint"]).lower() else "default"
        )
        wf["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": cfg["checkpoint"], "weight_dtype": dtype}}
        wf["10"] = {
            "class_type": "DualCLIPLoader",
            "inputs": {"clip_name1": parts.get("t5"), "clip_name2": parts.get("clip_l"), "type": "flux"},
        }
        wf["11"] = {"class_type": "VAELoader", "inputs": {"vae_name": parts.get("vae")}}
    return wf


def build_edit_workflow(spec: dict[str, Any], cfg: dict[str, Any], seed: int, image: str) -> dict[str, Any]:
    """A ComfyUI workflow that edits an uploaded base painting (`image`, in ComfyUI's input folder) as the
    spec's edit instruction says."""
    edit = cfg["edit"]
    kind = edit_kind(edit["model"])
    st = dict(EDIT_SETTINGS[kind])
    steps = SPEED.get(cfg.get("speed") or "quality", SPEED["quality"])[2]
    st["steps"] = max(8, round(st["steps"] * steps))
    parts = edit.get("parts") or {}
    dtype = "fp8_e4m3fn" if cfg.get("speed") == "fast" and "fp8" not in str(edit["model"]).lower() else "default"
    text = spec["edit"]["instruction"]
    wf: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": edit["model"], "weight_dtype": dtype}},
        "11": {"class_type": "VAELoader", "inputs": {"vae_name": parts.get("vae")}},
        "20": {"class_type": "LoadImage", "inputs": {"image": image}},
        "22": {"class_type": "VAEEncode", "inputs": {"pixels": ["21", 0], "vae": ["11", 0]}},
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": st["steps"],
                "cfg": st["cfg"],
                "sampler_name": st["sampler"],
                "scheduler": st["scheduler"],
                "positive": ["9", 0],
                "negative": ["3", 0],
                "latent_image": ["22", 0],
                "denoise": 1.0,
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["11", 0]}},
        "7": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["6", 0],
                "upscale_method": "area",
                "width": spec["out_w"],
                "height": spec["out_h"],
                "crop": "center",
            },
        },
        "8": {"class_type": "PreviewImage", "inputs": {"images": ["7", 0]}},
    }
    if kind == "kontext":  # Flux Kontext: the same text encoders and VAE as Flux
        wf["10"] = {
            "class_type": "DualCLIPLoader",
            "inputs": {"clip_name1": parts.get("t5"), "clip_name2": parts.get("clip_l"), "type": "flux"},
        }
        wf["21"] = {"class_type": "FluxKontextImageScale", "inputs": {"image": ["20", 0]}}
        wf["2"] = {"class_type": "CLIPTextEncode", "inputs": {"text": text, "clip": ["10", 0]}}
        wf["23"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["2", 0], "latent": ["22", 0]}}
        wf["9"] = {"class_type": "FluxGuidance", "inputs": {"conditioning": ["23", 0], "guidance": st["guidance"]}}
        wf["3"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
    else:  # Qwen Image Edit
        wf["10"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": parts.get("te"), "type": "qwen_image"}}
        wf["21"] = {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {"image": ["20", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1},
        }

        def encode(prompt: str) -> dict[str, Any]:
            """A Qwen edit prompt node that sees the scaled base image."""
            return {
                "class_type": "TextEncodeQwenImageEditPlus",
                "inputs": {"clip": ["10", 0], "prompt": prompt, "vae": ["11", 0], "image1": ["21", 0]},
            }

        wf["9"], wf["3"] = encode(text), encode("")  # positive, negative
        wf["25"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": st["shift"]}}
        wf["5"]["inputs"]["model"] = ["25", 0]
    return wf


async def _node_files(hass: HomeAssistant, url: str, node: str, field: str) -> list[str] | None:
    """The files ComfyUI offers for one input of one node, or None if it can't be reached."""
    try:
        async with async_get_clientsession(hass).get(
            f"{url.rstrip('/')}/object_info/{node}", timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            info = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None
    if not isinstance(info, dict):
        return None
    spec = info.get(node, {}).get("input", {}).get("required", {}).get(field, [[]])
    names = (
        spec[0] if spec and isinstance(spec[0], list) else (spec[1] or {}).get("options", []) if len(spec) > 1 else []
    )
    return [str(n) for n in names]


async def list_checkpoints(hass: HomeAssistant, url: str, family: str = "sdxl") -> list[str] | None:
    """Model files installed in ComfyUI for this model type (checkpoints, or diffusion_models for Flux in
    separate files), or None if it can't be reached."""
    return await _node_files(hass, url, *MODEL_LOADER.get(family, DEFAULT_LOADER))


def pick_flux_parts(encoders: list[str], vaes: list[str]) -> dict[str, str | None]:
    """The text encoders and VAE a separate-files Flux model needs, chosen from what's installed."""
    low = lambda n: n.replace("\\", "/").rsplit("/", 1)[-1].lower()  # noqa: E731
    clip_l = next((n for n in encoders if "clip_l" in low(n)), None)
    t5s = [n for n in encoders if "t5xxl" in low(n) or "t5-xxl" in low(n)]
    t5 = next((n for n in t5s if "fp16" in low(n)), t5s[0] if t5s else None)
    vae = next((n for n in vaes if low(n) in ("ae.safetensors", "ae.sft")), None) or next(
        (n for n in vaes if "flux" in low(n) or low(n).startswith("ae.")), None
    )
    return {"clip_l": clip_l, "t5": t5, "vae": vae}


async def find_flux_parts(hass: HomeAssistant, url: str) -> dict[str, str | None] | None:
    """Look up the installed text encoders and VAEs; None if ComfyUI can't be reached."""
    encoders = await _node_files(hass, url, "DualCLIPLoader", "clip_name1")
    vaes = await _node_files(hass, url, "VAELoader", "vae_name")
    if encoders is None or vaes is None:
        return None
    return pick_flux_parts(encoders, vaes)


def pick_qwen_parts(encoders: list[str], vaes: list[str]) -> dict[str, str | None]:
    """The text encoder and VAE Qwen Image Edit needs, chosen from what's installed."""
    low = lambda n: n.replace("\\", "/").rsplit("/", 1)[-1].lower()  # noqa: E731
    te = next((n for n in encoders if "qwen_2.5_vl" in low(n) or "qwen2.5" in low(n)), None) or next(
        (n for n in encoders if "qwen" in low(n)), None
    )
    vae = next((n for n in vaes if "qwen" in low(n)), None)
    return {"te": te, "vae": vae}


async def list_edit_models(hass: HomeAssistant, url: str) -> list[str] | None:
    """Image-edit candidates in ComfyUI's diffusion_models folder (Kontext and edit models first)."""
    names = await _node_files(hass, url, "UNETLoader", "unet_name")
    if names is None:
        return None
    return sorted(names, key=lambda n: (not any(w in n.lower() for w in ("kontext", "edit")), n.lower()))


async def find_edit_parts(hass: HomeAssistant, url: str, model: str) -> dict[str, str | None] | None:
    """The text encoders and VAE an edit model needs; None if ComfyUI can't be reached."""
    if edit_kind(model) == "kontext":
        return await find_flux_parts(hass, url)
    encoders = await _node_files(hass, url, "CLIPLoader", "clip_name")
    vaes = await _node_files(hass, url, "VAELoader", "vae_name")
    if encoders is None or vaes is None:
        return None
    return pick_qwen_parts(encoders, vaes)


class Studio:
    """Queue, ComfyUI client and the cache of finished paintings."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the studio (call async_load before use)."""
        self.hass = hass
        self.dir = Path(hass.config.path(DOMAIN, "art"))
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.art")
        self.index: dict[str, dict[str, Any]] = {}  # key -> {file, kind, used, failed_at, error}
        self.queue: dict[str, dict[str, Any]] = {}  # key -> job
        self.listeners: list[Callable[[], None]] = []
        self.status: dict[str, Any] = {"state": "idle", "error": None, "current": None}
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._offline_until = 0.0

    async def async_load(self) -> None:
        """Load the cache index and start the painter."""
        await self.hass.async_add_executor_job(lambda: self.dir.mkdir(parents=True, exist_ok=True))
        self.index = (await self.store.async_load() or {}).get("index", {})
        self._task = self.hass.async_create_background_task(self._run(), f"{DOMAIN}_studio")
        self.hass.async_create_background_task(self._tidy(), f"{DOMAIN}_studio_tidy")

    async def _tidy(self) -> None:
        """Once per start: shrink any painting still saved as PNG, note every file's size, and drop index entries
        whose file is gone and files nobody indexes (say, a repaint interrupted by a restart)."""

        def work() -> dict[str, tuple[str, int] | None]:
            """Runs in an executor (blocking file I/O): convert PNGs, measure files, delete strays; returns index fixes."""
            out: dict[str, tuple[str, int] | None] = {}
            known = set()
            for key, e in list(self.index.items()):
                name = e.get("file")
                if not name:
                    continue
                path = self.dir / name
                if not path.is_file():
                    out[key] = None
                    continue
                if name.endswith(".png"):
                    data, ext = shrink(path.read_bytes())
                    if ext == "webp":
                        new = name[:-4] + ".webp"
                        (self.dir / new).write_bytes(data)
                        path.unlink(missing_ok=True)
                        name, path = new, self.dir / new
                out[key] = (name, path.stat().st_size)
                known.add(name)
            for f in self.dir.iterdir():
                if (
                    f.is_file()
                    and f.suffix in (".png", ".webp", ".jpg")
                    and f.name not in known
                    and time.time() - f.stat().st_mtime > 3600
                ):  # not one being saved right now
                    f.unlink(missing_ok=True)
            return out

        try:
            found = await self.hass.async_add_executor_job(work)
        except OSError as err:
            _LOGGER.debug("Life RPG art tidy-up skipped: %s", err)
            return
        for key, info in found.items():
            entry = self.index.get(key)
            if entry is None:
                continue
            if info is None:
                self.index.pop(key, None)
            else:
                entry["file"], entry["bytes"] = info
        await self._prune()
        self.store.async_delay_save(lambda: {"index": self.index}, 5)

    async def async_stop(self) -> None:
        """Stop painting (on unload)."""
        if self._task:
            self._task.cancel()
        await self.store.async_save({"index": self.index})

    # --- lookups -------------------------------------------------------------------------------------
    def url(self, key: str) -> str | None:
        """URL of a finished painting, or None."""
        entry = self.index.get(key)
        if not entry or not entry.get("file"):
            return None
        entry["used"] = int(time.time())
        return f"{ART_URL}/{entry['file']}"

    def file_of(self, key: str) -> str | None:
        """The file name of a finished painting (it changes only when a repaint lands)."""
        return self.index.get(key, {}).get("file")

    def want(self, key: str, spec: dict[str, Any], priority: int, cfg: dict[str, Any] | None, seed: int) -> str | None:
        """Return the painting if it exists, otherwise queue it (when a painter is configured). A painting
        someone asked to repaint is shown until its replacement is ready. An edit waits for its base painting."""
        entry = self.index.get(key, {})
        found = self.url(key)
        if found and not entry.get("redo"):
            return found
        if not cfg:
            return found
        if spec.get("edit") and not self.file_of(spec["edit"]["base"]):
            return found
        seed = seed + 7919 * entry.get("v", 0)  # each repaint is a new picture of the same thing
        if found:  # a repaint: queue it first, keep showing the old one
            if key not in self.queue:
                self.queue[key] = {
                    "key": key,
                    "spec": spec,
                    "priority": 0,
                    "cfg": cfg,
                    "seed": seed,
                    "t": time.time(),
                    "seen": time.time(),
                }
                self._wake.set()
            return found
        failed = self.index.get(key, {}).get("failed_at", 0)
        if time.time() - failed < RETRY_FAILED:
            return None
        job = self.queue.get(key)
        if job is None:
            self.queue[key] = {
                "key": key,
                "spec": spec,
                "priority": priority,
                "cfg": cfg,
                "seed": seed,
                "t": time.time(),
                "seen": time.time(),
            }
            self._wake.set()
        else:
            job["seen"] = time.time()
            job["priority"] = min(priority, job["priority"])
        return None

    def redo(self, key: str) -> bool:
        """Paint this one again, with a new seed. The old painting stays until the new one is ready."""
        entry = self.index.get(key)
        if entry is None:
            return False
        entry["v"] = entry.get("v", 0) + 1
        entry.pop("failed_at", None)
        entry["redo"] = True
        self.store.async_delay_save(lambda: {"index": self.index}, 5)
        return True

    def key_for_url(self, url: str) -> str | None:
        """The painting a URL points at (the panel sends URLs back to ask for a repaint)."""
        name = str(url or "").split("?", 1)[0].rsplit("/", 1)[-1]
        return next((k for k, e in self.index.items() if e.get("file") == name), None) if name else None

    def pending(self, prefix: str) -> bool:
        """Is something with this key prefix waiting or painting?"""
        return any(k.startswith(prefix) for k in self.queue) or (self.status.get("current") or "").startswith(prefix)

    def summary(self) -> dict[str, Any]:
        """Studio state for the panel."""
        files = [e for e in self.index.values() if e.get("file")]
        return {
            **self.status,
            "queue": len(self.queue),
            "done": len(files),
            "bytes": sum(e.get("bytes", 0) for e in files),
            "repainting": [k for k, e in self.index.items() if e.get("redo")],
        }

    def forget_queue(self, keep: Callable[[dict[str, Any]], bool]) -> None:
        """Drop queued jobs nobody needs any more (e.g. an old portrait after a gear change)."""
        for key in [k for k, j in self.queue.items() if not keep(j)]:
            del self.queue[key]

    # --- the painter ---------------------------------------------------------------------------------
    async def _run(self) -> None:
        """The painter loop: take the most urgent job, paint it, save it, and sleep when the queue is empty."""
        while True:
            if not self.queue:
                self.status.update(state="idle", current=None)
                self._notify()
                self._wake.clear()
                await self._wake.wait()
                continue
            wait = self._offline_until - time.time()
            if wait > 0:
                self.status.update(state="offline")
                with contextlib.suppress(TimeoutError):  # woken early (settings changed) or the wait ran out
                    await asyncio.wait_for(self._wake.wait(), timeout=wait)
                self._wake.clear()
                continue
            now = time.time()
            for key in [k for k, j in self.queue.items() if now - j.get("seen", j["t"]) > STALE_JOB]:
                del self.queue[key]
            if not self.queue:
                continue
            job = min(self.queue.values(), key=lambda j: (j["priority"], j["t"]))
            self.status.update(state="painting", current=job["key"], error=None)
            self._notify()
            started = time.time()
            try:
                data = await self._paint(job)
                took = time.time() - started  # how long a painting takes, for the Gallery's estimate
                self.status["avg_s"] = round(
                    took if not self.status.get("avg_s") else 0.8 * self.status["avg_s"] + 0.2 * took, 1
                )
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("ComfyUI unreachable: %s", err)
                self._offline_until = time.time() + RETRY_OFFLINE
                self.status.update(error=f"ComfyUI isn't reachable at {job['cfg']['url']}.")
                continue
            except PaintError as err:
                _LOGGER.warning("Life RPG could not paint %s: %s", job["key"], err)
                self._failed(job, str(err)[:300])
                self.status.update(error=str(err)[:300])
                self.store.async_delay_save(lambda: {"index": self.index}, 30)
                continue
            except Exception:  # never let one bad painting stop the studio
                _LOGGER.exception("Unexpected error painting %s", job["key"])
                self._failed(job, "unexpected error")
                continue
            key, old = job["key"], self.index.get(job["key"], {})
            data, ext = await self.hass.async_add_executor_job(shrink, data)
            v = old.get("v", 0)
            name = f"{key}-{v}.{ext}" if v else f"{key}.{ext}"
            await self.hass.async_add_executor_job((self.dir / name).write_bytes, data)
            self.queue.pop(key, None)
            group = job["spec"].get("group")
            self.index[key] = {
                "file": name,
                "kind": job["spec"]["kind"],
                "used": int(time.time()),
                "bytes": len(data),
                **({"v": v} if v else {}),
                **({"group": group} if group else {}),
            }
            stale = [old.get("file")] if old.get("file") and old.get("file") != name else []
            if group:  # a new portrait replaces the adventurer's earlier ones
                for k in [k for k, e in self.index.items() if k != key and e.get("group") == group and e.get("file")]:
                    stale.append(self.index.pop(k)["file"])
            for n in stale:
                await self.hass.async_add_executor_job(lambda n=n: (self.dir / n).unlink(missing_ok=True))
            await self._prune()
            self.store.async_delay_save(lambda: {"index": self.index}, 30)
            self._notify()

    def _failed(self, job: dict[str, Any], error: str) -> None:
        """A painting failed: try again later. A repaint that failed keeps the painting it was replacing."""
        self.queue.pop(job["key"], None)
        entry = self.index.get(job["key"], {})
        if entry.get("file"):
            entry.pop("redo", None)
            entry["error"] = error
        else:
            self.index[job["key"]] = {"failed_at": int(time.time()), "error": error, "kind": job["spec"]["kind"]}

    async def _paint(self, job: dict[str, Any]) -> bytes:
        """Send one job to ComfyUI and wait for the picture; returns the image bytes."""
        cfg = job["cfg"]
        base = cfg["url"].rstrip("/")
        custom = None
        if cfg.get("family") == "custom":
            path = Path(self.hass.config.path(DOMAIN, "workflow.json"))
            try:
                custom = json.loads(await self.hass.async_add_executor_job(path.read_text))
            except (OSError, ValueError) as err:
                raise PaintError(f"Custom workflow {path} can't be read: {err}") from err
        workflow = build_workflow(job["spec"], cfg, job["seed"], custom)
        timeout = aiohttp.ClientTimeout(total=30)
        if (edit := job["spec"].get("edit")) and cfg.get("edit") and self.file_of(edit["base"]):
            try:  # paint it as an edit of its base painting, so the face stays the same
                image = await self._upload(base, edit["base"])
                return await self._comfy(base, build_edit_workflow(job["spec"], cfg, job["seed"], image), timeout)
            except PaintError as err:  # e.g. a node this ComfyUI doesn't have: paint it from the prompt instead
                _LOGGER.warning(
                    "Life RPG couldn't edit %s with %s (%s); painting it from the prompt instead",
                    job["key"],
                    cfg["edit"].get("model"),
                    err,
                )
        return await self._comfy(base, workflow, timeout)

    async def _upload(self, base: str, key: str) -> str:
        """Send a base painting to ComfyUI's input folder (as PNG); returns the name LoadImage wants."""
        path = self.dir / str(self.file_of(key))
        try:
            data = await self.hass.async_add_executor_job(lambda: as_png(path.read_bytes()))
        except (OSError, ValueError, ImportError) as err:
            raise PaintError(f"The base painting {path.name} can't be read: {err}") from err
        form = aiohttp.FormData()
        form.add_field("image", data, filename=f"{key}.png", content_type="image/png")
        form.add_field("type", "input")
        form.add_field("subfolder", UPLOAD_FOLDER)
        form.add_field("overwrite", "true")
        async with async_get_clientsession(self.hass).post(
            f"{base}/upload/image", data=form, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            body = await resp.json(content_type=None) if resp.status == 200 else None
        if not isinstance(body, dict) or not body.get("name"):
            raise PaintError("ComfyUI didn't accept the base painting upload")
        return f"{body.get('subfolder') or UPLOAD_FOLDER}/{body['name']}"

    async def _comfy(self, base: str, workflow: dict[str, Any], timeout: aiohttp.ClientTimeout) -> bytes:
        """Queue one workflow and wait for its image."""
        session = async_get_clientsession(self.hass)
        async with session.post(
            f"{base}/prompt", json={"prompt": workflow, "client_id": f"life_rpg-{uuid.uuid4()}"}, timeout=timeout
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200 or "prompt_id" not in body:
                raise PaintError(_comfy_error(body))
        prompt_id = body["prompt_id"]
        started = time.monotonic()
        while time.monotonic() - started < JOB_TIMEOUT:
            await asyncio.sleep(POLL)
            async with session.get(f"{base}/history/{prompt_id}", timeout=timeout) as resp:
                hist = (await resp.json(content_type=None)).get(prompt_id)
            if not hist:
                continue
            status = hist.get("status", {})
            if status.get("status_str") == "error":
                raise PaintError(_comfy_error(status))
            images = [
                img
                for out in hist.get("outputs", {}).values()
                for img in out.get("images", [])
                if img.get("type", "output") in ("output", "temp")
            ]
            if images:
                img = images[0]
                async with session.get(
                    f"{base}/view",
                    params={
                        "filename": img["filename"],
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output"),
                    },
                    timeout=timeout,
                ) as resp:
                    if resp.status != 200:
                        raise PaintError(f"ComfyUI returned {resp.status} for the finished image")
                    if (resp.content_length or 0) > MAX_BYTES:
                        raise PaintError("The finished image is too large")
                    data = bytearray()
                    async for chunk in resp.content.iter_chunked(65536):
                        data += chunk
                        if len(data) > MAX_BYTES:
                            raise PaintError("The finished image is too large")
                    if not data.startswith(IMAGE_MAGIC):
                        raise PaintError("ComfyUI didn't return an image")
                    return bytes(data)
            if status.get("completed"):
                raise PaintError(
                    "ComfyUI finished without an image (does the workflow have a SaveImage or PreviewImage node?)"
                )
        raise PaintError("ComfyUI took longer than 15 minutes")

    async def _prune(self) -> None:
        """Keep the art folder within its size budget: forget old failures, then delete the least recently used."""
        old = time.time() - 4 * RETRY_FAILED
        for key in [k for k, e in self.index.items() if not e.get("file") and e.get("failed_at", 0) < old]:
            del self.index[key]  # forget long-past failures
        files = sorted((e.get("used", 0), k) for k, e in self.index.items() if e.get("file"))
        total = sum(self.index[k].get("bytes", 0) for _, k in files)
        recent = time.time() - KEEP_RECENT  # never delete something still on screen, or it would be painted again
        for used, key in files:
            over_count, over_size = len(files) > MAX_FILES, total > MAX_TOTAL
            if not (over_count or over_size) or (used > recent and total <= HARD_TOTAL):
                break
            if used > time.time() - 3600:  # on screen right now
                break
            entry = self.index.pop(key)
            total -= entry.get("bytes", 0)
            files = files[1:]
            await self.hass.async_add_executor_job(lambda n=entry["file"]: (self.dir / n).unlink(missing_ok=True))

    @callback
    def _notify(self) -> None:
        """Tell every listener (the panel's subscriptions) that the painter's status changed."""
        for listener in list(self.listeners):
            listener()


def as_png(data: bytes) -> bytes:
    """A painting as PNG (what every ComfyUI build can load)."""
    if data.startswith(b"\x89PNG"):
        return data
    from PIL import Image  # noqa: PLC0415

    with Image.open(io.BytesIO(data)) as im:
        out = io.BytesIO()
        im.convert("RGB").save(out, "PNG")
    return out.getvalue()


def shrink(data: bytes) -> tuple[bytes, str]:
    """A painting as WebP (Pillow ships with Home Assistant); unchanged PNG if that isn't possible."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return data, "png"
    try:
        with Image.open(io.BytesIO(data)) as im:
            out = io.BytesIO()
            im.convert("RGB").save(out, "WEBP", quality=WEBP_QUALITY, method=4)
    except (OSError, ValueError):
        return data, "png"
    webp = out.getvalue()
    return (webp, "webp") if webp.startswith(b"RIFF") and len(webp) < len(data) else (data, "png")


class PaintError(Exception):
    """ComfyUI refused or failed a painting."""


def _comfy_error(body: Any) -> str:
    """The useful part of a ComfyUI error response."""
    if not isinstance(body, dict):
        return str(body)[:300]
    err = body.get("error")
    msg = err.get("message") if isinstance(err, dict) else err
    details = []
    for node in (body.get("node_errors") or {}).values():
        for e in node.get("errors", []):
            details.append(f"{node.get('class_type', '?')}: {e.get('message')} {e.get('details', '')}".strip())
    for m in body.get("messages", []) or []:
        if isinstance(m, list) and len(m) > 1 and m[0] == "execution_error":
            details.append(str(m[1].get("exception_message", "")).strip())
    return "; ".join([str(msg or "ComfyUI error"), *details])[:300]
