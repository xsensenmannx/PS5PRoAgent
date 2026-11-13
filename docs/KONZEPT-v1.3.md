# Konzept v1.3 — Alarmtreue, Verifikation, Schnell-Modus

**Status:** Entwurf. Kein Code, kein Release. Grundlage ist v1.2 (`versionCode 10200`).
**Ziel:** Die drei Lücken schließen, die Nutzer tatsächlich merken — nicht „mehr Features".

## 1. Ziel und Nicht-Ziele

### Ziele

| Nr. | Ziel | Messbar an |
|---|---|---|
| A | Ein Treffer erreicht den Nutzer auch dann, wenn er die App nicht ansieht | Webhook-Zustellung inkl. Fehleranzeige; p95 under 10 s nach Treffer |
| B | Ein Alarm ist verlässlich: „verfügbar" heißt bestätigt | Anteil falscher Alarme sinkt; Verifikationsquote sichtbar |
| C | Beim Öffnen der App ist ein Treffer schneller da | Hot-Shop-Pass under 10 s statt voller 42-Shop-Scan |

### Nicht-Ziele (bewusst, mit Begründung)

* **Captcha lösen, Proxy-Rotation, JS-Challenge-Bypass.** Verstößt gegen Shop-Bedingungen,
  führt zu Sperren und ist ein Wettrüsten ohne Ende. Die App erkennt Bot-Schutz und sagt es —
  das bleibt so.
* **Auto-Checkout / Warenkorb-Bots.** Zahlungs- und Haftungsrisiko, rechtlich unklar.
* **Server-Scraping ohne Einwilligung.** Ein Cloud-Wächter ist ein eigenes Produkt mit
  Hosting, Kosten und Shop-Bedingungen; nicht Teil von v1.3.
* **LLM im Scan-Pfad.** Teuer, langsam, nicht deterministisch. KI bleibt Werkzeug für
  Entwicklung und Auswertung (Abschnitt 7), nicht für jede Preisabfrage.

## 2. Feature A — Webhook-Alarme

### Problem

Benachrichtigungen laufen heute über `plyer` auf dem Gerät
(`main.py: notify`). Ist der Foreground-Service weg (Akku-Optimierung, OEM-Skin,
App vom Nutzer gestoppt), kommt nichts an. Das ist der größte Unterschied zu
Server-Bots.

### Lösung

Ein optionaler HTTP-POST an eine vom Nutzer eingetragene URL, ausgelöst an
denselben Stellen wie die lokale Benachrichtigung. Kein Konto, kein Server der App,
keine Telemetrie — nur die URL, die der Nutzer selbst besitzt.

### Kanäle (Presets, gleiche Mechanik)

| Preset | Endpoint | Payload |
|---|---|---|
| `ntfy` | `https://ntfy.sh/<topic>` | Textzeile + optional `Title`, `Priority`, `Click`-Header |
| `telegram` | `https://api.telegram.org/bot<token>/sendMessage` | `chat_id`, `text`, `disable_web_page_preview` |
| `discord` | Webhook-URL des Kanals | `content` |
| `generisch` | beliebige HTTPS-URL | JSON: `{shop, price, url, kind, ts}` |

Der Token steckt in der URL. Er wird **nicht** geloggt, nicht in Screenshots
angezeigt (Feld als Passwort maskiert) und nicht an Dritte gesendet.

### Verhalten

* Auslöser: identische Regeln wie heute (`alarm_ereignis`): neuer Treffer, Restock,
  Preisgrenze, Ruhezeit, stummgeschaltete Händler.
* Dedupe: pro `(shop, preis, art)` ein Cooldown von 10 Minuten; ein Restock zählt
  als eigene Art.
* Senden: ein Versuch, Timeout 8 s, bei 5xx/Timeout ein Retry nach 3 s.
  Bei 4xx kein Retry (URL/Token falsch → Fehler anzeigen).
* Der Scan wartet **nie** auf den Webhook: Senden in einem Daemon-Thread,
  Ergebnis in den Shop-Health-Eintrag (`webhook_ok`, `webhook_ts`, `webhook_fehler`).
* Testknopf in SETUP sendet eine Beispielnachricht und zeigt HTTP-Status + Fehlertext.

### Datenschutz und Sicherheit

* Nur `https://`, keine `file://`/`http://`-Ausnahmen.
* Payload minimal: Händler, Preis, Shop-URL, Zeitstempel. Keine Geräte-ID, kein Standort.
* Fehlermeldungen werden gekürzt und ohne URL-Query geloggt (Token-Schutz).
* Ein leerer Wert deaktiviert den Kanal vollständig.

### Tests

* Reine Funktion `webhook_nachricht(result, preset)` → Payload/Header (Unit-Tests).
* Lokaler HTTP-Stub (ThreadingHTTPServer) für Erfolg, 500, 403, Timeout.
* Dedupe/Cooldown als reine Funktion.
* Smoke: Testknopf gegen Stub, Einstellung überlebt Neustart.

## 3. Feature B — Treffer-Verifikation

### Problem

Ein Treffer entsteht aus einer einzigen Antwort. Shops liefern sporadisch alte
oder falsche Bestände (Cache, A/B-Tests, „nur im Markt"). Ein falscher Alarm ist
teurer als ein verpasster.

### Lösung

Nach einem Treffer (nicht bei jedem Shop) ein zweiter Abruf mit Cache-Umgehung.

* Zeitpunkt: 2 s nach dem ersten Treffer, nur wenn der Scan noch läuft.
* Request: gleiche URL, Header `Cache-Control: no-cache`, anderer Zeitstempel-Parameter
  nur wenn die URL bereits einen Query hat; sonst unverändert.
* Maximal ein Verify pro Shop und Scan; bei 403/429/Timeout wird nicht wiederholt.
* Ergebnis am Treffer: `verify` ∈ `bestaetigt | geaendert | weg | unbestaetigt`.

### Anzeige

* Karte: kleiner Zusatz `BESTÄTIGT` (cyan) bzw. `EINFACH GEPRÜFT` (grau).
* Detail: „VERIFIKATION: bestätigt (2. Abruf, 12:04:07)".
* Neue Alarm-Option **„Nur bestätigte Treffer melden"** (Standard: aus, damit
  niemand einen echten Treffer verpasst).

### Risiko und Gegenmaßnahmen

Zusätzliche Requests erhöhen die Bot-Schutz-Wahrscheinlichkeit. Deshalb:
nur bei Treffern (selten), Mindestabstand 2 s, kein Retry, Abbruch bei 403/429,
und die Option ist pro Nutzer abschaltbar.

### Tests

* Zustandsmaschine als reine Funktion (`verify_entscheidung(erster, zweiter)`).
* Stub-Szenarien: gleicher Preis, Preis geändert, 404, 403, Timeout.
* Smoke: Karte zeigt Badge, Detailzeile vorhanden.

## 4. Feature C — Schnell-Modus für heiße Shops

### Problem

Der volle Scan über 42 Shops dauert; beim Öffnen der App wartet man auf Shops,
die praktisch nie PS5-Pro-Bestand haben.

### Lösung

Solange die App im Vordergrund ist und kein Scan läuft:

* alle 60 s ein Pass über die **Hot-Shops** (Standard: Amazon DE, MediaMarkt,
  Saturn, Otto, Cyberport, Coolblue — in SETUP editierbar, max. 8),
* danach 5 Minuten Pause, dann wieder; der reguläre Intervall-Scan bleibt unverändert,
* HUD zeigt `SCHNELLSCAN · 6 SHOPS` und den nächsten Lauf,
* nur bei WLAN (Einstellung, Standard an) und nie parallel zu einem vollen Scan,
* Backoff: nach 403/429 für diesen Shop 10 Minuten aussetzen.

### Tests

* Scheduler als reine Funktion (nächster Lauf, Backoff, keine Überlappung).
* Smoke bei 620×380 und 884×700: HUD-Text, kein Doppel-Scan.

## 5. Querschnitt

* **Einstellungen:** neue Schlüssel `webhook_url`, `webhook_preset`,
  `alarm_nur_bestaetigt`, `schnellscan`, `schnellscan_shops`,
  `schnellscan_wlan` — Migration ohne Reset bestehender Werte.
* **Shop-Health:** Webhook- und Verify-Fehler getrennt zählen, nicht als Parserfehler.
* **Logs:** niemals vollständige Webhook-URL; `redact_url()` mit Test.
* **Screenshots:** SETUP mit maskiertem Feld, Karte mit Badge; keine Token in Bildern.
* **CI:** neue Unit-Tests in `tools/selftest.py`, Smoke-Fälle, bestehende sieben Jobs bleiben.

## 6. Aufwand und Risiko

| Teil | Aufwand | Risiko | Gegenmaßnahme |
|---|---|---|---|
| A Webhooks | 1,5–2 Tage | Token-Leak in Logs | Redaction + Test |
| B Verifikation | 1 Tag | mehr Bot-Schutz | nur Treffer, Backoff, abschaltbar |
| C Schnell-Modus | 0,5–1 Tag | Akku/Daten | WLAN-Standard, 60-s-Takt, Pause |
| Tests/Doku/Release | 1 Tag | — | bestehende Gates |

## 7. KI-Roadmap (nicht v1.3)

1. **CI-Regelvorschlag (sinnvoll):** Wenn eine Fixture bricht, schlägt ein LLM
   neue Selektoren vor; ein Mensch prüft, Tests entscheiden. Ausgeliefert wird
   weiterhin nur deklaratives JSON — kein Laufzeit-LLM.
2. **Kauf-Signal (sinnvoll):** „kaufen oder warten" aus Preisverlauf,
   30-Tage-Tief und Verfügbarkeitshäufigkeit — Statistik, erklärbar, offline.
3. **Natürlichsprachige Filter (optional):** „unter 700, nur Amazon, nur neu"
   → wird auf die vorhandenen Einstellungen abgebildet.
4. **Nicht empfohlen:** ein Agent, der Produktionscode ändert oder Captchas löst.
   Die sichere Evolutionsschleife bleibt Remote-Config + Tests + CI.

## 8. Abnahmekriterien für v1.3

* Ein Treffer erzeugt innerhalb von 10 s einen Webhook; ein 500er wird sichtbar
  als Fehler im Health-Eintrag, ohne den Scan zu blockieren.
* Ein bestätigter Treffer zeigt `BESTÄTIGT`; ein 403 beim Verify erzeugt keinen
  zweiten Versuch und keinen falschen Alarm.
* Bei geöffneter App läuft der Hot-Shop-Pass, ohne den vollen Scan zu überlappen.
* 699+ Logiktests, Smoke in fünf Größen, Release über Tag `v1.3` mit denselben
  Gates wie v1.2.
