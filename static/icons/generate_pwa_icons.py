#!/usr/bin/env python3
"""Generate PWA icons — solid pin-P from logo (no roof line, no inner map-pin dot)."""

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / 'logo.png'
OUT_DIR = Path(__file__).resolve().parent
BRAND = (0, 76, 140)
CYAN = (0, 150, 214)
INNER_DOT = (178, 205, 16)  # inner circle stroke in logo pin — removed
BOWL_SEED = (175, 195)  # inside P counter — keep as negative space when possible


def _cyan_mask(arr):
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    return (a > 40) & (g > 120) & (b > 120) & (r < 140)


def _flood(mask, start):
    h, w = mask.shape
    seen = np.zeros(mask.shape, bool)
    if not mask[start[1], start[0]]:
        return seen
    q = deque([start])
    seen[start[1], start[0]] = True
    while q:
        cy, cx = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return seen


def _largest_pin_component(stroke):
    h, w = stroke.shape
    visited = np.zeros(stroke.shape, bool)
    best = []
    for sy in range(h - 1, 115, -1):
        for sx in range(135, 235):
            if not stroke[sy, sx] or visited[sy, sx]:
                continue
            comp = []
            q = deque([(sy, sx)])
            visited[sy, sx] = True
            while q:
                cy, cx = q.popleft()
                comp.append((cy, cx))
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and stroke[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((ny, nx))
            if len(comp) > len(best):
                best = comp
    out = np.zeros(stroke.shape, bool)
    for cy, cx in best:
        out[cy, cx] = True
    return out


def _strip_roof_and_dot(mask):
    h, w = mask.shape
    for y in range(h):
        xs = np.where(mask[y])[0]
        if not len(xs):
            continue
        xmin, xmax = xs.min(), xs.max()
        width = xmax - xmin + 1
        if y < 145 and xmin >= 215:
            mask[y, xs] = False
        elif y < 132 and xmax >= 240 and width < 55:
            mask[y, xs] = False
    mask[:168] = False
    cx, cy, r = INNER_DOT
    yy, xx = np.ogrid[:h, :w]
    mask[((xx - cx) ** 2 + (yy - cy) ** 2) <= r * r] = False
    return mask


def build_master():
    arr = np.array(Image.open(LOGO).convert('RGBA'))
    stroke = _cyan_mask(arr)
    stroke[:, 252:] = False
    mask = _largest_pin_component(stroke)
    mask = _strip_roof_and_dot(mask)

    mimg = Image.fromarray((mask.astype(np.uint8) * 255))
    for _ in range(7):
        mimg = mimg.filter(ImageFilter.MaxFilter(7))
    solid = np.array(mimg) > 128

    inv = ~solid
    h, w = inv.shape
    exterior = np.zeros(inv.shape, bool)
    for cy, cx in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)):
        if inv[cy, cx]:
            exterior |= _flood(inv, (cx, cy))
    holes = inv & ~exterior
    solid = solid | holes

    # Smooth bottom spur
    eroded = np.array(Image.fromarray((solid.astype(np.uint8) * 255)).filter(ImageFilter.MinFilter(3))) > 128
    solid = eroded

    ys, xs = np.where(solid)
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    for y in range(y0, y0 + 10):
        row = np.where(solid[y])[0]
        if len(row) and row.min() >= 205:
            solid[y, row] = False

    ys, xs = np.where(solid)
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    pad = 18
    ch, cw = y1 - y0 + 1, x1 - x0 + 1
    side = max(cw, ch) + 2 * pad
    canvas = Image.new('RGB', (side, side), BRAND)
    patch = np.full((ch, cw, 3), BRAND, dtype=np.uint8)
    patch[solid[y0:y1 + 1, x0:x1 + 1]] = CYAN
    canvas.paste(Image.fromarray(patch), (pad, pad))
    return canvas


def write_icons():
    master = build_master()
    for size, name in [(192, 'icon-192.png'), (512, 'icon-512.png'), (180, 'apple-touch-icon.png')]:
        margin = int(size * 0.14)
        inner = size - 2 * margin
        scaled = master.resize((inner, inner), Image.Resampling.LANCZOS)
        out = Image.new('RGB', (size, size), BRAND)
        out.paste(scaled, (margin, margin))
        out.save(OUT_DIR / name, 'PNG')
        print('wrote', name)


if __name__ == '__main__':
    write_icons()