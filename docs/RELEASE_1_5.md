# Release 1.5 — Live-Überwachung und Händler-Erkennung

**Stand:** Plan, noch nicht umgesetzt. Ausgangspunkt ist v1.4.0 (`versionCode 10400`).
**Ziel:** v1.5.1 (`versionCode 10501`) erkennt Restocks früh und findet neue Händler mit
einem nachvollziehbaren Verfahren — ohne Bot-Schutz zu umgehen, ohne Backend und ohne
die Host-Allowlist der Remote-Konfiguration aufzuweichen.

**Stand der Umsetzung (main):** Etappe 0, 1 und 3 vollständig. Etappe 3 umfasst den
Live-Takt mit 20-s-Runde und Rundendeckel 12, das **Drop-Fenster** (10-s-Takt, HUD
`FENSTER`), die **Sofortmeldung** für belegte Treffer sowie den **Event-Ticker** mit
Fensterdauer und „zuletzt verfügbar am" je Shop. Offen: Etappe 2 (JSON-Datenpfad),
Etappe 4/5 (Discovery, Aufnahme, Marketplace-Zeile) und Etappe 6 (optional). Etappe 7
läuft: Tag `v1.5.1`, die CI baut die signierte APK.

---

## 1. Ausgangslage im Code

Was heute existiert und worauf der Plan aufsetzt:

| Baustein | Ort | Stand |
|---|---|---|
| Händlerliste | `scan_core.HAENDLER` (42 Einträge), `HAENDLER_BASIS` als unveränderliche Basis | hart im Code, Änderung nur per Release |
| Remote-Konfiguration | `shop_config.json` (Schema 1), `validiere_shop_config()` | nur URLs und Parser-Regeln **bekannter** Hosts |
| Scan | `scan_alle()` mit `ThreadPoolExecutor(WORKER=6)` | alle Shops in einer Runde, kein Budget |
| Live-Modus | `faellige_haendler()`, `shop_intervall()` in `scan_core`, `_fast_tick()` in `main.py` | umgesetzt in v1.5: 20 s, fällige statt fester Shops, Vordergrund |
| Hintergrund | `bg_intervall()` in `service.py` | hart auf mindestens 900 s (15 min) |
| Health / Cache | `ps5pro_health.json`, `HttpCache` mit ETag/304, `CACHE_MAX_ALTER` 6 h | vorhanden, aber nicht zur Taktung genutzt |
| Fixtures | `tools/fixtures/` (47 Dateien), `tools/capture_fixture.py` | je Shop eine Fixture, aufnehmen per Kommando |

Drei Dinge fehlen für 1.5:

1. **Kein Scheduler.** Alles läuft in festen Runden. Ein Shop, der gerade verfügbar
   ist, wird genauso oft geprüft wie einer, der seit drei Wochen ausverkauft ist.
2. **Kein schneller Datenpfad.** Jede Prüfung zieht die komplette HTML-Seite (bis 5 MB)
   und parst sie, obwohl der Shop den Bestand in einer kleinen JSON-Antwort liefert.
   Das ist die eigentliche Latenzquelle — nicht der Takt.
3. **Kein Verfahren für neue Händler.** Ein neuer Shop bedeutet heute: Code-Zeile
   von Hand, Fixture von Hand, Release. Das skaliert nicht über 42 hinaus.

---

## 2. Was „Live" hier heißt — und was nicht

**Ehrliche Grenze:** Kein Shop in der Liste bietet einen Push-Kanal, ein Restock-Feed
oder eine WebSocket-Schnittstelle, die dokumentiert wäre. „Live" kann deshalb nur heißen:
**die aktuellere, kleinere Quelle häufiger und gezielter abfragen** — nicht Sekunden-Push
aus dem Nichts.

| Betrieb | Takt | Warum |
|---|---|---|
| Vordergrund, heiße Shops | 10–30 s | Shops mit Trefferhistorie; kurze Runde, weil JSON statt HTML |
| Vordergrund, normale Shops | 2–5 min | Rest der Liste, rotierend |
| Vordergrund, gestörte Shops | 10–15 min | Parserfehler, Bot-Schutz, Rate-Limit |
| Hintergrunddienst | 15 min (unverändert) | Android-Grenze, Akku, Datenvolumen |

Damit bleibt das Versprechen aus dem Konzept („p95 Alarm lokal < 60 s") erreichbar,
ohne dass die Request-Zahl explodiert: die Priorisierung verschiebt Last von kalten
zu heißen Shops, sie erhöht sie nicht global.

**Pflicht-Bremse:** Ein globales Budget (Requests/Minute) ist Teil von Etappe 1, nicht
eine spätere Optimierung. Ohne Deckel ist „live" nur ein schnellerer Weg zur 403.

### Wie die „sofort"-Scraper das machen — und was davon hierher passt

Die Scraper, die einen Restock scheinbar in Sekunden melden, nutzen fast immer einen
dieser Wege:

| Mechanismus | Wie es funktioniert | Für diese App |
|---|---|---|
| **Interner JSON-/GraphQL-Endpoint des Shops** | Das Frontend holt Bestand und Preis aus einer kleinen JSON-Antwort; der Scraper ruft dieselbe URL ab — wenige KB statt mehrerer MB HTML | **ja** — größter echter Gewinn, Etappe 2 |
| WebSocket/SSE des Shops | Der Shop schiebt Lageränderungen an den Browser; ein Client abonniert denselben Kanal | nur wo vorhanden, pro Shop zu prüfen — kein Plan-Bestandteil |
| Hohe Frequenz über viele IPs | Sekundentakt von einem Rechner-Cluster mit rotierenden Proxys | **nein** — Proxy-Rotation ist ausgeschlossen |
| Warenkorb-Probe („add to cart") | Bestand wird durch Hinzufügen in den Warenkorb getestet | **nein** — ToS, Sperrgefahr, Kauf-Bot-Territorium |
| Händler-/Marktplatz-APIs | Amazon SP-API, Partner-APIs der Marktplätze | **nein** — setzt Verkäuferkonten und Rollen voraus |
| Fertige Alarm-Bots (Telegram/Discord) | dieselben Endpoints, zentral und dauerhaft betrieben | als Signal lesbar, nicht als Abhängigkeit |

Dazu die Grenze, die dabei oft übersehen wird: **Der Shop cached selbst.** Liefert der
CDN-Cache die Produktseite 60 s lang aus, sieht auch ein perfekter Client den Restock
erst nach 60 s. „Sofort" heißt in der Praxis deshalb: den *ungecachten* Endpoint treffen
— nicht schneller HTML raten. Genau das ist Etappe 2.

### Echtzeit: was hier erreichbar ist — und was nicht

„Echtzeitüberwachung" ist keine Eigenschaft des Codes, sondern eine Rechnung aus **Takt**
und **Betriebszeit**. Ein Verfügbarkeitsfenster von einer Minute wird von einem
15-Minuten-Takt mit rund 93 % Wahrscheinlichkeit verpasst — nicht weil der Parser
schlecht ist, sondern weil in diesen 15 Minuten niemand hinsieht.

| Takt | 1-Minuten-Fenster erkannt | 15-Sekunden-Fenster erkannt | Wo möglich |
|---|---|---|---|
| 15 min (Hintergrund heute) | ~7 % | ~2 % | Android-Grenze, Foreground-Service |
| 5 min | ~20 % | ~5 % | Hintergrund mit Wächter |
| 60 s | ~100 % | ~25 % | WLAN, wenige Shops |
| 30 s | ~100 % | ~50 % | **Ziel v1.5 im Vordergrund** |
| 20 s | ~100 % | ~75 % | nur heiße Shops, mit JSON-Pfad |
| < 10 s, verteilt | ~100 % | ~100 % | Bot-Niveau: Cluster und Proxy-Rotation — **ausgeschlossen** |

*(Wahrscheinlichkeit, dass mindestens eine Prüfung ins Fenster fällt: Fenster/Takt,
solange das Fenster kürzer als der Takt ist; ist es länger, wird es sicher erkannt.)*

Daraus folgen drei Stufen, die ehrlich getrennt bleiben:

1. **Vordergrund-Live (v1.5, Etappe 3):** Takt ≤ 30 s für heiße Shops → ein
   Ein-Minuten-Fenster wird praktisch immer gesehen. Gilt nur, solange die App offen ist.
2. **Hintergrund (v1.5 unverändert):** 15 min, also rund 7 % eines Minutenfensters. Diese
   Zahl steht in der Hilfe, nicht nur im Code — die Alternative wäre eine Lüge.
3. **24/7 in Sekunden (v1.6, Cloud-Wächter):** eigener kleiner Server, 30–60 s Takt für
   6–8 Shops. Das ist der einzige Weg zu „läuft, während das Handy aus ist" — und genau
   das, was Bestell.bar mit eigener Infrastruktur betreibt.

**Zwei Messgrößen, die dazugehören** (sonst bleibt „Echtzeit" ein Wort):

* **Erkennungslücke:** Zeit zwischen dem Abruf, der den Wechsel sieht, und dem Aufleuchten
  des Alarms. Ziel p95 < 5 s — der Alarmweg ist lokal und damit messbar.
* **Fensterdauer:** wie lange ein Treffer tatsächlich offen war, aus dem eigenen Verlauf.
  Sie zeigt, ob der Takt reicht: ein Shop mit 20-Sekunden-Fenstern braucht 20 s, einer mit
  Stundenfenstern nicht.

**Abnahme für die Live-Stufe:** Ein künstliches Testfenster von einer Minute wird im
Vordergrund in 20 von 20 Läufen erkannt; die Erkennungslücke hat p95 < 5 s; die Hilfe
nennt für den Hintergrund die Quote von rund 7 % und verweist auf v1.6.

---

## 3. Was „Händler-Erkennung" hier heißt

Gemeint ist: **automatisch Kandidaten für neue Shops finden** und sie nachprüfbar
aufnehmen. Nicht gemeint ist die Erkennung von Marketplace-Drittanbietern auf einer
Shop-Seite — die gibt es seit v1.4 (`_marketplace()`, Hinweis auf der Trefferkarte).

Der Ablauf ist bewusst zweistufig, weil ein automatisch erweiterter Host-Kreis die
einzige Sicherheitszusage der Remote-Konfiguration brechen würde:

1. **Finden (automatisch, offline):** Ein Werkzeug sammelt Händlerkandidaten aus
   Preisvergleichs-Händlerlisten und prüft sie deterministisch.
2. **Aufnehmen (geprüft):** Ein Kandidat wird erst zum eingebauten Händler, wenn er
   eine Fixture und den Testlauf besteht. Der Host-Kreis der `shop_config.json`
   bleibt unverändert.

**Warum Preisvergleich statt Suchmaschine:** Geizhals und Idealo führen zum Modell
bereits eine Händlerliste mit Domains — das ist genau die gesuchte Menge, ohne
SERP-Scraping und ohne geratene Domains. Ein Kandidat, der dort zum Produkt gelistet
ist, hat das Produkt nachweislich im Sortiment.

---

## 4. Etappen

Reihenfolge ist bindend: Etappe 1 ohne Etappe 0 hätte keinen Beleg, Etappe 2 ohne
Etappe 1 keinen ruhigen Takt, Etappe 5 ohne Etappe 4 keine Kandidaten.

### Etappe 0 — Messlatte (0,5 Tag)

**Ziel:** Vorher messen, sonst ist „live ist besser" eine Behauptung.

* `scan_core.health_uebersicht()`: pro Shop Erfolgsquote, Zähler für `challenge`,
  `parser`, `error`, p50/p95-Dauer und übertragene Bytes je Prüfung aus der
  vorhandenen `ps5pro_health.json`.
* Lokaler Zähler für das Request-Budget (nur im Speicher/Health, kein Versand).
* Diagnose-Zeile in der App (Konzept §9: Zähler bleiben lokal und sind sichtbar).

**Abnahme:** Selftest-Fall für das Aggregat mit synthetischen Health-Daten, ohne Netz.
**Risiko:** keins — reine Auswertung.

### Etappe 1 — Priorisierter Scheduler in `scan_core` (2–3 Tage)

**Ziel:** Statt „alle 42 alle N Minuten" entscheidet der Kern, welche Shops jetzt dran sind.

```python
def faellige_haendler(haendler, health, jetzt, budget, modus="live"):
    """Shops, die jetzt geprueft werden sollen - deterministisch."""

def shop_intervall(eintrag, health, jetzt):
    """10-30 s heiss, 2-5 min normal, 10-15 min gestoert, Ruhe nach 403/429."""
```

Regeln:

* **heiß:** letzter Zustand `in_stock`, `chance` oder Treffer in den letzten 60 min → 10–30 s
* **normal:** noch nie verfügbar gesehen → 2–5 min
* **gestört:** zwei Parserfehler in Folge → 10 min; `challenge`/Rate-Limit → 10 min Ruhe
  (Circuit Breaker, nicht dauerhaft)
* **Jitter:** ±20 % pro Shop, damit nicht alle gleichzeitig aufschlagen
* **Budget:** harte Obergrenze Requests/Minute (Vorschlag 40 Vordergrund, 20 Hintergrund);
  fällige Shops werden rotierend bedient, damit keiner verhungert
* **Determinismus:** `jetzt` und `random.Random(seed)` werden injiziert — im Betrieb die
  Uhr, im Test feste Werte

**Abnahme (Selftest, keine Netzzugriffe):**
* heißer Shop ist nach 30 s fällig, kalter erst nach 5 min
* Circuit Breaker greift nach 403 und lässt den Shop nach 10 min wieder zu
* Budgetdeckel wird eingehalten; über zwei Runden wird jeder fällige Shop bedient
* Jitter bleibt im erlaubten Band; gleicher Seed → gleiche Reihenfolge

**Risiko:** mehr Requests an heiße Shops. Gegenmaßnahme: Budget, Jitter, Ruhe nach 403 —
und Etappe 0 als Vorher-Nachher-Beleg.

### Etappe 2 — Schneller Datenpfad pro Shop (3–4 Tage, der eigentliche „Sofort"-Gewinn)

**Ziel:** Nicht schneller raten, sondern die kleinere und aktuellere Quelle abfragen:
den JSON-/GraphQL-Endpoint, den das Shop-Frontend selbst benutzt.

* Pro Shop recherchieren, welche Anfrage der Browser beim Öffnen der Produktseite stellt
  (Bestand, Preis, Zustand). Ergebnis: wenige KB JSON statt 1–5 MB HTML.
* Aufnahme **deklarativ** in `shop_config.json` (Schema 2, neues Feld `api`):
  `url` (weiterhin nur Hosts der Allowlist), `preis_pfad` und `bestand_pfad` als
  Punkt-Pfade in die JSON-Antwort, `bestand_werte` als Liste literaler Werte
  (z. B. `InStock`, `true`, `1`). Kein Code, keine Regexe aus der Remote-Datei —
  gleiche Begründung wie bei den Parser-Regeln (ReDoS, Injektion).
* `scan_core`: `fetch_json_mit_cache()` mit ETag/304 wie heute, `json_parser_ergebnis()`
  liefert `preis`, `state`, `sofort`. Bei jedem Fehler fällt der Shop auf den HTML-Pfad
  zurück und gilt nicht als kaputt.
* Das Ergebnis zählt wie heute: derselbe Zustandsautomat, dieselbe Klassifikation,
  dieselbe Verifikation — nur mit kürzerer Antwortzeit und kleinerem Traffic.

**Schema-Kompatibilität (wichtig):** v1.4 lehnt Schema 2 komplett ab und bleibt dann auf
der eingebauten Liste — inklusive aller URL-Korrekturen. Schema 2 wird deshalb erst
veröffentlicht, wenn 1.5 draußen ist; für ältere Installationen gibt es so lange keine
Remote-Updates. Das gehört in die Release-Notes.

**Abnahme:** Selftest-Fälle mit JSON-Fixtures (Preis, `in_stock`, `sold_out`,
Vorbestellung, fehlender Pfad → HTML-Fallback, ungültige Remote-Regel → ganze Datei
verworfen, private/relative API-URL abgelehnt). Messung gegen Etappe 0: für mindestens
drei Shops deutlich kleinere Antwort und kürzere p95-Dauer als der HTML-Abzug.

**Risiko:** Endpoints sind nicht zugesagt und können sich ändern. Gegenmaßnahme:
HTML-Fallback, Health-Serie, `--check` im Discovery-Werkzeug; nur Shops aufnehmen, bei
denen der Endpoint belegt ist.

### Etappe 3 — LIVE im Vordergrund: Takt ≤ 30 s + Verlaufs-Anzeige (3 Tage)

**Ziel:** Der Schnell-Modus wird zum echten Live-Betrieb — und das, was er sieht, wird
sichtbar.

* `_fast_tick()` fragt `faellige_haendler()` statt fix `HOT_SHOPS` alle 60 s.
* Takt 20 s im Vordergrund, WLAN-Regel und „kein Overlap" (`if self.scanning`) bleiben.
* HUD zeigt: `LIVE 20S · 4 FÄLLIG · BUDGET 12/40`.
* Der Verlauf hält **Fensterdauer** und **Erkennungslücke** fest („war 1 Min. offen",
  „Alarm 3 s nach Erkennung") — das ist der Nachweis, dass Live etwas bringt.
* Hintergrund bleibt bei 15 min — im HUD und in der Hilfe klar benannt, nicht schöngeredet.
* Der Schalter in SETUP heißt weiter „Schnellscan"; nur das Verhalten dahinter ändert sich.
* **Drop-Fenster:** In `DROP_FENSTER` stehen nur **belegte** Zeiten, die Herkunft steht
  als Kommentar im Code (Sony schaltet „in unregelmäßigen Abständen" frei — merkur.de,
  10.11.2026; Stempel eines Überwachungsdienstes 09:31 und 10:28–10:35 — bestell.bar;
  Community-Beobachtungen 08:57–17:36 — foraum.de, 11.11.2026). Daraus folgt für
  PlayStation Direct DE/AT das Fenster **09:00–18:00**: Scheduler-Takt 10 s, Runde im
  10-s-Takt, HUD zeigt `FENSTER`; die Rundengröße sinkt auf **6 Shops**, damit das Budget
  von 40 Requests/Minute hält. Für **MediaMarkt/Saturn ist keine Uhrzeit belegbar**
  (Presse und Leitfäden nennen nur „Schübe") — sie bleiben im normalen Takt, statt 10 s
  rund um die Uhr abgefragt zu werden. Eine Sperre schlägt das Fenster: nach 403/429
  wird nicht im 10-s-Takt angeklopft.
* **Sofortmeldung:** Ein Treffer aus JSON-LD oder einer belegten Remote-Regel, der
  ausdrücklich `in_stock` ist und einen plausiblen Preis hat, wird **sofort** gemeldet
  (`meldebereit`); der zweite Abruf läuft direkt danach als Nachtrag, korrigiert die Karte
  und zeigt bei Ausverkauf `ZURÜCKGESTUFT`. Treffer aus Text-Markern warten wie bisher
  auf die Verifikation — „ein Alarm muss stimmen" bleibt die Regel, nur der Umweg über
  zwei Sekunden Wartezeit fällt bei belegten Treffern weg.

**Detail A — Dauer des Verfügbarkeitsfensters im Event-Ticker**

Ein Drop ist oft nur eine Minute offen. Diese Dauer ist die eigentlich nützliche
Information — sie sagt, wie schnell man sein muss, und sie macht aus einem Haufen
Momentaufnahmen eine Geschichte.

* Neuer lokaler Ringpuffer `ps5pro_events.json` (höchstens 200 Einträge, FIFO):
  Zeitstempel, Shop, Wechsel (z. B. `sold_out → in_stock`), Preis und — beim
  Zurückspringen — **Dauer des abgelaufenen Fensters**.
* Quelle ist der vorhandene Verlauf (`History`: `verfuegbar`/`verfuegbar_zeit`) plus die
  Zustandswechsel aus `scan_einen()`: kein zusätzlicher Request, keine Serverdaten.
* Darstellung als Ticker/Verlaufsliste (Einstieg in SETUP, im Querformat als rechte
  Spalte unter der Trefferliste):
  `10:42 Amazon DE · verfügbar → ausverkauft · war 1 Min. offen · 899,99 €`.
* Dauer lesbar formatiert: unter 90 s als „45 s" bzw. „1 Min.", darüber „12 Min.", ab
  einer Stunde „2 Std.".
* Die Detailansicht eines Treffers zeigt zusätzlich das letzte Fenster: Beginn, Ende,
  Dauer und Preisbereich darin.
* Ein Eintrag entsteht nur bei echtem Zustandswechsel — bleibt ein Shop ausverkauft,
  wächst der Ticker nicht.

**Detail B — „zuletzt verfügbar am" pro Shop, auch ausverkauft**

Heute sieht man nur den aktuellen Zustand. Ob ein Shop seit Wochen tot ist oder gestern
noch lieferte, ist der Unterschied zwischen „beobachten" und „abschreiben".

* Aus `History.verfuegbar_zeit` pro Shop: „zuletzt verfügbar: 13.11., 10:35" bzw.
  „noch nie verfügbar".
* Sichtbar **auch im ausverkauften Zustand**: in der Trefferzeile, in der Detailansicht
  und in der Shop-Health-Liste (dort zusätzlich als Alter in Tagen).
* Kein Netzaufruf und keine neue Datei — die Angabe steht bereits lokal.
* Ehrliche Grenze: der Wert stammt aus eigenen Scans, nicht vom Händler. Stand die App
  eine Woche still, ist der Wert entsprechend alt — deshalb wird das Alter mitgenannt.

**Abnahme:** `tools/kivy_smoke.py` prüft HUD-Text und Umschalten; Layout bei 620×380
unverändert; STOP bricht eine Live-Runde ab; Hintergrunddienst unberührt. Dazu
Selftest-Fälle für Fensterdauer-Formatierung, Ringpuffer-Deckel und „zuletzt verfügbar"
mit und ohne Verlauf.

**Stand (umgesetzt):** `Events` (Ringpuffer `ps5pro_events.json`, 200 Einträge) schreibt
`History.update()` bei jedem echten Wechsel — im App-Prozess **und** im Hintergrunddienst;
`dauer_text`, `kurz_zeit`/`kurz_tag` und `event_zeile` formatieren die Zeilen. Sichtbar ist
es an drei Stellen: `VERLAUF` in SETUP (Ticker, 30 Einträge, mit `LEEREN`), `ZULETZT
VERFUEGBAR` und `LETZTES FENSTER` in der Detailansicht sowie `ZUL. TT.MM.` in der
Trefferzeile ausverkaufter Shops. Die Shop-Health-Liste bleibt bewusst bei der
Scan-Gesundheit — dort „verfügbar" mit „OK/ERROR" zu mischen, wäre irreführend.
**Risiko:** Akku/Datenvolumen. Gegenmaßnahme: nur Vordergrund, nur bei Bedarf, WLAN-Schalter
bleibt, Takt in SETUP sichtbar.

### Etappe 4 — Discovery-Werkzeug `tools/discover_shops.py` (3–4 Tage)

**Ziel:** Kandidaten finden und prüfen, ohne die App zu ändern.

Ablauf:

1. **Quellen:** Händlerliste der Geizhals-Produktseite (DE und AT) und, falls stabil,
   die Idealo-Händlerliste zum Modell. Kein SERP-Scraping.
2. **Extrahieren:** Händlername + Domain, nur `https`.
3. **Dedupe:** gegen `HAENDLER_BASIS`, Host-Normalisierung ohne `www.`
4. **Prüfen:** `robots.txt` (allgemeiner User-Agent), Produktseite über denselben
   `scan_core`-Pfad laden, `extract_structured()` + `extract_meta_preis()`:
   Produkt erkannt (PS5 Pro 2 TB, kein Zubehör) und Preis in 550–1500 €.
   Bot-Challenge → verwerfen, nicht umgehen.
5. **Bewerten:** JSON-LD (3 Punkte), GTIN (2), Preis beim zweiten Abruf gleich (2),
   Pflicht: `robots` erlaubt, Land DE/AT, HTTPS.
6. **Ausgeben:** `docs/kandidaten.json` (Name, Land, URL, Score, Beleg-Hash, Datum) und
   ein kurzer Konsolenreport. `--check` liefert Exit 1, wenn ein bereits aufgenommener
   Shop plötzlich nicht mehr erreichbar ist.

Randbedingungen: höchstens 1 Request/s, `--offline` mit gespeicherten Seiten für Tests,
keine Suchmaschinen-Umgehung, kein LLM im Pfad.

**Abnahme:** Testfälle gegen Fixture-Seiten ohne Netz (Score, Dedupe, Verwerfen bei
Challenge, Verwerfen bei falschem Produkt); Ausgabe deterministisch sortiert.
**Risiko:** Preisvergleichsseiten ändern ihr HTML. Gegenmaßnahme: dünner Parser, der bei
Bruch sauber scheitert; Fallback bleibt die manuelle Domainliste.

### Etappe 5 — Aufnahme eines Kandidaten (2 Tage)

**Ziel:** Aus einem Kandidaten wird ein echter Händler — nachprüfbar.

Ablauf, einmal dokumentiert:

1. Eintrag `_h("Name", "DE"|"AT", "https://…")` in `scan_core.HAENDLER`
   (`HAENDLER_BASIS` folgt automatisch).
2. Fixture aufnehmen: `python3 tools/capture_fixture.py --shop "Name"`.
3. Testfall in `tools/selftest.py` ergänzen (Produkt, Preis, Verfügbarkeit).
4. Feste Zahlen mitziehen: „42 Shops" in `README.md`, `docs/KONZEPT.md` und den
   Release-Notes; `HOT_SHOPS` prüfen (Namen müssen weiter existieren).

**Detail — Amazon-Marketplace-Angebot (`aod=1`) als eigene Zeile**

Bei Amazon steht neben dem eigenen Angebot (899,99 €) oft ein Marketplace-Angebot
(799,99 €). Beides in einer Zeile zu mitteln wäre falsch: anderer Verkäufer, andere
Gewährleistung, anderer Versand.

* Eigener Eintrag `_h("Amazon DE (Marketplace)", "DE", "https://www.amazon.de/dp/…?aod=1")`,
  damit Preis, Verkäufer und Zustand getrennt bleiben. `_marketplace()` kennzeichnet ihn
  weiterhin als Drittanbieter; der Hinweis steht auf der Karte.
* **Gate:** aufgenommen wird der Eintrag nur, wenn die Fixture Produkt **und** Preis
  liefert. Der Test vom 16.11. war negativ — die `aod=1`-Seite kam ohne Product-JSON-LD
  und ohne erkanntes Produkt zurück. Ohne Fixture bleibt Amazon ein blinder Fleck (siehe
  Etappe 2, Risiko), und es wird **kein** Eintrag angelegt.
* Keine Warenkorb-Probe und kein `aod=1`-Trick zum Bestandstest — nur die öffentliche
  Seite, mit demselben fairen Abruf wie jeder andere Shop.
* Alarm-Regel prüfen: ein Marketplace-Treffer ist kein Erstverkauf des Shops, die
  Konfidenz sinkt entsprechend und der Hinweis muss sichtbar bleiben.

**Abnahme:** `python3 tools/validate_shop_config.py` und `python3 tools/selftest.py`
grün, je neuem Shop eine Fixture, `HOT_SHOPS`-Selbsttest unverändert.
**Risiko:** wachsende Liste. Gegenmaßnahme: höchstens fünf neue Händler pro Release,
jeder mit Fixture.

### Etappe 6 — optional: Remote-Händlerliste (Schema 2) (3–5 Tage)

**Nur auf ausdrücklichen Wunsch.** Ermöglicht neue Hosts ohne APK-Update, kostet aber
das bisherige Sicherheitsmodell: `_erlaubte_hosts()` leitet den Kreis heute bewusst aus
der unveränderlichen Basis ab.

Falls gebaut, dann nur mit: Erlaubnisliste statt freier Hosts, Verbot privater/
Loopback-/Link-Local-Ziele (SSRF-Bremse), Redirects nur auf erlaubte Hosts, ganze Datei
bei einem Fehler verwerfen (wie heute), Host-Limit.

**Empfehlung:** nicht in 1.5. Etappen 4 und 5 lösen das Problem ohne diese Öffnung;
der Cloud-Wächter (v1.6) ist der natürlichere Ort dafür.

### Etappe 7 — Release 1.5.1 (1 Tag)

1. `buildozer.spec` **und** `buildozer.play.spec`: `version = 1.5.1`,
   `android.numeric_version = 10501` (`MAJOR*10000 + MINOR*100 + PATCH`).
2. README: Download-Link auf `v1.5.1`, Versionshistorie, „Was die App kann".
   `docs/KONZEPT.md`: Ist-Stand. `RELEASING.md` bleibt unverändert.
3. Gates: `validate_shop_config.py`, `selftest.py` (890 Zusicherungen),
   `check_hilfe_specs.py`, `unittest discover -s support_app/tests`,
   `kivy_smoke.py` in allen sechs Läufen.
4. Tag `v1.5.1` pushen; `set_version_from_tag.sh` leitet `1.5.1` / `10501` ab.
5. Nach dem Lauf prüfen: genau ein APK-Asset, `versionName 1.5.1`,
   `versionCode 10501`, nicht debuggable, Signatur gegen den hinterlegten
   Fingerprint, Release-Notes mit SHA-256.
6. **Rollback:** v1.4.0 bleibt als Asset. Ein Downgrade über eine installierte 1.5.1
   geht wegen des höheren `versionCode` nicht — nur Deinstallation und Neuinstallation
   von 1.4.0, Datenverlust inklusive. Das steht in den Release-Notes.

In Release-Notes und Commits erscheint nur `xsensenmannx` (siehe `AGENTS.md`).

---

## 5. Zeitplan und Meilensteine

| Etappe | Inhalt | Aufwand | Meilenstein |
|---|---|---|---|
| 0 | Messlatte | 0,5 Tag | Vorher-Zahlen liegen vor |
| 1 | Scheduler | 2–3 Tage | Kern taktet deterministisch, Tests grün |
| 2 | Schneller Datenpfad (JSON) | 3–4 Tage | ≥ 3 Shops mit belegtem JSON-Pfad, HTML-Fallback grün |
| 3 | LIVE + Ticker/„zuletzt verfügbar" | 3 Tage | **M1:** Live-Betrieb intern nutzbar |
| 4 | Discovery-Werkzeug | 3–4 Tage | Kandidatenbericht erzeugt |
| 5 | Aufnahme | 2 Tage | **M2:** ≥ 3 neue Händler mit Fixture |
| 6 | Remote-Liste (optional) | 3–5 Tage | nur auf Wunsch |
| 7 | Release 1.5.1 | 1 Tag | **M3:** APK veröffentlicht |

Summe ohne Etappe 6: **rund 15 Arbeitstage** plus Puffer für Shop-Änderungen.

---

## 6. Abnahme für das ganze Release

* **Live:** Takt ≤ 30 s für heiße Shops im Vordergrund, im Drop-Fenster 10 s; ein
  1-Minuten-Testfenster wird in 20 von 20 Läufen erkannt; Erkennungslücke p95 < 5 s;
  403/429-Anteil nicht schlechter als der Vorher-Wert aus Etappe 0; Falschalarme < 2 %
  (Konzept-Nordstern). Sofortmeldung ausschliesslich bei strukturiertem Beleg, jede
  Rückstufung ist sichtbar. Im Hintergrund bleibt es bei 15 min (rund 7 % eines
  Minutenfensters) — dokumentiert, nicht kaschiert.
* **Datenpfad:** bei den aufgenommenen JSON-Shops deutlich kleinere Antwort und kürzere
  p95-Dauer als beim HTML-Abzug, gemessen gegen Etappe 0 — kein Erfolg ohne Zahl.
* **Anzeige:** Ein ausverkaufter Shop nennt sein „zuletzt verfügbar am"; der Ticker
  zeigt die Dauer des abgelaufenen Fensters, und ein Marketplace-Angebot steht als
  eigene Zeile, wenn es eine Fixture besteht.
* **Händler:** mindestens drei geprüfte neue Händler mit Fixture; kein bestehender Shop
  verschwindet; `validate_shop_config.py` und `selftest.py` grün.
* **Nichts aufgeweicht:** kein Captcha-Solver, keine Proxy-Rotation, keine Warenkorb-Probe,
  kein Retry gegen Sperren, keine neuen Hosts in der Remote-Konfiguration.
* **Ehrlich dokumentiert:** die 15-Minuten-Grenze im Hintergrund und der CDN-Cache der
  Shops stehen im README und in der Hilfe, nicht nur im Code.

---

## 7. Bewusst nicht in 1.5

| Nicht gebaut | Grund |
|---|---|
| Sekunden-Push „in Echtzeit" | diese Shops bieten keinen Kanal; der Shop-Cache setzt die Untergrenze — Rechnung in §2 |
| Proxy-Rotation, Warenkorb-Probe, verteiltes Pollen | Umgehung/ToS, und auf einem Handy nicht erreichbar |
| Automatische Aufnahme neuer Shops ohne Prüfung | ein falscher Host kostet Vertrauen und Requests |
| Remote-Hosts ohne Allowlist (Schema 2) | öffnet SSRF-Fläche; erst in 1.6, wenn überhaupt |
| WebSocket-Abonnement des Shop-Frontends | pro Shop unbestätigt; erst wenn Etappe 2 es belegt |
| Cloud-Wächter | verschoben auf v1.6 (siehe `KONZEPT.md`) |
| LLM im Such- oder Scan-Pfad | Determinismus ist Produktprinzip; KI höchstens offline mit Freigabe |

---

## 8. Offene Entscheidungen

1. **Takt der heißen Runde:** 20 s (schneller, mehr Requests) gegen 30 s (ruhiger).
   Empfehlung: 30 s starten, 20 s nur mit WLAN und nur für Shops mit Trefferhistorie.
2. **Discovery-Quelle:** Geizhals allein (stabil, eine Quelle) oder zusätzlich Idealo
   (breiter, zweiter Parser). Empfehlung: Geizhals zuerst, Idealo nur wenn die
   Abdeckung nach Etappe 4 nachweislich Lücken hat.
3. **Aufnahme-Rhythmus:** neue Händler sammeln und mit 1.5 bündeln, oder 1.5.1 als
   reines Händler-Update. Empfehlung: bündeln, höchstens fünf pro Release.
4. **JSON-Pfad je Shop:** nur für die sechs heißen Shops (schnellster Nutzen) oder für
   alle 42 (mehr Arbeit, weniger Traffic überall). Empfehlung: heiße Shops zuerst,
   Rest in 1.5.1 nachziehen.

---

## 9. Abdeckung der heißen Shops (Messung 17.11.2026)

Gemessen mit dem App-Pfad (`scan_core.fetch_mit_cache`/`scan_einen`), je URL ein
Abruf, keine Umgehung von Bot-Schutz.

| Shop | Befund | Maßnahme |
|---|---|---|
| Amazon DE | HTTP 200, 2,4 MB, **0** `ld+json`-Blöcke. Kaufbox zeigte 1.469,98 € („Nur noch 1 auf Lager“); der generische Preis-Regex nahm 1.488,00 € aus einem Fremdangebot. | Neuer Pfad `extract_amazon`: liest Preis nur in `corePrice_feature_div`/`apex_desktop` (auch getrennte Ganz-/Nachkommateile), Bestand aus `id="availability"`. Fixture auf Kaufbox-Markup umgestellt. |
| Amazon AT | Wie DE, zusätzlich war die URL eine **Suchseite** (`/s?k=…`) ohne Kaufbox. | Produktseite `/dp/B0FRYBZR91` (HTTP 200, Kaufbox vorhanden) statt Suche. |
| Otto DE | Alle getesteten Pfade (`/suche/…` mit und ohne Schrägstrich, `/p/…`) antworten **HTTP 400** mit Kasada-Script (`window.KPSDK`), auch mit Cookies aus einem vorherigen Aufruf der Startseite und vollen Browser-Headern. Startseite selbst: 200. | Kein Umweg (KONZEPT §7). `kpsdk` gilt jetzt als Bot-Schutz: der 400er wird im Body erkannt, als `challenge` gemeldet und nicht wiederholt. |
| Otto AT | `www.otto.at` ist **OTTO Immobilien** (Immobilienmakler), nicht der Händler; jeder Produktpfad dort ist 404. Der Händler OTTO hat keinen österreichischen Shop. | Offen: Eintrag in einem Folgeschritt durch einen AT-Händler ersetzen — das ändert Shop-Liste, Fixtures, Zähler und Store-Texte und gehört nicht in diesen Fix. |
| Cyberport DE/AT | **Jeder** Pfad inklusive `/robots.txt`, `/sitemap.xml` und Startseite: HTTP 403 „Just a moment…“ (Cloudflare). Am 16.11. kam noch Inhalt, die Suchseite hatte aber keinen Produktpreis. | Erkennung als Bot-Schutz (kein Retry). Eine Produkt-URL lässt sich derzeit nicht belegen — bewusst keine geratene URL. Offen: Produktseite aufnehmen, sobald ein Abruf durchgeht. |

**Regel für Fixtures:** Was die Seite nicht hergibt, bleibt `None`. Die neuen
Amazon-Fixtures enthalten deshalb kein JSON-LD, sondern genau die Kaufbox; der
Selftest prüft, dass ein Fremdpreis außerhalb der Kaufbox nicht gewinnt.
