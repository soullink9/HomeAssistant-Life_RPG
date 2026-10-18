"""A minimal stand-in for Home Assistant, so the integration's own code can run end to end without it.

Not a substitute for real Home Assistant: it checks our code paths (reading states, unit conversion, sleep
sessions, sensors, the event entity, the config flow's schema, websocket commands) against small fakes of the
Home Assistant APIs we use. If Home Assistant changes one of those APIs, update the fake here to match.
Needs voluptuous (pip install voluptuous).
"""

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
import sys
import types
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "custom_components"))  # so `import life_rpg` finds the integration
import voluptuous as vol  # noqa: E402,F401 - the tests use it through `from stubs import *`

TZ = ZoneInfo("America/New_York")
NOW = [datetime(2026, 10, 12, 9, 0, tzinfo=TZ)]


def mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class Generic:
    def __class_getitem__(cls, item):
        return cls


# --- homeassistant stubs -----------------------------------------------------
def callback(f):
    return f


class State:
    def __init__(self, state, attributes=None, when=None):
        self.state, self.attributes = state, attributes or {}
        self.last_reported = self.last_changed = when or NOW[0].astimezone(timezone.utc)


class HomeAssistant:
    def __init__(self):
        self.states = types.SimpleNamespace(get=lambda e: self._states.get(e))
        self._states = {}


class Platform(StrEnum):
    EVENT = "event"
    SENSOR = "sensor"


class UnitOfTime(StrEnum):
    DAYS = "d"


mod("homeassistant")
mod(
    "homeassistant.const",
    EVENT_HOMEASSISTANT_STOP="homeassistant_stop",
    ATTR_UNIT_OF_MEASUREMENT="unit_of_measurement",
    STATE_UNAVAILABLE="unavailable",
    STATE_UNKNOWN="unknown",
    Platform=Platform,
    CONF_NAME="name",
    PERCENTAGE="%",
    UnitOfTime=UnitOfTime,
)


class Context:
    def __init__(self, user_id=None, parent_id=None, id=None):
        self.user_id, self.parent_id, self.id = user_id, parent_id, id


mod("homeassistant.core", Event=object, HomeAssistant=HomeAssistant, State=State, callback=callback, Context=Context)


class ConfigEntry(Generic):
    def __init__(self, options, title="User"):
        self.options, self.title, self.entry_id, self._unload = options, title, "abc123", []

    def async_on_unload(self, f):
        self._unload.append(f)

    def async_create_background_task(self, hass, coro, name):
        return asyncio.get_running_loop().create_task(coro)


class FlowBase:
    def async_show_form(self, **kw):
        return {"type": "form", **kw}

    def add_suggested_values_to_schema(self, schema, values):
        return schema

    def async_create_entry(self, **kw):
        return {"type": "create_entry", **kw}


class ConfigFlow(FlowBase):
    def __init_subclass__(cls, domain=None, **kw):
        super().__init_subclass__(**kw)

    async def async_set_unique_id(self, uid):
        self.uid = uid

    def _abort_if_unique_id_configured(self):
        pass


class OptionsFlowWithReload(FlowBase):
    def async_show_menu(self, **kw):
        return {"type": "menu", **kw}


mod(
    "homeassistant.config_entries",
    ConfigEntry=ConfigEntry,
    ConfigFlow=ConfigFlow,
    ConfigFlowResult=dict,
    OptionsFlowWithReload=OptionsFlowWithReload,
)
mod("homeassistant.helpers")
mod(
    "homeassistant.helpers.event",
    async_track_state_change_event=lambda h, e, f: lambda: None,
    async_track_time_change=lambda h, f, **kw: lambda: None,
)


class Store(Generic):
    saved = {}

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return Store.saved.get(self.key)

    def async_delay_save(self, f, delay):
        import json

        Store.saved[self.key] = json.loads(json.dumps(f()))

    async def async_save(self, data):
        Store.saved[self.key] = data


mod("homeassistant.helpers.storage", Store=Store)


class DataUpdateCoordinator(Generic):
    def __init__(self, hass, logger, *, config_entry, name, update_interval):
        self.hass, self.config_entry, self.data, self.listeners = hass, config_entry, None, []

    async def async_refresh(self):
        self.data = await self._async_update_data()
        for f in self.listeners:
            f()

    def async_add_listener(self, f):
        self.listeners.append(f)
        return lambda: self.listeners.remove(f)

    async def async_request_refresh(self):
        await self.async_refresh()


class CoordinatorEntity(Generic):
    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def async_added_to_hass(self):
        self.coordinator.listeners.append(self._handle_coordinator_update)

    def _handle_coordinator_update(self):
        pass


mod(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=DataUpdateCoordinator,
    CoordinatorEntity=CoordinatorEntity,
)


def parse_datetime(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def as_local(d):
    return (d if d.tzinfo else d.replace(tzinfo=TZ)).astimezone(TZ)


util = mod("homeassistant.util", slugify=lambda t: t.lower().replace(" ", "_"))
util.dt = mod("homeassistant.util.dt", now=lambda: NOW[0], as_local=as_local, parse_datetime=parse_datetime)


class SensorStateClass(StrEnum):
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"


from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True, kw_only=True)
class SensorEntityDescription:
    key: str
    icon: str | None = None
    native_unit_of_measurement: str | None = None
    state_class: str | None = None


mod("homeassistant.components")
mod(
    "homeassistant.components.sensor",
    SensorEntity=object,
    SensorEntityDescription=SensorEntityDescription,
    SensorStateClass=SensorStateClass,
)


class EventEntity:
    fired = []

    def _trigger_event(self, t, a):
        if t not in self._attr_event_types:
            raise ValueError(t)
        EventEntity.fired.append((t, a))

    def async_write_ha_state(self):
        pass


mod("homeassistant.components.event", EventEntity=EventEntity)
mod("homeassistant.helpers.device_registry", DeviceEntryType=types.SimpleNamespace(SERVICE="service"), DeviceInfo=dict)
mod("homeassistant.helpers.entity_platform", AddConfigEntryEntitiesCallback=object)
REMOVED = []
REG_ENTITIES = {}  # entity_id -> SimpleNamespace(entity_id, device_id): what the registry knows
_reg = types.SimpleNamespace(async_remove=REMOVED.append, async_get=lambda eid: REG_ENTITIES.get(eid))
_old = [
    types.SimpleNamespace(domain="sensor", unique_id="abc123_level", entity_id="sensor.alex_smith_level"),
    types.SimpleNamespace(
        domain="sensor", unique_id="abc123_charisma_quest", entity_id="sensor.alex_smith_charisma_quest"
    ),
    types.SimpleNamespace(domain="event", unique_id="abc123_achievements", entity_id="event.alex_smith_achievements"),
]
er = mod(
    "homeassistant.helpers.entity_registry",
    async_get=lambda h: _reg,
    async_entries_for_config_entry=lambda r, i: _old,
    async_entries_for_device=lambda r, dev, **kw: [e for e in REG_ENTITIES.values() if e.device_id == dev],
)
sys.modules["homeassistant.helpers"].entity_registry = er


class Sel:
    def __init__(self, *a, **kw):
        pass

    def __call__(self, v):
        return v


sel = mod(
    "homeassistant.helpers.selector",
    NumberSelector=Sel,
    NumberSelectorConfig=dict,
    NumberSelectorMode=types.SimpleNamespace(BOX="box"),
    EntitySelector=Sel,
    EntitySelectorConfig=dict,
    TimeSelector=Sel,
    BooleanSelector=Sel,
)
sys.modules["homeassistant.helpers"].selector = sel

# --- v2 extra stubs ---------------------------------------------------------------
import json as _json

sel.SelectSelector = Sel
sel.SelectSelectorConfig = dict
sel.SelectOptionDict = dict
sel.SelectSelectorMode = types.SimpleNamespace(LIST="list", DROPDOWN="dropdown")
sys.modules["homeassistant.helpers"].config_validation = mod(
    "homeassistant.helpers.config_validation", config_entry_only_config_schema=lambda d: lambda c: c
)
mod("homeassistant.helpers.typing", ConfigType=dict)
REGISTERED = {}


async def _reg_panel(hass, **kw):
    REGISTERED["panel"] = kw


mod("homeassistant.components.panel_custom", async_register_panel=_reg_panel)
sys.modules["homeassistant.components"].panel_custom = sys.modules["homeassistant.components.panel_custom"]
mod("homeassistant.components.frontend", add_extra_js_url=lambda h, u: REGISTERED.setdefault("js", u))
mod("homeassistant.components.http", StaticPathConfig=lambda *a, **k: (a, k))
WS = {}


def websocket_command(schema):
    def deco(f):
        f.schema = schema
        return f

    return deco


def async_response(f):
    f.is_async = True
    return f


ws_mod = mod(
    "homeassistant.components.websocket_api",
    ActiveConnection=object,
    async_register_command=lambda h, f: WS.setdefault(f.__name__, f),
    websocket_command=websocket_command,
    async_response=async_response,
)
sys.modules["homeassistant.components"].websocket_api = ws_mod


class Conn:
    def __init__(self, uid, admin=False):
        self.user = types.SimpleNamespace(id=uid, is_admin=admin)
        self.out = []
        self.subscriptions = {}

    def send_result(self, i, r=None):
        self.out.append(("result", i, _json.loads(_json.dumps(r))))

    def send_error(self, i, code, m):
        self.out.append(("error", i, code, m))

    def send_event(self, i, e):
        self.out.append(("event", i, _json.loads(_json.dumps(e))))


class Users:
    async def async_get_users(self):
        return [
            types.SimpleNamespace(id="u1", name="Kai", system_generated=False, is_active=True),
            types.SimpleNamespace(id="sys", name="Supervisor", system_generated=True, is_active=True),
        ]
