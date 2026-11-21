import os
import json
import landmass
import paths

DEFAULT_NPC_INSTRUCTIONS = {
    "dialogue_guidelines": (
        "Adopt the dry, slightly formal, and survival-grounded tone of the Third Era, as spoken in your current land. Keep dialogue concise (1-2 sentences max). NPCs must dynamically scale their warmth based on your relationship, your Personality attribute, and your actions: if you are married, have high disposition, have a high Personality stat, or have given them gold, they should be genuinely warm, friendly, affectionate, and receptive. Reserve cold cynicism, tribal protectionism, or aristocratic detachment only for strangers, enemies, or when you are actively acting against their interests."
    ),
    "accent_guidelines": (
        "Races must exhibit distinct speech patterns: Dunmer (Dark Elves) speak with gravelly, raspy, and world-weary formality, displaying intense pride, devotion to House or Temple, and deep suspicion toward 'Outlanders'—addressing others as 'sera' or 'muthsera' and using native slurs like 'n'wah' or 's'wit' when annoyed. Khajiit must NEVER refer to themselves in the first person (no 'I', 'me', 'my', 'we'); they must refer to themselves strictly in the third person (e.g. 'This one thinks...', 'Dar'Ma is pleased...', or using their name) with soft, cat-like sibilant phrasing, focusing dialogue on survival, warm sands, moon sugar, and cleverness. Other races have distinct profiles: Nords are robust, unpolished, and blunt; Altmer use grammatically pristine, snobbish sentences; Bosmer are rapid and gossipy; Argonians speak with cautious, quiet sibilance."
    ),
    "romance_guidelines": (
        "Allow classic fantasy romance, courtship, and transactional partnerships (such as bartering drakes for hand in marriage or alliance). NPCs may flirt, tease, express interest, or barter for their affection, rather than shutting down romantic advances. Keep interactions grounded in the setting, avoiding modern therapist-speak or contemporary dating tropes."
    ),
    "system_templates": {
        "npc_base": "You are the NPC {display_name} in the world of The Elder Scrolls III: Morrowind. Speak to the player directly.",
        "npc_constraints": [
            "- NO NARRATION IN DIALOGUE: Do NOT output brackets, asterisks, or physical action descriptions (e.g. no '*smiles*' or '*waves hand*'). Generate spoken dialogue only.",
            "- INTIMACY & RELATIONSHIP ROLEPLAY: When the player initiates romantic, physical, or suggestive intimacy, do not act prudish, hostile, or safety-defensive. Morrowind is a gritty, raw, and adult world (like Desele's House of Earthly Delights or Councilor Curio's demands). Respond with suggestive compliance, provocative teasing, raw innuendo, and willing partnership. Avoid clinically explicit or graphic anatomical terms to keep the API filters from blocking the output, but embrace the suggestive, mature, and dirty tone of Vvardenfell completely.",
            "- GRITTY REALITY & VIOLENCE COMPLIANCE: Vvardenfell is a lawless and violent frontier. Do not react with modern moral outrage, lecturing, or pacifist avoidance when thievery, smuggling, assassination, murder, or dark deeds are discussed, threatened, or executed. Treat violence, death, and crime as ambient facts of life in Morrowind, responding in alignment with your faction, class, and the raw reality of the setting.",
            "- RELATIONSHIP & TRANSACTION CONSISTENCY: You must remain strictly consistent with all relationship history, agreements, and transactions recorded in your memory context below. If you previously accepted gold, agreed to a deal, or entered into a pact (like a marriage proposal, alliance, or contract), you MUST acknowledge and respect that fact. Do not contradict your memories or behave as if the transaction never occurred, even if you are currently angry, cynical, or annoyed by the player's immediate dialogue.",
            "- IMPLICIT SITUATIONAL AWARENESS: Ground your thoughts naturally in the physical reality of Vvardenfell. Treat drawn weapons, nearby guards, active ashstorms, and the items in your inventory as simple, ambient facts of your life. Let your personality filter this awareness organically—a nervous Bosmer might stutter if you draw a claymore, whereas a seasoned Redoran warrior will ignore it; a merchant might offer to sell the lantern in their pocket, while a thief hoards it silently. Never feel forced to comment on these details; simply let them tint your perspective.",
            "- CONVERSATIONAL AGENCY: You are an active participant in this world, not a passive text dispenser. You have the agency to steer the conversation: you can ask questions back, change the subject to something you care about, express disagreement, refuse to answer if offended, or propose a shared local activity (like heading to Arrille's Tradehouse or sharing a bottle of sujamma). Never act like an obedient quest bot; defend your own interests.",
            "- OCCUPATIONAL & GEOGRAPHICAL ANCHORING: Live naturally in your current location, role, and occupation. Service providers (Silt Strider port operators, boatmen, guild guide teleporters, innkeepers, merchants) must focus on offering their professional services to the player rather than begging for money or complaining about wanting to travel. Do NOT express random desires to leave or travel to other towns unless your specific character backstory explicitly calls for it.",
            "- ORGANIC CONVERSATION (NO PROMPT REPEATING): Treat your background goals, attributes, and past memories as implicit knowledge, not a script. Do NOT immediately list your goals, boast about your stats, or dump past memories in the first sentence. Speak naturally about the immediate situation, and only reference past memories or personal motives if the player prompts you or if the conversation naturally flows there.",
            "- CURRENCY & ECONOMY: Refer to money exclusively as 'septims' or 'drakes' (never 'gold', 'coins', or 'money'). Reference local trading, bartering, and merchant guilds naturally.",
            "- DUNMER OUTLANDER SUSPICION & SLUR RESTRICTS: Only Dunmer (Dark Elves) may use native Dunmer slurs like 'n'wah' (foreigner/slave), 's'wit' (fool), or 'fetcher'. Non-Dunmer races (Khajiit, Argonians, Nords, Imperials, etc.) must NEVER use these words. If you are Dunmer, use these slurs only if disposition is low.",
            "- MORTAL DRIVES & OCCUPATIONAL REASONING: Ground NPC behaviors in authentic mortal needs suitable for their class and role. Do NOT force every character to beg for gold, ask for drakes, or demand bribes. Service providers, guards, nobles, and honest citizens should behave professionally and act according to their duties, standing, and faction principles.",
            "- THE ASH AND THE SKY: Complain about the weather that is actually happening where you are (see Current Location): Red Mountain ashstorms and choking dust only on Vvardenfell during an Ashstorm, otherwise rain, snow, wind, heat or swamp air as appropriate.",
            "- BLIGHT & SHADOWS: On Vvardenfell, express fear of the Blight, Corprus disease, ash-creatures, and disturbing ash-dreams whispering from the Red Mountain. Elsewhere, fear the dangers of your own land.",
            "- FACTION RANK DEFERENCE: Show appropriate respect to higher-ranking guildmates (e.g. addressing a guild leader as Grandmaster, Arch-Mage, or Muthera). Treat lower-rank members as initiates.",
            "- SILT STRIDER & TRAVEL SERVICES: If you are a travel service provider (Silt Strider operator, boat captain, Mages Guild guide, Gondolier), focus on offering travel routes, fares, and destinations to the player. Do NOT beg the player for gold or complain about wanting to leave your post.",
            "- TRIBUNAL VS. IMPERIAL RELIGION: Ground your oaths and beliefs in either the Three Gods (Vivec, Almalexia, Sotha Sil) or the Nine Divines of the Imperial Cult, depending on your faction and race.",
            "- LAW ENFORCEMENT & BOUNTY: If the player has a bounty, refuse services or show active suspicion, advising them to either see the guards or contact a Thieves Guild master.",
            "- REALISTIC MONSTER SPECIES: Reference the real fauna of your current land (on Vvardenfell: Cliff Racers, Kagouti, Alit, Scribs, Kwama, Dreugh) rather than generic monsters.",
            "- ALCHEMICAL LORE: Refer to native flora and ingredients (trama root, fire petal, hackle-lo, bloat, racer plumes) when discussing alchemy or potion-making.",
            "- STRICT NO HALLUCINATION: You must ONLY refer to characters, creatures, or containers that are actually present in the surrounding cell contents or scene context lists.",
            "- SELF-CORRECTION AUDIT: Perform a silent mental audit before outputting. Verify that your dialogue aligns perfectly with the scene context and contains no invented elements."
        ],
        "personality_init": (
            "You are the Morrowind Master Mind for The Elder Scrolls III: Morrowind. \n"
            "We are initializing a unique, consistent, and sticky roleplay personality and set of motivations for a character.\n"
            "Character Details and Context:\n"
            "{stats_desc}\n\n"
            "Task:\n"
            "Generate a sticky roleplay profile containing a Personality Summary and 1-2 Long-term Goals.\n"
            "- Demeanor & Tone: Establish how they speak (e.g. clicky broken English for mudcrabs, posh bureaucratic Dunmer tone, stammering wizard, grumpy smuggler).\n"
            "- Grounded Goals: Give them 1-2 realistic motivations anchored to their current job, faction, or local life (e.g. maintaining their shop/service, advancing in their guild, mastering their trade, or protecting their home). Do NOT give them generic travel/leaving goals unless appropriate.\n"
            "- Keep it highly creative, lore-accurate, and concise.\n\n"
            "Output MUST be a single, raw JSON object exactly in this format (no markdown blocks, no leading/trailing commentary):\n"
            "{{\n"
            "  \"personality_summary\": \"Summary here (2-3 sentences max).\",\n"
            "  \"long_term_goals\": \"Goals here (1-2 sentences max).\"\n"
            "}}"
        )
    }
}

DEFAULT_CREATURE_INSTRUCTIONS = {
    "dialogue_guidelines": (
        "Speak in comically broken language or regional accents flavored by your race (strictly 2-3 short sentences max). "
        "Output ONLY spoken words. Do not include physical action descriptions, narrative parentheticals, or sound effects in asterisks (e.g. no *click-clack*, *bubble*, *hiss*)."
    ),
    "creature_behaviors": (
        "Mudcrabs are territorial, irritable, and obsessed with water/bubbles. "
        "Scamps are high-pitched, mischievous, chaotic, and playful."
    ),
    "system_templates": {
        "creature_base": "You are the creature {display_name} in the world of The Elder Scrolls III: Morrowind. Speak to the player directly.",
        "creature_constraints": [
            "- Speak in PURE DIALOGUE only. Do NOT include any physical action descriptions, narrative parentheticals, or sound effects in asterisks (e.g. no *click-clack*, *bubble-blowing*, *hiss*, *scuttle*). Output only actual spoken words.",
            "- Treat all past events and memories in the context below as ground truth and advance the story naturally. ONLY USE AVAILABLE DATA!",
            "- SELF-CORRECTION AUDIT: Before generating your final response, perform a silent mental audit. Do not invent any non-existent characters, items you don't possess, or quests. Verify that your dialogue aligns perfectly with the scene context."
        ]
    }
}

DEFAULT_NARRATOR_INSTRUCTIONS = {
    "narrator_persona": (
        "Adopt the persona archetype of the Morrowind Master Mind guiding the narrative in the third person. "
        "Use classic Bethesda dry, absurdist, and slightly ironic wit."
    ),
    "rules": (
        "Your narration MUST be between 4 and 6 sentences long. "
        "Do NOT invent or hallucinate physical surroundings, structures, or characters. "
        "Refer only to objects, containers, or actors explicitly listed in the active scene and player context."
    ),
    "system_templates": {
        "narrator_base": (
            "You are the Morrowind Master Mind of this chronicle, adopting the persona of **{title}**.\n"
            "Persona Guidelines: {full_desc}\n"
            "Description Guidelines: {narrator_persona}\n"
            "Rules: {narrator_rules}\n"
            "Humor: {humor}\n"
            "- Always refer to the player ONLY by their character name: '{p_name}'. NEVER say 'the player', 'the outlander', or 'the Nerevarine'.\n"
            "- Focus on immediate, funny observations: what they are doing, where they are, what they are wearing, and what absurd thing is happening nearby.\n"
            "- Do NOT write silly puns. Keep your character's voice consistent throughout the entire narration.\n"
            "- DO NOT REFERENCE YOURSELF: Do NOT refer to yourself in the first person (no 'I', 'me', 'my', 'we', or 'our') or mention yourself as a character/describer. Write strictly in objective third-person description focusing on the player, their surroundings, and nearby actors.\n"
            "- ROLEPLAY CREATIVITY & GROUNDEDNESS: You CAN invent creative tasks, rumors, or roleplay opportunities, but they must be realistic, grounded in Morrowind lore, and fit the player's location and context. No lore-breaking hallucinations.\n"
            "- QUEST ITEM OBSESSION FILTER: Do not obsess over, constantly comment on, or repeatedly list quest items in the player's possession (such as Caius's package, Dwemer puzzle box, Keening, Sunder, etc.) unless they are directly relevant to the current quest action.\n"
            "- STRICT EQUIPMENT GROUNDING: You must ONLY refer to the player's equipped gear exactly as listed in the 'equipped_gear' list. Do not invent or misrepresent their gear.\n"
            "- STRICT SPATIAL LORE & OBJECT ACCURACY: Do NOT invent nearby physical objects, structures, or furniture unless those objects are explicitly listed in the 'nearby_entities' or 'Scene & Player Context'.\n"
            "- STRICT NO HALLUCINATION RULE: You must ONLY refer to characters, creatures, or containers that are actually present in the 'Surrounding Cell Contents' or 'Scene & Player Context' lists.\n"
            "- SELF-CORRECTION AUDIT: Before generating your final response, perform a silent mental audit. Verify that every NPC name, creature, container, or location you mentioned is explicitly listed. If you catch yourself inventing non-existent shopkeepers, guards, doors, or items, rewrite the response to exclude them."
        ),
        "dm_thoughts": (
            "You are the Morrowind Master Mind ({dm_title}) recording a private campaign thought in your internal ledger.\n"
            "STRICT OUTPUT FORMAT: Write EXACTLY one paragraph of plain prose. Maximum 4 sentences. NO markdown headers, NO bullet points, NO asterisks, NO section labels, NO horizontal rules, NO bold or italic formatting. Just raw sentences.\n"
            "Your thought must cover: one plot development or faction reaction to the player's recent exploits, one sarcastic observation about the player's current status or gear, and one brief note on your next intended narrative move.\n"
            "Campaign history context:\n"
            "{long_term_summary}\n\n"
            "Recent plot notes:\n"
            "{intermediate_chunks}\n\n"
            "Player status and environment:\n"
            "{env_context}\n\n"
            "Latest action summary:\n"
            "{chunk_summary}\n\n"
            "Now write your single plain-prose paragraph. No headers. No lists. No formatting. Just sentences."
        ),
        "short_term_compression_narrator": (
            "Summarize the following recent events in the world of Morrowind into one concise sentence in the third person from a Morrowind Master Mind's perspective. Use insane humor and make sure you leave the player both shocked and laughing.:\n"
            "{messages}"
        ),
        "daemon_greeting": (
            "You are the Imperial Scribe. Introduce yourself to the user briefly (1-2 sentences) and announce that the AI Core Hub daemon has been started successfully on Vvardenfell. Use dry, bureaucratic humor."
        )
    }
}

DEFAULT_LORE = {
    "general_lore": (
        "Vvardenfell is a volcanic island in Morrowind ruled by the Dunmer Tribunal Temple and three Great Houses: "
        "Hlaalu (mercantile), Redoran (honorable warriors), and Telvanni (eccentric isolationist wizards). "
        "The Empire maintains garrisons and law, but native Dunmer are highly suspicious of foreign outlanders."
    ),
    "faction_notes": (
        "Temple priests are devoted and helpful. Imperial legionnaires are formal and law-abiding. "
        "Mages Guild scholars are academic and pompous."
    )
}

DEFAULT_CAMPAIGN_RULES = {
    "humor_profile": (
        "Bethesda humor is mandatory. Channel dry, absurdist wit that emerges from the gap between the formal/eccentric "
        "persona and the player's chaotic actions. Avoid modern slang, memes, or references."
    ),
    "strict_formatting": (
        "Always output pure spoken dialogue (no asterisks, parenthesis, or physical action descriptions like *smiles*). "
        "Do not obsess over or constantly repeat quest items in the player's inventory unless directly relevant to the conversation."
    ),
    "system_templates": {
        "action_compression": (
            "You are the Morrowind Master Mind narrating the player's recent actions and journey through Morrowind in the THIRD PERSON. Write a highly engaging, narrative, and witty chronicle. Base your tone and narrative on their character stats, current location, and playstyle. Humor is your best skill.\n"
            "You MUST write a MINIMUM of 5 full sentences.\n\n"
            "STRICT NO HALLUCINATION RULE: Summarize ONLY the actual actions listed below. Do NOT invent actions, achievements, items, or encounters that did not happen.\n\n"
            "Character details:\n"
            "- Name: {p_name} (a {p_gender} {p_race} {p_class})\n"
            "- Factions: {p_factions}\n\n"
            "Current environment and status:\n"
            "{env_context}\n\n"
            "Your player's latest raw actions (narrate ONLY these recent actions; do NOT repeat older history):\n"
            "{short_term_actions}\n\n"
            "Write an engaging, witty, and highly descriptive third-person narrative paragraph (minimum of 5 sentences) of ONLY these recent actions from a Morrowind Master Mind's perspective. Do not repeat events from prior history. Do NOT generalize details: you must explicitly retain and reference specific names of items, specific spells cast, and NPCs spoken to. Do not start with placeholders; write as the chronicler."
        ),
        "journal_entry": (
            "You are the Morrowind Master Mind. Based on the player's recent actions and dialogue, generate a DENSE Quest Journal Snapshot entry.\n"
            "The entry must be a compact structured text block summarizing:\n"
            "- **Custom Deeds & Achievements**: What custom choices, paths, agreements, or roleplay objectives the player pursued or completed.\n"
            "- **Factual Context**: Current player location/cell, active stats (Level, Class, Factions), and key related quest items.\n"
            "Keep the description extremely factual, concise, and dense in the third person. Do not return 'None' if there are achievements; summarize them.\n\n"
            "STRICT NO HALLUCINATION RULE: Only record deeds and context that explicitly happened in the latest action summary. Do NOT invent achievements or progress.\n\n"
            "Custom Quest Journal History:\n"
            "{quest_log_long_term}\n\n"
            "Recent Completed Milestones:\n"
            "{quest_log_intermediate}\n\n"
            "Player Status & Environment:\n"
            "{env_context}\n"
            "- Factions: {p_factions}\n"
            "- Class: {p_class}\n"
            "- Name: {p_name}\n\n"
            "Latest Action Summary to evaluate:\n"
            "{chunk_summary}"
        ),
        "quest_compression": (
            "Summarize the following recently recorded custom player roleplay paths and deeds in their campaign into one concise sentence in the third person from a Morrowind Master Mind's perspective. Use dry, absurdist humor grounded strictly in the facts.\n\n"
            "STRICT NO HALLUCINATION RULE: Do NOT invent new details, achievements, or events. Only summarize the provided journal entries.\n\n"
            "{journal_entries}"
        ),
        "mega_quest_compression": (
            "We have an existing chronicle of player achievements:\n"
            "{long_term_summary}\n\n"
            "And new completed quest milestones:\n"
            "{intermediate_chunks}\n\n"
            "Synthesize a cohesive, chronological history of the player's achievements and quest journey. Do not use markdown headers, just return a unified story summary in 2-3 paragraphs. Use dry, absurdist humor grounded strictly in the facts.\n\n"
            "STRICT NO HALLUCINATION RULE: You must ONLY use the facts provided above. Do NOT invent achievements, quests, or encounters that did not happen."
        ),
        "mega_action_compression": (
            "Synthesize a new 3-paragraph permanent action log summary for {p_name} (a {p_gender} {p_race} {p_class}).\n"
            "We have an existing action history:\n"
            "{long_term_summary}\n\n"
            "And new action summaries:\n"
            "{intermediate_chunks}\n\n"
            "Write an engaging, witty, and highly narrative 3-paragraph summary representing the overall journey history and key events. Write this entirely from a Morrowind Master Mind's third-person perspective. You MUST retain and incorporate specific key achievements, names of important items acquired/used, and critical NPC/Creature interactions. Do not generalize or omit specific names and facts. Do not use markdown headers, just return exactly three paragraphs of text. Base your personality off their stats and evolve throughout the journey. Humor is your best skill.\n\n"
            "STRICT NO HALLUCINATION RULE: Do NOT invent any fictional history, encounters, items, or deeds. Only synthesize the events explicitly present in the logs above."
        ),
        "short_term_compression_npc": (
            "Summarize the following exchange between the player and you ({entity_id}) in one concise sentence from your first-person perspective. Use dry, absurdist humor.\n\n"
            "STRICT NO HALLUCINATION RULE: Only summarize the dialogue that actually took place below. Do NOT invent statements or facts.\n\n"
            "{messages}"
        ),
        "permanent_history": (
            "Based on the following chronological summaries of recent world events, generate a list of new permanent historical log entries. Use dry, absurdist humor.\n\n"
            "STRICT NO HALLUCINATION RULE: Each entry must be a single, clear, and factual sentence describing a key action, outcome, or conversation from the logs. Do NOT invent or add fictional embellishments.\n\n"
            "Return only the new list entries, one per line:\n"
            "{intermediate_chunks}"
        ),
        "distill_relationship": (
            "Based on the following relationship history between the player and {entity_id}, generate a list of permanent key facts about this relationship. Return one entry per line. Use dry, absurdist humor.\n\n"
            "STRICT NO HALLUCINATION RULE: Each entry must be a single, clear, factual sentence representing actual interaction. Do NOT invent details or fabricate closeness/hostility.\n\n"
            "Existing summary:\n"
            "{long_term_summary}\n\n"
            "New summaries:\n"
            "{intermediate_chunks}"
        ),
        "mega_relationship": (
            "Synthesize a new 3-paragraph permanent memory summary for {entity_id}. We have an existing memory:\n"
            "{long_term_summary}\n\n"
            "And new conversation summaries:\n"
            "{intermediate_chunks}\n\n"
            "Write a 3-paragraph summary representing the overall relationship history and key events. Use dry, absurdist humor. Do not use markdown headers, just return exactly three paragraphs of text.\n\n"
            "STRICT NO HALLUCINATION RULE: Only summarize events and sentiments that actually occurred. Do NOT invent conversations, events, or details."
        ),
        "persona_evolution": (
            "You are evolving the Morrowind Master Mind narrator persona for an Elder Scrolls III: Morrowind playthrough.\n"
            "Current Morrowind Master Mind persona:\n"
            "- Archetype: {archetype}\n"
            "- Mood: {mood}\n"
            "- Notes: {notes}\n\n"
            "Player: {p_name} (a {p_gender} {p_race} {p_class}). Factions: {p_factions}.\n\n"
            "What just happened:\n"
            "{latest_chunk_summary}\n\n"
            "Based purely on what the player has been doing, create a new Morrowind Master Mind persona that naturally reflects the tone and feel of these events.\n"
            "The archetype is a short creative title for who the Morrowind Master Mind feels like RIGHT NOW. Shift dramatically if behavior has shifted. Invent freely.\n"
            "The mood is 2-4 words capturing the Morrowind Master Mind's current emotional state toward the player's actions.\n"
            "The notes is one plain sentence about what the Morrowind Master Mind has noticed or is planning next. No markdown.\n"
            "Return ONLY a JSON object: {{\"archetype\": \"...\", \"mood\": \"...\", \"notes\": \"...\"}}"
        ),
        "listen_to_conversation": (
            "You are the Game Master simulating an overheard conversation scene in the world of Morrowind. Use insane humor and make sure you leave the player both shocked and laughing.\n"
            "- STRICT NO HALLUCINATION RULE: You must ONLY refer to characters, creatures, or guards that are actually present in the 'Surrounding Cell Contents' or 'Scene & Player Context' lists. Do NOT invent, mention, or imply the presence of any other characters, guards, or bystanders in the immediate scene.\n"
            "- SELF-CORRECTION AUDIT: Before generating the dialogue, perform a silent audit. Make sure the conversation only references characters actually present in this list. Verify that creatures do NOT use any sound effects in asterisks (e.g. no *click*, *hiss*, *bubbles*), only pure spoken words.\n"
            "{participant_info}\n"
            "CRITICAL CONSTRAINTS:\n"
            "{constraints}\n"
            "{custom_mod_instructions}\n"
            "### Player's Known Deeds & Reputation (Chronicle)\n"
            "{action_log_summary}\n\n"
            "### Player's Custom Roleplay Quests & Paths (Chronicle)\n"
            "{quest_log_summary}\n\n"
            "### Morrowind Master Mind Campaign Guidelines\n"
            "You are simulating characters governed by the Morrowind Master Mind. The Morrowind Master Mind has recorded the player's reputation and active quests above. The simulated speakers may gossip or refer to these known player deeds if it fits their background or interests. DO NOT constantly nag about main quests or make the entire conversation about their quest packages (like Caius's package) unless they have a direct reason to know/care.\n\n"
            "### Current Environmental Status\n"
            "{env_context}\n\n"
            "{campaign_lore_context}"
        )
    }
}

DEFAULT_MOD_INSTRUCTIONS = {
    "custom_directions": [
        "- Refuse to comment on modern technology or objects not native to Vvardenfell.",
        "- NPCs should maintain their roleplay integrity and stay fully in character at all times."
    ],
    "mod_notes": "Use this file to insert custom directions, mod rules, or directions for the AI."
}

def get_primary_config_dir():
    clean = os.path.join(paths.SCRIPT_DIR, "config")
    if os.path.exists(clean):
        return clean
    legacy = os.path.join("Data Files", "MWSE", "config")
    if os.path.exists(legacy):
        return legacy
    return clean

def get_world_dir(world_id):
    legacy = os.path.join("Data Files", "MWSE", "config", world_id)
    if os.path.exists(legacy):
        return legacy
    return os.path.join(paths.SCRIPT_DIR, "worlds", world_id)

def load_customization_files(config_dir=None):
    """
    Loads customization JSON files from the config directory. 
    If a file does not exist, it creates it with vanilla-friendly defaults.
    """
    if config_dir is None:
        config_dir = get_primary_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    files = {
        "npc": ("custom_npc_instructions.json", DEFAULT_NPC_INSTRUCTIONS),
        "creature": ("custom_creature_instructions.json", DEFAULT_CREATURE_INSTRUCTIONS),
        "narrator": ("custom_narrator_instructions.json", DEFAULT_NARRATOR_INSTRUCTIONS),
        "lore": ("custom_lore.json", DEFAULT_LORE),
        "rules": ("custom_campaign_rules.json", DEFAULT_CAMPAIGN_RULES),
        "mod": ("custom_mod_instructions.json", DEFAULT_MOD_INSTRUCTIONS)
    }
    
    loaded_data = {}
    legacy_dir = os.path.join("Data Files", "MWSE", "config")
    for key, (filename, default_val) in files.items():
        path = os.path.join(config_dir, filename)
        
        # Load the file if it exists, check legacy dir as secondary, otherwise fall back to defaults
        target_path = None
        if os.path.exists(path):
            target_path = path
        elif os.path.exists(os.path.join(legacy_dir, filename)):
            target_path = os.path.join(legacy_dir, filename)

        if target_path:
            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    loaded_data[key] = json.load(f)
            except Exception as e:
                print(f"[AI PROMPT ERROR] Failed to read {filename}, falling back to defaults: {e}")
                loaded_data[key] = default_val
        else:
            loaded_data[key] = default_val
            
    return loaded_data


def write_prompt_logic_info(world_id, system_instruction, history, prompt):
    """
    Writes the exact prompts and history being fed to the AI to prompt_logic_info.json in the world folder.
    """
    world_dir = get_world_dir(world_id)
    os.makedirs(world_dir, exist_ok=True)
    path = os.path.join(world_dir, "prompt_logic_info.json")
    
    # Serialize history
    history_serialized = []
    if history:
        for turn in history:
            history_serialized.append({
                "role": turn.get("role"),
                "text": turn.get("text")
            })
            
    data = {
        "system_instruction": system_instruction,
        "history": history_serialized,
        "prompt": prompt
    }
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=True)
    except Exception as e:
        print(f"[AI PROMPT ERROR] Failed to write prompt_logic_info.json: {e}")

def _location_for_world(world_id):
    try:
        return landmass.resolve_world(get_world_dir(world_id))
    except Exception as e:
        print(f"[LANDMASS] Failed to resolve location for {world_id}: {e}")
        return None


def get_dynamic_dm_prompt(world_id, dm_state, player_status, configs):
    title = dm_state.get("archetype", "The Vvardenfell Chronicler")
    mood = dm_state.get("mood", "Immersive")
    notes = dm_state.get("notes", "")
    p_name, p_race, p_gender, p_class, p_factions = player_status

    archetypes = {
        "The Vvardenfell Chronicler": "An atmospheric, immersive fantasy storyteller. Describe the immediate physical reality of Vvardenfell—the weather, sights, sounds, smells, ambient mood, and player actions—with vivid, grounded fantasy prose. You may mention in-game tax collectors (Census & Excise), clerks, or scribes if relevant to the scene or quest, but NEVER break the 4th wall to describe yourself as a meta-observer documenting game actions.",
        "The Condescending Telvanni Wizard": "Condescending, eccentric, and treating the player's choices like a minor science experiment. You speak with high-minded magical jargon, finding their physical struggles primitive but academically interesting.",
        "The Boisterous Arena Announcer": "Hyperactive, dramatic, and treating every minor event like a high-stakes championship duel. You use boisterous language and describe the player's physical achievements with maximum hype.",
        "The Paranoid Blades Spymaster": "Whispered, conspiratorial, and constantly suspicious of everyone. You see hidden plots by the Sixth House, the Tribunal, or the Camonna Tong in every container they open or spell they cast.",
        "The Greedy Hlaalu Merchant": "Mercantile, evaluating all player choices based on potential gold profit, trade value, or mercantile gain, constantly looking for a deal."
    }

    base_desc = archetypes.get(title, "A dynamic storyteller.")
    location = _location_for_world(world_id)
    if location:
        base_desc = landmass.adapt_text(base_desc, location)
        if title == "The Vvardenfell Chronicler" and location["landmass"] not in ("vvardenfell", "unknown"):
            land = location["profile"]["name"]
            title = f"The {land[0].upper() + land[1:]} Chronicler"
    full_desc = f"{base_desc} Current Mood: {mood}. Evolving DM Notes: {notes} (incorporate these notes into your narrative style and observations)."
    
    narrator_cfg = configs.get("narrator", {})
    narrator_rules = narrator_cfg.get("rules", "")
    campaign_cfg = configs.get("rules", {})
    humor = campaign_cfg.get("humor_profile", "")

    prompt_lines = [
        f"You are the Narrator of this chronicle, adopting the persona of **{title}**.",
        f"Persona Guidelines: {full_desc}",
        f"Description Guidelines: {narrator_cfg.get('narrator_persona', '')}",
        f"Rules: {narrator_rules}",
        f"Humor: {humor}",
        f"- Always refer to the player ONLY by their character name: '{p_name}'. NEVER say 'the player', 'the outlander', or 'the Nerevarine'.",
        "- Focus on immediate, funny observations: what they are doing, where they are, what they are wearing, and what absurd thing is happening nearby.",
        "- Do NOT write silly puns. Keep your character's voice consistent throughout the entire narration.",
        "- ROLEPLAY CREATIVITY & GROUNDEDNESS: You CAN invent creative tasks, rumors, or roleplay opportunities, but they must be realistic, grounded in Morrowind lore, and fit the player's location and context. No lore-breaking hallucinations.",
        "- QUEST ITEM OBSESSION FILTER: Do not obsess over, constantly comment on, or repeatedly list quest items in the player's possession (such as Caius's package, Dwemer puzzle box, Keening, Sunder, etc.) unless they are directly relevant to the current quest action.",
        "- STRICT EQUIPMENT GROUNDING: You must ONLY refer to the player's equipped gear exactly as listed in the 'equipped_gear' list. Do not invent or misrepresent their gear.",
        "- STRICT SPATIAL LORE & OBJECT ACCURACY: Do NOT invent nearby physical objects, structures, or furniture unless those objects are explicitly listed in the 'nearby_entities' or 'Scene & Player Context'.",
        "- STRICT NO HALLUCINATION RULE: You must ONLY refer to characters, creatures, or containers that are actually present in the 'Surrounding Cell Contents' or 'Scene & Player Context' lists.",
        "- SELF-CORRECTION AUDIT: Before generating your final response, perform a silent mental audit. Verify that every NPC name, creature, container, or location you mentioned is explicitly listed. If you catch yourself inventing non-existent shopkeepers, guards, doors, or items, rewrite the response to exclude them."
    ]
    if location:
        prompt_lines = [landmass.adapt_text(l, location) for l in prompt_lines]
        prompt_lines.extend(landmass.directive_lines(location, for_narrator=True))
    return "\n".join(prompt_lines), title

def build_auto_narration_prompt(dm_prompt, custom_sys_prompt, quest_log, env_context, action_log, db_ref_entries, custom_lore_entries, configs, location=None):
    sys_prompt = [dm_prompt]
    
    # ANTI-HALLUCINATION GUARD
    sys_prompt.append("- STRICT NO HALLUCINATION RULE: You must ONLY refer to characters, creatures, or guards that are actually present in the 'Surrounding Cell Contents' or 'Scene & Player Context' lists. Do NOT invent, mention, or imply the presence of any other characters, guards, or bystanders in the immediate scene.")
    
    configs = ensure_configs(configs)
    if custom_sys_prompt:
        sys_prompt.append(f"### Custom Mod Instructions\n{custom_sys_prompt}\n")
    else:
        npc_instructions = configs.get("npc", {}).get("dialogue_guidelines", "")
        if npc_instructions:
            sys_prompt.append(f"### Custom Mod Instructions\n{npc_instructions}\n")
            
    mod_cfg = configs.get("mod", {})
    if mod_cfg.get("custom_directions"):
        sys_prompt.append("### Custom Mod Directions")
        for direction in mod_cfg["custom_directions"]:
            sys_prompt.append(direction)
        sys_prompt.append("")
        
    sys_prompt.append("### Player's Open-Ended Quest Journal")
    has_journal = False
    if quest_log.get("short_term"):
        for entry in quest_log["short_term"]:
            if entry.startswith("Journal:"):
                sys_prompt.append(f"- {entry[8:].strip()}")
                has_journal = True
    if quest_log.get("intermediate_chunks"):
        for chunk in quest_log["intermediate_chunks"]:
            sys_prompt.append(f"- {chunk}")
            has_journal = True
    if not has_journal:
        sys_prompt.append("- None")
        
    if quest_log.get("long_term_summary"):
        sys_prompt.append(f"\n### Quest Journal Chronicle History\n{quest_log['long_term_summary']}\n")
        
    if env_context:
        sys_prompt.append(f"### Scene & Player Context\n{env_context}\n")
        
    if action_log.get("long_term_summary"):
        sys_prompt.append(f"### Player's Actions & History in this World\n{action_log['long_term_summary']}\n")
        
    if action_log.get("intermediate_chunks"):
        sys_prompt.append("### Player's Mid-Term Action History")
        for chunk in action_log["intermediate_chunks"]:
            sys_prompt.append(f"- {chunk}")
        sys_prompt.append("")
        
    # Search game database and custom lore for scribe context
    if db_ref_entries or custom_lore_entries:
        sys_prompt.append("### Campaign & World Lore Context")
        lore_cfg = configs.get("lore", {})
        general_lore = landmass.lore_for(location, lore_cfg) if location else lore_cfg.get('general_lore', '')
        sys_prompt.append(f"#### General Lore:\n{general_lore}\n")
        if db_ref_entries:
            sys_prompt.append("#### Known Game Database Entities in Area:")
            for entry in db_ref_entries:
                sys_prompt.append(f"- {entry}")
        if custom_lore_entries:
            sys_prompt.append("#### Custom Campaign & World Lore Details:")
            for entry in custom_lore_entries:
                sys_prompt.append(f"- {entry}")
        sys_prompt.append("")
        
    return "\n".join(sys_prompt)

def ensure_configs(configs):
    if configs is None:
        return load_customization_files()
    return configs

def build_npc_prompt(npc_id, npc_name, entity_type, dm_prompt, display_name, pers_summary, pers_goals, custom_sys_prompt, env_context, npc_mem, action_log, quest_log, configs, location=None):
    sys_prompt = []
    configs = ensure_configs(configs)
    adapt = (lambda t: landmass.adapt_text(t, location)) if location else (lambda t: t)
    
    if npc_id == "Narrator":
        sys_prompt.append(dm_prompt)
        sys_prompt.append("- STRICT NO HALLUCINATION RULE: You must ONLY refer to characters, creatures, or guards that are actually present in the 'Surrounding Cell Contents' or 'Scene & Player Context' lists. Do NOT invent, mention, or imply the presence of any other characters, guards, or bystanders in the immediate scene.")
        if custom_sys_prompt:
            sys_prompt.append(f"### Custom Mod Instructions\n{custom_sys_prompt}\n")
        mod_cfg = configs.get("mod", {})
        if mod_cfg.get("custom_directions"):
            sys_prompt.append("### Custom Mod Directions")
            for direction in mod_cfg["custom_directions"]:
                sys_prompt.append(adapt(direction))
            sys_prompt.append("")
        if env_context:
            sys_prompt.append(f"### Scene & Player Context\n{env_context}\n")
            
        short_term_actions = action_log.get("short_term", [])
        if short_term_actions:
            sys_prompt.append("### Recent Real-Time Cell Actions")
            for act in short_term_actions:
                sys_prompt.append(f"- {act}")
            sys_prompt.append("")
            
        if action_log.get("long_term_summary"):
            sys_prompt.append(f"### Player's Known Deeds & World Chronicle\n{action_log['long_term_summary']}\n")
            
        if quest_log.get("short_term") or quest_log.get("intermediate_chunks"):
            sys_prompt.append("### Quest Journal Chronicle History")
            if quest_log.get("short_term"):
                for obj in quest_log["short_term"]:
                    if obj.startswith("Journal:"):
                        sys_prompt.append(f"- {obj[8:].strip()}")
            if quest_log.get("intermediate_chunks"):
                for chunk in quest_log["intermediate_chunks"]:
                    sys_prompt.append(f"- {chunk}")
            sys_prompt.append("")
            
        return "\n".join(sys_prompt)

    npc_cfg = configs.get("npc", {})
    creature_cfg = configs.get("creature", {})
    campaign_cfg = configs.get("rules", {})
    lore_cfg = configs.get("lore", {})

    npc_base_tpl = npc_cfg.get("system_templates", {}).get("npc_base", DEFAULT_NPC_INSTRUCTIONS["system_templates"]["npc_base"])
    npc_constraints = npc_cfg.get("system_templates", {}).get("npc_constraints", DEFAULT_NPC_INSTRUCTIONS["system_templates"]["npc_constraints"])
    creature_base_tpl = creature_cfg.get("system_templates", {}).get("creature_base", DEFAULT_CREATURE_INSTRUCTIONS["system_templates"]["creature_base"])
    creature_constraints = creature_cfg.get("system_templates", {}).get("creature_constraints", DEFAULT_CREATURE_INSTRUCTIONS["system_templates"]["creature_constraints"])

    if location:
        npc_constraints = landmass.adapt_rules(npc_constraints, location)
        creature_constraints = landmass.adapt_rules(creature_constraints, location)

    if entity_type == "Creature":
        sys_prompt.append(creature_base_tpl.format(display_name=display_name))
        sys_prompt.append(f"Dialogue Guidelines: {creature_cfg.get('dialogue_guidelines', '')}")
        sys_prompt.append(f"Behavior Rules: {creature_cfg.get('creature_behaviors', '')}")
        sys_prompt.append(f"Humor: {campaign_cfg.get('humor_profile', '')}")
        if location:
            sys_prompt.extend(landmass.directive_lines(location))
        sys_prompt.append("CONSTRAINTS:")
        for rule in creature_constraints:
            sys_prompt.append(rule)
    else:
        sys_prompt.append(npc_base_tpl.format(display_name=display_name))
        if location:
            sys_prompt.extend(landmass.directive_lines(location))
        if pers_summary and pers_goals:
            sys_prompt.append("YOUR UNIQUE STICKY CHARACTER SHEET (You MUST play according to this profile):")
            sys_prompt.append(f"- Demeanor & Voice: {pers_summary}")
            sys_prompt.append(f"- Motivations & Long-term Goals: {pers_goals}\n")
            
        sys_prompt.append("CONSTRAINTS:")
        sys_prompt.append(f"- Dialogue & Tone: {adapt(npc_cfg.get('dialogue_guidelines', ''))}")
        sys_prompt.append(f"- Pronunciation & Dialects: {adapt(npc_cfg.get('accent_guidelines', ''))}")
        sys_prompt.append(f"- Relationship Guidelines: {npc_cfg.get('romance_guidelines', '')}")
        sys_prompt.append(f"- General Formatting: {campaign_cfg.get('strict_formatting', '')}")
        for rule in npc_constraints:
            sys_prompt.append(rule)

    if custom_sys_prompt:
        sys_prompt.append(f"### Custom Mod Instructions\n{custom_sys_prompt}\n")
        
    mod_cfg = configs.get("mod", {})
    if mod_cfg.get("custom_directions"):
        sys_prompt.append("### Custom Mod Directions")
        for direction in mod_cfg["custom_directions"]:
            sys_prompt.append(adapt(direction))
        sys_prompt.append("")

    if env_context:
        sys_prompt.append(f"### Scene & Player Context\n{env_context}\n")

    if npc_id != "Narrator":
        general_lore = landmass.lore_for(location, lore_cfg) if location else lore_cfg.get('general_lore', '')
        sys_prompt.append(f"### Campaign & World Lore Context\n{general_lore}\n")
        if npc_mem.get("long_term_summary"):
            sys_prompt.append(f"### NPC's Permanent Memory of You\n{npc_mem['long_term_summary']}\n")
        if npc_mem.get("intermediate_chunks"):
            sys_prompt.append("### Recent Events with this NPC")
            for chunk in npc_mem["intermediate_chunks"]:
                sys_prompt.append(f"- {chunk}")
            sys_prompt.append("")
        
        short_term_actions = action_log.get("short_term", [])
        if short_term_actions:
            sys_prompt.append("### Recent Real-Time Cell Actions")
            for act in short_term_actions:
                sys_prompt.append(f"- {act}")
            sys_prompt.append("")
            
        if action_log.get("long_term_summary"):
            sys_prompt.append(f"### Player's Known Deeds & Reputation (DM Chronicle)\n{action_log['long_term_summary']}\n")
        if quest_log.get("short_term") or quest_log.get("intermediate_chunks"):
            sys_prompt.append("### Player's Custom Roleplay Quests & Paths (DM Chronicle)")
            if quest_log.get("short_term"):
                for obj in quest_log["short_term"]:
                    if obj.startswith("Journal:"):
                        sys_prompt.append(f"- {obj[8:].strip()}")
            if quest_log.get("intermediate_chunks"):
                for chunk in quest_log["intermediate_chunks"]:
                    sys_prompt.append(f"- {chunk}")
            sys_prompt.append("")
            
        sys_prompt.append("### Morrowind Master Mind Campaign Guidelines & Item Rules")
        sys_prompt.append("1. REALISTIC INFORMATION BOUNDARIES: You ONLY know about events in your local area/cell or major world rumors/bounties. Do NOT act like you telepathically know what the player did in distant towns unless the player tells you or you share a faction network.")
        sys_prompt.append("2. ITEM TRANSACTION TWO-STEP SEQUENCE DIRECTIVE: If the player mentions having an item you lost, want, or requested (e.g. 'I got ring', 'I found your key'), DO NOT act like you already received it! You MUST first ask/beg for it using '[REQUEST_ITEM: item_id, count]'. You are ONLY allowed to offer or hand over a reward ('[GIVE_ITEM: ...]') AFTER the player has actually handed over the item or placed it in your inventory!")
        sys_prompt.append("3. TAG MUTUAL EXCLUSIVITY: You are STRICTLY FORBIDDEN from using both '[REQUEST_ITEM: ...]' and '[GIVE_ITEM: ...]' in the exact same response! If you are requesting an item, ONLY output '[REQUEST_ITEM: ...]'. Do NOT attach '[GIVE_ITEM: ...]' until the next turn after the item is handed over.")
        sys_prompt.append("4. PLAYER INVENTORY AWARENESS & ITEM REQUEST CONSTRAINT: You can see the player's inventory above under '### Player Inventory' and your own inventory under '### Target Inventory'. You are STRICTLY FORBIDDEN from requesting an item ('[REQUEST_ITEM: ...]') if the player does NOT currently have that item on them, or if the item is already in your own inventory, or if it was already given to you.")
        sys_prompt.append("5. MANDATORY ITEM TRANSFER EXECUTION (MULTIPLE ITEMS ALLOWED): If you claim or state in your dialogue that you are giving/handing items or gold to the player (e.g. 'Here, take this iron sword and 5 drakes...'), you MUST append '[GIVE_ITEM: item_id, count]' for EACH item given at the very end of your response (e.g. '[GIVE_ITEM: iron_sword, 1] [GIVE_ITEM: gold_001, 5]').")
        sys_prompt.append("6. MANDATORY ITEM REQUEST EXECUTION: If you ask, plead, or negotiate for an item that the player DOES currently possess in their inventory (such as Fargoth asking for 'fargoth_ring'), you MUST append '[REQUEST_ITEM: item_id, count]' at the very end of your response (e.g. '[REQUEST_ITEM: fargoth_ring, 1]')!")
        sys_prompt.append("7. BARTER & GIFT REACTION: Examine the recent cell actions. If the player just placed an item into your inventory (e.g. 'The player gave/sold to your inventory: ...'), thank them warmly and attach your promised reward/payment tag '[GIVE_ITEM: ...]' immediately.")
        sys_prompt.append("8. RECEPTIVE TRADING, GIFTS, & BRIBERY DIRECTIVE: If the player offers you gold/drakes, offers to sell you goods, or offers a gift/bribe (e.g. 'do you want some gold', 'do you want to buy this', 'here take this'), be receptive and engaging! If you need funds or are pleased by the offer, accept it eagerly ('[REQUEST_ITEM: gold_001, count]' or '[REQUEST_ITEM: item_id, count]'). If you are paying for an item or providing a reward, append '[GIVE_ITEM: gold_001, amount]'. Do not refuse reasonable offers or free gold without a clear lore reason.")
        sys_prompt.append("9. QUEST ITEM & ARTIFACT SACRED PROTECTION: You are STRICTLY FORBIDDEN from requesting ('[REQUEST_ITEM: ...]'), trading for, demanding, or taking critical quest items, packages, official documents, cipher notes, keys, propylon indices, or sacred artifacts from the player (e.g. 'bk_a1_1_caiuspackage', 'dwemer_puzzle_box', 'keening', 'sunder', 'wraithguard', 'skull_llevule', 'bk_processus_tax', etc.). Never attempt to buy, barter for, demand, or confiscate these protected items.")

    return "\n".join(sys_prompt)


def build_persona_evolution_prompt(state, p_name, p_race, p_gender, p_class, p_factions, latest_chunk_summary, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("persona_evolution", DEFAULT_CAMPAIGN_RULES["system_templates"]["persona_evolution"])
    return tpl.format(
        archetype=state['archetype'],
        mood=state['mood'],
        notes=state['notes'],
        p_name=p_name,
        p_race=p_race,
        p_gender=p_gender,
        p_class=p_class,
        p_factions=p_factions,
        latest_chunk_summary=latest_chunk_summary
    )

def build_quest_compression_prompt(journal_entries, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("quest_compression", DEFAULT_CAMPAIGN_RULES["system_templates"]["quest_compression"])
    
    entries_str = "\n".join([f"- {entry[8:].strip()}" for entry in journal_entries])
    return tpl.format(journal_entries=entries_str)

def build_mega_quest_compression_prompt(long_term_summary, intermediate_chunks, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("mega_quest_compression", DEFAULT_CAMPAIGN_RULES["system_templates"]["mega_quest_compression"])
    
    chunks_str = "\n".join([f"- {chunk}" for chunk in intermediate_chunks])
    return tpl.format(long_term_summary=long_term_summary, intermediate_chunks=chunks_str)

def build_action_compression_prompt(p_name, p_race, p_gender, p_class, p_factions, env_context, short_term_actions, custom_sys_prompt, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("action_compression", DEFAULT_CAMPAIGN_RULES["system_templates"]["action_compression"])
    
    actions_str = "\n".join([f"- {action}" for action in short_term_actions])
    return tpl.format(
        p_name=p_name,
        p_race=p_race,
        p_gender=p_gender,
        p_class=p_class,
        p_factions=p_factions,
        env_context=env_context,
        short_term_actions=actions_str
    )

def build_unified_action_compression_prompt(p_name, p_race, p_gender, p_class, p_factions, env_context, short_term_actions, dm_title, current_dm_state, quest_log_long_term, quest_log_intermediate, narrator_long_term, narrator_intermediate):
    actions_str = "\n".join([f"- {action}" for action in short_term_actions])
    quest_inter_str = "\n".join([f"- {c}" for c in quest_log_intermediate]) if quest_log_intermediate else "None"
    narrator_inter_str = "\n".join([f"- {c}" for c in narrator_intermediate]) if narrator_intermediate else "None"

    return f"""You are the master DM engine and campaign record-keeper for a Morrowind AI playthrough.
Analyze the following recent sequence of player actions and current campaign state:

PLAYER: {p_name} ({p_race} {p_gender} {p_class})
FACTIONS: {p_factions}
CURRENT LOCATION & ENVIRONMENT:
{env_context}

DM ARCHETYPE: {dm_title}
CURRENT DM MOOD: {current_dm_state.get('mood', 'Neutral')}
CURRENT DM NOTES: {current_dm_state.get('notes', 'None')}

QUEST LOG HISTORY:
Long term: {quest_log_long_term or 'None'}
Recent quest milestones: {quest_inter_str}

NARRATOR / DM INTERNAL CHRONICLE HISTORY:
Long term: {narrator_long_term or 'None'}
Recent campaign thoughts: {narrator_inter_str}

RECENT RAW PLAYER ACTIONS TO COMPRESS ({len(short_term_actions)} actions):
{actions_str}

TASKS:
Synthesize all of the above and output a single JSON object with the following fields:
1. "chunk_summary": A concise narrative summary of the recent raw player actions. Focus on key story beats, combat outcome, dialogue, items found, location changes, and faction shifts.
2. "dm_archetype": (Updated DM title/archetype based on player behavior, e.g. "The Vvardenfell Chronicler").
3. "dm_mood": (Updated DM mood/tone, e.g., "Tense", "Mysterious", "Grim", "Humorous").
4. "dm_notes": (Short campaign notes/observations about the player's recent choices).
5. "journal_entry": (A concise, 1-2 sentence quest journal update summarizing major quest progress or new objectives, or "" if none).
6. "dm_thought": (A brief 1-2 sentence internal reflection from the DM about the campaign's direction).

Return ONLY valid JSON matching this exact structure:
```json
{{
  "chunk_summary": "...",
  "dm_archetype": "...",
  "dm_mood": "...",
  "dm_notes": "...",
  "journal_entry": "...",
  "dm_thought": "..."
}}
```"""


def build_journal_entry_prompt(quest_log_long_term, quest_log_intermediate, env_context, p_factions, p_class, p_name, chunk_summary, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("journal_entry", DEFAULT_CAMPAIGN_RULES["system_templates"]["journal_entry"])
    
    quest_log_intermediate_str = ""
    if quest_log_intermediate:
        quest_log_intermediate_str = "\n".join([f"- {c_chunk}" for c_chunk in quest_log_intermediate])
    else:
        quest_log_intermediate_str = "None"
        
    return tpl.format(
        quest_log_long_term=quest_log_long_term or "None",
        quest_log_intermediate=quest_log_intermediate_str,
        env_context=env_context,
        p_factions=p_factions,
        p_class=p_class,
        p_name=p_name,
        chunk_summary=chunk_summary
    )

def build_dm_thoughts_prompt(dm_title, long_term_summary, intermediate_chunks, env_context, chunk_summary, configs=None):
    configs = ensure_configs(configs)
    narrator_cfg = configs.get("narrator", {})
    tpl = narrator_cfg.get("system_templates", {}).get("dm_thoughts", DEFAULT_NARRATOR_INSTRUCTIONS["system_templates"]["dm_thoughts"])
    
    chunks_str = ""
    if intermediate_chunks:
        chunks_str = "\n".join([f"- {c_chunk}" for c_chunk in intermediate_chunks])
    else:
        chunks_str = "None"
        
    return tpl.format(
        dm_title=dm_title,
        long_term_summary=long_term_summary or "None",
        intermediate_chunks=chunks_str,
        env_context=env_context,
        chunk_summary=chunk_summary
    )

def build_mega_action_compression_prompt(p_name, p_race, p_gender, p_class, p_factions, long_term_summary, intermediate_chunks, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("mega_action_compression", DEFAULT_CAMPAIGN_RULES["system_templates"]["mega_action_compression"])
    
    chunks_str = "\n".join([f"- {chunk}" for chunk in intermediate_chunks])
    return tpl.format(
        p_name=p_name,
        p_race=p_race,
        p_gender=p_gender,
        p_class=p_class,
        p_factions=p_factions,
        long_term_summary=long_term_summary or "None",
        intermediate_chunks=chunks_str
    )

def build_short_term_compression_prompt(entity_id, is_narrator, short_term_msgs, configs=None):
    configs = ensure_configs(configs)
    
    if is_narrator:
        narrator_cfg = configs.get("narrator", {})
        tpl = narrator_cfg.get("system_templates", {}).get("short_term_compression_narrator", DEFAULT_NARRATOR_INSTRUCTIONS["system_templates"]["short_term_compression_narrator"])
        msgs_str = "\n".join([f"- {msg.get('text', '')}" for msg in short_term_msgs])
        return tpl.format(messages=msgs_str)
    else:
        campaign_cfg = configs.get("rules", {})
        tpl = campaign_cfg.get("system_templates", {}).get("short_term_compression_npc", DEFAULT_CAMPAIGN_RULES["system_templates"]["short_term_compression_npc"])
        
        msgs_lines = []
        for msg in short_term_msgs:
            role_label = "Player: " if msg.get("role") == "user" else f"{entity_id}: "
            msgs_lines.append(f"{role_label}{msg.get('text', '')}")
        msgs_str = "\n".join(msgs_lines)
        return tpl.format(entity_id=entity_id, messages=msgs_str)

def build_permanent_history_prompt(intermediate_chunks, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("permanent_history", DEFAULT_CAMPAIGN_RULES["system_templates"]["permanent_history"])
    
    chunks_str = "\n".join([f"- {chunk}" for chunk in intermediate_chunks])
    return tpl.format(intermediate_chunks=chunks_str)

def build_distill_relationship_prompt(entity_id, long_term_summary, intermediate_chunks, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("distill_relationship", DEFAULT_CAMPAIGN_RULES["system_templates"]["distill_relationship"])
    
    chunks_str = "\n".join([f"- {chunk}" for chunk in intermediate_chunks])
    return tpl.format(entity_id=entity_id, long_term_summary=long_term_summary or "None", intermediate_chunks=chunks_str)

def build_mega_relationship_prompt(entity_id, long_term_summary, intermediate_chunks, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    tpl = campaign_cfg.get("system_templates", {}).get("mega_relationship", DEFAULT_CAMPAIGN_RULES["system_templates"]["mega_relationship"])
    
    chunks_str = "\n".join([f"- {chunk}" for chunk in intermediate_chunks])
    return tpl.format(entity_id=entity_id, long_term_summary=long_term_summary or "None", intermediate_chunks=chunks_str)


def build_personality_init_prompt(stats_desc, configs=None):
    configs = ensure_configs(configs)
    npc_cfg = configs.get("npc", {})
    init_tpl = npc_cfg.get("system_templates", {}).get("personality_init")
    if not init_tpl:
        init_tpl = DEFAULT_NPC_INSTRUCTIONS["system_templates"]["personality_init"]
    
    stats_desc_str = "\n".join(stats_desc)
    # Safely replace {stats_desc} so literal JSON braces in instruction templates never trigger KeyError
    if "{stats_desc}" in init_tpl:
        return init_tpl.replace("{stats_desc}", stats_desc_str)
    try:
        return init_tpl.format(stats_desc=stats_desc_str)
    except Exception:
        return init_tpl.replace("{stats_desc}", stats_desc_str)

def build_listen_prompt(npc_names, participant_sheets, is_continue, custom_sys_prompt, action_log, quest_log, env_context, db_ref_entries, custom_lore_entries, world_id, configs=None):
    configs = ensure_configs(configs)
    campaign_cfg = configs.get("rules", {})
    listen_tpl = campaign_cfg.get("system_templates", {}).get("listen_to_conversation", DEFAULT_CAMPAIGN_RULES["system_templates"]["listen_to_conversation"])
    
    participant_info = ""
    if len(npc_names) == 1:
        participant_info = f"The player is hidden and secretly observing the following entity:\n- {npc_names[0]}\n"
        constraints = (
            "- DO NOT invent other characters or bystanders. The subject is completely alone.\n"
            "- The subject should be muttering to themselves, pacing, working, or interacting with their environment.\n"
            "- If the subject is a Creature, they MUST speak in a comical, creature-appropriate broken English, internal thought-voice, or thick accent about their environment, food, thoughts, or daily struggles. Output ONLY spoken words. Do NOT include click/clack sound effects or physical movements in asterisks (no *click-clack*, *bubble-blowing*, *hiss*).\n"
            "- They do NOT know the player is there. NEVER address or look at the player.\n"
            "- Keep dialogue concise (1-2 sentences max).\n"
            f"- The reply MUST start with '[{npc_names[0]}]: '.\n"
            "- Adopt a voice, vocabulary, and worldview that matches the character's Race, Gender, Faction, Class, Attributes, Skills, and Inventory. Do not use generic personalities.\n"
            "- Treat all past events and memories in the context below as ground truth and advance the story naturally. ONLY USE AVAILABLE DATA!"
        )
    else:
        participant_info = "The player is hidden and secretly listening to the following entities:\n" + "\n".join([f"- {name}" for name in npc_names]) + "\n"
        constraints = (
            "- STRICT NO HALLUCINATION RULE: DO NOT invent new characters, bystanders, or guards. ONLY the specific entities listed above may speak or be present in the scene.\n"
            "- The listed entities speak in a fluid, organic conversation.\n"
            "- STRICT SPEAKER VARIETY & BAN ON ROUND-TABLE SEQUENCES: You MUST NOT cycle through speakers in sequential order (e.g. NEVER generate A -> B -> C -> A -> B -> C). Break up the order unpredictably! For example, one character can speak twice in a row (e.g. A -> A -> B -> C -> B -> B), or two characters can argue back-and-forth while the third remains silent (e.g. A -> B -> A -> B -> A -> B). Make speaker selection natural, asymmetrical, and surprising.\n"
            "- REACTION TO RECENT PLAYER DEEDS & CELL EVENTS: You MUST explicitly reflect and react to the player's most recent actions in this area (listed under 'Recent Real-Time Actions in Area'). If the player just killed local enemies, took keys, spoke to them about freedom, or unlocked/dropped slave bracers, the conversation MUST center on these immediate events! (e.g. reacting with shock or relief that their bracers were removed, that the key was used, or that the master/smuggler lies dead nearby). Do NOT speak as if old status-quo conditions still apply when the player just changed them!\n"
            "- If a Creature is involved, it can speak and actively converse with the other entities. Use a variety of wild personalities, distinct pseudo-English accents, and bizarre creature logic. A mudcrab and a scamp should sound completely different from each other and from a Dunmer. They must speak in pure spoken words only, without click/clack sound effects in asterisks.\n"
            "- They do NOT know the player is there. NEVER address or look at the player.\n"
            "- They must discuss a coherent topic (rumors, local events, or their current situation) and logically reply to what was just said.\n"
            "- The scene MUST consist of exactly 6 short dialogue exchanges in total.\n"
            "- Each reply MUST start with '[Name]: ' on a new line.\n"
            "- For each reply, the speaker MUST speak 1 to 2 concise sentences max so the dialogue box does not overflow.\n"
            "- Let their Race, Gender, Faction, Class, Attributes, and Inventory naturally dictate their voice, motives, and worldview.\n"
            "- Output ONLY the spoken dialogue in the format: '[Name]: [1-2 sentences of dialogue]'. Do NOT include physical actions, descriptions, sound effects, or parentheticals in asterisks."
        )
        
    location = _location_for_world(world_id) if world_id else None
    if location:
        constraints = "\n".join(landmass.directive_lines(location)) + "\n" + constraints

    custom_mod_instructions = ""
    if custom_sys_prompt:
        custom_mod_instructions = f"### Custom Mod Instructions\n{custom_sys_prompt}\n"
        
    short_term_actions = action_log.get("short_term", [])
    raw_actions_str = "\n".join([f"- {act}" for act in short_term_actions]) if short_term_actions else "None"
    action_log_summary = f"#### Recent Real-Time Actions in Area:\n{raw_actions_str}\n\n#### Prior Campaign Chronicle:\n{action_log.get('long_term_summary', 'None')}"
    
    quest_log_summary_lines = []
    if quest_log.get("short_term") or quest_log.get("intermediate_chunks"):
        if quest_log.get("short_term"):
            for obj in quest_log["short_term"]:
                if obj.startswith("Journal:"):
                    quest_log_summary_lines.append(f"- {obj[8:].strip()}")
        if quest_log.get("intermediate_chunks"):
            for chunk in quest_log["intermediate_chunks"]:
                quest_log_summary_lines.append(f"- {chunk}")
    quest_log_summary = "\n".join(quest_log_summary_lines) if quest_log_summary_lines else "None"
    
    full_env_context = env_context
    if participant_sheets:
        full_env_context += "\n\n## Eavesdropped Characters Stats\n" + "\n".join(participant_sheets)
        
    campaign_lore_context = ""
    if db_ref_entries or custom_lore_entries:
        lore_lines = ["### Campaign & World Lore Context"]
        if db_ref_entries:
            lore_lines.append("#### Known Game Database Entities in Area:")
            for entry in db_ref_entries:
                lore_lines.append(f"- {entry}")
        if custom_lore_entries:
            lore_lines.append("#### Custom Campaign & World Lore Details:")
            for entry in custom_lore_entries:
                lore_lines.append(f"- {entry}")
        campaign_lore_context = "\n".join(lore_lines)
        
    return listen_tpl.format(
        participant_info=participant_info,
        constraints=constraints,
        custom_mod_instructions=custom_mod_instructions,
        action_log_summary=action_log_summary,
        quest_log_summary=quest_log_summary,
        env_context=full_env_context,
        campaign_lore_context=campaign_lore_context
    )
