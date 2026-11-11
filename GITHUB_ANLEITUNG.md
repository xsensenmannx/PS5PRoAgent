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

Die eigentliche Arbeit steckt in zwei Skripten, die mit dem Projekt hochgeladen werden:

| Datei | Aufgabe |
| --- | --- |
| `tools/ci_build.sh` | prüft Pflichtdateien, installiert Systempakete, legt das venv mit Python 3.12 an, akzeptiert Lizenzen, baut die APK |
| `tools/ci_licenses.sh` | schreibt die akzeptierten SDK-Lizenzen in ein **fertig installiertes** SDK |
| `tools/ci_fix_cache.sh` | entfernt halb heruntergeladene SDK/NDK-Bäume, an denen buildozer sonst dauerhaft scheitert |

Beide laufen auch lokal auf Linux/WSL: `bash tools/ci_build.sh`.

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
tools/ci_build.sh
tools/ci_licenses.sh
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
| **Logiktests** | ~2 s | 35 Zusicherungen; rot = kein Build |
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

1. `ps5pro-apk.zip` entpacken → `ps5prosearchagent-1.0-arm64-v8a_armeabi-v7a-debug.apk`.
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
| `Invalid workflow file` | YAML beim Einfügen zerstört | Datei löschen und über **Create new file** neu anlegen; die YAML ist inzwischen nur ~60 Zeilen |
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

## Optional: dauerhafter Download-Link

Artifacts verfallen nach 90 Tagen und sind nur eingeloggt sichtbar. Für einen Link direkt
aufs Handy: **Releases → Draft a new release**, Tag z. B. `v1.0`, APK als Asset anhängen.
Automatisch geht das mit einem zusätzlichen `softprops/action-gh-release`-Schritt — sag
Bescheid, dann baue ich ihn ein.

## Play Store

Dafür braucht es einen signierten **AAB**: `android.release_artifact = aab`,
`android.api = 35` und einen eigenen Keystore über die `P4A_RELEASE_*`-Variablen. Details
in [BUILD_ANDROID.md](BUILD_ANDROID.md), Abschnitt 8.
