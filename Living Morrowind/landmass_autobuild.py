"""
Keeps landmass_map.json in sync with the player's load order.

Started by the daemon in a background thread. It builds the map the first time,
then rebuilds it whenever the active openmw.cfg changes (for example after you
add a landmass mod in MO2 and launch the game). Until a map exists, landmass.py
uses its built-in region and town tables, so nothing waits on this.
"""

import importlib.util
import json
import os
import threading
import time

import landmass
import paths

MAP_PATH = os.path.join(paths.MOD_ROOT, landmass.MAP_FILENAME)
CHECK_INTERVAL = 30.0
_started = False


def _load_builder():
    path = os.path.join(paths.MOD_ROOT, "tools", "build_landmass_map.py")
    spec = importlib.util.spec_from_file_location("build_landmass_map", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _current_signature():
    try:
        with open(MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("source_cfg"), data.get("source_cfg_mtime"), data.get("source_cfg_size"))
    except Exception:
        return None


def needs_build(cfg):
    if not cfg or not os.path.isfile(cfg):
        return False
    st = os.stat(cfg)
    want = (os.path.abspath(cfg), st.st_mtime, st.st_size)
    return _current_signature() != want


def build_now(cfg):
    builder = _load_builder()
    skipped = []

    def log(msg):
        if msg.startswith("  [skip]"):
            skipped.append(msg)
            return
        print(f"[LANDMASS] {msg}")

    t0 = time.time()
    builder.build(cfg, MAP_PATH, log=log)
    if skipped:
        print(f"[LANDMASS] {len(skipped)} plugins in the load order were not found on disk and were skipped.")
    print(f"[LANDMASS] Landmass map ready ({time.time() - t0:.1f}s).")


def _worker():
    announced_missing = False
    while True:
        try:
            cfg = paths.find_openmw_cfg()
            if not cfg:
                if not announced_missing:
                    print("[LANDMASS] No openmw.cfg found yet; using built-in landmass tables. "
                          "Set OPENMW_CFG in .env if your setup is unusual.")
                    announced_missing = True
            elif needs_build(cfg):
                print(f"[LANDMASS] Building landmass map from load order: {cfg}")
                build_now(cfg)
        except Exception as e:
            print(f"[LANDMASS] Map build failed: {e}")
        time.sleep(CHECK_INTERVAL)


def start_background():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_worker, name="landmass-map", daemon=True).start()
