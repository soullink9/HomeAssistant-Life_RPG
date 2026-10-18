"""One-tap logging buttons (a glass of water, a flight of stairs) for dashboards, NFC tags and automations."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LifeRPGConfigEntry
from .const import GLASS, STAIR_FLIGHT
from .coordinator import LifeRPGCoordinator
from .sensor import player_device

BUTTONS = {"hydration": ("log_water", "mdi:cup-water", None), "floors": ("log_floor", "mdi:stairs-up", STAIR_FLIGHT)}


async def async_setup_entry(
    hass: HomeAssistant, entry: LifeRPGConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a button for each quest that's logged by hand."""
    coordinator = entry.runtime_data
    async_add_entities(LogButton(coordinator, q) for q in BUTTONS if q in coordinator.manual)


class LogButton(ButtonEntity):
    """Adds one glass of water or one flight of stairs to today's quest."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LifeRPGCoordinator, quest: str) -> None:
        """Bind to the adventurer."""
        key, icon, self.amount = BUTTONS[quest]
        if quest == "hydration":  # a glass: 250 mL or 8 fl oz
            self.amount = GLASS[coordinator.water_unit]
        self.coordinator, self.quest = coordinator, quest
        self._attr_translation_key, self._attr_icon = key, icon
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = player_device(coordinator)

    async def async_press(self) -> None:
        """Log it."""
        await self.coordinator.async_action("log", quest=self.quest, amount=self.amount)
