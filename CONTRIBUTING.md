# Contributing to Life RPG

Thanks for helping. This page is for anyone changing the code: where things live, the rules the code keeps,
how to check a change, and how to release one.

## Ground rules

- **Nothing talks to the internet.** The only outside connections are the ComfyUI address the user enters and
  the AI Task entity or conversation agent they pick in Home Assistant. No fonts, scripts, images, analytics or
  update checks from anywhere else, in the integration or in the panel.
- **No new dependencies.** `manifest.json` has no `requirements`, and the panel has no build step. Pillow is used
  when present (it ships with Home Assistant) and everything works without it.
- **The engine stays pure.** `custom_components/life_rpg/engine/` never imports Home Assistant. It takes readings
  and a clock, and returns a view and events. That's what lets the simulations play 30 years in minutes.
- **The game decides every number.** The LLM only writes words, and it's told exactly what each reward is (a
  character's line that oversells a prize is thrown away).
- **Saves must keep loading.** A save is the JSON from `new_ledger()` in `engine/rules.py`. When it loads, any
  key the save doesn't have takes its default (`new_ledger() | saved`), so adding a key is safe. Renaming or
  reshaping a key needs a small conversion in `Game.__init__` so existing players keep their progress.

## Where things live

The [Files table in the README](README.md#files) has the full map. The usual places to make a change:

| To change | Look in |
|---|---|
| Names, flavour text, jobs, titles, badges, hidden quests, choices, side quests | `engine/content.py` |
| XP, levels, ranks, streaks, fines, limits and other tuning numbers | `engine/rules.py` |
| Chests, gear, affixes, enhancing, salvage, bonus caps | `engine/loot.py` |
| Prices, stock, deliveries, haggling | `engine/market.py` (rules) and `engine/shop.py` (the player's actions) |
| How characters look and the painting prompts | `engine/appearance.py` |
| ComfyUI workflows, the painting queue, the art folder | `art.py` |
| What the LLM is asked to write | `lore.py` |
| The panel and cards | `frontend/life-rpg.js`, styles in `frontend/styles.js` |
| The pixel art | `frontend/art.js` (adventurers, items, monsters) and `frontend/cast.js` (everyone else) |

**Adding a player action** (a new button): add the method to the `Game` class (or the mixin it belongs in),
add it to the handler table in `LifeRPGCoordinator.async_action` (`coordinator.py`), add any new argument to the
`life_rpg/action` schema in `websocket.py`, then call it from the panel with `this.action("name", {...})`.
Add an Assist tool in `llm_api.py` if it makes sense by voice.

**Adding an event:** add it to `EVENT_TYPES` in `engine/rules.py`, give it a line in `describe()` in
`frontend/life-rpg.js` (toasts and the log), add it to `translations/en.json` under `entity.event.achievements`, and list it
in the README's Entities section.

**Adding an option:** the form is in `config_flow.py`, its labels in `translations/en.json`, and the option is
read in `coordinator.py`. Options apply without losing progress (the entry reloads).

## Checking a change

You need Python 3.13. The engine checks need nothing else; for the rest:

```sh
pip install -r tests/requirements.txt
```

| Command | Time | When |
|---|---|---|
| `ruff check custom_components tests` and `ruff format custom_components tests` | seconds | every change |
| `for f in custom_components/life_rpg/frontend/*.js; do node --check "$f"; done` | seconds | any panel change |
| `python3 tests/test_game.py` | a minute or two | every change |
| `python3 tests/ha/test_integration.py` | seconds | any change outside `engine/` |
| `python3 tests/sim_longrun.py 30 1 2 3 4 5 6` | long (minutes per player and seed, on all cores) | any change to how the game plays |
| `python3 tests/ha/soak.py 3 sdxl` and `python3 tests/ha/soak.py 3 flux_unet` | several minutes each | any change to painting, writing or the coordinator |

Any change to how the game plays (rules, rewards, content pools, the market) gets the full 30-year run before it
ships: some problems (a list that grows forever, a number that overflows, a pool that runs dry) only show up
after years of play. The run prints `30/30 runs finished cleanly` when all is well.

GitHub Actions runs lint, the unit tests, a 3-year soak, the Home Assistant tests, `hassfest` and the HACS checks
on every push.

Code style: `ruff` settles formatting and import order (see `pyproject.toml`). Every function and class has a
docstring, and comments say why, not what. In the panel, keep to plain JavaScript modules with no build step.

## Releasing

1. Change the version in all four places (the unit tests fail if they disagree):
   - `VERSION` in `custom_components/life_rpg/const.py`
   - `version` in `custom_components/life_rpg/manifest.json`
   - `const VERSION` in `custom_components/life_rpg/frontend/life-rpg.js`
   - the `?v=` on every `import` in `frontend/life-rpg.js` and `frontend/cast.js`

   The version is part of the panel's element name and of every script URL. That is what makes browsers and the
   Home Assistant app load the new panel instead of one they kept in memory.
2. Add the release to `CHANGELOG.md`.
3. Run the checks above, including the 30-year run if the game changed.
4. Commit, tag `vX.Y.Z`, push, and publish a GitHub release from the tag. HACS offers releases as updates.

## Reporting bugs

Open an issue with your Home Assistant version, the Life RPG version, what you did and what you expected.
The log helps: **Settings → System → Logs**, search for `life_rpg`. For painting problems, say which model type and
image-edit model you use; for LLM problems, which integration provides your AI Task entity.
