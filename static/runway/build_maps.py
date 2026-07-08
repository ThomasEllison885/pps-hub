#!/usr/bin/env python3
"""Build Runway map PNGs from Wikimedia blank US map (borders baked in, no SVG overlay)."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent

# Continental US on Wikimedia blank map (states_only) — aligned to raster pixels.
USA_BOUNDS = {
    "lonMin": -124.85,
    "lonMax": -66.70,
    "latMin": 24.30,
    "latMax": 49.55,
}

OHIO_BOUNDS = {
    "lonMin": -87.35,
    "lonMax": -78.75,
    "latMin": 36.15,
    "latMax": 44.35,
}

OCEAN = (7, 21, 37)
LAND = (52, 98, 82)
LAND_EDGE = (42, 78, 66)
BORDER = (168, 215, 188)
COAST = (140, 195, 170)


def style_us_map(src: Image.Image) -> Image.Image:
    """Preserve Wikimedia's native state lines; do not draw GeoJSON overlays."""
    src = src.convert("RGBA")
    w, h = src.size
    out = Image.new("RGBA", (w, h), OCEAN + (255,))
    spx = src.load()
    opx = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b, a = spx[x, y]
            if a < 25:
                continue
            lum = (r + g + b) / 3
            # Wikimedia: bright gray = land interior, darker thin lines = state borders.
            if lum >= 175:
                opx[x, y] = LAND + (255,)
            elif lum >= 95:
                opx[x, y] = BORDER + (255,)
            elif lum >= 55:
                opx[x, y] = COAST + (255,)
            else:
                opx[x, y] = LAND_EDGE + (255,)

    return out


def project(lat: float, lon: float, bounds: dict, w: int, h: int) -> tuple[float, float]:
    x = (lon - bounds["lonMin"]) / (bounds["lonMax"] - bounds["lonMin"]) * w
    y = (bounds["latMax"] - lat) / (bounds["latMax"] - bounds["latMin"]) * h
    return x, y


def crop_region(img: Image.Image, bounds: dict, full_bounds: dict) -> Image.Image:
    w, h = img.size
    x1, y1 = project(bounds["latMin"], bounds["lonMin"], full_bounds, w, h)
    x2, y2 = project(bounds["latMax"], bounds["lonMax"], full_bounds, w, h)
    pad = 20
    left = int(max(0, min(x1, x2) - pad))
    top = int(max(0, min(y1, y2) - pad))
    right = int(min(w, max(x1, x2) + pad))
    bottom = int(min(h, max(y1, y2) + pad))
    crop = img.crop((left, top, right, bottom))
    scale = max(1, int(1400 / max(crop.size)))
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    return crop


def main() -> None:
    src_path = BASE / "us-map-wikimedia.png"
    if not src_path.exists():
        raise SystemExit(f"Missing {src_path} — download Wikimedia blank US map first.")

    styled = style_us_map(Image.open(src_path))
    usa_path = BASE / "us-map-styled.png"
    styled.save(usa_path, optimize=True)

    ohio = crop_region(styled, OHIO_BOUNDS, USA_BOUNDS)
    ohio_path = BASE / "ohio-region-map.png"
    ohio.save(ohio_path, optimize=True)

    config = {
        "usa": {
            "src": "/static/runway/us-map-styled.png",
            "width": styled.width,
            "height": styled.height,
            "bounds": USA_BOUNDS,
        },
        "ohio": {
            "src": "/static/runway/ohio-region-map.png",
            "width": ohio.width,
            "height": ohio.height,
            "bounds": OHIO_BOUNDS,
        },
    }
    with open(BASE / "map-config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("usa", styled.size, "->", usa_path.name)
    print("ohio", ohio.size, "->", ohio_path.name)


if __name__ == "__main__":
    main()