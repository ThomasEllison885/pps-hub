#!/usr/bin/env python3
"""
Build Runway map PNGs from us-land.json — one projection for land, borders, and airport dots.

Basic principle: geography (GeoJSON) and gameplay (lat/lon → pixel) share identical bounds
and equirectangular math. No Wikimedia pixel guessing.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent

OHIO_BOUNDS = {
    "lonMin": -87.35,
    "lonMax": -78.75,
    "latMin": 36.15,
    "latMax": 44.35,
}

OCEAN = (7, 21, 37)
LAND = (52, 98, 82)
BORDER = (186, 232, 205)
COAST = (125, 178, 155)

TARGET_WIDTH = 1920


def load_geo() -> dict:
    path = BASE / "us-land.json"
    with open(path) as f:
        return json.load(f)


def map_height(bounds: dict, width: int) -> int:
    lat_span = bounds["latMax"] - bounds["latMin"]
    lon_span = bounds["lonMax"] - bounds["lonMin"]
    return max(400, round(width * lat_span / lon_span))


def project(lat: float, lon: float, bounds: dict, w: int, h: int) -> tuple[float, float]:
    x = (lon - bounds["lonMin"]) / (bounds["lonMax"] - bounds["lonMin"]) * w
    y = (bounds["latMax"] - lat) / (bounds["latMax"] - bounds["latMin"]) * h
    return x, y


def ring_to_pixels(ring: list, bounds: dict, w: int, h: int) -> list[tuple[int, int]]:
    pts = []
    for lon, lat in ring:
        x, y = project(lat, lon, bounds, w, h)
        pts.append((int(round(x)), int(round(y))))
    return pts


def render_map(bounds: dict, geo: dict, width: int) -> Image.Image:
    height = map_height(bounds, width)
    img = Image.new("RGBA", (width, height), OCEAN + (255,))
    draw = ImageDraw.Draw(img)

    for ring in geo.get("silhouette", []):
        if len(ring) < 3:
            continue
        pts = ring_to_pixels(ring, bounds, width, height)
        draw.polygon(pts, fill=LAND + (255,), outline=COAST + (255,))

    stroke = max(1, int(width / 1400))
    for ring in geo.get("borders", []):
        if len(ring) < 2:
            continue
        pts = ring_to_pixels(ring, bounds, width, height)
        draw.line(pts, fill=BORDER + (255,), width=stroke, joint="curve")

    return img


def crop_region(img: Image.Image, crop_bounds: dict, full_bounds: dict) -> Image.Image:
    w, h = img.size
    x1, y1 = project(crop_bounds["latMin"], crop_bounds["lonMin"], full_bounds, w, h)
    x2, y2 = project(crop_bounds["latMax"], crop_bounds["lonMax"], full_bounds, w, h)
    pad = 18
    left = int(max(0, min(x1, x2) - pad))
    top = int(max(0, min(y1, y2) - pad))
    right = int(min(w, max(x1, x2) + pad))
    bottom = int(min(h, max(y1, y2) + pad))
    crop = img.crop((left, top, right, bottom))
    scale = max(1, int(1400 / max(crop.size)))
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    return crop


def verify_airports(bounds: dict, w: int, h: int) -> None:
    checks = [
        ("CMH", 39.99, -82.89),
        ("LUK", 39.10, -84.42),
        ("DAY", 39.90, -84.22),
        ("MIA", 25.79, -80.29),
        ("SEA", 47.45, -122.31),
    ]
    for code, lat, lon in checks:
        x, y = project(lat, lon, bounds, w, h)
        print(f"  {code}: ({x:.0f}, {y:.0f})")


def main() -> None:
    geo = load_geo()
    usa_bounds = geo["bounds"]

    styled = render_map(usa_bounds, geo, TARGET_WIDTH)
    usa_path = BASE / "us-map-styled.png"
    styled.save(usa_path, optimize=True)

    ohio = crop_region(styled, OHIO_BOUNDS, usa_bounds)
    ohio_path = BASE / "ohio-region-map.png"
    ohio.save(ohio_path, optimize=True)

    config = {
        "usa": {
            "src": "/static/runway/us-map-styled.png",
            "width": styled.width,
            "height": styled.height,
            "bounds": usa_bounds,
            "geoSource": "us-land.json",
        },
        "ohio": {
            "src": "/static/runway/ohio-region-map.png",
            "width": ohio.width,
            "height": ohio.height,
            "bounds": OHIO_BOUNDS,
            "geoSource": "us-land.json",
        },
    }
    with open(BASE / "map-config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("usa", styled.size, "bounds", usa_bounds)
    print("ohio", ohio.size)
    print("airport projection check:")
    verify_airports(usa_bounds, styled.width, styled.height)


if __name__ == "__main__":
    main()