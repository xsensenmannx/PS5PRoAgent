#!/usr/bin/env bash
# Leitet Anzeige-Version und versionCode aus dem Release-Tag ab und schreibt
# beides in buildozer.spec.
#
#   v1.2     -> version = 1.2,   android.numeric_version = 10200
#   v1.2.3   -> version = 1.2.3, android.numeric_version = 10203
#
# Liegt neben der Spec eine version.py, wird deren VERSION mitgeschrieben;
# die App zeigt sie im Reiter THEMEN an. Eine danebenliegende
# buildozer.play.spec (AAB/Play) bekommt version und versionCode ebenfalls,
# damit APK- und Play-Spec nicht auseinanderlaufen.
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

schreibe_version() {
    local datei="$1"
    sed -i -E "s/^version[[:space:]]*=.*/version = ${VERSION}/" "$datei"
    sed -i -E "s/^android\.numeric_version[[:space:]]*=.*/android.numeric_version = ${CODE}/" "$datei"

    if ! grep -qx "version = ${VERSION}" "$datei"; then
        echo "::error::version konnte in $datei nicht gesetzt werden" >&2
        return 1
    fi
    if ! grep -qx "android.numeric_version = ${CODE}" "$datei"; then
        echo "::error::android.numeric_version konnte in $datei nicht gesetzt werden" >&2
        return 1
    fi
}

schreibe_version "$SPEC"

# AAB-/Play-Spec neben der APK-Spec mitziehen, damit der Drift-Test gruen bleibt.
PLAY_SPEC="$(dirname "$SPEC")/buildozer.play.spec"
if [ -f "$PLAY_SPEC" ]; then
    schreibe_version "$PLAY_SPEC"
    echo "AAB-Spec aktualisiert: $PLAY_SPEC"
fi

# Die App zeigt ihre Version aus version.py; beim Tag-Build mitziehen.
VERSIONSDATEI="$(dirname "$SPEC")/version.py"
if [ -f "$VERSIONSDATEI" ]; then
    sed -i -E "s/^VERSION[[:space:]]*=.*/VERSION = \"${VERSION}\"/" "$VERSIONSDATEI"
    if ! grep -qx "VERSION = \"${VERSION}\"" "$VERSIONSDATEI"; then
        echo "::error::VERSION konnte in $VERSIONSDATEI nicht gesetzt werden" >&2
        exit 1
    fi
fi

echo "Tag $TAG -> version=$VERSION versionCode=$CODE"
