#!/usr/bin/env python3
"""AAB-Preflight für die Hilfe-App (ohne Netz, ohne Android-SDK).

Prüft vor dem teuren Build, dass APK- und Play-Spec dieselbe App, Version
und denselben versionCode beschreiben und dass die Play-Spec wirklich ein
AAB erzeugt. Mit ``--tag`` wird zusätzlich die erwartete Version aus dem
Release-Tag geprüft.

    python3 tools/check_hilfe_specs.py
    python3 tools/check_hilfe_specs.py --tag v1.2.0

Exit-Code: 0 = in Ordnung, 1 = mindestens ein Fehler.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APK_SPEC = ROOT / "support_app" / "buildozer.spec"
PLAY_SPEC = ROOT / "support_app" / "buildozer.play.spec"
VERSION_PY = ROOT / "support_app" / "version.py"

# Diese Werte müssen in beiden Specs identisch sein. Das Artefakt ist die
# einzige bewusste Ausnahme: APK für Sideload, AAB für Google Play.
GLEICHE_WERTE = (
    "title",
    "package.name",
    "package.domain",
    "version",
    "android.numeric_version",
    "android.api",
    "android.minapi",
    "android.permissions",
    "android.archs",
)


def wert(text, schluessel):
    treffer = re.search(
        r"^" + re.escape(schluessel) + r"\s*=\s*(.*)$", text, re.M)
    return treffer.group(1).strip() if treffer else ""


def tag_werte(tag):
    """v1.2.3 -> (1.2.3, 10203); gleiche Regel wie set_version_from_tag.sh."""
    version = tag[1:] if tag.startswith("v") else tag
    teile = version.split(".")
    if len(teile) not in (2, 3) or not all(t.isdigit() for t in teile):
        raise ValueError("Tag muss auf vMAJOR.MINOR[.PATCH] passen")
    major, minor = int(teile[0]), int(teile[1])
    patch = int(teile[2]) if len(teile) == 3 else 0
    if minor >= 100 or patch >= 100:
        raise ValueError("Minor und Patch müssen unter 100 bleiben")
    return version, major * 10000 + minor * 100 + patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="",
                        help="optionaler Release-Tag, z. B. v1.2.0")
    args = parser.parse_args()

    fehler = []
    for pfad in (APK_SPEC, PLAY_SPEC, VERSION_PY):
        if not pfad.is_file():
            fehler.append("Datei fehlt: %s" % pfad.relative_to(ROOT))
    if fehler:
        print("AAB-Preflight: FEHLER")
        for text in fehler:
            print("  -", text)
        return 1

    apk = APK_SPEC.read_text(encoding="utf-8")
    play = PLAY_SPEC.read_text(encoding="utf-8")
    version_quelle = VERSION_PY.read_text(encoding="utf-8")

    for schluessel in GLEICHE_WERTE:
        apk_wert = wert(apk, schluessel)
        play_wert = wert(play, schluessel)
        if not apk_wert or not play_wert:
            fehler.append("Pflichtwert fehlt: %s" % schluessel)
        elif apk_wert != play_wert:
            fehler.append(
                "%s driftet: APK=%r, Play=%r" % (schluessel, apk_wert, play_wert))

    if wert(apk, "android.release_artifact") != "apk":
        fehler.append("buildozer.spec muss android.release_artifact = apk setzen")
    if wert(play, "android.release_artifact") != "aab":
        fehler.append(
            "buildozer.play.spec muss android.release_artifact = aab setzen")

    version = wert(apk, "version")
    treffer = re.search(r'^VERSION\s*=\s*"([^"]+)"', version_quelle, re.M)
    version_py = treffer.group(1) if treffer else ""
    if version_py != version:
        fehler.append(
            "version.py (%r) passt nicht zur Spec (%r)" % (version_py, version))

    if args.tag:
        try:
            erwartet, erwarteter_code = tag_werte(args.tag)
        except ValueError as problem:
            fehler.append(str(problem))
        else:
            if version != erwartet:
                fehler.append(
                    "Tag erwartet Version %s, Spec hat %s" % (erwartet, version))
            if wert(apk, "android.numeric_version") != str(erwarteter_code):
                fehler.append(
                    "Tag erwartet versionCode %d, Spec hat %s"
                    % (erwarteter_code, wert(apk, "android.numeric_version") or "—"))

    if fehler:
        print("AAB-Preflight: FEHLER")
        for text in fehler:
            print("  -", text)
        return 1

    print("AAB-Preflight: ok (version=%s, versionCode=%s, Paket=%s.%s)" % (
        version,
        wert(apk, "android.numeric_version"),
        wert(apk, "package.domain"),
        wert(apk, "package.name"),
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
