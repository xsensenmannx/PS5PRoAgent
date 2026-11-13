#!/usr/bin/env bash
# Signiert die gebaute APK mit dem festen Release-Schluessel und prueft, dass
# wirklich dieses Zertifikat signiert hat. Ohne diesen Schritt signiert p4a
# jede APK mit einem neu erzeugten Debug-Key - dann laesst sich keine neue
# Version ueber eine bestehende Installation legen.
#
# Umgebung:
#   KEYSTORE_FILE         Pfad zur PKCS#12-Datei (Pflicht)
#   KEYSTORE_PASSWORD     Passwort fuer Store und Key (Pflicht)
#   KEY_ALIAS             Alias im Keystore (Standard: ps5pro)
#   EXPECTED_CERT_SHA256  SHA-256 des Zertifikats, mit oder ohne Doppelpunkte
#
# Aufruf: bash tools/ci_sign_apk.sh [bin/app.apk]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APK="${1:-}"
if [ -z "$APK" ]; then
    APK=$(ls -1 "$ROOT"/bin/*.apk 2>/dev/null | head -n 1 || true)
fi
if [ -z "$APK" ] || [ ! -f "$APK" ]; then
    echo "::error::keine APK gefunden: ${APK:-<leer>}"
    exit 1
fi

: "${KEYSTORE_FILE:?KEYSTORE_FILE fehlt}"
[ -f "$KEYSTORE_FILE" ] || { echo "::error::Keystore nicht gefunden: $KEYSTORE_FILE"; exit 1; }
: "${KEYSTORE_PASSWORD:?KEYSTORE_PASSWORD fehlt}"
: "${EXPECTED_CERT_SHA256:?EXPECTED_CERT_SHA256 fehlt}"
KEY_ALIAS="${KEY_ALIAS:-ps5pro}"

# Zeilenumbrueche aus dem Secret entfernen; apksigner liest das Passwort aus
# der Umgebung, damit es nicht in der Prozessliste auftaucht.
KEYSTORE_PASSWORD=$(printf '%s' "$KEYSTORE_PASSWORD" | tr -d '\r\n')

werkzeuge_finden() {
    local sdk bt
    for sdk in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" \
               "$HOME/.buildozer/android/platform/android-sdk" \
               "$ROOT/.buildozer/android/platform/android-sdk"; do
        [ -n "$sdk" ] && [ -d "$sdk/build-tools" ] || continue
        bt=$(find "$sdk/build-tools" -mindepth 1 -maxdepth 1 -type d 2>/dev/null \
             | sort -V | tail -n 1 || true)
        if [ -n "$bt" ] && [ -x "$bt/apksigner" ] && [ -x "$bt/zipalign" ]; then
            printf '%s\n%s\n' "$bt/apksigner" "$bt/zipalign"
            return 0
        fi
    done
    return 1
}

WERKZEUGE=$(werkzeuge_finden || true)
if [ -z "$WERKZEUGE" ]; then
    echo "::error::apksigner/zipalign nicht gefunden (Android build-tools fehlen)"
    exit 1
fi
APKSIGNER=$(printf '%s\n' "$WERKZEUGE" | sed -n 1p)
ZIPALIGN=$(printf '%s\n' "$WERKZEUGE" | sed -n 2p)

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Alte Debug-Signatur entfernen, damit apksigner sauber neu signiert.
cp "$APK" "$TMP/unsigniert.apk"
zip -q -d "$TMP/unsigniert.apk" "META-INF/*.SF" "META-INF/*.RSA" "META-INF/*.DSA" \
    >/dev/null 2>&1 || true

# zipalign vor dem Signieren: apksigner haengt den v2-Block hinter die
# Zip-Eintraege, die Ausrichtung muss vorher stimmen.
"$ZIPALIGN" -f -p 4 "$TMP/unsigniert.apk" "$TMP/aligned.apk"

"$APKSIGNER" sign \
    --ks "$KEYSTORE_FILE" \
    --ks-type PKCS12 \
    --ks-key-alias "$KEY_ALIAS" \
    --ks-pass env:KEYSTORE_PASSWORD \
    --key-pass env:KEYSTORE_PASSWORD \
    --out "$TMP/signed.apk" \
    "$TMP/aligned.apk"

if ! "$APKSIGNER" verify --verbose --print-certs "$TMP/signed.apk" > "$TMP/certs.txt" 2>&1; then
    cat "$TMP/certs.txt" >&2
    echo "::error::apksigner verify ist gescheitert"
    exit 1
fi

normalisieren() {
    tr -d ':\r' | tr 'A-F' 'a-f' | tr -d '[:space:]'
}

ACTUAL=$(grep -i "certificate SHA-256 digest" "$TMP/certs.txt" | head -n 1 \
    | sed 's/.*digest:[[:space:]]*//' | normalisieren)
EXPECTED=$(printf '%s' "$EXPECTED_CERT_SHA256" | normalisieren)

if [ -z "$ACTUAL" ]; then
    echo "::error::apksigner hat keinen Zertifikat-Fingerprint geliefert"
    exit 1
fi
if [ "$ACTUAL" != "$EXPECTED" ]; then
    echo "::error::Signaturzertifikat weicht ab: $ACTUAL (erwartet $EXPECTED)"
    exit 1
fi

# Erst nach erfolgreicher Pruefung ersetzen: bei einem Fehler bleibt die
# unsignierte APK liegen und der Job bricht ab.
cp "$TMP/signed.apk" "$APK"

echo "APK signiert und geprueft: $APK"
grep -E "Signer #1 certificate (DN|SHA-256)" "$TMP/certs.txt" | sed 's/^/  /'
