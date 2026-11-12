#!/usr/bin/env bash
# Hinterlegt die akzeptierten Android-SDK-Lizenzen, damit sdkmanager nicht
# interaktiv nachfragt. Ohne das bleibt buildozers pexpect-Automatik minutenlang
# beim Lizenztext stehen, bis der Lauf in den Timeout läuft.
#
# Pfad überschreibbar: ANDROID_SDK_LICENSES=/pfad/zu/licenses bash tools/ci_licenses.sh
set -euo pipefail

LIC="${ANDROID_SDK_LICENSES:-$HOME/.buildozer/android/platform/android-sdk/licenses}"
mkdir -p "$LIC"

# SHA1-Hashes der akzeptierten Lizenztexte (android-sdk / preview / googletv).
printf '%s\n%s\n%s\n' \
    8933bad161af4178b1185d1a37fbf41ea5269c55 \
    d56f5187479451eabf01fb78af6dfcb131a6481e \
    24333f8a63b6825ea9c5514f83c2829b004d1fee > "$LIC/android-sdk-license"
printf '%s\n' 84831b9409646a918e30573bab4c9c91346d8abd > "$LIC/android-sdk-preview-license"
printf '%s\n' 601085b94cd77f0b54ff86406957099ebe79c4d6 > "$LIC/android-googletv-license"

echo "SDK-Lizenzen hinterlegt in $LIC"
ls -l "$LIC"
