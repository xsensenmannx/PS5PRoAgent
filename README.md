# PS5 Pro Search Agent

Android-App (Kivy/Python), die 42 Elektronikhändler in Deutschland und Österreich
gleichzeitig nach der **PlayStation 5 Pro 2 TB** abfragt: Preis, Verfügbarkeit,
Preisänderung gegenüber dem letzten Scan — als Radar im PS1-BIOS-Look.

![Icon](icon.png)

## Was die App kann

* **Parallel-Scan** über 42 Shops (DE + AT) mit 6 Threads, Retry und wechselnden
  User-Agents.
* **Preis-Erkennung** über JSON-LD (`schema.org/Product`), Meta-Tags und Text-Fallback —
  inklusive Filter gegen Zubehör (DualSense Edge, Portal, Laufwerk …) und gegen alles,
  was nicht die 2-TB-Konsole ist.
* **Treffer-Logik**: „VERFÜGBAR" nur unter deiner Preisgrenze (700/800/900 €/offen),
  sonst „ZU TEUER"; Bot-Schutz und Fehler werden getrennt ausgewiesen.
* **Preisverlauf**: Differenz zum letzten Scan pro Händler (`−20,00 €`, `STABIL`).
* **Auto-Scan** im Intervall (5–60 min) und **Alarm** als Android-Benachrichtigung,
  sobald ein neuer Treffer auftaucht.
* **Abbruch**: der Scan-Button wird während eines Laufs zu **STOP**.
* Filter (Treffer/alle), Sortierung (Preis/Händler/Zeit), Händler-Auswahl, kurzer
  Tap auf eine Karte öffnet den Shop im Browser.

## APK bauen

Der Build läuft auf Linux — zwei Wege ohne eigenen Linux-Rechner:

* **Google Colab:** [`PS5Pro_APK_Colab.ipynb`](PS5Pro_APK_Colab.ipynb) hochladen,
  `ps5pro.zip` einlesen, Zellen 1–6 ausführen.
* **GitHub Actions:** [`.github/workflows/build-apk.yml`](.github/workflows/build-apk.yml)
  baut bei jedem Push und legt die APK als Artifact ab. Schritt für Schritt:
  [GITHUB_ANLEITUNG.md](GITHUB_ANLEITUNG.md).

Die vollständige Anleitung inklusive Installation, Bedienung, Fehlerbehebung und
Play-Store-Release steht in **[BUILD_ANDROID.md](BUILD_ANDROID.md)**.

## Projektstruktur

```
main.py                       komplette App (UI + Scanner)
buildozer.spec                Android-Build-Konfiguration
icon.png                      App-Icon (512×512)
assets/icon_fg.png            Adaptive-Icon Vordergrund (Android 8+)
assets/icon_bg.png            Adaptive-Icon Hintergrund
tools/selftest.py             Logiktests ohne Kivy (CI-Gate)
tools/ci_build.sh             kompletter Build-Ablauf (CI und lokal)
tools/ci_check_apk.sh         prüft die fertige APK (Größe, Python-Version)
tools/ci_licenses.sh          akzeptiert die Android-SDK-Lizenzen
tools/ci_fix_cache.sh         räumt halb geladene SDK/NDK-Bäume auf
PS5Pro_APK_Colab.ipynb        Build-Notebook für Colab
GITHUB_ANLEITUNG.md           Build über GitHub Actions (Web-Upload und CLI)
.github/workflows/build-apk.yml   CI-Build
.github/workflows/release.yml     Tag v* -> APK als Release-Asset
.github/workflows/diagnose.yml    manueller Diagnose-Lauf
ps5pro.zip                    Upload-Paket für Colab
```

## Tests

```
python3 tools/selftest.py
```

Prüft Preis-Parsing, JSON-LD, Verfügbarkeit, Bot-Schutz-Erkennung, Klassifizierung und
die Händlerdaten — 46 Zusicherungen, ohne Kivy und ohne Android. Der Workflow führt sie
vor jedem Build aus.

## Grenzen

* Hintergrund-Scans bei gesperrtem Bildschirm sind nicht garantiert (kein
  Foreground-Service); `AUTO` läuft zuverlässig im Vordergrund.
* Shops ändern URLs und verschärfen Bot-Schutz. Einzelne Händler können dauerhaft
  „BOT-SCHUTZ" melden — dann hilft nur eine neue URL in `HAENDLER`.
* Debug-APK zum Sideloading; für den Play Store ist ein signierter AAB-Build nötig.
