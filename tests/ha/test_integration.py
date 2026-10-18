"""Integration test: the whole Home Assistant side (setup, config and options flows, coordinator, sensors, buttons,
services, websocket API, Assist tools, the art studio and the LLM writer) against Home Assistant stand-ins
(stubs.py), a fake ComfyUI that checks every workflow against ComfyUI's real node signatures, and a fake AI Task LLM.

Run: python3 tests/ha/test_integration.py      (needs voluptuous and Pillow: pip install voluptuous pillow)
"""

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types

sys.path.insert(0, str(Path(__file__).parent))  # for stubs.py

from stubs import *  # noqa: F403,E402
from stubs import NOW, REGISTERED, TZ, WS, ConfigEntry, Conn, HomeAssistant, State, Users, mod, sel  # noqa: E402

TMP = Path(tempfile.mkdtemp())
H_NOW_REF = NOW
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAX+XDSwAAAABJRU5ErkJggg=="
)


# --- more HA stubs --------------------------------------------------------------------------------
class HomeAssistantError(Exception):
    pass


class Unauthorized(HomeAssistantError):
    def __init__(self, context=None, **kw):
        super().__init__("unauthorized")


mod("homeassistant.exceptions", HomeAssistantError=HomeAssistantError, Unauthorized=Unauthorized)
core = sys.modules["homeassistant.core"]
core.ServiceCall = object
core.ServiceResponse = dict
core.SupportsResponse = types.SimpleNamespace(OPTIONAL="optional")
sys.modules["homeassistant.const"].Platform.BUTTON = "button"


class ButtonEntity:
    pass


mod("homeassistant.components.button", ButtonEntity=ButtonEntity)
SERVICES = {}
mod("homeassistant.util.json", JsonObjectType=dict)
sys.modules["homeassistant.util"].json = sys.modules["homeassistant.util.json"]


@dataclass(slots=True)
class LLMContext:
    platform: str
    context: object
    language: str | None
    assistant: str
    device_id: str | None


@dataclass(slots=True)
class ToolInput:
    tool_name: str
    tool_args: dict


class Tool:
    name = ""
    description = None
    parameters = None


@dataclass
class APIInstance:
    api: object
    api_prompt: str
    llm_context: LLMContext
    tools: list
    custom_serializer: object = None


@dataclass(slots=True, kw_only=True)
class API:
    hass: object
    id: str
    name: str


APIS = {}
llm_mod = mod(
    "homeassistant.helpers.llm",
    Tool=Tool,
    API=API,
    APIInstance=APIInstance,
    LLMContext=LLMContext,
    ToolInput=ToolInput,
    async_register_api=lambda h, api: APIS.setdefault(api.id, api),
)
sys.modules["homeassistant.helpers"].llm = llm_mod
sel.TextSelector = sel.EntitySelector
sel.TextSelectorConfig = dict
sel.TextSelectorType = types.SimpleNamespace(URL="url")
sel.ConversationAgentSelector = sel.EntitySelector
sel.ConversationAgentSelectorConfig = dict
sel.NumberSelectorMode.SLIDER = "slider"
CONVERSE = []  # (data, user_id) for each conversation.process call


# aiohttp stand-in (only what art.py uses)
class ClientError(Exception):
    pass


class ClientConnectionError(ClientError):
    pass


class FormData:
    def __init__(self):
        self.fields = []

    def add_field(self, name, value, filename=None, content_type=None):
        self.fields.append((name, value, filename, content_type))


mod(
    "aiohttp",
    ClientError=ClientError,
    ClientConnectionError=ClientConnectionError,
    ClientTimeout=lambda total=None: total,
    FormData=FormData,
)

# --- fake ComfyUI: checks workflows against the real node signatures ---------------------------------
REQUIRED = {  # from ComfyUI nodes.py / comfy_extras/nodes_flux.py
    "CheckpointLoaderSimple": {"ckpt_name"},
    "CLIPTextEncode": {"text", "clip"},
    "VAEDecode": {"samples", "vae"},
    "EmptyLatentImage": {"width", "height", "batch_size"},
    "KSampler": {
        "model",
        "seed",
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
        "positive",
        "negative",
        "latent_image",
        "denoise",
    },
    "SaveImage": {"images", "filename_prefix"},
    "ImageScale": {"image", "upscale_method", "width", "height", "crop"},
    "FluxGuidance": {"conditioning", "guidance"},
    "PreviewImage": {"images"},
    "UNETLoader": {"unet_name", "weight_dtype"},
    "DualCLIPLoader": {"clip_name1", "clip_name2", "type"},
    "VAELoader": {"vae_name"},
    # image-edit models (comfy_extras/nodes_flux.py, nodes_edit_model.py, nodes_qwen.py, nodes_post_processing.py)
    "LoadImage": {"image"},
    "VAEEncode": {"pixels", "vae"},
    "FluxKontextImageScale": {"image"},
    "ReferenceLatent": {"conditioning"},
    "ConditioningZeroOut": {"conditioning"},
    "CLIPLoader": {"clip_name", "type"},
    "ImageScaleToTotalPixels": {"image", "upscale_method", "megapixels"},
    "TextEncodeQwenImageEditPlus": {"clip", "prompt"},
    "ModelSamplingAuraFlow": {"model", "shift"},
}
UNETS = ["flux1-dev.safetensors", "flux1-kontext-dev.safetensors", "qwen_image_edit_2509_fp8_e4m3fn.safetensors"]
QWEN_TE = ["qwen_2.5_vl_7b_fp8_scaled.safetensors"]
ENCODERS = ["clip_l.safetensors", "t5xxl_fp8_e4m3fn.safetensors", "t5xxl_fp16.safetensors"]
VAES = ["ae.safetensors", "sdxl_vae.safetensors", "qwen_image_vae.safetensors"]
SAMPLERS = {"euler", "dpmpp_2m", "dpmpp_2m_sde"}
SCHEDULERS = {"simple", "karras", "normal"}
CKPTS = ["juggernautXL_v9.safetensors", "flux1-dev-fp8.safetensors"]


class FakeComfy:
    def __init__(self):
        self.online, self.prompts, self.history, self.fail_next = True, [], {}, False
        self.uploads, self.no_edit_nodes = {}, False

    def validate(self, wf):
        errors = {}
        for nid, node in wf.items():
            req = REQUIRED.get(node["class_type"])
            if req is None:
                errors[nid] = f"unknown node {node['class_type']}"
                continue
            if missing := req - set(node["inputs"]):
                errors[nid] = f"missing {missing}"
            for v in node["inputs"].values():
                if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] not in wf:
                    errors[nid] = f"link to missing node {v[0]}"
            if node["class_type"] == "KSampler":
                i = node["inputs"]
                if (
                    i["sampler_name"] not in SAMPLERS
                    or i["scheduler"] not in SCHEDULERS
                    or not isinstance(i["seed"], int)
                ):
                    errors[nid] = "bad sampler settings"
            if node["class_type"] == "CheckpointLoaderSimple" and node["inputs"]["ckpt_name"] not in CKPTS:
                errors[nid] = "unknown checkpoint"
            if node["class_type"] == "UNETLoader" and (
                node["inputs"]["unet_name"] not in UNETS
                or node["inputs"]["weight_dtype"] not in ("default", "fp8_e4m3fn")
            ):
                errors[nid] = "unknown diffusion model"
            if node["class_type"] == "DualCLIPLoader" and (
                node["inputs"]["clip_name1"] not in ENCODERS
                or node["inputs"]["clip_name2"] not in ENCODERS
                or node["inputs"]["type"] != "flux"
            ):
                errors[nid] = "unknown text encoder"
            if node["class_type"] == "VAELoader" and node["inputs"]["vae_name"] not in VAES:
                errors[nid] = "unknown vae"
            if node["class_type"] == "CLIPLoader" and (
                node["inputs"]["clip_name"] not in QWEN_TE or node["inputs"]["type"] != "qwen_image"
            ):
                errors[nid] = "unknown text encoder"
            if node["class_type"] == "LoadImage" and node["inputs"]["image"] not in self.uploads:
                errors[nid] = f"Invalid image file: {node['inputs']['image']}"
            if self.no_edit_nodes and node["class_type"] in (
                "ReferenceLatent",
                "FluxKontextImageScale",
                "TextEncodeQwenImageEditPlus",
            ):
                errors[nid] = f"unknown node {node['class_type']}"
            if node["class_type"] == "ImageScale" and node["inputs"]["upscale_method"] not in (
                "nearest-exact",
                "bilinear",
                "area",
                "bicubic",
                "bislerp",
            ):
                errors[nid] = "bad upscale"
        if not any(n["class_type"] in ("SaveImage", "PreviewImage") for n in wf.values()):
            errors["-"] = "no output"
        return errors

    def handle(self, method, url, body=None, params=None):
        if not self.online:
            raise ClientConnectionError("connection refused")
        path = url.split("8188", 1)[1]
        if path == "/object_info/CheckpointLoaderSimple":
            return 200, {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [CKPTS, {}]}}}}
        if path == "/object_info/UNETLoader":  # newer ComfyUI: ["COMBO", {"options": [...]}]
            return 200, {
                "UNETLoader": {
                    "input": {
                        "required": {
                            "unet_name": ["COMBO", {"options": UNETS}],
                            "weight_dtype": [["default", "fp8_e4m3fn"]],
                        }
                    }
                }
            }
        if path == "/object_info/DualCLIPLoader":
            return 200, {
                "DualCLIPLoader": {
                    "input": {
                        "required": {
                            "clip_name1": [ENCODERS],
                            "clip_name2": [ENCODERS],
                            "type": [["sdxl", "sd3", "flux"]],
                        }
                    }
                }
            }
        if path == "/object_info/VAELoader":
            return 200, {"VAELoader": {"input": {"required": {"vae_name": [VAES]}}}}
        if path == "/object_info/CLIPLoader":
            return 200, {
                "CLIPLoader": {
                    "input": {"required": {"clip_name": [QWEN_TE], "type": [["stable_diffusion", "qwen_image"]]}}
                }
            }
        if path == "/upload/image" and method == "POST":
            f = {name: (value, filename) for name, value, filename, _ in body.fields}
            data, filename = f["image"]
            assert data.startswith(b"\x89PNG") and f["type"][0] == "input" and f["overwrite"][0] == "true", f.keys()
            name = f"{f['subfolder'][0]}/{filename}"
            self.uploads[name] = data
            return 200, {"name": filename, "subfolder": f["subfolder"][0], "type": "input"}
        if path == "/prompt" and method == "POST":
            wf = body["prompt"]
            errs = self.validate(wf)
            if self.fail_next:
                self.fail_next = False
                errs = {"5": "forced"}
            if errs:
                return 400, {
                    "error": {
                        "type": "prompt_outputs_failed_validation",
                        "message": "Prompt outputs failed validation",
                    },
                    "node_errors": {
                        k: {
                            "class_type": wf.get(k, {}).get("class_type", "?"),
                            "errors": [{"message": v, "details": ""}],
                        }
                        for k, v in errs.items()
                    },
                }
            pid = f"p{len(self.prompts)}"
            self.prompts.append(wf)
            self.history[pid] = 1  # appears after one poll
            return 200, {"prompt_id": pid, "number": len(self.prompts), "node_errors": {}}
        if path.startswith("/history/"):
            pid = path.rsplit("/", 1)[1]
            if self.history.get(pid, 0) > 0:
                self.history[pid] -= 1
                return 200, {}
            wf = self.prompts[int(pid[1:])]
            save = next(k for k, n in wf.items() if n["class_type"] in ("SaveImage", "PreviewImage"))
            if wf[save]["class_type"] == "SaveImage":  # custom workflows: ComfyUI's output folder
                img = {
                    "filename": wf[save]["inputs"]["filename_prefix"].split("/")[-1] + "_00001_.png",
                    "subfolder": "life_rpg",
                    "type": "output",
                }
            else:  # built-in workflows: ComfyUI's temp folder, so its output folder doesn't fill up
                img = {"filename": f"ComfyUI_temp_{pid}_00001_.png", "subfolder": "", "type": "temp"}
            return 200, {
                pid: {"outputs": {save: {"images": [img]}}, "status": {"status_str": "success", "completed": True}}
            }
        if path == "/view":
            assert (params["type"], params["subfolder"]) in (("output", "life_rpg"), ("temp", "")), params
            return 200, PNG
        return 404, {}


COMFY = FakeComfy()


class _Content:
    def __init__(self, data):
        self.data = data

    async def iter_chunked(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i : i + n]


class Resp:
    def __init__(self, status, payload):
        self.status, self.payload = status, payload
        self.content_length = len(payload) if isinstance(payload, bytes) else None
        self.content = _Content(payload if isinstance(payload, bytes) else b"")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self.payload

    async def read(self):
        return self.payload


class _Ctx:
    def __init__(self, method, url, **kw):
        self.args = (method, url, kw)

    async def __aenter__(self):
        method, url, kw = self.args
        status, payload = COMFY.handle(
            method, url, kw.get("json") if "json" in kw else kw.get("data"), kw.get("params")
        )
        return Resp(status, payload)

    async def __aexit__(self, *a):
        return False


class Session:
    def get(self, url, **kw):
        return _Ctx("GET", url, **kw)

    def post(self, url, **kw):
        return _Ctx("POST", url, **kw)


mod("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda h: Session())

# --- fake AI Task (an LLM that answers in the requested structure) ------------------------------------
LLM_CALLS = []


@dataclass
class GenDataTaskResult:
    conversation_id: str
    data: object


async def async_generate_data(
    hass, *, task_name, entity_id=None, instructions, structure=None, attachments=None, llm_api=None, context=None
):
    """The fake AI Task: canned answers shaped like what each kind of writing asks for."""
    LLM_CALLS.append((task_name, instructions))
    if entity_id == "ai_task.broken":
        raise HomeAssistantError("model offline")
    keys = [str(k) for k in structure.schema] if structure is not None else ["text"]
    if "tasks" in keys:
        data = {"tasks": ["Stretch your arms up high", "Put three things back where they belong", "Smile at someone"]}
    elif "reply" in keys:
        data = {"reply": "Oh, my only believer! You walked so far today. I'm proud of you.", "mood": "proud"}
        if "Merchant" in task_name:
            data = {"text": "Bah! Fine."}
    else:
        data = {"text": f"[{task_name}] A tale is told."}
    structure(data) if structure is not None else None  # the result must fit the schema
    return GenDataTaskResult("c1", data)


ai = mod("homeassistant.components.ai_task", async_generate_data=async_generate_data)
sys.modules["homeassistant.components"].ai_task = ai


# --- HomeAssistant extras -------------------------------------------------------------------------------
def hass_factory():
    """A fresh Home Assistant stand-in with users, services, an executor and static paths."""
    hass = HomeAssistant()
    hass.auth = Users()

    async def get_user(uid):
        return types.SimpleNamespace(id=uid, is_admin=uid == "admin")

    hass.auth.async_get_user = get_user
    hass.data = {}
    hass.config = types.SimpleNamespace(location_name="Home", country="US", path=lambda *p: str(TMP.joinpath(*p)))
    hass.bus = types.SimpleNamespace(async_listen_once=lambda e, f: None)

    async def call_service(domain, service, data, blocking=False, return_response=False, context=None):
        assert (domain, service) == ("conversation", "process") and blocking and return_response, (domain, service)
        CONVERSE.append((data, getattr(context, "user_id", None)))
        said = data["text"].rsplit("\n\n", 1)[-1]
        return {
            "response": {"speech": {"plain": {"speech": f"Oh, '{said}'? Tell me more, I'm so proud of you!"}}},
            "conversation_id": "conv-1",
        }

    hass.services = types.SimpleNamespace(
        async_register=lambda d, n, f, schema=None, supports_response=None: SERVICES.setdefault(n, (f, schema)),
        async_call=call_service,
    )

    async def executor(f, *a):
        return f(*a)

    hass.async_add_executor_job = executor
    hass.async_create_background_task = lambda coro, name: asyncio.get_running_loop().create_task(coro)

    async def reg_static(cfgs):
        REGISTERED["static"] = cfgs

    hass.http = types.SimpleNamespace(async_register_static_paths=reg_static)
    return hass


def utc(y, mo, d, h, mi=0):
    """A UTC datetime."""
    return datetime(y, mo, d, h, mi, tzinfo=TZ).astimezone(timezone.utc)


def iso(dt):
    """A datetime as an ISO string, the way Home Assistant states carry times."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def settle(studio, timeout=20):
    """Wait until the painter has finished every queued job."""
    for _ in range(int(timeout / 0.02)):
        if not studio.queue and studio.status["state"] in ("idle",):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"studio didn't finish: {studio.summary()}")


async def main():
    """Run every check in order; any failed assert stops the run."""
    import life_rpg
    from life_rpg import art, config_flow, coordinator as coord_mod, event as event_mod, sensor as sensor_mod, websocket

    art.POLL = 0.01
    hass = hass_factory()
    assert await life_rpg.async_setup(hass, {})
    studio = hass.data["life_rpg"]["studio"]
    assert {c[0][0] for c in REGISTERED["static"]} == {"/life_rpg_static", "/life_rpg_art"}
    assert "ws_chat" in WS and "life_rpg" in APIS

    # --- config + options flows
    flow = config_flow.LifeRPGConfigFlow()
    flow.hass = hass
    form = await flow.async_step_user()
    defaults = form["data_schema"]({"name": "Kai"})
    assert defaults["body"] == "androgynous"
    created = await flow.async_step_user(
        {
            **defaults,
            "name": "Kai",
            "user_id": "u1",
            "race": "elf",
            "body": "feminine",
            "steps_entity": "sensor.p_steps",
            "sleep_entity": "sensor.p_sleep",
            "hydration_entity": "sensor.p_water",
        }
    )
    opt = config_flow.LifeRPGOptionsFlow()
    opt.hass = hass
    opt.config_entry = types.SimpleNamespace(options=created["options"])
    assert (await opt.async_step_init())["menu_options"] == ["quests", "bounties", "goddess", "work", "studio"]
    form = await opt.async_step_studio()
    assert form["description_placeholders"]["found"] == "—"
    bad = await opt.async_step_studio(
        {
            "body": "feminine",
            "comfyui_url": "http://comfy:8188/",
            "model_family": "sdxl",
            "paint": ["portrait", "items", "guardians", "characters"],
            "llm_features": ["lune_chat", "flavour", "haggling"],
        }
    )
    assert bad["errors"] == {"checkpoint": "pick_checkpoint"} and bad["description_placeholders"]["found"] == "2", bad
    COMFY.online = False
    off = await opt.async_step_studio(
        {
            "body": "feminine",
            "comfyui_url": "http://comfy:8188",
            "model_family": "sdxl",
            "checkpoint": CKPTS[0],
            "paint": [],
            "llm_features": [],
        }
    )
    assert off["errors"] == {"comfyui_url": "cannot_connect"}
    COMFY.online = True
    done = await opt.async_step_studio(
        {
            "body": "feminine",
            "comfyui_url": "http://comfy:8188/",
            "model_family": "sdxl",
            "checkpoint": CKPTS[0],
            "paint": ["portrait", "items", "guardians", "characters"],
            "ai_task_entity": "ai_task.ollama",
            "llm_features": ["lune_chat", "flavour", "haggling"],
        }
    )
    assert (
        done["type"] == "create_entry"
        and done["data"]["race"] == "elf"
        and done["data"]["comfyui_url"] == "http://comfy:8188"
    ), done
    studio_in = {"body": "feminine", "comfyui_url": "http://comfy:8188", "paint": ["portrait"], "llm_features": []}
    wrong = await opt.async_step_studio({**studio_in, "model_family": "sdxl", "checkpoint": "flux1-dev.safetensors"})
    assert wrong["errors"] == {"checkpoint": "not_in_folder"}, wrong
    switch = await opt.async_step_studio({**studio_in, "model_family": "flux_unet"})
    assert (
        switch["errors"] == {"checkpoint": "pick_checkpoint"}
        and switch["description_placeholders"]["folder"] == "diffusion_models"
    ), switch
    fu = await opt.async_step_studio({**studio_in, "model_family": "flux_unet", "checkpoint": "flux1-dev.safetensors"})
    assert (
        fu["type"] == "create_entry"
        and fu["data"]["flux_t5"] == "t5xxl_fp16.safetensors"
        and fu["data"]["flux_vae"] == "ae.safetensors"
    ), fu
    VAES.remove("ae.safetensors")
    gap = await opt.async_step_studio({**studio_in, "model_family": "flux_unet", "checkpoint": "flux1-dev.safetensors"})
    assert (
        gap["errors"] == {"model_family": "flux_parts"}
        and "ae.safetensors" in gap["description_placeholders"]["missing"]
    ), gap
    VAES.insert(0, "ae.safetensors")
    FLUX_UNET_OPTIONS = fu["data"]
    print("  flux in separate files: options flow ok")
    q = await opt.async_step_quests(
        {
            "user_id": "u1",
            "steps_entity": "sensor.p_steps",
            "sleep_entity": "sensor.p_sleep",
            "hydration_entity": "sensor.p_water",
            "steps_goal": 8000,
            "sleep_goal": 7.5,
            "bedtime_quest": True,
            "bedtime_goal": "23:00:00",
            "floors_goal": 10,
            "hydration_goal": 2000,
        }
    )
    assert q["data"]["race"] == "elf" and q["data"]["body"] == "feminine", q  # saving one page keeps the rest

    # --- coordinator: play, paint, write
    entry = ConfigEntry(done["data"], title="Kai")
    entry.entry_id = "abc123"
    c = coord_mod.LifeRPGCoordinator(hass, entry)
    entry.runtime_data = c

    async def _unload(e, p):
        return True

    hass.config_entries = types.SimpleNamespace(async_loaded_entries=lambda d: [entry], async_unload_platforms=_unload)
    await c._async_setup()
    S = hass._states
    S["sensor.p_sleep"] = State(
        "470",
        {
            "unit_of_measurement": "min",
            "startTime": iso(utc(2026, 10, 11, 22, 40)),
            "endTime": iso(utc(2026, 10, 12, 6, 30)),
        },
    )
    S["sensor.p_steps"] = State("8400", {"endTime": iso(utc(2026, 10, 12, 8, 55))})
    S["sensor.p_water"] = State("1.1", {"unit_of_measurement": "L", "endTime": iso(utc(2026, 10, 12, 8, 50))})
    await c.async_refresh()
    v = c.data
    assert v["art"]["studio"]["state"] in ("idle", "painting") and studio.queue, studio.summary()
    first_prio = min(studio.queue.values(), key=lambda j: (j["priority"], j["t"]))
    assert first_prio["spec"]["kind"] == "portrait"
    assert not any(e["item"]["art"] for e in v["market"]["stock"] if e["kind"] == "gear") and not v["market"]["seen"]
    await c.async_action("market_seen")  # the panel opened the Market: now its goods are painted
    assert c.data["market"]["seen"]
    await settle(studio)
    await c.async_refresh()
    v = c.data
    assert v["art"]["portrait"] and v["art"]["portrait_current"], v["art"]
    assert v["labyrinth"]["art"] and all(i["art"] for i in v["gear"]["inventory"]), [
        i.get("art") for i in v["gear"]["inventory"]
    ]
    assert all(e["item"]["art"] for e in v["market"]["stock"] if e["kind"] == "gear")
    assert v["goddess"]["art"][v["goddess"]["mood"]] and v["market"]["art"][v["market"]["mood"]]
    files = [f for f in (TMP / "life_rpg" / "art").iterdir() if f.suffix in (".png", ".webp")]
    # saved as WebP when Pillow is installed (it ships with Home Assistant), else as the PNG ComfyUI sent
    assert files and all(f.read_bytes() == PNG or f.read_bytes().startswith(b"RIFF") for f in files)
    portrait_wf = next(w for w in COMFY.prompts if w["2"]["inputs"]["text"].startswith("Full-body character portrait"))
    assert portrait_wf["8"]["class_type"] == "PreviewImage", "built-in workflows leave ComfyUI's output folder alone"
    text = portrait_wf["2"]["inputs"]["text"]
    assert "elf woman" in text and portrait_wf["5"]["inputs"]["sampler_name"] == "dpmpp_2m", text
    print(f"  painted {len(files)} pictures; portrait prompt: {text[:160]}...")
    # gear change -> a new portrait queues; old one shows meanwhile
    old_portrait = v["art"]["portrait"]
    spare = next((i for i in c.game.L["inv"] if i["id"] not in c.game.L["equip"].values()), None)
    if spare:
        await c.async_action("equip", item_id=spare["id"])
        assert c.data["art"]["portrait"] == old_portrait and not c.data["art"]["portrait_current"]
        await settle(studio)
        await c.async_refresh()
        assert c.data["art"]["portrait"] != old_portrait and c.data["art"]["portrait_current"]
    # comfy errors and outages
    COMFY.fail_next = True
    await c.async_action("repaint")
    await settle(studio)
    failed = [e for e in studio.index.values() if e.get("error")]
    assert failed and "forced" in failed[0]["error"], failed
    COMFY.online = False
    await c.async_action("restyle")
    for _ in range(100):
        if studio.status["state"] == "offline":
            break
        await asyncio.sleep(0.02)
    assert studio.status["state"] == "offline" and "reach" in studio.status["error"]
    COMFY.online = True
    studio._offline_until = 0
    studio._wake.set()
    await settle(studio)
    # flux + custom workflows
    flux = art.build_workflow(
        {"kind": "item", "prompt": "p", "negative": "n", "w": 1024, "h": 1024, "out_w": 384, "out_h": 384},
        {"family": "flux", "checkpoint": CKPTS[1]},
        7,
    )
    assert (
        not COMFY.validate(flux) and flux["5"]["inputs"]["positive"] == ["9", 0] and flux["5"]["inputs"]["cfg"] == 1.0
    )
    parts = art.pick_flux_parts(ENCODERS, VAES)
    assert parts == {"clip_l": "clip_l.safetensors", "t5": "t5xxl_fp16.safetensors", "vae": "ae.safetensors"}, parts
    assert art.pick_flux_parts(["t5xxl_fp8_e4m3fn.safetensors"], ["sdxl_vae.safetensors"]) == {
        "clip_l": None,
        "t5": "t5xxl_fp8_e4m3fn.safetensors",
        "vae": None,
    }
    unet = art.build_workflow(
        {"kind": "item", "prompt": "p", "negative": "n", "w": 1024, "h": 1024, "out_w": 384, "out_h": 384},
        {"family": "flux_unet", "checkpoint": UNETS[0], "parts": parts},
        7,
    )
    assert not COMFY.validate(unet), COMFY.validate(unet)
    assert (
        unet["1"]["class_type"] == "UNETLoader"
        and unet["2"]["inputs"]["clip"] == ["10", 0]
        and unet["6"]["inputs"]["vae"] == ["11", 0]
    )
    assert await art.list_checkpoints(hass, "http://comfy:8188", "flux_unet") == UNETS
    custom = art.build_workflow(
        {"kind": "item", "prompt": "a sword", "negative": "n", "w": 1024, "h": 1024, "out_w": 384, "out_h": 384},
        {"family": "custom"},
        42,
        {"1": {"class_type": "X", "inputs": {"text": "best, %PROMPT%", "seed": "%SEED%", "w": "%WIDTH%"}}},
    )
    assert custom["1"]["inputs"] == {"text": "best, a sword", "seed": 42, "w": 1024}

    # LLM: flavour writing, Lune, the merchant
    for _ in range(50):
        await c.async_refresh()
        await asyncio.sleep(0.02)
        if all(c.game.L["lore"].get(k) for k in ("morning", "guardian")) and (
            not c.data["choice"] or c.game.L["lore"].get("choice")
        ):
            break
    lore = c.game.L["lore"]
    assert (
        lore["morning"]["text"].startswith("[Life RPG: morning]")
        and lore["guardian"]["ref"] == c.data["labyrinth"]["floor"]
    ), lore
    print("  lore written:", sorted(lore))
    owner, guest = Conn("u1"), Conn("u2")
    await websocket.ws_chat(hass, owner, {"id": 1, "entry_id": "abc123", "who": "lune", "text": "Lune, how did I do?"})
    assert owner.out[-1][0] == "result" and owner.out[-1][2]["mood"] == "proud", owner.out[-1]
    assert c.data["lune_chat"][-1]["role"] == "lune"
    websocket.ws_subscribe(hass, guest, {"id": 20, "entry_id": "abc123"})
    watched = guest.out[-1][2]["view"]
    assert watched["lune_chat"] == [] and c.data["lune_chat"], "watchers must not see private chats"
    await websocket.ws_chat(hass, guest, {"id": 2, "entry_id": "abc123", "who": "lune", "text": "hi"})
    assert guest.out[-1][2] == "unauthorized"
    gear = next(e for e in c.data["market"]["stock"] if e["kind"] == "gear" and not e["sold"])
    await websocket.ws_chat(
        hass,
        owner,
        {
            "id": 3,
            "entry_id": "abc123",
            "who": "merchant",
            "stock_id": gear["id"],
            "text": f"I'll give you {int(gear['list'] * 0.6):,} gold for it",
        },
    )
    res = owner.out[-1][2]
    assert (
        res["result"] in ("countered", "holding", "final")
        and "Merchant" in res["reply"]
        and res["offer"] == int(gear["list"] * 0.6)
    ), res
    assert gear["list"] * 0.7 <= res["price"] <= gear["list"] and res["face"] in ("fair", "stubborn", "annoyed"), res
    print("  merchant:", res["result"], res["price"], "list", gear["list"])

    # Assist tools
    api = APIS["life_rpg"]
    ctx = LLMContext("ollama", types.SimpleNamespace(user_id="u1"), "en", "conversation", None)
    inst = await api.async_get_api_instance(ctx)
    tools = {t.name: t for t in inst.tools}
    call = lambda name, ctx=ctx, **a: tools[name].async_call(hass, ToolInput(name, a), ctx)  # noqa: E731
    st = await call("life_rpg_status")
    json.dumps(st)
    assert st["adventurer"] == "Kai" and "guardian" in st and st["gold"] >= 0
    shop = await call("life_rpg_shop")
    c.game.L["gold"] = 50_000
    cons = next(s for s in shop["stock"] if s["kind"] == "consumable" and not s["sold"])
    h = await call("life_rpg_haggle", item=cons["name"], offer=int(cons["list_price"] * 0.9))
    b = await call("life_rpg_buy", item=str(cons["id"]))
    assert b["success"] and b["bought"] == cons["name"], b
    used = await call("life_rpg_use", item=cons["name"])
    print("  assist:", h["result"], "->", b["bought"], "| use:", used.get("effect") or used.get("error"))
    sold = await call("life_rpg_sell", item="junk")
    assert "gold_received" in sold
    lune = await call("life_rpg_talk_to_goddess", message="Good night!")
    assert "proud" in lune["she_says"] and lune["goddess"] == "Lune"
    sat = LLMContext("ollama", None, "en", "conversation", "satellite")  # a voice satellite: the only adventurer
    assert (await call("life_rpg_status", ctx=sat))["adventurer"] == "Kai"
    other = LLMContext("ollama", types.SimpleNamespace(user_id="u2"), "en", "conversation", None)
    try:
        await call("life_rpg_buy", ctx=other, item="anything")
        raise AssertionError("another user acted for Kai")
    except HomeAssistantError as err:
        assert "Only Kai" in str(err)
    # sensors + events still fine
    ents = []
    await sensor_mod.async_setup_entry(hass, entry, lambda e: ents.extend(e))
    await event_mod.async_setup_entry(hass, entry, lambda e: ents.extend(e))
    for e in ents:
        await e.async_added_to_hass()
        if isinstance(e, sensor_mod.RPGSensor):
            json.dumps([e.native_value, e.extra_state_attributes])
    gold = next(e for e in ents if getattr(e, "_attr_translation_key", "") == "gold")
    print("  sensor gold:", gold.native_value, gold.extra_state_attributes)
    json.dumps(c.data)
    # --- goddess name, persona, logging quests by hand, merchant temper
    from life_rpg import button as button_mod
    from life_rpg.coordinator import resolve_sleep

    lena_opts = {
        **done["data"],
        "goddess_name": "Lena",
        "goddess_persona": "own",
        "manual_quests": ["hydration", "floors", "sleep"],
    }
    lena_opts.pop("hydration_entity", None)
    lena_entry = ConfigEntry(lena_opts, title="Sam")
    lena_entry.entry_id = "lena1"
    lc = coord_mod.LifeRPGCoordinator(hass, lena_entry)
    lena_entry.runtime_data = lc
    hass.config_entries = types.SimpleNamespace(
        async_loaded_entries=lambda d: [entry, lena_entry], async_unload_platforms=_unload
    )
    await lc._async_setup()
    await lc.async_refresh()
    lv = lc.data
    assert (
        "hydration" in lv["quests"]
        and lv["manual"] == ["floors", "hydration", "sleep"]
        and lv["goddess"]["name"] == "Lena"
    )
    assert "Lune" not in json.dumps({k: x for k, x in lv.items() if k not in ("lune_chat", "lore")})
    btns = []
    await button_mod.async_setup_entry(hass, lena_entry, lambda e: btns.extend(e))
    assert sorted(b._attr_translation_key for b in btns) == ["log_floor", "log_water"]
    water = next(b for b in btns if b.quest == "hydration")
    for _ in range(8):
        await water.async_press()
    assert lc.data["quests"]["hydration"]["done"] and lc.data["manual_log"]["hydration"] == 2000
    # actions, as an automation (no user), as the owner, and as someone else
    log_fn, log_schema = SERVICES["log"]
    sleep_fn, sleep_schema = SERVICES["log_sleep"]
    call = lambda data, uid=None: types.SimpleNamespace(data=data, context=types.SimpleNamespace(user_id=uid))  # noqa: E731
    res = await log_fn(call(log_schema({"adventurer": "lena1", "quest": "floors", "amount": 3})))
    assert res == {"quest": "floors", "today": 3}
    try:
        await log_fn(call(log_schema({"quest": "floors", "amount": 1})))
        raise AssertionError("ambiguous adventurer accepted")
    except HomeAssistantError:
        pass
    try:
        await log_fn(call(log_schema({"adventurer": "lena1", "quest": "floors", "amount": 1}), uid="u2"))
        raise AssertionError("someone else logged for Sam")
    except HomeAssistantError:
        pass
    H_NOW = H_NOW_REF[0]
    res = await sleep_fn(call(sleep_schema({"adventurer": "lena1", "bedtime": "22:40", "wake": "06:50"})))
    assert res["hours"] == 8.17 and lc.data["quests"]["sleep"]["done"] and lc.data["quests"]["bedtime"]["done"], (
        res,
        lc.data["quests"],
    )
    s0, e0 = resolve_sleep("2026-10-11T23:10:00-04:00", "07:05", H_NOW)
    assert abs((e0 - s0).total_seconds() - (7 * 3600 + 55 * 60)) < 1, (s0, e0)
    for bad in [("25:00", "06:00"), ("22:00", "23:30")]:
        try:
            await sleep_fn(call(sleep_schema({"adventurer": "lena1", "bedtime": bad[0], "wake": bad[1]})))
            raise AssertionError(f"bad sleep accepted {bad}")
        except HomeAssistantError:
            pass
    # Assist logging and the renamed goddess
    lctx = LLMContext("ollama", types.SimpleNamespace(user_id="u1"), "en", "conversation", None)
    linst = await APIS["life_rpg"].async_get_api_instance(lctx)
    ltools = {t.name: t for t in linst.tools}
    lcall = lambda name, **a: ltools[name].async_call(hass, ToolInput(name, a), lctx)  # noqa: E731
    r = await lcall("life_rpg_log", quest="water", amount=-250, adventurer="Sam")
    assert r["today_total"] == 1750 and not lc.data["quests"]["hydration"]["done"], r
    r = await lcall("life_rpg_status", adventurer="Sam")
    assert r["goddess"] == "Lena"
    r = await lcall("life_rpg_talk_to_goddess", message="hi", adventurer="Sam")
    assert r["goddess"] == "Lena"
    persona_prompt = LLM_CALLS[-1][1]
    assert persona_prompt.startswith("You are Lena. Keep your own personality") and "Lune" not in persona_prompt
    # a merchant pushed too far, through chat
    lc.game.L["gold"] = 10**6
    lc.game.L["shop"]["restocks"] = []  # no delivery in the middle of this
    outcomes, lists = [], {e["id"]: e["list"] for e in lc.game.L["shop"]["stock"]}
    for e in list(lc.game.L["shop"]["stock"]):
        for _ in range(4):
            r = await lc.async_chat("merchant", "How about 10 gold?", e["id"])
            outcomes.append(r["result"])
    assert "fed_up" in outcomes and "insulted" in outcomes and lc.data["market"]["temper"] == "fed_up", outcomes
    assert lc.data["market"]["face"] == "furious" and all(
        e["price"] <= lists[e["id"]] * 1.1 for e in lc.data["market"]["stock"]
    )
    print(f"  goddess Lena, buttons, actions, Assist logging, sleep log ok; merchant {outcomes[:6]}... no markup")
    # --- working hours (options step and an entity), emergency fines, gifts from the goddess
    from life_rpg.coordinator import work_hours

    wk = await opt.async_step_work()
    assert wk["step_id"] == "work"
    wdone = await opt.async_step_work(
        {
            "emergency_penalty": True,
            "work_days": ["mon", "tue"],
            "work_start": "08:00:00",
            "work_end": "16:00:00",
            "work_entity": "input_boolean.at_work",
        }
    )
    assert wdone["data"]["work_days"] == ["mon", "tue"] and wdone["data"]["race"] == "elf", wdone
    assert work_hours(wdone["data"]) == {"penalty": True, "start": 480, "end": 960, "days": [0, 1]}
    assert work_hours({}) == {"penalty": True, "start": 540, "end": 1020, "days": [0, 1, 2, 3, 4]}
    lc.work_entity = "input_boolean.at_work"
    S["input_boolean.at_work"] = State("on", {})
    await lc.async_refresh()
    assert lc.game.at_work is True
    S["input_boolean.at_work"] = State("unavailable", {})
    await lc.async_refresh()
    assert lc.game.at_work is None
    gold0 = lc.game.L["gold"]
    assert lc.game.L["gifts"]["rolled"], "the earlier chat used up today's roll"
    lc.game.L["gifts"]["rolled"] = None  # pretend it's a new day
    lc.game.gift_offer = lambda: {"kind": "potion", "id": "lucky_charm", "name": "Lucky Charm", "desc": "Luck."}
    r = await lc.async_chat("lune", "Hello, any presents?")
    assert r["gift"]["name"] == "Lucky Charm" and r["mood"] == "delighted" and lc.game.L["bag"].get("lucky_charm")
    assert "Today you are giving them a gift: Lucky Charm" in LLM_CALLS[-1][1]
    ev = next(e for e in lc.data["events"] if e["type"] == "goddess_gift")
    assert ev["goddess"] == "Lena", ev
    del lc.game.gift_offer
    r = await lc.async_chat("lune", "Another one?")
    assert r["gift"] is None and "You have no gift to give today" in LLM_CALLS[-1][1]
    r = await lcall("life_rpg_talk_to_goddess", message="Gift please", adventurer="Sam")
    assert "gift" not in r and lc.game.L["gold"] == gold0
    print("  work step, work entity, gifts through chat and Assist ok")

    # --- goddess step, fl oz, sensor guard and corrections
    gd = await opt.async_step_goddess({"goddess_name": "  Lena  ", "goddess_persona": "own"})
    assert (
        gd["data"]["goddess_name"] == "Lena"
        and gd["data"]["race"] == "elf"
        and gd["data"].get("comfyui_url") == opt.config_entry.options.get("comfyui_url")
    )
    gd2 = await opt.async_step_goddess({"goddess_persona": "goddess"})
    assert "goddess_name" not in gd2["data"]
    base_q = {
        "user_id": "u1",
        "steps_entity": "sensor.p_steps",
        "hydration_entity": "sensor.p_water",
        "steps_goal": 8000,
        "sleep_goal": 7.5,
        "bedtime_quest": True,
        "bedtime_goal": "23:00:00",
        "floors_goal": 10,
    }
    bad = await opt.async_step_quests({**base_q, "water_unit": "floz", "hydration_goal": 2000})
    assert bad["errors"] == {"hydration_goal": "goal_floz"}, bad
    okq = await opt.async_step_quests({**base_q, "water_unit": "floz", "hydration_goal": 64})
    assert okq["type"] == "create_entry"
    oz_entry = ConfigEntry(
        {**lena_opts, "water_unit": "floz", "hydration_goal": 64, "corrections": ["steps", "hydration"]}, title="Oz"
    )
    oz_entry.entry_id = "oz1"
    oz = coord_mod.LifeRPGCoordinator(hass, oz_entry)
    oz_entry.runtime_data = oz
    hass.config_entries = types.SimpleNamespace(
        async_loaded_entries=lambda d: [entry, lena_entry, oz_entry], async_unload_platforms=_unload
    )
    await oz._async_setup()
    await oz.async_refresh()
    assert oz.game.goals["hydration"] == round(64 * 29.5735) and oz.data["quests"]["hydration"]["goal"] == 64
    assert oz.data["quests"]["hydration"]["unit"] == "fl oz"
    obtns = []
    await button_mod.async_setup_entry(hass, oz_entry, lambda e: obtns.extend(e))
    owater = next(b for b in obtns if b.quest == "hydration")
    assert owater.amount == 8
    await owater.async_press()
    assert oz.data["manual_log"]["hydration"] == 8
    # steps counted twice: a sudden jump is held back and can be fixed through the action and Assist
    S["sensor.p_steps"] = State("3000", {"endTime": iso(utc(2026, 10, 12, 14, 0))})
    await oz.async_refresh()
    S["sensor.p_steps"] = State("13000", {"endTime": iso(utc(2026, 10, 12, 14, 1))})
    await oz.async_refresh()
    assert oz.data["quests"]["steps"].get("held", 0) > 0, oz.data["quests"]["steps"]
    corr_fn, corr_schema = SERVICES["correct"]
    res = await corr_fn(call(corr_schema({"adventurer": "oz1", "quest": "steps", "today": 3200, "record": 9000})))
    assert res == {"quest": "steps", "today": 3200, "record": 9000}, res
    assert oz.data["quests"]["steps"]["value"] == 3200
    octx = LLMContext("ollama", types.SimpleNamespace(user_id="u1"), "en", "conversation", None)
    oinst = await APIS["life_rpg"].async_get_api_instance(octx)
    otools = {t.name: t for t in oinst.tools}
    r = await otools["life_rpg_fix_count"].async_call(
        hass, ToolInput("life_rpg_fix_count", {"quest": "water", "today": 40, "adventurer": "Oz"}), octx
    )
    assert r["today"] == 40 and r["unit"] == "fl oz", r
    r = await otools["life_rpg_log"].async_call(
        hass, ToolInput("life_rpg_log", {"quest": "water", "amount": 8, "adventurer": "Oz"}), octx
    )
    assert r["unit"] == "fl oz" and r["today_total"] == 16, r
    fx_entry = ConfigEntry({**FLUX_UNET_OPTIONS, "paint": ["portrait"], "art_style": "painted"}, title="Fx")
    fx_entry.entry_id = "fx1"
    fx = coord_mod.LifeRPGCoordinator(hass, fx_entry)
    fx_entry.runtime_data = fx
    assert fx.art_cfg and fx.art_cfg["family"] == "flux_unet" and fx.art_cfg["parts"]["vae"] == "ae.safetensors", (
        fx.art_cfg
    )
    before_jobs = len(COMFY.prompts)
    await fx._async_setup()
    await fx.async_refresh()
    await settle(studio)
    assert len(COMFY.prompts) > before_jobs, "a flux (separate files) portrait was painted"
    await fx.async_refresh()
    assert fx.data["art"]["portrait"], fx.data["art"]
    # --- 12-hour clock (from the country, or chosen), paintings for potions, charms and cosmetics
    assert fx.twelve and fx.data["clock"] == "12" and fx.data["quests"]["bedtime"]["goal"].endswith("PM"), fx.data[
        "quests"
    ].get("bedtime")
    form = await opt.async_step_quests()
    assert any(str(k) == "clock" for k in form["data_schema"].schema) and config_flow._clock_default(hass) == "12"
    h24 = coord_mod.LifeRPGCoordinator(hass, ConfigEntry({**FLUX_UNET_OPTIONS, "clock": "24"}, title="H24"))
    assert not h24.twelve
    fx.game.L["bag"]["elixir"] = 1
    await fx.async_refresh()
    m = fx.data["market"]
    trinkets = [e for e in m["stock"] if e["kind"] != "gear"]
    assert trinkets and all("art" in e for e in trinkets) and all("art" in b for b in fx.data["bag"]), (
        trinkets[:1],
        fx.data["bag"],
    )
    print("  12-hour clock and trinket paintings ok")

    from life_rpg.engine.game import GameError

    # --- corrections switch, the same night reported twice, repaint one picture, a tidy art folder
    hass.config_entries = types.SimpleNamespace(
        async_loaded_entries=lambda d: [entry, lena_entry, oz_entry, fx_entry], async_unload_platforms=_unload
    )
    try:
        await corr_fn(call(corr_schema({"adventurer": "fx1", "quest": "steps", "today": 1})))
        raise AssertionError("a correction went through with corrections off")
    except HomeAssistantError as err:
        assert "turned off" in str(err), err
    S["sensor.p_sleep"] = State(
        "470",
        {
            "unit_of_measurement": "min",
            "startTime": iso(utc(2026, 10, 11, 22, 40)),
            "endTime": iso(utc(2026, 10, 12, 6, 30)),
        },
    )
    await fx.async_refresh()
    S["sensor.p_sleep"] = State(
        "455",
        {
            "unit_of_measurement": "min",
            "startTime": iso(utc(2026, 10, 11, 22, 52)),
            "endTime": iso(utc(2026, 10, 12, 6, 27)),
        },
    )
    await fx.async_refresh()
    sl = fx.data["quests"]["sleep"]
    assert sl["value"] <= 470 / 60 + 0.01 and sl["pct"] < 120, (
        "the same night counted twice",
        sl,
        fx.game.L["inputs"]["sleep"],
    )
    # repaint one picture: a new version replaces the old file only once it's ready
    old_url = fx.data["art"]["portrait"]
    old_file = studio.dir / old_url.rsplit("/", 1)[-1]
    assert old_file.is_file()
    await fx.async_action("repaint_art", url=old_url)
    assert fx.data["art"]["portrait"] == old_url, "the old painting stays while the new one paints"
    await settle(studio)
    await fx.async_refresh()
    new_url = fx.data["art"]["portrait"]
    assert new_url != old_url and not old_file.exists() and (studio.dir / new_url.rsplit("/", 1)[-1]).is_file(), (
        old_url,
        new_url,
    )
    # a repaint that fails keeps the picture it was replacing
    COMFY.fail_next = True
    await fx.async_action("repaint_art", url=new_url)
    await settle(studio)
    await fx.async_refresh()
    assert fx.data["art"]["portrait"] == new_url and (studio.dir / new_url.rsplit("/", 1)[-1]).is_file()
    try:
        await fx.async_action("repaint_art", url="/life_rpg_art/not-a-painting.webp")
        raise AssertionError("repainted a picture that doesn't exist")
    except GameError:
        pass
    # a new portrait (new look) replaces the adventurer's earlier ones
    await fx.async_action("repaint")
    await settle(studio)
    await fx.async_refresh()
    group = [e for e in studio.index.values() if e.get("group") == "portrait:fx1" and e.get("file")]
    assert len(group) == 1, group
    # the tidy-up: stray files from old repaints and entries whose file vanished
    stray = studio.dir / "portrait-deadbeef.png"
    stray.write_bytes(PNG)
    os.utime(stray, (time.time() - 7200, time.time() - 7200))
    studio.index["ghost"] = {"file": "ghost.png", "kind": "item", "used": 1}
    await studio._tidy()
    assert not stray.exists() and "ghost" not in studio.index
    assert all("bytes" in e for e in studio.index.values() if e.get("file"))
    # the size budget: least recently shown go first
    keep_total, keep_recent = art.MAX_TOTAL, art.KEEP_RECENT
    for e in studio.index.values():
        if e.get("file"):
            e["used"] = 1
    total = sum(e.get("bytes", 0) for e in studio.index.values() if e.get("file"))
    art.MAX_TOTAL, art.KEEP_RECENT = total // 2, 0
    await studio._prune()
    left = sum(e.get("bytes", 0) for e in studio.index.values() if e.get("file"))
    assert left <= total // 2, (left, total)
    art.MAX_TOTAL, art.KEEP_RECENT = keep_total, keep_recent
    files = {f.name for f in studio.dir.iterdir() if f.is_file()}
    assert files == {e["file"] for e in studio.index.values() if e.get("file")}, "files and index agree"
    assert all(w.get("8", {}).get("class_type") in ("PreviewImage", None) for w in COMFY.prompts[-3:])
    print("  corrections switch, sleep reported twice, repaint one picture, art folder tidy and budget ok")

    # --- Lights out from Samsung-style sleep sensors, sleep logged by hand only, honest rewards
    import stubs as HS

    from life_rpg.coordinator import resolve_bedtime

    sam_opts = {
        **done["data"],
        "sleep_entity": "sensor.pixel_health_connect_sleep_duration",
        "bedtime_quest": True,
        "bedtime_goal": "23:00:00",
    }
    sam_entry = ConfigEntry(sam_opts, title="Sam S")
    sam_entry.entry_id = "sams1"
    sam = coord_mod.LifeRPGCoordinator(hass, sam_entry)
    await sam._async_setup()
    sam.game.L["inputs"]["sleep"] = {}
    sam.game.L["today"].pop("bedtime", None), sam.game.L["today"].pop("sleep", None)  # a fresh morning for each case
    # 1) no startTime/endTime, only the stage timeline
    S["sensor.pixel_health_connect_sleep_duration"] = State(
        "455",
        {
            "unit_of_measurement": "min",
            "stageTypes": ["light", "deep", "rem"],
            "stageStartTimes": [
                iso(utc(2026, 10, 11, 22, 52)),
                iso(utc(2026, 10, 12, 1, 0)),
                iso(utc(2026, 10, 12, 4, 0)),
            ],
            "stageEndTimes": [
                iso(utc(2026, 10, 12, 1, 0)),
                iso(utc(2026, 10, 12, 4, 0)),
                iso(utc(2026, 10, 12, 6, 30)),
            ],
        },
    )
    await sam.async_refresh()
    bq = sam.data["quests"]["bedtime"]
    assert bq["value"] and bq["value"].startswith("10:52"), bq
    # 2) just a duration, with the companion app's separate start / end sensors on the same phone
    sam.game.L["inputs"]["sleep"] = {}
    sam.game.L["today"].pop("bedtime", None), sam.game.L["today"].pop("sleep", None)  # a fresh morning for each case
    S["sensor.pixel_health_connect_sleep_duration"] = State("440", {"unit_of_measurement": "min"})
    S["sensor.pixel_health_connect_sleep_start"] = State(iso(utc(2026, 10, 11, 23, 20)), {})
    S["sensor.pixel_health_connect_sleep_end"] = State(iso(utc(2026, 10, 12, 6, 40)), {})
    await sam.async_refresh()
    assert sam.data["quests"]["bedtime"]["value"].startswith("11:20"), sam.data["quests"]["bedtime"]
    # ... found through the device when the names differ
    sam.game.L["inputs"]["sleep"] = {}
    sam.game.L["today"].pop("bedtime", None), sam.game.L["today"].pop("sleep", None)  # a fresh morning for each case
    del S["sensor.pixel_health_connect_sleep_start"]
    S["sensor.phone_sleep_start"] = State(iso(utc(2026, 10, 11, 23, 45)), {})
    HS.REG_ENTITIES.update(
        {
            e: types.SimpleNamespace(entity_id=e, device_id="phone1")
            for e in ("sensor.pixel_health_connect_sleep_duration", "sensor.phone_sleep_start")
        }
    )
    await sam.async_refresh()
    assert sam.data["quests"]["bedtime"]["value"].startswith("11:45"), sam.data["quests"]["bedtime"]
    # the same night logged by hand as well: Rest is not doubled
    rest = sam.data["quests"]["sleep"]["value"]
    sam.manual = {"sleep"}
    await sam.async_action("log_sleep", bedtime="23:40", wake="06:45")
    assert abs(sam.data["quests"]["sleep"]["value"] - rest) < 0.05, (rest, sam.data["quests"]["sleep"])
    # 3) no sleep sensor at all: Rest and Lights out logged by hand, or Lights out on its own
    hand_opts = {k: v for k, v in done["data"].items() if k != "sleep_entity"}
    hand_entry = ConfigEntry(
        {**hand_opts, "manual_quests": ["sleep"], "bedtime_quest": True, "bedtime_goal": "23:00:00"}, title="Hand"
    )
    hand_entry.entry_id = "hand1"
    hand = coord_mod.LifeRPGCoordinator(hass, hand_entry)
    await hand._async_setup()
    await hand.async_refresh()
    assert {"sleep", "bedtime"} <= set(hand.data["quests"]), hand.data["quests"].keys()
    assert await hand.async_action("log_sleep", bedtime="22:30") in ("10:30 PM", "22:30")
    assert hand.data["quests"]["bedtime"]["done"] and hand.data["quests"]["sleep"]["value"] is None
    hours = await hand.async_action("log_sleep", bedtime="22:30", wake="06:30")
    assert hours == 8.0 and hand.data["quests"]["sleep"]["done"] and hand.data["quests"]["bedtime"]["done"]
    sl_fn, sl_schema = SERVICES["log_sleep"]
    try:
        await sl_fn(call(sl_schema({"adventurer": "nope", "bedtime": "22:30"})))
    except HomeAssistantError:
        pass
    when = resolve_bedtime("23:50", H_NOW_REF[0])
    assert when < H_NOW_REF[0] and (H_NOW_REF[0] - when).total_seconds() < 86400
    # 4) honest rewards: an AI line that oversells the chest is rewritten, then dropped
    said = iter(["Take it, and a legendary hoard overflowing with treasure is yours!", "Riches untold await!"])
    real_text = lc.lore._text

    async def overselling(task, instructions):
        return next(said)

    lc.lore._text = overselling
    assert await lc.lore._honest("choice", "x") is None
    said = iter(["A king's ransom!", "Finish your walk and this chest is yours, friend."])
    assert await lc.lore._honest("choice", "x") == "Finish your walk and this chest is yours, friend."
    lc.lore._text = real_text
    print("  Lights out from stage times and sleep start sensors, no doubled Rest, hand-only sleep, honest rewards ok")

    # --- bounty board and kids mode, portrait choices, merchant faces, goddess through your own agent, speed
    from life_rpg.engine import appearance as A_mod

    bq = await opt.async_step_bounties()
    assert bq["step_id"] == "bounties"
    bdone = await opt.async_step_bounties({"daily_bounties": 3.0, "kids_mode": True})
    assert bdone["data"]["daily_bounties"] == 3 and bdone["data"]["kids_mode"] and bdone["data"]["race"] == "elf"
    assert (await opt.async_step_init())["menu_options"] == ["quests", "bounties", "goddess", "work", "studio"]
    kid_entry = ConfigEntry({**done["data"], "kids_mode": True, "daily_bounties": 2}, title="Kid")
    kid_entry.entry_id = "kid1"
    kid = coord_mod.LifeRPGCoordinator(hass, kid_entry)
    await kid._async_setup()
    await kid.async_refresh()
    daily = [b for b in kid.data["bounties"] if b["source"] == "daily"]
    assert len(daily) == 2 and sum(b["chest"] for b in daily) == 1
    try:
        await kid.async_action("add_bounty", title="Feed the dog", xp=50)
        raise AssertionError("a child posted their own chore")
    except GameError:
        pass
    chore = await kid.async_action(
        "add_bounty", _admin=True, title="Feed the dog", xp=60, gold=20, chest=True, repeat="daily"
    )
    assert await kid.async_action("claim_bounty", bounty_id=chore["id"]) == "claimed"
    try:
        await kid.async_action("approve_bounty", bounty_id=chore["id"])
        raise AssertionError("a child approved their own chore")
    except GameError:
        pass
    gold0, chests0 = kid.game.L["gold"], len(kid.game.L["chests"])
    assert await kid.async_action("approve_bounty", _admin=True, bounty_id=chore["id"], ok=True) == "done"
    assert kid.game.L["gold"] == gold0 + 20 and len(kid.game.L["chests"]) == chests0 + 1
    assert next(b for b in kid.data["bounties"] if b["id"] == chore["id"])["state"] == "done"
    side = next(b for b in kid.data["bounties"] if b["source"] == "daily")
    assert await kid.async_action("claim_bounty", bounty_id=side["id"]) == "done", "side quests are on your honour"
    # the LLM rewords side quests (rewards stay the game's)
    kid.game.set_bounty_titles(kid.data["now"][:10], ["Do ten jumping jacks", "Draw a picture for someone"])
    # by voice: "I put things back"
    hass.config_entries = types.SimpleNamespace(
        async_loaded_entries=lambda d: [entry, kid_entry], async_unload_platforms=_unload
    )
    kid_entry.runtime_data = kid
    kctx = LLMContext("ollama", types.SimpleNamespace(user_id="u1"), "en", "conversation", None)
    ktools = {t.name: t for t in (await APIS["life_rpg"].async_get_api_instance(kctx)).tools}
    board = await ktools["life_rpg_bounties"].async_call(
        hass, ToolInput("life_rpg_bounties", {"adventurer": "Kid"}), kctx
    )
    open_one = next(b for b in board["board"] if b["state"] == "open")
    said = " ".join(sorted(open_one["title"].lower().split(), key=len)[-2:])  # its two longest words
    r = await ktools["life_rpg_bounties"].async_call(
        hass, ToolInput("life_rpg_bounties", {"adventurer": "Kid", "done": f"I did {said}"}), kctx
    )
    assert r.get("result") in ("done", "claimed"), (r, said)
    r = await ktools["life_rpg_bounties"].async_call(
        hass, ToolInput("life_rpg_bounties", {"adventurer": "Kid", "done": "zzz qqq"}), kctx
    )
    assert r["success"] is False
    # portrait choices
    prefs = await kid.async_action(
        "set_portrait_prefs",
        prefs={
            "framing": "closeup",
            "hair": "crimson red",
            "eyes": "green",
            "build": "athletic",
            "weapon": "Longbow",
            "hairstyle": "",
        },
    )
    assert prefs == {
        "framing": "closeup",
        "hair": "crimson red",
        "eyes": "green",
        "build": "athletic",
        "weapon": "Longbow",
    }
    assert kid.data["appearance"]["hair"] == 6 and A_mod.portrait_prompt(kid.data, "feminine")["prompt"].startswith(
        "Full-body"
    ), "framing only crops"
    try:
        await kid.async_action("set_portrait_prefs", prefs={"hair": "<script>"})
        raise AssertionError("an unknown hair colour")
    except GameError:
        pass
    # merchant faces: the one showing is painted first
    sh = kid.game.L["shop"]
    sh["restocks"], sh["annoyance"], sh["calm_at"] = [], 7.5, time.time()
    kid.game.now = kid.game.now.fromtimestamp(time.time())
    await kid.async_refresh()
    assert kid.data["market"]["face"] == "angry" and set(kid.data["market"]["art"]) >= {"annoyed", "angry", "furious"}
    # the goddess through a conversation agent (your own assistant), with the game's briefing alongside
    kid.chat_agent = "conversation.lena"
    n0 = len(CONVERSE)
    r = await kid.async_chat("lune", "I walked to the park today")
    data, uid = CONVERSE[-1]
    assert (
        len(CONVERSE) == n0 + 1
        and data["agent_id"] == "conversation.lena"
        and data["text"].endswith("I walked to the park today")
    )
    assert "Life RPG game note" in data["text"] and r["mood"] in ("proud", "delighted") and "park" in r["reply"]
    r = await kid.async_chat("lune", "And I drank water")
    assert CONVERSE[-1][0].get("conversation_id") == "conv-1", "the same conversation continues"
    # painting speed: smaller items, fewer steps, Flux at half memory, a fast model's settings
    item = A_mod.item_prompt({"base": "Dagger", "slot": "weapon", "rarity": "rare", "name": "x"})
    q = art.build_workflow(item, {"family": "flux_unet", "checkpoint": UNETS[0], "parts": parts, "speed": "quality"}, 1)
    f = art.build_workflow(item, {"family": "flux_unet", "checkpoint": UNETS[0], "parts": parts, "speed": "fast"}, 1)
    assert (
        q["4"]["inputs"]["width"] == 1024
        and f["4"]["inputs"]["width"] == 768
        and f["1"]["inputs"]["weight_dtype"] == "fp8_e4m3fn"
    )
    assert f["5"]["inputs"]["steps"] < q["5"]["inputs"]["steps"] and not COMFY.validate(f)
    fm = art.build_workflow(item, {"family": "sdxl", "checkpoint": CKPTS[0], "fast_model": True}, 1)
    assert fm["5"]["inputs"]["steps"] == 6 and fm["5"]["inputs"]["cfg"] == 1.5
    print("  bounty board and kids mode, portrait choices, merchant faces, goddess via her agent, painting speed ok")

    # --- haggling back and forth, walking away, deliveries, job bonuses, goddess choices, the panel's version
    hk = kid.game
    hk.L["shop"]["restocks"], hk.L["shop"]["annoyance"], hk.L["gold"] = [], 0.0, 10**6
    e = next(
        x for x in hk.L["shop"]["stock"] if x["kind"] == "gear" and not x["sold"] and not x["deal"] and not x["closed"]
    )
    r1 = await kid.async_chat("merchant", f"{int(e['floor'] * 0.97)} gold?", e["id"])
    assert r1["result"] in ("countered", "accepted"), r1
    if r1["result"] == "countered":
        r2 = await kid.async_chat("merchant", "Never mind, too steep for me.", e["id"])
        assert r2["result"] in ("called_back", "walked") and r2["offer"] is None, r2
    w = await kid.async_action("walk_away", stock_id=e["id"])
    assert w["result"] == "walked", "he calls you back once at most"
    assert "theme_text" in kid.data["market"] and kid.data["market"]["delivery"] == 1
    ws_owner = Conn("u1", admin=False)
    websocket.ws_subscribe(hass, ws_owner, {"id": 31, "entry_id": "kid1"})
    assert ws_owner.out[-1][2]["version"] == life_rpg.VERSION
    ROOT = Path(life_rpg.__file__).parent
    js = (ROOT / "frontend" / "life-rpg.js").read_text()
    assert f'const VERSION = "{life_rpg.VERSION}"' in js and js.count(f"?v={life_rpg.VERSION}") == 3
    assert f"?v={life_rpg.VERSION}" in (ROOT / "frontend" / "cast.js").read_text()
    assert REGISTERED["panel"]["webcomponent_name"] == "life-rpg-panel-" + life_rpg.VERSION.replace(".", "-")
    kid.game.L["level"], kid.game.L["job"] = 6, None
    await kid.async_action("set_job", job="ranger")
    assert any(b["source"] == "job" for b in kid.data["bonus_sources"]) and kid.data["job"]["xp"] == 0
    gp = await kid.async_action("set_goddess_prefs", prefs={"framing": "full", "outfit": "starlight", "hair": ""})
    assert gp == {"framing": "full", "outfit": "starlight"} and kid.data["goddess"]["prefs"] == gp
    assert "midnight-blue gown" in A_mod.goddess_prompt("serene", 0, "Lune", gp)["prompt"]
    mp = await kid.async_action(
        "set_merchant_prefs",
        prefs={"age": "elderly", "backdrop": "caravan", "accessory": "pipe", "hair": "", "race": "dwarf"},
    )
    assert (
        mp == {"age": "elderly", "backdrop": "caravan", "accessory": "pipe", "race": "dwarf"}
        and kid.data["market"]["prefs"] == mp
    )
    assert await kid.async_action("set_portrait_prefs", prefs={"age": "teen"}) == {"age": "teen"}
    assert "teenage" in A_mod.portrait_prompt(kid.data, "feminine")["prompt"]
    assert kid.data["bonus_caps"]["limits"] and isinstance(kid.data["bonus_caps"]["capped"], list)
    print("  haggling back and forth, walking away, goddess choices, job bonuses and the panel's version ok")

    # --- an image-edit model: one base painting per character, every other picture an edit of it
    form = await opt.async_step_studio()
    assert any(str(k) == "edit_model" for k in form["data_schema"].schema)
    ed_in = {
        "art_style": "painted",
        "body": "feminine",
        "comfyui_url": "http://comfy:8188",
        "model_family": "flux_unet",
        "checkpoint": UNETS[0],
        "paint": ["portrait", "characters"],
        "paint_speed": "balanced",
        "fast_model": False,
        "llm_features": ["lune_chat", "flavour", "haggling"],
        "edit_model": "flux1-kontext-dev.safetensors",
    }
    saved = await opt.async_step_studio(ed_in)
    assert saved["data"]["edit_parts"] == {
        "t5": "t5xxl_fp16.safetensors",
        "clip_l": "clip_l.safetensors",
        "vae": "ae.safetensors",
    }, saved
    qsaved = await opt.async_step_studio({**ed_in, "edit_model": UNETS[2]})
    assert qsaved["data"]["edit_parts"] == {"te": QWEN_TE[0], "vae": "qwen_image_vae.safetensors"}, qsaved
    nosaved = await opt.async_step_studio({**ed_in, "edit_model": None})
    assert "edit_model" not in nosaved["data"] and "edit_parts" not in nosaved["data"]
    for label, opts in (("kontext", saved["data"]), ("qwen", qsaved["data"])):
        ed_entry = ConfigEntry({**done["data"], **opts}, title=f"Ed{label}")
        ed_entry.entry_id = f"ed-{label}"
        ed = coord_mod.LifeRPGCoordinator(hass, ed_entry)
        ed_entry.runtime_data = ed
        assert ed.art_cfg["edit"]["model"] == opts["edit_model"]
        await ed._async_setup()
        n0, u0 = len(COMFY.prompts), len(COMFY.uploads)
        await ed.async_refresh()
        queued = [
            j["spec"]
            for j in studio.queue.values()
            if j["spec"].get("owner") == ed_entry.entry_id or "edit" in j["spec"]
        ]
        assert all(studio.file_of(sp["edit"]["base"]) for sp in queued if "edit" in sp), (
            "edits wait for their base painting"
        )
        assert any(sp.get("group", "").startswith(("portrait-base", "goddess-base")) for sp in queued)
        await settle(studio)
        await ed.async_refresh()  # the bases are ready: the edits queue
        await settle(studio)
        await ed.async_refresh()
        await settle(studio)
        await ed.async_refresh()
        d = ed.data
        assert (
            d["art"]["edit"]
            and d["art"]["portrait_base"]
            and d["art"]["portrait"]
            and d["art"]["portrait"] != d["art"]["portrait_base"]
        )
        assert (
            d["goddess"]["base_art"]
            and all(d["goddess"]["art"].values())
            and d["market"]["base_art"]
            and all(d["market"]["art"].values())
        )
        assert d["market"]["base_art"] not in d["market"]["art"].values(), "his base is plain; every face is an edit"
        edits = [w for w in COMFY.prompts[n0:] if any(n["class_type"] == "LoadImage" for n in w.values())]
        # Kontext: you, six moods of the goddess and seven faces of the merchant; Qwen (a second adventurer) shares
        # the goddess and merchant edits already made, so only its own portrait is new
        assert len(edits) >= (14 if label == "kontext" else 1) and len(COMFY.uploads) > u0, (
            len(edits),
            len(COMFY.uploads),
        )
        assert all(not COMFY.validate(w) for w in edits)
        kinds = {n["class_type"] for w in edits for n in w.values()}
        assert ("ReferenceLatent" in kinds) if label == "kontext" else ("TextEncodeQwenImageEditPlus" in kinds), kinds
        pw = next(w for w in edits if "Keep this exact same person" in json.dumps(w))
        print(
            f"  {label}: {len(edits)} edits of {len(COMFY.uploads) - u0} base paintings; portrait edit: "
            f"{next(n['inputs'].get('text') or n['inputs'].get('prompt') for n in pw.values() if n['class_type'] in ('CLIPTextEncode', 'TextEncodeQwenImageEditPlus'))[:110]}..."
        )
        # gear change: only the edit is redone, from the same base
        n1 = len(COMFY.prompts)
        await ed.async_action("repaint")
        await settle(studio)
        assert any(any(n["class_type"] == "LoadImage" for n in w.values()) for w in COMFY.prompts[n1:]), (
            "a repaint is an edit"
        )
        # repaint a base: everything of that character is redone from the new base
        n2 = len(COMFY.prompts)
        assert await ed.async_action("repaint_art", url=d["goddess"]["base_art"])
        await settle(studio)
        await ed.async_refresh()
        await settle(studio)
        await ed.async_refresh()
        goddess_edits = [w for w in COMFY.prompts[n2:] if "Dress her in" in json.dumps(w)]
        assert len(goddess_edits) == 6, len(goddess_edits)
        assert all(u for u in ed.data["goddess"]["art"].values()), "every mood is shown throughout"
        if label == "kontext":  # what each kind of choice repaints
            await settle(studio)
            n4, base_url = len(COMFY.prompts), ed.data["goddess"]["base_art"]
            await ed.async_action("set_goddess_prefs", prefs={"framing": "closeup"})
            await settle(studio)
            assert len(COMFY.prompts) == n4 and ed.data["goddess"]["base_art"] == base_url, "framing repaints nothing"
            await ed.async_action(
                "set_goddess_prefs", prefs={"framing": "closeup", "outfit": "huntress", "backdrop": "mood"}
            )
            for _ in range(3):
                await settle(studio)
                await ed.async_refresh()
            new = COMFY.prompts[n4:]
            assert len(new) == 6 and all(any(n["class_type"] == "LoadImage" for n in w.values()) for w in new), len(new)
            assert ed.data["goddess"]["base_art"] == base_url, "an outfit is an edit: the base stays"
            n5 = len(COMFY.prompts)
            await ed.async_action(
                "set_goddess_prefs", prefs={"framing": "closeup", "outfit": "huntress", "race": "elf"}
            )
            for _ in range(3):
                await settle(studio)
                await ed.async_refresh()
            new = COMFY.prompts[n5:]
            plain = [w for w in new if not any(n["class_type"] == "LoadImage" for n in w.values())]
            assert len(plain) == 1 and "elven" in json.dumps(plain[0]) and len(new) == 7, len(new)
            assert ed.data["goddess"]["base_art"] != base_url, "a new race is a new base painting"
            hqw = next(n for n in plain[0].values() if n["class_type"] in ("EmptyLatentImage",))
            assert hqw["inputs"]["width"] == 896, hqw
    # an older ComfyUI without the edit nodes: pictures are painted from the prompt instead
    COMFY.no_edit_nodes = True
    n3 = len(COMFY.prompts)
    await ed.async_action("repaint")
    await settle(studio)
    await ed.async_refresh()
    assert ed.data["art"]["portrait"] and any(
        not any(n["class_type"] == "LoadImage" for n in w.values()) for w in COMFY.prompts[n3:]
    )
    COMFY.no_edit_nodes = False
    print(
        "  image-edit model: bases first, edits after, repaint a base redoes its edits, fallback without edit nodes ok"
    )
    print("  goddess step, fl oz goals/buttons/Assist, held-back jump, correct action and Assist fix ok")
    hass.config_entries = types.SimpleNamespace(async_loaded_entries=lambda d: [entry], async_unload_platforms=_unload)

    # pixel-art mode: nothing painted, nothing queued, saved paintings unused
    px_entry = ConfigEntry({**done["data"], "art_style": "pixel"}, title="Pix")
    px_entry.entry_id = "pix1"
    px = coord_mod.LifeRPGCoordinator(hass, px_entry)
    px_entry.runtime_data = px
    await px._async_setup()
    queued = len(studio.queue)
    await px.async_refresh()
    pv = px.data
    assert len(studio.queue) == queued and pv["art"]["portrait"] is None and pv["art"]["style"] == "pixel"
    assert not pv["labyrinth"]["art"] and not any(i.get("art") for i in pv["gear"]["inventory"])
    assert not any(pv["goddess"]["art"].values()) and "voice_index" in (pv["choice"] or {"voice_index": 0})
    # categories left off stay pixel art too
    part = ConfigEntry({**done["data"], "paint": ["guardians"]}, title="Part")
    part.entry_id = "part1"
    pc = coord_mod.LifeRPGCoordinator(hass, part)
    await pc._async_setup()
    await pc.async_refresh()
    assert pc.data["art"]["portrait"] is None and not any(i.get("art") for i in pc.data["gear"]["inventory"])
    print("  pixel mode and partial painting ok")
    await life_rpg.async_unload_entry(hass, entry)
    await studio.async_stop()
    print(f"\nINTEGRATION TEST PASSED ({len(COMFY.prompts)} ComfyUI jobs, {len(LLM_CALLS)} LLM calls)")


if __name__ == "__main__":
    asyncio.run(main())
