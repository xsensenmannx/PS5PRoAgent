# GitHub-Anleitung — APK automatisch bauen lassen

Diese Anleitung ist die Alternative zu Colab. Ergebnis: GitHub baut die APK auf einem
Ubuntu-Rechner, du lädst sie als ZIP herunter. Kein Warten im Browser-Tab, kein manuelles
Hochladen eines ZIPs, und bei einem Fehler liegt das komplette Build-Log bereit.

**Was du brauchst:** ein GitHub-Konto und dieses Projekt. Ein **öffentliches** Repository
hat unbegrenzte Actions-Minuten; bei einem privaten zählt jeder Lauf auf dein Kontingent
(2.000 Minuten/Monat, ein Erstlauf braucht ca. 25–40).

---

## Der Workflow ist absichtlich klein

`.github/workflows/build-apk.yml` enthält **keinen Shell-Code mehr** — nur
`checkout`, Java, Tests, Cache und einen Aufruf von `tools/ci_build.sh`. Der Grund: bei
jedem Einfügen über die Weboberfläche kann eine YAML-Datei durch verlorene Einrückung
kaputtgehen („Invalid workflow file"). Je weniger drinsteht, desto unwahrscheinlicher.

Die eigentliche Arbeit steckt in drei Skripten, die mit dem Projekt hochgeladen werden:

| Datei | Aufgabe |
| --- | --- |
| `tools/ci_build.sh` | prüft Pflichtdateien, installiert Systempakete, legt das venv mit Python 3.11.9 an, akzeptiert Lizenzen, baut die APK |
| `tools/ci_licenses.sh` | schreibt die akzeptierten SDK-Lizenzen in ein **fertig installiertes** SDK |
| `tools/ci_fix_cache.sh` | entfernt halb heruntergeladene SDK/NDK-Bäume, an denen buildozer sonst dauerhaft scheitert |
| `tools/ci_check_apk.sh` | prüft die fertige APK: plausible Größe und die gepinnte Python-Version wirklich enthalten |
| `tools/ci_check_apk_aapt2.sh` | prüft im Release die APK-Metadaten mit aapt2: versionCode, versionName, targetSdkVersion und foregroundServiceType |
| `tools/ci_log_failure.sh` | zieht die erste Fehlerzeile samt Kontext aus `buildozer.log` – genau die Zeilen, die bei einem roten Lauf in der Zusammenfassung erscheinen |

Beide laufen auch lokal auf Linux/WSL: `bash tools/ci_build.sh`.

`.github/workflows/release.yml` ist genauso aufgebaut und ruft dasselbe Skript auf — es
läuft nur bei einem Tag (`v*`) und hängt die APK zusätzlich an das Release.

---

## Variante 1 — ohne Kommandozeile

**1.** Auf <https://github.com> anmelden.

**2.** Oben rechts **+ → New repository**. Name z. B. `ps5pro-search-agent`, **Public**,
**kein** Haken bei „Add a README file" → **Create repository**.

**3.** **uploading an existing file** anklicken und diese Dateien ins Browserfenster ziehen:

```
main.py
buildozer.spec
icon.png
README.md
BUILD_ANDROID.md
GITHUB_ANLEITUNG.md
PS5Pro_APK_Colab.ipynb
tools/selftest.py
tools/kivy_smoke.py
tools/ci_build.sh
tools/ci_licenses.sh
tools/ci_fix_cache.sh
tools/ci_check_apk.sh
tools/ci_check_apk_aapt2.sh
assets/icon_fg.png
assets/icon_bg.png
```

Die Ordner `tools` und `assets` müssen **als Ordner** mitgezogen werden (Chrome/Edge
behalten den Pfad bei). Kommen sie nicht mit, bricht der Build mit einer klaren
Fehlermeldung ab — genau dafür ist die Pflichtdatei-Prüfung da. `ps5pro.zip` brauchst du
hier nicht, das ist nur für Colab.

**4.** Unten **Commit changes**.

**5. Die Workflow-Datei anlegen.**

5a. **Add file → Create new file**. Oben das Namensfeld, darunter die Inhaltsfläche.

5b. Ins Namensfeld exakt eintippen:

```
.github/workflows/build-apk.yml
```

Sobald du das Feld verlässt, zeigt GitHub den Pfad `… / .github / workflows /
build-apk.yml` und legt die Ordner an.

5c. Den Inhalt der Datei `.github/workflows/build-apk.yml` aus dem Projektordner
einfügen. Kontrollen: erste Zeile `name: APK bauen`, Einrückung überall **zwei
Leerzeichen**, keine Tabs.

5d. **Commit changes…** → Titel z. B. `Workflow hinzufügen` → **Commit directly to the
`main` branch** → **Commit changes**.

5e. Kontrolle: im Dateibaum liegt `.github/workflows/build-apk.yml`. Der erste Lauf
startet automatisch innerhalb von ~10 Sekunden.

5f. **Optional: Release-Workflow.** Genauso **Add file → Create new file** →
`.github/workflows/release.yml` → Inhalt aus dem Projektordner einfügen → **Commit
changes**. Ohne diese Datei baut nur der normale Workflow; mit ihr hängt sich die APK
bei einem Tag zusätzlich an ein Release (siehe *Dauerhafter Download-Link*).

**6. Den Lauf beobachten.**

6a. Tab **Actions** → links **APK bauen** → rechts die Liste der Läufe.
Symbole: **gelber Punkt** = wartet/läuft, **grüner Haken** = fertig, **rotes X** =
gescheitert, **grauer Balken** = abgebrochen (passiert, wenn kurz danach ein neuer Commit
kommt — `concurrency` bricht den alten Lauf ab).

6b. Steht „*There are no workflow runs yet*": Commit war nicht auf `main`/`master`, oder
Actions ist gesperrt → **Settings → Actions → General → Allow all actions and reusable
workflows → Save**, dann **Actions → APK bauen → Run workflow**.

6c. Auf den Lauf klicken → links den Job **apk** anklicken. Rechts die Schrittliste live:

| Schritt | Zeit | Inhalt |
| --- | --- | --- |
| Auschecken | Sekunden | lädt deinen Commit |
| Java 17 | ~20 s | Temurin-JDK, das Gradle erwartet |
| **Logiktests** | ~2 s | 572 Zusicherungen; rot = kein Build |
| **Kivy-Smoke-Test** | ~1 min | öffnet die drei Popups unter Xvfb; rot = kein Build |
| Build-Cache | ~1 min | SDK/NDK (~2 GB) aus dem Cache oder Download |
| **APK bauen** | 20–35 min | ruft `tools/ci_build.sh` auf (Pflichtdateien, Pakete, venv, Lizenzen, Build) |
| APK als Artifact | Sekunden | lädt `bin/*.apk` hoch |
| Log bei Fehler | nur bei Fehler | lädt `buildozer.log` hoch |

6d. Minutennlange Stille im Schritt **APK bauen** ist normal (NDK-Download, Kompilieren).
Abbrechen: **Cancel workflow** oben rechts.

**7. Ergebnis.** Grüner Lauf → unten auf der Lauf-Seite **Artifacts → `ps5pro-apk`** →
`ps5pro-apk.zip` herunterladen, entpacken, APK aufs Handy.

---

## Variante 2 — mit der Kommandozeile

`git` ist vorhanden. Im Projektordner:

```bash
git init
git add .
git commit -m "PS5 Pro Search Agent"
git branch -M main
git remote add origin https://github.com/<dein-name>/ps5pro-search-agent.git
git push -u origin main
```

Existiert das Repo schon mit Web-Uploads, überschreibt `git push --force-with-lease -u
origin main` sie mit dem vollständigen lokalen Stand (gewollt: der lokale Ordner enthält
alle Ordner).

Beim Push verlangt GitHub ein **Token** statt Passwort: Settings → Developer settings →
Personal access tokens (classic) → Haken `repo`. Die `.gitignore` hält `.buildozer/`,
`bin/` und Caches draußen.

---

## APK installieren

1. `ps5pro-apk.zip` entpacken → `ps5prosearchagent-5.0-arm64-v8a-debug.apk`.
2. Aufs Handy bringen (Kabel, Cloud, Messenger); der Name muss auf `.apk` enden.
3. Antippen → **Installation aus dieser Quelle erlauben** → **Installieren**.
4. Play-Protect-Hinweis „App wurde nicht geprüft" → **Mehr Details → Trotzdem installieren**.
5. Beim ersten Start alle drei Rechte erlauben (Netzwerk, Vibration, Benachrichtigungen).

---

## Wenn ein Lauf rot wird

1. **Actions → Lauf → Job `apk`** → roten Schritt aufklappen, ganz nach unten scrollen.
2. `tools/ci_build.sh` gibt bei einem Build-Fehler zusätzlich die 30 Zeilen **vor**
   `Command failed` aus — das ist die eigentliche Ursache.
3. Zusätzlich liegt unter **Artifacts → `buildozer-log`** das komplette Log.

Häufige Fälle:

| Meldung | Ursache | Lösung |
| --- | --- | --- |
| `Pflichtdatei fehlt: …` | Ordner beim Upload nicht mitgekommen | **Add file → Upload files**, `tools/` bzw. `assets/` als Ordner mitziehen |
| `Can not perform a '--user' install` | `VIRTUAL_ENV` fehlt | `ci_build.sh` setzt es — nur relevant, wenn du das Skript geändert hast |
| Lauf steht minutenlang beim Lizenztext | `sdkmanager` fragt interaktiv | buildozer beantwortet das selbst (`android.accept_sdk_license = True`); `ci_licenses.sh` hinterlegt die Lizenzen zusätzlich, sobald das SDK existiert. Hängt es trotzdem: abbrechen, unter **Actions → Caches** den `buildozer-…`-Eintrag löschen, neu starten |
| `sdkmanager path … does not exist, sdkmanager is not installed` | halb heruntergeladenes SDK im Cache — buildozer prüft nur, ob der Ordner existiert | `tools/ci_fix_cache.sh` räumt das auf und läuft automatisch in `ci_build.sh`. Zusätzlich **Actions → Caches** → `buildozer-…` löschen. |
| `UnicodeDecodeError` direkt beim Start von buildozer | Locale ist ASCII, die `buildozer.spec` enthält Umlaute | `ci_build.sh` setzt `LANG`/`PYTHONUTF8`; lokal zusätzlich `export LANG=C.UTF-8` |
| Abbruch mitten im Kivy-Build, im Log `window_info.c` oder `_PyLong_AsByteArray` | p4a baut ohne Pin gegen CPython 3.14.2, und Cython 0.29 kann nur bis 3.12 | `buildozer.spec` pinnt `python3==3.11.9, hostpython3==3.11.9`; `tools/ci_fix_cache.sh` setzt den Pin auch im p4a-Checkout durch und verwirft alte python3-Builds. |
| `Invalid workflow file` | YAML beim Einfügen zerstört | Datei löschen und über **Create new file** neu anlegen; die YAML ist inzwischen nur ~80 Zeilen |
| `Node.js 20 is deprecated … actions/checkout@v4` | Action-Version zu alt | Im Projekt laufen `checkout@v5`, `setup-java@v6`, `cache@v5`, `upload-artifact@v6` und `action-gh-release@v3` (alle Node 24). Eine alte Kopie im Repo durch den Stand aus dem Projektordner ersetzen. |
| `ubuntu-latest label will migrate to Ubuntu 26` | Hinweis, kein Fehler | Alle drei Workflows pinnen `runs-on: ubuntu-24.04`; damit bleibt die Toolchain reproduzierbar. |
| Actions-Minuten leer / Lauf startet nicht | privates Repo | Repo auf **Public** stellen |
| `Resource not accessible by integration` | Workflow-Rechte | **Settings → Actions → General → Workflow permissions → Read and write** |
| grün, aber kein Artifact | `bin/*.apk` fehlt | im Job-Log steht der tatsächliche Pfad; meist wurde der Build übersprungen |
| Bricht nach dem Cache-Restore | alter Cache nach NDK-Wechsel | **Actions → Caches** → `buildozer-…` löschen |

---

## Manuell neu bauen

**Actions → APK bauen → Run workflow → Branch `main` → Run workflow.**

Gebaut wird automatisch nur bei Änderungen an `main.py`, `buildozer.spec`, `icon.png`,
`assets/**`, `tools/**` oder am Workflow selbst — Doku-Änderungen lösen keinen Lauf aus.

## Updates einspielen

Datei im Repo ändern (Web: Datei öffnen → Stift → **Commit changes**) → Lauf startet →
nach 5–15 Minuten liegt das neue Artifact bereit. Neue APK über die alte installieren;
App-Daten bleiben erhalten, solange der Paketname `de.ps5pro.ps5prosearchagent` gleich
bleibt.

## Dauerhafter Download-Link (Release)

Artifacts verfallen nach 90 Tagen und sind nur eingeloggt sichtbar. Der Workflow
`.github/workflows/release.yml` baut die APK bei einem **Tag** und hängt sie an ein
Release — der Link ist danach ohne Login auf dem Handy zu öffnen.

**Tag setzen, ohne Kommandozeile:**

1. **Code** → rechts **Releases** → **Draft a new release**.
2. Bei **Choose a tag** `v5.0` eintippen → **Create new tag: v5.0 on publish**.
3. Titel z. B. `v5.0 Final` → **Publish release**.

Der Tag zeigt damit auf den aktuellen Stand von `main`, und der Workflow **Release**
startet. Nach 20–40 Minuten (erster Lauf länger) liegt die APK am Release:
**Releases → v5.0 → Assets → `ps5prosearchagent-5.0-arm64-v8a-debug.apk`**.

**Mit der Kommandozeile:**

```bash
git tag v5.0
git push origin v5.0
```

Der Workflow legt das Release selbst an (Titel = Tag, hier `v5.0`). Ein schon
publiziertes Release stört nicht — die APK wird dort ergänzt, der Titel bleibt.

**Release-Stand:** `buildozer.spec` setzt `version = 5.0`; der finale Tag heißt
`v5.0`. Tag und Spec-Version dürfen abweichen, aber der Dateiname der APK enthält die
Version aus der Spec — gleiche Nummern halten die Zuordnung eindeutig.

**Tag am falschen Commit oder vertippt?** Lokal und auf GitHub löschen, neu setzen:

```bash
git tag -d v5.0
git push origin :refs/tags/v5.0
```

Ein bereits angelegtes Release bleibt dabei bestehen (samt alter APK) — im Zweifel im
Web löschen und neu taggen.

## Play Store

Dafür braucht es einen signierten **AAB**: `android.release_artifact = aab`,
`android.api = 36` und einen eigenen Keystore über die vier GitHub-Secrets
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` und
`ANDROID_KEY_PASSWORD`. Ohne diese Secrets erzeugt der v5.0-Lauf nur ein
Smoke-Test-AAB. Die vollständige Anleitung inklusive nachträglichem AAB-Release
für v5.0 steht in [PLAY_STORE.md](PLAY_STORE.md).
