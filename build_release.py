"""
Package the "Living Morrowind" mod folder into an MO2-installable archive.

    python build_release.py            -> dist/Living Morrowind <version>.zip

The archive root is the mod's data root (living_morrowind.omwscripts, scripts/,
the daemon files), which is what MO2 expects. Per-user runtime files are left out:
API key (.env), saves/memories (worlds/), logs, caches and the generated
landmass map (rebuilt automatically from each player's load order).
"""

import fnmatch
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "Living Morrowind")
VERSION = sys.argv[1] if len(sys.argv) > 1 else "1.0.0"

EXCLUDE_DIRS = {"__pycache__", "worlds", ".legacy_bak", ".corrupted_bak"}
EXCLUDE_FILES = [".env", ".env.txt", "daemon_debug.log", "daemon_debug.log.old", "openmw.log",
                 "landmass_map.json", "landmass_map.json.tmp", "*.pyc", "*.omwscripts.esp",
                 "ai_request.json"]


def excluded(name):
    return any(fnmatch.fnmatch(name.lower(), pat.lower()) for pat in EXCLUDE_FILES)


def main():
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", f"Living Morrowind {VERSION}.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(MOD):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                if excluded(fname):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, MOD)
                z.write(full, rel)
                count += 1
    print(f"Wrote {out} ({count} files)")


if __name__ == "__main__":
    main()
