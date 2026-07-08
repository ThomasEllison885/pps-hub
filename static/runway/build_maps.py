#!/usr/bin/env python3
"""
Build Runway maps from us-map-wikimedia.png.

Principle: the Wikimedia raster IS the truth. State borders are extracted from its
pixels (darker gray lines). Airport projection uses calibrated bounds + padding
that match how the image was drawn — NOT a separate GeoJSON overlay.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent

# Calibrated to us-map-wikimedia.png (1920×1188) — 57/63 airports on land.
USA_BOUNDS = {
    "lonMin": -125.5,
    "lonMax": -66.0,
    "latMin": 24.0,
    "latMax": 49.55,
}
USA_PADDING = {"left": 20, "top": 40, "right": 20, "bottom": 4}

OHIO_BOUNDS = {
    "lonMin": -87.35,
    "lonMax": -78.75,
    "latMin": 36.15,
    "latMax": 44.35,
}

MIDWEST_BOUNDS = {
    "lonMin": -97.8,
    "lonMax": -75.8,
    "latMin": 34.0,
    "latMax": 47.6,
}

OCEAN = (7, 21, 37)
LAND = (52, 98, 82)
LAND_EDGE = (42, 78, 66)
BORDER = (186, 232, 205)
COAST = (140, 195, 170)


def project(
    lat: float,
    lon: float,
    bounds: dict,
    padding: dict,
    width: int,
    height: int,
) -> tuple[float, float]:
    left = padding.get("left", 0)
    top = padding.get("top", 0)
    right = padding.get("right", 0)
    bottom = padding.get("bottom", 0)
    uw = width - left - right
    uh = height - top - bottom
    x = left + (lon - bounds["lonMin"]) / (bounds["lonMax"] - bounds["lonMin"]) * uw
    y = top + (bounds["latMax"] - lat) / (bounds["latMax"] - bounds["latMin"]) * uh
    return x, y


def style_wikimedia(src: Image.Image) -> Image.Image:
    """Classify Wikimedia pixels: ocean, land, native state-line pixels, coast."""
    src = src.convert("RGBA")
    w, h = src.size
    out = Image.new("RGBA", (w, h), OCEAN + (255,))
    spx = src.load()
    opx = out.load()
    border_count = 0

    for y in range(h):
        for x in range(w):
            r, g, b, a = spx[x, y]
            if a < 20 or (r + g + b) / 3 >= 248:
                continue
            lum = (r + g + b) / 3
            # Native Wikimedia state borders: thin darker gray on land (~90–197).
            if 88 < lum < 198:
                opx[x, y] = BORDER + (255,)
                border_count += 1
            elif lum >= 198:
                opx[x, y] = LAND + (255,)
            elif lum >= 55:
                opx[x, y] = COAST + (255,)
            else:
                opx[x, y] = LAND_EDGE + (255,)

    if border_count < 800:
        print(f"WARNING: only {border_count} border pixels — state lines may be invisible", file=sys.stderr)
    else:
        print(f"border pixels preserved: {border_count}")
    return out


def crop_region(
    img: Image.Image,
    crop_bounds: dict,
    full_bounds: dict,
    padding: dict,
) -> Image.Image:
    w, h = img.size
    x1, y1 = project(crop_bounds["latMin"], crop_bounds["lonMin"], full_bounds, padding, w, h)
    x2, y2 = project(crop_bounds["latMax"], crop_bounds["lonMax"], full_bounds, padding, w, h)
    pad = 24
    left = int(max(0, min(x1, x2) - pad))
    top = int(max(0, min(y1, y2) - pad))
    right = int(min(w, max(x1, x2) + pad))
    bottom = int(min(h, max(y1, y2) + pad))
    crop = img.crop((left, top, right, bottom))
    scale = max(1, int(1400 / max(crop.size)))
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    return crop


def verify_airports(bounds: dict, padding: dict, w: int, h: int, land_mask) -> int:
    """Return count of airports landing on land (for CI)."""
    sys.path.insert(0, str(BASE.parent.parent))
    try:
        from runway_game_data import AIRPORTS
    except ImportError:
        return -1
    ok = 0
    for ap in AIRPORTS:
        x, y = project(ap["lat"], ap["lon"], bounds, padding, w, h)
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < w and 0 <= yi < h and land_mask[yi][xi]:
            ok += 1
    return ok


def main() -> None:
    src_path = BASE / "us-map-wikimedia.png"
    if not src_path.exists():
        raise SystemExit(f"Missing {src_path}")

    wiki = Image.open(src_path)
    w, h = wiki.size

    styled = style_wikimedia(wiki)
    usa_path = BASE / "us-map-styled.png"
    styled.save(usa_path, optimize=True)

    ohio = crop_region(styled, OHIO_BOUNDS, USA_BOUNDS, USA_PADDING)
    ohio_path = BASE / "ohio-region-map.png"
    ohio.save(ohio_path, optimize=True)

    midwest = crop_region(styled, MIDWEST_BOUNDS, USA_BOUNDS, USA_PADDING)
    midwest_path = BASE / "midwest-region-map.png"
    midwest.save(midwest_path, optimize=True)

    config = {
        "usa": {
            "src": "/static/runway/us-map-styled.png",
            "width": styled.width,
            "height": styled.height,
            "bounds": USA_BOUNDS,
            "padding": USA_PADDING,
            "projection": "equirectangular+padded",
            "borderSource": "us-map-wikimedia.png native pixels",
        },
        "ohio": {
            "src": "/static/runway/ohio-region-map.png",
            "width": ohio.width,
            "height": ohio.height,
            "bounds": OHIO_BOUNDS,
            "padding": {"left": 0, "top": 0, "right": 0, "bottom": 0},
            "projection": "crop",
            "parent": "usa",
        },
        "midwest": {
            "src": "/static/runway/midwest-region-map.png",
            "width": midwest.width,
            "height": midwest.height,
            "bounds": MIDWEST_BOUNDS,
            "padding": {"left": 0, "top": 0, "right": 0, "bottom": 0},
            "projection": "crop",
            "parent": "usa",
        },
    }
    with open(BASE / "map-config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("usa", styled.size, "->", usa_path.name)
    print("ohio", ohio.size, "->", ohio_path.name)
    print("midwest", midwest.size, "->", midwest_path.name)
    print("bounds", USA_BOUNDS)
    print("padding", USA_PADDING)


if __name__ == "__main__":
    main()