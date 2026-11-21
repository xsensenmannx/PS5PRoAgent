# Cloud-Wächter (P0)

Ein kleiner, dauerhaft laufender Prozess für **PS Direct DE** und **PS Direct
AT**. Er prüft die öffentlichen Produktseiten im Fenster **09:00–18:00**
(Europe/Berlin) alle **30–60 s**, außerhalb ruhiger, und meldet einen
bestätigten Treffer über den vorhandenen Webhook-Weg (ntfy, Telegram, Discord).

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

Die Ausgabe ist zeilenweises JSON auf stdout. Der lokale Schattenlauf braucht
keinen Webhook. `Strg+C` beendet sauber und schreibt den Zustand.

### Alarmweg einmal testen

Der direkte Kanal-Test sendet sofort, ohne auf einen Treffer zu warten. Er
nutzt denselben Transport und dasselbe Nachrichtenformat wie der Wächter:

```bash
WATCH_WEBHOOK_URL='https://ntfy.sh/<geheimer-topic>' \
  python -c "import os,scan_core as c; u=os.environ['WATCH_WEBHOOK_URL']; print(c.webhook_senden(u,c.webhook_preset(u),'PS5 Pro Waechter','Testalarm','https://example.invalid'))"
```

`(True, 'HTTP 200')` bedeutet angekommen. Für einen kompletten Wächterlauf
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
benannten Volume `watcher_data`.

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
| `WATCH_SHOPS` | `PS Direct DE,PS Direct AT` | Exakte Namen aus `scan_core.HAENDLER` |
| `WATCH_WINDOW_TAKT` | `45` | Sekunden im Fenster, auf 30–60 begrenzt |
| `WATCH_TAKT_AUSSEN` | `180` | Sekunden außerhalb, mindestens 60 |
| `WATCH_SHADOW` | `1` | `0` erst nach dem Schattenlauf |
| `WATCH_SHADOW_HOURS` | `48` | Frist beim ersten Start; wird nie verkürzt |
| `WATCH_MAX_PREIS` | `900` | Preisdeckel in Euro; AT erbt DE |
| `WATCH_PREIS_TOLERANZ` | `1` | Neupreis-Alarm erst ab dieser Senkung in Euro; Restock bleibt unberührt |
| `WATCH_MAX_REQ_MIN` | `12` | Globales Request-Budget pro Minute; PS Direct zuerst |
| `WATCH_TZ` | `Europe/Berlin` | Fenster und Log-Zeit |
| `WATCH_DATA_DIR` | `/data` | Zustand, Health, HTTP-Cache |
| `WATCH_WEBHOOK_URL` | leer | **Geheim.** ntfy-/Telegram-/Discord-URL |
| `WATCH_WEBHOOK_PRESET` | automatisch | `ntfy`, `telegram`, `discord`, `generisch` |
| `WATCH_OPS_WEBHOOK_URL` | leer | Optionaler, unabhängiger Kanal nur für den Systemalarm; geheim |
| `WATCH_HEARTBEAT_URL` | leer | Optionaler Ping nach jeder Runde, geheim |

`WATCH_MAX_REQ_MIN` zählt echte Abrufe im gleitenden 60-Sekunden-Fenster; ist
es erschöpft, wartet der Wächter kurz, statt heiß zu drehen, und bedient bei
knappem Budget zuerst PS Direct DE/AT. `WATCH_PREIS_TOLERANZ` gilt nur für
neue Preise: Ein Restock meldet immer.

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

Der Zustand enthält pro Shop `initialisiert`, `verfuegbar`, `preis`, `tief`,
`status`, `fail_streak`, `challenge_bis` und den letzten Erfolg. `verfuegbar`
wird nur bei einem bestätigten, sofort kaufbaren, nicht gebrauchten Treffer
`true`; unbestätigte Treffer, Vorbestellungen und Gebrauchtware bleiben
`false`, damit der spätere echte Restock nicht verdeckt wird. Die Datei wird
über eine temporäre Datei plus `os.replace` atomar geschrieben.

### Ausfallsicherung der Live-Alarme

Ein Live-Alarm wird zuerst als Outbox-Eintrag im Zustand gespeichert und erst
dann gesendet. Schlägt die Zustellung fehl, versucht der Wächter es nach
**30 s, 2 min, 10 min, 30 min und 2 h** erneut. Nach **sechs Versuchen** bleibt
der Eintrag als `failed` sichtbar und es wird einmalig ein Systemalarm über den
konfigurierten Webhook versucht. HTTP-4xx (außer 408/425/429) beendet die
Zustellung sofort. Im Schattenmodus entstehen keine Outbox-Einträge.

Ist zusätzlich `WATCH_OPS_WEBHOOK_URL` gesetzt, geht **nur** dieser
Systemalarm an den Ops-Kanal. Ein endgültig fehlgeschlagener Produkt-Webhook
blockiert die Warnung dann nicht; der Produkt-Webhook selbst bleibt
unverändert. Ohne Ops-Kanal nutzt der Systemalarm weiterhin den
Produkt-Webhook. Auch die Ops-URL wird nie geloggt.

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

Die Logs liegen nur auf stdout. Für 48 h vorher mitschneiden (Fly: Log-Drain
oder `fly logs`; Hetzner: `docker compose logs`). Zustand und Health-Datei auf
dem Volume zeigen nur den letzten Stand, nicht die ganze Historie.

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
