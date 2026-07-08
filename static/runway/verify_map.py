#!/usr/bin/env python3
"""Verify Runway map alignment — run after build_maps.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent.parent))


def project(lat, lon, bounds, padding, w, h):
    left, top = padding.get("left", 0), padding.get("top", 0)
    right, bottom = padding.get("right", 0), padding.get("bottom", 0)
    uw, uh = w - left - right, h - top - bottom
    x = left + (lon - bounds["lonMin"]) / (bounds["lonMax"] - bounds["lonMin"]) * uw
    y = top + (bounds["latMax"] - lat) / (bounds["latMax"] - bounds["latMin"]) * uh
    return int(round(x)), int(round(y))


def main() -> int:
    from runway_game_data import AIRPORTS, OHIO_REGION_IATA

    with open(BASE / "map-config.json") as f:
        cfg = json.load(f)
    usa = cfg["usa"]
    wiki = Image.open(BASE / "us-map-wikimedia.png").convert("RGBA")
    styled = Image.open(BASE / "us-map-styled.png").convert("RGB")
    w, h = wiki.size

    rgb = [[0] * w for _ in range(h)]
    land = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, a = wiki.getpixel((x, y))
            lum = (r + g + b) / 3
            rgb[y][x] = lum
            land[y][x] = a > 20 and lum < 248

    bounds, pad = usa["bounds"], usa["padding"]
    ok = miss = 0
    ohio_miss = []
    for ap in AIRPORTS:
        xi, yi = project(ap["lat"], ap["lon"], bounds, pad, w, h)
        if 0 <= xi < w and 0 <= yi < h and land[yi][xi]:
            ok += 1
        else:
            miss += 1
            if ap["iata"] in OHIO_REGION_IATA:
                ohio_miss.append(ap["iata"])

    border_color = (186, 232, 205)
    border_px = sum(
        1
        for y in range(styled.height)
        for x in range(styled.width)
        if styled.getpixel((x, y)) == border_color
    )

    print(f"airports on land: {ok}/{len(AIRPORTS)}")
    if ohio_miss:
        print(f"OHIO misses: {ohio_miss}")
    print(f"border pixels in styled map: {border_px}")

    if ok < 55:
        print("FAIL: too many airports off land")
        return 1
    if border_px < 800:
        print("FAIL: state borders not visible in styled map")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())