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
for f in main.py scan_core.py service.py buildozer.spec icon.png \
         assets/icon_fg.png assets/icon_bg.png assets/notify_icon.png tools/selftest.py \
         tools/ci_fix_cache.sh tools/ci_licenses.sh tools/ci_check_apk.sh \
         tools/ci_check_aab.sh tools/p4a_hook.py tools/ci_log_failure.sh \
         android_src/de/ps5pro/ps5prosearchagent/BootReceiver.java; do
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

# Vorab-Pruefung in Sekunden statt nach 40 Minuten Build: p4a baut ohne Pin
# CPython 3.14.2, das mit Cython 0.29.36 (fest im p4a-Recipe) und Kivy 2.3
# nicht kompiliert. Und p4a verlangt python3 == hostpython3.
say "Python-Pin pruefen"
# Wichtig: [[:space:],] vor python3, sonst trifft das Muster auch das
# "python3==" innerhalb von "hostpython3==" und liest die falsche Version.
PYPIN=$(sed -n 's/.*[[:space:],]python3==\([0-9][0-9.]*\).*/\1/p' buildozer.spec | head -n 1)
HOSTPIN=$(sed -n 's/.*hostpython3==\([0-9][0-9.]*\).*/\1/p' buildozer.spec | head -n 1)
if [ -z "$PYPIN" ] || [ -z "$HOSTPIN" ]; then
    echo "::error::buildozer.spec pinnt python3/hostpython3 nicht (requirements)."
    echo "Ohne Pin baut p4a CPython 3.14, das hier nicht kompiliert."
    exit 1
fi
if [ "$PYPIN" != "$HOSTPIN" ]; then
    echo "::error::python3==$PYPIN vs hostpython3==$HOSTPIN - p4a verlangt identische Versionen."
    exit 1
fi
case "$PYPIN" in
    3.10.*|3.11.*|3.12.*) echo "Python $PYPIN (Cython-0.29-kompatibel)" ;;
    *) echo "::error::Python $PYPIN ist zu neu fuer Cython 0.29.36 und Kivy 2.3 (nur 3.10-3.12)."
       exit 1 ;;
esac

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
    say "Python 3.11.9 + Buildozer"
    # p4a master baut ohne Pin CPython 3.14.2, das sich mit Cython 0.29 und
    # Kivy 2.3 nicht kompilieren laesst. buildozer.spec pinnt python3 und
    # hostpython3 deshalb auf 3.11.9; der Host im venv ist derselbe Stand,
    # damit koennen Ziel- und Host-Version nicht auseinanderlaufen.
    if ! command -v uv >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    export PATH="$HOME/.local/bin:$PATH"
    uv venv --python 3.11.9 .venv
    uv pip install --python .venv/bin/python --upgrade pip setuptools wheel
    uv pip install --python .venv/bin/python \
        "git+https://github.com/kivy/buildozer" "cython==0.29.37" legacy-cgi
fi

echo "Host-Python: $(.venv/bin/python -V 2>&1)"
.venv/bin/buildozer --version

say "SDK/NDK-Cache pruefen"
bash tools/ci_fix_cache.sh

# Der Actions-Cache stellt auch einen alten p4a-Dist her. Buildozer baut den
# nicht neu, wenn nur die Spec sich geaendert hat (z. B. android.api 34 -> 36) -
# dann landet still die alte targetSdk in der APK. Deshalb bei geaenderter Spec
# den Dist-Build verwerfen; SDK/NDK in ~/.buildozer bleiben erhalten.
say "Spec-Stand pruefen"
SPEC_HASH=$(sha256sum buildozer.spec | cut -d' ' -f1)
OLD_HASH=$(cat .buildozer/.spec-hash 2>/dev/null || true)
if [ -d .buildozer ] && [ "$OLD_HASH" != "$SPEC_HASH" ]; then
    echo "Spec geaendert - alten Dist-Build verwerfen (SDK/NDK bleiben)"
    rm -rf .buildozer/android/platform/build-*
fi
mkdir -p .buildozer
echo "$SPEC_HASH" > .buildozer/.spec-hash

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

# ARTIFACT=aab signiert ein App Bundle fuer Google Play, sonst Debug-APK.
ARTIFACT="${ARTIFACT:-apk}"
# Ohne VIRTUAL_ENV ruft buildozer intern `pip install --user` auf, was in einem
# venv mit "Can not perform a '--user' install" abbricht.
export VIRTUAL_ENV="$PWD/.venv"
export PATH="$PWD/.venv/bin:$PATH"

if [ "$ARTIFACT" = "aab" ]; then
    say "AAB bauen (signiert)"
    missing=0
    for v in P4A_RELEASE_KEYSTORE P4A_RELEASE_KEYSTORE_PASSWD \
             P4A_RELEASE_KEYALIAS P4A_RELEASE_KEYALIAS_PASSWD; do
        if [ -z "${!v:-}" ]; then
            echo "::error::$v fehlt - AAB waere unsigniert und fuer Play unbrauchbar."
            missing=1
        fi
    done
    if [ "$missing" -ne 0 ]; then
        echo "Secrets siehe PLAY_STORE.md (GitHub -> Settings -> Secrets and variables -> Actions)."
        exit 1
    fi
    if [ ! -f "$P4A_RELEASE_KEYSTORE" ]; then
        echo "::error::Keystore nicht gefunden: $P4A_RELEASE_KEYSTORE"
        exit 1
    fi
    set +e
    .venv/bin/buildozer -v android release 2>&1 | tee buildozer.log
    rc=${PIPESTATUS[0]}
    set -e
else
    say "APK bauen"
    set +e
    .venv/bin/buildozer -v android debug 2>&1 | tee buildozer.log
    rc=${PIPESTATUS[0]}
    set -e
fi

if [ "$rc" -ne 0 ]; then
    echo "::error::buildozer ist mit Code $rc gescheitert - Details in buildozer.log"
    bash tools/ci_log_failure.sh buildozer.log
    # Bekannte Signatur: es wurde gegen ein zu neues CPython gebaut.
    if grep -qE 'include/python3\.(1[3-9])' buildozer.log; then
        echo "::error::Gebaut wurde gegen Python 3.1x. Der Pin aus buildozer.spec"
        echo "(python3==3.11.9, hostpython3==3.11.9) hat nicht gegriffen."
        echo "p4a-Checkout verwerfen: rm -rf .buildozer/android/platform/python-for-android"
    fi
    exit "$rc"
fi

say "Ergebnis"
if [ "$ARTIFACT" = "aab" ]; then
    ls -lh bin/*.aab
    AAB=$(ls -1 bin/*.aab 2>/dev/null | head -n 1 || true)
    bash tools/ci_check_aab.sh "$AAB" "$PYPIN"
else
    ls -lh bin/*.apk
    # "Build erfolgreich" heisst noch nicht, dass die richtige Python-Version
    # in der APK steckt. Genau das hat hier 40 Minuten gekostet.
    APK=$(ls -1 bin/*.apk 2>/dev/null | head -n 1 || true)
    bash tools/ci_check_apk.sh "$APK" "$PYPIN"
fi
