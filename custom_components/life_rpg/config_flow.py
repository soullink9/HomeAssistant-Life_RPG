"""UI setup for Life RPG: one entry per adventurer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector as sel
from homeassistant.util import slugify
import voluptuous as vol

from .art import edit_kind, find_edit_parts, find_flux_parts, list_checkpoints, list_edit_models
from .const import (
    ART_STYLES,
    BODY_OPTIONS,
    CLOCK_OPTIONS,
    CONF_AI_TASK,
    CONF_ART_STYLE,
    CONF_BEDTIME,
    CONF_BEDTIME_ON,
    CONF_BODY,
    CONF_CHAT_AGENT,
    CONF_CHECKPOINT,
    CONF_CLOCK,
    CONF_COMFY_URL,
    CONF_CORRECTIONS,
    CONF_DAILY_BOUNTIES,
    CONF_EDIT_MODEL,
    CONF_EDIT_PARTS,
    CONF_FAMILY,
    CONF_FAST_MODEL,
    CONF_GODDESS,
    CONF_KIDS,
    CONF_LLM,
    CONF_MANUAL,
    CONF_PAINT,
    CONF_PENALTY,
    CONF_PERSONA,
    CONF_RACE,
    CONF_SPEED,
    CONF_USER,
    CONF_WATER_UNIT,
    CONF_WORK_DAYS,
    CONF_WORK_END,
    CONF_WORK_ENTITY,
    CONF_WORK_START,
    CORRECTION_OPTIONS,
    DOMAIN,
    FAMILY_OPTIONS,
    FLUX_PARTS,
    GOALS,
    LLM_OPTIONS,
    MANUAL_OPTIONS,
    PAINT_OPTIONS,
    PERSONAS,
    SOURCES,
    SPEED_OPTIONS,
    TWELVE_HOUR_COUNTRIES,
    WATER_UNIT_OPTIONS,
    WEEKDAYS,
    WORK_DEFAULTS,
)
from .engine.content import RACES


def _number(low: float, high: float, step: float, unit: str) -> sel.NumberSelector:
    """A number box for the options form."""
    return sel.NumberSelector(
        sel.NumberSelectorConfig(
            min=low, max=high, step=step, unit_of_measurement=unit, mode=sel.NumberSelectorMode.BOX
        )
    )


SENSOR = sel.EntitySelector(sel.EntitySelectorConfig(domain="sensor"))
QUEST_SCHEMA = {
    vol.Optional(SOURCES["steps"]): SENSOR,
    vol.Required(GOALS["steps"][0], default=GOALS["steps"][1]): _number(500, 50000, 500, "steps"),
    vol.Optional(SOURCES["sleep"]): SENSOR,
    vol.Required(GOALS["sleep"][0], default=GOALS["sleep"][1]): _number(4, 12, 0.25, "h"),
    vol.Required(CONF_BEDTIME_ON, default=True): sel.BooleanSelector(),
    vol.Required(CONF_BEDTIME, default=GOALS["bedtime"][1]): sel.TimeSelector(),
    vol.Optional(CONF_CLOCK): sel.SelectSelector(
        sel.SelectSelectorConfig(options=CLOCK_OPTIONS, translation_key="clock", mode=sel.SelectSelectorMode.LIST)
    ),
    vol.Optional(SOURCES["floors"]): SENSOR,
    vol.Required(GOALS["floors"][0], default=GOALS["floors"][1]): _number(1, 100, 1, "floors"),
    vol.Optional(SOURCES["hydration"]): SENSOR,
    vol.Required(CONF_WATER_UNIT, default="ml"): sel.SelectSelector(
        sel.SelectSelectorConfig(
            options=WATER_UNIT_OPTIONS, translation_key="water_unit", mode=sel.SelectSelectorMode.LIST
        )
    ),
    vol.Required(GOALS["hydration"][0], default=GOALS["hydration"][1]): sel.NumberSelector(
        sel.NumberSelectorConfig(min=1, max=6000, step=1, mode=sel.NumberSelectorMode.BOX)
    ),
    vol.Optional(CONF_MANUAL, default=[]): sel.SelectSelector(
        sel.SelectSelectorConfig(
            options=MANUAL_OPTIONS, translation_key="manual_quests", multiple=True, mode=sel.SelectSelectorMode.LIST
        )
    ),
    vol.Optional(CONF_CORRECTIONS, default=[]): sel.SelectSelector(
        sel.SelectSelectorConfig(
            options=CORRECTION_OPTIONS, translation_key="corrections", multiple=True, mode=sel.SelectSelectorMode.LIST
        )
    ),
}
BODY_SELECTOR = sel.SelectSelector(
    sel.SelectSelectorConfig(options=BODY_OPTIONS, translation_key="body", mode=sel.SelectSelectorMode.LIST)
)
RACE_SELECTOR = sel.SelectSelector(
    sel.SelectSelectorConfig(
        options=[
            sel.SelectOptionDict(value=k, label=f"{r['name']}: {r['gift'][0]}. {r['lore']}") for k, r in RACES.items()
        ],
        mode=sel.SelectSelectorMode.LIST,
    )
)


async def _user_selector(hass: HomeAssistant) -> sel.SelectSelector:
    """Home Assistant people who can be linked to an adventurer (they'll see it in the System panel)."""
    users = [u for u in await hass.auth.async_get_users() if not u.system_generated and u.is_active]
    return sel.SelectSelector(
        sel.SelectSelectorConfig(
            options=[sel.SelectOptionDict(value=u.id, label=u.name or u.id) for u in users],
            mode=sel.SelectSelectorMode.DROPDOWN,
        )
    )


def _clock_default(hass: HomeAssistant) -> str:
    """12-hour where that's the custom (Home Assistant's country setting), else 24-hour."""
    return "12" if hass.config.country in TWELVE_HOUR_COUNTRIES else "24"


def _errors(options: dict[str, Any]) -> dict[str, str]:
    """Check the options form; returns the form errors (empty when all is well)."""
    ok = any(options.get(key) for key in SOURCES.values()) or options.get(CONF_MANUAL)
    if not ok:
        return {"base": "no_sources"}
    goal, unit = float(options.get(GOALS["hydration"][0], GOALS["hydration"][1])), options.get(CONF_WATER_UNIT, "ml")
    if unit == "floz" and not 8 <= goal <= 300:  # 2000 left over from mL, most likely
        return {GOALS["hydration"][0]: "goal_floz"}
    if unit == "ml" and not 250 <= goal <= 6000:
        return {GOALS["hydration"][0]: "goal_ml"}
    return {}


class LifeRPGConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create an adventurer."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Name the adventurer, link their Home Assistant user, pick a race and sensors."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options = {k: v for k, v in user_input.items() if k != CONF_NAME}
            await self.async_set_unique_id(slugify(user_input[CONF_NAME]))
            self._abort_if_unique_id_configured()
            if not (errors := _errors(options)):
                return self.async_create_entry(title=user_input[CONF_NAME], data={}, options=options)
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="User"): str,
                vol.Optional(CONF_USER): await _user_selector(self.hass),
                vol.Required(CONF_RACE, default="human"): RACE_SELECTOR,
                vol.Required(CONF_BODY, default="androgynous"): BODY_SELECTOR,
                vol.Optional(CONF_GODDESS): sel.TextSelector(),
                **QUEST_SCHEMA,
            }
        )
        suggested = user_input or {CONF_CLOCK: _clock_default(self.hass)}
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, suggested), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: Any) -> LifeRPGOptionsFlow:
        """Change the linked user, sensors and goals later (the race is for life)."""
        return LifeRPGOptionsFlow()


class LifeRPGOptionsFlow(OptionsFlowWithReload):
    """Edit quests and goals, or the art and AI settings; progress is kept."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick what to change."""
        return self.async_show_menu(step_id="init", menu_options=["quests", "bounties", "goddess", "work", "studio"])

    async def async_step_quests(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The same form as setup, minus name and race."""
        errors: dict[str, str] = {}
        current = self.config_entry.options
        if user_input is not None and not (errors := _errors(user_input)):
            keep = {k: v for k, v in current.items() if k not in QUEST_KEYS}
            return self.async_create_entry(data={**keep, **user_input})
        schema = vol.Schema({vol.Optional(CONF_USER): await _user_selector(self.hass), **QUEST_SCHEMA})
        return self.async_show_form(
            step_id="quests",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or {CONF_CLOCK: _clock_default(self.hass), **current}
            ),
            errors=errors,
        )

    async def async_step_goddess(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Her name and personality (kept apart from the art settings so nothing there can block it)."""
        current = dict(self.config_entry.options)
        if user_input is not None:
            keep = {k: v for k, v in current.items() if k not in GODDESS_KEYS}
            name = " ".join(str(user_input.get(CONF_GODDESS) or "").split())[:30]
            data = {**keep, **{k: v for k, v in user_input.items() if v not in (None, "")}}
            data.pop(CONF_GODDESS, None)
            return self.async_create_entry(data={**data, **({CONF_GODDESS: name} if name else {})})
        schema = vol.Schema(
            {
                vol.Optional(CONF_GODDESS): sel.TextSelector(),
                vol.Required(CONF_PERSONA, default="goddess"): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=PERSONAS, translation_key="goddess_persona", mode=sel.SelectSelectorMode.LIST
                    )
                ),
                vol.Optional(CONF_CHAT_AGENT): sel.ConversationAgentSelector(sel.ConversationAgentSelectorConfig()),
            }
        )
        return self.async_show_form(step_id="goddess", data_schema=self.add_suggested_values_to_schema(schema, current))

    async def async_step_bounties(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The bounty board: small daily side quests, and kids mode (chores a parent posts and approves)."""
        current = dict(self.config_entry.options)
        if user_input is not None:
            keep = {k: v for k, v in current.items() if k not in BOUNTY_KEYS}
            return self.async_create_entry(
                data={**keep, **user_input, CONF_DAILY_BOUNTIES: int(user_input[CONF_DAILY_BOUNTIES])}
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_DAILY_BOUNTIES, default=5): sel.NumberSelector(
                    sel.NumberSelectorConfig(min=0, max=10, step=1, mode=sel.NumberSelectorMode.SLIDER)
                ),
                vol.Required(CONF_KIDS, default=False): sel.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="bounties", data_schema=self.add_suggested_values_to_schema(schema, current)
        )

    async def async_step_work(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Working hours: emergency quests that pop up while you're at work never cost anything."""
        current = dict(self.config_entry.options)
        if user_input is not None:
            keep = {k: v for k, v in current.items() if k not in WORK_KEYS}
            return self.async_create_entry(data={**keep, **user_input})
        schema = vol.Schema(
            {
                vol.Required(CONF_PENALTY, default=WORK_DEFAULTS[CONF_PENALTY]): sel.BooleanSelector(),
                vol.Required(CONF_WORK_DAYS, default=WORK_DEFAULTS[CONF_WORK_DAYS]): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=WEEKDAYS, translation_key="weekday", multiple=True, mode=sel.SelectSelectorMode.LIST
                    )
                ),
                vol.Required(CONF_WORK_START, default=WORK_DEFAULTS[CONF_WORK_START]): sel.TimeSelector(),
                vol.Required(CONF_WORK_END, default=WORK_DEFAULTS[CONF_WORK_END]): sel.TimeSelector(),
                vol.Optional(CONF_WORK_ENTITY): sel.EntitySelector(
                    sel.EntitySelectorConfig(domain=["schedule", "calendar", "binary_sensor", "input_boolean"])
                ),
            }
        )
        return self.async_show_form(step_id="work", data_schema=self.add_suggested_values_to_schema(schema, current))

    async def async_step_studio(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """ComfyUI for the paintings, the LLM for words, and how your adventurer is drawn."""
        errors: dict[str, str] = {}
        current = dict(self.config_entry.options)
        values = {**current, **(user_input or {})}
        url = (values.get(CONF_COMFY_URL) or "").strip().rstrip("/")
        web = url.lower().startswith(("http://", "https://"))
        family = values.get(CONF_FAMILY, "sdxl")
        checkpoints = await list_checkpoints(self.hass, url, family) if url and web else None
        edit_models = await list_edit_models(self.hass, url) if url and web and checkpoints is not None else None
        missing = ""
        if user_input is not None:
            pixel = user_input.get(CONF_ART_STYLE) == "pixel"
            if url and not url.lower().startswith(("http://", "https://")):
                errors[CONF_COMFY_URL] = "bad_url"
            elif url and checkpoints is None and not pixel:
                errors[CONF_COMFY_URL] = "cannot_connect"
            elif (
                url
                and not pixel
                and user_input.get(CONF_FAMILY, "sdxl") != "custom"
                and not user_input.get(CONF_CHECKPOINT)
            ):
                errors[CONF_CHECKPOINT] = "pick_checkpoint"
            elif (
                url
                and not pixel
                and user_input.get(CONF_FAMILY) == "custom"
                and not await self.hass.async_add_executor_job(
                    Path(self.hass.config.path(DOMAIN, "workflow.json")).is_file
                )
            ):
                errors[CONF_FAMILY] = "no_workflow"
            elif (
                url
                and not pixel
                and family != "custom"
                and checkpoints is not None
                and user_input.get(CONF_CHECKPOINT) not in checkpoints
            ):
                errors[CONF_CHECKPOINT] = "not_in_folder_unet" if family == "flux_unet" else "not_in_folder"
            parts: dict[str, Any] = {}
            if url and not pixel and family == "flux_unet" and not errors:
                found = await find_flux_parts(self.hass, url) or {}
                labels = {
                    "clip_l": "clip_l (models/text_encoders)",
                    "t5": "t5xxl (models/text_encoders)",
                    "vae": "ae.safetensors (models/vae)",
                }
                if gaps := [labels[k] for k in FLUX_PARTS if not found.get(k)]:
                    errors[CONF_FAMILY], missing = "flux_parts", ", ".join(gaps)
                parts = {FLUX_PARTS[k]: v for k, v in found.items()}
            edit = user_input.get(CONF_EDIT_MODEL)
            if url and not pixel and edit and not errors:
                found = await find_edit_parts(self.hass, url, edit) or {}
                need = (
                    {
                        "t5": "t5xxl (models/text_encoders)",
                        "clip_l": "clip_l (models/text_encoders)",
                        "vae": "ae.safetensors (models/vae)",
                    }
                    if edit_kind(edit) == "kontext"
                    else {"te": "qwen_2.5_vl_7b (models/text_encoders)", "vae": "qwen_image_vae (models/vae)"}
                )
                if gaps := [label for k, label in need.items() if not found.get(k)]:
                    errors[CONF_EDIT_MODEL], missing = "edit_parts", ", ".join(gaps)
                parts[CONF_EDIT_PARTS] = {k: found.get(k) for k in need}
            if not errors:
                keep = {k: v for k, v in current.items() if k not in STUDIO_KEYS}
                data = {**keep, **user_input, **parts, CONF_COMFY_URL: url}
                return self.async_create_entry(data={k: v for k, v in data.items() if v not in (None, "")})
        schema = vol.Schema(
            {
                vol.Required(CONF_ART_STYLE, default="painted"): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=ART_STYLES, translation_key="art_style", mode=sel.SelectSelectorMode.LIST
                    )
                ),
                vol.Required(CONF_BODY, default="androgynous"): BODY_SELECTOR,
                vol.Optional(CONF_COMFY_URL): sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.URL)),
                vol.Required(CONF_FAMILY, default="sdxl"): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=FAMILY_OPTIONS, translation_key="model_family", mode=sel.SelectSelectorMode.LIST
                    )
                ),
                vol.Optional(CONF_CHECKPOINT): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=checkpoints or ([values[CONF_CHECKPOINT]] if values.get(CONF_CHECKPOINT) else []),
                        custom_value=True,
                        mode=sel.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_PAINT, default=PAINT_OPTIONS): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=PAINT_OPTIONS, translation_key="paint", multiple=True, mode=sel.SelectSelectorMode.LIST
                    )
                ),
                vol.Required(CONF_SPEED, default="balanced"): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=SPEED_OPTIONS, translation_key="paint_speed", mode=sel.SelectSelectorMode.LIST
                    )
                ),
                vol.Required(CONF_FAST_MODEL, default=False): sel.BooleanSelector(),
                vol.Optional(CONF_EDIT_MODEL): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=edit_models or ([values[CONF_EDIT_MODEL]] if values.get(CONF_EDIT_MODEL) else []),
                        custom_value=True,
                        mode=sel.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_AI_TASK): sel.EntitySelector(sel.EntitySelectorConfig(domain="ai_task")),
                vol.Required(CONF_LLM, default=LLM_OPTIONS): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=LLM_OPTIONS,
                        translation_key="llm_features",
                        multiple=True,
                        mode=sel.SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="studio",
            data_schema=self.add_suggested_values_to_schema(schema, values),
            errors=errors,
            description_placeholders={
                "workflow": self.hass.config.path(DOMAIN, "workflow.json"),
                "found": str(len(checkpoints)) if checkpoints is not None else "—",
                "folder": "diffusion_models" if family == "flux_unet" else "checkpoints",
                "missing": missing,
            },
        )


QUEST_KEYS = {
    CONF_CORRECTIONS,
    CONF_CLOCK,
    CONF_USER,
    CONF_BEDTIME,
    CONF_BEDTIME_ON,
    CONF_MANUAL,
    CONF_WATER_UNIT,
    *SOURCES.values(),
    *(g[0] for g in GOALS.values()),
}
GODDESS_KEYS = {CONF_GODDESS, CONF_PERSONA, CONF_CHAT_AGENT}
BOUNTY_KEYS = {CONF_KIDS, CONF_DAILY_BOUNTIES}
WORK_KEYS = {CONF_PENALTY, CONF_WORK_DAYS, CONF_WORK_START, CONF_WORK_END, CONF_WORK_ENTITY}
STUDIO_KEYS = {
    *FLUX_PARTS.values(),
    CONF_EDIT_MODEL,
    CONF_EDIT_PARTS,
    CONF_SPEED,
    CONF_FAST_MODEL,
    CONF_ART_STYLE,
    CONF_BODY,
    CONF_COMFY_URL,
    CONF_FAMILY,
    CONF_CHECKPOINT,
    CONF_PAINT,
    CONF_AI_TASK,
    CONF_LLM,
}
