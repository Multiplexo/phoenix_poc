"""Erzeugt die Hintergrundbilder (Midnight Navy mit weichem Licht und Lichtstreifen) für die PowerPoint-Fassung.
Die HTML-Fassung baut dieselben Effekte mit CSS nach. Einmal ausführen: python deck/make_backgrounds.py"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080
NAVY = np.array([16, 29, 53], float)
CYAN = np.array([22, 200, 219], float)
GOLD = np.array([203, 167, 106], float)
OUT = Path(__file__).with_name("assets")


def glow(cx, cy, r, color, strength):
    y, x = np.mgrid[0:H, 0:W]
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / r
    a = np.clip(1 - d, 0, 1) ** 2 * strength
    return a[..., None] * (color - NAVY)


def streak(img, x0, y0, x1, y1, color, width, blur):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).line([(x0, y0), (x1, y1)], fill=tuple(int(c) for c in color) + (255,), width=width)
    soft = layer.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(soft)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1)))


def base(glows):
    arr = np.broadcast_to(NAVY, (H, W, 3)).copy()
    for g in glows:
        arr += g
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).convert("RGBA")


# Titelfolie: Licht oben rechts, ein Lichtstreifenpaar (Cyan + Gold) aus der Ecke unten rechts
t = base([glow(1500, 120, 900, np.array([40, 70, 120], float), 0.9)])
streak(t, 640, 1080, 1920, 760, CYAN, 3, 10)
streak(t, 1580, 860, 1880, 420, GOLD, 2, 8)
t.convert("RGB").save(OUT / "bg_titel.png", optimize=True)

# Inhaltsfolie: nur weiches Licht oben rechts, kein Streifen (ruhig)
c = base([glow(1650, 0, 1000, np.array([34, 58, 100], float), 0.8)])
c.convert("RGB").save(OUT / "bg_inhalt.png", optimize=True)
print("ok")
