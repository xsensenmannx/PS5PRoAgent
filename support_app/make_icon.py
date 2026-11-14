"""Erzeugt das Icon der Hilfe-App.

Ein Motiv, drei Ausgaben:
  icon.png       512x512, vollflächig (Store/Launcher-Fallback)
  icon_fg.png    432x432, transparente Vorderebene (adaptives Icon)
  icon_bg.png    432x432, Verlauf als Hintergrund (adaptives Icon)
  icon.ico       Windows-Symbole 16-256 px

Gezeichnet wird vierfach vergrößert und danach verkleinert; dadurch sind die
Kanten glatt, ohne dass eine SVG-Abhängigkeit nötig wäre.

    python make_icon.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

S = 2048  # Arbeitsfläche, 4x der Zielgröße 512
HIER = os.path.dirname(os.path.abspath(__file__))

BLAU = (59, 130, 246, 255)
BLAU_HELL = (110, 168, 255, 255)
WEISS = (255, 255, 255, 255)
BG_OBEN = (9, 16, 30)
BG_UNTEN = (23, 42, 68)


def verlauf(w, h, oben, unten):
    """Senkrechter Verlauf ohne numpy."""
    spalte = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        spalte.putpixel(
            (0, y),
            tuple(int(a + (b - a) * t) for a, b in zip(oben, unten)),
        )
    return spalte.resize((w, h))


def marke(px, mit_schatten=True):
    """Lupe mit Euro-Zeichen, zentriert auf transparenter Fläche."""
    bild = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    cx = cy = px / 2
    r = px * 0.285          # Ringradius
    strich = px * 0.080     # Ringstärke

    if mit_schatten:
        schatten = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        sd = ImageDraw.Draw(schatten)
        sd.ellipse(
            (cx - r * 1.1, cy - r * 0.95, cx + r * 1.15, cy + r * 1.25),
            fill=(0, 0, 0, 120),
        )
        schatten = schatten.filter(ImageFilter.GaussianBlur(px * 0.045))
        bild.alpha_composite(schatten, (0, int(px * 0.02)))

    d = ImageDraw.Draw(bild)

    # Angedeutete Radar-Schleife oben rechts, bewusst blass.
    for faktor, alpha in ((1.22, 80), (1.38, 45)):
        rr = r * faktor
        d.arc(
            (cx - rr, cy - rr, cx + rr, cy + rr),
            start=-40, end=30,
            fill=(110, 168, 255, alpha),
            width=max(int(px * 0.010), 2),
        )

    # Glasfläche dezent aufhellen, dann der Ring im Verlauf.
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(59, 130, 246, 30))
    ring_maske = Image.new("L", (px, px), 0)
    ImageDraw.Draw(ring_maske).ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        outline=255, width=int(strich),
    )
    bild.paste(verlauf(px, px, (124, 178, 255), (37, 99, 235)).convert("RGBA"),
               (0, 0), ring_maske)


    # Euro-Zeichen
    h = r * 1.08
    w = r * 0.72
    lw = max(int(px * 0.044), 3)
    d.arc(
        (cx - w * 0.58, cy - h / 2, cx + w * 0.58, cy + h / 2),
        start=40, end=320, fill=WEISS, width=lw,
    )
    for versatz, breite in ((-h * 0.11, 1.02), (h * 0.15, 0.92)):
        d.line(
            (cx - w * 0.60, cy + versatz, cx - w * 0.60 + w * breite, cy + versatz),
            fill=WEISS, width=lw,
        )

    # Griff, nach dem Ring gezeichnet, damit er sauber anschließt.
    winkel = math.radians(45)
    start = r * 0.92
    ende = r + px * 0.115
    x1, y1 = cx + start * math.cos(winkel), cy + start * math.sin(winkel)
    x2, y2 = cx + ende * math.cos(winkel), cy + ende * math.sin(winkel)
    griff_maske = Image.new("L", (px, px), 0)
    gm = ImageDraw.Draw(griff_maske)
    gm.line((x1, y1, x2, y2), fill=255, width=int(strich))
    for x, y in ((x1, y1), (x2, y2)):
        gm.ellipse(
            (x - strich / 2, y - strich / 2, x + strich / 2, y + strich / 2),
            fill=255,
        )
    bild.paste(verlauf(px, px, (90, 150, 245), (37, 99, 235)).convert("RGBA"),
               (0, 0), griff_maske)

    return bild


def icon_png():
    grund = verlauf(S, S, BG_OBEN, BG_UNTEN).convert("RGBA")
    grund.alpha_composite(marke(S))
    return grund.convert("RGB").resize((512, 512), Image.LANCZOS)


def adaptive():
    vorn = marke(S, mit_schatten=False)
    vorn = vorn.crop((int(S * 0.08), int(S * 0.08), int(S * 0.92), int(S * 0.92)))
    vorn = vorn.resize((432, 432), Image.LANCZOS)
    hinten = verlauf(432, 432, BG_OBEN, BG_UNTEN).convert("RGBA")
    return vorn, hinten


def main():
    bild = icon_png()
    bild.save(os.path.join(HIER, "icon.png"))

    vorn, hinten = adaptive()
    vorn.save(os.path.join(HIER, "icon_fg.png"))
    hinten.save(os.path.join(HIER, "icon_bg.png"))

    bild.save(
        os.path.join(HIER, "icon.ico"),
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    for name in ("icon.png", "icon_fg.png", "icon_bg.png", "icon.ico"):
        pfad = os.path.join(HIER, name)
        print("%-12s %6d Bytes" % (name, os.path.getsize(pfad)))


if __name__ == "__main__":
    main()
