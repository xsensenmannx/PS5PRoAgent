# PS5 Pro Search Agent — Anleitung von A bis Z

Diese Anleitung führt von „nichts installiert" bis „App läuft auf dem Handy". Sie
enthält drei Build-Wege (einer genügt), die Installation, die Bedienung und eine
Fehlerbehebung, die auf den tatsächlichen Fehlermeldungen dieser Toolchain basiert.

---

## 0. Was hier gebaut wird

`main.py` ist eine Kivy-App, die 42 Händler in DE und AT gleichzeitig nach der
PlayStation 5 Pro 2 TB abfragt. Der Build verpackt Python 3.11, Kivy und den Code in
eine APK — das passiert mit **Buildozer** (python-for-android) und **nur auf Linux**.
Deshalb die drei Wege: Colab und GitHub Actions stellen das Linux, Weg C nutzt dein
eigenes.

| Datei | Zweck |
| --- | --- |
| `main.py` | die komplette App (UI, Radar, Scanner) |
| `buildozer.spec` | Build-Konfiguration (API, NDK, Icon, Rechte) |
| `icon.png` | Launcher-Icon (512×512, Legacy) |
| `assets/icon_fg.png`, `assets/icon_bg.png` | Adaptive Icon für Android 8+ |
| `tools/selftest.py` | Logiktests ohne Kivy (67 Zusicherungen) |
| `tools/ci_build.sh` | kompletter Build-Ablauf für Linux/CI (auch lokal: `bash tools/ci_build.sh`) |
| `tools/ci_licenses.sh` | akzeptiert die Android-SDK-Lizenzen in einem fertig installierten SDK |
| `tools/ci_fix_cache.sh` | entfernt halb geladene SDK/NDK-Bäume (sonst überspringt buildozer die Installation) |
| `tools/ci_check_apk.sh` | prüft die fertige APK (Größe, enthält `libpython3.11.so`) |
| `tools/ci_log_failure.sh` | holt die erste echte Fehlerstelle aus `buildozer.log` (für die Job-Zusammenfassung) |
| `PS5Pro_APK_Colab.ipynb` | Build-Notebook für Colab |
| `.github/workflows/build-apk.yml` | CI-Build mit Artifact |
| `.github/workflows/release.yml` | bei Tag `v*`: Build + APK als Release-Asset |
| `.github/workflows/diagnose.yml` | manueller Diagnose-Lauf (SDK/NDK, venv, letzter Fehler) |
| `ps5pro.zip` | Upload-Paket für Colab (main.py, scan_core.py, service.py, spec, icons, `assets/`) |
| `GITHUB_ANLEITUNG.md` | Build über GitHub Actions, Schritt für Schritt |
| `.gitignore` | hält `.buildozer/`, `bin/` und Caches aus dem Repo |

---

## 1. Weg A — Google Colab (schnellster Start, kein Konto nötig außer Google)

1. <https://colab.research.google.com> öffnen → **Datei → Notebook hochladen** →
   `PS5Pro_APK_Colab.ipynb` auswählen.
2. Zelle 1 ausführen (`▶` links, oder `Strg+Enter`): installiert Autotools und JDK.
   Erwartete Ausgabe: eine `java version`-Zeile.
3. Zelle 2: legt mit `uv` eine **Python-3.11.9-Umgebung** an und installiert Buildozer.
   Die Version ist nicht beliebig: p4a verlangt Host-Python == Ziel-Python (3.11.9).
   Erwartete Ausgabe: `Buildozer 1.6.x`. Das dauert 1–3 Minuten.
4. Zelle 3: ZIP auswählen → `ps5pro.zip` aus dem Projekt hochladen. Erwartete Ausgabe:
   `Projekt entpackt nach: /content/ps5pro` mit `['assets', 'buildozer.spec', 'icon.png', 'main.py']`.
5. Zelle 4 (optional): `USE_CACHE = True` setzen, wenn du Google Drive nutzen willst —
   dann liegt der Build-Cache dort und jeder weitere Lauf dauert Minuten statt ~30.
   **Beim ersten Lauf nach einem Toolchain-Wechsel auf `False` lassen.**
6. Zelle 5: baut die APK. 10–40 Minuten, je nach Cache. Zeilen mit
   `[INFO]: Building ...` sind normal; am Ende steht `Exit-Code: 0` und ein Pfad
   `bin/ps5prosearchagent-1.0-arm64-v8a-debug.apk`.
7. Zelle 6: lädt die APK herunter.

**Wenn Colab die Sitzung trennt** (Inaktivität, Verbindungsabbruch, 12-Stunden-Limit):
neu verbinden, Zelle 1–3 erneut ausführen (bei aktivem Drive-Cache reicht 1–2), dann
Zelle 5 und 6. Ein halb fertiger `.buildozer`-Ordner ohne Cache-Zelle wird bei Zelle 3
komplett ersetzt — das ist so gewollt.

---

## 2. Weg B — GitHub Actions (empfohlen für Wiederholbarkeit)

Die ausführliche Schritt-für-Schritt-Anleitung — inklusive Hochladen ohne Kommandozeile —
steht in **[GITHUB_ANLEITUNG.md](GITHUB_ANLEITUNG.md)**. Die Kurzfassung:

Voraussetzung: ein GitHub-Repository mit diesem Projekt.

```bash
git init
git add .
git commit -m "PS5 Pro Search Agent"
git branch -M main
git remote add origin https://github.com/<dein-name>/<dein-repo>.git
git push -u origin main
```

Danach passiert eines von zwei Dingen:

* Der Push auf `main` startet den Workflow automatisch (Pfadfilter: `main.py`,
  `buildozer.spec`, `icon.png`, `assets/**`, `tools/**`, der Workflow selbst).
* Oder manuell: **Actions → APK bauen → Run workflow**.

Nach 15–40 Minuten (erster Lauf; danach deutlich kürzer dank Cache) liegt die APK unter
**Actions → der Lauf → Artifacts → `ps5pro-apk`**. Das ZIP enthält die `.apk`.
Scheitert der Build, lädt derselbe Lauf `buildozer-log` hoch — dort steht die Ursache.

Vor dem Build laufen die **Logiktests** (`tools/selftest.py`) als Gate: schlägt einer
fehl, wird gar nicht erst gebaut.

---

## 3. Weg C — lokal unter Linux, WSL oder Docker

Nur nötig, wenn du ohnehin Linux hast (Windows: WSL2 mit Ubuntu 22.04/24.04).

Am einfachsten mit dem Skript, das auch der CI-Workflow benutzt — es prüft die
Pflichtdateien, installiert die Pakete, legt das venv an, akzeptiert die SDK-Lizenzen
und baut:

```bash
bash tools/ci_build.sh
```

Oder von Hand:

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip \
    autoconf libtool pkg-config zlib1g-dev libncurses-dev libffi-dev \
    libssl-dev cmake ccache
pip install --user "buildozer" "cython==0.29.37" legacy-cgi
buildozer android debug
```

Mit Docker bleibt das System unberührt:

```bash
docker run --rm -v "$PWD":/home/user/hostcwd kivy/buildozer android debug
```

Die APK landet in `bin/`. Wichtig: Das Host-Python im venv muss **exakt** der Version des
p4a-Rezepts `python3` entsprechen (derzeit 3.11.9). Mit einem neueren Host bricht der Build
mit `python3 should have same version as hostpython3, 3.11.9 != 3.14.2` ab — dann
`uv venv --python 3.11.9` benutzen, wie im Notebook und in `tools/ci_build.sh`.

---

## 4. APK installieren

1. APK per Kabel, Cloud oder Messenger aufs Handy bringen (nicht per Mail-Anhang
   umbenennen lassen — der Dateiname muss auf `.apk` enden).
2. Datei antippen → Android fragt nach der Erlaubnis für „Unbekannte Apps" →
   **Einstellungen → Installation aus dieser Quelle erlauben** (der Dialog führt direkt
   dorthin).
3. Play Protect meldet eventuell „App wurde nicht geprüft" → **Mehr Details →
   Trotzdem installieren**. Das ist bei selbst signierten Debug-APKs normal.
4. Alternativ per Kabel: `adb install -r bin/ps5prosearchagent-*-debug.apk`

Beim ersten Start fragt die App nach Netzwerk-, Vibrations- und
Benachrichtigungs-Rechten. **Alle drei erlauben** — ohne Benachrichtigungs-Recht
(Android 13+) kommt kein Alarm an, ohne das Netzwerk-Recht kein Scan.

**Update:** neue APK über die alte installieren (`adb install -r` bzw. Datei antippen).
Die App-Daten (Verlauf, Einstellungen) bleiben erhalten, solange der Paketname
`de.ps5pro.ps5prosearchagent` gleich bleibt.

---

## 5. Erster Start — Checkliste

1. Kopfzeile zeigt „PLAYSTATION 5 PRO / SEARCH AGENT", darunter das Radar.
2. **SCAN** drücken. Der Button wird zu **STOP**, oben läuft `SCANNE 7/42`.
   Ein voller Lauf dauert je nach Netz 1–4 Minuten.
3. Treffer erscheinen als Karten, sortiert nach Preis; die Farbe links ist der Status
   (grün = verfügbar, gelb = zu teuer, grau = nicht verfügbar, rot = Fehler).
4. Tap auf eine Karte öffnet den Shop im Browser.
5. Chip **MAX 900 €** zykelt durch 700/800/900/offen — „ZU TEUER" wird sofort neu
   bewertet, ohne neuen Scan.
6. Chip **TREFFER/ALLE** filtert; **SORT** wechselt Preis/Händler/Zeit.
7. **HÄNDLER 42** öffnet die Auswahl (ALLE/KEINE/DE/AT). Die Auswahl wird gespeichert.
8. **AUTO** startet den Intervall-Scan (5–60 min über den Chip daneben), **ALARM**
   schaltet die Benachrichtigung bei neuen Treffern.

---

## 6. Fehlerbehebung

| Meldung / Symptom | Ursache | Lösung |
| --- | --- | --- |
| `Buildozer failed to execute the last command` | irgendein Schritt | Immer den Block davor lesen: `/content/buildozer.log` bzw. das Artifact `buildozer-log`. Die letzte `Command failed`-Zeile nennt den echten Fehler. |
| `No module named 'distutils'` / `pkg_resources` | zu neues Host-Python | venv mit 3.11.9 anlegen (`uv venv --python 3.11.9`), `setuptools` installieren. |
| `python3 should have same version as hostpython3` | Host-Python ≠ Ziel-Python | venv mit der Rezeptversion anlegen: `uv venv --python 3.11.9` (Zelle 2 / `tools/ci_build.sh`). |
| Fehler in `Cython.Compiler…` | Cython 3 statt 0.29 | `cython==0.29.37` installieren, `.buildozer` löschen. |
| Abbruch mitten im Kivy-Build, im Log `window_info.c` und `_PyLong_AsByteArray` | p4a baut ohne Pin CPython 3.14.2; Cython 0.29 kann nur bis 3.12 | `requirements` in `buildozer.spec` pinnt `python3==3.11.9, hostpython3==3.11.9`; `tools/ci_fix_cache.sh` setzt das auch im p4a-Checkout durch und verwirft alte python3-Builds. |
| `incompatible function pointer types` in `cgl_gl.c`, danach `Backend subprocess exited when trying to invoke build_wheel` | clang 20 aus NDK 28c wertet den alten `glShaderSource`-Prototyp aus Kivy 2.3.0 (`const GLchar**` statt `const GLchar* const *`) als Fehler | `kivy==2.3.1` in `requirements` – behebt die Signatur und castet `SDL_SetEventFilter` korrekt. Danach `buildozer android clean` bzw. `.buildozer` löschen. |
| `Can not perform a '--user' install` | Buildozer erkennt das venv nicht und ruft `pip install --user` auf | `VIRTUAL_ENV` setzen oder das venv aktivieren — Zelle 5 im Notebook und der Actions-Workflow tun das bereits. |
| `No module named pip` | venv ohne pip (z. B. frisches `uv venv`) | `uv pip install --python <venv>/bin/python pip` (Zelle 2 erledigt das). |
| `Aidl not found` | fehlendes Build-Tool | `sudo apt install aidl` (oder `android-sdk-build-tools`). |
| `SDK license not accepted` | Lizenz | In der Spec steht `android.accept_sdk_license = True`; danach `buildozer android clean`. |
| Lauf bleibt beim Lizenztext stehen (`License android-sdk-license:`) | `sdkmanager` wartet auf eine Eingabe | Buildozer beantwortet das selbst (`android.accept_sdk_license = True`); `bash tools/ci_licenses.sh` hinterlegt die Lizenzen zusätzlich. Sonst Lauf abbrechen, `.buildozer`-Cache löschen, neu starten. |
| `sdkmanager does not exist, sdkmanager is not installed` | halb geladenes SDK: buildozer prüft nur, ob der Ordner existiert, und überspringt dann die Installation | `bash tools/ci_fix_cache.sh` (läuft automatisch in `tools/ci_build.sh`) entfernt den kaputten Baum; danach neu bauen. |
| `Unable to find recommended Android NDK` | alte p4a-Kopie | `rm -rf .buildozer` und Cache verwerfen, neu bauen. |
| Build bricht nach NDK-/API-Wechsel | alter Cache | `buildozer android clean`, `rm -rf .buildozer bin`, Drive-Cache bzw. Actions-Cache löschen. |
| APK installiert nicht („App nicht installiert") | anderer Schlüssel/ältere Version | Alte App deinstallieren oder `adb install -r` mit gleichem Paketnamen. |
| App startet und zeigt „Startup Error" | Python-Ausnahme beim Start | Text im Fenster lesen; dieselbe Ursache steht in `adb logcat | grep python`. |
| Alle Händler „BOT-SCHUTZ" | Cloudflare & Co. blocken | In der App normal; einzelne Händler über die Händler-Auswahl abwählen. Neue URL in `HAENDLER` hilft, wenn ein Shop umgezogen ist. |
| Alle Händler „FEHLER" | kein Netz / DNS / TLS | WLAN/Mobilfunk prüfen; `PS5_PROXY` ist nicht gesetzt (kein Proxy nötig). |
| Alarm kommt nicht | Benachrichtigungs-Recht fehlt | Einstellungen → Apps → PS5 Pro → Benachrichtigungen erlauben. |
| Scan wirkt eingefroren | Netz hängt bei einem Shop | **STOP** drücken: Teilauswertung bleibt stehen, nächster Scan startet sauber. |

---

## 7. Was in der `buildozer.spec` warum so steht

| Einstellung | Wert | Grund |
| --- | --- | --- |
| `android.api` / `android.minapi` | 34 / 24 | Ab targetSdk 35 erzwingt Android Edge-to-Edge; Kivy 2.3 zeichnet dann unter Status- und Navigationsleiste, bei 36 ist der Opt-out entfernt. 34 hält Fullscreen intakt, läuft ab Android 7.0. |
| `android.ndk` / `android.ndk_api` | 28c / 24 | Aktuelle p4a-Empfehlung, inkl. 16-KB-Page-Support für Android 15+. |
| `p4a.branch` | `master` | Dessen `python3`-Rezept ist 3.14.2; der Pin in `requirements` setzt 3.11.9 durch. |
| `icon.filename` | `icon.png` | Legacy-Icon (Android 7 und Fallback). |
| `icon.adaptive_*` | `assets/icon_fg.png`, `assets/icon_bg.png` | Android 8+ maskiert das Icon (Kreis/Squircle); ohne Adaptive-Variante wird das Logo verkleinert in eine weiße Fläche gesetzt. |
| `fullscreen` | `1` | Konsolen-Look, keine Titelleiste. |
| `android.display_cutout` | `never` | Inhalt bleibt aus der Notch-Region. |
| `android.presplash_color` | `#04080a` | Kein weißes Aufblitzen beim Start. |
| `android.accept_sdk_license` | `True` | Keine interaktive Lizenzabfrage in Colab/CI. |
| `android.archs` | `arm64-v8a` | Alle aktuellen Geräte sind 64-Bit; der 32-Bit-Pfad verdoppelte die Bauzeit und war die häufigste Fehlerquelle. Für alte Geräte `, armeabi-v7a` ergänzen. |
| `android.permissions` | INTERNET, VIBRATE, POST_NOTIFICATIONS | Scan, haptisches Feedback, Alarm. |
| `source.exclude_*` | `.buildozer, bin, __pycache__, _verify, .github, .git, .venv, fonts, tools`; `ps5pro.zip, ps5pro_settings.json, ps5pro_history.json, *.ipynb, *.md, *.log` | Doku, Git-Historie, lokale App-Daten, Build-Werkzeuge und Upload-Paket landen nicht in der APK. |

---

## 8. Release für den Play Store (optional)

Nur nötig, wenn die App in den Store soll. Sideloading braucht das nicht.

1. Keystore erzeugen:
   ```bash
   keytool -genkey -v -keystore ps5pro.keystore -alias ps5pro \
       -keyalg RSA -keysize 2048 -validity 10000
   ```
2. In der `buildozer.spec`: `android.release_artifact = aab` und
   `android.api = 35` (Play verlangt mindestens 35). Damit greift Edge-to-Edge — die
   Kopf- und Fußleiste brauchen dann zusätzlichen Abstand, sonst liegen sie unter
   Systemleisten.
3. Signiert bauen:
   ```bash
   export P4A_RELEASE_KEYSTORE=$PWD/ps5pro.keystore
   export P4A_RELEASE_KEYSTORE_PASSWD=...
   export P4A_RELEASE_KEYALIAS=ps5pro
   export P4A_RELEASE_KEYALIAS_PASSWD=...
   buildozer android release
   ```
4. `bin/*.aab` im Play Console hochladen. Keystore und Passwörter niemals committen.

---

## 9. Wartung

* **URL-Rot:** Shops ändern Produktpfade. Ein Händler, der dauerhaft „nicht PS5 Pro 2 TB"
  meldet, hat meist eine neue URL — in `HAENDLER` in `main.py` anpassen.
* **Bot-Schutz:** Die App nutzt normale Browser-Header und Retries. Härtere Sperren
  (Cloudflare „Just a moment") lassen sich ohne Browser-Engine nicht umgehen; solche
  Shops bleiben gelb. Das ist bewusst so, statt an Captchas vorbeizuarbeiten.
* **Nach Änderungen an `main.py`:** Keystore/API unverändert lassen, dann
  `buildozer android debug` — es wird nur der Python-Teil neu gepackt (schnell).
* **Tests vor jedem Build:** `python3 tools/selftest.py` (im CI automatisch).

---

## 10. Was geprüft ist — und was nicht

**Geprüft in dieser Umgebung** (Windows ohne Java/SDK, daher ohne echten Build):

* `main.py` kompiliert fehlerfrei (CPython 3.12.10).
* `tools/selftest.py`: 67 Zusicherungen grün (CPython 3.12.10) — Preis-Parsing
  (`1.299,00 €`, `799,99`, `EUR 1.199,00`), JSON-LD `InStock`/`OutOfStock`,
  Zubehör-Ausschluss („DualSense Edge"), Meta-Preis-Fallback, Bot-Schutz-Erkennung,
  Verfügbarkeits-Heuristik, Klassifizierung, Kürzel, 42 eindeutige Händler-URLs und der
  Python-Pin in der `buildozer.spec`.
* Alle Shell-Skripte (`bash -n`) und alle drei Workflow-YAMLs sind syntaktisch gültig.
* Optimierungen gemessen (CPython 3.12.10, synthetische 5-MB-Shopseite): Bot-Schutz-Prüfung
  3,27 ms → 0,006 ms (nur noch 3 KB statt der ganzen Seite kleingeschrieben),
  Produkt-/Verfügbarkeitsprüfung 136 ms → 120 ms. Ein kombinierter Produkt-Regex war in
  der Messung 3,5× langsamer (154 ms) und wurde deshalb verworfen.
* Radar-Bildrate als reine Funktion `radar_frame_step()` abgesichert: 12 Bilder/s im
  Leerlauf, 30 beim Scan, Pause zeichnet nie, und die gezeichnete Bewegungszeit bleibt
  pro Sekunde exakt 1,0 s (der Sweep läuft dadurch bei beiden Bildraten gleich schnell).
* `buildozer.spec` parst (API 34, NDK 28c, minapi 24, p4a master), Notebook-JSON valide.
* Icon-Assets: 432×432, korrekte Modi, mit der echten Adaptive-Icon-Maske (72 von
  108 dp) auf Kreis und Squircle geprüft. Der vollflächig deckende Vordergrund ist
  gewollt: sein Rahmen liegt außerhalb der Maske, sichtbar bleibt das Radar.

**Nicht geprüft:** der Android-Build selbst und die App auf realer Hardware. Der erste
echte Test ist der Lauf in Colab/Actions. Dort bitte gezielt prüfen: Start ohne Absturz,
kompletter Scan, **STOP** während eines Laufs, Händler-Auswahl, Alarm, und die Ansicht
auf einem kleinen (720×1280) sowie einem großen Gerät.
