#!/usr/bin/env python3
"""Erzeugt die neutralen Play-Assets (Icon, Adaptive Icon, Feature-Grafik).

Die Sideload-Assets unter ``icon.png`` und ``assets/icon_*.png`` werden
absichtlich nicht angefasst. Ausgabe:

    assets/play/icon.png            512x512, Legacy-Icon
    assets/play/icon_fg.png         432x432, adaptiver Vordergrund
    assets/play/icon_bg.png         432x432, adaptiver Hintergrund
    assets/play/notify_icon.png     432x432, weisse Statusleisten-Silhouette
    store/assets/icon-512.png       Play-Store-Icon
    store/assets/feature-1024x500.png

Das Motiv ist ein Radar mit Preis-Pfeil. Es enthaelt bewusst keine
PlayStation-Formen (Dreieck/Kreis/Kreuz/Quadrat) und keine Sony-Marke.
"""
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PLAY = ROOT / "assets" / "play"
STORE = ROOT / "store" / "assets"

INK = (5, 13, 20)
INK2 = (9, 31, 43)
CYAN = (48, 190, 235)
CYAN_DIM = (31, 112, 145)
MINT = (51, 220, 160)
WHITE = (238, 250, 255)


def font(size, bold=True):
    names = ["segoeuib.ttf" if bold else "segoeui.ttf",
             "arialbd.ttf" if bold else "arial.ttf"]
    for name in names:
        path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def gradient(size):
    im = Image.new("RGB", (size, size), INK)
    px = im.load()
    for y in range(size):
        for x in range(size):
            # diagonal, sehr dunkel; bleibt auch bei kleinen Icons ruhig.
            t = (x + y) / (2.0 * max(1, size - 1))
            px[x, y] = (int(INK[0] * (1 - t) + INK2[0] * t),
                        int(INK[1] * (1 - t) + INK2[1] * t),
                        int(INK[2] * (1 - t) + INK2[2] * t))
    return im


def radar_mark(size, transparent=False, monochrome=False):
    """Zeichnet Ringe, Peilpunkte und einen Preis-Pfeil."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = size * 0.50, size * 0.53
    r = size * 0.335
    ring = WHITE if monochrome else CYAN
    dim = (255, 255, 255, 120) if monochrome else (*CYAN_DIM, 170)

    # Radar-Sweep als sehr transparentes Segment.
    if not monochrome:
        pts = [(cx, cy)]
        for i in range(22):
            a = math.radians(-72 + i * 2.8)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        d.polygon(pts, fill=(48, 190, 235, 34))

    for frac, width in ((1.0, max(2, int(size * 0.012))),
                        (0.76, max(1, int(size * 0.006))),
                        (0.52, max(1, int(size * 0.004)))):
        box = (cx - r * frac, cy - r * frac, cx + r * frac, cy + r * frac)
        d.ellipse(box, outline=ring if frac == 1.0 else dim, width=width)

    # Peilpunkte an den Diagonalen, keine vier PlayStation-Formen.
    for angle, color in ((-48, MINT), (132, MINT), (32, CYAN), (208, CYAN)):
        a = math.radians(angle)
        x = cx + r * 0.78 * math.cos(a)
        y = cy + r * 0.78 * math.sin(a)
        rr = max(3, size * 0.018)
        d.ellipse((x - rr, y - rr, x + rr, y + rr),
                  fill=(255, 255, 255, 230) if monochrome else (*color, 255))

    # Zentraler Preis-Pfeil nach unten.
    w = size * 0.105
    top = cy - size * 0.105
    d.line([(cx - w, top), (cx, top + w), (cx + w, top)],
           fill=WHITE if monochrome else WHITE, width=max(4, int(size * 0.055)),
           joint="curve")
    d.line([(cx, top + w * 0.55), (cx, top + w * 2.3)],
           fill=WHITE if monochrome else WHITE, width=max(4, int(size * 0.055)))

    # Kleiner Mittelpunkt, damit die Marke auch bei 48 px lesbar bleibt.
    d.ellipse((cx - size * 0.018, cy - size * 0.018,
               cx + size * 0.018, cy + size * 0.018),
              fill=WHITE)
    return im


def rounded_icon(size=512):
    base = gradient(size).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                           radius=int(size * 0.22), fill=255)
    base.putalpha(mask)
    mark = radar_mark(size)
    base.alpha_composite(mark)
    return base


def adaptive_foreground(size=432):
    # Inhalt bleibt in der Android-Sicherheitszone (ca. 66 %).
    inner = int(size * 0.76)
    mark = radar_mark(inner)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(mark, ((size - inner) // 2, (size - inner) // 2))
    return canvas


def adaptive_background(size=432):
    im = gradient(size).convert("RGBA")
    # dezente Horizontlinien, kein Sony-Motiv
    d = ImageDraw.Draw(im)
    for y in range(0, size, max(8, size // 24)):
        d.line([(0, y), (size, y)], fill=(30, 90, 110, 22), width=1)
    return im


def notify_icon(size=432):
    mark = radar_mark(size, monochrome=True)
    # Statusleiste erwartet eine weisse Silhouette; Alpha bleibt erhalten.
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(mark)
    return out


def feature():
    w, h = 1024, 500
    im = gradient(max(w, h)).resize((w, h)).convert("RGB")
    d = ImageDraw.Draw(im)
    # Radar-Asset links, gross und ruhig.
    icon = rounded_icon(300)
    im.paste(icon, (54, 100), icon)
    title_f = font(58, True)
    sub_f = font(27, False)
    tag_f = font(20, True)
    d.text((398, 108), "KONSOLEN-RADAR", font=title_f, fill=WHITE)
    d.text((400, 184), "Preisalarm für die PS5 Pro 2 TB", font=sub_f, fill=(190, 216, 228))
    d.text((400, 242), "Bestand  ·  Preis  ·  Beweis", font=tag_f, fill=MINT)
    d.text((400, 284), "Kein Konto. Keine Werbung. Keine Kaufzusage.", font=tag_f,
           fill=(150, 180, 194))
    # feine Linie und Randnotiz, keine Markenformen
    d.line([(400, 334), (940, 334)], fill=(50, 150, 175), width=2)
    d.text((400, 352), "42 Händler in DE + AT", font=font(20, False),
           fill=(190, 216, 228))
    return im


def main():
    PLAY.mkdir(parents=True, exist_ok=True)
    STORE.mkdir(parents=True, exist_ok=True)

    icon = rounded_icon(512)
    icon.save(PLAY / "icon.png")
    adaptive_foreground().save(PLAY / "icon_fg.png")
    adaptive_background().save(PLAY / "icon_bg.png")
    notify_icon().save(PLAY / "notify_icon.png")
    icon.save(STORE / "icon-512.png")
    feature().save(STORE / "feature-1024x500.png", optimize=True)

    for p in (PLAY / "icon.png", PLAY / "icon_fg.png", PLAY / "icon_bg.png",
              PLAY / "notify_icon.png", STORE / "icon-512.png",
              STORE / "feature-1024x500.png"):
        im = Image.open(p)
        print(f"{p.relative_to(ROOT)} {im.size} {im.mode} {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
