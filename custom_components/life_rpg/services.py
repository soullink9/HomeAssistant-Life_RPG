"""Actions for logging quests from automations, NFC tags, scripts and Apple Shortcuts.

life_rpg.log        add water (in the adventurer's water unit, mL or fl oz) or flights of stairs (negative undoes)
life_rpg.correct    set today's real count for steps, floors or water, and/or the all-time record
life_rpg.log_sleep  last night's sleep: bedtime and wake-up ("22:30" / "06:45" or full date-times); bedtime alone = Lights out only
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, Unauthorized
import voluptuous as vol

from .const import DOMAIN
from .engine.rules import GameError

ADVENTURER = vol.Optional("adventurer")
LOG_SCHEMA = vol.Schema(
    {
        ADVENTURER: str,
        vol.Required("quest"): vol.In(["hydration", "floors"]),
        vol.Required("amount"): vol.All(vol.Coerce(float), vol.Range(min=-5000, max=5000)),
    }
)
CORRECT_SCHEMA = vol.Schema(
    {
        ADVENTURER: str,
        vol.Required("quest"): vol.In(["steps", "floors", "hydration"]),
        vol.Optional("today"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
        vol.Optional("record"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
    }
)
SLEEP_SCHEMA = vol.Schema({ADVENTURER: str, vol.Required("bedtime"): str, vol.Optional("wake"): str})


async def _coordinator(hass: HomeAssistant, call: ServiceCall):
    """The adventurer an action is for: the one named, the caller's own, or the only one."""
    coords = [e.runtime_data for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    if entry_id := call.data.get("adventurer"):
        found = [c for c in coords if c.config_entry.entry_id == entry_id]
    elif call.context.user_id and (mine := [c for c in coords if c.user_id == call.context.user_id]):
        found = mine
    else:
        found = coords if len(coords) == 1 else []
    if not found:
        raise HomeAssistantError("Pick which adventurer to log for.")
    coord = found[0]
    user_id = call.context.user_id
    if user_id and coord.user_id and coord.user_id != user_id:
        user = await hass.auth.async_get_user(user_id)
        if not (user and user.is_admin):
            raise Unauthorized(context=call.context)
    return coord


def async_register(hass: HomeAssistant) -> None:
    """Register the actions."""

    async def log(call: ServiceCall) -> ServiceResponse:
        """Service life_rpg.log: add water or stairs by hand."""
        coord = await _coordinator(hass, call)
        try:
            total = await coord.async_action("log", quest=call.data["quest"], amount=call.data["amount"])
        except GameError as err:
            raise HomeAssistantError(str(err)) from err
        return {"quest": call.data["quest"], "today": total}

    async def log_sleep(call: ServiceCall) -> ServiceResponse:
        """Service life_rpg.log_sleep: log bedtime and wake-up time."""
        coord = await _coordinator(hass, call)
        try:
            res = await coord.async_action("log_sleep", bedtime=call.data["bedtime"], wake=call.data.get("wake"))
        except GameError as err:
            raise HomeAssistantError(str(err)) from err
        return {"hours": res} if call.data.get("wake") else {"fell_asleep": res}

    async def correct(call: ServiceCall) -> ServiceResponse:
        """Service life_rpg.correct: fix a count the sensor got wrong."""
        coord = await _coordinator(hass, call)
        try:
            return await coord.async_action(
                "correct", quest=call.data["quest"], today=call.data.get("today"), record=call.data.get("record")
            )
        except GameError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN, "correct", correct, schema=CORRECT_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(DOMAIN, "log", log, schema=LOG_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, "log_sleep", log_sleep, schema=SLEEP_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
