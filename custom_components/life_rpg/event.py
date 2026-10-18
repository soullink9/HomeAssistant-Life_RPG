"""Life RPG achievements: one event entity per player (level ups, quests, bosses...)."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LifeRPGConfigEntry
from .coordinator import LifeRPGCoordinator
from .engine.rules import EVENT_TYPES
from .sensor import player_device


async def async_setup_entry(
    hass: HomeAssistant, entry: LifeRPGConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the achievements entity."""
    async_add_entities([Achievements(entry.runtime_data)])


class Achievements(CoordinatorEntity[LifeRPGCoordinator], EventEntity):
    """Fires an event for every achievement; trigger automations or show a logbook card."""

    _attr_has_entity_name = True
    _attr_translation_key = "achievements"
    _attr_icon = "mdi:trophy"
    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator: LifeRPGCoordinator) -> None:
        """Bind to the player."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_achievements"
        self._attr_device_info = player_device(coordinator)

    async def async_added_to_hass(self) -> None:
        """Deliver anything earned during setup."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire this update's events, one state change each."""
        events = self.coordinator.data["events"]
        for event in events:
            data = {k: v for k, v in event.items() if k != "type"}
            self._trigger_event(event["type"], {"player": self.coordinator.config_entry.title, **data})
            self.async_write_ha_state()
        if not events:
            self.async_write_ha_state()  # keep availability current
