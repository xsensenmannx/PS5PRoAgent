# Cloud-Wächter — Entwurf für sechs bis acht Shops

**Stand:** 21.11.2026 · **Status:** P0 umgesetzt in `cloud_watcher/` (Schattenbetrieb)
**Baut auf:** `docs/KONZEPT.md` §5/§6 (v1.6) und `docs/RELEASE_1_5.md` §2

> **Umsetzung (21.11.2026):** Der P0-Wächter liegt in `cloud_watcher/` und
> startet mit zwei Shops (PS Direct DE/AT), 45 s im Fenster und 48 h
> Schattenbetrieb. Dazu sind Alarm-Outbox mit optionalem Ops-Kanal, Preflight,
> Tageszusammenfassung, Preistoleranz sowie Challenge- und Request-Budget
> umgesetzt. Der Sechs-Shop-Ausbau bleibt P1; die Grenzen in diesem Dokument
> gelten weiter.

Dieses Dokument entscheidet, *was* gebaut würde, *was* es kostet und *wo* die
Grenzen liegen. Es enthält keinen Code, kein Deployment und keine Änderung an
der App.

---

## 1. Ziel und Abgrenzung

**Ziel:** Ein kleiner, dauerhaft laufender Prozess prüft sechs bis acht Shops
auch dann, wenn das Handy ausgeschaltet ist, und schickt bei einem bestätigten
Treffer eine Meldung über den vorhandenen Webhook-Weg.

**Nicht Ziel:** ein zweites Produkt, ein Konto, ein zentraler Dienst für alle
Nutzer, Sekunden-Push, Kaufautomatik oder eine Umgehung von Bot-Schutz.

**Erfolg wird an vier Zahlen gemessen:**

| Größe | Zielwert |
|---|---|
| Alarm bei geschlossener App | kommt an, p95 < 90 s nach dem Abruf, der den Treffer sieht |
| Falschalarme | < 2 % der gemeldeten Treffer (zweiter Abruf bestätigt) |
| Betriebskosten | ≤ 5 €/Monat, ohne Überraschungen durch Traffic |
| Aufwand bis zum Schattenbetrieb | 3–4 Personentage |

**Wichtige Ehrlichkeit:** „24/7" heißt hier *dauerhaft abfragen*, nicht
*sofort wissen*. Kein Shop bietet einen Push-Kanal; der Shop-Cache und die
Abfragefrequenz setzen die Untergrenze. Ein 30–60-Sekunden-Takt erkennt ein
Ein-Minuten-Fenster praktisch immer, ein 15-Sekunden-Fenster nur zu etwa
25–50 %.

---

## 2. Empfehlung in einem Satz

> Eine dauerhaft laufende **Fly.io-Machine** (`shared-cpu-1x`, 512 MB,
> Frankfurt) führt den **unveränderten `scan_core`** aus, prüft **sechs Shops**
> im Takt von 30–120 s, hält den Zustand in einer kleinen JSON-Datei und
> meldet über **ntfy oder Telegram** mit der bereits vorhandenen
> `webhook_nachricht`-Logik: **3–4 Personentage, ca. 4–5 $/Monat, keine
> App-Änderung.**

Warum nicht zuerst Cloudflare Worker: Der Free-Tarif erlaubt **10 ms CPU pro
Aufruf** — für das Parsen von 1–2,5 MB HTML unmöglich. Der Paid-Tarif kostet
mindestens **5 $/Monat** und verlangt trotzdem einen TypeScript-Port der
Parser. Damit gäbe es zwei Wahrheiten für dieselbe Shop-Seite. Der Worker ist
eine spätere Option (P2), nicht der Anfang.

---

## 3. Shop-Auswahl

### 3.1 Startseite (sechs Shops)

| Shop | Land | Takt | Warum | Stand vor Aufnahme |
|---|---|---|---|---|
| PS Direct DE | DE | 30 s in 09:00–18:00, sonst 180 s | Sony-Drops, in der App bereits 10-s-Fenster | URL geprüft 20.11.2026: 200 ohne Redirect, Canonical = Ziel; alte direct-URL → 301 |
| Amazon DE | DE | 90 s | größter Marktplatz, Parser belegt | 2,4 MB, Kaufbox-Pfad, Messung 17.11.2026 |
| MediaMarkt DE | DE | 60 s | Schübe, hohe Nachfrage | Parser vorhanden, Aufnahme-Gate offen |
| Saturn DE | DE | 60 s | gleiche Plattform wie MediaMarkt | Aufnahme-Gate offen |
| Alternate DE | DE | 120 s | Fachhändler, strukturierte Daten erwartet | Aufnahme-Gate offen |
| Amazon AT | AT | 120 s | AT-Abdeckung ohne zweiten Parser | Produktseite belegt, 17.11.2026 |

**P1, nach dem Schattenbetrieb:** PS Direct AT (30 s im Fenster) und
MediaMarkt AT (120 s). Damit sind es acht Shops.

### 3.2 Bewusst nicht in der Startseite

| Shop | Grund |
|---|---|
| Otto DE | Kasada, HTTP 400 auf jedem Produktpfad (17.11.2026). Ein Slot wäre dauerhaft verbrannt. |
| Cyberport DE/AT | Cloudflare, HTTP 403 inklusive `robots.txt` (17.11.2026). |
| e-tec AT | Parser funktioniert, aber 1.699 € liegen über dem Deckel von 900 €. Der Shop würde nie einen Alarm auslösen, nur `expensive` liefern. |
| Euronics, Expert, Müller, Kaufland, GameStop, Notebooksbilliger, Conrad, Proshop, Computeruniverse, Galaxus, Alza, Spielekauf, Geizhals, Libro, Hartlauer, Electronic4you, Quelle, Universal, Gameware, shöpping, Computerexpert, Aetka | Suchseiten ohne exakte SKU oder ohne belegten Produktpfad. Im Cloud-Wächter zählt jede Fehlmessung als Alarmrisiko; sie kommen erst mit exakter Produkt-URL und Fixture dazu. |

**Aufnahme-Gate (vor dem ersten Alarm):** Drei Abrufe im Abstand von fünf
Minuten müssen Produkt, Preis und Verfügbarkeitszustand liefern, ohne
Challenge. Ein Shop, der das nicht besteht, bleibt draußen — unabhängig davon,
wie wichtig er wäre.

**Preisdeckel:** Der Wächter übernimmt den Deckel aus den Einstellungen
(Standard 900 €, AT erbt). `scan_einen` klassifiziert zunächst mit
`MAX_PREIS`; der Wächter zieht die Klassifikation danach mit
`preis_deckel()` nach, genau wie `scan_alle` es tut. Sonst wäre ein AT-Treffer
über 900 € ein Alarm, obwohl die App ihn als `expensive` zeigt.

---

## 4. Architektur

```
┌─────────────────────────────────────────────────────────────┐
│ Fly.io Machine (always on, Frankfurt, 512 MB, 1 vCPU shared)│
│                                                             │
│  Loop (Weckruf alle 15 s)                                   │
│    │                                                        │
│    ├─ Scheduler: fällige Shops, Jitter, Budget 12/min       │
│    │     └─ ThreadPoolExecutor(max_workers=2)               │
│    │           └─ scan_core.scan_einen()   ← unverändert    │
│    │                 ├─ fetch_mit_cache (ETag/304, 20 s)    │
│    │                 ├─ Parser (JSON-LD → Amazon → Meta)   │
│    │                 └─ classify + Konfidenz                │
│    │                                                        │
│    ├─ Treffer? → verify_treffer() (zweiter Abruf, 2 s)      │
│    │                                                        │
│    ├─ Zustand: /data/watch_state.json (atomar)              │
│    ├─ Alarm: sende_webhook_alarm() → ntfy/Telegram          │
│    ├─ Health: /data/health.json + Tageszusammenfassung      │
│    └─ Log: JSON-Zeilen nach stdout (Fly-Logs)               │
│                                                             │
│  Kein offener Port. Kein HTTP-Server. Kein Token in P0.     │
└─────────────────────────────────────────────────────────────┘
```

### 4.1 Was unverändert wiederverwendet wird

| Baustein | Funktion | Warum wichtig |
|---|---|---|
| Abruf und Parser | `scan_core.scan_einen()` | Dieselbe Erkennung wie App und Hintergrunddienst; keine zweite Parser-Wahrheit. |
| Verifikation | `verify_treffer(h, r, pause=2.0)` | Ein Alarm muss stimmen; der zweite Abruf bleibt Pflicht. |
| Alarmentscheidung | `alarm_ereignis()` plus `ist_sofort_treffer()` im Wächter | Restock/Neupreis, bestätigter Sofortkauf, Neuware; `alarm_erlaubt()` bleibt die App-Regel. |
| Nachricht | `webhook_nachricht()` | ntfy, Telegram, Discord und generisch bleiben identisch zur App. |
| Zustellung | `sende_webhook_alarm()` | Enthält Dedupe, Retry und die Statusdatei. |
| Maskierung | `redact_url()` | Webhook-Tokens erscheinen nie im Log. |
| Drop-Fenster | `im_drop_fenster(name, jetzt)` | Die belegten PS-Direct-Zeiten stehen schon im Code. |
| Health | `health().record(r)` und `health_uebersicht()` | Fehlerserie für den Breaker, Erfolgsquote, Alter je Shop. |
| Cache sichern | `flush_http_cache()` nach jeder Runde | Ohne den Flush überlebt der ETag/304-Cache den Prozess nicht — jede Runde würde neu laden. |
| Datenverzeichnis | `set_data_dir("/data")` | Cache, Dedupe und Status landen auf dem Volume. |

### 4.2 Was der Wächter bewusst selbst macht

| Baustein | Grund |
|---|---|
| Taktprofil | `shop_intervall()` ist auf Akku und Vordergrund ausgelegt (30 s heiß, 4 min normal). Der Wächter hat keinen Akku, aber ein kleineres Budget und andere Shops. Er bringt eine eigene Tabelle mit. |
| Scheduler | `faellige_haendler()` sortiert richtig, ist aber an `LIVE_*`-Konstanten gebunden. Der Wächter braucht zusätzlich Schattenmodus, Budgetanzeige und ein anderes Rundenziel. Rund 60 Zeilen, kein Eingriff in die App. |
| Zustand | `History` und `Events` sind App-Dateien mit eigener Semantik. Der Wächter braucht nur: letzter Zustand, letzter Preis, Fehlerserie, letzte Prüfung. Eine kleine JSON-Datei reicht; keine Datenbank, keine Migration. |
| Health-Verlauf | `health_uebersicht()` liefert die Kennzahlen, aber keinen 30-Tage-Verlauf. Der Wächter schreibt zusätzlich NDJSON-Zeilen (14 Tage, rotierend). |

### 4.3 Konfiguration (Environment, keine Datei im Repository)

| Variable | Bedeutung | Beispiel |
|---|---|---|
| `WATCH_WEBHOOK_URL` | Ziel für Alarme; **Secret** | `https://ntfy.sh/<langer-zufallstopic>` |
| `WATCH_WEBHOOK_PRESET` | optional; sonst aus URL erkannt | `ntfy` |
| `WATCH_SHOPS` | kommagetrennte Namen aus `HAENDLER` | `Amazon DE,MediaMarkt DE,…` |
| `WATCH_SHADOW` | `1` = nur protokollieren, nicht senden | `1` beim Schattenlauf |
| `WATCH_DATA_DIR` | Volume-Pfad | `/data` |
| `WATCH_TZ` | Zeitzone fürs Drop-Fenster | `Europe/Berlin` |
| `WATCH_MAX_REQ_MIN` | globales Budget | `12` |
| `WATCH_HEARTBEAT_URL` | optionaler Dead-Man-Ping | `https://hc-ping.com/<uuid>` |

Der Webhook-URL wird **nie** geloggt, nur über `redact_url()` als
`https://ntfy.sh/…` ausgegeben.

---

## 5. Takt, Budget und Mengen

### 5.1 Taktprofil

| Zustand | Takt |
|---|---|
| PS Direct im belegten Fenster 09:00–18:00 | 30 s |
| Treffer in den letzten 60 Minuten gesehen | 60 s |
| normal | 60–180 s je Shop (Tabelle oben); 60 s für MediaMarkt/Saturn, 90–180 s für die übrigen |
| zwei Parserfehler in Folge | 12 min |
| Challenge, 403, 429 | 15 min Circuit Breaker, danach halbe Frequenz |
| drei Challenges in Folge | 60 min, eine Infozeile pro Tag |

Dazu: Jitter ±15 % pro Shop (stabil über `crc32`, nicht `hash`), maximal zwei
gleichzeitige Abrufe, keine Überlappung von Runden.

### 5.2 Requests pro Tag (sechs Shops)

| Shop | Takt | Requests/Tag |
|---|---|---|
| PS Direct DE | 30 s (9 h) + 180 s (15 h) | 1.080 + 300 = **1.380** |
| Amazon DE | 90 s | **960** |
| MediaMarkt DE | 60 s | **1.440** |
| Saturn DE | 60 s | **1.440** |
| Alternate DE | 120 s | **720** |
| Amazon AT | 120 s | **720** |
| **Summe** | | **6.660/Tag ≈ 200.000/Monat** |

Mit acht Shops kommen PS Direct AT (1.380) und MediaMarkt AT (720) dazu:
**8.760/Tag ≈ 263.000/Monat**. Das Spitzenfenster liegt bei etwa 5–7
Requests/Minute und damit unter dem Deckel von 12.

### 5.3 Traffic und Rechenlast

Annahme: 1,5 MB pro HTML-Antwort im Mittel (Amazon 2,4 MB, PS Direct und
Alternate deutlich kleiner).

| Größe | sechs Shops | acht Shops |
|---|---|---|
| Traffic pro Tag | ca. 10 GB | ca. 13 GB |
| Traffic pro Monat | ca. 300 GB | ca. 394 GB |
| CPU pro Tag (0,4 s je Parse) | ca. 44 min | ca. 58 min |
| Spitzenspeicher | < 200 MB | < 200 MB |

Das ist auf einer 512-MB-Machine machbar, aber unschön: 300–400 GB pro Monat
für sechs Produktseiten sind der eigentliche Grund, den JSON-Pfad (P1) früh
nachzuziehen. Ein ETag/304 reduziert die Last, wenn der Shop ihn liefert; bei
Amazon ist das nicht garantiert.

**Konsequenz für die Reihenfolge:** sechs Shops starten, acht erst, wenn der
JSON-Pfad für die zwei schwersten Shops belegt ist — oder wenn der
Schattenlauf zeigt, dass Traffic und Laufzeit im Rahmen bleiben.

---

## 6. Alarmweg

1. **Nur Zustandswechsel melden.** Ein Shop, der verfügbar bleibt, erzeugt
   keinen zweiten Alarm. Maßgeblich ist der Übergang von „nicht verfügbar“ zu
   „verfügbar“ (`restock`) oder ein neuer, niedrigerer Preis (`new`).
2. **Verifikation vor dem Senden.** `verify_treffer()` ruft die Seite ohne
   Cache erneut ab. Ergebnis `weg` oder `unbestaetigt` → kein Alarm, nur ein
   Log-Eintrag. Das kostet 2 Sekunden und ist der wichtigste Falschalarm-Filter.
3. **Dedupe.** `sende_webhook_alarm()` nutzt `webhook_dedupe()`: gleicher Shop,
   gleicher Preis, gleiche Art innerhalb von 10 Minuten → schweigen.
4. **Zustellung.** Ein Versuch, ein Retry nach 10 s (in `webhook_senden`
   enthalten). Schlägt es fehl, bleibt der Treffer als „offen“ markiert und
   wird in der nächsten Runde erneut versucht. At-least-once, nie ein
   Retry-Sturm.
5. **Text.** Identisch zur App:
   `PS5 Pro 2 TB: 799,00 €` / `Amazon DE - jetzt verfügbar` plus URL.
6. **Kanal.** Empfehlung ntfy: kostenlos, kein Konto, kein Bot-Token. Der
   Topic-Name muss lang und zufällig sein, weil öffentliche ntfy-Topics
   mitlesbar sind. Telegram ist die Alternative, wenn ein Bot ohnehin existiert.
7. **Ruhezeiten.** Standardmäßig **aus** — der Zweck ist der Alarm um 3 Uhr.
   Wer sie will, bekommt sie als Option.
8. **Doppelte Alarme.** App und Wächter haben getrennte Dedupe-Dateien. Läuft
   beides, kann derselbe Treffer zweimal ankommen. Für P0 ist das akzeptiert
   („lieber zweimal als nie“); die saubere Lösung ist ein gemeinsamer
   Dedupe-Schlüssel über einen kleinen Endpunkt — das ist App-Kopplung und
   gehört zu P2.

---

## 7. Aufwand

### P0 — Schattenbetrieb (3–4 Personentage)

| Paket | Inhalt | Tage |
|---|---|---|
| Aufnahme-Gate | sechs Shops dreimal prüfen, Fixtures gegen die echten Seiten abgleichen, PS-Direct-URL klären | 0,5 |
| Loop und Scheduler | Weckruf, Fälligkeit, Jitter, Budget, zwei Worker, sauberes Beenden | 1,0 |
| Zustand und Breaker | `watch_state.json`, Fehlerserien, Circuit Breaker, Restart-Festigkeit | 0,5 |
| Alarmweg | Wiederverwendung von `sende_webhook_alarm`, Shadow-Modus, Redaction, Statusdatei | 0,5 |
| Verpackung | Dockerfile, `fly.toml` mit `auto_stop_machines = false`, Volume, Secrets, Runbook | 0,5 |
| Nachweis | Offline-Tests mit vorhandenen Fixtures, 48-h-Schattenlauf, Auswertung | 0,5 |

**P0 enthält ausdrücklich keine App-Änderung.** Der Wächter ist ein
outbound-only Prozess; niemand muss ein Token in der App hinterlegen.

### P1 — Qualität und acht Shops (2–3 Personentage)

| Paket | Inhalt | Tage |
|---|---|---|
| JSON-Pfad | Für die zwei schwersten Shops den kleineren Endpoint belegen und deklarativ einbinden; HTML-Fallback bleibt | 1,0 |
| Health und Dead-Man | Tageszusammenfassung, Heartbeat-Ping, Alarm bei drei ausgefallenen Runden | 0,5 |
| Acht Shops | PS Direct AT, MediaMarkt AT, Takt nachmessen, Budget prüfen | 0,5 |
| Feinschliff | Logrotation, Aufbewahrungsfristen, Runbook ergänzen | 0,5 |

### P2 — Komfort und Alternativen (6–9 Personentage)

| Paket | Inhalt | Tage |
|---|---|---|
| App-Kopplung | `watcher_url` + Einmal-Token, Heartbeat im HUD, Kill-Switch, QR-Code | 2–3 |
| Cloudflare-Worker-Port | Parser in TypeScript, Paritätstests gegen dieselben Fixtures, D1/KV | 6–9 |
| Zweite Region | Ausfallübernahme, doppelte Kosten | 1–2 |

**Reihenfolge:** P0 → Schattenlauf → P1 → entscheiden, ob P2 überhaupt nötig
ist. Die App-Kopplung ist Komfort, nicht Voraussetzung: Der Alarm kommt auch
ohne sie an.

---

## 8. Kosten

Preise Stand November 2026, netto bzw. ohne Steuer, sofern nicht anders
angegeben. Wechselkurse schwanken.

| Variante | Fixkosten/Monat | Aufwand | 24/7 | `scan_core` wiederverwendet | Betrieb |
|---|---|---|---|---|---|
| **Fly.io `shared-cpu-1x` 512 MB, Frankfurt** | **ca. 4,26 $ + 0,15 $ Volume ≈ 4,40 $** | 3–4 Tage | ja | vollständig | gering |
| Hetzner CX23 (2 vCPU, 4 GB) | 5,49 € + 0,50 € IPv4 ≈ 5,99 € netto | 3–4 Tage | ja | vollständig | mittel (systemd, Patches) |
| Cloudflare Worker, Paid | 5 $ Minimum | 6–9 Tage | ja | nein (TS-Port) | sehr gering |
| Cloudflare Worker, Free | 0 $ | 6–9 Tage | **nein für dieses Parsing** (10 ms CPU) | nein | — |
| GitHub Actions Cron | 0 $ | 1–2 Tage | **nein für 24/7-SLA** (5-Minuten-Boden, verspätete und ausgelassene Läufe) | vollständig | sehr gering |

**Laufende Zusatzkosten:** ntfy 0 €, Telegram 0 €, TLS über die Plattform 0 €,
Traffic bei Fly eingehend frei, Volume 1 GB 0,15 $/Monat. Ein optionaler
Dead-Man-Dienst (z. B. healthchecks.io) ist im kostenlosen Kontingent
ausreichend.

**Realistische Gesamtkosten: 4–5 €/Monat**, mit Hetzner als Alternative
**6–7 €/Monat** netto. Es gibt kein Traffic-Risiko, weil das
Minutenbudget gedeckelt ist und die Shop-Liste fest ist.

**Was die Kosten treibt:** nicht die Requests, sondern die HTML-Größe. Der
JSON-Pfad (P1) senkt 300–400 GB/Monat auf wenige GB und macht acht Shops
erst wirtschaftlich unspektakulär.

---

## 9. Grenzen

| Grenze | Wirkung | Umgang |
|---|---|---|
| **Kein Push vom Shop** | „Live“ ist Polling; kein Kanal, kein Feed, keine WebSocket-Zusage | 30–120 s Takt, ehrliche Kommunikation |
| **Shop-CDN cached** | Ein Restock ist erst sichtbar, wenn der Cache ihn ausliefert — oft 30–120 s | kleineren/ungecachten Endpoint nutzen (P1), nicht schneller raten |
| **Kurze Fenster** | 1-Minuten-Fenster bei 30–60 s fast immer, 15-Sekunden-Fenster zu 25–50 % | PS Direct im Fenster 30 s; keine Sekunden-Versprechen |
| **Rechenzentrums-IP** | Otto und Cyberport sind bereits dauerhaft gesperrt; Cloudflare-Shops können 403 liefern | Challenge erkennen, Breaker, kein Umweg; Handy bleibt Fallback |
| **Eine Machine** | Kein HA; Neustart, Plattformwartung oder Absturz unterbrechen die Überwachung | Zustand auf Volume, Dead-Man-Ping, Neustart automatisch |
| **Sechs bis acht Shops** | Mehr Shops bei gleichem Budget heißt längere Runden oder mehr Sperren | Obergrenze bewusst; Erweiterung nur mit JSON-Pfad und Messung |
| **Kein lokaler Marktbestand** | „Nur im Markt“-Verfügbarkeit (MediaMarkt) sieht der Wächter nicht | Das bleibt die Lücke zu Bestell.bar; nicht als Feature versprechen |
| **HTML-Markup ändert sich** | Parserfehler, keine Treffer | Health-Serie, Fixtures, kein Alarm bei `parser` |
| **Webhook-Abhängigkeit** | ntfy/Telegram down → kein Alarm | Retry, offene Treffer, optional zweiter Kanal |
| **Öffentliche ntfy-Topics** | Topic-Name ist der einzige Schutz | langer Zufallswert, kein sprechender Name, Rotation möglich |
| **Doppelte Alarme** | App und Wächter melden denselben Treffer | P0 akzeptiert; P2 gemeinsamer Dedupe-Schlüssel |
| **Recht und ToS** | Öffentliche Preise, faire Frequenz, kein Kauf, keine Umgehung | dokumentiert; keine Rechtsberatung, keine Garantie |

**Die wichtigste Grenze in einem Satz:** Der Wächter schließt die Lücke
„Handy aus“, nicht die Lücke „Shop liefert sofort“. Er ist eine Verstärkung
der App, kein Ersatz für einen Shop mit Push-Kanal.

---

## 10. Betrieb und Ausfallsicherheit

**Start:** `WATCH_SHADOW=1` für 48 Stunden. Es wird geprüft, protokolliert und
nichts gesendet. Erst danach scharf schalten.

**Log:** eine JSON-Zeile pro Prüfung mit `ts`, `shop`, `ms`, `bytes`,
`klass`, `http`, `verify`, `alert`. Dazu eine Tageszeile mit Quote, p50/p95,
Challenge-Zahl und offenen Zustellungen. Aufbewahrung: 14 Tage NDJSON,
danach rotieren.

**Health:** `/data/health.json` mit denselben Kennzahlen wie
`health_uebersicht()`. Zusätzlich ein Heartbeat-Ping nach jeder vollständigen
Runde. Bleibt er drei Runden aus, schlägt der externe Dienst Alarm — der
Wächter kann seinen eigenen Ausfall nicht melden.

**Runbook (Kurzfassung):**

| Symptom | Erste Prüfung | Maßnahme |
|---|---|---|
| keine Prüfungen mehr | Prozess, Volume, letzte Logzeile | Machine neu starten; Volume prüfen |
| ein Shop nur `challenge` | HTTP-Code, Body-Anfang | Breaker greift; Shop bleibt gelistet, kein Retry |
| viele `parser` | Seitenstruktur, Fixture | Shop pausieren, Parser separat reparieren |
| Alarme kommen nicht an | `webhook_status_lesen()`, Token | URL/Secret prüfen, Testalarm senden |
| Kosten steigen | Traffic pro Check | JSON-Pfad vorziehen, Takt senken |

**Update:** Image neu bauen, `fly deploy`. Kein Datenbankschema, keine
Migration. **Kill-Switch:** `fly scale count 0` oder das Webhook-Secret
entfernen; beides stoppt Alarme sofort.

**Backup:** wöchentlicher Snapshot des 1-GB-Volumes ist optional; der Zustand
ist nach einem Verlust in wenigen Minuten neu aufgebaut (erster Lauf setzt
alles auf „unbekannt“, es gibt höchstens einen verpassten Alarm).

---

## 11. Sicherheit und Datensparsamkeit

* **Outbound only.** Kein offener Port, kein HTTP-Endpunkt, kein Token in P0.
  Damit gibt es keine Angriffsfläche für fremde Aufrufe.
* **Secrets** nur über Fly-Secrets. Der Webhook-URL erscheint nie in Logs,
  Fehlermeldungen oder im Repository; `redact_url()` maskiert ihn.
* **Container** als Nicht-root, Root-Dateisystem schreibgeschützt, nur
  `/data` beschreibbar. Abhängigkeiten: Standardbibliothek plus `requests`
  (bereits im Projekt), feste Version.
* **Datenminimierung:** gespeichert werden Shopname, Preis, Zustand,
  Zeitstempel und ein Beleg-Hash. Keine IP-Adressen, keine Nutzerkennungen,
  keine Standortdaten, keine Telemetrie.
* **Aufbewahrung:** Prüfungen 30 Tage, Alarme 90 Tage, Logs 14 Tage. Danach
  löschen, nicht archivieren.
* **Kein Kauf, kein Warenkorb, kein Captcha, keine Proxy-Rotation.** Der
  Wächter liest dieselben öffentlichen Seiten wie die App, mit demselben
  User-Agent und derselben fairen Frequenz.

---

## 12. Abnahme vor dem Bau

Der Entwurf gilt als umsetzungsreif, wenn diese Punkte belegt sind:

1. **Aufnahme:** sechs Shops liefern an drei aufeinanderfolgenden Abrufen
   Produkt, Preis und Zustand; kein Shop ist dauerhaft `challenge`.
2. **Schattenlauf:** 48 Stunden ohne Push; Erfolgsquote ≥ 95 % je Shop, keine
   unbehandelte Ausnahme, p95 Prüfdauer < 5 s, p95 Runde < 30 s.
3. **Alarm bei geschlossener App:** mit einer lokalen Testseite/Fixture, nicht
   mit einem echten Shop: App beendet, Wächter erkennt den Wechsel und sendet
   in < 90 s. (Ein echter Restock lässt sich nicht terminieren.)
4. **Falschalarm-Bremse:** ein simulierter Ausverkauf zwischen erstem und
   zweitem Abruf führt zu „unbestaetigt“ und **keinem** Alarm.
5. **Sperre:** ein simulierter 403 löst den Breaker aus; in den folgenden
   15 Minuten kein weiterer Abruf dieses Shops.
6. **Zustellung:** Webhook aus → Retry, Treffer bleibt offen, kein
   Doppelalarm nach Wiederkehr.
7. **Kosten:** Hochrechnung aus dem Schattenlauf < 5 €/Monat.
8. **Geheimnisse:** `grep` über Logs und Image findet keinen Webhook-Token.

Erst danach beginnt die Umsetzung. Dieses Dokument selbst ändert keinen Code.

---

## 13. Offene Entscheidungen

1. **Hosting:** Fly.io (Empfehlung: geringster Aufwand, volle
   Codewiederverwendung) gegen Hetzner (mehr Leistung, mehr Betrieb) gegen
   Cloudflare Worker (null Betrieb, aber Port und zwei Parser-Wahrheiten).
2. **Kanal:** ntfy (Empfehlung: kostenlos, kein Konto) gegen Telegram
   (gewohnter, aber Bot-Token nötig).
3. **Startgröße:** sechs Shops (Empfehlung) gegen acht ab Tag eins. Acht erst
   nach JSON-Pfad oder belastbarer Traffic-Messung.
4. **Doppelte Alarme:** akzeptieren (Empfehlung für P0) oder App-Kopplung
   vorziehen.
5. **App-Anbindung:** jetzt (QR, Token, HUD) oder später. Empfehlung: später;
   der Alarmweg funktioniert ohne sie.

---

## 14. Bewusst nicht in diesem Schritt

* Kein Code, kein Container, kein Deployment, keine Änderung an `scan_core`,
  `main.py`, `service.py` oder der APK.
* Keine neuen Shops, keine Änderung der 42er-Liste.
* Kein Cloudflare-Worker, keine Datenbank, kein Dashboard.
* Keine Proxy-Rotation, kein Captcha-Solver, keine Warenkorb-Probe.
* Keine lokalen Marktbestände und keine Kaufautomatik.
* Keine Rechtsberatung und keine Zusage, dass einzelne Shops das Polling
  dauerhaft erlauben.
