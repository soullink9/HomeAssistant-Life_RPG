This project was primarily created for personal use and for my family. While I may provide updates, they are not guaranteed. However, if you've stumbled upon this and find it interesting, feel free to download and use it. I had a great time building this and hope you enjoy it.

Note: Built with the assistance of Claude.ai. I’m putting it here now so you don't have to hunt for it below.

=========================================================================================================

# Life RPG: the System

A game for Home Assistant. Your phone's health sensors become daily quests, and the rest is an RPG built to be played for years.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=soullink9&repository=HomeAssistant-Life_RPG&category=integration)
[![Open your Home Assistant instance and start setting up Life RPG.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=life_rpg)

- XP and levels that never cap, with letter ranks on top (E → S, then S+1, S+2…)
- eight jobs, each with its own level, passives and skills
- skill proficiency that grows with every day you practise
- a racial gift that evolves down the path you train most
- a labyrinth: one floor a week, forever, each guarded by a generated monster
- daily choices from a travelling cast of merchants, spirits and rivals
- emergency, penalty and hidden quests, and a bounty board (with a kids mode for chores)
- loot: chests, six gear slots, six rarities, named uniques, enhancement
- titles, endless badges, and devotion to a goddess whose only believer is you
- **gold and a market**: Marrow Fennick's cart restocks three times a day, and he loves a good haggle
- **painted art** from your own ComfyUI, with the pixel art as the stand-in
- **your LLM in the game**: talk to the goddess, haggle in your own words, get written mornings, side quests, item lore and a weekly chronicle, and play by voice through Assist

Everything lives in a full-screen **System** panel in the sidebar. Each logged-in Home Assistant user sees their own adventurer and can watch the rest of the household's. Matching dashboard cards are included. Setup is all in the UI: no YAML, no helpers to create, nothing to add as a dashboard resource.

## Install

**Needs:** Home Assistant 2026.9 or newer. Optional: [ComfyUI](https://github.com/comfyanonymous/ComfyUI) for paintings, and an LLM integration with an AI Task entity (Ollama, for example) for the goddess's and the merchant's words.

1. **Download.** Press the first button above to open this repository in HACS (or in HACS go to ⋮ → **Custom repositories** and add `https://github.com/soullink9/HomeAssistant-Life_RPG` as an **Integration**), download **Life RPG** and restart Home Assistant. Without HACS, copy `custom_components/life_rpg` from the [latest release](https://github.com/soullink9/HomeAssistant-Life_RPG/releases/latest) into `/config/custom_components/` and restart.
2. **Add an adventurer.** Press the second button, or go to **Settings → Devices & services → Add integration → Life RPG**. Each entry is one adventurer: pick a name, the Home Assistant user who plays, a race, and the sensors and goals for each quest.
3. **Play.** Open **System** in the sidebar.

On Android, the quests read the companion app's Health Connect sensors (daily steps, sleep duration, daily floors, daily hydration). Any quest can also be logged by hand. The [Installation](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Installation) and [Phones and Sensors](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Phones-and-Sensors) pages have the details, including iPhone.

## Documentation

The [wiki](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki) has everything else:

| Page | What's in it |
|---|---|
| [Installation](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Installation) | Download, setup, every option, and updating. |
| [Phones and Sensors](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Phones-and-Sensors) | Android and iPhone sensors, logging by hand, and sensors that count wrong. |
| [How the Game Works](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/How-the-Game-Works) | Quests, streaks, emergencies, choices, the bounty board, jobs, skills, the labyrinth, races, gear, titles, badges, devotion and pacing. |
| [Market and Haggling](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Market-and-Haggling) | Gold, deliveries, consumables, cosmetics and haggling. |
| [Paintings and ComfyUI](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Paintings-and-ComfyUI) | Pixel art or paintings, models, image-edit models, the Gallery and painting speed. |
| [The Goddess and Your LLM](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/The-Goddess-and-Your-LLM) | The goddess, words from your own LLM, and playing by voice. |
| [Screens and Entities](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Screens-and-Entities) | The panel's tabs, dashboard cards, example automations, sensors and events. |
| [Privacy](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Privacy) | What leaves your Home Assistant. |
| [Development](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Development) | Tests and the file map. |

## Privacy

Nothing calls out to the internet. The only outside connections are to the ComfyUI address you enter and the AI Task entity or conversation agent you pick; with a local LLM such as Ollama, everything stays on your network. See [Privacy](https://github.com/soullink9/HomeAssistant-Life_RPG/wiki/Privacy).

## Contributing

Bug reports and pull requests are welcome: [open an issue](https://github.com/soullink9/HomeAssistant-Life_RPG/issues/new/choose). [CONTRIBUTING.md](CONTRIBUTING.md) covers how the code is laid out, how to run the checks and how to release a new version.

## Credits
Code from other people in this project:
- `frontend/art.js`: the seeded random numbers behind the pixel art are adapted from the public-domain `xmur3` hash and `mulberry32` generator, as collected by [bryc](https://github.com/bryc/code/blob/master/jshash/PRNGs.md).
- `art.py`: the built-in ComfyUI workflows (SDXL, Flux, Flux Kontext and Qwen Image Edit) follow the node layouts of [ComfyUI's example workflows](https://comfyanonymous.github.io/ComfyUI_examples/).

Everything else was written for this project, with help from Claude, Anthropic's AI model.

## License
[GNU General Public License v3.0](LICENSE). You may use, study, share and change Life RPG; if you share a changed version, share its source under the same licence.
