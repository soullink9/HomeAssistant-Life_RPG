"""Life RPG sensors, for automations and plain dashboards (the System panel shows everything)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LifeRPGConfigEntry
from .const import DOMAIN, VERSION
from .coordinator import LifeRPGCoordinator
from .engine.rules import QUESTS


@dataclass(frozen=True, kw_only=True)
class RPGSensorDescription(SensorEntityDescription):
    """A sensor reading one slice of the game view."""

    value: Callable[[dict[str, Any]], Any]
    attrs: Callable[[dict[str, Any]], dict[str, Any]] = lambda d: {}


MEASURE = SensorStateClass.MEASUREMENT
CORE = (
    RPGSensorDescription(
        key="level",
        icon="mdi:shield-star",
        state_class=MEASURE,
        value=lambda d: d["level"],
        attrs=lambda d: {
            "rank": d["rank"],
            "job": (d["job"] or {}).get("title", "Villager"),
            "title": (d["title"] or {}).get("name"),
            "race": d["race"]["name"],
            "xp": d["xp"],
            "next_level_xp": d["next_level_xp"],
        },
    ),
    RPGSensorDescription(
        key="level_progress",
        icon="mdi:progress-star",
        native_unit_of_measurement=PERCENTAGE,
        state_class=MEASURE,
        value=lambda d: d["progress"],
        attrs=lambda d: {"xp_into_level": d["level_xp"], "xp_for_level": d["level_span"]},
    ),
    RPGSensorDescription(
        key="xp",
        icon="mdi:star-four-points",
        native_unit_of_measurement="XP",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value=lambda d: d["xp"],
    ),
    RPGSensorDescription(
        key="xp_today",
        icon="mdi:star-plus",
        native_unit_of_measurement="XP",
        state_class=MEASURE,
        value=lambda d: d["xp_today"],
        attrs=lambda d: {
            "base_xp": d["base_xp"],
            "multiplier": d["multiplier"],
            "bonus_xp": d["bonus_xp"],
            "quests_done": d["done"],
            "quests_needed": d["needed"],
            "day_cleared": d["cleared"],
            "perfect_day": d["perfect"],
        },
    ),
    RPGSensorDescription(
        key="streak",
        icon="mdi:fire",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=MEASURE,
        value=lambda d: d["streak"],
        attrs=lambda d: {
            "day_cleared": d["cleared"],
            "quests_left_to_clear": max(d["needed"] - d["done"], 0),
            "shields": d["shields"],
            "multiplier": d["multiplier"],
            "best_streak": d["best_streak"],
            "penalty_quest": d["penalty"] is not None and not d["penalty"]["met"],
            "penalty_quests_needed": (d["penalty"] or {}).get("need"),
        },
    ),
    RPGSensorDescription(
        key="rank",
        icon="mdi:alpha-s-box",
        value=lambda d: d["rank"],
        attrs=lambda d: {"next_rank_level": d["next_rank_level"]},
    ),
    RPGSensorDescription(
        key="job",
        icon="mdi:sword-cross",
        value=lambda d: (d["job"] or {}).get("title", "Villager"),
        attrs=lambda d: {
            "job": (d["job"] or {}).get("name"),
            "job_level": (d["job"] or {}).get("level"),
            "recommended": d["recommended_job"],
        },
    ),
    RPGSensorDescription(
        key="title",
        icon="mdi:crown",
        value=lambda d: (d["title"] or {}).get("name") or "None",
        attrs=lambda d: {"earned": len(d["titles"])},
    ),
    RPGSensorDescription(
        key="race",
        icon="mdi:dna",
        value=lambda d: d["race"]["gift"]["name"],
        attrs=lambda d: {
            "race": d["race"]["name"],
            "gift_tier": d["race"]["gift"]["tier"],
            "next_evolution_level": d["race"]["next_evolution"],
            "effects": d["effects"],
        },
    ),
    RPGSensorDescription(
        key="labyrinth",
        icon="mdi:stairs-down",
        native_unit_of_measurement=PERCENTAGE,
        state_class=MEASURE,
        value=lambda d: d["labyrinth"]["pct"],
        attrs=lambda d: {
            "floor": d["labyrinth"]["floor"],
            "guardian": d["labyrinth"]["name"],
            "creature": d["labyrinth"]["kind"],
            "element": d["labyrinth"]["element"],
            "elite": d["labyrinth"]["elite"],
            "cursed": d["labyrinth"]["cursed"],
            "floor_trait": d["labyrinth"]["trait"]["name"],
            "hp": d["labyrinth"]["hp"],
            "damage": d["labyrinth"]["damage"],
            "defeated": d["labyrinth"]["defeated"],
            "reward_xp": d["labyrinth"]["reward"],
            "ends": d["labyrinth"]["ends"],
            "bestiary": d["bestiary_total"],
        },
    ),
    RPGSensorDescription(
        key="daily_choice",
        icon="mdi:cards-playing-outline",
        value=lambda d: (d["choice"] or {}).get("status", "none"),
        attrs=lambda d: {
            k: v for k, v in (d["choice"] or {}).items() if k in ("voice", "text", "kind", "reward_xp", "deadline")
        },
    ),
    RPGSensorDescription(
        key="chests",
        icon="mdi:treasure-chest",
        state_class=MEASURE,
        value=lambda d: len(d["gear"]["chests"]),
        attrs=lambda d: {"shards": d["gear"]["shards"], "gear_score": d["gear"]["score"]},
    ),
    RPGSensorDescription(
        key="gold",
        icon="mdi:cash-multiple",
        native_unit_of_measurement="gold",
        state_class=MEASURE,
        value=lambda d: d["gold"],
        attrs=lambda d: {
            "bag": {b["name"]: b["count"] for b in d["bag"]},
            "merchant_mood": (d["market"] or {}).get("mood"),
        },
    ),
    RPGSensorDescription(
        key="emergency_quest",
        icon="mdi:alarm-light",
        value=lambda d: (d["emergency"] or {}).get("status", "none"),
        attrs=lambda d: {k: v for k, v in (d["emergency"] or {}).items() if k != "status"},
    ),
    RPGSensorDescription(
        key="devotion",
        icon="mdi:hands-pray",
        value=lambda d: d["devotion"]["tier"],
        attrs=lambda d: {
            "faith": d["devotion"]["faith"],
            "next_tier": d["devotion"]["next_tier"],
            "next_at": d["devotion"]["next_at"],
            "goddess_says": d["goddess"]["line"],
            "morning_message": (d["lore"].get("morning") or {}).get("text")
            if (d["lore"].get("morning") or {}).get("ref") == d["now"][:10]
            else None,
        },
    ),
)
ICONS = {
    "stamina": "mdi:run-fast",
    "strength": "mdi:arm-flex",
    "vitality": "mdi:heart-pulse",
    "intelligence": "mdi:brain",
    "wisdom": "mdi:meditation",
}


def _attribute(attr: str) -> RPGSensorDescription:
    """Sensor description for one attribute (its points, XP and the skills that train it)."""
    return RPGSensorDescription(
        key=attr,
        icon=ICONS[attr],
        state_class=MEASURE,
        value=lambda d: d["attrs"][attr]["points"],
        attrs=lambda d: {
            "xp": d["attrs"][attr]["xp"],
            "next_point_xp": d["attrs"][attr]["next_point_xp"],
            **{
                f"skill_{k}": v
                for q, sk in d["skills"].items()
                if QUESTS[q].attr == attr
                for k, v in sk.items()
                if k in ("name", "proficiency", "grade")
            },
        },
    )


def _quest(quest: str) -> RPGSensorDescription:
    """Sensor description for one quest (today's percent done)."""
    return RPGSensorDescription(
        key=f"{QUESTS[quest].attr}_quest",
        icon=ICONS[QUESTS[quest].attr],
        native_unit_of_measurement=PERCENTAGE,
        state_class=MEASURE,
        value=lambda d: d["quests"][quest]["pct"],
        attrs=lambda d: {"quest": quest, **{k: v for k, v in d["quests"][quest].items() if k not in ("pct", "attr")}},
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: LifeRPGConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the adventurer's sensors."""
    coordinator = entry.runtime_data
    quests = list(coordinator.game.goals)
    descriptions = [*CORE, *(_attribute(QUESTS[q].attr) for q in quests), *(_quest(q) for q in quests)]
    wanted = {f"{entry.entry_id}_{d.key}" for d in descriptions}
    registry = er.async_get(hass)
    for old in er.async_entries_for_config_entry(registry, entry.entry_id):
        if old.domain == "sensor" and old.unique_id not in wanted:  # removed quest or retired sensor
            registry.async_remove(old.entity_id)
    async_add_entities(RPGSensor(coordinator, d) for d in descriptions)


def player_device(coordinator: LifeRPGCoordinator) -> DeviceInfo:
    """One service device per adventurer, so entity ids read sensor.<adventurer>_<name>."""
    entry = coordinator.config_entry
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Life RPG",
        model="Adventurer",
        sw_version=VERSION,  # shown on the device page, handy for bug reports
        entry_type=DeviceEntryType.SERVICE,
    )


class RPGSensor(CoordinatorEntity[LifeRPGCoordinator], SensorEntity):
    """A Life RPG sensor."""

    _attr_has_entity_name = True
    entity_description: RPGSensorDescription

    def __init__(self, coordinator: LifeRPGCoordinator, description: RPGSensorDescription) -> None:
        """Bind the sensor to its adventurer."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = player_device(coordinator)

    @property
    def native_value(self) -> Any:
        """Current value."""
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Details for dashboards and automations."""
        return self.entity_description.attrs(self.coordinator.data)
