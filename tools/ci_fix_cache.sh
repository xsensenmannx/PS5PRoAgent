#!/usr/bin/env bash
# Repariert halb heruntergeladene Android-SDK/NDK-Bäume im Cache.
#
# Hintergrund: buildozer prueft nur, ob das SDK-Verzeichnis existiert, und
# ueberspringt dann die Installation ("Android SDK found at ..."). Ein
# abgebrochener Lauf - oder ein Verzeichnis, das nur licenses/ enthaelt -
# hinterlaesst genau so einen Zustand; danach bricht jeder weitere Lauf mit
# "sdkmanager is not installed" ab, egal wie oft man neu startet.
#
# Pfad ueberschreibbar: BUILDOZER_PLATFORM=/pfad/zu/platform bash tools/ci_fix_cache.sh
set -euo pipefail

PLATFORM="${BUILDOZER_PLATFORM:-$HOME/.buildozer/android/platform}"
SDK="$PLATFORM/android-sdk"

# 1. Neuere Commandline-Tools liegen unter cmdline-tools/latest, buildozer sucht
#    tools/bin/sdkmanager. Ein Symlink genuegt - und bewahrt ein intaktes SDK.
if [ -d "$SDK" ] && [ ! -f "$SDK/tools/bin/sdkmanager" ] \
        && [ -f "$SDK/cmdline-tools/latest/bin/sdkmanager" ]; then
    rm -rf "$SDK/tools"
    ln -s cmdline-tools/latest "$SDK/tools"
    echo "habe $SDK/cmdline-tools/latest -> tools verlinkt"
fi

# 2. Alles, was danach kein sdkmanager hat, ist Schrott und muss weg.
if [ -d "$SDK" ] && [ ! -f "$SDK/tools/bin/sdkmanager" ]; then
    echo "unvollstaendiges SDK ohne tools/bin/sdkmanager -> entferne $SDK"
    rm -rf "$SDK"
fi

# 3. Dasselbe fuer das NDK: buildozer ueberspringt auch hier vorhandene Ordner.
for ndk in "$PLATFORM"/android-ndk-r*; do
    [ -d "$ndk" ] || continue
    if [ ! -f "$ndk/source.properties" ]; then
        echo "unvollstaendiges NDK $(basename "$ndk") -> entferne es"
        rm -rf "$ndk"
    fi
done

if [ -d "$SDK" ]; then
    echo "SDK in Ordnung: $SDK"
else
    echo "kein SDK vorhanden - buildozer installiert es beim naechsten Lauf"
fi
