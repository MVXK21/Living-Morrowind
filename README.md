# Living Morrowind

AI-driven NPCs, creatures and narrator for **OpenMW** (0.49 to 0.51), packaged as a drop-in **Mod Organizer 2** mod.

Talk to anyone in the world in your own words. NPCs remember you, react to your gear, bounty, deeds and surroundings, trade and hand over items, and an evolving narrator chronicles your journey.

Living Morrowind knows **where you are**. Every landmass in your load order is detected automatically:

| Land | From | NPCs talk about |
| --- | --- | --- |
| Vvardenfell | vanilla | ash storms (only during a real Ashstorm), the Blight, Great Houses, the Tribunal |
| Solstheim | Bloodmoon / Tomb of the Snow Prince | snow and blizzards, the Skaal, rieklings, Fort Frostmoth, Raven Rock |
| Mainland Morrowind | Tamriel Rebuilt | Houses Indoril and Dres, Mournhold, Necrom, Old Ebonheart |
| Skyrim | Skyrim: Home of the Nords, New Windhelm | jarls, Reachmen, Nordic barrows, Windhelm |
| Cyrodiil | Project Cyrodiil | the Gold Coast, Anvil, Colovian wine, the Nine Divines |
| Oblivion | Daedric-realm mods | the realm's Daedric Prince |

Based on **Sentient Morrowind** (released with open permissions), with landmass awareness, an MO2-friendly layout and stability fixes.

## Install (MO2 + OpenMW Player)

1. Download `Living Morrowind <version>.zip` from [Releases](../../releases) and install it in MO2 like any other mod. Enable it.
2. In the Plugins tab, make sure `living_morrowind.omwscripts` is enabled.
3. Disable Sentient Morrowind if you had it; Living Morrowind replaces it.

**Requirements:** OpenMW 0.49 to 0.51, [Python 3.10+](https://www.python.org/downloads/) (tick *Add python.exe to PATH*), and a free [Google Gemini API key](https://aistudio.google.com/).

## Play

1. In MO2, right-click **Living Morrowind** and choose **Open in Explorer**.
2. Double-click **`Launch Living Morrowind.bat`**. The first run asks for your Gemini API key and saves it to `.env`. Keep the window open.
3. Launch OpenMW from MO2 as usual. In game, look at someone and press **K** to talk.

The daemon finds your MO2 install, the active profile, its `openmw.cfg` and the `openmw.log` OpenMW Player uses. It then builds a landmass map of your load order in the background, and rebuilds it whenever the load order changes.

## Install without MO2

Extract the zip to a folder of its own (for example `C:\Games\Living Morrowind`) and add it to OpenMW, either in the OpenMW Launcher's **Data Files** tab (then tick `living_morrowind.omwscripts`), or in `openmw.cfg`:

```
data="C:/Games/Living Morrowind"
content=living_morrowind.omwscripts
```

Then run `Launch Living Morrowind.bat` from that folder and start OpenMW normally. Extracting into Morrowind's `Data Files` also works, and other mod managers work as long as the mod ends up as an OpenMW data folder.

Without MO2 the daemon reads `openmw.cfg` and `openmw.log` from OpenMW's standard config folder:

| OS | Folder |
| --- | --- |
| Windows | `Documents\My Games\OpenMW` (OneDrive Documents too) |
| Linux | `~/.config/openmw` (Flatpak: `~/.var/app/org.openmw.OpenMW/config/openmw`) |
| macOS | `~/Library/Preferences/openmw` |

If yours are elsewhere, set `OPENMW_CFG=` and `OPENMW_LOG=` in `.env`.

### Linux and macOS (untested)

The `.bat` launcher is Windows-only. Install the mod as above, copy `env_template.txt` to `.env` and add your Gemini API key, then run `python3 main.py` in the mod folder. This should work but hasn't been tested on those systems yet; please open an issue if it doesn't.

**Coming from Sentient Morrowind?** Copy `scripts/sentient_morrowind/worlds/` from the old mod into `scripts/living_morrowind/worlds/` and your saves keep their NPC memories.

## Repository layout

```
Living Morrowind/          the mod (this folder is what goes in MO2's mods/)
  Launch Living Morrowind.bat   starts the AI daemon
  living_morrowind.omwscripts   OpenMW script registration
  scripts/living_morrowind/     OpenMW Lua scripts + editable config/
  main.py, prompt_generator.py  AI daemon
  landmass.py                   land profiles, location resolver, prompt rewriting
  landmass_autobuild.py         keeps landmass_map.json in sync with the load order
  paths.py                      MO2 / OpenMW Player path discovery
  tools/build_landmass_map.py   load-order scanner (also runnable by hand)
build_release.py           packages the mod into dist/Living Morrowind <version>.zip
```

See [`Living Morrowind/README.txt`](Living%20Morrowind/README.txt) for customization and troubleshooting.

## Building a release

```
python build_release.py 1.0.0
```
