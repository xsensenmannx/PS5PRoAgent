#!/usr/bin/env bash
# Repariert halb heruntergeladene Android-SDK/NDK-Baeume und veraltete
# Python-Build-Verzeichnisse im Cache.
#
# Hintergrund SDK: buildozer prueft nur, ob das SDK-Verzeichnis existiert, und
# ueberspringt dann die Installation ("Android SDK found at ..."). Ein
# abgebrochener Lauf - oder ein Verzeichnis, das nur licenses/ enthaelt -
# hinterlaesst genau so einen Zustand; danach bricht jeder weitere Lauf mit
# "sdkmanager is not installed" ab, egal wie oft man neu startet.
#
# Hintergrund Python: p4a baut ohne Pin CPython 3.14.2. Das laesst sich mit
# Cython 0.29.36 (fest im p4a-Recipe) und Kivy 2.3 nicht kompilieren - ab
# Python 3.13 aendert sich die Signatur von _PyLong_AsByteArray, und der von
# Cython erzeugte C-Code ruft sie mit zu wenigen Argumenten auf. Deshalb pinnt
# buildozer.spec python3 und hostpython3 auf dieselbe Version. Hier wird
#   (a) der alte python3/hostpython3-Build und die fertige Distribution
#       verworfen, sobald sich der Pin aendert, und
#   (b) im bereits ausgecheckten p4a die Recipe-Version direkt gesetzt, weil
#       p4a Versionsangaben aus den Requirements nicht in jedem Codepfad
#       uebernimmt (kivy/python-for-android#3273).
#
# Pfad ueberschreibbar: BUILDOZER_PLATFORM=/pfad/zu/platform bash tools/ci_fix_cache.sh
# Python-Pin ueberschreibbar: P4A_PYTHON_PIN=3.11.9 (sonst aus buildozer.spec)
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT_DEFAULT="${BUILDOZER_PLATFORM:-$HOME/.buildozer/android/platform}"
ROOT_WORKSPACE="$HERE/.buildozer/android/platform"

# Erster Treffer von python3==x.y.z in der Spec.
PIN="${P4A_PYTHON_PIN-}"
if [ -z "$PIN" ] && [ -f "$HERE/buildozer.spec" ]; then
    # [[:space:],] davor, sonst trifft das Muster auch das "python3==" in
    # "hostpython3==" und liefert die falsche Version.
    PIN=$(sed -n 's/.*[[:space:],]python3==\([0-9][0-9.]*\).*/\1/p' "$HERE/buildozer.spec" | head -n 1)
fi

fix_platform() {
    local PLATFORM="$1"
    local SDK="$PLATFORM/android-sdk"
    local P4A="$PLATFORM/python-for-android"

    # 1. Commandline-Tools liegen je nach SDK unter cmdline-tools/latest oder
    #    cmdline-tools/<version>; buildozer sucht tools/bin/sdkmanager. Ein
    #    Symlink genuegt - und bewahrt ein intaktes SDK vor dem Loeschen.
    local CLT=""
    local cand
    for cand in "$SDK"/cmdline-tools/latest "$SDK"/cmdline-tools/*; do
        [ -f "$cand/bin/sdkmanager" ] || continue
        CLT="$cand"
        break
    done
    if [ -d "$SDK" ] && [ ! -f "$SDK/tools/bin/sdkmanager" ] && [ -n "$CLT" ]; then
        rm -rf "$SDK/tools"
        ln -s "${CLT#"$SDK"/}" "$SDK/tools"
        echo "habe ${CLT#"$SDK"/} -> tools verlinkt"
    fi

    # 2. Alles, was danach kein sdkmanager hat, ist Schrott und muss weg.
    if [ -d "$SDK" ] && [ ! -f "$SDK/tools/bin/sdkmanager" ]; then
        echo "unvollstaendiges SDK ohne tools/bin/sdkmanager -> entferne $SDK"
        rm -rf "$SDK"
    fi

    # 3. Dasselbe fuer das NDK: buildozer ueberspringt auch hier vorhandene Ordner.
    local ndk
    for ndk in "$PLATFORM"/android-ndk-r*; do
        [ -d "$ndk" ] || continue
        if [ ! -f "$ndk/source.properties" ]; then
            echo "unvollstaendiges NDK $(basename "$ndk") -> entferne es"
            rm -rf "$ndk"
        fi
    done

    # 3b. Betriebssystem: p4a legt hostpython3 und Hilfswerkzeuge als fertige
    #     Binaries ab. Ein Cache von Ubuntu 26 laesst sich auf 24.04 nicht
    #     starten (GLIBC-Version) - buildozer bricht dann nach wenigen Minuten
    #     ab. SDK/NDK bleiben erhalten, nur die Build-Baeume fliegen raus.
    local osid oldos
    osid=$( (. /etc/os-release 2>/dev/null && printf '%s' "${VERSION_ID:-unknown}") || echo unknown )
    oldos=$(cat "$PLATFORM/.p4a-os-id" 2>/dev/null || true)
    if [ "$osid" != "unknown" ] && [ "$oldos" != "$osid" ]; then
        echo "OS ${osid} (vorher: ${oldos:-unbekannt}) -> verwerfe kompilierte Build-Baeume"
        rm -rf "$PLATFORM"/build-*
        mkdir -p "$PLATFORM"
        printf '%s\n' "$osid" > "$PLATFORM/.p4a-os-id"
    fi

    if [ -n "$PIN" ]; then
        # 4. Versionswechsel: alte Builds mischen sonst 3.14-Header mit dem Pin.
        local MARK="$PLATFORM/.p4a-python-pin"
        local OLD
        OLD=$(cat "$MARK" 2>/dev/null || true)
        if [ "$OLD" != "$PIN" ]; then
            echo "Python-Pin $PIN (vorher: ${OLD:-unbekannt}) -> verwerfe python3/hostpython3 und die Distribution"
            rm -rf "$PLATFORM"/build-*/build/other_builds/python3 \
                   "$PLATFORM"/build-*/build/other_builds/hostpython3 \
                   "$PLATFORM"/build-*/dists
            mkdir -p "$PLATFORM"
            printf '%s\n' "$PIN" > "$MARK"
        fi

        # 5. Version im vorhandenen p4a-Checkout setzen (siehe Kopfkommentar).
        local rec f
        for rec in python3 hostpython3; do
            f="$P4A/pythonforandroid/recipes/$rec/__init__.py"
            [ -f "$f" ] || continue
            if grep -qE "^[[:space:]]*version = ['\"]$PIN['\"]" "$f"; then
                echo "$rec-Recipe steht bereits auf $PIN"
            else
                sed -i -E "s/^([[:space:]]*)version = ['\"][0-9][0-9.]*['\"]/\1version = '$PIN'/" "$f"
                echo "$rec-Recipe auf $PIN gesetzt"
            fi
        done
    fi

    if [ -d "$SDK" ]; then
        echo "SDK in Ordnung: $SDK"
    else
        echo "kein SDK in $PLATFORM - buildozer installiert es beim naechsten Lauf"
    fi
}

found=0
for p in "$ROOT_DEFAULT" "$ROOT_WORKSPACE"; do
    [ -d "$p" ] || continue
    found=1
    fix_platform "$p"
done

if [ "$found" -eq 0 ]; then
    echo "kein Platform-Ordner vorhanden - buildozer legt SDK/NDK beim naechsten Lauf an"
fi
