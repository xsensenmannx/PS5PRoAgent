#!/usr/bin/env bash
# Baut die Android-APK auf einem Linux-Rechner (GitHub-Runner, WSL, VM).
# Genau dieses Skript ruft .github/workflows/build-apk.yml auf - lokal ist es
# derselbe Weg:   bash tools/ci_build.sh
#
# Umgebungsvariablen (optional):
#   SKIP_APT=1   Systempakete nicht anfassen (wenn schon installiert)
#   SKIP_VENV=1  vorhandenes .venv mit Buildozer weiterbenutzen
set -euo pipefail

cd "$(dirname "$0")/.."
say() { printf '\n=== %s ===\n' "$1"; }

# UTF-8 erzwingen: buildozer liest buildozer.spec mit der Locale-Kodierung. Auf
# Systemen mit LANG=C (ASCII) endet das bei Umlauten in Kommentaren mit einem
# UnicodeDecodeError, bevor der Build startet.
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

say "Pflichtdateien pruefen"
missing=0
for f in main.py buildozer.spec icon.png \
         assets/icon_fg.png assets/icon_bg.png tools/selftest.py; do
    if [ ! -f "$f" ]; then
        echo "::error file=$f::Pflichtdatei fehlt: $f"
        missing=1
    fi
done
if [ "$missing" -ne 0 ]; then
    echo "Bitte die genannten Dateien ins Repository legen (GITHUB_ANLEITUNG.md, Schritt 2)."
    exit 1
fi
echo "alle vorhanden"

if [ "${SKIP_APT:-0}" != "1" ]; then
    say "Systempakete"
    sudo apt-get update -qq
    sudo apt-get install -y -qq --no-install-recommends \
        build-essential autoconf automake libtool pkg-config zlib1g-dev \
        libncurses-dev libffi-dev libssl-dev liblzma-dev cmake unzip zip \
        ccache git libltdl-dev
    # aidl fehlt auf manchen Images; buildozer nutzt sonst das SDK-eigene.
    sudo apt-get install -y -qq --no-install-recommends aidl || true
fi

if [ "${SKIP_VENV:-0}" != "1" ]; then
    say "Python 3.12 + Buildozer"
    # python-for-android "master" ist fuer Host-Python bis 3.12 freigegeben.
    if ! command -v uv >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    export PATH="$HOME/.local/bin:$PATH"
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python --upgrade pip setuptools wheel
    uv pip install --python .venv/bin/python \
        "git+https://github.com/kivy/buildozer" "cython==0.29.36" legacy-cgi
fi

.venv/bin/buildozer --version

say "SDK/NDK-Cache pruefen"
bash tools/ci_fix_cache.sh

# Lizenzen nur in ein FERTIGES SDK schreiben. Ein selbst angelegtes SDK-Verzeichnis
# laesst buildozer die Installation ueberspringen ("Android SDK found at ...");
# danach fehlt tools/bin/sdkmanager und der Build bricht ab.
SDK="$HOME/.buildozer/android/platform/android-sdk"
if [ -f "$SDK/tools/bin/sdkmanager" ]; then
    say "Android-SDK-Lizenzen"
    bash tools/ci_licenses.sh
else
    echo "SDK noch nicht installiert - buildozer legt ihn an und beantwortet"
    echo "den Lizenz-Prompt selbst (android.accept_sdk_license = True)"
fi

say "APK bauen"
# Ohne VIRTUAL_ENV ruft buildozer intern `pip install --user` auf, was in einem
# venv mit "Can not perform a '--user' install" abbricht.
export VIRTUAL_ENV="$PWD/.venv"
export PATH="$PWD/.venv/bin:$PATH"

set +e
.venv/bin/buildozer -v android debug 2>&1 | tee buildozer.log
rc=${PIPESTATUS[0]}
set -e

if [ "$rc" -ne 0 ]; then
    echo "::error::buildozer ist mit Code $rc gescheitert - Details in buildozer.log"
    echo "--- Umgebung der Fehlerstelle ---"
    grep -n -B 30 'Command failed' buildozer.log | tail -40 || tail -40 buildozer.log
    exit "$rc"
fi

say "Ergebnis"
ls -lh bin/*.apk
