"""Life RPG: Health Connect sensors become a role-playing game, with its own System panel."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from . import services, websocket
from .art import Studio
from .const import ART_URL, DOMAIN, PANEL_PATH, URL_BASE, VERSION
from .coordinator import LifeRPGCoordinator
from .llm_api import LifeRPGAPI

PLATFORMS = [Platform.BUTTON, Platform.EVENT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
type LifeRPGConfigEntry = ConfigEntry[LifeRPGCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the game UI (System panel, cards, paintings), start the art studio, offer tools to Assist."""
    studio = Studio(hass)
    await studio.async_load()
    hass.data[DOMAIN] = {"studio": studio}

    async def _stop(_event: Event) -> None:
        """Stop the painter cleanly when Home Assistant shuts down."""
        await studio.async_stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(URL_BASE, str(Path(__file__).parent / "frontend"), cache_headers=False),
            StaticPathConfig(ART_URL, str(studio.dir), cache_headers=True),  # file names are content hashes
        ]
    )
    llm.async_register_api(hass, LifeRPGAPI(hass=hass, id=DOMAIN, name="Life RPG"))
    script = f"{URL_BASE}/life-rpg.js?v={VERSION}"
    add_extra_js_url(hass, script)  # defines the cards on every dashboard
    # the element's name carries the version, so an app that kept an older panel loaded switches to the new one
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name=f"life-rpg-panel-{VERSION.replace('.', '-')}",
        module_url=script,
        sidebar_title="System",
        sidebar_icon="mdi:sword-cross",
        require_admin=False,
    )
    websocket.async_register(hass)
    services.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LifeRPGConfigEntry) -> bool:
    """Set up one adventurer."""
    coordinator = LifeRPGCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LifeRPGConfigEntry) -> bool:
    """Unload an adventurer, saving progress first."""
    coordinator = entry.runtime_data
    await coordinator.store.async_save(coordinator.game.L)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: LifeRPGConfigEntry) -> None:
    """Delete the adventurer's save file."""
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
