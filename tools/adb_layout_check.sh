#!/usr/bin/env bash
# Prueft Radar und Trefferliste auf einem angeschlossenen Android-Geraet.
#
#   tools/adb_layout_check.sh [pfad/zur.apk]
#
# Ohne APK wird die bereits installierte App geprueft. Fuer jede Groesse wird
# wm size/wm density gesetzt, die App neu gestartet und die vom Layout
# berechnete Radarflaeche aus logcat gelesen ([Layout] ... radar=NN).
# Dichte 160 heisst: 1 px = 1 dp, damit die dp-Grenzen direkt gelten.
#
# Voraussetzungen: adb im PATH, USB-Debugging, entsperrtes Geraet.
# Groessen ueberschreibbar: PS5PRO_LAYOUT_SIZES="620x380 884x700" ...
set -euo pipefail

PKG="de.ps5pro.ps5prosearchagent"
APK="${1:-}"
SIZES="${PS5PRO_LAYOUT_SIZES:-620x380 640x360 720x480 884x700 360x780 420x820}"

command -v adb >/dev/null 2>&1 || { echo "adb nicht gefunden"; exit 2; }
adb get-state >/dev/null 2>&1 || { echo "kein Geraet ueber adb erreichbar"; exit 2; }

if [ -n "$APK" ]; then
  echo "Installiere $APK"
  adb install -r "$APK" >/dev/null
fi

restore() {
  adb shell wm size reset >/dev/null 2>&1 || true
  adb shell wm density reset >/dev/null 2>&1 || true
  adb shell settings put system accelerometer_rotation 1 >/dev/null 2>&1 || true
}
trap restore EXIT

fail=0
for size in $SIZES; do
  w="${size%x*}"; h="${size#*x}"
  adb shell wm size "${w}x${h}" >/dev/null
  adb shell wm density 160 >/dev/null
  # Querformat erzwingen, damit die App nicht in der Geraeteausrichtung bleibt.
  if [ "$w" -gt "$h" ]; then rot=1; else rot=0; fi
  adb shell settings put system accelerometer_rotation 0 >/dev/null
  adb shell settings put system user_rotation "$rot" >/dev/null
  adb shell am force-stop "$PKG" >/dev/null 2>&1 || true
  adb logcat -c >/dev/null 2>&1 || true
  adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
  sleep 6
  zeile=$(adb logcat -d 2>/dev/null | grep -F '[Layout]' | tail -n 1 || true)
  if [ -z "$zeile" ]; then
    echo "FAIL $size: keine [Layout]-Zeile (App gestartet?)"
    fail=1
    continue
  fi
  radar=$(printf '%s' "$zeile" | sed -n 's/.*radar=\([0-9][0-9]*\).*/\1/p')
  if [ -z "$radar" ] || [ "$radar" -lt 60 ]; then
    echo "FAIL $size: Radarflaeche fehlt oder zu klein ($zeile)"
    fail=1
    continue
  fi
  adb exec-out screencap -p > "layout-${w}x${h}.png"
  echo "PASS $size: $zeile (Screenshot layout-${w}x${h}.png)"
done

if [ "$fail" -ne 0 ]; then
  echo "Mindestens eine Groesse ist durchgefallen." >&2
  exit 1
fi
echo "Alle Groessen bestanden."
