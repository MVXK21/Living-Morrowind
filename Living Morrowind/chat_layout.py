"""
Tells the in-menu chat bar where the native dialogue window is.

OpenMW Lua cannot read the window's position, but OpenMW saves it in settings.cfg.
The daemon copies it to scripts/living_morrowind/chat_layout.json, which the Lua
side reads whenever the chat bar opens.
"""

import json
import os

import paths

LAYOUT_FILE = os.path.join(paths.SCRIPT_DIR, "chat_layout.json")
DEFAULTS = {"x": 0.15, "y": 0.5, "w": 0.7, "h": 0.45}
MAXIMIZED_DEFAULTS = {"x": 0.015, "y": 0.02, "w": 0.97, "h": 0.875}


def read_dialogue_rect(settings_path):
    values = {}
    section = ""
    with open(settings_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
            elif section == "windows" and "=" in line and line.lower().startswith("dialogue"):
                key, value = line.split("=", 1)
                values[key.strip().lower()] = value.strip().lower()

    maximized = values.get("dialogue maximized") == "true"
    prefix = "dialogue maximized " if maximized else "dialogue "
    base = MAXIMIZED_DEFAULTS if maximized else DEFAULTS
    rect = {}
    for key, default in base.items():
        try:
            rect[key] = max(0.0, min(1.0, float(values.get(prefix + key, default))))
        except ValueError:
            rect[key] = default
    return rect


def update():
    """Refresh chat_layout.json; returns the rectangle, or None if unavailable."""
    cfg = paths.find_openmw_cfg()
    if not cfg:
        return None
    settings = os.path.join(os.path.dirname(cfg), "settings.cfg")
    if not os.path.isfile(settings):
        return None
    rect = read_dialogue_rect(settings)
    text = json.dumps(rect) + "\n"
    try:
        with open(LAYOUT_FILE, "r", encoding="utf-8") as f:
            if f.read() == text:
                return rect
    except OSError:
        pass
    with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    return rect
