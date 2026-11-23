"""
Build living_morrowind_chat.esp: the "* Chat *" topic in the native dialogue menu.

The plugin holds one topic with one unfiltered response, so every actor that can
open the dialogue menu offers it. Its result script runs ClearInfoActor, which
removes the entry again so the Chat topic never clutters the player's journal.

    python tools/build_chat_plugin.py
"""

import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "living_morrowind_chat.esp")

TOPIC = "* Chat *"
INFO_ID = "7400210411021977"
RESPONSE = "What is it?"
RESULT_SCRIPT = "ClearInfoActor"


def sub(tag, data):
    return tag + struct.pack("<I", len(data)) + data


def zstr(text):
    return text.encode("latin-1") + b"\0"


def record(tag, body):
    return tag + struct.pack("<III", len(body), 0, 0) + body


def fixed(text, size):
    return text.encode("latin-1")[:size - 1].ljust(size, b"\0")


def build():
    hedr = struct.pack("<fI", 1.3, 0)
    hedr += fixed("Living Morrowind", 32)
    hedr += fixed("Adds the Chat topic to the dialogue menu for Living Morrowind.", 256)
    hedr += struct.pack("<I", 2)  # DIAL + INFO
    header = record(b"TES3", sub(b"HEDR", hedr))

    dial = record(b"DIAL", sub(b"NAME", zstr(TOPIC)) + sub(b"DATA", b"\x00"))

    # DATA: type 0 (topic), disposition 0, then rank / gender / PC rank = none
    info_data = struct.pack("<iibbbb", 0, 0, -1, -1, -1, 0)
    info = record(
        b"INFO",
        sub(b"INAM", zstr(INFO_ID))
        + sub(b"PNAM", b"\0")
        + sub(b"NNAM", b"\0")
        + sub(b"DATA", info_data)
        + sub(b"NAME", RESPONSE.encode("latin-1"))
        + sub(b"BNAM", RESULT_SCRIPT.encode("latin-1")),
    )
    return header + dial + info


if __name__ == "__main__":
    with open(OUT, "wb") as f:
        f.write(build())
    print(f"Wrote {OUT} ({os.path.getsize(OUT)} bytes)")
