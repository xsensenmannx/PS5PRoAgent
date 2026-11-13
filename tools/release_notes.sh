#!/usr/bin/env bash
# Erzeugt die Release-Beschreibung fuer den Tag-Workflow:
# Aenderungen seit dem letzten Tag, Installationshinweis und SHA-256 der APK.
#
# Aufruf: bash tools/release_notes.sh <tag> <apk> <ausgabe.md>
set -euo pipefail

TAG="${1:?Tag fehlt}"
APK="${2:?APK fehlt}"
OUT="${3:?Ausgabedatei fehlt}"

[ -f "$APK" ] || { echo "APK nicht gefunden: $APK" >&2; exit 1; }
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || {
    echo "Tag nicht gefunden: $TAG" >&2
    exit 1
}

REPO="${GITHUB_REPOSITORY:-xsensenmannx/PS5PRoAgent}"
SERVER="${GITHUB_SERVER_URL:-https://github.com}"

SIZE_BYTES=$(wc -c < "$APK" | tr -d ' ')
SIZE_MB=$(awk -v b="$SIZE_BYTES" 'BEGIN { printf "%.1f", b / 1000000 }' | tr '.' ',')
SHA=$(sha256sum "$APK" | cut -d' ' -f1)
NAME=$(basename "$APK")

# Letzter Tag in der Vorfahrenlinie (der Normalfall). Fehlt er, wird der
# nach Erstellungsdatum juengste andere Tag genommen; die Commits davor
# liefert git log dann ueber die Bereichsangabe.
PREV=$(git describe --tags --abbrev=0 --match 'v*' "$TAG^" 2>/dev/null || true)
if [ -z "$PREV" ]; then
    PREV=$(git tag --sort=-creatordate --list 'v*' | grep -vx "$TAG" | head -n 1 || true)
fi

if [ -n "$PREV" ]; then
    RANGE="$PREV..$TAG"
else
    RANGE="$TAG"
fi

TOTAL=$(git log --no-merges --pretty=format:'%s' "$RANGE" | grep -c . || true)
CHANGES=$(git log --no-merges --pretty=format:'- %s' "$RANGE" | head -n 25 || true)
[ -n "$CHANGES" ] || CHANGES="- Keine einzelnen Aenderungen erfasst."
if [ "$TOTAL" -gt 25 ]; then
    CHANGES="$CHANGES"$'\n'"- … und $((TOTAL - 25)) weitere Commits"
fi

{
    echo "## Änderungen"
    echo
    echo "$CHANGES"
    echo
    if [ -n "$PREV" ]; then
        echo "**Vollständiger Vergleich:** [$PREV...$TAG]($SERVER/$REPO/compare/$PREV...$TAG)"
        echo
    fi
    echo "## Installation"
    echo
    echo "- Android 8.0 oder neuer, **arm64-v8a**"
    echo "- Debug-APK, **$SIZE_MB MB** (\`$NAME\`)"
    echo "- Unbekannte Quellen für Browser bzw. Dateimanager erlauben"
    echo "- Ein Update legt sich über die bestehende Installation; nur beim Wechsel aus der alten 5.x-Reihe vorher deinstallieren"
    echo
    echo "## Prüfsumme"
    echo
    echo '```'
    echo "SHA-256  $SHA"
    echo '```'
} > "$OUT"

echo "Release-Notes geschrieben: $OUT ($TOTAL Commits, SHA-256 $SHA)"
