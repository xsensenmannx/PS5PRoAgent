# Schattenlauf im Dauerbetrieb

Betriebsanleitung für den lokalen 48-Stunden-Schattenlauf des Cloud-Wächters
auf diesem Rechner. Der Lauf prüft PS Direct DE/AT im 15-s-Takt sowie
Alternate DE im 30-s-Takt, protokolliert alles und sendet **keine** Alarme.

## Was läuft

| Prozess | Aufgabe | Start |
| --- | --- | --- |
| `tools/shadow_guard.py --supervise` | Wache: startet den Wächter neu, hält den Rechner wach, beendet alles zum Fristende | Autostart nach Anmeldung, sonst manuell |
| `python -m cloud_watcher.watcher` | Wächter: Abrufe, Zustand, NDJSON-Log | von der Wache gestartet |

Beide Prozesse laufen mit dem System-Python (3.12) und den Abhängigkeiten aus
`cloud_watcher/requirements.txt` (`requests`, `tzdata`). Weitere Pakete braucht
der Lauf nicht.

Datenverzeichnis des aktuellen Laufs:

```
_verify/cloud_shadow_20261123_225425
```

Die Wache schreibt in dieses Verzeichnis:

| Datei | Inhalt |
| --- | --- |
| `cloud_watch_state.json` | Zustand, Runden, Schattenfrist, Outbox, Tageszähler |
| `watcher_status.json` | Lebenszeichen des Wächters, PID, Runden |
| `watcher-log-YYYY-MM-DD.ndjson` | eine Zeile je Abruf, Runde und Alarm |
| `guard_status.json` | Lebenszeichen der Wache, Neustarts, Schlafschutz |
| `guard.log` | Klartext-Protokoll der Wache (Start, Neustart, Fristende) |
| `run.log` | Standardausgabe des Wächters |

## Fortschritt prüfen

Kurzfassung, empfohlen:

```bash
python tools/shadow_guard.py --status
```

Beispielausgabe:

```
Waechter:     laeuft (PID 6816), letzter Status vor 10 s
Runden:       17, letzte Runde 2026-11-24 13:52:46
Schatten bis: 2026-11-25 22:54:26 (noch 33.0 h)
Heute:        2 Checks, 0 Treffer, 0 Challenges, 0 Parserfehler, 0 Alarme
Alarme:       0 gesendet, 0 im Schatten; Outbox 0 offen, 0 fehlerhaft
Wache:        laeuft (PID 11356), 1 Neustarts, Schlafschutz aktiv
Abkopplung:   ok
```

Worauf zu achten ist:

- **`Waechter: laeuft`** und `letzter Status vor` deutlich unter 300 s. Älter
  heißt: der Wächter hängt, die Wache ersetzt ihn beim nächsten Takt.
- **`Abkopplung: ok`** – die Wache hängt nicht an der aufrufenden Sitzung.
  `fehlt (Auftragsgruppe)` bedeutet, dass sie beim Schließen des Aufrufers
  mit beendet wird; dann `--detach` erneut ausführen.
- **`Runden`** muss zwischen zwei Prüfungen steigen (PS Direct rund um die
  Uhr etwa alle 15 s, Zusatzshops alle 30 s).
- **`Schatten bis`** bleibt fest; die Frist wird nie verlängert oder verkürzt.
- **`Schlafschutz aktiv`** bestätigt, dass der Standby blockiert ist.

Zum Tageswechsel schickt der Wächter zusätzlich einen **Tagesbericht** über den
Ops-Kanal (`WATCH_OPS_WEBHOOK_URL`), inklusive p95-Abrufdauer und Lücken über
zwei Takte. Die Wache setzt den Ops-Kanal bewusst leer, damit der Schattenlauf
keine Meldung nach außen schickt.

Ausführliche Auswertung über den gesamten Lauf:

```bash
python tools/watcher_report.py --dir _verify/cloud_shadow_20261123_225425
```

Rohdaten und Protokoll:

```bash
type _verify\cloud_shadow_20261123_225425\watcher_status.json
type _verify\cloud_shadow_20261123_225425\guard.log
powershell -NoProfile -Command "Get-Content '_verify\cloud_shadow_20261123_225425\guard.log' -Tail 20"
```

## Neustart und Schlafmodus

Abgesichert:

- **Standby (S3):** Die Wache hält dauerhaft eine Ausführungsanforderung
  (`SetThreadExecutionState`). Der Rechner geht nicht in den Standby, der
  Bildschirm darf abschalten.
- **Absturz des Wächters:** Die Wache prüft alle 20 s PID und Statusalter und
  startet den Wächter neu, höchstens einmal pro Minute. Neustarts stehen in
  `guard_status.json` und `guard.log`.
- **Neustart des Rechners:** Nach der Benutzeranmeldung startet die Wache über
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PS5ProShadowWatcher.cmd`
  und setzt den Lauf im selben Datenverzeichnis fort (`cloud_watch_state.json`).

Nicht abgesichert:

- **Rechner aus oder im Ruhezustand:** Ohne Strom läuft nichts. Die Frist
  `schatten_bis` ist ein absoluter Zeitpunkt und läuft weiter; es entsteht eine
  Messlücke, keine Falschdaten.
- **Neustart ohne Anmeldung:** Autostart greift erst nach der Anmeldung. Ein
  unbeaufsichtigter Neustart (etwa durch Windows Update) pausiert den Lauf bis
  zur nächsten Anmeldung.
- **Erzwungener Standby:** Ein geschlossener Deckel oder ein manuell
  ausgelöster Standby kann die Anforderung überstimmen.

Nach einem Neustart genügt also: anmelden, dann `--status` prüfen. Steht dort
`Waechter: laeuft NICHT`, einmal `python tools/shadow_guard.py --detach`
ausführen.

## Steuern

```bash
# Wache und Wächter abgekoppelt starten
python tools/shadow_guard.py --detach

# Zustand im Vordergrund prüfen und den Wächter bei Bedarf einmal starten
python tools/shadow_guard.py --once

# Alles beenden (Zustand bleibt erhalten)
python tools/shadow_guard.py --stop

# Autostart einrichten bzw. entfernen
python tools/shadow_guard.py --install-startup
python tools/shadow_guard.py --remove-startup
```

Zum Fristende beendet die Wache den Wächter selbst und trägt
`laeuft: false` in `guard_status.json` ein.

## Sicherheitsregeln

Die Wache setzt für jeden Start fest:

```
WATCH_SHADOW=1
WATCH_WEBHOOK_URL=
WATCH_OPS_WEBHOOK_URL=
WATCH_HEARTBEAT_URL=
```

Damit sind Produktionsalarme aus diesem Lauf strukturell ausgeschlossen, auch
wenn in der Umgebung etwas anderes gesetzt wäre. Prüfen lässt sich das an jeder
`start`-Zeile im NDJSON-Log: `"schatten": true`, `"webhook": "-"`,
`"heartbeat": false`, `"ops": false`. Zusätzlich bleiben `alarme_gesendet: 0`
und eine leere Outbox im Zustand.

Erst nach dem Fristende und nur mit ausdrücklicher Freigabe wird
`WATCH_SHADOW=0` gesetzt; dafür ist ein anderer Startweg nötig, nicht diese
Wache.
