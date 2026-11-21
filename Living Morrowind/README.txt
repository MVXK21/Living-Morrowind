================================================================================
                              LIVING MORROWIND
            AI-driven NPCs, creatures and narrator for OpenMW (0.49 - 0.51)
================================================================================

Talk to anyone in the world in your own words. NPCs remember you, react to your
gear, bounty, deeds and surroundings, trade and hand over items, and an evolving
narrator chronicles your journey.

Living Morrowind knows WHERE you are. On Vvardenfell people grumble about ash
storms (only when there really is one); on Solstheim it is snow and rieklings; on
the Morrowind mainland (Tamriel Rebuilt) it is Great House Indoril and Dres; in
Skyrim (Skyrim: Home of the Nords, New Windhelm...) it is jarls and Reachmen; on
Cyrodiil's Gold Coast (Project Cyrodiil) it is Colovian wine and the Nine. Your
load order is scanned automatically, so every landmass mod you have is covered.

Based on Sentient Morrowind by BooskTheBold (open permissions), with landmass
awareness, a Mod Organizer 2 friendly layout, and stability fixes.
Original mod: https://www.nexusmods.com/morrowind/mods/60221

--------------------------------------------------------------------------------
REQUIREMENTS
--------------------------------------------------------------------------------
  1. OpenMW 0.49, 0.50 or 0.51.
  2. Mod Organizer 2 with the "OpenMW Player" plugin (standard in OpenMW
     modlists such as NEMAS). Manual installs also work; see the end of this file.
  3. Python 3.10 or newer: https://www.python.org/downloads/
     During setup, tick "Add python.exe to PATH".
  4. A free Google Gemini API key: https://aistudio.google.com/  -> "Get API key"

--------------------------------------------------------------------------------
INSTALL (MO2)
--------------------------------------------------------------------------------
  1. In MO2, install the Living Morrowind archive like any other mod
     (Install a new mod from an archive, or drag it into the mod list) and tick it.
  2. In the Plugins tab, make sure living_morrowind.omwscripts is enabled
     (it appears as "living_morrowind.omwscripts.esp" with OpenMW Player).

  Do NOT enable Sentient Morrowind at the same time. Living Morrowind replaces it.

  Coming from Sentient Morrowind? Copy the folder
      scripts/sentient_morrowind/worlds   (from the old mod)
  to  scripts/living_morrowind/worlds     (in this mod)
  and your existing saves keep their NPC memories.

--------------------------------------------------------------------------------
PLAY
--------------------------------------------------------------------------------
  1. In MO2, right-click Living Morrowind -> "Open in Explorer".
  2. Double-click  "Launch Living Morrowind.bat".
     - The first time, it asks for your Gemini API key and saves it to .env.
     - Leave this window open while you play.
  3. Launch OpenMW from MO2's executable list as usual.
  4. In game, look at an NPC or creature and press K to talk.
     Press K with nobody targeted for the narrator. ESC or Goodbye closes the window.

  Tip: you can add "Launch Living Morrowind.bat" to MO2's executables
  (Executables -> + -> Add from file) to start the daemon from MO2's dropdown.

--------------------------------------------------------------------------------
WHAT HAPPENS AUTOMATICALLY
--------------------------------------------------------------------------------
  - The daemon finds your MO2 install and active profile, reads that profile's
    openmw.cfg (your load order) and watches the openmw.log OpenMW writes,
    wherever OpenMW Player puts it (profile folder, local saves, or Documents).
  - On first start, and whenever your load order changes, it builds
    landmass_map.json: every exterior cell and interior in your load order mapped
    to Vvardenfell / Solstheim / mainland Morrowind / Skyrim / Cyrodiil / Oblivion.
    This takes a few seconds and runs in the background.
  - Conversations, memories and personalities are stored per save in
    scripts/living_morrowind/worlds/ inside this mod folder.

--------------------------------------------------------------------------------
CUSTOMIZING
--------------------------------------------------------------------------------
  scripts/living_morrowind/config/
    custom_npc_instructions.json        how NPCs talk and behave
    custom_creature_instructions.json   creatures
    custom_narrator_instructions.json   the narrator
    custom_campaign_rules.json          summaries, journal, humor
    custom_mod_instructions.json        your own extra rules
    custom_lore.json                    world lore; "landmass_lore" sets what
                                        NPCs believe about each land
  landmass.py                           climate, wildlife, faiths and taboos per
                                        land; region -> land table
  .env                                  API key, optional model names, and
                                        OPENMW_CFG / OPENMW_LOG overrides for
                                        unusual setups (see env_template.txt)
  addons/                               drop-in Python addons

--------------------------------------------------------------------------------
TROUBLESHOOTING
--------------------------------------------------------------------------------
  "Python 3.10 or newer was not found"
      Install Python from python.org with "Add python.exe to PATH" ticked.
  NPC replies time out after 25s
      The daemon window must be open. Check it for errors (bad API key, quota).
      The full log is daemon_debug.log in this folder.
  Daemon says "No openmw.log found yet"
      Normal before the game's first launch; it attaches automatically.
  Wrong landmass detected
      Delete landmass_map.json and restart the daemon to rebuild it. Regions the
      builder reports as "not in landmass.REGION_LANDMASS" can be added to
      landmass.py.
  Change your API key
      Edit or delete .env in this folder.

--------------------------------------------------------------------------------
MANUAL INSTALL (no MO2)
--------------------------------------------------------------------------------
  1. Extract the archive to a folder of its own, e.g. C:\Games\Living Morrowind
     (keep everything together: the daemon must stay next to "scripts").
  2. Add that folder to OpenMW, either way:
       - OpenMW Launcher -> Data Files -> add the folder as a data directory,
         then tick living_morrowind.omwscripts in the content list, or
       - edit openmw.cfg and add these two lines:
             data="C:/Games/Living Morrowind"
             content=living_morrowind.omwscripts
  3. Run "Launch Living Morrowind.bat" from that folder, then start OpenMW
     normally (launcher or openmw.exe).

  Extracting straight into Morrowind's "Data Files" folder also works, but it
  scatters the daemon files among your game data; a separate folder is tidier.
  You still need to tick living_morrowind.omwscripts.

  Without MO2, the daemon reads openmw.cfg and openmw.log from OpenMW's standard
  config folder:
      Windows   Documents\My Games\OpenMW   (including OneDrive Documents)
      Linux     ~/.config/openmw   (Flatpak: ~/.var/app/org.openmw.OpenMW/config/openmw)
      macOS     ~/Library/Preferences/openmw
  If yours are elsewhere, set OPENMW_CFG= and OPENMW_LOG= in .env.
  Other mod managers (Vortex etc.) work the same way as long as the mod ends up
  as an OpenMW data folder.

--------------------------------------------------------------------------------
LINUX AND macOS (untested)
--------------------------------------------------------------------------------
  The launcher .bat is Windows-only. On Linux or macOS:
    1. Install the mod as above (add the folder as an OpenMW data directory).
    2. Copy env_template.txt to .env and put your Gemini API key in it.
    3. Open a terminal in the mod folder and run:   python3 main.py
  Python 3.10+ is required. This should work but has not been tested on these
  systems yet; please report problems on GitHub.

--------------------------------------------------------------------------------
CREDITS
--------------------------------------------------------------------------------
  BooskTheBold - author of Sentient Morrowind, the original mod this is built
                 on (AI daemon, OpenMW Lua scripts, dialogue UI, memory system,
                 prompt design). Released with open permissions; please support
                 the original: https://www.nexusmods.com/morrowind/mods/60221
  MVXK21       - Living Morrowind changes: landmass awareness, MO2 packaging,
                 fixes.  https://github.com/MVXK21/Living-Morrowind
================================================================================
