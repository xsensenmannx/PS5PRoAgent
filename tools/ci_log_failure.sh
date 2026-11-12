#!/usr/bin/env bash
# Zieht aus buildozer.log die Stelle heraus, an der es wirklich gescheitert ist.
#
# Hintergrund: buildozer beendet sich mit "Buildozer failed to execute the last
# command" und einem ENVIRONMENT-Block. Die eigentliche Ursache steht weit
# darueber - ein tail -60 zeigt genau den unbrauchbaren Teil. Genau daran ist
# die Fehlersuche im ersten Actions-Lauf gescheitert.
#
# Aufruf: bash tools/ci_log_failure.sh [buildozer.log]
# Ausgabe ist bewusst klein genug fuer die Job-Zusammenfassung.
set -uo pipefail

LOG="${1:-buildozer.log}"

if [ ! -f "$LOG" ]; then
    echo "kein $LOG vorhanden - der Fehler lag vor dem Build (z. B. Logiktests)."
    exit 0
fi

echo "### Fehlgeschlagener Befehl (letzte Treffer)"
grep -n "Command failed" "$LOG" | tail -n 3 || echo "(kein 'Command failed' im Log)"

echo
echo "### Erste Fehlerstelle mit Kontext"
# Reihenfolge = Wahrscheinlichkeit. Der erste Treffer ist die Ursache; spaetere
# Meldungen sind oft nur Folgefehler ("Command failed" etc.).
line=$(grep -niE "error:|fatal error|Traceback \(most recent call last\)|ModuleNotFoundError|ImportError|Cython\.Compiler|collect2:|undefined reference|No such file or directory" "$LOG" \
        | head -n 1 | cut -d: -f1)
if [ -n "${line:-}" ]; then
    start=$(( line > 10 ? line - 10 : 1 ))
    sed -n "${start},$(( line + 25 ))p" "$LOG"
else
    echo "(kein bekannter Fehlermarker gefunden)"
fi

echo
echo "### Letzte 15 Zeilen"
tail -n 15 "$LOG"
