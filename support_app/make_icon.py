"""Erzeugt das Roboter-Icon der Hilfe-App.

Dunkler Squircle, Metallkopf mit Headset und leuchtend blauen Augen.
Erzeugt icon.png (512), die adaptiven Ebenen icon_fg.png/icon_bg.png (432)
und icon.ico fuer die Windows-EXE. Nur Pillow, keine externen Dateien.
"""
import os

from PIL import Image, ImageDraw, ImageFilter

S = 4  # Supersampling gegen Treppenkanten

NAVY_TOP = (9, 15, 27)
NAVY_BOT = (27, 46, 80)
METALL_TOP = (248, 251, 255)
METALL_BOT = (176, 192, 214)
DARK = (7, 13, 24)
CYAN = (86, 226, 255)
BLUE = (28, 74, 132)
BAND = (78, 122, 172)

HIER = os.path.dirname(os.path.abspath(__file__))


def _verlauf(groesse, oben, unten):
    breite, hoehe = groesse
    streifen = Image.new("RGB", (1, hoehe))
    malen = ImageDraw.Draw(streifen)
    for y in range(hoehe):
        t = y / max(hoehe - 1, 1)
        malen.point((0, y), tuple(
            int(oben[i] + (unten[i] - oben[i]) * t) for i in range(3)))
    return streifen.resize((breite, hoehe))


def _hintergrund(groesse, rund=False, radius=0.235):
    bild = _verlauf((groesse, groesse), NAVY_TOP, NAVY_BOT).convert("RGBA")
    schein = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    malen = ImageDraw.Draw(schein)
    r = groesse * 0.42
    mitte = groesse * 0.48
    malen.ellipse([mitte - r, mitte - r * 0.95, mitte + r, mitte + r * 0.95],
                  fill=(52, 132, 214, 110))
    schein = schein.filter(ImageFilter.GaussianBlur(groesse * 0.10))
    bild.alpha_composite(schein)
    if rund:
        maske = Image.new("L", (groesse, groesse), 0)
        ImageDraw.Draw(maske).rounded_rectangle(
            [0, 0, groesse - 1, groesse - 1],
            radius=int(groesse * radius), fill=255)
        bild.putalpha(maske)
    return bild


def _roboter(groesse, scale=1.0):
    """Roboter als transparentes RGBA-Bild, Kopf mittig."""
    bild = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    w = groesse
    cx, cy = w / 2, w * 0.525
    hw, hh = w * 0.300 * scale, w * 0.248 * scale
    ecke = w * 0.118 * scale
    kopf = [cx - hw, cy - hh, cx + hw, cy + hh]

    # Kopfband (liegt hinter dem Kopf)
    band = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    ImageDraw.Draw(band).arc(
        [kopf[0] - w * 0.010, kopf[1] - w * 0.078,
         kopf[2] + w * 0.010, kopf[3] - w * 0.010],
        start=184, end=356, fill=BAND + (255,),
        width=max(1, int(w * 0.034 * scale)))
    bild.alpha_composite(band)

    # Ohrmuscheln (halb hinter dem Kopf, wirken so angesetzt)
    malen = ImageDraw.Draw(bild)
    cup_w, cup_h = w * 0.080 * scale, hh * 1.02
    for seite in (-1, 1):
        ex = kopf[2] + cup_w * 0.05 if seite > 0 else kopf[0] - cup_w * 0.05
        box = [ex - cup_w / 2, cy - cup_h / 2, ex + cup_w / 2, cy + cup_h / 2]
        malen.rounded_rectangle(box, radius=cup_w * 0.44, fill=BLUE + (255,),
                                outline=(122, 196, 240, 170),
                                width=max(1, int(w * 0.005)))
        led = w * 0.014 * scale
        lx = ex + seite * cup_w * 0.26
        malen.ellipse([lx - led, cy - cup_h * 0.28 - led,
                       lx + led, cy - cup_h * 0.28 + led],
                      fill=CYAN + (255,))

    # Schatten unter dem Kopf
    schatten = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    ImageDraw.Draw(schatten).rounded_rectangle(
        [kopf[0] + w * 0.02, kopf[1] + w * 0.055,
         kopf[2] + w * 0.02, kopf[3] + w * 0.105],
        radius=ecke, fill=(0, 0, 0, 125))
    bild.alpha_composite(schatten.filter(
        ImageFilter.GaussianBlur(w * 0.032 * scale)))

    # Kopf mit Metallverlauf
    metall = _verlauf((groesse, groesse), METALL_TOP, METALL_BOT).convert("RGBA")
    maske = Image.new("L", (groesse, groesse), 0)
    ImageDraw.Draw(maske).rounded_rectangle(kopf, radius=ecke, fill=255)
    kopfbild = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    kopfbild.paste(metall, (0, 0), maske)
    bild.alpha_composite(kopfbild)
    malen = ImageDraw.Draw(bild)
    malen.rounded_rectangle(kopf, radius=ecke, outline=(255, 255, 255, 120),
                            width=max(1, int(w * 0.006)))

    # Visier: fast schwarz, damit die Augen auch klein leuchten
    visier = [kopf[0] + w * 0.052 * scale, kopf[1] + w * 0.068 * scale,
              kopf[2] - w * 0.052 * scale, kopf[3] - w * 0.075 * scale]
    malen.rounded_rectangle(visier, radius=w * 0.072 * scale, fill=DARK + (255,))

    # Augen
    augen = []
    aug_breite = (visier[2] - visier[0]) * 0.300
    aug_hoehe = (visier[3] - visier[1]) * 0.380
    for seite in (-1, 1):
        ex = cx + seite * (visier[2] - visier[0]) * 0.210
        ey = cy - w * 0.012 * scale
        augen.append([ex - aug_breite / 2, ey - aug_hoehe / 2,
                      ex + aug_breite / 2, ey + aug_hoehe / 2])
    schein = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    malen_s = ImageDraw.Draw(schein)
    for box in augen:
        malen_s.rounded_rectangle(
            [box[0] - w * 0.014, box[1] - w * 0.014,
             box[2] + w * 0.014, box[3] + w * 0.014],
            radius=aug_breite * 0.55, fill=CYAN + (185,))
    bild.alpha_composite(schein.filter(
        ImageFilter.GaussianBlur(w * 0.017 * scale)))
    malen = ImageDraw.Draw(bild)
    for box in augen:
        malen.rounded_rectangle(box, radius=aug_breite * 0.40,
                               fill=CYAN + (255,))
        # kleiner heller Kern
        kern = aug_breite * 0.30
        malen.ellipse([box[0] + aug_breite * 0.22, box[1] + aug_hoehe * 0.20,
                       box[0] + aug_breite * 0.22 + kern,
                       box[1] + aug_hoehe * 0.20 + kern],
                      fill=(235, 252, 255, 230))

    # Lautsprecher-Schlitze
    for i in (-1, 0, 1):
        bx = cx + i * w * 0.036 * scale
        malen.rounded_rectangle(
            [bx - w * 0.008 * scale, visier[3] - w * 0.062 * scale,
             bx + w * 0.008 * scale, visier[3] - w * 0.028 * scale],
            radius=w * 0.008 * scale, fill=(112, 146, 180, 255))
    return bild


def _zusammensetzen(groesse, scale):
    bild = _hintergrund(groesse, rund=True)
    bild.alpha_composite(_roboter(groesse, scale=scale))
    return bild


def main():
    gross = 1024 * S

    # Legacy-Icon 512 (Store/Launcher)
    icon = _zusammensetzen(gross, 1.03).resize((512, 512), Image.LANCZOS)
    icon.save(os.path.join(HIER, "icon.png"))

    # Adaptive Ebenen: Vordergrund mit Sicherheitsrand, Hintergrund randlos
    fg = Image.new("RGBA", (gross, gross), (0, 0, 0, 0))
    fg.alpha_composite(_roboter(gross, scale=0.80))
    fg.resize((432, 432), Image.LANCZOS).save(
        os.path.join(HIER, "icon_fg.png"))

    bg = _hintergrund(gross, rund=False)
    bg.resize((432, 432), Image.LANCZOS).save(
        os.path.join(HIER, "icon_bg.png"))

    icon.save(os.path.join(HIER, "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                     (64, 64), (128, 128), (256, 256)])

    # Vorschau in echten Groessen
    vorschau = Image.new("RGBA", (512 + 3 * 136, 160), (18, 24, 36, 255))
    vorschau.alpha_composite(icon.resize((128, 128), Image.LANCZOS), (16, 16))
    for i, kante in enumerate((16, 32, 48)):
        klein = icon.resize((kante, kante), Image.LANCZOS)
        vorschau.alpha_composite(klein, (170 + i * 136, 60))
    vorschau.convert("RGB").save(
        os.path.join(os.path.dirname(HIER), "artifacts", "icon-vorschau.png"))

    for name in ("icon.png", "icon_fg.png", "icon_bg.png", "icon.ico"):
        pfad = os.path.join(HIER, name)
        with Image.open(pfad) as pruefung:
            print(name, pruefung.size)


if __name__ == "__main__":
    main()
