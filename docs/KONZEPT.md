# Konzept — PS5 Pro Search Agent

**Stand:** v1.4.0 ist veröffentlicht (`versionCode 10400`); v1.3 bleibt als
Release unverändert. Dieses Dokument beschreibt, was das Produkt ist, warum es
so gebaut ist und was als Nächstes kommt.
**Leitsatz:** Ein Alarm muss stimmen. Lieber 30 Sekunden später als einmal falsch.

---

## 1. Nordstern

### Der Job

> „Sag mir verlässlich, wann und wo ich die PS5 Pro 2 TB zum fairen Preis kaufen kann —
> ohne 42 Tabs, ohne Konto, ohne dass ich nachts alle 10 Minuten nachsehe."

### Die zwei Zahlen, die zählen

Alles andere ist Dekoration. Erfolg wird an genau zwei Größen gemessen:

| Metrik | Ziel | Warum |
|---|---|---|
| **Falschalarme pro Monat** | < 2 % aller gemeldeten Treffer | Ein falscher Alarm zerstört Vertrauen schneller als zehn verpasste |
| **Verpasste echte Treffer** | < 5 % der Verfügbarkeitsfenster | Der zweite Fehler, der Nutzer wirklich ärgert |

Geschwindigkeit ist diesen beiden Zahlen untergeordnet. Ein Tool, das in 20 Sekunden
meldet, aber in 10 % der Fälle lügt, ist schlechter als eines, das in 90 Sekunden
meldet und immer recht hat.

### Positionierung

Die App ist **kein Kauf-Bot**. Sie kauft nicht, sie löst keine Captchas, sie rotiert keine
Proxys, sie legt keine Konten an und sie sammelt keine Telemetrie. Genau das ist der
Vorteil: Sie fliegt nicht raus, sperrt keine Shop-Konten und bleibt auch dann nutzbar,
wenn Shops ihre Bot-Abwehr verschärfen.

Der Wettbewerb ist nicht „der schnellste Bot", sondern **das offene Fenster und die
offene Tabelle**. Die App gewinnt durch Verlässlichkeit, Nachvollziehbarkeit und
Datensparsamkeit — nicht durch mehr Shops oder aggressivere Requests.

### Was „unglaublich" hier bedeutet

Nicht ein Versprechen, das niemand halten kann, sondern vier Bausteine, die den
Unterschied machen. Die Basis dafür steht seit v1.3; die Bausteine selbst sind Roadmap:

1. **Beweisfenster** (v1.4) — zu jedem Treffer ein lokal gespeicherter, redigierter
   Beleg (Preis, Stock-Text, Zeitstempel, Hash). Der Nutzer sieht, *warum* die App das glaubt.
2. **Chance ≠ Treffer** (v1.4) — Lotterien, Einladungen und „nur im Markt" werden als
   eigene Kategorie gemeldet, nicht als verfügbar.
3. **Persönlicher Cloud-Wächter** (v1.5) — ein Ein-Klick-Deployment, das prüft, während
   das Handy aus ist, ohne Konto und ohne zentrale Datensammlung.
4. **Parser-Doktor** (v1.4, CI) — KI schlägt neue Regeln vor, wenn eine Shop-Seite bricht;
   Tests entscheiden, ein Mensch gibt frei. Kein LLM im Scan-Pfad.

Bereits gebaut: Webhook-Alarme, Treffer-Verifikation und Schnell-Modus (v1.3);
Verfügbarkeitszustände, Konfidenz, Beleg und GTIN/Bundle (v1.4).

---

## 2. Ist-Stand v1.4

Bereits gebaut und getestet:

* 42 Shops (DE + AT), 6 Threads, Retry mit wechselnden User-Agents, ETag/304-Cache.
* Preis-Erkennung über JSON-LD, Meta/Microdata und Text-Fallback, inklusive
  Zubehör-Filter und Fremdwährungs-Schutz.
* Treffer-Logik mit Preisgrenze, Zustand (neu/gebraucht), Vorbestellung, Bot-Schutz.
* Preisverlauf, 30-Tage-Tief, Sparkline, Shop-Health.
* Alarm-Regeln (sofort, Tiefstpreis, Ruhezeit, Stummschaltung) und Foreground-Service
  mit Boot-Start.
* **Webhook-Alarme** (ntfy, Telegram, Discord, generisch) mit Maskierung und Dedupe.
* **Treffer-Verifikation** per zweitem Abruf ohne Cache; Rückstufung bei Ausverkauf.
* **Schnell-Modus** für sechs heiße Shops im Minutentakt.
* Remote-Konfiguration für URLs und deklarative Parser-Regeln.
* **v1.4:** Verfügbarkeitszustände (Markt/Lotterie/Einladung/Vorbestellung),
  Konfidenz 0–100, Beleg-Ausschnitt mit Hash, GTIN/EAN, Bundle-Filter,
  Marketplace-Hinweis und ein 304-Cache mit maximal sechs Stunden Alter.
* 777 Logiktests, sechs Kivy-Smoke-Läufe (inkl. 120 % Schrift), signierte Releases.

Was das *nicht* löst: Das Handy schläft weiterhin, Lotterien werden nicht erkannt,
und ein Treffer ist noch keine erklärte Entscheidung.

---

## 3. Harte Randbedingungen

Diese fünf Fakten bestimmen jede Design-Entscheidung. Wer sie ignoriert, baut Demo-Software.

| Fakt | Konsequenz |
|---|---|
| **Shops haben keine API.** HTML ändert sich, A/B-Tests, Regionen, Bot-Schutz. | Parser sind Schätzungen. Deshalb zweiter Abruf, Konfidenz und Beleg statt „ist so". |
| **Das Handy schläft.** OEM-Akkumanager beenden Dienste, Android begrenzt Hintergrundarbeit. | Ohne zweiten Rechner gibt es keine Sekunden-Alarme. Der Cloud-Wächter ist optional, nicht Magie. |
| **Drops sind oft keine Bestände.** Amazon-Einladung, MediaMarkt-Lotterie, „nur im Markt". | Diese Zustände brauchen eigene Parser und eine eigene Alarmart. Ein Preis-Scraper sieht sie nicht. |
| **Rate-Limits und ToS gelten.** Mehr Requests sind nicht mehr Chancen, sondern mehr Sperren. | Faires Budget, Backoff, keine Proxy-Rotation, keine Umgehung. |
| **Solo-Maintainer.** Jede Automatik, die niemand prüft, ist ein Risiko. | Deterministischer Kern, Tests als Vertrag, KI nur mit menschlicher Freigabe. |

---

## 4. Produktprinzipien

1. **Wahrheit vor Tempo.** Ein Treffer wird gegengeprüft, bevor er zählt.
2. **Erklärbar.** Jede Meldung beantwortet: welcher Shop, welcher Preis, welcher Beleg,
   welche Konfidenz.
3. **Deterministisch.** Parsing ist Code plus deklarative Regeln — kein LLM, keine
   Zufallsentscheidung im Scan-Pfad.
4. **Faire Last.** Ein Scan-Budget pro Minute, Jitter, Backoff, kein Retry gegen Sperren.
5. **Datensparsamkeit.** Keine Konten, keine Telemetrie, keine Standortdaten. Webhook-Tokens
   bleiben lokal und maskiert.
6. **Ausfallsicher.** Jede Funktion hat einen degradierten Modus: ohne Cloud lokal,
   ohne Netz aus dem Cache, ohne Verifikation als „ungeprüft" gekennzeichnet.
7. **Offen.** MIT-Lizenz, reproduzierbare Builds, prüfbare Hashes, kein Lock-in.

---

## 5. Architektur

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  App (Kivy, Android)         │        │  Optionaler Cloud-Wächter     │
│  Radar, Karten, Detail,      │        │  Cron 2–5 min, 6–8 Hot-Shops  │
│  SETUP, Alarm-Regeln         │        │  Push über ntfy/Telegram      │
│  lokaler Scan + Service      │        │  Zustand in D1/KV             │
└──────────────┬───────────────┘        └──────────────┬───────────────┘
               │  gleiche Regeln, gleiches Ergebnis   │
               ▼                                      ▼
        ┌──────────────────────────────────────────────────┐
        │  scan_core (deterministisch, ohne Kivy)          │
        │  Fetch/Cache · Parser · Health · History         │
        │  Klassifikation · Verifikation · Alarm-Regeln    │
        └──────────────────────────────────────────────────┘
```

**Warum kein Backend-Zwang:** Die App bleibt vollständig nutzbar, wenn niemand einen
Server betreibt. Der Wächter ist eine Verstärkung für Nutzer, die bereit sind, ein
kostenloses Konto bei einem Hosting-Anbieter zu verbinden — kein Gate.

**Warum `scan_core` getrennt bleibt:** App, Hintergrunddienst und Wächter teilen exakt
dieselbe Logik. Ein Treffer im Hintergrund ist derselbe Treffer wie im Vordergrund.

---

## 6. Roadmap

Drei Releases, jedes mit einem klaren Zweck. Keine Version ohne Abnahmekriterien.

### v1.4 — „Vertrauen" (Kern umgesetzt)

Das Release, das die zwei Nordstern-Zahlen wirklich bewegt. **In v1.4 umgesetzt:
A (Konfidenz), B (Beweisfenster), C (Chance statt Treffer) sowie GTIN/Bundle und
Cache-Frische. Offen bleiben D (adaptiver Scan) und E (Parser-Doktor).**

**A. Konfidenz 2.0 (0–100)**
Signale mit Gewicht: zweiter Abruf bestätigt (40), Preis plausibel zum 30-Tage-Median (15),
Stock-Beleg explizit statt Text-Fallback (15), neu und erster Verkäufer (10),
Preisänderung plausibel (10), Antwort frisch statt 304 (10). Alarm ab Schwelle 70
(einstellbar). Die Karte zeigt `92 %`, das Detail erklärt die Signale einzeln.

**B. Beweisfenster**
Zu jedem Treffer werden lokal ~1 KB redigierter Kontext gespeichert: Preis-Marker,
Stock-Text, Zeitstempel, SHA-256 des Ausschnitts. Details zeigen „BELEG 12:04:07 ·
799,00 € · InStock". Maximal 200 Belege, danach FIFO; Export nur auf Knopfdruck.
Das ist der stärkste Vertrauensbeweis, den ein Scraper liefern kann.

**C. Chance statt Treffer**
Neue Zustände `invite`, `lottery`, `market_only`, `preorder_window`. Eigene Parser für
Amazon-Einladung, MediaMarkt-Lotterie und Marktabholung. Alarmart **CHANCE** mit
eigenem Ton/Text und ohne „VERFÜGBAR"-Status. Keine Kaufzusage, keine Warteschlange.

**D. Adaptiver Scan**
Health-basierte Intervalle (kaputte Shops seltener, gesunde öfter), Circuit Breaker pro
Shop, Jitter, globales Budget (z. B. 120 Requests/Minute), Ruhe nach 403/429 für 10 min.

**E. Parser-Doktor (CI)**
Wenn eine Fixture bricht, erzeugt ein LLM aus dem Diff einen Vorschlag für deklarative
Regeln. Der Vorschlag läuft gegen Schema-Validierung und alle Tests; ein Mensch merged.
Kein Laufzeit-LLM, keine automatische Veröffentlichung, keine Nutzerdaten.

**Abnahme v1.4**
* Falschalarm-Quote in 30 Tagen Testbetrieb < 2 % (lokal gezählt).
* Jeder Alarm trägt Konfidenz und Beleg; Detail zeigt beides.
* Ein Lotterie-/Einladungszustand erzeugt CHANCE, nie VERFÜGBAR.
* 800+ Tests, alle sechs Smoke-Läufe, Release-Gates wie v1.3.

### v1.5 — „Cloud" (2–4 Wochen)

**Persönlicher Wächter, ohne Konto in der App.**
Ein kleines Worker-Deployment (Cron 2–5 min, 6–8 Hot-Shops, ntfy-Push), das der Nutzer
mit einem Klick in sein eigenes Hosting legt. Kopplung per QR-Code: Die App zeigt
`watcher-url` + einmaliges Token, danach Heartbeat und letzte Prüfung im HUD.

* Zustand: letzte Treffer, Dedupe, Cooldown, Health — in D1/KV des Nutzers.
* Push: dieselben Webhook-Kanäle wie v1.3, plus Signatur (HMAC) optional.
* Kosten: 0–5 €/Monat, abhängig vom Anbieter; im Konzept dokumentiert.
* **Ehrliche Grenze:** Cloud-IPs werden von Shops häufiger geblockt. Der Wächter ist
  Ergänzung, kein Ersatz. Fällt er aus, übernimmt das Handy.

**Sicherheit:** Kein zentraler Server, kein geteiltes Geheimnis, Rate-Limit pro Token,
Kill-Switch in der App, keine Secrets im Repository.

**Abnahme v1.5**
* Zwei Geräte, ein Wächter: Alarm kommt an, wenn die App geschlossen ist.
* Fremdes Token wird abgelehnt; fehlendes Token ebenfalls.
* Ausfall des Wächters ist im HUD sichtbar, lokaler Scan läuft weiter.
* Deploy-Anleitung in unter 10 Minuten, ohne Terminal-Zwang (Deploy-Button).

### v2.0 — „Intelligenz" (3–6 Wochen)

**Preis-Assistent.** 90-Tage-Bänder statt Punktprognose: „typisch 799–849 €",
„aktuell am oberen Rand", „kaufen oder warten" mit erklärbaren Faktoren. Dazu
Restock-Fenster aus der Historie („MediaMarkt war in 8 von 10 Fällen zwischen 09 und 11 Uhr
verfügbar") — mit Konfidenz, nie als Garantie.

**Natürlichsprachige Filter.** „unter 700, nur Amazon, nur neu" wird auf vorhandene
Einstellungen abgebildet. Optional per LLM, immer mit sichtbarer Übersetzung in
konkrete Regeln; ohne LLM per Muster-Parser.

**Lokale Qualitätsanzeige.** Scans, Treffer, bestätigte Treffer, Falschalarme
(Selbstauskunft), Webhook-Fehler — exportierbar als JSON. Standard: keine Telemetrie.
Opt-in-Aggregat frühestens, wenn es einen echten Nutzen für den Nutzer hat.

**Abnahme v2.0**
* Prognose ist als Band mit Unsicherheit dargestellt, nie als sichere Zahl.
* Jede Empfehlung nennt ihre Faktoren.
* Ohne Opt-in verlässt kein einziges Byte das Gerät.

---

## 7. Was bewusst nicht kommt

| Anti-Feature | Grund |
|---|---|
| Auto-Checkout / Warenkorb-Bot | ToS, Zahlungs- und Haftungsrisiko, rechtlich unklar |
| Captcha-Solver, Proxy-Rotation, JS-Challenge-Bypass | Umgehung von Schutzmaßnahmen, führt zu Sperren |
| Kauf von Accounts oder Warteschlangenplätzen | Verletzt Shop-Bedingungen, schadet anderen Nutzern |
| Standort-Tracking | Für den Zweck nicht nötig |
| Ungefragte Telemetrie | Widerspricht dem Kernversprechen |
| „Garantierte" Treffer oder Bestände | Nicht wissen ist ehrlicher als raten |
| Play-Store-Zwang | Unabhängigkeit und direkte Updates bleiben erhalten |

---

## 8. Datenmodell und Schnittstellen

### Ergebnis (Schema v2, Auszug)

```json
{
  "schema": 2,
  "haendler": "Amazon DE",
  "land": "DE",
  "preis": 799.0,
  "klass": "hit",
  "availability_state": "in_stock",
  "confidence": 92,
  "signals": {
    "verified": true,
    "price_plausible": true,
    "stock_source": "jsonld",
    "condition": "new",
    "fresh": true
  },
  "verify": "bestaetigt",
  "evidence": {"ts": "2026-11-13T12:04:07", "hash": "…", "excerpt": "799,00 € · InStock"},
  "zeit": "12:04:07"
}
```

### Webhook (v2)

```json
{
  "schema": 2,
  "event": "hit",
  "shop": "Amazon DE",
  "price": 799.0,
  "confidence": 92,
  "url": "https://…",
  "ts": "2026-11-13T12:04:07Z"
}
```

Optional `X-PS5Pro-Signature: sha256=…` (HMAC mit nutzereigenem Secret). Kanäle ohne
JSON-Verständnis (ntfy) bekommen weiterhin die kurze Textzeile.

### Einstellungen (neu in v1.4/v1.5)

`confidence_min`, `evidence_keep`, `chance_alerts`, `scan_budget`,
`watcher_url`, `watcher_token`, `alarm_nur_bestaetigt` (seit v1.3).

---

## 9. Messbarkeit ohne Telemetrie

Zähler bleiben lokal und sind im Diagnose-Screen sichtbar:

* Scans, geprüfte Shops, Treffer, bestätigte Treffer, Rückstufungen.
* Falschalarme (Nutzer tippt „war nicht verfügbar") — die einzige ehrliche Quelle.
* Webhook-Zustellungen und Fehler, Wächter-Heartbeat.
* Parser-Fehler pro Shop und Serie.

Qualitätsziele:

| Ziel | Wert |
|---|---|
| Falschalarme | < 2 % |
| Verpasste Fenster | < 5 % |
| p95 Alarm lokal | < 60 s nach Treffer |
| p95 Alarm Cloud | < 5 min |
| Scan-Erfolgsquote | ≥ 90 % |
| Akku (Hintergrund) | ≤ 3 %/Tag |
| Absturzfreiheit | ≥ 99,5 % |

---

## 10. Risiko-Register

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Shop ändert HTML | Parser bricht, Treffer fehlen | Fixtures, Parser-Doktor, Remote-Regeln, Health-Serie |
| Bot-Schutz verschärft | Scan blockiert | Kein Umgehen, Backoff, langsamere Intervalle, klare Anzeige |
| Cloud-IPs geblockt | Wächter nutzlos | Wächter optional, Handy-Fallback, ehrliche Kommunikation |
| Token-Leak | Fremder Zugriff auf Webhook/Wächter | Maskierung, Redaction, per-Gerät-Token, Rotationsknopf |
| Recht/ToS | Abmahnung, Sperre | Keine Umgehung, keine Käufe, öffentliche Preise, Dokumentation |
| Bus-Faktor 1 | Projekt stirbt | Tests als Vertrag, Dokumentation, reproduzierbare Builds |
| Supply Chain | Kompromittierte APK | Signaturprüfung, Hash im Release, feste Abhängigkeiten |

---

## 11. Release-Gates

Jede Version muss dieselben Tore passieren wie v1.3:

1. `tools/validate_shop_config.py`, `tools/selftest.py` (0 Fehler), alle sechs Smoke-Läufe.
2. APK-Manifest: Paket, `versionName`, `versionCode`, `targetSdk`, nicht debuggable.
3. Signatur gegen den festen Zertifikat-Fingerprint.
4. Release-Notes mit Änderungen seit dem letzten Tag und SHA-256.
5. Direktlink liefert HTTP 200; Asset-Größe plausibel.
6. Rollback beschrieben: vorherige Version bleibt als Asset erhalten.

---

## 12. Offene Entscheidungen

1. **Hosting für den Wächter:** Cloudflare Worker (kostenlos, schnell, aber Cloud-IPs)
   gegen kleinen VPS (flexibler, kostet). Empfehlung: Worker zuerst, VPS als Alternative
   dokumentieren.
2. **Opt-in-Metriken:** gar nicht, oder erst nach lokalem Diagnose-Screen? Empfehlung:
   zuerst lokal, Opt-in frühestens in v2.0.
3. **ARM32:** weitere Geräte gegen größere APK und mehr Testmatrix. Empfehlung: erst
   wenn Nachfrage belegt ist.
4. **F-Droid:** wünschenswert für Vertrauen, kostet Reproduzierbarkeit und Pflege.
   Empfehlung: nach v1.4 prüfen.

---

## 13. Definition von „fertig"

Eine Version ist fertig, wenn ein fremder Mensch sie ohne Erklärung bedienen kann:
App installieren, Alarm einrichten (lokal oder Webhook), einen Testalarm sehen, einen
echten Treffer mit Beleg und Konfidenz nachvollziehen — und danach weiß, was die App
**nicht** tut. Alles andere ist Zwischenstand.
