"""
Landmass awareness for Sentient Morrowind.

Works out which landmass the player is on (Vvardenfell, Solstheim, mainland
Morrowind / Tamriel Rebuilt, Skyrim / Skyrim: Home of the Nords, Cyrodiil /
Project Cyrodiil) and produces prompt text so NPCs, creatures and the narrator
stop treating every place as Vvardenfell.

Sources of truth, best first:
  1. Live data sent by the Lua side (player_data.location): cell region,
     exterior grid coordinates, current weather, exterior door exits of the
     current interior, and the last exterior the player stood in.
  2. landmass_map.json, generated from the actual load order by
     tools/build_landmass_map.py (exterior grid -> landmass, interior cell
     name -> landmass via door links, named settlements).
  3. Hand-written region / settlement tables below (work without the map).
"""

import json
import os
import re
import threading

MAP_FILENAME = "landmass_map.json"

# ---------------------------------------------------------------------------
# Landmass profiles
# ---------------------------------------------------------------------------

LANDMASSES = {
    "vvardenfell": {
        "name": "Vvardenfell",
        "full_name": "Vvardenfell, the volcanic island district of Morrowind",
        "province": "Morrowind",
        "vvardenfell_lies": "",
        "summary": (
            "Vvardenfell is the volcanic island at the heart of Morrowind, ringed around Red Mountain and "
            "the Ghostfence. Great Houses Hlaalu, Redoran and Telvanni vie for power, the Tribunal Temple "
            "rules the faithful, Ashlander tribes roam the wastes, and Imperial forts keep the Emperor's peace."
        ),
        "climate": "ash storms and Blight storms near Red Mountain and the Ashlands, humid swamp along the Bitter Coast, warm grassland in the Ascadian Isles and Grazelands",
        "fears": "the Blight and Corprus spreading from Red Mountain, ash-creatures, Sixth House cultists and troubling ash-dreams",
        "fauna": "cliff racers, guar, kagouti, alit, nix-hounds, netch, kwama, scribs, mudcrabs, slaughterfish and dreugh",
        "flora": "saltrice, trama root, fire petal, hackle-lo, marshmerrow, comberry, ash yam and bungler's bane",
        "travel": "silt striders, boats and gondolas, Mages Guild guides, and Dunmer propylon chambers",
        "religion": "the Tribunal (Almalexia, Sotha Sil and Vivec) and ancestor worship, with the Imperial Cult of the Nine Divines among foreigners",
        "powers": "Great Houses Hlaalu, Redoran and Telvanni, the Tribunal Temple, the Ashlander tribes, the Imperial Legion, Camonna Tong and Morag Tong",
        "drink": "sujamma, mazte or flin",
        "foreigners": "Outlanders (non-Dunmer) are viewed with suspicion by many native Dunmer.",
        "not_here": [],
    },
    "solstheim": {
        "name": "Solstheim",
        "full_name": "Solstheim, a cold, wild island in the Sea of Ghosts north-west of Vvardenfell",
        "province": "Morrowind (Imperial-administered island)",
        "vvardenfell_lies": "to the south-east, across the Sea of Ghosts",
        "summary": (
            "Solstheim is a frozen island of pine forest, snowfields and glaciers. The Nordic Skaal live in "
            "their village in harmony with the All-Maker, the Imperial Legion holds Fort Frostmoth, and the "
            "East Empire Company runs the ebony mining colony of Raven Rock. Thirsk mead hall stands on a lake "
            "in the north."
        ),
        "climate": "biting cold, snow, blizzards, icy sea wind and long grey skies; never volcanic ash",
        "fears": "werewolves, draugr in the barrows, rieklings raiding travellers, bitter blizzards and the dark spirits the Skaal speak of",
        "fauna": "wolves, bears, rieklings, horkers, bristlebacks, grahl, spriggans, draugr and frost atronachs",
        "flora": "holly berries, belladonna, wolfsbane, heather and pine",
        "travel": "ships to and from Khuul and Ebonheart, and long treks on foot through the snow",
        "religion": "the Skaal faith in the All-Maker and nature spirits, Nordic tradition, and the Imperial Cult at Fort Frostmoth",
        "powers": "the Skaal, the Imperial Legion at Fort Frostmoth, the East Empire Company at Raven Rock, and the Nords of Thirsk",
        "drink": "mead or Nord mead",
        "foreigners": "Mainlanders, Imperials and Dunmer are outsiders here; the Skaal are wary of anyone who disrespects the land.",
        "not_here": [
            "ash storms or volcanic ash", "the Blight or Blight storms", "the Ghostfence",
            "silt striders", "cliff racers as local pests", "the Ashlands",
        ],
    },
    "morrowind_mainland": {
        "name": "mainland Morrowind",
        "full_name": "the Morrowind mainland, the Dunmer heartland across the Inner Sea from Vvardenfell",
        "province": "Morrowind",
        "vvardenfell_lies": "across the Inner Sea",
        "summary": (
            "The Morrowind mainland is the old Dunmer heartland across the Inner Sea from Vvardenfell. "
            "Great House Indoril holds the orthodox Temple lands around Mournhold, Great House Dres keeps its "
            "slave plantations in the southern swamps, Telvanni wizards rule mushroom towers along the "
            "north-eastern coasts and isles, and Hlaalu traders push into the west. Old Ebonheart is the "
            "Imperial seat of the province, and Necrom is the holy city of the dead. Vvardenfell, Red Mountain "
            "and the Blight are across the water; mainlanders know of them mostly as news, pilgrim stories and "
            "worried rumours."
        ),
        "climate": "varies by region: temperate grassland and farmland, river valleys, forests, southern swamps and highlands; ash storms only happen in the Armun Ashlands",
        "fears": "bandits and smugglers, Daedra worshippers, swamp sickness, unrest between the Great Houses, and worried rumours of the Blight across the water on Vvardenfell",
        "fauna": "guar, nix-hounds, kagouti, alit, netch, kwama, mudcrabs, slaughterfish and dreugh, along with mainland beasts such as velk and ornada",
        "flora": "saltrice, comberry, marshmerrow, hackle-lo, scathecraw, and the crops and herbs of the mainland farms",
        "travel": "silt striders, ships along the Inner Sea and the coasts, guild guides, and the old Velothi roads",
        "religion": "the Tribunal Temple, which is strongest and most orthodox here (Almalexia herself rules from Mournhold), plus ancestor worship and the Imperial Cult in Imperial towns",
        "powers": "Great Houses Indoril, Dres, Telvanni and Hlaalu, the Tribunal Temple and its Ordinators, the Imperial administration at Old Ebonheart and the Imperial Legion",
        "drink": "sujamma, mazte or greef",
        "foreigners": "Outlanders are viewed with suspicion by many native Dunmer, and even Vvardenfell Dunmer are sometimes treated as frontier provincials.",
        "not_here": [
            "Red Mountain looming nearby", "the Ghostfence", "Blight storms as a local danger",
            "ash storms (except in the Armun Ashlands)",
        ],
    },
    "skyrim": {
        "name": "Skyrim",
        "full_name": "Skyrim, the cold Nordic province west of Morrowind",
        "province": "Skyrim",
        "vvardenfell_lies": "far to the east, beyond the Velothi Mountains",
        "summary": (
            "Skyrim is the cold homeland of the Nords: highlands, heaths, pine forests, snowfields and rivers. "
            "Nordic jarls rule the holds under the High King and the Empire, and the Imperial Legion patrols the "
            "roads. In the west, the native Reachfolk clans (witchmen and hagraven-led covens among them) resist "
            "outsiders from the crags of the Reach; in the east, Eastmarch and ancient Windhelm, the old City of "
            "Kings, look toward the Morrowind border. Old Nordic barrows dot the hills."
        ),
        "climate": "cold highland air, rain, fog, frost and snow in the mountains, crisp clear days on the heaths; never volcanic ash",
        "fears": "Reachmen raiders and witchmen, hagravens, draugr stirring in the barrows, trolls, bandits on the roads and hard winters",
        "fauna": "wolves, bears, elk and deer, goats, foxes, mudcrabs and horkers along the coast, trolls, spriggans and draugr",
        "flora": "juniper berries, snowberries, mountain flowers, pine, heather and barley",
        "travel": "the roads between the holds, river crossings and coastal ships",
        "religion": "the Nine Divines (Talos is honoured by Nords), old Nordic traditions and the Ysmir legends; Reachfolk keep their own old gods and spirit worship",
        "powers": "the Nordic jarls and their housecarls, the Imperial Legion, the Reachmen clans, the Fighters and Mages Guilds and local mining concerns",
        "drink": "mead, ale or Nord mead",
        "foreigners": "Dunmer, Altmer and other Elves are foreigners here and are often met with Nordic mistrust; Nords speak bluntly and value strength and honour.",
        "not_here": [
            "ash storms or volcanic ash", "the Blight", "Red Mountain nearby", "the Ghostfence",
            "silt striders", "Great House politics as local affairs", "cliff racers", "the Tribunal as the local faith",
        ],
    },
    "cyrodiil": {
        "name": "Cyrodiil",
        "full_name": "the Gold Coast and Colovian west of Cyrodiil, the Imperial heartland",
        "province": "Cyrodiil",
        "vvardenfell_lies": "far to the north-east, across most of Tamriel",
        "summary": (
            "The western Gold Coast of Cyrodiil is a warm, prosperous Colovian land of sea cliffs, vineyards, "
            "rolling hills and busy ports. The great harbour city of Anvil looks out over the Abecean Sea, "
            "Stirk Isle lies offshore, and Colovian towns, farms and estates follow the coast and hills inland. "
            "This is the heart of the Empire: Imperial law, the Nine Divines and Colovian nobility rule here, "
            "and pirates and smugglers haunt the Abecean."
        ),
        "climate": "a mild, sunny Mediterranean-like coast with salt sea breezes, warm afternoons, summer rain and occasional sea storms; never volcanic ash",
        "fears": "Abecean pirates and smugglers, bandits on the roads, goblin warrens, sea storms and shipwrecks, and Daedra cults in hidden shrines",
        "fauna": "mudcrabs, slaughterfish, wolves, boars, bears, rats, goblins, and gulls along the coast",
        "flora": "grapes and vineyards, wheat, olives, lavender, sea flowers and coastal herbs",
        "travel": "ships out of Anvil and the coastal ports, roads and carriages between the Colovian towns",
        "religion": "the Nine Divines of the Imperial Cult, especially Dibella and Julianos, with chapels in every town",
        "powers": "the Imperial Legion and city watch, Colovian counts and nobility, the East Empire Company and merchant houses, the Fighters and Mages Guilds, and Abecean pirates",
        "drink": "Colovian wine, Cyrodiilic brandy or ale",
        "foreigners": "Cyrodiil is cosmopolitan; Dunmer and other provincials are foreigners but not unusual. Colovians are proud, traditional and practical.",
        "not_here": [
            "ash storms or volcanic ash", "the Blight", "Red Mountain nearby", "the Ghostfence",
            "silt striders", "Great House politics as local affairs", "cliff racers", "the Tribunal as the local faith",
            "Dunmer calling locals 'Outlanders' (here the Dunmer are the outlanders)",
        ],
    },
    "oblivion": {
        "name": "Oblivion",
        "full_name": "a realm of Oblivion, the planes of the Daedric Princes beyond Mundus",
        "province": "Oblivion (not part of Tamriel)",
        "vvardenfell_lies": "back in Mundus, beyond the veil of Oblivion",
        "summary": (
            "This is a plane of Oblivion, shaped by the will of a Daedric Prince rather than by nature. "
            "Mortal provinces, Great Houses, Imperial law and ordinary weather mean little here; the realm's "
            "master, its Daedra and its own strange rules are what matter."
        ),
        "climate": "unnatural and shaped by the realm's Daedric master; no ordinary mortal weather",
        "fears": "the realm's Daedric Prince and their servants, being trapped forever, and losing one's soul",
        "fauna": "Daedra and the strange beings of this plane",
        "flora": "the uncanny plants of this plane, and daedra hearts, void salts and other Daedric reagents",
        "travel": "portals, gates and the will of the realm's master",
        "religion": "the realm's Daedric Prince, whom everything here serves or fears",
        "powers": "the realm's Daedric Prince and their Daedra",
        "drink": "whatever strange drink the realm offers",
        "foreigners": "Every mortal here is a stranger in a Daedric realm.",
        "not_here": [
            "ash storms", "the Blight", "Red Mountain", "silt striders",
            "ordinary weather, towns or provincial politics as local affairs",
        ],
    },
    "unknown": {
        "name": "an uncertain part of Tamriel",
        "full_name": "an unidentified place in Tamriel",
        "province": "Unknown",
        "vvardenfell_lies": "",
        "summary": "The player's exact landmass could not be determined. Rely on the cell name, nearby people and objects to judge where you are, and do not assume Vvardenfell.",
        "climate": "whatever the cell name and surroundings suggest",
        "fears": "local dangers fitting the surroundings",
        "fauna": "creatures fitting the surroundings",
        "flora": "plants fitting the surroundings",
        "travel": "local roads and ships",
        "religion": "faiths fitting the people present",
        "powers": "the powers fitting the people present",
        "drink": "the local drink",
        "foreigners": "",
        "not_here": [],
    },
}

# Region id (lower case) -> landmass. Water regions are resolved by grid instead.
REGION_LANDMASS = {
    # Vvardenfell (vanilla + Firemoth)
    "ascadian isles region": "vvardenfell",
    "ashlands region": "vvardenfell",
    "azura's coast region": "vvardenfell",
    "bitter coast region": "vvardenfell",
    "grazelands region": "vvardenfell",
    "molag mar region": "vvardenfell",
    "red mountain region": "vvardenfell",
    "sheogorad": "vvardenfell",
    "sheogorad region": "vvardenfell",
    "west gash region": "vvardenfell",
    "firemoth region": "vvardenfell",
    "julan-shar region": "vvardenfell",  # Secrets of the Crystal City
    "agb dunbal region": "vvardenfell",  # Darkness Over Dunbal (isles north of Vvardenfell)
    "agb_cove region": "vvardenfell",
    "agb_kilhaven region": "vvardenfell",
    # Solstheim (Bloodmoon / Tomb of the Snow Prince)
    "brodir grove region": "solstheim",
    "felsaad coast region": "solstheim",
    "hirstaang forest region": "solstheim",
    "isinfier plains region": "solstheim",
    "moesring mountains region": "solstheim",
    "thirsk region": "solstheim",
    "lokken region": "solstheim",  # Whitewolf of Lokken
    "unnamed isle": "solstheim",  # Unnamed Isle (Freydis Barrow), off western Solstheim
    # Mainland Morrowind (Tamriel Rebuilt)
    "aanthirin region": "morrowind_mainland",
    "aranyon pass region": "morrowind_mainland",
    "alt orethan region": "morrowind_mainland",
    "armun ashlands region": "morrowind_mainland",
    "boethiah's spine region": "morrowind_mainland",
    "dagon urul region": "morrowind_mainland",
    "lan orethan region": "morrowind_mainland",
    "mephalan vales region": "morrowind_mainland",
    "molag ruhn region": "morrowind_mainland",
    "molagreahd region": "morrowind_mainland",
    "nedothril region": "morrowind_mainland",
    "old ebonheart region": "morrowind_mainland",
    "othreleth woods region": "morrowind_mainland",
    "roth roryn region": "morrowind_mainland",
    "sacred lands region": "morrowind_mainland",
    "shipal-shin region": "morrowind_mainland",
    "sundered scar region": "morrowind_mainland",
    "telvanni isles region": "morrowind_mainland",
    "thirr valley region": "morrowind_mainland",
    "velothi mountains region": "morrowind_mainland",
    "deshaan plains region": "morrowind_mainland",
    "grey meadows region": "morrowind_mainland",
    "clambering moor region": "morrowind_mainland",
    "arnesian jungle region": "morrowind_mainland",
    "salt marsh region": "morrowind_mainland",
    "mudflats region": "morrowind_mainland",
    "ascadian bluffs region": "morrowind_mainland",
    "helnim fields region": "morrowind_mainland",
    "uld vraech region": "morrowind_mainland",
    # Skyrim (Skyrim: Home of the Nords)
    "druadach highlands region": "skyrim",
    "falkheim region": "skyrim",
    "lorchwuir heath region": "skyrim",
    "midkarth region": "skyrim",
    "sundered hills region": "skyrim",
    "vorndgad forest region": "skyrim",
    "reach region": "skyrim",
    "karth river region": "skyrim",
    "skyrim": "skyrim",  # New Windhelm - City of Kings
    "fjollvint region": "skyrim",  # Beneath the Permafrost
    # Cyrodiil (Project Cyrodiil)
    "dasek marsh region": "cyrodiil",
    "gilded hills region": "cyrodiil",
    "gold coast region": "cyrodiil",
    "stirk isle region": "cyrodiil",
    "kvatch region": "cyrodiil",
    "colovian highlands region": "cyrodiil",
    "strident coast region": "cyrodiil",
}

# Seas shared by several landmasses: the grid decides.
WATER_REGIONS = {"sea of ghosts region", "padomaic ocean region", "abecean sea region", "inner sea region"}

# Short, safe notes per region (only what the region names make plain).
REGION_NOTES = {
    "armun ashlands region": "ash wastes of the mainland where ash storms do blow, home to Ashlander camps",
    "sacred lands region": "the holy lands around Necrom, the City of the Dead, full of tombs and pilgrims",
    "telvanni isles region": "Telvanni wizard isles with mushroom towers",
    "velothi mountains region": "the high Velothi Mountains on Morrowind's western border",
    "old ebonheart region": "the Imperial city of Old Ebonheart on the Inner Sea coast",
    "thirr valley region": "the Thirr River valley",
    "othreleth woods region": "the Othreleth woods",
    "shipal-shin region": "the far south of Morrowind near the Black Marsh border",
    "sea of ghosts region": "the cold Sea of Ghosts",
    "padomaic ocean region": "the open Padomaic Ocean off Morrowind's eastern coast",
    "druadach highlands region": "the Druadach highlands of the Reach",
    "skyrim": "Eastmarch and the ancient Nordic city of Windhelm",
    "fjollvint region": "the frozen far north of Skyrim",
    "lorchwuir heath region": "open heathland",
    "vorndgad forest region": "deep pine forest",
    "midkarth region": "the valley of the Karth River",
    "gold coast region": "the sunny Gold Coast of the Abecean Sea",
    "gilded hills region": "the golden, vine-covered Gilded Hills",
    "dasek marsh region": "the Dasek Marsh",
    "stirk isle region": "Stirk Isle in the Abecean Sea",
    "abecean sea region": "the Abecean Sea",
    "hirstaang forest region": "the snowy Hirstaang pine forest",
    "isinfier plains region": "the frozen Isinfier plains",
    "moesring mountains region": "the icy Moesring Mountains",
    "felsaad coast region": "the frozen Felsaad coast",
}

# Interior-only places and well known towns (cell name prefix, lower case).
SETTLEMENT_LANDMASS = {
    "mournhold": "morrowind_mainland",
    "old mournhold": "morrowind_mainland",
    "sotha sil": "morrowind_mainland",
    "old ebonheart": "morrowind_mainland",
    "necrom": "morrowind_mainland",
    "firewatch": "morrowind_mainland",
    "almas thirr": "morrowind_mainland",
    "akamora": "morrowind_mainland",
    "port telvannis": "morrowind_mainland",
    "helnim": "morrowind_mainland",
    "bal foyen": "morrowind_mainland",
    "raven rock": "solstheim",
    "fort frostmoth": "solstheim",
    "skaal village": "solstheim",
    "thirsk": "solstheim",
    "karthwasten": "skyrim",
    "windhelm": "skyrim",
    "kynholm": "skyrim",
    "dragonstar": "skyrim",
    "markarth": "skyrim",
    "anvil": "cyrodiil",
    "brina cross": "cyrodiil",
    "charach": "cyrodiil",
    "archad": "cyrodiil",
    "stirk": "cyrodiil",
    "kvatch": "cyrodiil",
    "seyda neen": "vvardenfell",
    "balmora": "vvardenfell",
    "vivec": "vvardenfell",
    "ald'ruhn": "vvardenfell",
    "sadrith mora": "vvardenfell",
    "caldera": "vvardenfell",
    "pelagiad": "vvardenfell",
    "suran": "vvardenfell",
    "ebonheart": "vvardenfell",
}

# Places reached only by magic/teleport, whose door links mislead the map.
# Any cell whose name starts with one of these always gets this landmass.
FORCED_PREFIX_LANDMASS = {
    "oblivion,": "oblivion",
    "solstheim,": "solstheim",
    "mournhold": "morrowind_mainland",
    "old mournhold": "morrowind_mainland",
    "sotha sil": "morrowind_mainland",
}


def forced_landmass(cell_name):
    name = str(cell_name or "").strip().lower()
    for prefix, lm in FORCED_PREFIX_LANDMASS.items():
        if name.startswith(prefix):
            return lm
    return None


# Rule labels in the NPC constraint list that only make sense on Vvardenfell.
# Each is replaced by a landmass-appropriate rule built from the profile.
RULE_REWRITES = {
    "THE ASH AND THE SKY": lambda p, w: (
        f"- WEATHER & CLIMATE: You live in {p['name']}. The climate here is: {p['climate']}. "
        + (f"The weather right now is {w}; only remark on weather that matches it. " if w else "")
        + "Never complain about ash storms or choking ash unless the current weather really is an Ashstorm."
    ),
    "BLIGHT & SHADOWS": lambda p, w: f"- LOCAL FEARS: Worry about the dangers people really face in {p['name']}: {p['fears']}.",
    "REALISTIC MONSTER SPECIES": lambda p, w: f"- REALISTIC MONSTER SPECIES: Reference the real fauna of {p['name']} ({p['fauna']}) rather than creatures from other provinces.",
    "ALCHEMICAL LORE": lambda p, w: f"- ALCHEMICAL LORE: Refer to ingredients that grow or are traded in {p['name']} ({p['flora']}) when discussing alchemy or potion-making.",
    "TRAVEL MOTIVATIONS": lambda p, w: (
        f"- TRAVEL MOTIVATIONS & GEOGRAPHICAL CONSTRAINTS: You may express desires to travel to other settlements of {p['name']} or beyond, "
        f"but realistically evaluate your limits: lack of septims for passage, fear of the wilds ({p['fears']}), duties that tie you to your post, "
        f"or bad weather. Travel here is by {p['travel']}. Remember your place of origin and the real dangers of the roads of {p['name']}."
    ),
    "SILT STRIDER": lambda p, w: f"- TRAVEL SERVICES: Travel here is by {p['travel']}. If you provide travel, offer your routes, fares and destinations; do NOT beg for gold or complain about wanting to leave your post.",
    "TRIBUNAL VS. IMPERIAL RELIGION": lambda p, w: f"- RELIGION: Ground your oaths and beliefs in the faiths of {p['name']}: {p['religion']}, according to your race and faction.",
}

# Phrase swaps applied to instruction text (never to memories) when not on Vvardenfell.
PHRASE_SWAPS_FOREIGN = [
    ("Third Era Vvardenfell", "Third Era {name}"),
    ("physical reality of Vvardenfell", "physical reality of {name}"),
    ("Vvardenfell terms", "{name} terms"),
    ("not native to Vvardenfell", "not native to {name}"),
    ("tone of Vvardenfell", "tone of {name}"),
    ("Vvardenfell is a lawless and violent frontier", "{name} is a harsh and often violent land"),
    ("active ashstorms", "the local weather"),
    ("Silt Strider port operators", "ship captains, caravan and carriage drivers"),
    ("Silt Strider operator", "ship captain or driver"),
    ("seasoned Redoran warrior", "seasoned local warrior"),
    ("heading to Arrille's Tradehouse or sharing a bottle of sujamma", "heading to a local tavern or sharing some {drink}"),
    ("(flin, mazte, sujamma)", "({drink})"),
    ("An NPC in Balmora does NOT magically or telepathically know what the player did in Seyda Neen", "An NPC in one town does NOT magically or telepathically know what the player did in another town"),
    ("ambient facts of life in Morrowind", "ambient facts of life in {name}"),
    ("Morrowind is a gritty, raw, and adult world", "{name} is a gritty, raw, and adult world"),
    ("grounded in Morrowind lore", "grounded in Elder Scrolls lore for {name}"),
    ("nearby mudcrabs, Silt Strider calls,", "nearby wildlife, the everyday sounds of {name},"),
    ("Vvardenfell", "{name}"),
]
PHRASE_SWAPS_MAINLAND = [
    ("Third Era Vvardenfell", "Third Era Morrowind"),
    ("physical reality of Vvardenfell", "physical reality of mainland Morrowind"),
    ("Vvardenfell terms", "Third Era Morrowind terms"),
    ("not native to Vvardenfell", "not native to Morrowind"),
    ("tone of Vvardenfell", "tone of Morrowind"),
    ("Vvardenfell is a lawless and violent frontier", "Morrowind is a harsh and often violent land"),
    ("active ashstorms", "the local weather"),
    ("heading to Arrille's Tradehouse", "heading to the local cornerclub"),
    ("An NPC in Balmora does NOT magically or telepathically know what the player did in Seyda Neen", "An NPC in one town does NOT magically or telepathically know what the player did in another town"),
    ("dangerous realities of Vvardenfell roads", "dangerous realities of the mainland roads"),
    ("Vvardenfell", "mainland Morrowind"),
]

# ---------------------------------------------------------------------------
# Map loading
# ---------------------------------------------------------------------------

_map_lock = threading.Lock()
_map_cache = {"mtime": None, "data": None}


def _map_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), MAP_FILENAME)


def load_map():
    path = _map_path()
    with _map_lock:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            _map_cache["data"] = {}
            _map_cache["mtime"] = None
            return {}
        if _map_cache["mtime"] == mtime and _map_cache["data"] is not None:
            return _map_cache["data"]
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            grid = {}
            for key, val in data.get("grid", {}).items():
                x, y = key.split(",")
                grid[(int(x), int(y))] = val
            data["_grid"] = grid
        except Exception as e:
            print(f"[LANDMASS] Failed to load {MAP_FILENAME}: {e}")
            data = {}
        _map_cache["data"] = data
        _map_cache["mtime"] = mtime
        return data


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _lower(s):
    return str(s).strip().lower() if s else ""


def _region_landmass(region_id):
    r = _lower(region_id)
    if not r or r in WATER_REGIONS:
        return None
    if r in REGION_LANDMASS:
        return REGION_LANDMASS[r]
    m = load_map().get("region_landmass", {})
    return m.get(r)


def _grid_entry(gx, gy):
    if gx is None or gy is None:
        return None
    try:
        gx, gy = int(gx), int(gy)
    except (TypeError, ValueError):
        return None
    grid = load_map().get("_grid", {})
    if (gx, gy) in grid:
        return grid[(gx, gy)]
    # Nearest known cell (open sea cells may have no record)
    best, best_d = None, None
    for (x, y), entry in grid.items():
        d = (x - gx) ** 2 + (y - gy) ** 2
        if best_d is None or d < best_d:
            best, best_d = entry, d
    if best is not None and best_d <= 36 * 36:
        return best
    return None


def _grid_landmass_fallback(gx, gy):
    """Coarse coordinate boxes for when no map file exists."""
    try:
        gx, gy = int(gx), int(gy)
    except (TypeError, ValueError):
        return None
    if gx <= -90:
        return "cyrodiil" if gy <= -30 else "skyrim"
    if (-35 <= gx <= -9 and gy >= 21) or (-35 <= gx <= -19 and gy >= 13):
        return "solstheim"
    if -20 <= gx <= 25 and -20 <= gy <= 28:
        return "vvardenfell"
    if -60 < gx < 60 and -70 < gy < 40:
        return "morrowind_mainland"
    return None


def _from_grid(gx, gy):
    entry = _grid_entry(gx, gy)
    if entry:
        return entry[0], (entry[1] if len(entry) > 1 else ""), (entry[2] if len(entry) > 2 else "")
    lm = _grid_landmass_fallback(gx, gy)
    return (lm, "", "") if lm else (None, "", "")


def _settlement_prefix(cell_name):
    name = _lower(cell_name)
    if not name:
        return ""
    return name.split(",")[0].strip()


def _from_cell_name(cell_name):
    name = _lower(cell_name)
    if not name:
        return None
    forced = forced_landmass(name)
    if forced:
        return forced
    m = load_map()
    interiors = m.get("interiors", {})
    if name in interiors:
        return interiors[name]
    prefix = _settlement_prefix(name)
    for table in (m.get("settlements", {}), m.get("prefixes", {}), SETTLEMENT_LANDMASS):
        if prefix in table:
            return table[prefix]
    mm = re.match(r"cell \((-?\d+),\s*(-?\d+)\)", name)
    if mm:
        return _from_grid(mm.group(1), mm.group(2))[0]
    return None


def region_display(region_id):
    r = _lower(region_id)
    if not r:
        return ""
    names = load_map().get("regions", {})
    if names.get(r):
        return names[r]
    return " ".join(w.capitalize() if w not in ("of",) else w for w in r.split())


def resolve(player):
    """Return a dict describing where the player is."""
    player = player or {}
    loc = player.get("location") if isinstance(player.get("location"), dict) else {}
    cell = loc.get("cell") or player.get("cell") or ""
    is_ext = bool(loc.get("is_exterior"))
    region = loc.get("region") or ""
    weather = loc.get("weather") or ""
    landmass, source, settlement = None, "", ""

    if is_ext:
        landmass = _region_landmass(region)
        if landmass:
            source = "cell region"
        lm, grid_region, grid_name = _from_grid(loc.get("grid_x"), loc.get("grid_y"))
        if not landmass and lm:
            landmass, source = lm, "exterior grid map"
        if not region:
            region = grid_region
        settlement = cell if cell and not cell.lower().startswith("cell (") else grid_name
    else:
        landmass = _from_cell_name(cell)
        if landmass:
            source = "interior cell map"
        if not landmass:
            for ex in loc.get("exits") or []:
                if not isinstance(ex, dict):
                    continue
                lm = _region_landmass(ex.get("region"))
                if not lm and ex.get("grid_x") is not None:
                    lm = _from_grid(ex.get("grid_x"), ex.get("grid_y"))[0]
                if not lm and ex.get("cell"):
                    lm = _from_cell_name(ex.get("cell"))
                if lm:
                    landmass, source = lm, "door leading outside"
                    region = region or ex.get("region") or ""
                    break
        if not landmass:
            lm = _region_landmass(loc.get("last_ext_region"))
            if not lm and loc.get("last_ext_grid_x") is not None:
                lm = _from_grid(loc.get("last_ext_grid_x"), loc.get("last_ext_grid_y"))[0]
            if lm:
                landmass, source = lm, "last exterior visited"
        if not region:
            region = loc.get("last_ext_region") or ""
        settlement = cell

    if not landmass:
        landmass, source = "unknown", "undetermined"

    return {
        "landmass": landmass,
        "profile": LANDMASSES.get(landmass, LANDMASSES["unknown"]),
        "cell": cell,
        "settlement": settlement,
        "region_id": _lower(region),
        "region": region_display(region),
        "is_exterior": is_ext,
        "weather": weather,
        "source": source,
    }


def resolve_world(world_dir):
    """Resolve from a world folder's environment.json / player_tracker.json."""
    player = {}
    for fname in ("environment.json", "player_tracker.json"):
        path = os.path.join(world_dir, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            p = data.get("player", data) if fname == "environment.json" else data
            if isinstance(p, dict) and p:
                if not player:
                    player = dict(p)
                else:
                    for k, v in p.items():
                        player.setdefault(k, v)
                if fname == "environment.json" and not player.get("cell"):
                    player["cell"] = data.get("active_cell")
        except Exception:
            pass
    return resolve(player)


# ---------------------------------------------------------------------------
# Prompt text
# ---------------------------------------------------------------------------

def _place_phrase(info):
    p = info["profile"]
    parts = []
    cell = info.get("cell") or ""
    if cell and not cell.lower().startswith("cell ("):
        parts.append(cell)
    elif info.get("is_exterior"):
        parts.append("the wilderness")
    if info.get("region") and info["region"].lower() not in (info.get("cell") or "").lower():
        parts.append(info["region"])
    parts.append(p["full_name"])
    return ", ".join(parts)


def location_block(info):
    """Markdown block placed at the top of the environment context."""
    p = info["profile"]
    lines = ["### Current Location (authoritative, read from the game world)"]
    lm_label = p["name"][0].upper() + p["name"][1:]
    if info["landmass"] == "vvardenfell":
        lines.append(f"- **Landmass**: {lm_label} (province of Morrowind)")
    elif info["landmass"] == "unknown":
        lines.append("- **Landmass**: Undetermined. Do NOT assume Vvardenfell; judge from the cell name and surroundings.")
    else:
        lines.append(f"- **Landmass**: {lm_label}: {p['full_name']}. This is NOT Vvardenfell.")
    place = []
    if info.get("cell"):
        place.append(f"**Cell**: {info['cell']} ({'outdoors' if info.get('is_exterior') else 'indoors'})")
    if info.get("region"):
        note = REGION_NOTES.get(info.get("region_id", ""), "")
        place.append(f"**Region**: {info['region']}" + (f" ({note})" if note else ""))
    if place:
        lines.append("- " + " | ".join(place))
    if info.get("weather"):
        lines.append(f"- **Current Weather**: {info['weather']}")
    elif not info.get("is_exterior"):
        lines.append("- **Current Weather**: Indoors; describe outside weather only in general terms.")
    if info["landmass"] != "unknown":
        lines.append(f"- **About this land**: {p['summary']}")
        lines.append(f"- **Climate**: {p['climate']}")
        lines.append(f"- **Local powers**: {p['powers']}")
        lines.append(f"- **Faith**: {p['religion']}")
        lines.append(f"- **Wildlife**: {p['fauna']}")
    if p.get("not_here"):
        lines.append(
            "- **Not part of local life here**: " + "; ".join(p["not_here"]) +
            ". These belong to Vvardenfell" + (f", which lies {p['vvardenfell_lies']}" if p.get("vvardenfell_lies") else "") +
            ", and may only come up as distant news or travellers' tales."
        )
    return "\n".join(lines)


def directive_lines(info, for_narrator=False):
    """High-priority rules placed near the top of system prompts."""
    p = info["profile"]
    lm = info["landmass"]
    who = "the scene you narrate takes place" if for_narrator else "you are"
    out = ["### CURRENT LOCATION (overrides any conflicting setting instruction below)"]
    if lm == "vvardenfell":
        out.append(f"- Right now {who} in {_place_phrase(info)}.")
        if info.get("weather"):
            out.append(f"- The current weather is {info['weather']}. Only mention ash storms, Blight storms or choking ash if the weather really is an Ashstorm or Blight; otherwise describe the weather as it is.")
        return out
    if lm == "unknown":
        out.append(f"- Right now {who} in {info.get('cell') or 'an unidentified place'}. Do NOT assume this is Vvardenfell; take the setting from the cell name and the people present.")
        out.append("- Do not mention ash storms, the Blight or Red Mountain as local unless the surroundings clearly indicate Vvardenfell.")
        return out
    out.append(f"- Right now {who} in {_place_phrase(info)}. This is NOT Vvardenfell, and any instruction that assumes Vvardenfell must be read as applying to {p['name']} instead.")
    if info.get("weather"):
        out.append(f"- The current weather is {info['weather']}. The usual climate here: {p['climate']}.")
    else:
        out.append(f"- The usual climate here: {p['climate']}.")
    if p.get("not_here"):
        where = f", which lies {p['vvardenfell_lies']}" if p.get("vvardenfell_lies") else ""
        out.append(
            "- Never describe these as part of local life here: " + "; ".join(p["not_here"]) +
            f". At most they are distant news from Vvardenfell{where}."
        )
    if not for_narrator:
        out.append(f"- Speak as someone living in {p['name']}: the local powers are {p['powers']}; the faiths are {p['religion']}; people drink {p['drink']}.")
        if p.get("foreigners"):
            out.append(f"- {p['foreigners']} If your race is not native to this land, you are an immigrant or traveller here and know it.")
    return out


def _swaps_for(info):
    lm = info["landmass"]
    if lm == "vvardenfell":
        return []
    if lm == "morrowind_mainland":
        return PHRASE_SWAPS_MAINLAND
    return PHRASE_SWAPS_FOREIGN


def adapt_text(text, info):
    """Rewrite Vvardenfell-specific phrasing in instruction text for the current landmass."""
    if not isinstance(text, str) or not text:
        return text
    swaps = _swaps_for(info)
    if not swaps:
        return text
    p = info["profile"]
    for old, new in swaps:
        text = text.replace(old, new.format(name=p["name"], drink=p["drink"]))
    return text


def adapt_rules(rules, info):
    """Adapt a list of '- LABEL: ...' constraint lines for the current landmass."""
    if not rules:
        return rules
    if info["landmass"] == "vvardenfell":
        if info.get("weather"):
            fixed = []
            for r in rules:
                if isinstance(r, str) and "THE ASH AND THE SKY" in r:
                    r = r.rstrip() + f" The weather right now is {info['weather']}; only complain about ash storms during an actual Ashstorm or Blight."
                fixed.append(r)
            return fixed
        return list(rules)
    p = info["profile"]
    w = info.get("weather") or ""
    out = []
    for r in rules:
        if not isinstance(r, str):
            out.append(r)
            continue
        label = r.lstrip("- ").split(":", 1)[0].strip().upper()
        rewrite = None
        for key, fn in RULE_REWRITES.items():
            if label.startswith(key):
                rewrite = fn
                break
        if rewrite and info["landmass"] != "unknown":
            out.append(rewrite(p, w))
        elif rewrite:
            continue
        else:
            out.append(adapt_text(r, info))
    return out


def lore_for(info, lore_cfg):
    """General lore paragraph for the current landmass.

    custom_lore.json may contain a "landmass_lore" object keyed by landmass id
    (vvardenfell, solstheim, morrowind_mainland, skyrim, cyrodiil) to override
    the built-in text for that land.
    """
    lore_cfg = lore_cfg or {}
    lm = info["landmass"]
    overrides = lore_cfg.get("landmass_lore") or {}
    if lm == "vvardenfell":
        return overrides.get(lm) or lore_cfg.get("general_lore", "")
    if lm == "unknown":
        return lore_cfg.get("general_lore", "") + "\n(Note: the player's landmass is uncertain; the lore above describes Vvardenfell only.)"
    p = info["profile"]
    text = overrides.get(lm) or p["summary"]
    return (
        f"{text}\n"
        f"(The player is in {p['name']}, not Vvardenfell. Vvardenfell lore applies only to that island"
        + (f", which lies {p['vvardenfell_lies']}" if p.get("vvardenfell_lies") else "")
        + ".)"
    )


def personality_line(info):
    """Line added to the stats used when a new NPC personality is generated."""
    p = info["profile"]
    if info["landmass"] == "unknown":
        return f"Home: {info.get('cell') or 'unknown'}"
    return f"Home: lives and works in {_place_phrase(info)}. Their goals, worries and speech should fit {p['name']}."
