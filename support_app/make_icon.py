"""Erzeugt das Icon der Hilfe-App.

Motiv: Sprechblase (Hilfe/Antwort) mit Radar-Ping und bernsteinfarbenem
Treffer-Punkt (Alarm). Drei Ausgaben aus einer Zeichnung:

  icon.png       512x512, vollflaechig (Store/Launcher-Fallback)
  icon_fg.png    432x432, transparente Vorderebene (adaptives Icon)
  icon_bg.png    432x432, Verlauf als Hintergrund (adaptives Icon)
  icon.ico       Windows-Symbole 16-256 px

Gezeichnet wird vierfach vergroessert und danach verkleinert; dadurch sind die
Kanten glatt, ohne dass eine SVG-Abhaengigkeit noetig waere.

    python make_icon.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

S = 2048  # Arbeitsflaeche, 4x der Zielgroesse 512
HIER = os.path.dirname(os.path.abspath(__file__))
NEIGUNG = -7  # Grad; gibt dem Motiv Sticker-Charakter statt Stock-Optik

# Sprechblase: hell oben links, satt unten rechts.
BLAU_OBEN = (118, 176, 255)
BLAU_UNTEN = (40, 102, 232)
# Hintergrund: fast schwarzes Navy mit blauem Schimmer.
BG_OBEN = (8, 13, 26)
BG_UNTEN = (24, 41, 70)
WEISS = (255, 255, 255, 255)
AMBER = (255, 176, 46, 255)


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


def blasenmaske(px):
    """Sprechblase mit Schwanz unten links als Maske."""
    maske = Image.new("L", (px, px), 0)
    d = ImageDraw.Draw(maske)

    bw, bh = px * 0.615, px * 0.465
    x0, y0 = (px - bw) / 2, px * 0.205
    x1, y1 = x0 + bw, y0 + bh
    radius = bh * 0.30
    d.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=255)

    # Schwanz: breite Basis in der Blase, Spitze unten links.
    basis_links, basis_rechts = x0 + bw * 0.17, x0 + bw * 0.37
    spitze = (x0 + bw * 0.10, y1 + bh * 0.26)
    d.polygon([(basis_links, y1 - 2), (basis_rechts, y1 - 2), spitze], fill=255)
    return maske, (x0, y0, x1, y1, bw, bh)


def marke(px, mit_schatten=True):
    """Sprechblase mit Ping, zentriert auf transparenter Flaeche."""
    bild = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    maske, (x0, y0, x1, y1, bw, bh) = blasenmaske(px)

    if mit_schatten:
        schatten = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        schatten.paste((0, 0, 0, 135), (0, int(px * 0.022)), maske)
        schatten = schatten.filter(ImageFilter.GaussianBlur(px * 0.035))
        bild.alpha_composite(schatten)

    # Blasenflaeche im Verlauf, dazu ein sehr weiches Licht oben links.
    bild.paste(verlauf(px, px, BLAU_OBEN, BLAU_UNTEN).convert("RGBA"), (0, 0), maske)
    licht = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    ld = ImageDraw.Draw(licht)
    ld.ellipse(
        (x0 - bw * 0.10, y0 - bh * 0.55, x1 - bw * 0.20, y0 + bh * 0.55),
        fill=(255, 255, 255, 46),
    )
    licht = licht.filter(ImageFilter.GaussianBlur(px * 0.055))
    licht.putalpha(Image.composite(licht.getchannel("A"), Image.new("L", (px, px), 0), maske))
    bild.alpha_composite(licht)

    # Zielscheibe: zwei Ringe, in der Mitte der amberne Treffer.
    cx = (x0 + x1) / 2
    cy = y0 + bh * 0.50
    dot = px * 0.043
    strich = int(px * 0.024)
    z = ImageDraw.Draw(bild)
    # Aussenring als vier Radar-Segmente, innen ein geschlossener Ring.
    r_aussen = px * 0.158
    for start in (0, 90, 180, 270):
        z.arc(
            (cx - r_aussen, cy - r_aussen, cx + r_aussen, cy + r_aussen),
            start=start + 10, end=start + 70,
            fill=(255, 255, 255, 150), width=strich,
        )
    r_innen = px * 0.092
    z.ellipse(
        (cx - r_innen, cy - r_innen, cx + r_innen, cy + r_innen),
        outline=(255, 255, 255, 250), width=strich,
    )

    gluehen = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gluehen)
    gr = dot * 1.55
    gd.ellipse((cx - gr, cy - gr, cx + gr, cy + gr), fill=(255, 176, 46, 95))
    gluehen = gluehen.filter(ImageFilter.GaussianBlur(px * 0.013))
    bild.alpha_composite(gluehen)

    # Der Punkt sitzt auf den Boegen und bleibt auch bei 16 px sichtbar.
    d = ImageDraw.Draw(bild)
    d.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=AMBER)
    return bild


def icon_png():
    grund = verlauf(S, S, BG_OBEN, BG_UNTEN).convert("RGBA")

    # Blauer Schimmer hinter dem Motiv, damit das Icon nicht flach wirkt.
    schimmer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(schimmer)
    r = S * 0.40
    sd.ellipse((S / 2 - r, S * 0.44 - r, S / 2 + r, S * 0.44 + r), fill=(58, 118, 214, 74))
    schimmer = schimmer.filter(ImageFilter.GaussianBlur(S * 0.10))
    grund.alpha_composite(schimmer)

    grund.alpha_composite(marke(S).rotate(NEIGUNG, resample=Image.BICUBIC))
    return grund.convert("RGB").resize((512, 512), Image.LANCZOS)


def adaptive():
    vorn = marke(S, mit_schatten=False)
    vorn = vorn.rotate(NEIGUNG, resample=Image.BICUBIC)
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
