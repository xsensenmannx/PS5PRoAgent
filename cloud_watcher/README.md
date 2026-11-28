# Cloud-Wächter (P0)

Ein kleiner, dauerhaft laufender Prozess für **PS Direct DE/AT** und **Alternate
DE**. PS Direct prüft er rund um die Uhr alle **15 s**, Alternate DE alle
**30 s**. Das ist eine eigene Wahl, kein
gemessener Gleichstand: Der öffentliche Bestell.bar-Feed belegt für den
20.11.2026 einen PS-Direct-Drop, der im Minutenraster um **22:49** bestellbar
und **22:50** wieder ausverkauft war („1 Min. verfügbar“) – also außerhalb des
Fensters **09:00–18:00** (Europe/Berlin). Wie Bestell.bar selbst pollt, lässt
sich daraus nicht ableiten; 15 s halbieren die maximale Verzögerung gegenüber
30 s und kosten mit zwei PS-Direct-Shops 8 Abrufe/Minute. Alternate DE läuft
mit 30 s (2 Abrufe/Minute), zusammen 10 von 12.
Er meldet einen bestätigten Treffer über den vorhandenen Webhook-Weg (ntfy,
Telegram, Discord).

Der Wächter ist **outbound-only**: kein Port, kein Konto, keine App-Änderung.
Er nutzt `scan_core.py` aus diesem Repository, damit Preis-, JSON-LD- und
Bot-Schutz-Logik nicht doppelt gepflegt werden.

## Schattenbetrieb: 48 Stunden ohne Versand

Beim ersten Start legt der Wächter `/data/cloud_watch_state.json` an und setzt
`schatten_bis` auf **jetzt + 48 h**. In dieser Zeit wird geprüft und
protokolliert, aber **keine Alarmmeldung gesendet** – auch dann nicht, wenn ein
Webhook konfiguriert ist. Ein optionaler `WATCH_HEARTBEAT_URL` ist nur ein
Lebenszeichen und standardmäßig aus. Für den Schattenlauf ist er empfohlen:
Ohne Lebenszeichen sieht ein abgestürzter Wächter wie „kein Restock“ aus.

Zwei Sicherungen greifen unabhängig voneinander:

1. `WATCH_SHADOW=1` (Standard) hält den Wächter im Schattenmodus.
2. Selbst mit `WATCH_SHADOW=0` wird vor Ablauf von `schatten_bis` nicht
   gesendet.

Nach den 48 Stunden prüft man die Logs und schaltet bewusst scharf:

- Fly.io: in `fly.toml` unter `[env]` `WATCH_SHADOW = "0"` setzen, `fly deploy`.
- Hetzner: in `cloud_watcher/.env` `WATCH_SHADOW=0` setzen,
  `docker compose up -d --force-recreate`.

Ein Löschen des Zustandsvolumes setzt die 48 Stunden wieder auf null. Das ist
Absicht: Ein neuer Datenstand ist ein neuer Schattenlauf. Der Zustand bleibt
beim Scharfschalten erhalten: Ein Artikel, der bereits während des
Schattenlaufs verfügbar wurde, löst deshalb keine neue Live-Meldung aus; die
Schattenzeile `wuerde_senden` zeigt ihn.

Der **erste gültige Abruf eines Shops ist nur Baseline** und löst keinen Alarm
aus. Erst ein späterer Wechsel auf „verfügbar“ meldet. Ein Wächterstart während
eines laufenden Verkaufs schickt also keine Altmeldung.

## Zwei Shops

| Shop | Land | Quelle |
|---|---|---|
| PS Direct DE | DE | `https://www.playstation.com/de-de/ps5/ps5-pro/buy-now/` |
| PS Direct AT | AT | `https://www.playstation.com/de-at/ps5/ps5-pro/buy-now/` |

Beide Seiten liefern ein JSON-LD mit Preis und Verfügbarkeit (rund 33 KB). Der
Wächter liest dafür höchstens 64 KB, prüft einen Treffer mit einem zweiten
Abruf nach und stuft ihn bei `sold_out` wieder zurück. Weitere Shops kommen
erst nach dem Schattenlauf dazu.

## Lokal starten (ohne Docker)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: . .venv/bin/activate
pip install -r cloud_watcher/requirements.txt

# Git Bash
WATCH_DATA_DIR=./cloud_watcher/data WATCH_SHADOW=1 \
  python -m cloud_watcher.watcher

# PowerShell
$env:WATCH_DATA_DIR="./cloud_watcher/data"; $env:WATCH_SHADOW="1"
python -m cloud_watcher.watcher
```

Die Ausgabe ist zeilenweises JSON auf stdout; dieselben Zeilen landen als
NDJSON-Tagesdateien im Datenverzeichnis (siehe „Logs und Zustand“). Der lokale
Schattenlauf braucht keinen Webhook. `Strg+C` beendet sauber und schreibt den
Zustand.

### Alarmweg einmal testen

`--test-alarm` schickt eine klar markierte Testnachricht durch den echten
Outbox-Weg und meldet das Ergebnis (Details unter „Testalarm“):

```bash
WATCH_WEBHOOK_URL='https://ntfy.sh/<geheimer-topic>' \
  python -m cloud_watcher.watcher --test-alarm
```

Für einen kompletten Wächterlauf
ohne 48-h-Wartezeit kann man die Frist auf einem Wegwerf-Datenverzeichnis
überspringen; eine Zustellung kommt dabei aber nur bei einem echten Ereignis:

```bash
WATCH_DATA_DIR=./cloud_watcher/data/testalarm \
WATCH_SHADOW=0 WATCH_SHADOW_HOURS=0 \
WATCH_WEBHOOK_URL='https://ntfy.sh/<geheimer-topic>' \
  python -m cloud_watcher.watcher
```

Im Normalbetrieb bleibt es bei 48 Stunden. Die Webhook-URL nie in eine Datei
schreiben, die ins Repository gelangt.

## Fly.io

Voraussetzungen: `flyctl` ist angemeldet, die App und ein Volume existieren.
Der App-Name in `fly.toml` muss frei sein.

```bash
# aus dem Repository-Hauptverzeichnis
fly apps create ps5pro-watcher        # oder Namen in fly.toml anpassen
fly volumes create watcher_data --region fra --size 1
fly secrets set WATCH_WEBHOOK_URL='https://ntfy.sh/<geheimer-topic>'
# optional:
# fly secrets set WATCH_HEARTBEAT_URL='https://hc-ping.com/<uuid>'
# fly secrets set WATCH_OPS_WEBHOOK_URL='https://ntfy.sh/<geheimer-ops-topic>'

fly deploy
fly logs
```

`fly.toml` nutzt `shared-cpu-1x` mit 512 MB und ein 1-GB-Volume. Der Prozess
hat keinen HTTP-Dienst; Fly startet ihn als Worker. Die Neustartpolitik
`always` hält ihn auch nach einem Host-Neustart am Laufen. `SIGTERM` wird
abgefangen, der Zustand wird beim Beenden atomar gespeichert.

Zustand und Schattenfrist prüfen:

```bash
fly ssh console -C 'cat /data/cloud_watch_state.json'
```

Scharf schalten nach dem Schattenlauf:

```bash
# fly.toml: WATCH_SHADOW = "0"
fly deploy
```

Stoppen, ohne Daten zu löschen:

```bash
fly scale count 0
# wieder starten
fly scale count 1
```

## Hetzner (Docker Compose)

```bash
git clone <repository> && cd PS5ProSerachAGENT-apk
cp cloud_watcher/.env.example cloud_watcher/.env
# cloud_watcher/.env bearbeiten: WATCH_WEBHOOK_URL setzen
cd cloud_watcher
docker compose up -d --build
docker compose logs -f --tail=50
```

Das Composefile baut aus dem Repository-Hauptverzeichnis, läuft mit
`read_only`, ohne Capabilities und als UID 10001. Der Zustand liegt im
benannten Volume `watcher_data`. Das Image bringt einen `HEALTHCHECK` mit,
der `watcher_status.json` liest; `docker compose ps` zeigt damit `healthy`
oder `unhealthy`. Auf Fly.io wird der Docker-Healthcheck nicht ausgewertet –
dort tragen die Neustartpolitik und der externe Heartbeat.

```bash
# Zustand ansehen
docker compose exec watcher cat /data/cloud_watch_state.json
# Scharf schalten: WATCH_SHADOW=0 in .env, dann
docker compose up -d --force-recreate
# Anhalten (Daten bleiben)
docker compose down
# Anhalten und Daten löschen (setzt die 48 h zurück)
docker compose down -v
```

Auf einem frischen Host muss Docker installiert sein; weitere Pakete braucht
der Container nicht.

## Konfiguration

| Variable | Standard | Bedeutung |
|---|---|---|
| `WATCH_SHOPS` | `PS Direct DE,PS Direct AT,Alternate DE` | Exakte Namen aus `scan_core.HAENDLER` |
| `WATCH_TAKT` | `15` | Sekunden für PS Direct, auf 15–3600 begrenzt |
| `WATCH_TAKT_NEBEN` | `30` | Sekunden für die Zusatzshops, auf 30–3600 begrenzt |
| `WATCH_SHADOW` | `1` | `0` erst nach dem Schattenlauf |
| `WATCH_SHADOW_HOURS` | `48` | Frist beim ersten Start; wird nie verkürzt |
| `WATCH_MAX_PREIS` | `900` | Preisdeckel in Euro; AT erbt DE |
| `WATCH_PREIS_TOLERANZ` | `1` | Neupreis-Alarm erst ab dieser Senkung in Euro gegenüber dem letzten Alarm; Restock bleibt unberührt |
| `WATCH_MAX_REQ_MIN` | `12` | Globales Request-Budget pro Minute; PS Direct zuerst |
| `WATCH_TZ` | `Europe/Berlin` | Log-Zeit und Tagesgrenze |
| `WATCH_DATA_DIR` | `/data` | Zustand, Health, HTTP-Cache, NDJSON-Logs |
| `WATCH_WEBHOOK_URL` | leer | **Geheim.** ntfy-/Telegram-/Discord-URL |
| `WATCH_WEBHOOK_PRESET` | automatisch | `ntfy`, `telegram`, `discord`, `generisch` |
| `WATCH_OPS_WEBHOOK_URL` | leer | Optionaler Kanal nur für den Systemalarm; nur HTTPS, sonst Produkt-Webhook; geheim |
| `WATCH_HEARTBEAT_URL` | leer | Optionaler Lebenszeichen-Ping alle 60 s, geheim |

PS Direct läuft mit 15 s (**8 Abrufe/Minute** für zwei Shops), Alternate DE mit
30 s (**2**). Das sind **10 von 12** Abrufen pro Minute; bei knappem Budget bedient der Wächter zuerst PS Direct.
Die früheren Variablen `WATCH_WINDOW_TAKT` und `WATCH_TAKT_AUSSEN` entfallen;
`WATCH_TAKT` gilt rund um die Uhr, `WATCH_TAKT_NEBEN` für alle Shops außerhalb
von PS Direct.

`WATCH_MAX_REQ_MIN` zählt echte Abrufe im gleitenden 60-Sekunden-Fenster; ist
es erschöpft, wartet der Wächter kurz, statt heiß zu drehen, und bedient bei
knappem Budget zuerst PS Direct DE/AT. `WATCH_PREIS_TOLERANZ` gilt nur für
neue Preise und misst gegen den Preis des letzten Alarms: Mehrere kleine
Senkungen summieren sich, ein Restock meldet immer.

### Tagesbericht

Zum lokalen Tageswechsel (00:00 `WATCH_TZ`) schickt der Wächter **einmal pro
Tag** eine Zusammenfassung über den Ops-Kanal (`WATCH_OPS_WEBHOOK_URL`); ohne
Ops-Kanal geht sie an den Produkt-Webhook. Inhalt: Checks, Treffer,
Challenges, Parser-/Netzfehler, Erfolgsquote, Anfragen, **p50/p95** der
Abrufdauer, **Lücken über zwei Takte** (Anzahl, Summe, längste), Alarme,
Outbox-Stand sowie die Canary-Zeilen (Fehlerserien, Kaufbox-Drift). Das ist
eine Statusmeldung, kein Alarm — sie geht auch im Schattenmodus raus.

Eine **Lücke** ist der Abstand zwischen zwei Prüfungen desselben Shops, der
über dem Doppelten seines Takts liegt. Geplante Pausen zählen mit; ihre
Ursache steht in den Zählern `challenge`, `fehler` und `parser`. Schlägt der
Versand fehl, versucht es der Wächter dreimal im Abstand von fünf Minuten und
vermerkt danach `tag_bericht` mit `aufgegeben` im NDJSON-Log.

### Parser-Canary

Zwei stille Ausfälle sollen auffallen, ohne einen einzigen Extra-Abruf:

- **Fehlerserie:** Drei Parser- oder Netzfehler in Folge (`error`/`parser`,
  ohne Challenge dazwischen) tragen den Shop als `Canary: …` in den
  Tagesbericht. Gemeldet wird gesammelt einmal pro Tag über den Ops-Kanal;
  ein erfolgreicher Abruf setzt die Serie zurück.
- **Kaufbox-Fingerprint:** Aus der ohnehin geladenen Seite hasht der Scan die
  Reihenfolge der Preis-Marker (`corePrice_feature_div`, `a-price-whole`,
  `a-offscreen`, `availability`, JSON-LD …) — ohne Preise, Bestand oder
  Tokens. Ändert sich der Hash, steht `markup_drift` mit altem und neuem
  Fingerprint im NDJSON-Log und der Shop erscheint unter `Kaufbox-Drift`.
  Fortgeschrieben wird der Fingerprint nur bei einem Abruf mit Preis; eine
  gesperrte oder kaputte Seite erzeugt keinen Drift.

### ntfy

Ein langes, zufälliges Topic verwenden, nicht `ps5pro`. Die URL ist der
Schreibzugang:

```
https://ntfy.sh/<geheimer-topic>
```

Der Wächter sendet Titel, Text und den Produktlink als `Click`-Header.

### Telegram

1. Bot bei `@BotFather` anlegen.
2. Dem Bot eine Nachricht schicken.
3. `chat_id` über `https://api.telegram.org/bot<TOKEN>/getUpdates` holen.
4. URL mit `chat_id` als Query-Parameter setzen:

```
https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>
```

Der Token steht in der URL und damit im Fly-Secret bzw. in der lokalen `.env`.
Er wird nie geloggt.

## Logs und Zustand

Beispiele (eine Zeile pro Ereignis):

```json
{"typ":"start","schatten":true,"schatten_bis":"2026-11-23T10:00:00+01:00","shops":["PS Direct DE","PS Direct AT"],"preset":"ntfy"}
{"typ":"check","shop":"PS Direct DE","klass":"unavail","preis":899.99,"status":"sold_out","ms":420,"verify":null,"event":null}
{"typ":"alarm","modus":"schatten","shop":"PS Direct DE","event":"restock","aktion":"wuerde_senden","ok":null}
{"typ":"runde","geprueft":2,"treffer":0,"dauer_ms":910,"schatten":true}
```

- `preflight` prüft vor dem ersten Abruf Datenverzeichnis, Webhook (live
  Pflicht und HTTPS), Ops-Kanal und Zustand; ein kritischer Fehler beendet den
  Start mit Code 2.
- `check` zeigt jeden Abruf, auch Fehler und Sperren.
- `alarm` mit `aktion: wuerde_senden` ist der Schattenalarm. Es wird kein
  Webhook kontaktiert.
- `alarm` mit `modus: live` und `aktion: eingereiht` ist persistent
  vorgemerkt; die Zustellung selbst erscheint als `outbox`.
- `outbox` mit `aktion: gesendet` ist eine echte Zustellung.
- `start` zeigt die Schattenfrist und den maskierten Webhook (`https://host/…`).
- `systemalarm` zeigt `kanal: ops` oder `kanal: produkt`, nie die URL.
- `tag` ist die Tageszusammenfassung beim lokalen Tageswechsel: Checks,
  Treffer, Quote, p50/p95 der Prüfdauer, Challenge-/Parserfehler, Requests und
  offene Outbox-Einträge.
- `challenge` erscheint einmal pro Tag, wenn ein Shop nach drei Challenges in
  Folge für 60 Minuten pausiert.
- `runde` nennt `budget_verbraucht` und `budget_max`.
- `heartbeat` zeigt nur `ok`/`info`, nie die URL.
- `testalarm` zeigt `ok` und den Grund eines fehlgeschlagenen Testalarms.

Die Zeilen werden zusätzlich im Datenverzeichnis gespeichert:
`watcher-log-YYYY-MM-DD.ndjson`, Tagesgrenze nach `WATCH_TZ`. Pro Tag sind
höchstens drei Teile à 4 MB erlaubt (`…-2.ndjson`, `…-3.ndjson`); danach wird
bis zum nächsten Tag verworfen und einmal `log_verworfen` auf stdout gemeldet.
Dateien älter als 14 Tage löscht der Wächter beim Start und beim Tageswechsel.
Jede Zeile wird sofort geflusht, beim Wechsel und beim Beenden zusätzlich
fsync; ein harter Stopp kostet höchstens die letzte Zeile.

Der Zustand enthält pro Shop `initialisiert`, `verfuegbar`, `preis`,
`alarm_preis` (Referenz der Preistoleranz), `tief`, `status`, `fail_streak`,
`challenge_bis` und den letzten Erfolg. `verfuegbar`
wird nur bei einem bestätigten, sofort kaufbaren, nicht gebrauchten Treffer
`true`; unbestätigte Treffer, Vorbestellungen und Gebrauchtware bleiben
`false`, damit der spätere echte Restock nicht verdeckt wird. Die Datei wird
über eine temporäre Datei plus `os.replace` atomar geschrieben.

Zusätzlich schreibt der Loop höchstens alle 15 s `watcher_status.json` mit
`wach_ts`, `runden`, `letzte_runde`, Schattenmodus, Outbox-Stand und
Budgetverbrauch. Der Docker-Healthcheck liest nur diese Datei und meldet den
Container nach 180 s ohne frische Wachzeit als unhealthy. Damit ist ein
hängender Loop von einer gewollten Challenge-Pause unterscheidbar: Der
Heartbeat pingt alle 60 s unabhängig von fälligen Shops, die Statusdatei
bleibt frisch. Der Ping meldet `ok runden=… offen=… fehler=… verfallen=…
budget=…/…`, damit ein kaputter Alarmweg nicht als „ok“ durchgeht.

### Ausfallsicherung der Live-Alarme

Ein Live-Alarm wird zuerst als Outbox-Eintrag im Zustand gespeichert und erst
dann gesendet. Schlägt die Zustellung fehl, versucht der Wächter es nach
**30 s, 2 min und 10 min** erneut.

Ein Treffer-Alarm **verfällt nach 10 Minuten**: Ein „verfügbar“, das eine
Stunde später ankommt, ist bei einem Fenster von einer Minute eine
Falschmeldung. Solche Einträge werden als `expired` mit Grund `zu_alt`
markiert, nicht mehr gesendet und im Tagesbericht als „verfallen“ gezählt.
Die Frist gilt nur für `new`/`restock`; Testalarm und Systemalarm sind
ausgenommen. HTTP-4xx (außer 408/425/429) beendet die Zustellung sofort als
`failed`, und es wird einmalig ein Systemalarm über den konfigurierten
Webhook versucht. Im Schattenmodus entstehen keine Outbox-Einträge.

Ist zusätzlich `WATCH_OPS_WEBHOOK_URL` gesetzt, geht **nur** dieser
Systemalarm an den Ops-Kanal. Ein endgültig fehlgeschlagener Produkt-Webhook
blockiert die Warnung dann nicht; der Produkt-Webhook selbst bleibt
unverändert. Ohne Ops-Kanal nutzt der Systemalarm weiterhin den
Produkt-Webhook. Eine Ops-URL ohne vollständiges HTTPS gilt als nicht gesetzt,
dann greift der Produkt-Webhook. Schlägt der Systemalarm fehl, wird er bis zu
dreimal versucht (nach 2 und 10 Minuten) und erst danach endgültig als
fehlgeschlagen markiert. Auch die Ops-URL wird nie geloggt.

### Testalarm

Der erste echte Alarm soll nicht der Test sein. Dieses Kommando schickt eine
klar markierte Nachricht (`Waechter Testalarm (kein Treffer)`) durch denselben
Weg wie ein Treffer: vormerken, im Zustand persistieren, senden, Ergebnis
melden. Es funktioniert auch im Schattenmodus, weil es kein Produkttreffer ist.

```bash
python -m cloud_watcher.watcher --test-alarm
docker compose exec watcher python -m cloud_watcher.watcher --test-alarm
```

Exit-Code 0 heißt zugestellt, 1 heißt fehlgeschlagen; der Grund steht auf
stderr, ohne URL. Ein Fehlschlag bleibt nicht als Retry in der Outbox, ein
erfolgreicher Test bleibt als `sent` sichtbar und wird später aufgeräumt.

```
testalarm: {"typ": "testalarm", "ok": true, "info": "gesendet"}
outbox:    {"aktion": "gesendet", "shop": "Testalarm", ...}
```

### Schattenlauf auswerten

Vor dem Scharfschalten die Logs des gesamten Zeitraums ansehen:

- `start`: `schatten: true`, `schatten_bis` und beide Shops.
- `check`: für beide Shops regelmäßige Zeilen; `klass: parser`/`challenge`
  und `fehler` prüfen, `ms`/`bytes` auf Auffälligkeiten.
- `alarm` mit `modus: schatten` und `aktion: wuerde_senden`: Das sind die
  Meldungen, die live rausgegangen wären; Titel, Text und Link prüfen.
- `runde`: `geprueft` zeigt die Zahl der in dieser Runde fälligen Shops (1
  oder 2); `dauer_ms` sollte deutlich unter dem Takt liegen.
- `heartbeat`: Mit gesetztem `WATCH_HEARTBEAT_URL` zeigt der externe Dienst,
  ob der Prozess durchlief. Ohne Heartbeat ist ein abgestürzter Wächter nicht
  von einem ruhigen Markt zu unterscheiden.

Die NDJSON-Dateien liegen im Volume und sind damit die eigentliche Historie
für den 48-h-Lauf; ein Log-Drain ist nicht nötig. Auswerten:

```bash
# lokal, Logs im Projektverzeichnis
python tools/watcher_report.py --dir cloud_watcher/data

# im Container (Hetzner)
docker compose exec watcher python tools/watcher_report.py --dir /data --json
```

Der Report beginnt mit der **Abnahme des 48-h-Laufs**: sechs Kriterien.
Abdeckung je Kalendertag und je Shop (jede erwartete Stunde mindestens ein
gültiger Check, Randtage mit ihrem tatsächlichen Fenster, größte Lücke je
Shop und über alle Shops höchstens 5 Minuten), Shop-Quote (Ungültig-Anteil
je Shop), höchstens
5 % übersprungene fällige Shops, kein volles Minutenbudget, mindestens ein
erfolgreicher Alarm-Canary je Kalendertag (mehrere Läufe am selben Tag sind
erlaubt) und keine stillen Shops. Abdeckung und
Beobachtungszeit zählen nur gültige Bestandsbeobachtungen (`hit`,
`expensive`, `unavail`, `unknown`); je Shop müssen Challenge-/Fehlerquote und
der Anteil ungültiger Checks (inklusive `chance`; Challenge und Fehler sind
darin enthalten) unter 5 % liegen. Die Challenge-/Fehlerquote steht getrennt
daneben. Die Entscheidung nutzt den ungerundeten Wert; angezeigt werden zwei
Nachkommastellen. Eine eigene Sitzungsprüfung entfällt: Die Lückengrenze von
5 Minuten ist strenger als „eine Sitzung“ und deckt sie ab. Oben steht `BESTANDEN` oder
`NICHT BESTANDEN`; `--json` liefert dasselbe als `abnahme.bestanden` und
`abnahme.fehlgeschlagen`.

Das Tool berechnet p50/p95 der Prüfdauer, die 304-Quote (Anteil der Abrufe mit
beobachtetem HTTP 304), Traffic aus der Summe von `bytes`, Alarme und die
Kosten pro nützlichem Alarm (`--kosten`, Standard 4,40 €/Monat). Checks mit
`frisch: false` sind zusätzlich die aus dem Cache beantworteten; ein 304 im
JSON-Fastpath wird als `not_modified: true` vermerkt, auch wenn danach frisch
neu geladen wurde. Nützlich heißt: nicht unterdrückt und
nicht wegen voller Outbox verworfen; im Schatten zählen `wuerde_senden`, live
`eingereiht`. `zugestellt` zählt `outbox`/`gesendet`. Der zweite
Verifikationsabruf eines Treffers steckt nicht in `check.bytes`; die
Traffic-Zahl ist deshalb eine leichte Untergrenze.

## Grenzen und Verhalten

- **Nur öffentliche Produktseiten.** Kein Warenkorb, kein Captcha, keine
  Proxy-Rotation. Bei `403`/`429` wird der Shop 15 Minuten ausgesetzt; zwei
  Parser-/Netzfehler in Folge ergeben 12 Minuten Pause.
- **Ein Treffer wird zweitgeprüft.** Ist die Seite beim zweiten Abruf
  ausverkauft oder unklar, gibt es keinen Alarm.
- **Keine Gebrauchtware, keine Vorbestellung, kein „Chance“-Alarm.** Die
  Bestandsregel `ist_sofort_treffer` setzt `verfuegbar` nur für einen
  bestätigten, sofort kaufbaren, neuen Treffer; nur dann entsteht ein Alarm.
- **Kein Alarm beim ersten Abruf.** Baseline verhindert Altmeldungen.
- **Zustandsverlust startet den Schattenlauf neu.** Das Volume ist die
  Gedächtnisdatei; ohne es gibt es keine 48-h-Historie.
- **Die 48-h-Frist ist Wanduhr, keine Uptime-Garantie.** Ein Ausfall verkürzt
  die beobachtete Zeit. Die Neustartpolitik `always` und
  `WATCH_HEARTBEAT_URL` machen Lücken sichtbar.
- **Parseränderung ist sichtbar, aber still.** Ein `parser`-Fehler steht in
  `check` und in der Health-Datei; er löst keinen Produktalarm aus.
- **Der Wächter ersetzt keine Garantie.** Shops können A/B-Tests, Geoblocking
  oder andere Markup-Varianten ausliefern. Der Schattenlauf ist genau dafür da,
  das vor dem Scharfschalten zu sehen.

## Tests

Die reinen Bausteine (Konfiguration, Takt, Schattenfrist, Baseline, Zustand,
Nachrichtenformat) laufen ohne Netz und ohne Kivy:

```bash
python -m py_compile scan_core.py cloud_watcher/watcher.py
PYTHONIOENCODING=utf-8 python tools/selftest.py
```
