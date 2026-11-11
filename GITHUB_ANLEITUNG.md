# GitHub-Anleitung — APK automatisch bauen lassen

Diese Anleitung ist die Alternative zu Colab. Ergebnis: Bei jedem Push baut GitHub die
APK auf einem Ubuntu-Rechner, und du lädst sie als ZIP herunter. Kein Warten im
Browser-Tab, kein manuelles Hochladen eines ZIPs, und bei einem Fehler liegt das
komplette Build-Log als Download bereit.

**Was du brauchst:** ein GitHub-Konto (kostenlos) und dieses Projekt. Ein **öffentliches**
Repository hat unbegrenzte Actions-Minuten; bei einem privaten Repo zählt jeder Lauf auf
dein Freikontingent (2.000 Minuten/Monat — ein Erstlauf belegt ca. 25–40).

---

## Variante 1 — ohne Kommandozeile (empfohlen, wenn git neu für dich ist)

**1.** Auf <https://github.com> anmelden.

**2.** Oben rechts **+ → New repository**.

**3.** Name z. B. `ps5pro-search-agent`, Sichtbarkeit **Public**, **kein** Haken bei
„Add a README file" (sonst gibt es einen Konflikt beim ersten Upload). → **Create repository**.

**4.** Auf der leeren Repo-Seite **uploading an existing file** anklicken.

**5.** Diese Dateien aus dem Projektordner ins Browserfenster ziehen:

```
main.py
buildozer.spec
icon.png
README.md
BUILD_ANDROID.md
GITHUB_ANLEITUNG.md
PS5Pro_APK_Colab.ipynb
tools/selftest.py
assets/icon_fg.png
assets/icon_bg.png
```

Den Ordner `assets` kannst du als Ordner mitziehen (Chrome/Edge behalten den Pfad) —
sonst die zwei Dateien einzeln über **Add file → Create new file** mit dem Pfad
`assets/icon_fg.png` anlegen. `ps5pro.zip` brauchst du **nicht** hochladen, das ist nur
für Colab.

**6.** Unten **Commit changes**. Ein Lauf startet eventuell schon — das ist okay, er
wird gleich vom nächsten abgelöst.

**7.** Jetzt den Workflow anlegen: **Add file → Create new file**, als Dateiname exakt

```
.github/workflows/build-apk.yml
```

eintippen (die Schrägstriche erzeugen die Ordner), den Inhalt der Datei
`.github/workflows/build-apk.yml` aus dem Projektordner hineinkopieren → **Commit changes**.

**8.** Oben auf **Actions** gehen. Links steht **APK bauen**. Der Lauf heißt
„*<dein Commit-Text>*" und hat einen gelben Punkt (läuft) bzw. grünen Haken (fertig).

**9.** Lauf anklicken, dann den Job **apk** anklicken — dort siehst du live jeden Schritt
(`Systempakete`, `Python 3.12 und Buildozer`, `Logiktests`, `Build-Cache`, `APK bauen`).
Der Schritt **APK bauen** ist der lange: 25–40 Minuten beim ersten Mal.

**10.** Wenn der Lauf grün ist: unten auf der Lauf-Seite unter **Artifacts** auf
**`ps5pro-apk`** klicken. Der Browser lädt `ps5pro-apk.zip` — darin liegt die `.apk`.
ZIP entpacken, APK aufs Handy, fertig (Installation: siehe unten).

---

## Variante 2 — mit der Kommandozeile

`git` ist auf deinem Rechner vorhanden. Im Projektordner:

```bash
git init
git add .
git commit -m "PS5 Pro Search Agent"
git branch -M main
git remote add origin https://github.com/<dein-name>/ps5pro-search-agent.git
git push -u origin main
```

Beim Push fragt GitHub nach Zugangsdaten. Das Passwort funktioniert **nicht** — du
brauchst ein Token: **Settings → Developer settings → Personal access tokens → Tokens
(classic) → Generate new token**, Haken bei `repo`, Token als Passwort einfügen. Oder
einmalig `gh auth login` (GitHub CLI), dann läuft es automatisch.

Die `.gitignore` im Projekt sorgt dafür, dass `.buildozer/`, `bin/` und `__pycache__/`
nicht mitgehen — Pushes bleiben dadurch klein.

---

## Was der Workflow macht

| Schritt | Dauer (1. Lauf) | Inhalt |
| --- | --- | --- |
| Auschecken | Sekunden | dein Commit |
| Java 17 | ~20 s | Temurin-JDK, das Gradle erwartet |
| Systempakete | ~1 min | Autotools, OpenSSL-Header, CMake, ccache |
| Python 3.12 + Buildozer | ~1 min | `uv` pinnt Python 3.12, Buildozer aus dem Git-Master |
| **Logiktests** | ~2 s | `tools/selftest.py` — 35 Zusicherungen; rot = kein Build |
| Build-Cache | ~1 min | SDK/NDK (~2 GB) aus dem Cache, sonst Download |
| APK bauen | 20–35 min | lädt SDK/NDK, kompiliert Python, Kivy und die App |
| Artifact | Sekunden | `ps5pro-apk` (ZIP mit der APK) |

Läufe danach: **5–15 Minuten**, weil SDK, NDK und die kompilierten Dist-Ordner im Cache
liegen.

---

## APK installieren

1. `ps5pro-apk.zip` entpacken → `ps5prosearchagent-1.0-arm64-v8a_armeabi-v7a-debug.apk`.
2. Datei aufs Handy bringen (Kabel, Cloud, Messenger). Der Name muss auf `.apk` enden.
3. Antippen → **Installation aus dieser Quelle erlauben** → **Installieren**.
4. Play-Protect-Hinweis „App wurde nicht geprüft" → **Mehr Details → Trotzdem installieren**.
5. Beim ersten Start alle drei Rechte-Dialoge erlauben (Netzwerk, Vibration,
   Benachrichtigungen) — ohne das Benachrichtigungs-Recht kommt kein Alarm.

---

## Wenn ein Lauf rot wird

1. **Actions → Lauf → Job `apk`** öffnen und den **roten Schritt** aufklappen.
2. Ganz unten in diesem Schritt steht die eigentliche Fehlermeldung.
3. Zusätzlich liegt unter **Artifacts → `buildozer-log`** das komplette Build-Log
   (`buildozer.log`) — dort steht die Ursache ein paar Zeilen **über** `Command failed`.
4. Diesen Block kopieren und mir schicken; ich ändere die Dateien, du committest neu.

Häufige Fälle in Actions (nicht Colab-spezifisch):

| Meldung | Ursache | Lösung |
| --- | --- | --- |
| `Can not perform a '--user' install` | `VIRTUAL_ENV` fehlt | ist im Workflow gesetzt — nur relevant, wenn du den Block selbst geändert hast |
| `Actions minutes` / Lauf startet nicht | privates Repo, Kontingent leer | Repo auf **Public** stellen |
| `Resource not accessible by integration` | Workflow-Rechte | **Settings → Actions → General → Workflow permissions → Read and write** |
| Lauf bricht nach dem Cache-Restore | alter Cache nach NDK-Wechsel | **Actions → Caches** → Eintrag `buildozer-…` löschen, neu starten |
| Alles grün, aber kein Artifact | `bin/*.apk` nicht gefunden | Job-Log prüfen: dort steht der tatsächliche Pfad der APK |

---

## Manuell neu bauen

**Actions → APK bauen → Run workflow → Branch `main` → Run workflow.** Nützlich, wenn du
nur den Cache aufwärmen willst oder ein Lauf abgebrochen ist.

Der Workflow baut automatisch nur, wenn sich `main.py`, `buildozer.spec`, `icon.png`,
`assets/**`, `tools/selftest.py` oder der Workflow selbst ändern — Doku-Änderungen lösen
keinen 30-Minuten-Lauf aus. Mehrere Uploads hintereinander werden durch `concurrency`
abgebrochen, es läuft immer nur der neueste.

---

## Updates einspielen

1. Datei im Repo ändern (Web: Datei öffnen → Stift-Symbol → **Commit changes**).
2. Der Push startet den Build; nach 5–15 Minuten liegt das neue Artifact bereit.
3. Neue APK über die alte installieren — App-Daten bleiben erhalten, solange der
   Paketname `de.ps5pro.ps5prosearchagent` gleich bleibt.

---

## Optional: dauerhafter Download-Link statt Artifact

Artifacts verfallen nach 90 Tagen und sind nur eingeloggt sichtbar. Für einen Link, den
du auf dem Handy direkt öffnen kannst, eignet sich ein **Release**: Auf der Repo-Seite
**Releases → Draft a new release**, Tag z. B. `v1.0`, und die APK als Asset anhängen.
Der Workflow kann das automatisch, wenn man einen `softprops/action-gh-release`-Schritt
ergänzt — sag Bescheid, dann baue ich ihn ein.

## Play Store

Dafür braucht es einen signierten **AAB** statt der Debug-APK: `android.release_artifact
= aab`, `android.api = 35` und einen eigenen Keystore über die `P4A_RELEASE_*`-Umgebungs­variablen.
Die Schritte stehen in [BUILD_ANDROID.md](BUILD_ANDROID.md), Abschnitt 8.
