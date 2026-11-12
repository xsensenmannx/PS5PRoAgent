#!/usr/bin/env bash
# Prueft die fertige APK: Groesse plausibel und die gepinnte Python-Version
# wirklich enthalten. Genau hier lag der teure Fehler - buildozer meldet
# "Android packaging done", die APK enthaelt aber libpython3.14 statt 3.11.
#
# Aufruf: bash tools/ci_check_apk.sh bin/ps5prosearchagent-2.0-arm64-v8a-debug.apk 3.11.9
set -euo pipefail

APK="${1:-}"
PIN="${2:-}"

if [ -z "$APK" ] || [ ! -f "$APK" ]; then
    echo "::error::keine APK gefunden: ${APK:-<leer>}"
    exit 1
fi
if [ -z "$PIN" ]; then
    echo "::error::Python-Version fehlt (2. Argument)"
    exit 1
fi

SIZE=$(wc -c < "$APK" | tr -d ' ')
if [ "$SIZE" -lt 3000000 ]; then
    echo "::error::$APK ist mit $SIZE Bytes zu klein fuer eine vollstaendige APK"
    exit 1
fi

LIST=$(unzip -l "$APK" 2>/dev/null || true)
if [ -z "$LIST" ]; then
    echo "::error::$APK ist kein lesbares ZIP"
    exit 1
fi

PYLIB="libpython${PIN%.*}.so"
if ! printf '%s\n' "$LIST" | grep -q "$PYLIB"; then
    echo "::error::$PYLIB fehlt in der APK - gebaut wurde gegen eine andere Python-Version"
    printf '%s\n' "$LIST" | grep -E 'libpython|libmain' || true
    exit 1
fi

echo "APK ok: $SIZE Bytes, $PYLIB enthalten"
printf '%s\n' "$LIST" | grep -E "$PYLIB|libmain" | head -4
