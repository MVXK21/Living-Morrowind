"""
Path discovery for Living Morrowind.

The mod folder is both the OpenMW data folder (scripts/, living_morrowind.omwscripts)
and the home of the Python daemon. Everything is resolved relative to this file, so
the daemon works no matter where it is started from.

It also finds the Mod Organizer 2 install this mod lives in, the active MO2
profile, and from those the openmw.cfg (load order) and openmw.log (IPC channel)
that OpenMW Player uses. Explicit overrides can be put in .env:

    OPENMW_CFG=C:/path/to/openmw.cfg
    OPENMW_LOG=C:/path/to/openmw.log
"""

import glob
import os
import re

MOD_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT_NAME = "living_morrowind"


def _data_root():
    # Normal MO2 layout: scripts/ sits directly in the mod folder.
    if os.path.isdir(os.path.join(MOD_ROOT, "scripts", SCRIPT_NAME)):
        return MOD_ROOT
    # Manual install into a Morrowind folder: daemon next to "Data Files".
    alt = os.path.join(MOD_ROOT, "Data Files")
    if os.path.isdir(os.path.join(alt, "scripts", SCRIPT_NAME)):
        return alt
    return MOD_ROOT


DATA_ROOT = _data_root()
SCRIPT_DIR = os.path.join(DATA_ROOT, "scripts", SCRIPT_NAME)
CONFIG_DIR = os.path.join(SCRIPT_DIR, "config")
WORLDS_DIR = os.path.join(SCRIPT_DIR, "worlds")
RESPONSE_FILE = os.path.join(SCRIPT_DIR, "ai_response.json")
OMWSCRIPTS_FILE = os.path.join(DATA_ROOT, SCRIPT_NAME + ".omwscripts")
ENV_FILE = os.path.join(MOD_ROOT, ".env")


def read_env_value(key):
    val = os.environ.get(key)
    if val:
        return val.strip().strip('"')
    for candidate in (ENV_FILE, ENV_FILE + ".txt"):
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(key + "="):
                        return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    return None


# ---------------------------------------------------------------------------
# Mod Organizer 2
# ---------------------------------------------------------------------------

def _read_ini(path):
    data = {}
    section = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].lower()
                elif "=" in line:
                    k, v = line.split("=", 1)
                    data[(section, k.strip().lower())] = v.strip()
    except OSError:
        pass
    return data


def _ini_str(v):
    if v is None:
        return None
    m = re.match(r"@ByteArray\((.*)\)$", v)
    if m:
        v = m.group(1)
    return v.strip().strip('"')


def _expand_base(v, base):
    if not v:
        return None
    v = v.replace("%BASE_DIR%", base).replace("\\\\", "\\")
    return os.path.normpath(v)


def find_mo2():
    """Return {"base": ..., "profile": name, "profile_dir": ...} or None."""
    mods_dir = os.path.dirname(MOD_ROOT)
    ini_candidates = []
    # Portable instance: <base>/mods/<this mod>, <base>/ModOrganizer.ini
    ini_candidates.append(os.path.join(os.path.dirname(mods_dir), "ModOrganizer.ini"))
    # Global instances: %LOCALAPPDATA%/ModOrganizer/<instance>/ModOrganizer.ini
    local = os.environ.get("LOCALAPPDATA")
    if local:
        ini_candidates.extend(glob.glob(os.path.join(local, "ModOrganizer", "*", "ModOrganizer.ini")))
    for ini in ini_candidates:
        if not os.path.isfile(ini):
            continue
        d = _read_ini(ini)
        base = _expand_base(_ini_str(d.get(("settings", "base_directory"))), os.path.dirname(ini)) or os.path.dirname(ini)
        mod_dir = _expand_base(_ini_str(d.get(("settings", "mod_directory"))), base) or os.path.join(base, "mods")
        if os.path.normcase(os.path.normpath(mod_dir)) != os.path.normcase(os.path.normpath(mods_dir)):
            continue
        profiles = _expand_base(_ini_str(d.get(("settings", "profiles_directory"))), base) or os.path.join(base, "profiles")
        profile = _ini_str(d.get(("general", "selected_profile")))
        profile_dir = os.path.join(profiles, profile) if profile else None
        return {"base": base, "profile": profile, "profile_dir": profile_dir, "profiles_dir": profiles}
    return None


def _documents_dirs():
    out = []
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        val, _ = winreg.QueryValueEx(key, "Personal")
        winreg.CloseKey(key)
        out.append(os.path.expandvars(val))
    except Exception:
        pass
    home = os.path.expanduser("~")
    out += [os.path.join(home, "OneDrive", "Documents"), os.path.join(home, "Documents")]
    return list(dict.fromkeys(out))


def _openmw_dirs():
    """Folders where OpenMW Player / OpenMW keep openmw.cfg and openmw.log, best first."""
    dirs = []
    mo2 = find_mo2()
    if mo2:
        if mo2.get("profile_dir"):
            dirs.append(mo2["profile_dir"])                       # profile-specific settings
            dirs.append(os.path.join(mo2["profile_dir"], "openmw"))  # profile-local saves (user-data)
        dirs.append(os.path.join(mo2["base"], "plugins", "data", "openmwplayer"))
    for docs in _documents_dirs():
        dirs.append(os.path.join(docs, "My Games", "OpenMW"))          # Windows
    home = os.path.expanduser("~")
    dirs.append(os.path.join(home, ".config", "openmw"))                # Linux
    dirs.append(os.path.join(home, ".var", "app", "org.openmw.OpenMW", "config", "openmw"))  # Linux Flatpak
    dirs.append(os.path.join(home, "Library", "Preferences", "openmw"))  # macOS
    return list(dict.fromkeys(os.path.normpath(d) for d in dirs))


def openmw_cfg_candidates():
    override = read_env_value("OPENMW_CFG")
    if override:
        return [override]
    return [os.path.join(d, "openmw.cfg") for d in _openmw_dirs()]


def find_openmw_cfg():
    """The openmw.cfg describing the load order this mod is used with."""
    for c in openmw_cfg_candidates():
        if os.path.isfile(c) and _cfg_mentions_this_mod(c):
            return c
    for c in openmw_cfg_candidates():
        if os.path.isfile(c):
            return c
    return None


def _cfg_mentions_this_mod(cfg):
    try:
        with open(cfg, "r", encoding="utf-8", errors="replace") as f:
            text = f.read().lower()
    except OSError:
        return False
    return (SCRIPT_NAME + ".omwscripts") in text or os.path.normcase(MOD_ROOT).replace("\\", "/").lower() in text.replace("\\", "/")


def openmw_log_candidates():
    override = read_env_value("OPENMW_LOG")
    if override:
        return [override]
    return [os.path.join(d, "openmw.log") for d in _openmw_dirs()]


def describe():
    mo2 = find_mo2()
    lines = [f"Mod folder: {MOD_ROOT}", f"Lua scripts: {SCRIPT_DIR}"]
    if mo2:
        lines.append(f"Mod Organizer 2: {mo2['base']} (profile: {mo2.get('profile') or '?'})")
    else:
        lines.append("Mod Organizer 2: not detected (using OpenMW's standard config folder)")
    lines.append(f"openmw.cfg: {find_openmw_cfg() or 'not found'}")
    return lines
