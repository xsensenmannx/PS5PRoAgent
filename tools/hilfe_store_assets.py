"""Erzeugt die beiden Play-Grafiken der Hilfe-App.

    store/hilfe/assets/icon-512.png          512x512, 32-bit RGBA
    store/hilfe/assets/feature-1024x500.png  1024x500

Basis ist das Roboter-Icon aus `support_app/icon.png` (dieselbe Quelle wie
Launcher und APK), damit Store und App nicht auseinanderlaufen.

    python tools/hilfe_store_assets.py
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "support_app" / "icon.png"
ZIEL = ROOT / "store" / "hilfe" / "assets"

INK = (11, 18, 32)
INK2 = (22, 40, 70)
WEISS = (230, 237, 249)
GEDAEMPFT = (154, 170, 196)
AKZENT = (47, 124, 246)
MINT = (72, 214, 178)


def font(size, bold=True):
    """Segoe UI wie in der Radar-Store-Grafik; Fallback Arial."""
    namen = ["segoeuib.ttf" if bold else "segoeui.ttf",
             "arialbd.ttf" if bold else "arial.ttf"]
    for name in namen:
        pfad = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
        if pfad.exists():
            return ImageFont.truetype(str(pfad), size)
    return ImageFont.load_default()


def verlauf(width, height):
    """Diagonaler, sehr dunkler Verlauf wie im Radar-Store-Bild."""
    im = Image.new("RGB", (width, height), INK)
    px = im.load()
    for y in range(height):
        for x in range(width):
            t = (x / max(1, width - 1) + y / max(1, height - 1)) / 2.0
            px[x, y] = (int(INK[0] * (1 - t) + INK2[0] * t),
                        int(INK[1] * (1 - t) + INK2[1] * t),
                        int(INK[2] * (1 - t) + INK2[2] * t))
    return im


def icon_quelle(size):
    if not ICON.exists():
        raise SystemExit("Icon fehlt: %s (zuerst support_app/make_icon.py)" % ICON)
    return Image.open(ICON).convert("RGBA").resize((size, size), Image.LANCZOS)


def icon_512():
    im = icon_quelle(512)
    # Play verlangt ein 32-bit PNG mit Alpha. Der Alphakanal bleibt erhalten;
    # der Hintergrund ist voll deckend, die Ecken maskiert Play selbst.
    flach = Image.new("RGBA", (512, 512), INK + (255,))
    flach.paste(im, (0, 0), im)
    return flach


def feature():
    w, h = 1024, 500
    im = verlauf(w, h)
    d = ImageDraw.Draw(im)

    marke = icon_quelle(300)
    im.paste(marke, (58, 100), marke)

    d.text((396, 92), "PS5 PRO SEARCH AGENT", font=font(44), fill=WEISS)
    d.text((398, 158), "Hilfe & Diagnose", font=font(32), fill=WEISS)
    d.text((398, 214), "Offline · Alarme · Webhooks · KI optional",
           font=font(19), fill=MINT)
    d.text((398, 252), "Antworten aus 16 Karten, kein Konto, keine Werbung",
           font=font(17, False), fill=GEDAEMPFT)
    d.line([(398, 300), (930, 300)], fill=AKZENT, width=2)
    d.text((398, 320), "Diagnose-Bericht prüfen", font=font(17, False),
           fill=GEDAEMPFT)
    d.text((398, 346), "Suchauftrag in Schritte übersetzen",
           font=font(17, False), fill=GEDAEMPFT)
    return im


def main():
    ZIEL.mkdir(parents=True, exist_ok=True)
    icon_512().save(ZIEL / "icon-512.png", optimize=True)
    feature().save(ZIEL / "feature-1024x500.png", optimize=True)
    for name in ("icon-512.png", "feature-1024x500.png"):
        pfad = ZIEL / name
        with Image.open(pfad) as probe:
            print(name, probe.size, probe.mode, pfad.stat().st_size, "B")


if __name__ == "__main__":
    main()
