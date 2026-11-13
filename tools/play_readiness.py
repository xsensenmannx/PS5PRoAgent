#!/usr/bin/env python3
"""Beratender Play-Store-Readiness-Check (ohne Netz, ohne Kivy).

Prueft Spec, Permissions, Listing-Texte, Datenschutzseite und vorhandene Assets.
Der Check blockiert nichts im Release; er zeigt, was fuer eine Play-Einreichung
noch fehlt.

    python3 tools/play_readiness.py
    python3 tools/play_readiness.py --strict   # Exit 1 bei Blockern

Exit-Code: 0 = nur Hinweise, 1 = Blocker (mit --strict), 2 = Aufruffehler.
"""
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCK, WARN, OK = [], [], []


def add(level, text):
    (BLOCK if level == "BLOCK" else WARN if level == "WARN" else OK).append(text)


def spec_text():
    with open(os.path.join(ROOT, "buildozer.spec"), encoding="utf-8") as f:
        return f.read()


def spec_value(text, key):
    m = re.search(r"^%s\s*=\s*(.*)$" % re.escape(key), text, re.M)
    return m.group(1).strip() if m else ""


def normalize_title(value):
    """Titel vergleichbar machen: Geviertstriche, Doppel-Leerzeichen, Gross/Klein."""
    text = str(value or "").casefold()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def png_size(path):
    """Breite/Hoehe aus dem IHDR lesen - ohne Pillow."""
    try:
        with open(path, "rb") as f:
            kopf = f.read(24)
        if kopf[:8] != b"\x89PNG\r\n\x1a\n" or kopf[12:16] != b"IHDR":
            return None
        return struct.unpack(">II", kopf[16:24])
    except OSError:
        return None


def image_size(path):
    if path.lower().endswith(".png"):
        return png_size(path)
    return None


def main():
    spec = spec_text()

    version = spec_value(spec, "version")
    api = spec_value(spec, "android.api")
    minapi = spec_value(spec, "android.minapi")
    artifact = spec_value(spec, "android.release_artifact") or "aab (Default)"
    pkg = ".".join(x for x in (spec_value(spec, "package.domain"),
                               spec_value(spec, "package.name")) if x)
    perms = spec_value(spec, "android.permissions")
    services = spec_value(spec, "services")

    add("OK" if version else "BLOCK", f"version: {version or 'fehlt'}")
    add("OK" if api.isdigit() and int(api) >= 36 else "BLOCK",
        f"targetSdk: {api or 'fehlt'} (Play verlangt 36)")
    add("OK" if minapi else "WARN", f"minSdk: {minapi or 'fehlt'}")
    add("OK" if artifact.lower() == "aab" else "BLOCK",
        f"release_artifact: {artifact} (Play braucht aab)")
    if re.search(r"ps5|playstation|sony", pkg, re.I):
        add("BLOCK", f"Package-Name enthaelt eine Sony-Marke: {pkg} "
                     "(Play: Markenrisiko, neuer Package-Name noetig)")
    else:
        add("OK", f"Package-Name neutral: {pkg}")

    gefaehrlich = ("CAMERA", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION",
                   "READ_CONTACTS", "RECORD_AUDIO", "READ_SMS", "SEND_SMS",
                   "READ_EXTERNAL_STORAGE", "MANAGE_EXTERNAL_STORAGE")
    treffer = [p.strip() for p in perms.split(",") if p.strip() in gefaehrlich]
    add("BLOCK" if treffer else "OK",
        "keine sensiblen Permissions" if not treffer
        else "sensible Permissions: " + ", ".join(treffer))
    add("OK" if "specialUse" in services else "WARN",
        "Foreground-Service specialUse deklariert" if "specialUse" in services
        else "kein specialUse in services")
    add("OK" if "FOREGROUND_SERVICE_SPECIAL_USE" in perms else "WARN",
        "FOREGROUND_SERVICE_SPECIAL_USE in Permissions")

    # Titel und Kurzbeschreibung aus dem deutschen Listing.
    listing_titel = ""
    listing = os.path.join(ROOT, "store", "listing.de.md")
    if not os.path.isfile(listing):
        add("BLOCK", "store/listing.de.md fehlt")
    else:
        text = open(listing, encoding="utf-8").read()
        listing_titel = next((l[2:].strip() for l in text.splitlines()
                              if l.startswith("# ")), "")
        if not listing_titel:
            add("BLOCK", "Listing-Titel fehlt")
        else:
            add("OK" if len(listing_titel) <= 30 else "BLOCK",
                f"Listing-Titel ({len(listing_titel)}/30): {listing_titel}")
            if re.search(r"\b(ps5|playstation|sony)\b", listing_titel, re.I):
                add("BLOCK", "Store-Titel enthaelt eine Sony-Marke")
            else:
                add("OK", "Store-Titel ohne Sony-Marke")
        m = re.search(r"## Kurzbeschreibung.*?\n+([^\n#][^\n]*)", text)
        kurz = m.group(1).strip() if m else ""
        add("OK" if kurz and len(kurz) <= 80 else "WARN",
            f"Kurzbeschreibung ({len(kurz)}/80)" if kurz else "Kurzbeschreibung fehlt")
        hat_disclaimer = bool(re.search(
            r"(keine|keiner)\s+Verbindung|nicht\s+mit\s+Sony", text, re.I))
        add("OK" if hat_disclaimer else "WARN",
            "Disclaimer vorhanden" if hat_disclaimer else "Disclaimer fehlt")

    # Der tatsaechliche App-Titel (Launcher/APK) muss zum Store-Titel passen.
    # Sonst zeigt der Store einen anderen Namen als die installierte App - und
    # eine Sony-Marke im Launcher-Namen bleibt ein IP-Risiko, auch wenn das
    # Listing selbst neutral ist.
    app_titel = spec_value(spec, "title")
    if not app_titel:
        add("BLOCK", "App-Titel fehlt in buildozer.spec")
    else:
        if re.search(r"\b(ps5|playstation|sony)\b", app_titel, re.I):
            add("BLOCK", f"App-Titel enthaelt eine Sony-Marke: {app_titel}")
        else:
            add("OK", f"App-Titel ohne Sony-Marke: {app_titel}")
        if listing_titel and normalize_title(app_titel) != normalize_title(listing_titel):
            add("BLOCK", "App-Titel weicht vom Store-Titel ab: "
                         f"\"{app_titel}\" vs. \"{listing_titel}\"")
        elif listing_titel:
            add("OK", "App-Titel und Store-Titel stimmen ueberein")

    # Datenschutzseite (Play verlangt eine oeffentliche URL).
    priv = os.path.join(ROOT, "docs", "privacy.html")
    if os.path.isfile(priv) and os.path.getsize(priv) > 1500:
        add("OK", "docs/privacy.html vorhanden (GitHub Pages faehig)")
    else:
        add("BLOCK", "docs/privacy.html fehlt oder ist zu klein")

    # Pflicht-Assets.
    assets = os.path.join(ROOT, "store", "assets")
    icon = os.path.join(assets, "icon-512.png")
    if os.path.isfile(icon) and png_size(icon) == (512, 512):
        add("OK", "Icon 512x512")
    else:
        add("WARN", "store/assets/icon-512.png (512x512) fehlt")
    feature = None
    for name in ("feature-1024x500.png", "feature-1024x500.jpg"):
        p = os.path.join(assets, name)
        if os.path.isfile(p):
            feature = image_size(p) or (1024, 500)
            break
    add("OK" if feature else "WARN",
        "Feature-Grafik 1024x500" if feature else "Feature-Grafik 1024x500 fehlt")

    telefon = os.path.join(assets, "phone")
    bilder = []
    if os.path.isdir(telefon):
        bilder = [os.path.join(telefon, n) for n in sorted(os.listdir(telefon))
                  if n.lower().endswith((".png", ".jpg", ".jpeg"))]
    gute = []
    for p in bilder:
        size = image_size(p)
        if not size:
            continue
        w, h = size
        if min(w, h) >= 320 and max(w, h) <= 3840 and max(w, h) <= 2 * min(w, h):
            gute.append(p)
    add("OK" if len(gute) >= 2 else "WARN",
        f"Telefon-Screenshots: {len(gute)} gueltig (mind. 2, 320-3840 px, max. 2:1)")

    aab = os.path.join(ROOT, "bin")
    hat_aab = os.path.isdir(aab) and any(n.endswith(".aab") for n in os.listdir(aab))
    add("OK" if hat_aab else "WARN",
        "AAB gebaut" if hat_aab else "noch kein AAB in bin/ gebaut")

    print("Play-Store-Readiness\n" + "=" * 21)
    for titel, liste in (("BLOCKER", BLOCK), ("HINWEISE", WARN), ("OK", OK)):
        if not liste:
            continue
        print(f"\n{titel}")
        for t in liste:
            print("  -", t)
    print(f"\nErgebnis: {len(BLOCK)} Blocker, {len(WARN)} Hinweise, {len(OK)} ok")
    if BLOCK:
        print("Details und Reihenfolge: docs/PLAY_STORE.md")
    return 1 if (BLOCK and "--strict" in sys.argv) else 0


if __name__ == "__main__":
    sys.exit(main())
