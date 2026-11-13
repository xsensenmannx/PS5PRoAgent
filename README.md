# PS5 Pro Search Agent

Android-App (Kivy/Python), die 42 Elektronikhändler in Deutschland und Österreich
gleichzeitig nach der **PlayStation 5 Pro 2 TB** abfragt: Preis, Verfügbarkeit,
Preisänderung gegenüber dem letzten Scan — als Radar im PS1-BIOS-Look.

![Icon](icon.png)

## Was die App kann

* **Parallel-Scan** über 42 Shops (DE + AT) mit 6 Threads, Retry und wechselnden
  User-Agents.
* **Preis-Erkennung** über JSON-LD (`schema.org/Product`, auch verschachtelte
  `priceSpecification` und Angebotslisten), Meta-Tags/Microdata und Text-Fallback —
  inklusive Filter gegen Zubehör (DualSense Edge, Portal, Laufwerk …) und gegen alles,
  was nicht die 2-TB-Konsole ist. Bei mehreren Angeboten gewinnt das günstigste
  neue Angebot vor Gebrauchtware; Fremdwährungen werden nicht als Euro gezählt.
* **Treffer-Logik**: „VERFÜGBAR" nur unter deiner Preisgrenze (700/800/900 €/offen),
  sonst „ZU TEUER"; Bot-Schutz und Fehler werden getrennt ausgewiesen.
* **Fairer Bot-Schutz:** 403/CAPTCHA wird erkannt und nicht wiederholt; 429
  respektiert `Retry-After` und wird höchstens einmal erneut versucht. Kein
  Captcha-Solver, keine Proxy-Rotation, kein JavaScript-Challenge-Bypass.
* **Preisverlauf**: Differenz zum letzten Scan pro Händler (`−20,00 €`, `STABIL`),
  Sparkline und 30-Tage-Tief auf jeder Trefferkarte.
* **Trefferqualität**: erkennt Zustand (neu/gebraucht), Verkäufer, Vorbestellung
  und Bot-Schutz. Gebrauchtware und Vorbestellungen lösen standardmäßig keinen
  Alarm aus; Details stehen beim langen Tippen auf einer Karte.
* **Shop-Health**: zeigt pro Händler den letzten Zustand, Fehlerzähler und
  Alter des letzten erfolgreichen Scans; auffällige Shops lassen sich einzeln
  erneut prüfen.
* **Remote-Konfiguration**: URL-Korrekturen und deklarative Parser-Regeln
  (Preis-Marker, Lieferstatus) werden über `shop_config.json` veröffentlicht
  und täglich geladen – ohne neues APK. Akzeptiert werden nur HTTPS-URLs auf
  bekannten Shop-Hosts und literale, begrenzte Marker; kein Code, keine Regexe.
* **Alarm-Regeln**: nur sofort verfügbar, nur echte Tiefstpreise, Ruhezeit
  23–07, eigene Preisgrenze und Händler-Stummschaltung. Ein Restock wird auch
  dann gemeldet, wenn der Preis gegenüber dem letzten Treffer unverändert ist.
* **Auto-Scan** im Intervall (5–60 min) und **Alarm** als Android-Benachrichtigung,
  sobald ein neuer Treffer auftaucht. Ein Tap öffnet direkt den Shop; mehrere
  Treffer eines Laufs werden gruppiert.
* **Hintergrund-Scan**: mit aktivem AUTO läuft der Scan als Foreground-Service
  weiter, wenn die App geschlossen oder das Display aus ist — inklusive Alarm.
  Im Hintergrund höchstens alle 15 Minuten, damit Akku und Datenvolumen tragen.
  Ein Heartbeat zeigt, wann zuletzt gescannt wurde; bleibt der Dienst wegen
  Akku-Optimierung stehen, warnt die App und verlinkt die Systemeinstellungen.
* **Neustart-fest**: Ist AUTO aktiv, startet der geschützte Foreground-Service
  nach einem Neustart oder App-Update automatisch wieder. Der Boot-Receiver
  prüft zuerst die lokale Einstellung und startet nur dann.
* **Kompakte Trefferliste**: Treffer erscheinen in allen Ansichten als vertikale
  Zeilen mit Preis und Status rechts; mehrere Treffer sind gleichzeitig sichtbar.
  Im Querformat ab 600 dp wandert die Liste an den rechten Rand, das Radar bleibt
  links. Dialoge sind in der Breite begrenzt; System-Insets werden berücksichtigt.
* **Abbruch**: der Scan-Button wird während eines Laufs zu **STOP**. STOP und
  App-Pause setzen ein Abbruchsignal; laufende Requests laufen höchstens noch
  bis zum Timeout, danach starten keine Retries oder weiteren Shops mehr.
* **Fortschritt**: die Kopfzeile zeigt kompakt `SCANNE 7/42 · 2 TREFFER ·
  REST ~70S`, ohne die Ergebnisliste zu verschieben.
* **Ressourcen-schonend:** das Radar zeichnet im Leerlauf 12 statt 30 Bilder/s und
  pausiert im Hintergrund, `requests` wird erst beim ersten Scan importiert. Der
  Scan nutzt ETag/Last-Modified (304 spart den Download) und bricht Antworten über
  5 MB ab; die Bot-Schutz-Prüfung liest nur die ersten 3 KB. Neue Cache-Einträge
  werden pro Scan einmal statt pro Shop geschrieben, und nach dem letzten
  Fehlversuch wartet der Retry nicht mehr unnötig.
* Filter (Treffer/alle), Sortierung (Preis/Händler/Zeit), Händler-Auswahl, kurzer
  Tap auf eine Karte öffnet den Shop im Browser.

## APK bauen

Der Build läuft auf Linux — zwei Wege ohne eigenen Linux-Rechner:

* **Google Colab:** [`PS5Pro_APK_Colab.ipynb`](PS5Pro_APK_Colab.ipynb) hochladen,
  `ps5pro.zip` einlesen, Zellen 1–6 ausführen.
* **GitHub Actions:** [`.github/workflows/build-apk.yml`](.github/workflows/build-apk.yml)
  baut bei jedem Push und legt die APK als Artifact ab. Schritt für Schritt:
  [GITHUB_ANLEITUNG.md](GITHUB_ANLEITUNG.md).

Die vollständige Anleitung inklusive Installation, Bedienung und Fehlerbehebung
steht in **[BUILD_ANDROID.md](BUILD_ANDROID.md)**. Für Google Play (targetSdk 36,
signiertes AAB, Keystore und Secrets) siehe **[PLAY_STORE.md](PLAY_STORE.md)**.

## Projektstruktur

```
main.py                       Oberfläche (Kivy) und App-Start
scan_core.py                  Scan-/Preis-/Speicherlogik ohne Kivy (auch im Service)
service.py                    Hintergrund-Scan als Android-Foreground-Service
buildozer.spec                Android-Build-Konfiguration
android_src/.../BootReceiver.java  startet den Service nach Neustart/App-Update
shop_config.json              Remote-Vorlage für URL-/Parser-Korrekturen (täglich geladen)
icon.png                      App-Icon (512×512)
assets/icon_fg.png            Adaptive-Icon Vordergrund (Android 8+)
assets/icon_bg.png            Adaptive-Icon Hintergrund
assets/notify_icon.png        Statusleisten-Icon des Hintergrund-Service
tools/selftest.py             Logiktests ohne Kivy (CI-Gate)
tools/kivy_smoke.py           echte Kivy-Popup-Smoke-Tests (CI-Gate)
tools/fixtures/               47 minimale Parser-Fixtures (42 Shops + Randfaelle)
tools/capture_fixture.py      Fixture aus einer echten Shop-Seite aufnehmen
tools/ci_build.sh             kompletter Build-Ablauf (CI und lokal, APK oder AAB)
tools/ci_check_apk.sh         prüft die fertige APK (Größe, Python-Version)
tools/ci_check_apk_aapt2.sh   prüft versionCode, versionName, targetSdk und foregroundServiceType
tools/ci_check_aab.sh         prüft das AAB (Struktur, Signatur, Python-Version)
PLAY_STORE.md                 Play-Release: Keystore, Secrets, AAB, Play Console
tools/ci_licenses.sh          akzeptiert die Android-SDK-Lizenzen
tools/ci_fix_cache.sh         räumt halb geladene SDK/NDK-Bäume auf
PS5Pro_APK_Colab.ipynb        Build-Notebook für Colab
GITHUB_ANLEITUNG.md           Build über GitHub Actions (Web-Upload und CLI)
.github/workflows/build-apk.yml   CI-Build
.github/workflows/release.yml     Tag v* -> APK als Release-Asset
.github/workflows/diagnose.yml    manueller Diagnose-Lauf
LICENSE                       MIT-Lizenz
THIRD_PARTY_NOTICES.md        Lizenzen der gebündelten Bibliotheken
ps5pro.zip                    Upload-Paket für Colab
```

## Tests

```
python3 tools/selftest.py
python3 tools/kivy_smoke.py
```

Prüft Preis-Parsing, JSON-LD, Verfügbarkeit, Bot-Schutz-Erkennung, Klassifizierung,
HTTP-Cache, Preisverlauf, Alarm-Regeln, Shop-Health, Remote-Config inklusive
Parser-Regeln, responsive Layout-Geometrie und Boot-Manifest — 572 Zusicherungen,
ohne Kivy und ohne Android. Der Workflow führt sie vor jedem Build aus. Der Kivy-Smoke-Test ist ebenfalls
ein eigenes CI-Gate und braucht kein Android-Gerät.

`tools/kivy_smoke.py` öffnet die Popups **Alarm-Regeln**, **Shop-Health** und
**Detailansicht** mit echtem Kivy, prüft Inhalt und Größe und klickt die
wichtigsten Schaltflächen durch. Er nutzt ein temporäres Datenverzeichnis und
ersetzt alle Netzwerk-, Benachrichtigungs- und Browser-Aufrufe. Auf Linux ohne
Display läuft er über Xvfb:

```bash
xvfb-run -a python3 tools/kivy_smoke.py
```

## Fixtures vor dem Release

Für jeden der 42 Shops liegt eine kleine Fixture in `tools/fixtures/`; die
Suite prüft damit Preis, Produkt, Zustand, Verfügbarkeit und Lieferstatus,
ohne eine Shop-Seite zu laden. Zusätzlich decken die Fixtures JSON-LD, Meta-Tags,
Text-Fallback, Vorbestellung, Gebrauchtware und Ausverkauf ab. Fehlt ein Shop
oder ändert sich ein Parser unerwartet, schlägt `tools/selftest.py` vor dem
Build fehl.

Die eingecheckten Fixtures sind bewusst kleine, lizenzfreie Vertragsausschnitte.
Eine echte Seite lässt sich jederzeit manuell aufnehmen:

```bash
python3 tools/capture_fixture.py --shop "Amazon DE"
python3 tools/capture_fixture.py --shop "Amazon DE" --input page.html
python3 tools/capture_fixture.py --all --force
python3 tools/capture_fixture.py --check
```

Der Helfer nutzt denselben `scan_core`-Pfad, speichert keine dauerhafte
HTTP-Cache-Datei des Nutzers und reduziert die Seite auf Titel, relevante
Meta-Tags, JSON-LD sowie Text-/Attribut-Ausschnitte. Er lehnt fremde Hosts und
Bot-Challenges ab. `--input` arbeitet offline; `--full` ist der Notausgang, wenn
eine echte Seite durch die Minimierung anders geparst würde. Die CI führt den
Helfer nicht aus und braucht keinen Shop-Zugriff.

## Versionen

* **v5.0 Final** – Das aufgeräumte Gesamtsystem (versionCode 17): Das Radar
  zeigt jetzt ein ruhiges HUD mit Scan-Fortschritt, Zielmarken für Treffer,
  Sonar-Pings und einem `TARGET · 2 TB`-Status. Die Trefferliste bekommt einen
  Metall-Verlauf, eine cyanfarbene `BEST`-Markierung für den günstigsten Treffer
  und eine feinere Statuskante. `SETUP` öffnet eine zentrale Systemkonfiguration
  für Scan, Alarme, Preisgrenze, Sortierung, Händler, Regeln und Shop-Health.
  Enthält v4.0 Beta 2, den v3.3.2-Layout-Fix und alle älteren Parser-, Alarm-
  und Hintergrunddienste. 572 Zusicherungen.
* **v4.0 Beta 2** – Länderflagge in der Trefferliste (versionCode 15): Die
  Flagge steht klein in der Meta-Zeile vor `DE · 12:00` und zeigt die Herkunft
  des Treffers; vor dem Händlernamen bleibt die Zeile symbolfrei. Keine
  Händler-Kachel und keine Pfeil-Buttons mehr vor der Liste; der Händlername
  bekommt die freie Breite. Der BOT-SCHUTZ-Hinweis ist mit 8,2 sp lesbarer und
  bleibt auf 246 dp vollständig sichtbar.
* **v4.0 Beta** – Aufgeräumte Trefferliste (versionCode 14): keine Händler-Kachel
  und keine Pfeil-Buttons mehr vor der Liste; der Händlername bekommt die freie
  Breite. Der BOT-SCHUTZ-Hinweis ist mit 8,2 sp lesbarer und bleibt auf 246 dp
  vollständig sichtbar. Vordergrund und Hintergrund nutzen dieselbe Alarmlogik:
  Wieder-Verfügbarkeit wird auch bei gleichem Preis gemeldet, Preiserhöhungen
  lösen keinen Alarm aus. Der Preisverlauf speichert jetzt alle plausiblen
  Preise und die Verfuegbarkeit. 572 Zusicherungen. Enthält v3.3.1.
* **v3.3.1** – Layout-Patch (versionCode 13): Der BOT-SCHUTZ-Hinweis steht
  auf einer eigenen vollbreiten Zeile und bleibt auch auf schmalen Displays
  vollständig sichtbar; die breitere Preisspalte verhindert abgeschnittene
  Beträge wie `1.299,00 €`. Enthält den vollständigen Stand aus v3.3.
* **v3.3** – Kompakte Trefferliste (versionCode 12): vertikale Zeilen statt
  breiter Karten, dadurch mehrere Treffer gleichzeitig sichtbar; Preis, Status
  und Preisänderung stehen rechts. Der BOT-SCHUTZ-Hinweis bleibt sichtbar.
  Benachrichtigungen laufen außerhalb des UI-Threads, und der Karten-Neubau am
  Scan-Ende wird entzerrt, damit das Radar bei Treffern flüssiger bleibt.
  Enthält den vollständigen Stand aus v3.2.
* **v3.2** – Robustere Treffer (versionCode 11): verschachtelte JSON-LD-Angebote,
  Angebotslisten mit „neu vor gebraucht“, Meta-/Microdata-Preise, Punkt-Dezimalpreise
  und Meta-Verfügbarkeit. Enthält den vollständigen Stand aus v3.1.
* **v3.1** – Fairer Scan (versionCode 10): 429 wartet gemäß `Retry-After` und
  wird höchstens einmal wiederholt; 403/CAPTCHA wird ohne weitere Versuche als
  Bot-Schutz gemeldet. Enthält den vollständigen Stand aus v3.0.
* **v3.0** – Finaler Feinschliff (versionCode 9): STOP und App-Pause brechen
  laufende Retry-Schleifen kooperativ ab; die Kopfzeile zeigt Fortschritt und
  eine geschätzte Restzeit. Enthält den vollständigen Stand aus v2.0.
* **v2.0** – Vorheriger Abschluss-Release (versionCode 8); enthält den
  vollständigen Stand aus v1.6.
* **v1.6** – Effizienterer Scan: HTTP-Cache wird einmal pro Lauf statt pro
  Shop geschrieben, und der letzte fehlgeschlagene Versuch wartet nicht mehr
  unnötig (versionCode 7).
* **v1.5** – Sicher validierte Remote-Konfiguration für Shop-URLs und
  deklarative Parser-Regeln (versionCode 6).
* **v1.4** – Boot-Receiver für den Hintergrund-Service und adaptives
  Querformat-Layout für Tablets/Foldables (versionCode 5).
* **v1.3** – Remote-Shop-Liste, Onboarding und tägliche URL-Aktualisierung
  (versionCode 4).
* **v1.2** – Shop-Health, Fixtures, Treffer-Metadaten (Zustand/Verkäufer/
  Vorbestellung), Alarm-Regeln, Detailansicht und Crash-Log (versionCode 3).
* **v1.1** – HTTP-Cache/304, Preisverlauf mit Sparkline, Heartbeat-Warnung,
  Notification-Deep-Links und Gruppierung (versionCode 2).
* **v1.0** – erster Play-vorbereiteter Build (targetSdk 36, signierbares AAB);
  bleibt als eigenes Release erhalten.

## Grenzen

* Hintergrund-Scans können von OEM-Akku-Managern beendet werden; der Boot-Receiver
  startet nach Neustart/Update nur, wenn AUTO aktiv ist. Der Heartbeat zeigt,
  ob der Dienst tatsächlich läuft, und verlinkt die Systemeinstellungen.
* Der Boot-Start erfolgt erst nach dem Entsperren (kein Direct-Boot-Zugriff auf
  die Einstellungen). Nach einem vom Nutzer erzwungenen Stopp startet Android
  den Receiver erst wieder nach dem nächsten manuellen Öffnen der App.
* Shops ändern URLs und verschärfen Bot-Schutz. Einzelne Händler können dauerhaft
  „BOT-SCHUTZ" melden — dann hilft eine neue URL oder eine Parser-Regel in der
  Remote-Datei `shop_config.json`.

## Shop-URLs und Parser-Regeln ohne APK aktualisieren

`shop_config.json` wird aus dem `main`-Branch geladen und vor dem Anwenden
vollständig validiert. Ein einziger Fehler verwirft die ganze Datei; dann bleibt
die zuletzt gültige bzw. die eingebaute Konfiguration aktiv.

```json
{
  "schema": 1,
  "updated": "2026-11-12",
  "shops": {
    "MediaMarkt DE": {
      "urls": ["https://www.mediamarkt.de/de/product/_sony-playstationr5-pro-2-tb-konsole-3018022.html"],
      "parser": {
        "price_before": "data-ps5-price=\"",
        "price_after": "\"",
        "in_stock": ["Auf Lager"],
        "out_of_stock": ["Ausverkauft"],
        "preorder": ["Vorbestellung"],
        "immediate": ["Sofort lieferbar"]
      }
    }
  }
}
```

**URLs:** nur absolute HTTPS-URLs auf Hosts der eingebauten Händlerliste,
höchstens 3 pro Shop, ohne Zugangsdaten, ohne Port außer 443 und ohne Fragment.
Doppelte URLs und unbekannte Shops werden abgelehnt.

**Parser-Regeln:** `price_before` und `price_after` bilden ein Paar aus exakten,
literalen Markern; dazwischen läuft der vorhandene Preisparser. `in_stock`,
`out_of_stock`, `preorder` und `immediate` sind Listen literaler Textmarker
(maximal 8 pro Feld, 120 Zeichen pro Marker); sie werden ohne Beachtung der
Groß-/Kleinschreibung gesucht, `out_of_stock` gewinnt konservativ. Es gibt
bewusst **keine freien Regexe und keinen ausführbaren Code** aus der Remote-Datei
— damit sind ReDoS und Code-Injektion ausgeschlossen. Preis- und Lieferregeln
haben Vorrang vor JSON-LD/Meta/Text, fallen bei fehlendem Treffer aber sauber
zurück. Bei einer Regeländerung wird der alte HTTP-Cache des betroffenen Shops
verworfen, damit ein 304 nicht den alten Preis konserviert.

App und Hintergrund-Service laden höchstens einmal pro Tag und nutzen ETag/304.
Der Button **SHOPS → REMOTE-CONFIG AKTUALISIEREN** erzwingt einen Abruf.
APKs bis v1.4 ignorieren zusätzliche `parser`-Felder, solange `urls` vorhanden
ist; damit ältere Clients die Datei weiterhin akzeptieren, sollte ein Eintrag
mit Parser-Regel auch `urls` enthalten.
* Debug-APK zum Sideloading; für den Play Store ist ein signierter AAB-Build nötig.

## Lizenz

MIT — siehe [LICENSE](LICENSE). Du darfst die App frei nutzen, verändern und
weitergeben, solange der Copyright- und Lizenzhinweis erhalten bleibt.

Die APK bündelt zusätzlich Kivy, python-for-android und weitere
Open-Source-Bibliotheken. Deren Lizenzen (MIT, BSD-3-Clause, Apache-2.0,
MPL-2.0, PSF-2.0 u. a.) stehen mit Copyright-Hinweisen in
**[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**; die MIT-Lizenz hier
betrifft nur den Projektcode.
