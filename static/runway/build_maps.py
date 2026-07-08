#!/usr/bin/env python3
"""Build Runway map PNGs with state borders baked in (GeoJSON aligned to raster bounds)."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent

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
BORDER = (186, 232, 205)
COAST = (140, 195, 170)


def project(lat: float, lon: float, bounds: dict, w: int, h: int) -> tuple[float, float]:
    x = (lon - bounds["lonMin"]) / (bounds["lonMax"] - bounds["lonMin"]) * w
    y = (bounds["latMax"] - lat) / (bounds["latMax"] - bounds["latMin"]) * h
    return x, y


def style_us_map(src: Image.Image) -> Image.Image:
    """Classify Wikimedia land/ocean; state lines drawn separately from GeoJSON."""
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
            if lum >= 200:
                opx[x, y] = LAND + (255,)
            elif lum >= 150:
                opx[x, y] = COAST + (255,)
            elif lum >= 90:
                opx[x, y] = LAND_EDGE + (255,)
            else:
                opx[x, y] = LAND_EDGE + (255,)

    return out


def draw_state_borders(img: Image.Image, bounds: dict) -> Image.Image:
    """Overlay state boundaries from us-states.json using the same projection as airport dots."""
    states_path = BASE / "us-states.json"
    if not states_path.exists():
        return img

    with open(states_path) as f:
        data = json.load(f)

    w, h = img.size
    draw = ImageDraw.Draw(img)
    stroke = max(1, int(w / 1100))

    for ring in data.get("paths", []):
        if not ring or len(ring) < 2:
            continue
        pts = []
        for lon, lat in ring:
            if lat < bounds["latMin"] - 2 or lat > bounds["latMax"] + 2:
                continue
            if lon < bounds["lonMin"] - 2 or lon > bounds["lonMax"] + 2:
                continue
            x, y = project(lat, lon, bounds, w, h)
            pts.append((x, y))
        if len(pts) >= 2:
            draw.line(pts, fill=BORDER + (255,), width=stroke, joint="curve")

    return img


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
    styled = draw_state_borders(styled, USA_BOUNDS)

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