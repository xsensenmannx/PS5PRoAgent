#!/usr/bin/env bash
# Leitet Anzeige-Version und versionCode aus dem Release-Tag ab und schreibt
# beides in buildozer.spec.
#
#   v1.2     -> version = 1.2,   android.numeric_version = 10200
#   v1.2.3   -> version = 1.2.3, android.numeric_version = 10203
#
# Der versionCode muss bei jedem Update steigen; aus dem Tag abgeleitet kann er
# nicht mehr vergessen werden. Minor und Patch muessen unter 100 bleiben,
# damit die Reihenfolge eindeutig ist.
#
# Aufruf: bash tools/set_version_from_tag.sh v1.2 [buildozer.spec]
set -euo pipefail

TAG="${1:-}"
SPEC="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/buildozer.spec}"

if [ -z "$TAG" ]; then
    echo "::error::Tag fehlt (erwartet z. B. v1.2)" >&2
    exit 1
fi
if ! printf '%s' "$TAG" | grep -Eq '^v[0-9]+\.[0-9]+(\.[0-9]+)?$'; then
    echo "::error::Tag '$TAG' passt nicht auf vMAJOR.MINOR[.PATCH]" >&2
    exit 1
fi
if [ ! -f "$SPEC" ]; then
    echo "::error::buildozer.spec nicht gefunden: $SPEC" >&2
    exit 1
fi

VERSION="${TAG#v}"
MAJOR="${VERSION%%.*}"
REST="${VERSION#*.}"
MINOR="${REST%%.*}"
PATCH=0
case "$VERSION" in
    *.*.*) PATCH="${REST#*.}" ;;
esac

if [ "$MINOR" -ge 100 ] || [ "$PATCH" -ge 100 ]; then
    echo "::error::Minor und Patch muessen unter 100 bleiben (Tag: $TAG)" >&2
    exit 1
fi

CODE=$((MAJOR * 10000 + MINOR * 100 + PATCH))
if [ "$CODE" -gt 2100000000 ]; then
    echo "::error::versionCode $CODE liegt ueber dem Android-Maximum" >&2
    exit 1
fi

sed -i -E "s/^version[[:space:]]*=.*/version = ${VERSION}/" "$SPEC"
sed -i -E "s/^android\.numeric_version[[:space:]]*=.*/android.numeric_version = ${CODE}/" "$SPEC"

if ! grep -qx "version = ${VERSION}" "$SPEC"; then
    echo "::error::version konnte in $SPEC nicht gesetzt werden" >&2
    exit 1
fi
if ! grep -qx "android.numeric_version = ${CODE}" "$SPEC"; then
    echo "::error::android.numeric_version konnte in $SPEC nicht gesetzt werden" >&2
    exit 1
fi

echo "Tag $TAG -> version=$VERSION versionCode=$CODE"
