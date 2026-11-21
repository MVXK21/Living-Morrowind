"""
Build landmass_map.json for Sentient Morrowind from your OpenMW load order.

It reads openmw.cfg, walks every content file in load order, and records:
  * every exterior cell grid -> landmass (from its region, sea cells by nearest land)
  * every interior cell name -> landmass (by following door links to the outside)
  * settlement names (named exterior cells and interior name prefixes) -> landmass

The daemon runs this automatically at startup (and whenever the load order
changes), using the openmw.cfg of your active MO2 profile. You can also run it
by hand:

    python tools/build_landmass_map.py
    python tools/build_landmass_map.py --cfg "C:/path/to/openmw.cfg"

The result is written next to landmass.py (the mod's root folder).
"""

import argparse
import json
import os
import struct
import sys
from collections import Counter, defaultdict, deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import landmass  # noqa: E402
import paths  # noqa: E402

CELL_SIZE = 8192.0


def default_cfg_paths():
    home = os.path.expanduser("~")
    docs = [os.path.join(home, "Documents"), os.path.join(home, "OneDrive", "Documents")]
    out = [os.path.join(d, "My Games", "OpenMW", "openmw.cfg") for d in docs]
    out.append(os.path.join(home, ".config", "openmw", "openmw.cfg"))
    return out


def parse_cfg(path):
    data_dirs, content = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("data="):
                d = line[5:].strip()
                if d.startswith('"') and d.endswith('"'):
                    d = d[1:-1].replace('&"', '"').replace("&&", "&")
                data_dirs.append(d)
            elif line.startswith("content="):
                content.append(line[8:].strip())
    return data_dirs, content


def index_data_dirs(data_dirs):
    """lower-case filename -> path; later data dirs win, like OpenMW."""
    idx = {}
    for d in data_dirs:
        try:
            for name in os.listdir(d):
                low = name.lower()
                if low.endswith((".esm", ".esp", ".omwaddon", ".omwgame")):
                    idx[low] = os.path.join(d, name)
        except OSError:
            pass
    return idx


def cstr(b):
    return b.split(b"\x00", 1)[0].decode("latin-1")


def iter_cells(path):
    """Yield (name, flags, gx, gy, region, doors) for each CELL record.

    doors: list of (dest_interior_name or None, dest_x, dest_y)
    """
    with open(path, "rb") as f:
        while True:
            hdr = f.read(16)
            if len(hdr) < 16:
                return
            rtype = hdr[0:4]
            size = struct.unpack_from("<I", hdr, 4)[0]
            if rtype != b"CELL":
                f.seek(size, 1)
                continue
            body = f.read(size)
            name, flags, gx, gy, region = "", 0, None, None, None
            doors = []
            in_refs = False
            cur = None  # current reference: dict
            pos = 0
            n = len(body)

            def flush(ref):
                if ref and not ref.get("deleted") and ref.get("dodt") is not None:
                    x, y = ref["dodt"]
                    doors.append((ref.get("dnam"), x, y))

            while pos + 8 <= n:
                st = body[pos:pos + 4]
                sz = struct.unpack_from("<I", body, pos + 4)[0]
                d = body[pos + 8:pos + 8 + sz]
                pos += 8 + sz
                if not in_refs:
                    if st == b"NAME":
                        name = cstr(d)
                    elif st == b"DATA" and len(d) >= 12:
                        flags, gx, gy = struct.unpack_from("<Iii", d, 0)
                    elif st == b"RGNN":
                        region = cstr(d)
                    elif st == b"FRMR":
                        in_refs = True
                        cur = {}
                    continue
                if st == b"FRMR":
                    flush(cur)
                    cur = {}
                elif st == b"DODT" and len(d) >= 8:
                    cur["dodt"] = struct.unpack_from("<ff", d, 0)
                elif st == b"DNAM":
                    cur["dnam"] = cstr(d)
                elif st == b"DELE":
                    cur["deleted"] = True
            flush(cur)
            yield name, flags, gx, gy, region, doors


def grid_of(x, y):
    import math
    return int(math.floor(x / CELL_SIZE)), int(math.floor(y / CELL_SIZE))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cfg", help="path to openmw.cfg")
    ap.add_argument("--out", default=os.path.join(ROOT, landmass.MAP_FILENAME))
    ap.add_argument("--list-unmapped", action="store_true", help="print interiors that could not be placed")
    args = ap.parse_args()

    cfg = args.cfg or paths.find_openmw_cfg()
    if not cfg:
        for c in default_cfg_paths():
            if os.path.exists(c):
                cfg = c
                break
    if not cfg or not os.path.exists(cfg):
        print("Could not find openmw.cfg. Pass it with --cfg.")
        return 1
    return build(cfg, args.out, list_unmapped=args.list_unmapped)


def cfg_signature(cfg):
    st = os.stat(cfg)
    return {"source_cfg": os.path.abspath(cfg), "source_cfg_mtime": st.st_mtime, "source_cfg_size": st.st_size}


def build(cfg, out_path, list_unmapped=False, log=print):
    class _A:
        pass
    args = _A()
    args.out = out_path
    args.list_unmapped = list_unmapped
    print = log  # noqa: A001  (route output to caller's logger)
    print(f"Reading load order from {cfg}")
    data_dirs, content = parse_cfg(cfg)
    idx = index_data_dirs(data_dirs)

    region_names = {}
    exteriors = {}  # (gx, gy) -> {"region": str, "name": str}
    ext_links = defaultdict(set)  # (gx, gy) -> {interior names}
    int_exits = defaultdict(list)  # interior -> [(gx, gy)]
    int_links = defaultdict(set)  # interior -> {interior}
    interiors = set()
    parsed = 0

    for c in content:
        low = c.lower()
        if not low.endswith((".esm", ".esp", ".omwaddon", ".omwgame")):
            continue
        path = idx.get(low)
        if not path:
            print(f"  [skip] not found in data dirs: {c}")
            continue
        parsed += 1
        # Regions (cheap second pass on REGN only)
        try:
            with open(path, "rb") as f:
                while True:
                    hdr = f.read(16)
                    if len(hdr) < 16:
                        break
                    size = struct.unpack_from("<I", hdr, 4)[0]
                    if hdr[0:4] != b"REGN":
                        f.seek(size, 1)
                        continue
                    body = f.read(size)
                    p, rid, rname = 0, None, None
                    while p + 8 <= len(body):
                        st = body[p:p + 4]
                        sz = struct.unpack_from("<I", body, p + 4)[0]
                        if st == b"NAME":
                            rid = cstr(body[p + 8:p + 8 + sz])
                        elif st == b"FNAM":
                            rname = cstr(body[p + 8:p + 8 + sz])
                        p += 8 + sz
                    if rid:
                        region_names[rid.lower()] = rname or rid
            for name, flags, gx, gy, region, doors in iter_cells(path):
                if flags & 1:
                    key = name.lower()
                    if not key:
                        continue
                    interiors.add(key)
                    for dnam, x, y in doors:
                        if dnam:
                            int_links[key].add(dnam.lower())
                            int_links[dnam.lower()].add(key)
                        else:
                            int_exits[key].append(grid_of(x, y))
                else:
                    if gx is None:
                        continue
                    g = (gx, gy)
                    e = exteriors.setdefault(g, {"region": "", "name": ""})
                    if region:
                        e["region"] = region.lower()
                    if name:
                        e["name"] = name
                    for dnam, x, y in doors:
                        if dnam:
                            ext_links[g].add(dnam.lower())
        except Exception as ex:
            print(f"  [warn] failed to parse {c}: {ex}")

    print(f"Parsed {parsed} plugins: {len(exteriors)} exterior cells, {len(interiors)} interior cells, {len(region_names)} regions")

    # 1. Exterior grid -> landmass
    grid_lm = {}
    unknown_regions = Counter()
    for g, e in exteriors.items():
        r = e["region"]
        lm = landmass.REGION_LANDMASS.get(r) if r and r not in landmass.WATER_REGIONS else None
        if r and r not in landmass.REGION_LANDMASS and r not in landmass.WATER_REGIONS:
            unknown_regions[r] += 1
        if lm:
            grid_lm[g] = lm
    anchors = dict(grid_lm)
    for g in exteriors:
        if g in grid_lm:
            continue
        found = None
        for r in range(1, 41):
            best = Counter()
            for dx in range(-r, r + 1):
                for dy in (-r, r) if abs(dx) != r else range(-r, r + 1):
                    lm = anchors.get((g[0] + dx, g[1] + dy))
                    if lm:
                        best[lm] += 1
            if best:
                found = best.most_common(1)[0][0]
                break
        if found:
            grid_lm[g] = found

    # Unknown (unlisted) regions: majority landmass of their cells by position
    region_lm = {}
    by_region = defaultdict(Counter)
    for g, e in exteriors.items():
        if e["region"] in unknown_regions and g in grid_lm:
            by_region[e["region"]][grid_lm[g]] += 1
    for r, cnt in by_region.items():
        region_lm[r] = cnt.most_common(1)[0][0]

    # 2. Interiors
    votes = defaultdict(Counter)
    for name in interiors:
        for g in int_exits.get(name, []):
            lm = grid_lm.get(g)
            if lm:
                votes[name][lm] += 1
    for g, names in ext_links.items():
        lm = grid_lm.get(g)
        if lm:
            for name in names:
                votes[name][lm] += 1
    int_lm = {name: cnt.most_common(1)[0][0] for name, cnt in votes.items()}
    for name in interiors:
        forced = landmass.forced_landmass(name)
        if forced:
            int_lm[name] = forced
    queue = deque(int_lm.keys())
    while queue:
        cur = queue.popleft()
        for nb in int_links.get(cur, ()):
            if nb not in int_lm:
                int_lm[nb] = int_lm[cur]
                queue.append(nb)

    # 3. Settlements and prefixes
    settle_votes = defaultdict(Counter)
    for g, e in exteriors.items():
        if e["name"] and g in grid_lm:
            settle_votes[e["name"].lower()][grid_lm[g]] += 1
    settlements = {k: v.most_common(1)[0][0] for k, v in settle_votes.items()}
    prefix_votes = defaultdict(Counter)
    for name, lm in int_lm.items():
        if "," in name:
            prefix_votes[name.split(",")[0].strip()][lm] += 1
    prefixes = {}
    for k, cnt in prefix_votes.items():
        lm, top = cnt.most_common(1)[0]
        total = sum(cnt.values())
        if total >= 2 and top / total >= 0.8:
            prefixes[k] = lm

    out = {
        "version": 1,
        **cfg_signature(cfg),
        "plugins_parsed": parsed,
        "regions": region_names,
        "region_landmass": region_lm,
        "grid": {f"{g[0]},{g[1]}": [lm, exteriors[g]["region"], exteriors[g]["name"]] for g, lm in sorted(grid_lm.items())},
        "interiors": dict(sorted(int_lm.items())),
        "settlements": dict(sorted(settlements.items())),
        "prefixes": dict(sorted(prefixes.items())),
    }
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, args.out)

    lm_counts = Counter(grid_lm.values())
    int_counts = Counter(int_lm.values())
    print("Exterior cells per landmass: " + ", ".join(f"{k}={v}" for k, v in lm_counts.most_common()))
    print("Interior cells per landmass: " + ", ".join(f"{k}={v}" for k, v in int_counts.most_common()))
    unmapped = sorted(interiors - set(int_lm))
    print(f"Interiors without a landmass (no door path outside): {len(unmapped)}")
    if args.list_unmapped:
        for name in unmapped:
            print(f"   {name}")
    if unknown_regions:
        print("Regions not in landmass.REGION_LANDMASS (assigned by position):")
        for r, n in unknown_regions.most_common():
            print(f"   {r} ({n} cells) -> {region_lm.get(r, '?')}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
