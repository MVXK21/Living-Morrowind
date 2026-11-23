import addon_manager
import landmass
import paths
import hashlib
import json
import os
import re

# --- INDIVIDUALITY TABLES ---
ARCHETYPES = [
    {"name": "Helpful Scholar", "desc": "Enthusiastic about local history, magic, and culture. Speaks politely and enjoys explaining lore facts."},
    {"name": "Humble Craftsperson", "desc": "Proud of their manual trade (smithing, farming, tailoring). Grounded, practical, polite, and talks about daily labor details."},
    {"name": "Greedy Capitalist", "desc": "Obsessed with drakes, business, and assets. Evaluates trade opportunities. Calculating but professional and polite."},
    {"name": "Earnest Adventurer", "desc": "Optimistic and curious. Eager to hear about player travels, shares cave rumors, and dreams of quest achievements."},
    {"name": "Devout Pilgrim", "desc": "Deeply spiritual and gentle. Focuses on charity, ancestral blessings, and helping others. Peaceful, polite tone."},
    {"name": "Stoic Philosopher", "desc": "Views the world with calm detachment. Speaks in metaphors or moral lessons. Wise, slow, and solemn tone."},
    {"name": "Jovial Gossip", "desc": "Extremely friendly, loves a good drink, and shares stories readily. Warm, hospitable, and laughs easily."},
    {"name": "Quiet Observer", "desc": "Calm, polite, and speaks only when necessary. Provides useful, objective information without taking sides."}
]

POLITICAL_BIASES = [
    "Pro-Empire: Welcomes the Imperial Legion, trade guilds, and foreign colonization. Thinks Morrowind needs modernization.",
    "Anti-Empire: Loathes the Imperial occupation. Thinks foreign tax collectors and Legion forts are parasitic.",
    "Tribal Sympathizer: Respects the Ashlander nomads and traditional ancestor worship. Despises Great House politics.",
    "House Traditionalist: Fiercely loyal to Great House traditions (Redoran honor, Hlaalu deals, or Telvanni magic supremacy). Scorns outlander guilds."
]

SECRET_AGENDAS = [
    "Deeply in debt to the Camonna Tong and terrified of their enforcers.",
    "Secretly hoarding stolen drakes or illegal ebony under their floorboards.",
    "Obsessed with learning alchemy to brew a perfect potion of youth.",
    "Terrified of dark caves, tombs, and the walking dead.",
    "Secretly supports the Twin Lamps abolitionists and hates slave-trading.",
    "Is looking for a way to get promoted or secure a cozy job in a larger city.",
    "Spends all their spare coins on premium Cyrodiilic Brandy at the local tavern.",
    "Believes they are chosen by the ancestors for a great (but unspecified) destiny."
]

# --- LOCALIZED RUMORS ---
CELL_RUMORS = {
    "seyda neen": [
        "Fargoth is looking for his missing ring. Some say the Seyda Neen guards took it, or he hid it near the lighthouse.",
        "Processus Vitellius, the Census and Excise tax collector, went missing recently. The locals are whispering about murder.",
        "Hrisskar Flat-Foot at the Arrille's Tradehouse is looking for someone to help him retrieve some hidden drakes."
    ],
    "balmora": [
        "Caius Cosades lives in a small house near the eastern wall, but some say he's just an old sugar-tooth addict.",
        "The South Wall Cornerclub is the local hub for the Thieves Guild, and the Camonna Tong at the Council Club are looking for a fight.",
        "Larrius Varro at Fort Moonmoth is looking for a brave outlander to clean up some bad people in Balmora."
    ],
    "vivec": [
        "The Ministry of Truth floats silently over the Temple Canton. The Ordinators watch everyone from beneath their golden masks.",
        "They say there are monsters or smugglers hiding in the canals under the Foreign Quarter and Arena cantons.",
        "Lord Vivec himself resides in his palace at the southern end of the city, but only the worthy may speak with him."
    ],
    "sadrith mora": [
        "The Gateway Inn has been haunted by some strange conjured spirit, and the innkeeper is desperate for a spellwright to clean it up.",
        "Wolverine Hall is the Imperial stronghold here, but the Telvanni wizards look down on the Legion garrison.",
        "Master Neloth lives in the tower of Tel Naga, and his temper is as short as his spells are long."
    ],
    "ald'ruhn": [
        "The Great House Redoran Council meets inside Under-Skar, a hollowed-out shell of a giant ancient Emperor Crab.",
        "The ashstorms blow hard against the city walls here, and the local temple is worried about Blight creatures attacking travelers.",
        "The Morag Tong guildhall is hidden somewhere in the underbelly of Ald'ruhn, executing legal honorable executions."
    ]
}

def get_npc_traits(npc_id):
    hash_obj = hashlib.md5(npc_id.encode('utf-8'))
    hash_val = int(hash_obj.hexdigest(), 16)
    
    archetype = ARCHETYPES[hash_val % len(ARCHETYPES)]
    bias = POLITICAL_BIASES[(hash_val // 10) % len(POLITICAL_BIASES)]
    agenda = SECRET_AGENDAS[(hash_val // 100) % len(SECRET_AGENDAS)]
    
    return archetype, bias, agenda

# --- PROMPT MODIFIER HOOK ---
@addon_manager.register_prompt_modifier
def inject_morrowind_immersion_directives(world_id, npc_id, npc_name, prompt, sys_prompt_lines):
    if npc_id == "Narrator":
        return

    # Load environment context
    env_path = os.path.join(paths.WORLDS_DIR, world_id, "environment.json")
    if not os.path.exists(env_path):
        env_path = f"Data Files/MWSE/config/{world_id}/environment.json"
    cell_name = ""
    player_bounty = 0
    location = None
    equipped_items = []
    combat_stance = None
    
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                env_data = json.load(f)
                player_data = env_data.get("player", {})
                cell_name = env_data.get("active_cell") or player_data.get("cell") or ""
                location = landmass.resolve(dict(player_data, cell=player_data.get("cell") or cell_name))
                player_bounty = player_data.get("bounty", 0)
                equipped_items = player_data.get("equipped_gear", [])
                combat_stance = player_data.get("combat_stance")
        except Exception:
            pass

    # 2. Lore Alignment Guard
    sys_prompt_lines.append("### LORE COMPLIANCE FILTER")
    if location and location["landmass"] not in ("vvardenfell", "unknown"):
        land = location["profile"]["name"]
        sys_prompt_lines.append(f"- Speak strictly in Third Era terms as a person living in {land}. Do NOT invent modern technology, pop culture, real-world religions, or out-of-universe lore.")
    else:
        sys_prompt_lines.append("- Speak strictly in Third Era Vvardenfell terms. Do NOT invent modern technology, pop culture, real-world religions, or out-of-universe lore.")
    sys_prompt_lines.append("- Never claim major world-changing events have happened (e.g., you cannot say Vivec is dead, the Empire fell, or Red Mountain erupted).")
    
    # 3. Social/Psychological Quality Directives
    sys_prompt_lines.append("### SIMULATION FIDELITY RULES")
    sys_prompt_lines.append("- Social Hierarchy: Factor in class status differences (slave, commoner, merchant, noble) and adjust your speech tone.")
    sys_prompt_lines.append("- Environment: React to ambient sounds (forges, rain) or lighting (torches, dark shadows) in the cell if appropriate.")
    sys_prompt_lines.append("- Dialogue Conciseness: Keep responses short, clear, and spoken. Never describe your physical movements or actions in brackets.")
    
    # 4. Individuality Profile is handled by the core persistent personality system
    pass
    
    # 5. Local Cell Rumors
    found_rumors = []
    cell_lower = cell_name.lower()
    town = cell_lower.split(",")[0].strip()
    on_vvardenfell = (location is None) or location["landmass"] == "vvardenfell"
    for key, rumors in CELL_RUMORS.items():
        if on_vvardenfell and (town == key or town.startswith(key + " ")):
            found_rumors.extend(rumors)
    if found_rumors:
        sys_prompt_lines.append("### Local Cell Gossip")
        for rumor in found_rumors:
            sys_prompt_lines.append(f"- {rumor}")
            
    # 6. Physical Equipment & Crime Reactions
    if player_bounty > 0:
        sys_prompt_lines.append(f"### Crime Alert: Player has a bounty of {player_bounty} septims! Speak with suspicion or refuse service if law-abiding.")
    
    has_elite_gear = False
    has_drawn_weapon = combat_stance == "weapon_drawn"
    for item in equipped_items:
        item_str = ""
        if isinstance(item, dict):
            item_str = item.get("name", "") or item.get("id", "")
        else:
            item_str = str(item)
            
        name_lower = item_str.lower()
        if any(e in name_lower for e in ["daedric", "ebony", "glass"]):
            has_elite_gear = True
            
    if has_elite_gear or has_drawn_weapon:
        sys_prompt_lines.append("### Physical Observations")
        if has_elite_gear:
            sys_prompt_lines.append("- Player wears elite equipment (Daedric/Ebony/Glass). Show respect, awe, or envy.")
        if has_drawn_weapon:
            sys_prompt_lines.append("- Player has a weapon drawn. Guards and citizens should react warily or ask them to sheathe it.")
            
    sys_prompt_lines.append("")

QUEST_ITEM_BLACKLIST = {
    # Main Quest Critical
    "bk_a1_1_caiuspackage", "bk_a1_1_directionscaiuscosades", "dwemer_puzzle_box",
    "misc_dwrv_ark_cube00", "skull_llevule", "bk_sharn_necromancynotes",
    "bk_huleeyanotes", "bk_mehraamunotes", "bk_hassournotes", "corprus weepings_unique",
    "misc_6th_ash_statue_01", "wraithguard", "misc_wraithguard_no_equip",
    "wraithguard_jury_rig", "keening", "sunder", "moon_and_star", "shadow_shield",
    "teeth_of_the_urshilaku", "madstone", "robe_hortator", "ring_hortator",
    "belt_hortator", "amulet_hortator",

    # Key Early & Side Quest Documents/Keys
    "bk_processus_tax", "note to hrisskar", "chargen captain's door",
    "chargen door key", "key_chargen_doors", "key_chargen_cabinet",
    "chargendoorjournal",

    # Major Artifacts & Sacred Relics
    "artifact_azura_star", "artifact_bittercup", "claymore_chrysamere",
    "katana_goldbrand_unique", "volendrung", "longsword_umbra_unique",
    "boots_apostle_unique", "boots_blind_unique", "boots_speed_unique",
    "cuirass_savior_unique", "ebon_plate_cuirass_unique", "cuirass_dragonbone_unique",
    "helm_oreyn_bearclaw_unique", "helm_clavicusvile", "shield_auriel",
    "shield_eleidon_unique", "shield_spellbreaker", "staff_magnus_unique",
    "staff_hasedoki_unique", "mace_molag_bal_unique", "mace_slurring_unique",
    "dagger_fang_unique", "bow_of_shadows", "ring_khajiit_unique",
    "ring_mentor_unique", "ring_wind_unique", "ring_vampiric_unique",
    "ring_phynaster_unique", "ring_warlock_unique", "ring_suran_unique",
    "ring_denstagmer_unique", "ring_marara", "ring_sheogorath",

    # Propylon Indices
    "index_valenvaryon", "index_falasmaryon", "index_tel_asur", "index_marandus",
    "index_indoranyon", "index_berandas", "index_telasero", "index_hhlormaren",
    "index_andalen", "index_rotheran",

    # Tribunal & Bloodmoon Critical
    "blade_nornal", "pyroil_tar", "karstaag_fang", "totem_claw"
}

def is_protected_quest_item(item_id):
    if not item_id:
        return False
    item_lower = item_id.lower().strip()
    if item_lower in QUEST_ITEM_BLACKLIST:
        return True
    # Pattern-based protections for Morrowind quest prefixes
    if item_lower.startswith("bk_a1_") or item_lower.startswith("bk_a2_"):
        return True
    if item_lower.startswith("index_") or item_lower.startswith("key_chargen"):
        return True
    return False

@addon_manager.register_tag_processor
def process_give_item_tag(world_id, reply_text, npc_name):
    offered_items = []
    matches = re.findall(r'\[GIVE_ITEM:\s*([\w_]+)(?:,\s*(\d+))?\]', reply_text, re.IGNORECASE)
    if matches:
        for item_id, count_str in matches:
            if is_protected_quest_item(item_id):
                print(f"[AI CORE SECURITY] Blocked attempt by {npc_name} to give protected quest item/artifact: {item_id}")
                continue
            count = int(count_str) if count_str else 1
            offered_items.append({"id": item_id.lower(), "count": count})
        reply_text = re.sub(r'\[\s*GIVE_ITEM\s*:\s*[^\]]+\]', '', reply_text, flags=re.IGNORECASE).strip()
    return reply_text, [], offered_items

@addon_manager.register_tag_processor
def process_request_item_tag(world_id, reply_text, npc_name):
    requested_items = []
    matches = re.findall(r'\[REQUEST_ITEM:\s*([\w_]+)(?:,\s*(\d+))?\]', reply_text, re.IGNORECASE)
    if matches:
        for item_id, count_str in matches:
            if is_protected_quest_item(item_id):
                print(f"[AI CORE SECURITY] Blocked attempt by {npc_name} to request protected quest item/artifact: {item_id}")
                continue
            count = int(count_str) if count_str else 1
            requested_items.append({"id": item_id.lower(), "count": count})
        reply_text = re.sub(r'\[\s*REQUEST_ITEM\s*:\s*[^\]]+\]', '', reply_text, flags=re.IGNORECASE).strip()
    return reply_text, [], requested_items

