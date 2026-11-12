#!/usr/bin/env bash
# Prueft das fertige App Bundle: richtige Struktur, Signatur und Python-Version.
# Ein unsigniertes AAB laedt Google Play nicht hoch - deshalb ist die Signatur
# hier ein harter Fehler und keine Warnung.
#
# Aufruf: bash tools/ci_check_aab.sh bin/ps5prosearchagent-3.0-arm64-v8a-release.aab 3.11.9
set -euo pipefail

AAB="${1:-}"
PIN="${2:-}"

if [ -z "$AAB" ] || [ ! -f "$AAB" ]; then
    echo "::error::kein AAB gefunden: ${AAB:-<leer>}"
    exit 1
fi
if [ -z "$PIN" ]; then
    echo "::error::Python-Version fehlt (2. Argument)"
    exit 1
fi

SIZE=$(wc -c < "$AAB" | tr -d ' ')
if [ "$SIZE" -lt 5000000 ]; then
    echo "::error::$AAB ist mit $SIZE Bytes zu klein fuer ein vollstaendiges Bundle"
    exit 1
fi

LIST=$(unzip -l "$AAB" 2>/dev/null || true)
if [ -z "$LIST" ]; then
    echo "::error::$AAB ist kein lesbares ZIP"
    exit 1
fi

for need in "base/manifest/AndroidManifest.xml" "BundleConfig.pb"; do
    if ! printf '%s\n' "$LIST" | grep -q "$need"; then
        echo "::error::$need fehlt - das ist kein gueltiges App Bundle"
        exit 1
    fi
done

if ! printf '%s\n' "$LIST" | grep -qE 'META-INF/[^/]+\.(RSA|EC|DSA)$'; then
    echo "::error::AAB ist nicht signiert (keine META-INF/*.RSA)."
    echo "P4A_RELEASE_KEYSTORE / KEYSTORE_PASSWD / KEYALIAS / KEYALIAS_PASSWD pruefen."
    exit 1
fi

PYLIB="base/lib/arm64-v8a/libpython${PIN%.*}.so"
if ! printf '%s\n' "$LIST" | grep -q "$PYLIB"; then
    echo "::error::$PYLIB fehlt im Bundle - gebaut wurde gegen eine andere Python-Version"
    printf '%s\n' "$LIST" | grep -E 'libpython|libmain' | head -6 || true
    exit 1
fi

echo "AAB ok: $SIZE Bytes, signiert, $PYLIB enthalten"
printf '%s\n' "$LIST" | grep -E "META-INF/.*\.(RSA|EC|DSA)$|$PYLIB" | head -4
