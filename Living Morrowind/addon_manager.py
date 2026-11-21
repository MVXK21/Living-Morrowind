import os
import importlib.util
import sys

# Registries
prompt_modifiers = []  # callbacks: func(world_id, npc_id, npc_name, prompt, sys_prompt_lines)
tcp_handlers = {}      # command -> func(world_id, payload_dict)
tag_processors = []    # callbacks: func(world_id, reply_text, npc_name) -> (new_reply, commands_list)

def register_prompt_modifier(func):
    prompt_modifiers.append(func)
    return func

def register_tcp_handler(command):
    def decorator(func):
        tcp_handlers[command] = func
        return func
    return decorator

def register_tag_processor(func):
    tag_processors.append(func)
    return func

def load_addons():
    addons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addons")
    if not os.path.exists(addons_dir):
        os.makedirs(addons_dir)
        with open(os.path.join(addons_dir, "README.txt"), "w") as f:
            f.write("Drop your Python addon scripts (*.py) here. They will be loaded dynamically at startup.")
            
    if addons_dir not in sys.path:
        sys.path.append(addons_dir)
        
    for filename in os.listdir(addons_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            try:
                spec = importlib.util.spec_from_file_location(module_name, os.path.join(addons_dir, filename))
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                print(f"[AI CORE ADDON] Successfully loaded: {filename}")
            except Exception as e:
                print(f"[AI CORE ERROR] Failed to load addon {filename}: {e}")

def modify_system_prompt(world_id, npc_id, npc_name, prompt, sys_prompt_lines):
    for mod in prompt_modifiers:
        try:
            mod(world_id, npc_id, npc_name, prompt, sys_prompt_lines)
        except Exception as e:
            print(f"[AI CORE ERROR] Error in prompt modifier: {e}")

def execute_tcp_command(command, world_id, payload):
    if command in tcp_handlers:
        try:
            return tcp_handlers[command](world_id, payload)
        except Exception as e:
            print(f"[AI CORE ERROR] Error executing TCP handler for '{command}': {e}")
            return None
    return None

def process_npc_tags(world_id, reply_text, npc_name):
    all_cmds = []
    requested_items = []
    offered_items = []
    for proc in tag_processors:
        try:
            res = proc(world_id, reply_text, npc_name)
            if isinstance(res, tuple) and len(res) == 3:
                reply_text, cmds, items = res
                if items:
                    if proc.__name__ == "process_give_item_tag":
                        if isinstance(items, list):
                            offered_items.extend(items)
                        else:
                            offered_items.append(items)
                    else:
                        if isinstance(items, list):
                            requested_items.extend(items)
                        else:
                            requested_items.append(items)
            else:
                reply_text, cmds = res
            if cmds:
                all_cmds.extend(cmds)
        except Exception as e:
            print(f"[AI CORE ERROR] Tag processor failed: {e}")
    return reply_text, all_cmds, requested_items, offered_items

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() in ["repair", "autofix", "verify"]:
        import system_autofix
        print("[AI CORE CLI] Running System Self-Healing & Diagnostic Scan...")
        res = system_autofix.run_system_self_healing()
        print(f"[AI CORE CLI] Consolidate Folders: {res['folders_consolidated']} merged.")
        print(f"[AI CORE CLI] JSON Files Repaired: {len(res['json_repaired'])}")
        for j in res['json_repaired']:
            print(f"  - {j}")
        print(f"[AI CORE CLI] Logs Pruned: {len(res['logs_pruned'])}")
        for l in res['logs_pruned']:
            print(f"  - {l}")
        print(f"[AI CORE CLI] Missing Scripts: {res['missing_scripts']}")
        print("[AI CORE CLI] System Health Check Complete.")
    else:
        print("Usage: python addon_manager.py [repair|autofix|verify]")
