#!/usr/bin/env python3
"""
BARQ Icon Generator
===================
Renders the BARQ app icon: a glowing neural-node hexagon emblem above a
cyan "BARQ" wordmark on a dark rounded tile — matching the app's
neon-cyan cybernetic theme (StartupSequence / Sidebar branding).

Outputs (into <repo>/resources/):
  icon.png   512x512  — Electron BrowserWindow icon (src/main/index.ts)
  icon.ico   multi-size (16..256) — Windows exe / desktop shortcut icon
  icon.svg   vector source for future branding use

Requires Pillow (already in python/requirements.txt).
Usage:  python scripts/generate_barq_icon.py
"""

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "resources"
OUT.mkdir(parents=True, exist_ok=True)

SIZE = 1024

# ── Palette (matches app theme) ──────────────────────────────────────────
CYAN_BRIGHT = (140, 250, 255)   # #8CFAFF  highlight
CYAN_MID    = (34, 211, 238)    # #22D3EE  brand cyan
CYAN_DIM    = (8, 145, 178)     # #0891B2  deep cyan
BG_TOP      = (13, 18, 34)      # tile top
BG_BOTTOM   = (4, 6, 12)        # tile bottom
RING_GLOW   = (0, 200, 230)     # hexagon glow


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def v_gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / max(h - 1, 1)))
    return img


def radial_glow(w, h, cx, cy, radius, color, max_alpha=110):
    """Soft radial glow sprite (RGBA)."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    steps = 48
    for i in range(steps, 0, -1):
        r = radius * i / steps
        alpha = int(max_alpha * (1 - i / steps) ** 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=(color[0], color[1], color[2], alpha))
    return img.filter(ImageFilter.GaussianBlur(radius / 6))


def polygon_points(cx, cy, radius, n=6, start_deg=-90):
    pts = []
    for i in range(n):
        ang = math.radians(start_deg + i * 360.0 / n)
        pts.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    return pts


def load_font(size, want_bold=True):
    """Best-effort techy font: Bahnschrift (variable) → Impact → Segoe UI Black → Arial Bold."""
    candidates = [
        "C:/Windows/Fonts/bahnschrift.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/seguibl.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            f = ImageFont.truetype(path, size)
            if "bahnschrift" in path.lower() and want_bold:
                try:
                    f.set_variation_by_axes([700])
                except Exception:
                    try:
                        f.set_variation_by_name("Bold")
                    except Exception:
                        pass
            return f
        except Exception:
            continue
    return ImageFont.load_default()


def draw_spaced(d, xy, text, font, fill, tracking=16):
    """Draw text with letter-spacing, centered on xy's x."""
    x, y = xy
    widths = [d.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x -= total / 2
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=font, fill=fill)
        x += w + tracking


# ── Base tile ────────────────────────────────────────────────────────────
base = v_gradient(SIZE, SIZE, BG_TOP, BG_BOTTOM).convert("RGBA")
tile = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(tile)
d.rounded_rectangle([24, 24, SIZE - 24, SIZE - 24], radius=200, fill=(0, 0, 0, 0))
# Draw gradient inside the rounded mask: paint base clipped by mask
mask = Image.new("L", (SIZE, SIZE), 0)
dm = ImageDraw.Draw(mask)
dm.rounded_rectangle([24, 24, SIZE - 24, SIZE - 24], radius=200, fill=255)
tile.paste(base, (0, 0), mask)

# Center spotlight (subtle)
spot = radial_glow(SIZE, SIZE, SIZE // 2, 430, 460, CYAN_DIM, max_alpha=90)
tile = Image.alpha_composite(tile, spot)

# Faint inner border ring
d = ImageDraw.Draw(tile)
d.rounded_rectangle([30, 30, SIZE - 30, SIZE - 30], radius=196,
                    outline=(CYAN_MID[0], CYAN_MID[1], CYAN_MID[2], 46), width=3)

# ── Hexagon emblem (neural node) ─────────────────────────────────────────
HEX_CX, HEX_CY, HEX_R = SIZE // 2, 378, 190
hex_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
hd = ImageDraw.Draw(hex_layer)
hex_pts = polygon_points(HEX_CX, HEX_CY, HEX_R)

# Glow behind hexagon
hex_glow = radial_glow(SIZE, SIZE, HEX_CX, HEX_CY, HEX_R + 60, RING_GLOW, max_alpha=70)
tile = Image.alpha_composite(tile, hex_glow)

# Hexagon stroke (double: bright on top of dim for depth)
hd.polygon(hex_pts, outline=(CYAN_DIM[0], CYAN_DIM[1], CYAN_DIM[2], 120), width=8)
hd.polygon(hex_pts, outline=(CYAN_BRIGHT[0], CYAN_BRIGHT[1], CYAN_BRIGHT[2], 220), width=4)

# Node dots at vertices (knowledge-graph vibe)
for px, py in hex_pts:
    hd.ellipse([px - 13, py - 13, px + 13, py + 13],
               fill=(CYAN_BRIGHT[0], CYAN_BRIGHT[1], CYAN_BRIGHT[2], 255))
    hd.ellipse([px - 13, py - 13, px + 13, py + 13],
               outline=(255, 255, 255, 90), width=3)

# Center node (core) with ring
hd.ellipse([HEX_CX - 34, HEX_CY - 34, HEX_CX + 34, HEX_CY + 34],
           fill=(16, 24, 40, 255))
hd.ellipse([HEX_CX - 34, HEX_CY - 34, HEX_CX + 34, HEX_CY + 34],
           outline=(CYAN_MID[0], CYAN_MID[1], CYAN_MID[2], 255), width=6)
hd.ellipse([HEX_CX - 14, HEX_CY - 14, HEX_CX + 14, HEX_CY + 14],
           fill=(CYAN_BRIGHT[0], CYAN_BRIGHT[1], CYAN_BRIGHT[2], 255))

# Blend hexagon layer into tile (blurred halo first, crisp on top)
halo = hex_layer.filter(ImageFilter.GaussianBlur(18))
tile = Image.alpha_composite(tile, halo)
tile = Image.alpha_composite(tile, hex_layer)

# ── "BARQ" wordmark with gradient + glow ─────────────────────────────────
font = load_font(268)
track = 30
text = "BARQ"
word_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
wd = ImageDraw.Draw(word_layer)

# White text used as a mask for the gradient fill
mask_layer = Image.new("L", (SIZE, SIZE), 0)
wm = ImageDraw.Draw(mask_layer)
draw_spaced(wm, (SIZE // 2, 640), text, font, 255, track)

# Vertical cyan gradient for the fill
grad = v_gradient(SIZE, SIZE, CYAN_BRIGHT, CYAN_DIM).convert("RGBA")
word_layer.paste(grad, (0, 0), mask_layer)

# Glow behind the wordmark
glow_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow_layer)
draw_spaced(gd, (SIZE // 2, 640), text, font, RING_GLOW + (200,), track)
glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(26))
tile = Image.alpha_composite(tile, glow_layer)
tile = Image.alpha_composite(tile, word_layer)

# Gradient underline (like the StartupSequence divider)
line_y = 970
line_half = 300
d = ImageDraw.Draw(tile)
for i in range(line_half):
    t = 1 - abs(i - line_half) / line_half
    color = (CYAN_BRIGHT[0], CYAN_BRIGHT[1], CYAN_BRIGHT[2], int(120 * t))
    d.line([(SIZE // 2 - line_half + i, line_y), (SIZE // 2 - line_half + i + 1, line_y)],
           fill=color, width=3)

# ── Save ─────────────────────────────────────────────────────────────────
img_1024 = tile.convert("RGBA")
img_512 = img_1024.resize((512, 512), Image.LANCZOS)

img_512.save(OUT / "icon.png", "PNG")
img_1024.save(OUT / "icon.ico", format="ICO",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                     (128, 128), (256, 256)])
print(f"[IconGen] wrote {OUT / 'icon.png'}")
print(f"[IconGen] wrote {OUT / 'icon.ico'} (16..256px)")

# ── SVG source (vector) ──────────────────────────────────────────────────
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0d1222"/>
      <stop offset="1" stop-color="#04060c"/>
    </linearGradient>
    <linearGradient id="word" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#8cfaff"/>
      <stop offset="1" stop-color="#0891b2"/>
    </linearGradient>
  </defs>
  <rect x="12" y="12" width="488" height="488" rx="100" fill="url(#tile)"
        stroke="#22d3ee" stroke-opacity="0.18" stroke-width="2"/>
  <g stroke="#22d3ee" fill="none" stroke-linejoin="round">
    <polygon points="256,99 392,178 392,334 256,413 120,334 120,178"
             stroke="#0891b2" stroke-width="6" opacity="0.6"/>
    <polygon points="256,99 392,178 392,334 256,413 120,334 120,178"
             stroke="#8cfaff" stroke-width="3"/>
    <circle cx="256" cy="256" r="22" stroke="#22d3ee" stroke-width="5"/>
    <circle cx="256" cy="256" r="8" fill="#8cfaff" stroke="none"/>
  </g>
  <g fill="#8cfaff">
    <circle cx="256" cy="99" r="7"/><circle cx="392" cy="178" r="7"/>
    <circle cx="392" cy="334" r="7"/><circle cx="256" cy="413" r="7"/>
    <circle cx="120" cy="334" r="7"/><circle cx="120" cy="178" r="7"/>
  </g>
  <text x="256" y="370" text-anchor="middle"
        font-family="Orbitron, Bahnschrift, sans-serif" font-size="132"
        font-weight="700" letter-spacing="14" fill="url(#word)">BARQ</text>
  <line x1="156" y1="486" x2="356" y2="486" stroke="#22d3ee" stroke-opacity="0.55"
        stroke-width="3" stroke-linecap="round"/>
</svg>
'''
(OUT / "icon.svg").write_text(svg, encoding="utf-8")
print(f"[IconGen] wrote {OUT / 'icon.svg'}")
