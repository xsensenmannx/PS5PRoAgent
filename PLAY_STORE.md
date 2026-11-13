# Google Play: Release-Keystore, AAB und die noetigen Secrets

Ziel: ein **signiertes App Bundle (.aab)** mit **targetSdk 36**, das Google Play
annimmt. Die Debug-APK fuer Sideloading bleibt unabhaengig davon bestehen.

## 0. Status des v5.1-Stands

Der v5.1-Stand ist vorbereitet, aber **noch nicht veroeffentlicht**: Tag und
GitHub-Release `v5.1` existieren noch nicht. Nach der Veroeffentlichung enthaelt
der Release **die Debug-APK**. Der AAB-Job des Tag-Laufs verwendet denselben
Secret-Pfad wie v3.2. Ohne
Release-Keystore baut er nur ein Smoke-Test-AAB, das als Workflow-Artefakt
`ps5pro-aab-smoketest` vorliegt und **nicht fuer Google Play
geeignet** ist; in diesem Fall fehlt das Release-Asset
`ps5prosearchagent-5.1-arm64-v8a-release.aab`.

Die Releases v3.3.1, v3.3 und v3.2 bleiben als eigene, unveraenderte Staende erhalten.

## 1. Release-Keystore erzeugen (einmalig, auf deinem Rechner)

Der Keystore ist der **Upload-Key**. Ohne ihn sind spaetere Updates nicht mehr
moeglich, deshalb sofort an zwei sicheren Orten sichern (Passwortmanager +
Offline-Kopie). Nicht ins Repository legen.

**Windows (PowerShell, JDK 17):**
```powershell
keytool -genkeypair -v -keystore "$env:USERPROFILE\ps5pro-upload.jks" `
  -alias upload -keyalg RSA -keysize 2048 -validity 10000
```

**macOS/Linux:**
```bash
keytool -genkeypair -v -keystore ~/ps5pro-upload.jks \
  -alias upload -keyalg RSA -keysize 2048 -validity 10000
```

`keytool` fragt nach Passwort, Name/Organisation und bestaetigt am Ende.
Keystore- und Key-Passwort duerfen identisch sein (einfacher, ueberall unterstuetzt).

Pruefen:
```bash
keytool -list -v -keystore ps5pro-upload.jks -alias upload
```

## 2. Keystore als Base64 fuer GitHub

**Windows:**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\ps5pro-upload.jks")) |
  Set-Clipboard
```

**macOS/Linux:**
```bash
base64 -w0 ~/ps5pro-upload.jks    # macOS: base64 -i ~/ps5pro-upload.jks
```

## 3. Secrets im Repository hinterlegen

GitHub → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Inhalt |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | kompletter Inhalt aus Schritt 2 (eine Zeile, ohne Zeilenumbrueche) |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore-Passwort |
| `ANDROID_KEY_ALIAS` | Alias, z. B. `upload` |
| `ANDROID_KEY_PASSWORD` | Key-Passwort (oft identisch mit dem Keystore-Passwort) |

**Signing-Status v5.1:** Der Tag-Lauf prueft die vier Secrets. Ohne
`ANDROID_KEYSTORE_BASE64` zeigt er `real=false` und erzeugt nur das
Smoke-Test-Artefakt. Die drei weiteren Secrets `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS` und `ANDROID_KEY_PASSWORD` werden ohne Base64 gar nicht
ausgewertet; fuer Play muessen alle vier zusammen gesetzt sein. Ob einzelne
davon bereits im Repository hinterlegt sind, laesst sich ohne Admin-Zugriff auf
die Repository-Secrets nicht feststellen.

`PLAY_SERVICE_ACCOUNT_JSON` ist **nicht** Teil dieses Workflows. Ein
automatischer Upload zur Play Developer API ist nicht implementiert; das AAB
wird nach dem Download manuell in der Play Console hochgeladen.

Die vier `ANDROID_*`-Secrets werden vom Workflow zu
`P4A_RELEASE_KEYSTORE`, `P4A_RELEASE_KEYSTORE_PASSWD`,
`P4A_RELEASE_KEYALIAS` und `P4A_RELEASE_KEYALIAS_PASSWD` und bleiben in Logs
maskiert. Der Keystore wird nur in `$RUNNER_TEMP` entpackt, nie committet.

**Ohne diese Secrets** baut der Tag-Lauf trotzdem ein AAB, aber mit einem
Wegwerf-Schluessel. Das landet nur als Workflow-Artefakt `ps5pro-aab-smoketest`
und **nicht** im Release – es ist ausdruecklich nicht fuer Play geeignet.

## 4. Was der Tag-Lauf baut

Bei `git tag v5.1 && git push origin refs/tags/v5.1` laufen zwei Jobs (die
vorherigen Releases bleiben unveraendert bestehen):

1. **release** – Debug-APK wie bisher (Sideloading) → Release-Asset `*.apk`.
2. **aab** – `buildozer android release` → `bin/*.aab`, signiert mit dem
   hinterlegten Keystore → Release-Asset `*.aab` (nur mit echten Secrets).

Beide Jobs pruefen das Ergebnis: die APK mit `aapt2` auf `versionCode`,
`versionName`, `targetSdkVersion` und `foregroundServiceType` sowie auf die
Python-Version; das AAB auf `base/manifest/AndroidManifest.xml`,
`BundleConfig.pb`, eine `META-INF/*.RSA`-Signatur und `libpython3.11.so`.

Lokal (Linux/WSL) derselbe Weg (die vier Variablen muessen gesetzt sein):
```bash
export P4A_RELEASE_KEYSTORE=~/ps5pro-upload.jks
export P4A_RELEASE_KEYSTORE_PASSWD='...'
export P4A_RELEASE_KEYALIAS=upload
export P4A_RELEASE_KEYALIAS_PASSWD='...'
ARTIFACT=aab bash tools/ci_build.sh
```

## 4.1 v5.1 als AAB veroeffentlichen

Beim ersten v5.1-Release wird der Tag auf den freigegebenen Commit gesetzt.
Bleibt der Tag-Lauf ohne Keystore, enthaelt das Release nur die Debug-APK.
Nachdem die vier Secrets aus Abschnitt 3 gesetzt wurden:

1. **Actions → Release → Lauf fuer `v5.1` → Re-run all jobs** auswaehlen
   (falls noch kein Tag-Lauf existiert: zuerst `v5.1` taggen und pushen).
   Dadurch wird derselbe Commit erneut gebaut; die Secrets werden neu geladen.
2. Im AAB-Job muss `Signierschluessel bereitstellen` den Wert `real=true`
   ausgeben. Danach laufen `AAB bauen`, `AAB als Artefakt (echter Schluessel)`
   und `AAB ans Release haengen` erfolgreich.
3. Unter **Releases → v5.1 → Assets** erscheint nach erfolgreichem Lauf
   `ps5prosearchagent-5.1-arm64-v8a-release.aab` neben der Debug-APK.
4. Die AAB herunterladen und in der Play Console unter **Interner Test**
   hochladen; Play App Signing aktivieren (Abschnitt 6). Die AAB aus
   `ps5pro-aab-smoketest` niemals dafuer verwenden.

Ein erneuter Lauf mit denselben Secrets ergaenzt die Assets des bestehenden
Releases, statt ein zweites Release anzulegen. Der versionCode bleibt fuer v5.1
bei **18**. Die aelteren Staende v3.3.1 (versionCode 13), v3.3 (versionCode 12)
und v3.2 (versionCode 11) bleiben separat erhalten; derselbe Ablauf funktioniert
auch mit deren Tags.

## 5. versionCode

`buildozer.spec` setzt fuer v5.1 `android.numeric_version = 18`. Google Play verlangt
fuer **jeden** Upload einen **hoeheren** versionCode – vor dem naechsten Upload
erhoehen (19, 20, …). Die sichtbare Version (`version = 5.1`) ist davon unabhaengig;
bei einem echten Release beide anheben.

## 6. Play Console – einmalige Einrichtung

1. <https://play.google.com/console> → **App erstellen** (Name, Sprache, App/Spiel).
2. **App-Inhalte** ausfuellen:
   * Datenschutzerklaerung: Die App speichert nur lokal (Einstellungen/Verlauf),
     sendet keine Nutzerdaten an dich. Kurze Datenschutz-URL hinterlegen ist
     trotzdem der einfachste Weg (GitHub Pages/Notion-Seite genuegt).
   * **Datensicherheit**: „Es werden keine Daten erfasst oder geteilt" –
     Ausnahme: Netzwerkzugriffe zu Haendlern sind keine Datenerhebung durch dich.
   * **Foreground-Service-Typen**: `specialUse` angeben und begruenden
     („periodische Preis-/Verfuegbarkeitspruefung fuer ein vom Nutzer
     beobachtetes Produkt, per AUTO-Schalter gestartet"). Der Subtyp steht
     zusaetzlich als `<property>` im Manifest (siehe Abschnitt 7).
   * Werbung: nein. Altersfreigabe: IARC-Fragebogen.
3. **Produktion → Interner Test** anlegen, das AAB aus dem Release hochladen.
4. **Play App Signing** aktivieren (Google verwaltet den App-Signaturschluessel,
   dein Keystore ist nur der Upload-Key). Danach AAB pruefen lassen und im
   internen Test installieren.
5. Erst nach bestandenem Test auf **Geschlossener/Offener Test** oder
   **Produktion** befoerdern.

Hinweis: Ein AAB laesst sich **nicht** direkt per `adb install` installieren –
dafuer die Debug-APK aus demselben Release verwenden.

## 7. Warum targetSdk 36, specialUse und Edge-to-Edge

* Seit **31.08.2026** verlangt Play fuer neue Apps und Updates **API 36**
  (Android 16). `android.api = 36` setzt compileSdk und targetSdk.
* Ab targetSdk 35 zeichnet Android hinter Status- und Navigationsleiste.
  Die App liest die Insets per pyjnius (`android_insets()` in `main.py`) und
  verschiebt Titel, ErgebnisPanel und Buttons; der Gestenbereich unten wird
  mit `mandatorySystemGestures` freigehalten. Im Querformat werden auch linke
  und rechte Insets (seitliche Navigationsleiste/Notch) beruecksichtigt.
  `android.display_cutout = shortEdges` erlaubt die Nutzung der Notch-Flaeche.
* **Tablets/Foldables:** `orientation = all` erlaubt das Querformat; ab 600 dp
  Breite schaltet die Oberflaeche auf eine zweispaltige Ansicht mit der kompakten
  Trefferliste rechts um. Die Liste ist auch im Hochformat vertikal. Das ist reine
  Kivy-Layout-Logik, keine zweite Activity.
* **Boot-Receiver:** `RECEIVE_BOOT_COMPLETED` ist deklariert. Der Java-Receiver
  `BootReceiver` startet den `specialUse`-Foreground-Service nach `BOOT_COMPLETED`
  oder `MY_PACKAGE_REPLACED` nur dann, wenn `auto_scan` in den Einstellungen aktiv
  ist. Android 15 erlaubt diesen Service-Typ aus dem Boot-Receiver; er ist nicht
  in der Liste der gesperrten Typen.
* Der Hintergrund-Service nutzt **`specialUse`**, nicht `dataSync`: Android 15
  beendet `dataSync`-Foreground-Services nach **6 Stunden pro 24 h** und wirft
  eine Exception, wenn der Dienst nicht selbst stoppt. Ein dauerhaft laufender
  Preis-Beobachter wuerde also nach sechs Stunden abbrechen. `specialUse` hat
  dieses Limit nicht; Play verlangt dafuer den Subtyp im Manifest, den
  `tools/p4a_hook.py` beim Build eintraegt. Im Play-Console-Formular denselben
  Zweck angeben – der Reviewer sieht beides.
* Die nativen Bibliotheken sind 16-KB-Seiten-faehig (NDK 28c) – Play-Voraussetzung
  fuer Apps mit targetSdk 35+.

## 8. Kontrollieren

```bash
# Signatur des AAB
keytool -printcert -jarfile bin/ps5prosearchagent-5.1-arm64-v8a-release.aab | head

# targetSdk im gebauten Bundle (aapt2 aus den Android build-tools)
aapt2 dump badging bin/ps5prosearchagent-5.1-arm64-v8a-release.aab | grep -E "sdkVersion|targetSdkVersion|package"
```

Erwartet: `targetSdkVersion:'36'`, Paket `de.ps5pro.ps5prosearchagent`,
`native-code: 'arm64-v8a'`.
