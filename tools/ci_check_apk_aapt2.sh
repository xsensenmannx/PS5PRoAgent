#!/usr/bin/env bash
# Prueft die fertige APK mit aapt2: versionCode, versionName, targetSdkVersion
# und foregroundServiceType des Hintergrund-Service. Die Sollwerte kommen aus
# buildozer.spec, damit ein Release nicht versehentlich mit alten Werten
# veroeffentlicht wird.
#
# Aufruf: bash tools/ci_check_apk_aapt2.sh bin/ps5prosearchagent-3.2-arm64-v8a-debug.apk
# Optional: SPEC=/pfad/buildozer.spec AAPT2=/pfad/zu/aapt2 ...
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APK="${1:-}"
SPEC="${2:-${SPEC:-$ROOT/buildozer.spec}}"

if [ -z "$APK" ]; then
    APK=$(ls -1 "$ROOT"/bin/*.apk 2>/dev/null | head -n 1 || true)
fi
if [ -z "$APK" ] || [ ! -f "$APK" ]; then
    echo "::error::keine APK gefunden: ${APK:-<leer>}"
    exit 1
fi
if [ ! -f "$SPEC" ]; then
    echo "::error::buildozer.spec nicht gefunden: $SPEC"
    exit 1
fi

spec_wert() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$SPEC" \
        | head -n 1 | tr -d '\r' | sed 's/[[:space:]]*$//'
}

EXPECTED_VERSION_NAME=$(spec_wert "version")
EXPECTED_VERSION_CODE=$(spec_wert "android.numeric_version")
EXPECTED_TARGET_SDK=$(spec_wert "android.api")
EXPECTED_FGS=$(spec_wert "services" \
    | sed -n 's/.*foregroundServiceType=\([^,[:space:]]*\).*/\1/p' \
    | head -n 1)

if [ -z "$EXPECTED_VERSION_NAME" ] || [ -z "$EXPECTED_VERSION_CODE" ] \
        || [ -z "$EXPECTED_TARGET_SDK" ] || [ -z "$EXPECTED_FGS" ]; then
    echo "::error::version, android.numeric_version, android.api und foregroundServiceType in buildozer.spec pruefen"
    exit 1
fi

# Android-Bitmasken der Foreground-Service-Typen. specialUse ist 1 << 30.
case "$EXPECTED_FGS" in
    dataSync)             FGS_HEX="1" ;;
    mediaPlayback)       FGS_HEX="2" ;;
    phoneCall)            FGS_HEX="4" ;;
    location)             FGS_HEX="8" ;;
    connectedDevice)      FGS_HEX="10" ;;
    mediaProjection)     FGS_HEX="20" ;;
    camera)               FGS_HEX="40" ;;
    microphone)           FGS_HEX="80" ;;
    health)               FGS_HEX="100" ;;
    remoteMessaging)      FGS_HEX="200" ;;
    systemExempted)       FGS_HEX="400" ;;
    shortService)         FGS_HEX="800" ;;
    specialUse)           FGS_HEX="40000000" ;;
    *)
        echo "::error::unbekannter foregroundServiceType '$EXPECTED_FGS' in buildozer.spec"
        exit 1
        ;;
esac
FGS_DEC=$(printf '%d' "0x$FGS_HEX")

aapt2_finden() {
    if [ -n "${AAPT2:-}" ]; then
        if [ ! -x "$AAPT2" ]; then
            echo "::error::AAPT2 ist nicht ausfuehrbar: $AAPT2" >&2
            return 1
        fi
        printf '%s\n' "$AAPT2"
        return 0
    fi
    if command -v aapt2 >/dev/null 2>&1; then
        command -v aapt2
        return 0
    fi
    for sdk in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" \
               "$HOME/.buildozer/android/platform/android-sdk" \
               "$ROOT/.buildozer/android/platform/android-sdk"; do
        [ -n "$sdk" ] || continue
        [ -d "$sdk/build-tools" ] || continue
        KANDIDAT=$(find "$sdk/build-tools" -maxdepth 2 -type f -name aapt2 \
            2>/dev/null | sort -V | tail -n 1 || true)
        if [ -n "$KANDIDAT" ] && [ -x "$KANDIDAT" ]; then
            printf '%s\n' "$KANDIDAT"
            return 0
        fi
    done
    return 1
}

AAPT2_BIN=$(aapt2_finden || true)
if [ -z "$AAPT2_BIN" ]; then
    echo "::error::aapt2 nicht gefunden (Android build-tools oder AAPT2 setzen)"
    exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
BADGING="$TMP/badging.txt"
TREE="$TMP/xmltree.txt"

if ! "$AAPT2_BIN" dump badging "$APK" >"$BADGING" 2>"$TMP/badging.err"; then
    cat "$TMP/badging.err" >&2
    echo "::error::aapt2 dump badging ist fehlgeschlagen"
    exit 1
fi
if ! "$AAPT2_BIN" dump xmltree "$APK" --file AndroidManifest.xml \
        >"$TREE" 2>"$TMP/xmltree.err"; then
    cat "$TMP/xmltree.err" >&2
    echo "::error::aapt2 dump xmltree AndroidManifest.xml ist fehlgeschlagen"
    exit 1
fi

VERSION_CODE=$(sed -n "s/^package:.*versionCode='\([^']*\)'.*/\1/p" \
    "$BADGING" | head -n 1)
VERSION_NAME=$(sed -n "s/^package:.*versionName='\([^']*\)'.*/\1/p" \
    "$BADGING" | head -n 1)
TARGET_SDK=$(sed -n "s/^targetSdkVersion:'\([^']*\)'.*/\1/p" \
    "$BADGING" | head -n 1)

FEHLER=0
vergleiche() {
    if [ "$2" != "$3" ]; then
        echo "::error::$1 ist '$2', erwartet '$3'"
        FEHLER=1
    fi
}
vergleiche "versionCode" "$VERSION_CODE" "$EXPECTED_VERSION_CODE"
vergleiche "versionName" "$VERSION_NAME" "$EXPECTED_VERSION_NAME"
vergleiche "targetSdkVersion" "$TARGET_SDK" "$EXPECTED_TARGET_SDK"

# Der Service muss im kompilierten Manifest vorhanden sein. aapt2 gibt den
# foregroundServiceType als Integer-Bitmaske aus, z. B. specialUse als
# 0x40000000; die Dezimalform wird zur Sicherheit ebenfalls akzeptiert.
if ! grep -Fq "ServicePs5proscan" "$TREE"; then
    echo "::error::ServicePs5proscan fehlt im kompilierten Manifest"
    FEHLER=1
fi
FGS_LINES=$(grep -F "foregroundServiceType" "$TREE" || true)
if [ -z "$FGS_LINES" ]; then
    echo "::error::foregroundServiceType fehlt im kompilierten Manifest"
    FEHLER=1
elif ! printf '%s\n' "$FGS_LINES" \
        | grep -Eiq "0x0*${FGS_HEX}([^0-9a-f]|$)|(^|[^0-9])${FGS_DEC}([^0-9]|$)" \
        && ! printf '%s\n' "$FGS_LINES" | grep -Fq "$EXPECTED_FGS"; then
    echo "::error::foregroundServiceType ist nicht '$EXPECTED_FGS' (0x$FGS_HEX)"
    printf '%s\n' "$FGS_LINES" | head -n 3
    FEHLER=1
fi

if [ "$FEHLER" -ne 0 ]; then
    exit 1
fi

echo "APK-Manifest ok: versionCode=$VERSION_CODE versionName=$VERSION_NAME targetSdkVersion=$TARGET_SDK foregroundServiceType=$EXPECTED_FGS (0x$FGS_HEX)"
