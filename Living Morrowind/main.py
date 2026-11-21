import os
import sys
# Living Morrowind: always run from the mod folder, wherever we were launched from
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import json
import sqlite3
import shutil
import paths
import prompt_generator
import landmass
import addon_manager
import socket
import re
import urllib.request
import urllib.error
import threading
import time
from concurrent.futures import ThreadPoolExecutor

class Logger(object):
    def __init__(self, filename="daemon_debug.log"):
        self.terminal = sys.stdout
        self.filename = filename
        if os.path.exists(filename) and os.path.getsize(filename) > 10 * 1024 * 1024:
            try:
                if os.path.exists(filename + ".old"):
                    os.remove(filename + ".old")
                os.rename(filename, filename + ".old")
            except Exception:
                pass
        self.log = open(filename, "a", encoding="utf-8", errors="ignore")
        self.log.write(f"\n--- DAEMON STARTED AT {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        self.log.flush()

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger()
sys.stderr = sys.stdout

def disable_windows_quickedit():
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            h_stdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
                # Clear ENABLE_QUICK_EDIT_MODE (0x0040) and set ENABLE_EXTENDED_FLAGS (0x0080)
                new_mode = (mode.value & ~0x0040) | 0x0080
                kernel32.SetConsoleMode(h_stdin, new_mode)
        except Exception:
            pass

ENV_PATH = ".env"
should_shutdown = False
memory_write_lock = threading.Lock()
server_socket = None

def parse_env():
    env_file = None
    for candidate in [ENV_PATH, ".env.txt"]:
        if os.path.exists(candidate):
            env_file = candidate
            break

    if not env_file:
        print(f"[AI CORE ERROR] .env file not found in: {os.path.abspath('.')}")
        print("[AI CORE ERROR] Run 'Launch Living Morrowind.bat' to enter your API key, or copy 'env_template.txt' to '.env' and paste your GEMINI_API_KEY into it.")
        return None, None, None, None
        
    api_key = ""
    model_name = "gemini-3.5-flash-lite"
    fallback_model = "gemini-3.1-flash-lite-preview"
    lightweight_model = "models/gemma-4-26b-a4b-it"
    
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.split("GEMINI_API_KEY=", 1)[1].strip()
                elif line.startswith("PRIMARY_MODEL="):
                    model_name = line.split("PRIMARY_MODEL=", 1)[1].strip()
                elif line.startswith("MODEL_NAME="):
                    model_name = line.split("MODEL_NAME=", 1)[1].strip()
                elif line.startswith("FALLBACK_MODEL="):
                    fallback_model = line.split("FALLBACK_MODEL=", 1)[1].strip()
                elif line.startswith("LIGHTWEIGHT_MODEL="):
                    lightweight_model = line.split("LIGHTWEIGHT_MODEL=", 1)[1].strip()
    except Exception as e:
        print(f"[AI CORE ERROR] Error reading {env_file}: {e}")
        return None, None, None, None
        
    if not api_key or api_key in ("YOUR_API_KEY_HERE", "YOUR_GEMINI_API_KEY_HERE"):
        print(f"[AI CORE ERROR] GEMINI_API_KEY in your {env_file} file is empty or set to the default placeholder!")
        print(f"[AI CORE ERROR] Please update {env_file} with your actual Gemini API key from https://aistudio.google.com/")
        return None, None, None, None
        
    return api_key, model_name, fallback_model, lightweight_model

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

def open_db(world_id):
    world_dir = get_world_dir(world_id)
    os.makedirs(world_dir, exist_ok=True)
    db_path = os.path.join(world_dir, "morrowind_ai.db")
    
    try:
        db = sqlite3.connect(db_path, timeout=15.0)
        cursor = db.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        cursor.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, val TEXT);")
        cursor.execute("""CREATE TABLE IF NOT EXISTS game_database (
                            id TEXT PRIMARY KEY,
                            name TEXT,
                            type TEXT
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS character_memory (
                            world_id TEXT,
                            npc_id TEXT,
                            long_term_summary TEXT,
                            intermediate_chunks TEXT,
                            short_term TEXT,
                            permanent_entries TEXT,
                            PRIMARY KEY (world_id, npc_id)
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS action_logs (
                            world_id TEXT PRIMARY KEY,
                            long_term_summary TEXT,
                            intermediate_chunks TEXT,
                            short_term TEXT
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS quest_logs (
                            world_id TEXT PRIMARY KEY,
                            long_term_summary TEXT,
                            intermediate_chunks TEXT,
                            short_term TEXT
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS character_names (
                            world_id TEXT,
                            id TEXT,
                            name TEXT,
                            PRIMARY KEY (world_id, id)
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS character_personality (
                            world_id TEXT,
                            npc_id TEXT,
                            personality_summary TEXT,
                            long_term_goals TEXT,
                            initialized INTEGER DEFAULT 0,
                            PRIMARY KEY (world_id, npc_id)
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS custom_lore (
                            id TEXT PRIMARY KEY,
                            name TEXT,
                            lore TEXT
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS dm_campaign_state (
                            world_id TEXT PRIMARY KEY,
                            archetype TEXT,
                            mood TEXT,
                            notes TEXT
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS custom_quests (
                            quest_id TEXT PRIMARY KEY,
                            world_id TEXT,
                            title TEXT,
                            description TEXT,
                            giver_npc_id TEXT,
                            status TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                          );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS player_factions (
                            world_id TEXT,
                            faction_name TEXT,
                            rank_name TEXT,
                            is_custom INTEGER DEFAULT 0,
                            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            status TEXT DEFAULT 'joined',
                            PRIMARY KEY (world_id, faction_name)
                          );""")
        try:
            cursor.execute("ALTER TABLE player_factions ADD COLUMN status TEXT DEFAULT 'joined';")
        except Exception:
            pass
        db.commit()
        return db
    except Exception as e:
        print(f"[AI SQLITE ERROR] Cannot open or initialize database: {e}")
        return None

def check_and_import_game_database(world_id):
    world_dir = get_world_dir(world_id)
    db_json_path = os.path.join(world_dir, "game_database.json")
    if not os.path.exists(db_json_path):
        return
        
    mtime = str(os.path.getmtime(db_json_path))
    db = open_db(world_id)
    if not db:
        return
        
    cursor = db.cursor()
    cursor.execute("SELECT val FROM metadata WHERE key = 'last_import_mtime'")
    row = cursor.fetchone()
    last_import_mtime = row[0] if row else ""
    
    if last_import_mtime == mtime:
        db.close()
        return
        
    print("[AI CORE HUB] Importing game_database.json records into SQLite...")
    try:
        db.execute("BEGIN TRANSACTION;")
        with open(db_json_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('[') or line.endswith(']'):
                    continue
                if line.endswith(','):
                    line = line[:-1].strip()
                try:
                    obj = json.loads(line)
                    entity_id = obj.get("id")
                    name = obj.get("name")
                    entity_type = obj.get("type", "unknown")
                    if entity_id and name:
                        cursor.execute("INSERT OR REPLACE INTO game_database (id, name, type) VALUES (?, ?, ?)", (entity_id, name, entity_type))
                except json.JSONDecodeError:
                    continue
        cursor.execute("INSERT OR REPLACE INTO metadata (key, val) VALUES ('last_import_mtime', ?)", (mtime,))
        db.execute("COMMIT;")
        print("[AI CORE HUB] Import finished successfully.")
    except Exception as e:
        db.execute("ROLLBACK;")
        print(f"[AI CORE ERROR] Failed to import game database: {e}")
    finally:
        db.close()

def check_and_import_custom_lore(world_id):
    default_path = os.path.join(get_primary_config_dir(), "custom_lore.json")
    world_dir = get_world_dir(world_id)
    db_json_path = os.path.join(world_dir, "custom_lore.json")
    
    if not os.path.exists(db_json_path) and os.path.exists(default_path):
        os.makedirs(world_dir, exist_ok=True)
        import shutil
        shutil.copyfile(default_path, db_json_path)
        print(f"[AI CORE HUB] Copied custom_lore.json from config to world folder: {world_id}")
            
    if not os.path.exists(db_json_path):
        return
        
    mtime = str(os.path.getmtime(db_json_path))
    db = open_db(world_id)
    if not db:
        return
        
    cursor = db.cursor()
    cursor.execute("SELECT val FROM metadata WHERE key = 'last_custom_lore_import_mtime'")
    row = cursor.fetchone()
    last_import_mtime = row[0] if row else ""
    
    if last_import_mtime == mtime:
        db.close()
        return
        
    print("[AI CORE HUB] Importing custom_lore.json records into SQLite...")
    try:
        db.execute("BEGIN TRANSACTION;")
        with open(db_json_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('[') or line.endswith(']'):
                    continue
                if line.endswith(','):
                    line = line[:-1].strip()
                try:
                    obj = json.loads(line)
                    entity_id = obj.get("id")
                    name = obj.get("name")
                    lore = obj.get("lore")
                    if entity_id and name:
                        cursor.execute("INSERT OR REPLACE INTO custom_lore (id, name, lore) VALUES (?, ?, ?)", (entity_id, name, lore))
                except json.JSONDecodeError:
                    continue
        cursor.execute("INSERT OR REPLACE INTO metadata (key, val) VALUES ('last_custom_lore_import_mtime', ?)", (mtime,))
        db.execute("COMMIT;")
        print("[AI CORE HUB] Custom lore import finished successfully.")
    except Exception as e:
        db.execute("ROLLBACK;")
        print(f"[AI CORE ERROR] Failed to import custom lore: {e}")
    finally:
        db.close()

def fork_world_memories(old_world_id, new_world_id):
    new_dir = get_world_dir(new_world_id)
    os.makedirs(new_dir, exist_ok=True)
    if old_world_id == "default" or not old_world_id:

        return
    old_dir = get_world_dir(old_world_id)
    if os.path.exists(old_dir):
        import shutil
        for item in os.listdir(old_dir):
            s = os.path.join(old_dir, item)
            d = os.path.join(new_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)


def get_clean_name_for_display(world_id, entity_id, name):
    if entity_id in ("Narrator", "Eavesdrop_Session"):
        return name
        
    is_generic = False
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = "SELECT COUNT(*) FROM game_database WHERE name = ? AND (type = 'NPC' OR type = 'Creature') AND id NOT GLOB '*[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' AND id NOT LIKE '%test%' AND id NOT LIKE '%dummy%' AND id NOT LIKE '%template%' AND id NOT LIKE '%active%' AND id NOT LIKE '%copy%';"
        try:
            cursor.execute(sql, (name,))
            row = cursor.fetchone()
            if row and row[0] > 1:
                is_generic = True
        except Exception as e:
            print(f"[ERROR] SQL get_clean_name_for_display error: {e}")
        db.close()
        
    if is_generic:
        match = re.search(r'(\d+)$', entity_id)
        if match:
            num_suffix = match.group(1)
            try:
                num = int(num_suffix)
                short_num = num % 10000
                return f"{name} {short_num + 1}"
            except ValueError:
                return f"{name} {num_suffix}"
    return name

def get_clean_memory_file_prefix(world_id, entity_id):
    if entity_id == "Narrator":
        return "Narrator"
    if entity_id == "Eavesdrop_Session":
        return "Eavesdrop_Session"
        
    base_id = entity_id
    while base_id and base_id[-1].isdigit():
        base_id = base_id[:-1]
        
    npc_name = base_id
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = "SELECT name FROM game_database WHERE id = ?;"
        try:
            cursor.execute(sql, (base_id,))
            row = cursor.fetchone()
            if row and row[0]:
                npc_name = row[0]
        except Exception as e:
            print(f"[ERROR] SQL get_clean_memory_file_prefix error: {e}")
        db.close()
        
    display_name = get_clean_name_for_display(world_id, entity_id, npc_name)
    
    clean_name = ""
    for c in display_name:
        if c in '\\/:*?"<>|':
            clean_name += '_'
        elif c == ' ':
            clean_name += '_'
        else:
            clean_name += c
            
    return f"Memory_{clean_name}"

def save_memory(world_id, entity_id, mem):
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = """INSERT OR REPLACE INTO character_memory 
                 (world_id, npc_id, long_term_summary, intermediate_chunks, short_term, permanent_entries) 
                 VALUES (?, ?, ?, ?, ?, ?);"""
        try:
            cursor.execute(sql, (
                world_id,
                entity_id,
                mem.get("long_term_summary", ""),
                json.dumps(mem.get("intermediate_chunks", [])),
                json.dumps(mem.get("short_term", [])),
                json.dumps(mem.get("permanent_entries", []))
            ))
            db.commit()
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to save memory to SQLite: {e}")
        db.close()
        
    prefix = get_clean_memory_file_prefix(world_id, entity_id)
    world_dir = get_world_dir(world_id)
    
    if entity_id not in ("Narrator", "Eavesdrop_Session"):
        npc_folder_name = prefix
        if npc_folder_name.startswith("Memory_"):
            npc_folder_name = npc_folder_name[7:]
        target_dir = os.path.join(world_dir, "NPCs", npc_folder_name)
    else:
        target_dir = world_dir
        
    os.makedirs(target_dir, exist_ok=True)
    
    try:
        # Sanitize short_term - handle both plain strings (NPC) and dicts (Narrator)
        def _sanitize_st(entry):
            if isinstance(entry, dict):
                return {**entry, "text": clean_utf8_to_ansi(entry.get("text", ""))}
            return clean_utf8_to_ansi(str(entry))
            
        clean_st = [_sanitize_st(e) for e in mem.get("short_term", [])]
        clean_chunks = [clean_utf8_to_ansi(e) for e in mem.get("intermediate_chunks", [])]
        clean_lt = clean_utf8_to_ansi(mem.get("long_term_summary", ""))
        clean_perm = [clean_utf8_to_ansi(e) for e in mem.get("permanent_entries", [])]
        
        with memory_write_lock:
            with open(os.path.join(target_dir, f"{prefix}_ShortTerm.json"), 'w', encoding='utf-8') as f:
                json.dump({"short_term": clean_st}, f, indent=2, ensure_ascii=True)
            with open(os.path.join(target_dir, f"{prefix}_Intermediate.json"), 'w', encoding='utf-8') as f:
                json.dump({"intermediate_chunks": clean_chunks}, f, indent=2, ensure_ascii=True)
            with open(os.path.join(target_dir, f"{prefix}_LongTerm.json"), 'w', encoding='utf-8') as f:
                json.dump({"long_term_summary": clean_lt}, f, indent=2, ensure_ascii=True)
            with open(os.path.join(target_dir, f"{prefix}_Permanent.json"), 'w', encoding='utf-8') as f:
                json.dump({"permanent_entries": clean_perm}, f, indent=2, ensure_ascii=True)
    except Exception as e:
        print(f"[AI CORE ERROR] Failed to write memory files: {e}")


def load_memory(world_id, entity_id):
    loaded = False
    mem = {
        "long_term_summary": "",
        "intermediate_chunks": [],
        "short_term": [],
        "permanent_entries": []
    }
    
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = "SELECT long_term_summary, intermediate_chunks, short_term, permanent_entries FROM character_memory WHERE world_id = ? AND npc_id = ?;"
        try:
            cursor.execute(sql, (world_id, entity_id))
            row = cursor.fetchone()
            if row:
                mem["long_term_summary"] = row[0] or ""
                mem["intermediate_chunks"] = json.loads(row[1]) if row[1] else []
                mem["short_term"] = json.loads(row[2]) if row[2] else []
                mem["permanent_entries"] = json.loads(row[3]) if row[3] else []
                loaded = True
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to load memory from SQLite: {e}")
        db.close()
        
    if not loaded:
        prefix = get_clean_memory_file_prefix(world_id, entity_id)
        world_dir = get_world_dir(world_id)
        if entity_id not in ("Narrator", "Eavesdrop_Session"):
            npc_folder_name = prefix
            if npc_folder_name.startswith("Memory_"):
                npc_folder_name = npc_folder_name[7:]
            target_dir = os.path.join(world_dir, "NPCs", npc_folder_name)
        else:
            target_dir = world_dir
            
        fst_p = os.path.join(target_dir, f"{prefix}_ShortTerm.json")
        fint_p = os.path.join(target_dir, f"{prefix}_Intermediate.json")
        flt_p = os.path.join(target_dir, f"{prefix}_LongTerm.json")
        fperm_p = os.path.join(target_dir, f"{prefix}_Permanent.json")
        
        if os.path.exists(fst_p) and os.path.exists(fint_p) and os.path.exists(flt_p) and os.path.exists(fperm_p):
            try:
                with open(fst_p, 'r', encoding='utf-8') as f:
                    mem["short_term"] = json.load(f).get("short_term", [])
                with open(fint_p, 'r', encoding='utf-8') as f:
                    mem["intermediate_chunks"] = json.load(f).get("intermediate_chunks", [])
                with open(flt_p, 'r', encoding='utf-8') as f:
                    mem["long_term_summary"] = json.load(f).get("long_term_summary", "")
                with open(fperm_p, 'r', encoding='utf-8') as f:
                    mem["permanent_entries"] = json.load(f).get("permanent_entries", [])
                loaded = True
                save_memory(world_id, entity_id, mem)
            except Exception as e:
                print(f"[AI CORE ERROR] Error reading memory files: {e}")
        else:
            legacy_p = os.path.join(world_dir, f"ai_memory_{entity_id}.json")
            if not os.path.exists(legacy_p):
                legacy_p = os.path.join(world_dir, f"Memory_{prefix}.json")
            if os.path.exists(legacy_p):
                try:
                    with open(legacy_p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        mem["long_term_summary"] = data.get("long_term_summary", "")
                        mem["intermediate_chunks"] = data.get("intermediate_chunks", [])
                        mem["short_term"] = data.get("short_term", [])
                        mem["permanent_entries"] = data.get("permanent_entries", [])
                    loaded = True
                    print(f"[AI CORE HUB] Fallback loaded memory from legacy JSON for '{entity_id}'")
                    save_memory(world_id, entity_id, mem)
                except Exception as e:
                    print(f"[AI CORE ERROR] Error reading legacy memory file: {e}")
                    
    return mem

def save_action_log(world_id, act):
    # Sanitize all tiers before saving so no raw Unicode curly quotes reach the JSON
    clean_short = [clean_utf8_to_ansi(e) for e in act.get("short_term", [])]
    clean_intermediate = [clean_utf8_to_ansi(e) for e in act.get("intermediate_chunks", [])]
    clean_longterm = clean_utf8_to_ansi(act.get("long_term_summary", ""))
    
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = """INSERT OR REPLACE INTO action_logs 
                 (world_id, long_term_summary, intermediate_chunks, short_term) 
                 VALUES (?, ?, ?, ?);"""
        try:
            cursor.execute(sql, (
                world_id,
                clean_longterm,
                json.dumps(clean_intermediate),
                json.dumps(clean_short)
            ))
            db.commit()
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to save ActionLog to SQLite: {e}")
        db.close()
        
    world_dir = get_world_dir(world_id)
    os.makedirs(world_dir, exist_ok=True)
    try:
        with open(os.path.join(world_dir, "Global_Action_ShortTerm.json"), 'w', encoding='utf-8') as f:
            json.dump({"short_term": clean_short}, f, indent=2, ensure_ascii=True)
        with open(os.path.join(world_dir, "Global_Action_Intermediate.json"), 'w', encoding='utf-8') as f:
            json.dump({"intermediate_chunks": clean_intermediate}, f, indent=2, ensure_ascii=True)
        with open(os.path.join(world_dir, "Global_Action_LongTerm.json"), 'w', encoding='utf-8') as f:
            json.dump({"long_term_summary": clean_longterm}, f, indent=2, ensure_ascii=True)
    except Exception as e:
        print(f"[AI CORE ERROR] Failed to write action logs: {e}")

def load_dm_state(world_id):
    state = {
        "archetype": "The Vvardenfell Chronicler",
        "mood": "Immersive",
        "notes": "Chronicle initiated. Observing Vvardenfell."
    }
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = "SELECT archetype, mood, notes FROM dm_campaign_state WHERE world_id = ?;"
        try:
            cursor.execute(sql, (world_id,))
            row = cursor.fetchone()
            if row:
                state["archetype"] = row[0] or "The Vvardenfell Chronicler"
                state["mood"] = row[1] or "Immersive"
                state["notes"] = row[2] or ""
            else:
                state["archetype"] = "The Vvardenfell Chronicler"
                state["notes"] = "Chronicle initiated. Observing Vvardenfell."
                state["mood"] = "Immersive"
                
                cursor.execute("INSERT INTO dm_campaign_state (world_id, archetype, mood, notes) VALUES (?, ?, ?, ?);",
                               (world_id, state["archetype"], state["mood"], state["notes"]))
                db.commit()
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to load/init dm_state: {e}")
        db.close()
    return state

def save_dm_state(world_id, state):
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = """INSERT INTO dm_campaign_state (world_id, archetype, mood, notes) VALUES (?, ?, ?, ?)
                 ON CONFLICT(world_id) DO UPDATE SET archetype=excluded.archetype, mood=excluded.mood, notes=excluded.notes;"""
        try:
            cursor.execute(sql, (world_id, state.get("archetype", "The Vvardenfell Chronicler"), state.get("mood", "Immersive"), state.get("notes", "")))
            db.commit()
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to save dm_state: {e}")
        db.close()

def evolve_dm_persona(api_key, model_name, world_id, latest_chunk_summary):
    state = load_dm_state(world_id)
    try:
        p_name, p_race, p_gender, p_class, p_factions = load_player_status_from_env_json(world_id)
    except Exception:
        p_name, p_race, p_gender, p_class, p_factions = "the player", "outlander", "adventurer", "none", "none"

    prompt = prompt_generator.build_persona_evolution_prompt(state, p_name, p_race, p_gender, p_class, p_factions, latest_chunk_summary)
    prompt_generator.write_prompt_logic_info(world_id, "DM Persona Evolution", None, prompt)
    reply = call_gemini_single_prompt(api_key, model_name, prompt, max_tokens=350, system_instruction="You are the Morrowind DM persona engine. Return only a valid raw JSON object.", response_mime_type="application/json")
    if reply:
        data = extract_json_from_text(reply)
        if data and isinstance(data, dict):
            if "archetype" in data and "mood" in data and "notes" in data:
                state["archetype"] = clean_utf8_to_ansi(str(data["archetype"]))
                state["mood"] = clean_utf8_to_ansi(str(data["mood"]))
                state["notes"] = clean_utf8_to_ansi(str(data["notes"]))
                save_dm_state(world_id, state)
        else:
            print(f"[AI CORE ERROR] Failed to parse evolved DM state. Raw reply: {reply}")

def load_action_log(world_id):
    loaded = False
    act = {
        "long_term_summary": "",
        "intermediate_chunks": [],
        "short_term": []
    }
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = "SELECT long_term_summary, intermediate_chunks, short_term FROM action_logs WHERE world_id = ?;"
        try:
            cursor.execute(sql, (world_id,))
            row = cursor.fetchone()
            if row:
                act["long_term_summary"] = row[0] or ""
                act["intermediate_chunks"] = json.loads(row[1]) if row[1] else []
                act["short_term"] = json.loads(row[2]) if row[2] else []
                loaded = True
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to load ActionLog: {e}")
        db.close()
        
    if not loaded:
        world_dir = get_world_dir(world_id)
        fst_p = os.path.join(world_dir, "Global_Action_ShortTerm.json")
        fint_p = os.path.join(world_dir, "Global_Action_Intermediate.json")
        flt_p = os.path.join(world_dir, "Global_Action_LongTerm.json")
        if os.path.exists(fst_p) and os.path.exists(fint_p) and os.path.exists(flt_p):
            try:
                with open(fst_p, 'r', encoding='utf-8') as f:
                    act["short_term"] = json.load(f).get("short_term", [])
                with open(fint_p, 'r', encoding='utf-8') as f:
                    act["intermediate_chunks"] = json.load(f).get("intermediate_chunks", [])
                with open(flt_p, 'r', encoding='utf-8') as f:
                    act["long_term_summary"] = json.load(f).get("long_term_summary", "")
                loaded = True
                save_action_log(world_id, act)
            except Exception as e:
                print(f"[AI CORE ERROR] Error reading action files: {e}")
        else:
            legacy_p = os.path.join(world_dir, "Global_Action_History.json")
            if not os.path.exists(legacy_p):
                legacy_p = os.path.join(world_dir, "ai_actions.json")
            if os.path.exists(legacy_p):
                try:
                    with open(legacy_p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        act["long_term_summary"] = data.get("long_term_summary", "")
                        act["intermediate_chunks"] = data.get("intermediate_chunks", [])
                        act["short_term"] = data.get("short_term", [])
                    loaded = True
                    print(f"[AI CORE HUB] Fallback loaded ActionLog from legacy JSON for world '{world_id}'")
                    save_action_log(world_id, act)
                except Exception as e:
                    print(f"[AI CORE ERROR] Error reading legacy action file: {e}")
    return act

def save_quest_log(world_id, ql):
    # Sanitize before saving
    clean_short = [clean_utf8_to_ansi(e) for e in ql.get("short_term", [])]
    clean_intermediate = [clean_utf8_to_ansi(e) for e in ql.get("intermediate_chunks", [])]
    clean_longterm = clean_utf8_to_ansi(ql.get("long_term_summary", ""))
    
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = """INSERT OR REPLACE INTO quest_logs 
                 (world_id, long_term_summary, intermediate_chunks, short_term) 
                 VALUES (?, ?, ?, ?);"""
        try:
            cursor.execute(sql, (
                world_id,
                clean_longterm,
                json.dumps(clean_intermediate),
                json.dumps(clean_short)
            ))
            db.commit()
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to save QuestLog to SQLite: {e}")
        db.close()
        
    world_dir = get_world_dir(world_id)
    os.makedirs(world_dir, exist_ok=True)
    try:
        with open(os.path.join(world_dir, "Quest_ShortTerm.json"), 'w', encoding='utf-8') as f:
            json.dump({"short_term": clean_short}, f, indent=2, ensure_ascii=True)
        with open(os.path.join(world_dir, "Quest_Intermediate.json"), 'w', encoding='utf-8') as f:
            json.dump({"intermediate_chunks": clean_intermediate}, f, indent=2, ensure_ascii=True)
        with open(os.path.join(world_dir, "Quest_LongTerm.json"), 'w', encoding='utf-8') as f:
            json.dump({"long_term_summary": clean_longterm}, f, indent=2, ensure_ascii=True)
    except Exception as e:
        print(f"[AI CORE ERROR] Failed to write quest logs: {e}")

def compress_quest_log(api_key, model_name, world_id, quest_log):
    journal_entries = [entry for entry in quest_log.get("short_term", []) if entry.startswith("Journal:")]
    
    if len(journal_entries) >= 40:
        print("[AI SCRIBE AUTO QUEST] Compressing quest log...")
        prompt = prompt_generator.build_quest_compression_prompt(journal_entries)
        prompt_generator.write_prompt_logic_info(world_id, "Quest Chunk Compression", None, prompt)
        chunk_summary = call_gemini_single_prompt(api_key, model_name, prompt)
        if chunk_summary:
            print(f"[AI SCRIBE AUTO QUEST] Quest chunk summary synthesized: {chunk_summary}")
            quest_log["intermediate_chunks"].append(chunk_summary)
            
        quest_log["short_term"] = [entry for entry in quest_log["short_term"] if not entry.startswith("Journal:")]
        
    if len(quest_log.get("intermediate_chunks", [])) >= 40:
        print("[AI SCRIBE AUTO QUEST] Intermediate quest chunks limit reached. Synthesizing permanent history...")
        prompt = prompt_generator.build_mega_quest_compression_prompt(quest_log.get('long_term_summary', ''), quest_log["intermediate_chunks"])
        prompt_generator.write_prompt_logic_info(world_id, "Mega Quest Compression", None, prompt)
        new_quest_lt = call_gemini_single_prompt(api_key, model_name, prompt)
        if new_quest_lt:
            quest_log["long_term_summary"] = new_quest_lt
        quest_log["intermediate_chunks"] = []

def load_quest_log(world_id):
    loaded = False
    ql = {
        "long_term_summary": "",
        "intermediate_chunks": [],
        "short_term": []
    }
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        sql = "SELECT long_term_summary, intermediate_chunks, short_term FROM quest_logs WHERE world_id = ?;"
        try:
            cursor.execute(sql, (world_id,))
            row = cursor.fetchone()
            if row:
                ql["long_term_summary"] = row[0] or ""
                ql["intermediate_chunks"] = json.loads(row[1]) if row[1] else []
                ql["short_term"] = json.loads(row[2]) if row[2] else []
                loaded = True
        except Exception as e:
            print(f"[AI SQLITE ERROR] Failed to load QuestLog: {e}")
        db.close()
        
    if not loaded:
        world_dir = get_world_dir(world_id)
        fst_p = os.path.join(world_dir, "Quest_ShortTerm.json")
        fint_p = os.path.join(world_dir, "Quest_Intermediate.json")
        flt_p = os.path.join(world_dir, "Quest_LongTerm.json")
        if os.path.exists(fst_p) and os.path.exists(fint_p) and os.path.exists(flt_p):
            try:
                with open(fst_p, 'r', encoding='utf-8') as f:
                    ql["short_term"] = json.load(f).get("short_term", [])
                with open(fint_p, 'r', encoding='utf-8') as f:
                    ql["intermediate_chunks"] = json.load(f).get("intermediate_chunks", [])
                with open(flt_p, 'r', encoding='utf-8') as f:
                    ql["long_term_summary"] = json.load(f).get("long_term_summary", "")
                loaded = True
                save_quest_log(world_id, ql)
            except Exception as e:
                print(f"[AI CORE ERROR] Error reading quest files: {e}")
    return ql

def load_player_status_from_env_json(world_id):
    path = os.path.join(get_world_dir(world_id), "environment.json")
    if not os.path.exists(path):
        return "the player", "Dunmer", "Male", "Spellsword", "None"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            player = data.get("player", {})
            name = player.get("name", "the player")
            race = player.get("race", "Dunmer")
            gender = player.get("gender", "Male")
            class_name = player.get("class", "Spellsword")
            factions = player.get("factions", [])
            faction_str = ", ".join(factions) if factions else "None"
            return name, race, gender, class_name, faction_str
    except Exception as e:
        print(f"[ERROR] load_player_status_from_env_json error: {e}")
        return "the player", "Dunmer", "Male", "Spellsword", "None"

def format_environment_context(world_id):
    world_dir = get_world_dir(world_id)
    path = os.path.join(world_dir, "environment.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] format_environment_context error reading JSON: {e}")
        return ""
        
    cell = data.get("active_cell", "unknown cell")
    player = data.get("player", {})
    if not player or player.get("name") in ["Unknown", "the player", None] or not player.get("skills"):
        p_track_path = os.path.join(world_dir, "player_tracker.json")
        if os.path.exists(p_track_path):
            try:
                with open(p_track_path, 'r', encoding='utf-8') as pf:
                    p_track = json.load(pf)
                    if isinstance(p_track, dict) and p_track:
                        if not player:
                            player = p_track
                        else:
                            for pk, pv in p_track.items():
                                if pv and (pk not in player or not player[pk]):
                                    player[pk] = pv
            except Exception:
                pass

    name = player.get("name", "Unknown")
    race = player.get("race", "Unknown")
    gender = player.get("gender", "Unknown")
    class_name = player.get("class", "Unknown")
    level = player.get("level", 1)
    
    health = player.get("health", {})
    magicka = player.get("magicka", {})
    fatigue = player.get("fatigue", {})
    hp_cur, hp_base = health.get("current", 0), health.get("base", 0)
    mp_cur, mp_base = magicka.get("current", 0), magicka.get("base", 0)
    fp_cur, fp_base = fatigue.get("current", 0), fatigue.get("base", 0)
    
    attributes = player.get("attributes", {})
    skills = player.get("skills", {})
    bounty = player.get("bounty", 0)
    reputation = player.get("reputation", 0)
    
    factions = player.get("factions", [])
    faction_str = ", ".join(factions) if factions else "None"
    
    eq_gear = player.get("equipped_gear", [])
    inv = player.get("inventory", [])
    
    ss = []
    try:
        loc_info = landmass.resolve(dict(player, cell=player.get("cell") or cell))
        ss.append(landmass.location_block(loc_info))
        ss.append("")
    except Exception as e:
        print(f"[LANDMASS] Failed to resolve location: {e}")
    ss.append("### Player Status & Stats")
    ss.append(f"- **Name**: {name} | **Race**: {race} | **Gender**: {gender} | **Level**: {level}")
    ss.append(f"- **Class**: {class_name}")
    ss.append(f"- **Vitals**: Health {hp_cur}/{hp_base} | Magicka {mp_cur}/{mp_base} | Fatigue {fp_cur}/{fp_base}")
    
    if attributes:
        attr_parts = [f"{k}: {v}" for k, v in attributes.items()]
        ss.append(f"- **Attributes**: {', '.join(attr_parts)}")
    
    ss.append(f"- **Bounty**: {bounty} septims | **Reputation**: {reputation}")
    
    if faction_str != "None":
        ss.append(f"- **Factions**: {faction_str}")
        

    if skills:
        skill_parts = [f"{k}: {v}" for k, v in skills.items()]
        ss.append(f"- **Skills**: {', '.join(skill_parts)}")
        
    ss.append("\n### Equipped Gear")
    if eq_gear:
        for item in eq_gear:
            if isinstance(item, dict):
                item_name = item.get("name", "Unnamed")
                item_id = item.get("id")
                gear_str = f"- {item_name}"
                if item_id:
                    gear_str += f" (ID: {item_id})"
                ss.append(gear_str)
            else:
                ss.append(f"- {item}")
    else:
        ss.append("- None")
        
    ss.append("\n### Player Inventory")
    if inv:
        for item in inv:
            if isinstance(item, dict):
                item_name = item.get("name", "Unnamed")
                item_id = item.get("id")
                count = item.get("count", 1)
                inv_str = f"- {item_name} x{count}"
                if item_id:
                    inv_str += f" (ID: {item_id})"
                ss.append(inv_str)
            else:
                ss.append(f"- {item}")
    else:
        ss.append("- Empty")
        
    target = data.get("target")
    if target and target != "null" and isinstance(target, dict):
        t_id = target.get("id")
        if t_id and t_id != "null":
            t_name = target.get("name", "Unknown")
            t_type = target.get("type", "NPC")
            t_race = target.get("race", "Unknown")
            t_gender = target.get("gender", "Unknown")
            t_class = target.get("class", "Unknown")
            t_level = target.get("level", 1)
            t_inv = target.get("inventory", [])
            t_faction = target.get("faction", "None")
            t_disp = target.get("disposition")
            
            t_attitude = "Neutral / Indifferent"
            if t_disp is not None:
                try:
                    disp = int(t_disp)
                    if disp <= 20: t_attitude = "Hostile / Despises you"
                    elif disp <= 40: t_attitude = "Guarded / Cold"
                    elif disp <= 60: t_attitude = "Neutral / Indifferent"
                    elif disp <= 80: t_attitude = "Friendly / Warm"
                    else: t_attitude = "Adoring / Extremely helpful"
                except ValueError:
                    pass
                    
            ss.append("\n### Target Status & Stats")
            ss.append(f"- **Name**: {t_name} | **Type**: {t_type} | **Race**: {t_race} | **Gender**: {t_gender}")
            ss.append(f"- **Class**: {t_class} | **Level**: {t_level}")
            if t_disp is not None:
                ss.append(f"- **Disposition**: {t_disp} ({t_attitude})")
            if t_faction and t_faction not in ("None", "null"):
                ss.append(f"- **Faction**: {t_faction}")
                
            ss.append("\n### Target Inventory")
            if t_inv:
                for item in t_inv:
                    if isinstance(item, dict):
                        item_name = item.get("name", "Unnamed")
                        item_id = item.get("id")
                        count = item.get("count", 1)
                        t_inv_str = f"- {item_name} x{count}"
                        if item_id:
                            t_inv_str += f" (ID: {item_id})"
                        ss.append(t_inv_str)
            else:
                ss.append("- Empty")
                
    nearby = data.get("nearby_entities", [])
    corpses = [e for e in nearby if "Corpse" in e.get("type", "") or "Dead" in e.get("type", "")]
    if corpses:
        ss.append("\n### DEAD BODIES & CORPSES PRESENT IN CELL")
        for c in corpses:
            c_name = c.get("name", "Unnamed Corpse")
            c_dist = c.get("distance", 9999)
            ss.append(f"- **DEAD BODY / CORPSE**: {c_name} (Type: {c.get('type')}, Distance: {c_dist} units)")

    ss.append("\n### Surrounding Cell Contents")
    ss.append(f"- **Active Cell**: {cell}")
    if nearby:
        ss.append("| Type | ID | Name | Proximity / Distance |")
        ss.append("| --- | --- | --- | --- |")
        for ent in nearby:
            e_type = ent.get("type", "Other")
            e_id = ent.get("id", "Unknown")
            e_name = ent.get("name", "Unnamed")
            dist = ent.get("distance", 9999)
            if dist <= 350:
                prox_tag = f"CLOSE BY ({dist} units - right beside player)"
            else:
                prox_tag = f"DISTANT / NEARBY IN CELL ({dist} units - in distance)"
            ss.append(f"| {e_type} | {e_id} | {e_name} | {prox_tag} |")
    else:
        ss.append("- No surrounding entities detected in cell.")
        
    return "\n".join(ss)

def tokenize(text):
    if not text:
        return []
    words = re.findall(r'\b\w{3,}\b', text.lower())
    stop_words = {'the', 'and', 'you', 'was', 'for', 'with', 'that', 'this', 'from', 'they', 'have'}
    return [w for w in words if w not in stop_words]

def search_game_database(world_id, prompt):
    keywords = tokenize(prompt)[:30]  # Cap to prevent SQLite expression tree overflow
    if not keywords:
        return []
    db = open_db(world_id)
    if not db:
        return []
    
    cursor = db.cursor()
    query_parts = []
    params = []
    for kw in keywords:
        query_parts.append("name LIKE ?")
        params.append(f"%{kw}%")
        
    if not query_parts:
        db.close()
        return []
        
    sql = "SELECT name, id, type FROM game_database WHERE " + " OR ".join(query_parts) + " LIMIT 50"
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"[AI RAG ERROR] Game DB SQL error: {e}")
        db.close()
        return []
        
    ranked = []
    for name, entity_id, entity_type in rows:
        tokens = tokenize(name)
        score = sum(1 for kw in keywords if kw in tokens)
        if score > 0:
            ranked.append(((entity_type, name, entity_id), score))
            
    ranked.sort(key=lambda x: x[1], reverse=True)
    results = []
    for (entity_type, name, entity_id), score in ranked[:5]:
        results.append(f"{entity_type}: \"{name}\" (ID: {entity_id})")
    db.close()
    return results

def search_custom_lore(world_id, prompt):
    keywords = tokenize(prompt)[:30]  # Cap to prevent SQLite expression tree overflow
    if not keywords:
        return []
    db = open_db(world_id)
    if not db:
        return []
        
    cursor = db.cursor()
    query_parts = []
    params = []
    for kw in keywords:
        query_parts.append("name LIKE ? OR lore LIKE ?")
        params.extend([f"%{kw}%", f"%{kw}%"])
        
    if not query_parts:
        db.close()
        return []
        
    sql = "SELECT name, lore FROM custom_lore WHERE " + " OR ".join(query_parts) + " LIMIT 50"
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"[AI RAG ERROR] Custom lore SQL error: {e}")
        db.close()
        return []
        
    ranked = []
    for name, lore in rows:
        tokens = tokenize(name) + tokenize(lore)
        score = sum(1 for kw in keywords if kw in tokens)
        if score > 0:
            ranked.append(((name, lore), score))
            
    ranked.sort(key=lambda x: x[1], reverse=True)
    results = []
    for (name, lore), score in ranked[:5]:
        results.append(f"{name}: {lore}")
    db.close()
    return results

def retrieve_relevant_narrative(prompt, permanent_entries, top_n=3):
    prompt_tokens = tokenize(prompt)
    if not prompt_tokens or not permanent_entries:
        return []
    ranked = []
    for entry in permanent_entries:
        entry_tokens = tokenize(entry)
        score = sum(1 for pt in prompt_tokens if pt in entry_tokens)
        if score > 0:
            ranked.append((entry, score))
    if not ranked:
        return []
    ranked.sort(key=lambda x: x[1], reverse=True)
    res = []
    for entry, score in ranked[:top_n]:
        res.append(entry)
    return res

def extract_json_from_text(text):
    if not text:
        return None
    clean = text.strip()
    try:
        return json.loads(clean)
    except Exception:
        pass
    md_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', clean, re.IGNORECASE)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except Exception:
            pass
    first_brace = clean.find('{')
    last_brace = clean.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(clean[first_brace:last_brace + 1])
        except Exception:
            pass
    first_brack = clean.find('[')
    last_brack = clean.rfind(']')
    if first_brack != -1 and last_brack > first_brack:
        try:
            return json.loads(clean[first_brack:last_brack + 1])
        except Exception:
            pass

    # OpenMW timestamp line-wrap and key quote repair fallback
    try:
        repaired = re.sub(r'\"?([a-zA-Z0-9_]+)\"?\s*:\s*\[\d{2}:\d{2}:\d{2}\.\d{3}\s*[\*\w]?\]\s*(-?\d+)', r'"\1": \2', clean)
        repaired = re.sub(r'\[\d{2}:\d{2}:\d{2}\.\d{3}\s*[\*\w]?\]', '', repaired)
        fb = repaired.find('{')
        lb = repaired.rfind('}')
        if fb != -1 and lb > fb:
            return json.loads(repaired[fb:lb + 1])
    except Exception:
        pass

    return None


def call_gemini_api(api_key, model, system_instruction, conversation_history, max_tokens=600, fallback_model="gemini-3.1-flash-lite-preview", response_mime_type=None):
    clean_model = model.replace("models/", "") if model else model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
    payload = {}
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
    contents = []
    if not conversation_history:
        contents.append({
            "role": "user",
            "parts": [{"text": "Greet the player."}]
        })
    else:
        for msg in conversation_history:
            contents.append({
                "role": msg.get("role", "user"),
                "parts": [{"text": msg.get("text", "")}]
            })
    payload["contents"] = contents
    payload["generationConfig"] = {
        "maxOutputTokens": max_tokens,
        "temperature": 0.7
    }
    if response_mime_type:
        payload["generationConfig"]["responseMimeType"] = response_mime_type

    payload["safetySettings"] = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    headers = {"Content-Type": "application/json"}
    
    max_retries = 3
    retry_delay = 2.0
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30.0) as response:
                res_data = response.read().decode('utf-8')
                res_json = json.loads(res_data)
                
                candidates = res_json.get("candidates")
                if not candidates:
                    print(f"[AI CORE WARNING] call_gemini_api: No candidates in response! Response JSON: {res_json}")
                    break
                content = candidates[0].get("content")
                if not content:
                    print(f"[AI CORE WARNING] call_gemini_api: Candidate has no content! finishReason: {candidates[0].get('finishReason')}")
                    break
                parts = content.get("parts")
                if not parts:
                    print(f"[AI CORE WARNING] call_gemini_api: Content parts are empty!")
                    break
                    
                # Collect dialogue while filtering out any internal thought tokens
                text_parts = [p.get("text", "") for p in parts if not p.get("thought") and p.get("text")]
                if not text_parts and parts:
                    text_parts = [parts[0].get("text", "")]
                text = "".join(text_parts).strip()
                return text
        except urllib.error.HTTPError as e:
            if e.code in [429, 500, 502, 503, 504] and attempt < max_retries - 1:
                base_delay = 4.0 if e.code == 429 else retry_delay
                sleep_time = base_delay * (2 ** attempt)
                print(f"[Gemini API WARNING] HTTP {e.code} received for model '{clean_model}'. Retrying in {sleep_time:.2f}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(sleep_time)
                continue
            print(f"[Gemini API ERROR] HTTP error on model '{clean_model}': {e}")
            break
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                sleep_time = retry_delay * (2 ** attempt)
                print(f"[Gemini API WARNING] Connection failed for '{clean_model}': {e}. Retrying in {sleep_time:.2f}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(sleep_time)
                continue
            print(f"[Gemini API ERROR] Connection failed permanently on '{clean_model}': {e}")
            break
        except Exception as e:
            print(f"[Gemini API ERROR] Request failed on '{clean_model}': {e}")
            import traceback
            traceback.print_exc()
            break

    # Failover execution to backup model if primary or lightweight model fails
    if fallback_model and fallback_model != clean_model:
        print(f"[AI CORE FAILOVER] Model '{clean_model}' failed/rate-limited. Failing over to backup model '{fallback_model}'...")
        next_fallback = "gemini-3.1-flash-lite-preview" if fallback_model == "gemini-3.5-flash-lite" else None
        return call_gemini_api(api_key, fallback_model, system_instruction, conversation_history, max_tokens=max_tokens, fallback_model=next_fallback, response_mime_type=response_mime_type)
        
    return ""

def call_gemini_single_prompt(api_key, model, prompt, max_tokens=400, system_instruction="You are the Morrowind Master Mind chronicler, maintaining strict lore accuracy, dry authentic Third Era wit, and campaign chronicle consistency.", response_mime_type=None):
    history = [{"role": "user", "text": prompt}]
    return call_gemini_api(api_key, model, system_instruction, history, max_tokens=max_tokens, response_mime_type=response_mime_type)

def clean_utf8_to_ansi(text):
    if not text:
        return ""
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": " - ",
        "\u2013": "-",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('ascii', errors='ignore').decode('ascii')

def strip_memory_markdown(text):
    """Strip markdown formatting from a memory entry so it stores as clean readable text."""
    if not text:
        return text
    import re
    # Remove horizontal rules
    text = re.sub(r'\n\s*\*{3,}\s*\n', '\n', text)
    text = re.sub(r'\n\s*-{3,}\s*\n', '\n', text)
    # Remove markdown headers (## Header, ### Header etc.)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic markers (**text** -> text, *text* -> text)
    text = re.sub(r'\*{2,3}(.*?)\*{2,3}', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # Remove leading bullet dashes that are part of markdown lists
    text = re.sub(r'^\*\s+', '', text, flags=re.MULTILINE)
    # Collapse excessive blank lines to a single newline
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def load_target_stats_from_env(world_id, target_id):
    world_dir = get_world_dir(world_id)
    path = os.path.join(world_dir, "environment.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            target = data.get("target")
            if target and target != "null" and isinstance(target, dict):
                t_id = target.get("id")
                if t_id and t_id.lower() == target_id.lower():
                    return target
    except Exception as e:
        print(f"[ERROR] load_target_stats_from_env error: {e}")
    return None

def get_or_create_personality(api_key, model_name, world_id, npc_id, npc_name, entity_type):
    if npc_id == "Narrator" or npc_id == "Eavesdrop_Session":
        return None, None
        
    db = open_db(world_id)
    if not db:
        return None, None
        
    cursor = db.cursor()
    try:
        cursor.execute("SELECT personality_summary, long_term_goals FROM character_personality WHERE world_id = ? AND npc_id = ? AND initialized = 1", (world_id, npc_id))
        row = cursor.fetchone()
        if row:
            db.close()
            return row[0], row[1]
    except Exception as e:
        print(f"[AI CORE ERROR] Failed to query personality from DB: {e}")
        db.close()
        return None, None
        
    db.close()
    print(f"[AI CORE HUB] Initializing persistent sticky personality for NPC '{npc_name}' (ID: {npc_id})")
    
    target_stats = load_target_stats_from_env(world_id, npc_id)
    stats_desc = []
    if target_stats:
        stats_desc.append(f"Name: {target_stats.get('name', npc_name)}")
        stats_desc.append(f"Type: {target_stats.get('type', entity_type)}")
        stats_desc.append(f"Race: {target_stats.get('race', 'Unknown')}")
        stats_desc.append(f"Gender: {target_stats.get('gender', 'Unknown')}")
        stats_desc.append(f"Class: {target_stats.get('class', 'Unknown')}")
        stats_desc.append(f"Level: {target_stats.get('level', 1)}")
        stats_desc.append(f"Faction: {target_stats.get('faction', 'None')}")
        disp = target_stats.get("disposition")
        if disp is not None:
            stats_desc.append(f"Disposition: {disp}")
    else:
        stats_desc.append(f"Name: {npc_name}")
        stats_desc.append(f"Type: {entity_type}")
    try:
        stats_desc.append(landmass.personality_line(landmass.resolve_world(get_world_dir(world_id))))
    except Exception as e:
        print(f"[LANDMASS] Failed to add home location to personality: {e}")
        
    prompt = prompt_generator.build_personality_init_prompt(stats_desc)
    prompt_generator.write_prompt_logic_info(world_id, f"Initialize NPC Personality: {npc_name}", None, prompt)
    
    personality_summary = "A generic local of this land."
    long_term_goals = "Wants to survive in this harsh land."
    
    raw_reply = call_gemini_single_prompt(api_key, model_name, prompt, max_tokens=400, system_instruction="You are the Morrowind Master Mind personality engine. Return only a valid raw JSON object.", response_mime_type="application/json")
    if raw_reply:
        p_data = extract_json_from_text(raw_reply)
        if p_data and isinstance(p_data, dict):
            personality_summary = p_data.get("personality_summary", personality_summary)
            long_term_goals = p_data.get("long_term_goals", long_term_goals)
        else:
            print(f"[AI CORE ERROR] Failed to parse personality JSON. Raw response: {raw_reply}")
            
    db = open_db(world_id)
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("""INSERT OR REPLACE INTO character_personality 
                             (world_id, npc_id, personality_summary, long_term_goals, initialized) 
                             VALUES (?, ?, ?, ?, 1)""", 
                           (world_id, npc_id, personality_summary, long_term_goals))
            db.commit()
            print(f"[AI CORE HUB] Cached personality for '{npc_name}' successfully.")
        except Exception as ex:
            print(f"[AI CORE ERROR] Failed to save personality to SQLite: {ex}")
        db.close()
        
    return personality_summary, long_term_goals

def handle_action_compression(api_key, model_name, world_id, act, custom_sys_prompt):
    if len(act.get("short_term", [])) >= 50:

        p_name, p_race, p_gender, p_class, p_factions = load_player_status_from_env_json(world_id)
        env_context = format_environment_context(world_id)
        
        quest_log = load_quest_log(world_id)
        narrator_mem = load_memory(world_id, "Narrator")
        state = load_dm_state(world_id)
        dm_title = state.get("archetype", "The Vvardenfell Chronicler")

        prompt = prompt_generator.build_unified_action_compression_prompt(
            p_name, p_race, p_gender, p_class, p_factions, env_context, act.get("short_term", []),
            dm_title, state, quest_log.get("long_term_summary"), quest_log.get("intermediate_chunks"),
            narrator_mem.get("long_term_summary"), narrator_mem.get("intermediate_chunks")
        )
        prompt_generator.write_prompt_logic_info(world_id, "Unified Action Compression & DM Update", None, prompt)
        
        raw_reply = call_gemini_single_prompt(api_key, model_name, prompt, max_tokens=750, system_instruction="You are the master DM engine and campaign record-keeper for Morrowind. Output only a valid raw JSON object.", response_mime_type="application/json")
        if raw_reply:
            u_data = extract_json_from_text(raw_reply)
            if u_data and isinstance(u_data, dict):
                # 1. Action Chunk Summary
                chunk_summary = u_data.get("chunk_summary", "")
                if chunk_summary:
                    act["intermediate_chunks"].append(chunk_summary)
                    
                # 2. DM Persona Evolution
                new_archetype = u_data.get("dm_archetype")
                new_mood = u_data.get("dm_mood")
                new_notes = u_data.get("dm_notes")
                if new_archetype or new_mood or new_notes:
                    if new_archetype:
                        state["archetype"] = new_archetype
                    if new_mood:
                        state["mood"] = new_mood
                    if new_notes:
                        state["notes"] = new_notes
                    save_dm_state(world_id, state)
                    
                # 3. Quest Journal Entry
                journal_entry = u_data.get("journal_entry", "")
                if journal_entry:
                    clean_entry = strip_memory_markdown(clean_utf8_to_ansi(journal_entry))
                    if clean_entry:
                        quest_log["short_term"].append(f"Journal: {clean_entry}")
                        compress_quest_log(api_key, model_name, world_id, quest_log)
                        save_quest_log(world_id, quest_log)
                        print(f"[AI CORE JOURNAL] Recorded custom quest path: {clean_entry}")
                        
                # 4. DM Internal Campaign Thought
                dm_thought = u_data.get("dm_thought", "")
                if dm_thought:
                    clean_thought = strip_memory_markdown(clean_utf8_to_ansi(dm_thought))
                    if clean_thought:
                        narrator_mem["short_term"].append({"role": "model", "text": f"DM Chronicle Thought: {clean_thought}"})
                        handle_compression(api_key, model_name, world_id, "Narrator", narrator_mem, True)
                        save_memory(world_id, "Narrator", narrator_mem)
                        print(f"[AI CORE NARRATOR] Recorded DM internal thought: {clean_thought}")
            else:
                print(f"[AI CORE ERROR] Failed to parse unified action compression JSON. Raw: {raw_reply}")

        act["short_term"] = []
        
        # Trigger scene description for the player
        trigger_scribe_auto_narration(api_key, model_name, world_id, custom_sys_prompt)
            
        if len(act["intermediate_chunks"]) >= 40:

            prompt_m = prompt_generator.build_mega_action_compression_prompt(p_name, p_race, p_gender, p_class, p_factions, act.get('long_term_summary', ''), act["intermediate_chunks"])
            prompt_generator.write_prompt_logic_info(world_id, "Mega Action Log Compression", None, prompt_m)
            mega_summary = call_gemini_single_prompt(api_key, model_name, prompt_m)
            if mega_summary:
                act["long_term_summary"] = mega_summary
            act["intermediate_chunks"] = []

def handle_compression(api_key, model_name, world_id, entity_id, mem, is_narrator):
    short_term_threshold = 40
    intermediate_threshold = 40
    
    if len(mem.get("short_term", [])) >= short_term_threshold:

        prompt = prompt_generator.build_short_term_compression_prompt(entity_id, is_narrator, mem["short_term"])
        prompt_generator.write_prompt_logic_info(world_id, f"Short-term Memory Compression: {entity_id}", None, prompt)
        chunk_summary = call_gemini_single_prompt(api_key, model_name, prompt)
        if chunk_summary:

            mem["intermediate_chunks"].append(chunk_summary)
            
        if is_narrator:
            mem["short_term"] = []
        else:
            last_turn = mem["short_term"][-1] if mem["short_term"] else None
            mem["short_term"] = [last_turn] if last_turn else []
            
        if len(mem["intermediate_chunks"]) >= intermediate_threshold:

            if is_narrator:
                prompt_p = prompt_generator.build_permanent_history_prompt(mem["intermediate_chunks"])
                prompt_generator.write_prompt_logic_info(world_id, "Permanent Historical Entries Generation", None, prompt_p)
                new_entries_str = call_gemini_single_prompt(api_key, model_name, prompt_p)
                if new_entries_str:
                    for line in new_entries_str.split("\n"):
                        line = line.strip()
                        if line.startswith("- "):
                            line = line[2:].strip()
                        if line:
                            mem["permanent_entries"].append(line)
                    if len(mem["permanent_entries"]) > 150:
                        mem["permanent_entries"] = mem["permanent_entries"][-150:]
            else:
                if mem.get("long_term_summary"):
                    prompt_d = prompt_generator.build_distill_relationship_prompt(entity_id, mem['long_term_summary'], mem['intermediate_chunks'])
                    prompt_generator.write_prompt_logic_info(world_id, f"Relationship Fact Distillation: {entity_id}", None, prompt_d)
                    distilled = call_gemini_single_prompt(api_key, model_name, prompt_d)
                    if distilled:
                        for line in distilled.split("\n"):
                            line = line.strip()
                            if line.startswith("- "):
                                line = line[2:].strip()
                            if line:
                                mem["permanent_entries"].append(line)
                        if len(mem["permanent_entries"]) > 100:
                            mem["permanent_entries"] = mem["permanent_entries"][-100:]
                            
                prompt_r = prompt_generator.build_mega_relationship_prompt(entity_id, mem.get('long_term_summary', ''), mem["intermediate_chunks"])
                prompt_generator.write_prompt_logic_info(world_id, f"Mega Relationship Summary: {entity_id}", None, prompt_r)
                mega_summary = call_gemini_single_prompt(api_key, model_name, prompt_r)
                if mega_summary:
                    mem["long_term_summary"] = mega_summary
            mem["intermediate_chunks"] = []

# Prompt functions moved to prompt_generator.py

def trigger_scribe_auto_narration(api_key, model_name, world_id, custom_sys_prompt):
    print("[AI SCRIBE AUTO] Triggering auto-narration at 20 actions milestone...")
    narrator_mem = load_memory(world_id, "Narrator")
    action_log = load_action_log(world_id)
    quest_log = load_quest_log(world_id)
    
    configs = prompt_generator.load_customization_files()
    dm_state = load_dm_state(world_id)
    try:
        player_status = load_player_status_from_env_json(world_id)
    except Exception:
        player_status = ("the player", "outlander", "adventurer", "none", "none")
    dm_prompt, dm_title = prompt_generator.get_dynamic_dm_prompt(world_id, dm_state, player_status, configs)
    print(f"[AI SCRIBE AUTO] Evolving DM Narrator personality selected: {dm_title}")
    
    env_context = format_environment_context(world_id)
    
    recent_events = "The player has performed several actions recently:\n"
    sz = len(action_log.get("intermediate_chunks", []))
    if sz >= 2:
        recent_events += f"- {action_log['intermediate_chunks'][-2]}\n"
        recent_events += f"- {action_log['intermediate_chunks'][-1]}\n"
    elif sz == 1:
        recent_events += f"- {action_log['intermediate_chunks'][0]}\n"
        
    narrator_mem["short_term"].append({"role": "user", "text": recent_events + "\nWrite the next entry in the chronicle based on these events and the environment."})
    
    # Search game database and custom lore for scribe context
    search_query = f"{env_context} {' '.join(action_log.get('short_term', []))}"
    db_ref_entries = search_game_database(world_id, search_query)
    custom_lore_entries = search_custom_lore(world_id, search_query)
    
    sys_prompt_str = prompt_generator.build_auto_narration_prompt(dm_prompt, custom_sys_prompt, quest_log, env_context, action_log, db_ref_entries, custom_lore_entries, configs, location=prompt_generator._location_for_world(world_id))
    
    # Write prompt logic info
    prompt_generator.write_prompt_logic_info(world_id, sys_prompt_str, narrator_mem["short_term"], "Write the next entry in the chronicle based on these events and the environment.")
    
    print("[AI SCRIBE AUTO] Querying Gemini...")
    reply = call_gemini_api(api_key, model_name, sys_prompt_str, narrator_mem["short_term"])
    reply = clean_utf8_to_ansi(reply)
    
    # Remove the temporary user prompt entry to keep narrator memory clean
    if narrator_mem["short_term"]:
        narrator_mem["short_term"].pop()
        
    if not reply:
        return
        
    print(f"[AI SCRIBE AUTO] Narrative generated: {reply}")
    clean_reply = strip_memory_markdown(reply.strip())
    
    narrator_mem["short_term"].append({"role": "model", "text": clean_reply})
    handle_compression(api_key, model_name, world_id, "Narrator", narrator_mem, True)
    save_memory(world_id, "Narrator", narrator_mem)

def read_payload_from_socket(conn):
    length_buf = b""
    while True:
        chunk = conn.recv(1)
        if not chunk:
            return None
        if chunk == b'\n':
            break
        length_buf += chunk
        if len(length_buf) > 10:
            return None
            
    try:
        length = int(length_buf.decode('utf-8').strip())
    except ValueError:
        return None
        
    payload = b""
    while len(payload) < length:
        chunk = conn.recv(length - len(payload))
        if not chunk:
            return None
        payload += chunk
    return payload.decode('utf-8')

def send_response_to_socket(conn, response_str):
    try:
        response_bytes = response_str.encode('utf-8')
        header = f"{len(response_bytes)}\n".encode('utf-8')
        conn.sendall(header + response_bytes)
    except Exception as e:
        print(f"[AI CORE ERROR] Failed to send response: {e}")

def handle_listen_to_conversation(api_key, model_name, world_id, request_data):
    npc_names = []
    npc_ids = []
    participant_sheets = []
    
    participants = request_data.get("participants", [])
    for p_obj in participants:
        p_id = p_obj.get("id")
        name = p_obj.get("name")
        p_type = p_obj.get("type", "NPC")
        race = p_obj.get("race", "Unknown")
        gender = p_obj.get("gender", "Unknown")
        class_name = p_obj.get("class", "Unknown")
        faction = p_obj.get("faction", "None")
        level = p_obj.get("level", 1)
        
        if p_id:
            npc_ids.append(p_id)
            npc_names.append(name)
            p_mem = load_memory(world_id, p_id)
            sheet = f"### Character Sheet & Memory: {name} ({p_type})\n- **Race**: {race} | **Gender**: {gender} | **Class**: {class_name} | **Level**: {level}\n"
            if faction and faction != "None":
                sheet += f"- **Faction**: {faction}\n"
            if p_mem.get("short_term"):
                sheet += "- **Recent Personal Memories & Interactions**:\n"
                for m in p_mem["short_term"][-6:]:
                    if isinstance(m, dict):
                        sheet += f"  - {m.get('role', 'memory')}: {m.get('text', '')}\n"
                    else:
                        sheet += f"  - {m}\n"
            if p_mem.get("long_term_summary"):
                sheet += f"- **Permanent Memory & History**: {p_mem['long_term_summary']}\n"
            participant_sheets.append(sheet)
            
    is_continue = request_data.get("is_continue") == "true"
    custom_sys_prompt = request_data.get("system_prompt", "")

    
    narrator_mem = load_memory(world_id, "Narrator")
    action_log = load_action_log(world_id)
    quest_log = load_quest_log(world_id)
    listen_mem = load_memory(world_id, "Listen_Session")
    
    if not is_continue:
        listen_mem["short_term"] = []
    listen_mem["short_term"].append({"role": "user", "text": "Continue the scene natively. Do not repeat previous dialogue or actions. Advance the moment logically."})
    
    configs = prompt_generator.load_customization_files()
    env_context = format_environment_context(world_id)
    
    # Search game database and custom lore for conversation context
    search_query = f"{' '.join(npc_names)} {env_context}"
    db_ref_entries = search_game_database(world_id, search_query)
    custom_lore_entries = search_custom_lore(world_id, search_query)
    
    sys_prompt_str = prompt_generator.build_listen_prompt(
        npc_names=npc_names,
        participant_sheets=participant_sheets,
        is_continue=is_continue,
        custom_sys_prompt=custom_sys_prompt,
        action_log=action_log,
        quest_log=quest_log,
        env_context=env_context,
        db_ref_entries=db_ref_entries,
        custom_lore_entries=custom_lore_entries,
        world_id=world_id,
        configs=configs
    )

    reply = call_gemini_api(api_key, model_name, sys_prompt_str, listen_mem["short_term"], max_tokens=800)
    reply = clean_utf8_to_ansi(reply)
    
    if not reply:
        reply = "*(The voices fade into whispers. You hear nothing.)*"
        

    listen_mem["short_term"].append({"role": "model", "text": reply})
    save_memory(world_id, "Listen_Session", listen_mem)
    
    # Log the conversation into the memory of each participating NPC
    for p_obj in participants:
        p_id = p_obj.get("id")
        p_name = p_obj.get("name")
        if p_id:
            try:
                npc_mem = load_memory(world_id, p_id)
                npc_mem["short_term"].append({"role": "user", "text": f"Overheard conversing with {', '.join(npc_names)}:\n{reply}"})
                handle_compression(api_key, model_name, world_id, p_name, npc_mem, False)
                save_memory(world_id, p_id, npc_mem)
            except Exception as e:
                print(f"[AI CORE ERROR] Failed to save conversation log to participant {p_id} memory: {e}")
                
    return json.dumps({"reply": reply})

def clean_dialogue_text(text, npc_name, world_id):
    if not text:
        return ""
    
    # 1. Remove @ and # (topic markers)
    text = text.replace('@', '').replace('#', '')
    
    # 2. Remove standalone case-insensitive "link" or "[link]" or "link "
    text = re.sub(r'\b[Ll]ink\b', '', text)
    text = text.replace('[]', '')
    
    # 3. Replace player placeholders
    try:
        p_name, p_race, _, p_class, p_faction = load_player_status_from_env_json(world_id)
        if not p_faction or p_faction == "None":
            p_faction = "No faction"
    except Exception:
        p_name, p_race, p_class, p_faction = "the player", "outlander", "adventurer", "none"
        
    text = re.sub(r'%[Pp]c[Nn]ame\b', p_name, text)
    text = re.sub(r'%[Pp]c[Cc]lass\b', p_class, text)
    text = re.sub(r'%[Pp]c[Rr]ace\b', p_race, text)
    text = re.sub(r'%[Pp]c[Ff]action\b', p_faction, text)
    
    # 4. Replace NPC placeholders
    text = re.sub(r'%[Nn]ame\b', npc_name, text)
    text = re.sub(r'%[Cc]lass\b', "commoner", text)
    text = re.sub(r'%[Rr]ace\b', "native", text)
    text = re.sub(r'%[Ff]action\b', "faction", text)
    text = re.sub(r'%[Rr]ank\b', "rank", text)
    
    # 5. Clean up spacing and trailing punctuation
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text

def format_compact_json(obj, indent=2, level=0):
    """
    Formats JSON data with clean, compact inline formatting for short dicts and array items,
    reducing vertical line height dramatically while preserving human readability.
    """
    if isinstance(obj, (int, float, bool, type(None))):
        return json.dumps(obj)
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)

    ind = " " * (indent * level)
    ind_next = " " * (indent * (level + 1))

    if isinstance(obj, dict):
        if not obj:
            return "{}"
        is_simple = len(obj) <= 4 and all(not isinstance(v, (dict, list)) for v in obj.values())
        if is_simple:
            compact_str = "{ " + ", ".join(f'"{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in obj.items()) + " }"
            if len(compact_str) <= 100:
                return compact_str

        items = []
        for k, v in obj.items():
            val_str = format_compact_json(v, indent, level + 1)
            items.append(f'{ind_next}"{k}": {val_str}')
        return "{\n" + ",\n".join(items) + "\n" + ind + "}"

    if isinstance(obj, list):
        if not obj:
            return "[]"
        items = [format_compact_json(item, indent, level + 1) for item in obj]
        all_inline = all("\n" not in item for item in items)
        if all_inline and sum(len(item) for item in items) <= 80:
            return "[ " + ", ".join(items) + " ]"

        return "[\n" + ",\n".join(f"{ind_next}{item}" for item in items) + "\n" + ind + "]"

    return json.dumps(obj, ensure_ascii=False)

def ensure_world_state_inherited(world_id, parent_world_id=None):
    """
    When a new session snapshot directory (e.g. world_Booska_1785768940) is created,
    automatically inherit/copy base memory state from the parent_world_id baked into the .omwsave file!
    """
    if not world_id:
        return
    target_dir = get_world_dir(world_id)
    os.makedirs(target_dir, exist_ok=True)

    # Check if target directory already has initialized memory state
    if os.path.exists(os.path.join(target_dir, "morrowind_ai.db")) or os.path.exists(os.path.join(target_dir, "quest_log.json")):
        return

    # Extract character prefix (e.g. "world_Booska")
    parts = world_id.split("_")
    if len(parts) < 2:
        return
    player_name = parts[1]
    # Search for candidate source directories to inherit from (parent_world_id from save file first!)
    source_candidates = []
    if parent_world_id and parent_world_id != world_id:
        source_candidates.append(get_world_dir(parent_world_id))

    search_dirs = [
        os.path.join(paths.SCRIPT_DIR, "worlds"),
        os.path.join("Data Files", "MWSE", "config")
    ]
    for sdir in search_dirs:
        if os.path.exists(sdir):
            candidate_dirs = [
                d for d in os.listdir(sdir)
                if os.path.isdir(os.path.join(sdir, d)) and d.startswith(f"world_{player_name}_") and "_session_" not in d and d != world_id
            ]
            candidate_dirs.sort(reverse=True)
            for d in candidate_dirs:
                source_candidates.append(os.path.join(sdir, d))

    source_dir = None
    for cand in source_candidates:
        if os.path.exists(cand) and cand != target_dir:
            source_dir = cand
            break

    if not source_dir or not os.path.exists(source_dir):
        return

    print(f"[AI CORE HUB] Initializing new session snapshot '{world_id}' by inheriting state from '{os.path.basename(source_dir)}'")
    for item in os.listdir(source_dir):
        src_item = os.path.join(source_dir, item)
        dst_item = os.path.join(target_dir, item)
        if os.path.isfile(src_item) and not item.startswith("."):
            if item == "morrowind_ai.db":
                try:
                    src_conn = sqlite3.connect(src_item)
                    dst_conn = sqlite3.connect(dst_item)
                    src_conn.backup(dst_conn)
                    dst_conn.close()
                    src_conn.close()
                except Exception as e:
                    print(f"[AI CORE ERROR] SQLite online backup failed for {item}: {e}")
                    try:
                        shutil.copy2(src_item, dst_item)
                    except Exception as e2:
                        print(f"[AI CORE ERROR] Fallback copy failed for {item}: {e2}")
            else:
                try:
                    shutil.copy2(src_item, dst_item)
                except Exception as e:
                    print(f"[AI CORE ERROR] Failed to copy state file {item}: {e}")
        elif os.path.isdir(src_item) and item in ["NPCs", "Quests"]:
            try:
                shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
            except Exception as e:
                print(f"[AI CORE ERROR] Failed to copy state dir {item}: {e}")

def copy_memory_folder(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dst_dir, item)
        if os.path.isfile(s):
            if item == "morrowind_ai.db":
                try:
                    src_conn = sqlite3.connect(s)
                    dst_conn = sqlite3.connect(d)
                    src_conn.backup(dst_conn)
                    dst_conn.close()
                    src_conn.close()
                except Exception as e:
                    try:
                        shutil.copy2(s, d)
                    except Exception:
                        pass
            elif not item.startswith("."):
                try:
                    shutil.copy2(s, d)
                except Exception:
                    pass
        elif os.path.isdir(s) and item in ["NPCs", "Quests"]:
            try:
                shutil.copytree(s, d, dirs_exist_ok=True)
            except Exception:
                pass

def handle_save_game(frozen_save_id, prev_session_id, new_session_id):
    """
    1. Freeze current session into frozen_save_id and mark .frozen.
    2. Initialize new_session_id from frozen_save_id for continuing gameplay.
    """
    frozen_dir = get_world_dir(frozen_save_id)
    prev_dir   = get_world_dir(prev_session_id) if prev_session_id else None
    new_dir    = get_world_dir(new_session_id) if new_session_id else None

    if prev_dir and os.path.exists(prev_dir):
        print(f"[AI CORE HUB] Freezing save checkpoint '{frozen_save_id}' from active session '{prev_session_id}'")
        copy_memory_folder(prev_dir, frozen_dir)
        try:
            with open(os.path.join(frozen_dir, ".frozen"), "w") as f:
                f.write("locked")
        except Exception:
            pass
    
    if new_dir and os.path.exists(frozen_dir):
        print(f"[AI CORE HUB] Initializing post-save active session '{new_session_id}'")
        copy_memory_folder(frozen_dir, new_dir)

def update_environment_from_payload(world_id, request_data):
    if not world_id:
        return
    world_dir = get_world_dir(world_id)
    if os.path.exists(os.path.join(world_dir, ".frozen")):
        return
    parent_world_id = request_data.get("parent_world_id")
    ensure_world_state_inherited(world_id, parent_world_id)
    os.makedirs(world_dir, exist_ok=True)
    
    env_path    = os.path.join(world_dir, "environment.json")
    player_path = os.path.join(world_dir, "player_tracker.json")
    entity_path = os.path.join(world_dir, "entity_tracker.json")

    # Load existing state to prevent stripping rich data when receiving partial updates
    existing_player = {}
    if os.path.exists(player_path):
        try:
            with open(player_path, 'r', encoding='utf-8') as pf:
                existing_player = json.load(pf)
        except Exception:
            pass

    existing_entity = {}
    if os.path.exists(entity_path):
        try:
            with open(entity_path, 'r', encoding='utf-8') as enf:
                existing_entity = json.load(enf)
        except Exception:
            pass

    existing_env = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as evf:
                existing_env = json.load(evf)
        except Exception:
            pass

    incoming_player  = request_data.get("player_data")
    nearby_entities  = request_data.get("nearby_entities")
    incoming_target  = request_data.get("target_data")

    # 1. Merge & Save player_tracker.json
    final_player = dict(existing_player)
    if isinstance(incoming_player, dict) and incoming_player:
        # If incoming has rich data or existing is empty, merge keys
        for k, v in incoming_player.items():
            if v is not None and v != "" and v != {} and v != []:
                final_player[k] = v
            elif k not in final_player:
                final_player[k] = v

    # Sanitize engine-generated class identifier (e.g. "Generated:0xf2")
    p_class = str(final_player.get("class") or "").strip()
    if p_class.lower().startswith("generated:") or not p_class:
        final_player["class"] = "Adventurer"

    if final_player:
        try:
            with open(player_path, 'w', encoding='utf-8') as pf:
                pf.write(format_compact_json(final_player))
        except Exception as e:
            print(f"[AI CORE ERROR] Failed to write player_tracker.json: {e}")

        factions = final_player.get("factions")
        if factions and isinstance(factions, list):
            db = open_db(world_id)
            if db:
                cursor = db.cursor()
                try:
                    for f in factions:
                        f_id = f.get("id") or f.get("name")
                        f_rank = f.get("rank", 0)
                        if f_id:
                            cursor.execute("""INSERT OR REPLACE INTO player_factions 
                                             (world_id, faction_name, rank_name, is_custom, status)
                                             VALUES (?, ?, ?, 0, 'joined')""",
                                           (world_id, str(f_id), f"Rank {f_rank}"))
                    db.commit()
                except Exception as fe:
                    print(f"[AI CORE ERROR] Failed to update player factions: {fe}")
                db.close()

    # 2. Separate actors from non-actor environment objects
    actors_list = []
    env_objects_list = []
    if nearby_entities is not None and isinstance(nearby_entities, list) and len(nearby_entities) > 0:
        for ent in nearby_entities:
            if isinstance(ent, dict):
                e_type = ent.get("type", "")
                if "NPC" in e_type or "Creature" in e_type or ent.get("stats"):
                    actors_list.append(ent)
                else:
                    env_objects_list.append(ent)
    else:
        # Preserve existing entities if incoming was not provided or empty
        actors_list = existing_entity.get("nearby_actors", [])
        env_objects_list = existing_env.get("cell_objects", [])

    final_target = dict(existing_entity.get("target", {}))
    if isinstance(incoming_target, dict) and incoming_target:
        final_target = incoming_target

    # Save entity_tracker.json
    entity_payload = {
        "target": final_target,
        "nearby_actors": actors_list
    }
    try:
        with open(entity_path, 'w', encoding='utf-8') as ef:
            ef.write(format_compact_json(entity_payload))
    except Exception as e:
        print(f"[AI CORE ERROR] Failed to write entity_tracker.json: {e}")

    # 3. Save Standalone environment.json with unified player, target, and cell_objects
    active_cell = final_player.get("cell") or existing_env.get("active_cell") or "Unknown Cell"
    env_payload = {
        "active_cell": active_cell,
        "player": final_player,
        "target": final_target,
        "cell_objects": env_objects_list
    }
    try:
        with open(env_path, 'w', encoding='utf-8') as evf:
            evf.write(format_compact_json(env_payload))
    except Exception as e:
        print(f"[AI CORE ERROR] Failed to write environment.json: {e}")

def sanitize_world_id(raw_world_id):
    if not raw_world_id or not isinstance(raw_world_id, str):
        return "world_Traveler"
    w = raw_world_id.strip()
    if w in ["", "default", "world_", "world_unknown", "world_default"]:
        return "world_Traveler"
    if not w.startswith("world_"):
        w = "world_" + w
    w = re.sub(r'[^a-zA-Z0-9_]', '_', w)
    return w

def process_request(api_key, model_name, payload):
    try:
        return _process_request_impl(api_key, model_name, payload)
    except Exception as e:
        print(f"[AI CORE ERROR] Exception in process_request: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"reply": "*(An error occurred in the AI backend. Check the console for details.)*"})

def _process_request_impl(api_key, model_name, payload):
    try:
        request_data = json.loads(payload)
    except json.JSONDecodeError:
        print("[AI CORE ERROR] Invalid JSON payload received.")
        return json.dumps({"reply": "*(Arcane static rings in your ears. The message was garbled.)*"})
        
    command = request_data.get("command")
    if command == "shutdown":
        print("[AI CORE HUB] Received remote shutdown request. Exiting...")
        global should_shutdown
        should_shutdown = True
        return json.dumps({"status": "shutdown_ok"})
        
    world_id = sanitize_world_id(request_data.get("world_id", "default"))
    parent_world_id = request_data.get("parent_world_id")
    ensure_world_state_inherited(world_id, parent_world_id)
    custom_sys_prompt = request_data.get("system_prompt", "")
    
    if command == "ping" or command == "test":
        print("[AI CORE HUB] Received ping/test request from client successfully!")
        return json.dumps({"status": "ok", "reply": "Connection test successful! Backend is fully operational."})
    
    if command in ["load_game", "sync_environment"]:
        check_and_import_game_database(world_id)
        check_and_import_custom_lore(world_id)
        update_environment_from_payload(world_id, request_data)
        print(f"[AI CORE HUB] Activated active playing session '{world_id}' (Parent Save: '{parent_world_id}')")
        return json.dumps({"status": "ok"})

    if command in ["save_game", "save_checkpoint"]:
        frozen_save_id  = world_id
        prev_session_id = request_data.get("parent_world_id")
        new_session_id  = request_data.get("new_session_id")
        handle_save_game(frozen_save_id, prev_session_id, new_session_id)
        check_and_import_game_database(frozen_save_id)
        check_and_import_custom_lore(frozen_save_id)
        update_environment_from_payload(frozen_save_id, request_data)
        return json.dumps({"status": "ok"})

    if command == "fork":
        old_world_id = request_data.get("old_world_id", "default")
        new_world_id = request_data.get("new_world_id")

        fork_world_memories(old_world_id, new_world_id)
        return json.dumps({"status": "ok"})
        
    # Route command to loaded addons first
    addon_res = addon_manager.execute_tcp_command(command, world_id, request_data)
    if addon_res is not None:
        return addon_res
        
    check_and_import_game_database(world_id)
    check_and_import_custom_lore(world_id)
    
    if command == "record_event":
        event_text = request_data.get("event")
        update_environment_from_payload(world_id, request_data)

        action_log = load_action_log(world_id)
        action_log["short_term"].append(event_text)
        handle_action_compression(api_key, model_name, world_id, action_log, custom_sys_prompt)
        save_action_log(world_id, action_log)
        return json.dumps({"status": "ok"})
        
    if command == "record_dialogue":
        npc_id = request_data.get("npc_id")
        npc_name = request_data.get("npc", "NPC")
        prompt_text = request_data.get("prompt")
        reply_text = request_data.get("reply")
        
        if not npc_id:
            print("[AI CORE ERROR] record_dialogue missing npc_id!")
            raise ValueError("npc_id is required for record_dialogue")
            
        try:
            update_environment_from_payload(world_id, request_data)
            cleaned_prompt = clean_dialogue_text(prompt_text, npc_name, world_id)
            cleaned_reply = clean_dialogue_text(reply_text, npc_name, world_id)
            
            npc_mem = load_memory(world_id, npc_id)
            if cleaned_prompt:
                npc_mem["short_term"].append({"role": "user", "text": cleaned_prompt})
            if cleaned_reply:
                npc_mem["short_term"].append({"role": "model", "text": cleaned_reply})
            handle_compression(api_key, model_name, world_id, npc_name, npc_mem, False)
            save_memory(world_id, npc_id, npc_mem)
            
            # Record this vanilla conversation in the global Action Log if not already present
            if cleaned_prompt and cleaned_reply:
                action_log = load_action_log(world_id)
                recent_entries = action_log.get("short_term", [])[-5:]
                if not any(cleaned_reply in existing_entry for existing_entry in recent_entries):
                    p_name, _, _, _, _ = load_player_status_from_env_json(world_id)
                    action_text = f"{p_name} spoke with {npc_name} about '{cleaned_prompt}', who responded: \"{cleaned_reply}\""
                    action_log["short_term"].append(action_text)
                    handle_action_compression(api_key, model_name, world_id, action_log, custom_sys_prompt)
                    save_action_log(world_id, action_log)
        except Exception as e:
            print(f"[AI CORE ERROR] Failed to record dialogue to SQLite/Log: {e}")
            import traceback
            traceback.print_exc()
            raise e
            
        return json.dumps({"status": "ok"})
        
    update_environment_from_payload(world_id, request_data)

    if command == "listen_to_conversation":
        return handle_listen_to_conversation(api_key, model_name, world_id, request_data)
        
    prompt = request_data.get("prompt", "")
    npc_name = request_data.get("npc", "Narrator")
    npc_id = request_data.get("npc_id", "Narrator")
    entity_type = request_data.get("entity_type", "NPC")
    is_narrator = (npc_id or "").strip().lower() == "narrator"
    
    npc_mem = load_memory(world_id, npc_id)
    narrator_mem = load_memory(world_id, "Narrator")
    action_log = load_action_log(world_id)
    quest_log = load_quest_log(world_id)
    if not is_narrator:
        effective_prompt = prompt
        prompt_lower = prompt.strip().lower()
        short_mem = npc_mem.get("short_term", [])
        
        p_name, _, _, _, _ = load_player_status_from_env_json(world_id)
        if "handed over " in prompt_lower:
            item_details = prompt.replace("The player handed over ", "").replace(" to you.", "").strip()
            effective_prompt = f"{prompt} [SYSTEM INSTRUCTION: The player just handed over {item_details}! Thank them profusely, express immense gratitude, and react directly in your spoken dialogue.]"
            action_log["short_term"].append(f"{p_name} handed over {item_details} to {npc_name}.")
            save_action_log(world_id, action_log)
        elif "refused to give" in prompt_lower or "refused the request" in prompt_lower:
            item_details = prompt.replace("The player refused to give you ", "").replace(".", "").strip()
            effective_prompt = f"{prompt} [SYSTEM INSTRUCTION: The player just refused to give you {item_details}! Express disappointment, frustration, or sadness in alignment with your personality, reacting directly to their refusal in your spoken dialogue.]"
            action_log["short_term"].append(f"{p_name} refused to give {item_details} to {npc_name}.")
            save_action_log(world_id, action_log)
        elif "accepted " in prompt_lower:
            item_details = prompt.replace("The player accepted ", "").replace(" from you.", "").strip()
            effective_prompt = f"{prompt} [SYSTEM INSTRUCTION: The player ALREADY accepted and received {item_details}! You MUST NOT append any '[GIVE_ITEM: ...]' tag again! Simply express pleasure, warmth, or satisfaction in spoken dialogue without attaching any item tags!]"
            action_log["short_term"].append(f"{npc_name} gave {item_details} to {p_name}.")
            save_action_log(world_id, action_log)
        elif "declined " in prompt_lower:
            item_details = prompt.replace("The player declined ", "").replace(" offered by you.", "").strip()
            effective_prompt = f"{prompt} [SYSTEM INSTRUCTION: The player just declined {item_details}! Express surprise, polite acceptance, or mild disappointment in your spoken dialogue without attaching any item tags.]"
            action_log["short_term"].append(f"{p_name} declined {item_details} offered by {npc_name}.")
            save_action_log(world_id, action_log)
        elif prompt_lower in ["greet the player.", "greet the player"]:
            direct_user_msgs = [
                m for m in short_mem 
                if m.get("role") == "user" and not m.get("text", "").startswith("Overheard conversing")
            ]
            if len(direct_user_msgs) > 0:
                last_user_msg = direct_user_msgs[-1].get("text", "").lower()
                if any(w in last_user_msg for w in ["goodbye", "farewell", "bye", "see you", "leaving"]):
                    effective_prompt = "The player previously said goodbye and has now returned shortly after to speak with you again. Deliver a natural re-engagement greeting acknowledging seeing them again so soon (e.g. 'Back so soon?', 'Did you forget to ask me something, sera?', 'Ah, you're back—what else is on your mind?'). Do NOT give a cold, first-time stranger intro!"
                else:
                    effective_prompt = "The player accidentally exited and re-opened the dialogue window while you were right in the middle of an active conversation! Do NOT greet them, say hello, or ask why they returned. Seamlessly resume the ongoing conversation right where you left off (e.g. 'As I was saying...', 'Where were we?', or directly continuing your previous thought without any greeting)."
            else:
                effective_prompt = prompt
        npc_mem["short_term"].append({"role": "user", "text": effective_prompt})
        handle_compression(api_key, model_name, world_id, npc_name, npc_mem, False)
    
    pers_summary, pers_goals = get_or_create_personality(api_key, model_name, world_id, npc_id, npc_name, entity_type)
    
    configs = prompt_generator.load_customization_files()
    dm_state = load_dm_state(world_id)
    try:
        player_status = load_player_status_from_env_json(world_id)
    except Exception:
        player_status = ("the player", "outlander", "adventurer", "none", "none")
    dm_prompt, dm_title = prompt_generator.get_dynamic_dm_prompt(world_id, dm_state, player_status, configs)

    display_name = get_clean_name_for_display(world_id, npc_id, npc_name)
    env_context = format_environment_context(world_id)
    try:
        loc_info = landmass.resolve_world(get_world_dir(world_id))
    except Exception as e:
        print(f"[LANDMASS] Failed to resolve location: {e}")
        loc_info = None
    sys_prompt_str = prompt_generator.build_npc_prompt(npc_id, npc_name, entity_type, dm_prompt, display_name, pers_summary, pers_goals, custom_sys_prompt, env_context, npc_mem, action_log, quest_log, configs, location=loc_info)
    
    sys_prompt_lines = [sys_prompt_str]
    global_rag = retrieve_relevant_narrative(prompt, narrator_mem.get("permanent_entries", []))
    if global_rag:
        sys_prompt_lines.append("### Relevant Global Knowledge")
        for entry in global_rag:
            sys_prompt_lines.append(f"- {entry}")
        sys_prompt_lines.append("")
        
    if npc_id != "Narrator" and npc_mem.get("permanent_entries"):
        npc_rag = retrieve_relevant_narrative(prompt, npc_mem["permanent_entries"])
        if npc_rag:
            sys_prompt_lines.append("### Deep Memory of This Relationship")
            for entry in npc_rag:
                sys_prompt_lines.append(f"- {entry}")
            sys_prompt_lines.append("")
            
    db_ref_entries = search_game_database(world_id, prompt)
    if db_ref_entries:
        sys_prompt_lines.append("### Game Database Factsheet (ESM/ESP Records Referenced)")
        for db_entry in db_ref_entries:
            sys_prompt_lines.append(f"- {db_entry}")
        sys_prompt_lines.append("")
        
    custom_lore_entries = search_custom_lore(world_id, prompt)
    if custom_lore_entries:
        sys_prompt_lines.append("### Custom Lore & Mod Information")
        for entry in custom_lore_entries:
            sys_prompt_lines.append(f"- {entry}")
        sys_prompt_lines.append("")

    addon_manager.modify_system_prompt(world_id, npc_id, npc_name, prompt, sys_prompt_lines)
    final_sys_prompt = "\n".join(sys_prompt_lines)

    if is_narrator:
        narrator_mem["short_term"].append({"role": "user", "text": prompt + "\nDo NOT repeat previous scene descriptions. Focus on new ambient sights, sounds, wildlife, or subtle NPC movements."})
        prompt_generator.write_prompt_logic_info(world_id, final_sys_prompt, narrator_mem["short_term"], prompt)
        
        reply = call_gemini_api(api_key, model_name, final_sys_prompt, narrator_mem["short_term"])
        reply = clean_utf8_to_ansi(reply)
        
        if not reply:
            reply = "*(The wind shifts through Seyda Neen silently.)*"
            
        clean_reply = reply.strip()
        narrator_mem["short_term"].append({"role": "model", "text": clean_reply})
        handle_compression(api_key, model_name, world_id, "Narrator", narrator_mem, True)
        save_memory(world_id, "Narrator", narrator_mem)
        
        try:
            quest_log = load_quest_log(world_id)
            quest_log["short_term"].append(f"Journal: Scene Description: {clean_reply}")
            compress_quest_log(api_key, model_name, world_id, quest_log)
            save_quest_log(world_id, quest_log)
            print(f"[AI CORE JOURNAL] Logged manual scene description to Quest Journal: {clean_reply}")
        except Exception as ex:
            print(f"[AI CORE ERROR] Failed to log manual scene description to Quest Journal: {ex}")
            
        return json.dumps({"reply": clean_reply})
    else:
        prompt_generator.write_prompt_logic_info(world_id, final_sys_prompt, npc_mem["short_term"], prompt)
        
        reply = call_gemini_api(api_key, model_name, final_sys_prompt, npc_mem["short_term"])
        reply = clean_utf8_to_ansi(reply)
        
        lua_cmds = []
        requested_items = []
        offered_items = []
        if not reply:
            reply = "..."
        else:
            reply, lua_cmds, requested_items, offered_items = addon_manager.process_npc_tags(world_id, reply, npc_name)
            reply = re.sub(r'\[\s*(?:GIVE|REQUEST)_ITEM\s*:\s*[^\]]+\]', '', reply, flags=re.IGNORECASE).strip()
            
        npc_mem["short_term"].append({"role": "model", "text": reply})
        handle_compression(api_key, model_name, world_id, npc_name, npc_mem, False)
        save_memory(world_id, npc_id, npc_mem)
        
        p_name, _, _, _, _ = load_player_status_from_env_json(world_id)
        action_text = f"{p_name} spoke with {npc_name}, who said: \"{reply}\""
        action_log["short_term"].append(action_text)
        handle_action_compression(api_key, model_name, world_id, action_log, custom_sys_prompt)
        save_action_log(world_id, action_log)
        
        display_name = get_clean_name_for_display(world_id, npc_id, npc_name)
        res_dict = {"reply": reply, "display_name": display_name, "commands": lua_cmds}
        if requested_items:
            res_dict["requested_items"] = requested_items
            res_dict["requested_item"] = requested_items[0]
        if offered_items:
            res_dict["offered_items"] = offered_items
        return json.dumps(res_dict)

def handle_socket_connection(conn, addr, api_key, model_name):
    try:
        conn.settimeout(5.0)
        payload = read_payload_from_socket(conn)
        if payload:
            response_json = process_request(api_key, model_name, payload)
            
            # Check if it was a fire-and-forget command
            is_fire_and_forget = False
            try:
                req_data = json.loads(payload)
                is_fire_and_forget = req_data.get("command") in ["fork", "record_event", "record_dialogue"]
            except Exception:
                pass
                
            if not is_fire_and_forget:
                send_response_to_socket(conn, response_json)
    except socket.timeout:
        pass
    except ConnectionResetError:
        pass
    except Exception as e:
        print(f"[AI CORE ERROR] Error handling socket connection from {addr}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def file_ipc_watcher_thread(api_key, model_name):
    global should_shutdown
    
    possible_req_paths = [
        os.path.join("Data Files", "MWSE", "config", "ai_request.json"),
        os.path.expanduser(r"~\Documents\My Games\OpenMW\ai_request.json"),
        os.path.join("OpenMW 0.51.0", "ai_request.json"),
        "ai_request.json"
    ]
    
    last_mtimes = {}
    
    print("[AI CORE HUB] File IPC Watcher Active for OpenMW (scanning all paths).")
    while not should_shutdown:
        try:
            for req_file in possible_req_paths:
                if os.path.exists(req_file):
                    mtime = os.path.getmtime(req_file)
                    if mtime > last_mtimes.get(req_file, 0):
                        last_mtimes[req_file] = mtime
                        time.sleep(0.02)
                        with open(req_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        if content and content.strip():
                            print(f"[AI CORE IPC] Read request payload from OpenMW at {req_file} ({len(content)} bytes)")
                            response_json = process_request(api_key, model_name, content)
                            
                            res_file = req_file.replace("ai_request.json", "ai_response.json")
                            with open(res_file, 'w', encoding='utf-8') as f:
                                f.write(response_json)
                                
                            print(f"[AI CORE LOG STREAM] Wrote AI response for OpenMW.")
        except Exception as e:
            pass
processed_req_ids = set()
processed_req_lock = threading.Lock()

def get_windows_documents_folder():
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            val, _ = winreg.QueryValueEx(key, "Personal")
            winreg.CloseKey(key)
            expanded = os.path.expandvars(val)
            if os.path.exists(expanded):
                return expanded
        except Exception:
            pass
    return None

def start_external_log_bridge(src_path, dst_path):
    global should_shutdown
    def _sync_worker():
        sync_pos = 0
        if os.path.exists(src_path):
            sync_pos = os.path.getsize(src_path)
        while not should_shutdown:
            try:
                if os.path.exists(src_path):
                    s_size = os.path.getsize(src_path)
                    if s_size < sync_pos:
                        sync_pos = 0
                    if s_size > sync_pos:
                        with open(src_path, 'r', encoding='utf-8', errors='ignore') as rf:
                            rf.seek(sync_pos)
                            chunk = rf.read()
                            sync_pos = rf.tell()
                        if chunk:
                            with open(dst_path, 'a', encoding='utf-8') as wf:
                                wf.write(chunk)
                                wf.flush()
            except Exception:
                pass
            time.sleep(0.05)
            
    t = threading.Thread(target=_sync_worker, daemon=True)
    t.start()

def find_openmw_log(quiet=False):
    """Return the openmw.log OpenMW is writing to (newest of the known locations)."""
    candidates = list(paths.openmw_log_candidates())
    # Manual (non-MO2) installs: a log next to the daemon / in an OpenMW subfolder
    candidates += [os.path.join(paths.MOD_ROOT, "OpenMW 0.51.0", "openmw.log")]
    existing = []
    for p in candidates:
        try:
            if os.path.isfile(p):
                existing.append(os.path.normpath(p))
        except OSError:
            pass
    existing = list(dict.fromkeys(existing))
    if existing:
        existing.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        active = existing[0]
        if not quiet:
            size_kb = os.path.getsize(active) / 1024.0
            print(f"[AI CORE DIAGNOSTIC] Detected active OpenMW log: {active} ({size_kb:.1f} KB)")
        return active
    if not quiet:
        print("[AI CORE DIAGNOSTIC] No openmw.log found on disk yet.")
        print("[AI CORE DIAGNOSTIC] The daemon is listening and will automatically attach as soon as you boot OpenMW.")
    return os.path.normpath(candidates[0]) if candidates else os.path.join(paths.MOD_ROOT, "openmw.log")

def is_json_complete(s):
    if not s or not s.startswith("{"):
        return False
    depth = 0
    in_string = False
    escape = False
    for char in s:
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return True
    return False

def openmw_log_watcher_thread(api_key, model_name):
    global should_shutdown
    log_path = find_openmw_log()
    
    print(f"[AI CORE HUB] OpenMW Log Stream Watcher Active: {log_path}")
    
    last_size = 0
    if os.path.exists(log_path):
        last_size = os.path.getsize(log_path)

    chunk_buffers = {}

    def dispatch_openmw_payload(raw_payload, r_id):
        if r_id:
            print(f"[AI CORE LOG STREAM] Captured OpenMW request payload: {raw_payload[:80]}...")
            with processed_req_lock:
                if r_id in processed_req_ids:
                    print(f"[AI CORE DUP FILTER] Request {r_id} already processed. Skipping duplicate execution.")
                    return
                processed_req_ids.add(r_id)
                if len(processed_req_ids) > 100:
                    processed_req_ids.clear()
        
        is_fire_and_forget = False
        try:
            req_check = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
            is_fire_and_forget = req_check.get("command") in ["fork", "record_event", "record_dialogue"]
        except Exception:
            pass

        try:
            resp = process_request(api_key, model_name, raw_payload)
        except Exception as req_err:
            print(f"[AI CORE LOG STREAM ERROR] Exception during process_request: {req_err}")
            resp = json.dumps({"reply": f"An internal AI core error occurred: {req_err}", "request_id": r_id})

        if is_fire_and_forget:
            if r_id:
                print(f"[AI CORE LOG STREAM] Processed background event (req_id={r_id}).")
            return

        if r_id and resp:
            try:
                resp_data = json.loads(resp)
                resp_data["request_id"] = r_id
                resp = json.dumps(resp_data)
            except Exception:
                if resp.rstrip().endswith("}"):
                    resp = resp.rstrip()[:-1] + f', "request_id": "{r_id}"}}'

        res_targets = [
            os.path.join(paths.SCRIPT_DIR, "ai_response.json"),
        ]
        log_dir = os.path.dirname(log_path) if log_path else None
        if log_dir and os.path.exists(log_dir):
            active_target = os.path.join(log_dir, "ai_response.json")
            if active_target not in res_targets:
                res_targets.insert(0, active_target)

        for t in res_targets:
            try:
                with open(t, 'w', encoding='utf-8') as rf:
                    rf.write(resp)
            except Exception as write_err:
                print(f"[AI CORE WARNING] Could not write response to {t}: {write_err}")
        if r_id:
            print(f"[AI CORE LOG STREAM] Wrote AI response for OpenMW (req_id={r_id}).")

    last_log_check = time.time()
    while not should_shutdown:
        try:
            # Re-check every 2s: OpenMW may start writing a different (newer) log,
            # e.g. when MO2 switches profile or the game is launched after the daemon.
            if time.time() - last_log_check > 2.0:
                last_log_check = time.time()
                newest = find_openmw_log(quiet=True)
                if os.path.normcase(newest) != os.path.normcase(log_path) and os.path.exists(newest) and (
                        not os.path.exists(log_path) or os.path.getmtime(newest) > os.path.getmtime(log_path)):
                    log_path = newest
                    last_size = 0
                    print(f"[AI CORE HUB] OpenMW Log Stream Watcher switched to: {log_path}")
            if os.path.exists(log_path):
                curr_size = os.path.getsize(log_path)
                if curr_size < last_size:
                    last_size = 0
                if curr_size > last_size:
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(last_size)
                        new_lines = f.readlines()
                        last_size = f.tell()
                        
                    i = 0
                    num_lines = len(new_lines)
                    while i < num_lines:
                        line = new_lines[i]
                        i += 1

                        if "[LIVINGMW_IPC_CHUNK:" in line:
                            m_chunk = re.search(r'\[LIVINGMW_IPC_CHUNK:([^:]+):(\d+):(\d+)\]\s*(.*)', line)
                            if m_chunk:
                                c_req_id = m_chunk.group(1)
                                c_idx = int(m_chunk.group(2))
                                c_total = int(m_chunk.group(3))
                                c_data = m_chunk.group(4)
                                if c_req_id not in chunk_buffers:
                                    chunk_buffers[c_req_id] = {"total": c_total, "parts": {}, "created_at": time.time()}
                                chunk_buffers[c_req_id]["parts"][c_idx] = c_data
                                if len(chunk_buffers[c_req_id]["parts"]) == c_total:
                                    full_payload = "".join(chunk_buffers[c_req_id]["parts"][j] for j in range(1, c_total + 1))
                                    del chunk_buffers[c_req_id]
                                    now_t = time.time()
                                    chunk_buffers = {k: v for k, v in chunk_buffers.items() if now_t - v.get("created_at", now_t) < 60}
                                    parsed = extract_json_from_text(full_payload)
                                    payload_str = json.dumps(parsed) if parsed else full_payload
                                    dispatch_openmw_payload(payload_str, c_req_id)
                            continue

                        if "[LIVINGMW_IPC_REQ]" in line:
                            payload_str = line.split("[LIVINGMW_IPC_REQ]", 1)[1].strip()
                            parsed = extract_json_from_text(payload_str)
                            clean_line = payload_str
                            
                            retry_attempts = 0
                            while parsed is None and retry_attempts < 4:
                                while i < num_lines:
                                    raw_next = new_lines[i]
                                    clean_next = re.sub(r'\[\d{2}:\d{2}:\d{2}\.\d{3}\s*[\*\w]?\]', '', raw_next)
                                    clean_line += clean_next.rstrip("\r\n")
                                    i += 1
                                parsed = extract_json_from_text(clean_line)
                                if parsed is not None:
                                    break
                                time.sleep(0.05)
                                try:
                                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as rf:
                                        rf.seek(last_size)
                                        more_lines = rf.readlines()
                                        last_size = rf.tell()
                                        if more_lines:
                                            new_lines.extend(more_lines)
                                            num_lines = len(new_lines)
                                except Exception:
                                    pass
                                retry_attempts += 1
                                parsed = extract_json_from_text(clean_line)

                            req_id = ""
                            payload_str = json.dumps(parsed) if parsed else clean_line
                            if parsed and isinstance(parsed, dict):
                                req_id = parsed.get("request_id", "")
                            else:
                                rid_match = re.search(r'"request_id"\s*:\s*"([^"]+)"', clean_line)
                                if rid_match:
                                    req_id = rid_match.group(1)

                            dispatch_openmw_payload(payload_str, req_id)
        except Exception as e:
            print(f"[AI CORE LOG WATCHER ERROR] {e}")
        time.sleep(0.05)

def socket_listener_thread(api_key, model_name):
    global should_shutdown, server_socket
    executor = ThreadPoolExecutor(max_workers=8)
    while not should_shutdown:
        try:
            conn, addr = server_socket.accept()
        except OSError:
            break
        except Exception as e:
            print(f"[AI CORE ERROR] Exception during accept: {e}")
            continue
            
        executor.submit(handle_socket_connection, conn, addr, api_key, model_name)
    executor.shutdown(wait=False)

def main():
    global should_shutdown, server_socket
    disable_windows_quickedit()
    print("[AI CORE HUB] Python Daemon starting...")
    emblem = r"""
          (====)                (====)
           \  .------------------.  /
            \/   /\          /\   \/
            |   /  \        /  \   |
            |  | (><)  ||  (><) |  |
            |  \  /\  /  \  /\  /  |
             \  `----'    `----'  /
              \    \/\    /\     /
               \   |VV|  |VV|   /
                \  |  |__|  |  /
                 `------------'
    """
    print(emblem)
    api_key, model_name, fallback_model, lightweight_model = parse_env()
    if not api_key:
        sys.exit(1)
        
    print(f"[AI CORE HUB] Loaded configuration: Primary={model_name}, Fallback={fallback_model}, Lightweight={lightweight_model}")
    
    # Ensure base OpenMW config directory exists
    os.makedirs(get_primary_config_dir(), exist_ok=True)

    try:
        import system_autofix
        heal_res = system_autofix.run_system_self_healing()
        print(f"[AI CORE HEALTH] Self-Healing scan complete: {heal_res['folders_consolidated']} folders merged, {len(heal_res['json_repaired'])} JSON files repaired, {len(heal_res['logs_pruned'])} logs pruned.")
    except Exception as heal_err:
        print(f"[AI CORE HEALTH WARNING] Self-healing scan skipped: {heal_err}")
    addon_manager.load_addons()
    
    print("[AI CORE DIAGNOSTIC] Verifying game environment and mod installation...")
    lua_dir = paths.SCRIPT_DIR
    if os.path.exists(lua_dir):
        print(f"[AI CORE DIAGNOSTIC] OpenMW Lua scripts verified at: {os.path.abspath(lua_dir)}")
    else:
        print(f"[AI CORE WARNING] Could not find '{lua_dir}'! main.py must stay in the Living Morrowind mod folder next to the 'scripts' folder.")
        
    omw_script = paths.OMWSCRIPTS_FILE
    if os.path.exists(omw_script):
        print(f"[AI CORE DIAGNOSTIC] Mod registration file verified: {omw_script}")
    else:
        print(f"[AI CORE WARNING] Missing '{omw_script}'! Enable living_morrowind.omwscripts in MO2's plugin list so OpenMW loads the Lua scripts.")
    for line in paths.describe():
        print(f"[AI CORE DIAGNOSTIC] {line}")
    try:
        import landmass_autobuild
        landmass_autobuild.start_background()
    except Exception as lm_err:
        print(f"[LANDMASS] Automatic landmass map build unavailable: {lm_err}")
    
    print("[AI CORE HUB] Verifying AI model connection...")
    try:
        import random
        sample_scenarios = [
            ("Dunmer Ordinator", "You are an Ordinator patrolling Vivec City. Reply with a short, stern greeting to an outlander (1 short sentence max).", "What are you looking at?"),
            ("Khajiit Smuggler", "You are a Khajiit merchant with contraband. Reply strictly in the third person with soft, clever sibilant phrasing (1 short sentence max).", "What wares do you have for sale?"),
            ("Telvanni Wizard", "You are an arrogant Telvanni wizard in Sadrith Mora. Reply dismissively to a stranger interrupting your research (1 short sentence max).", "Can you teach me a spell?"),
            ("Nord Barbarian", "You are a hearty Nord warrior drinking at an inn. Reply with loud, friendly vigor (1 short sentence max).", "May I join your table, friend?"),
            ("Ashlander Hunter", "You are an Ashlander hunter on the Grazelands. Reply cautiously, guarding your camp (1 short sentence max).", "Peace to your yurt, hunter."),
            ("Bosmer Scout", "You are an excitable Bosmer scout in Seyda Neen. Reply with rapid, gossipy curiosity (1 short sentence max).", "Any news from the rest of the island?")
        ]
        role_name, sys_instruct, user_msg = random.choice(sample_scenarios)
        sample_prompt = [{"role": "user", "text": user_msg}]
        sample_reply = call_gemini_api(
            api_key,
            model_name,
            sys_instruct,
            sample_prompt,
            max_tokens=60,
            fallback_model=fallback_model
        )
        if sample_reply:
            print(f"[AI CORE TEST] Sample Generation ({role_name}): \"{sample_reply.strip()}\"")
        else:
            print("[AI CORE WARNING] Sample generation returned an empty response. Please verify your GEMINI_API_KEY in .env.")
    except Exception as sample_err:
        print(f"[AI CORE WARNING] Sample generation encountered an issue: {sample_err}")
    
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(0.5)
        test_sock.connect(('127.0.0.1', 50007))
        shutdown_cmd = json.dumps({"command": "shutdown"})
        header = f"{len(shutdown_cmd)}\n"
        test_sock.sendall((header + shutdown_cmd).encode('utf-8'))
        test_sock.close()
        print("[AI CORE HUB] Found running daemon instance. Sent shutdown signal and waiting for port release...")
        time.sleep(1.0)
    except Exception:
        pass
        
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_ok = True
    try:
        server_socket.bind(('', 50007))
        server_socket.listen(5)
        print("[AI CORE HUB] Python TCP Server Active. Listening on port 50007...")
    except Exception as e:
        # OpenMW talks to the daemon through openmw.log + ai_response.json, not TCP.
        # Port 50007 sits in Windows' temporary-port range and can be taken by any
        # app (a browser connection, for example), so carry on without it.
        tcp_ok = False
        try:
            server_socket.close()
        except Exception:
            pass
        print(f"[AI CORE WARNING] Port 50007 is busy ({e}). Continuing without the optional TCP server; the game connection is unaffected.")
    print("[AI CORE HUB] Press Ctrl+C at any time to stop the server.")
    

        
    should_shutdown = False
    
    if tcp_ok:
        listener = threading.Thread(target=socket_listener_thread, args=(api_key, model_name), daemon=True)
        listener.start()
    
    ipc_listener = threading.Thread(target=file_ipc_watcher_thread, args=(api_key, model_name), daemon=True)
    ipc_listener.start()
    
    log_listener = threading.Thread(target=openmw_log_watcher_thread, args=(api_key, model_name), daemon=True)
    log_listener.start()
    
    try:
        while not should_shutdown:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[AI CORE HUB] Ctrl+C detected. Shutting down...")
        should_shutdown = True
        
    try:
        server_socket.close()
    except Exception:
        pass
        
    print("[AI CORE HUB] Python Daemon stopped.")

if __name__ == "__main__":
    main()
