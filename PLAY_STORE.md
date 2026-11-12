# Google Play: Release-Keystore, AAB und die noetigen Secrets

Ziel: ein **signiertes App Bundle (.aab)** mit **targetSdk 36**, das Google Play
annimmt. Die Debug-APK fuer Sideloading bleibt unabhaengig davon bestehen.

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

Optional, nur fuer automatisches Hochladen zu Play:
| `PLAY_SERVICE_ACCOUNT_JSON` | Base64 des Service-Account-JSON aus der Google-Cloud-Console (Play Developer API) |

Die vier `ANDROID_*`-Secrets werden vom Workflow zu
`P4A_RELEASE_KEYSTORE`, `P4A_RELEASE_KEYSTORE_PASSWD`,
`P4A_RELEASE_KEYALIAS` und `P4A_RELEASE_KEYALIAS_PASSWD` und bleiben in Logs
maskiert. Der Keystore wird nur in `$RUNNER_TEMP` entpackt, nie committet.

**Ohne diese Secrets** baut der Tag-Lauf trotzdem ein AAB, aber mit einem
Wegwerf-Schluessel. Das landet nur als Workflow-Artefakt `ps5pro-aab-smoketest`
und **nicht** im Release – es ist ausdruecklich nicht fuer Play geeignet.

## 4. Was der Tag-Lauf baut

Bei `git tag v1.2 && git push origin refs/tags/v1.2` laufen zwei Jobs (die
Release `v1.0` bleibt unveraendert bestehen):

1. **release** – Debug-APK wie bisher (Sideloading) → Release-Asset `*.apk`.
2. **aab** – `buildozer android release` → `bin/*.aab`, signiert mit dem
   hinterlegten Keystore → Release-Asset `*.aab` (nur mit echten Secrets).

Beide Jobs pruefen das Ergebnis: die APK auf Python-Version, das AAB auf
`base/manifest/AndroidManifest.xml`, `BundleConfig.pb`, eine
`META-INF/*.RSA`-Signatur und `libpython3.11.so`.

Lokal (Linux/WSL) derselbe Weg:
```bash
export P4A_RELEASE_KEYSTORE=~/ps5pro-upload.jks
export P4A_RELEASE_KEYSTORE_PASSWD='...'
export P4A_RELEASE_KEYALIAS=upload
export P4A_RELEASE_KEYALIAS_PASSWD='...'
ARTIFACT=aab bash tools/ci_build.sh
```

## 5. versionCode

`buildozer.spec` setzt fuer v1.2 `android.numeric_version = 3`. Google Play verlangt
fuer **jeden** Upload einen **hoeheren** versionCode – vor dem naechsten Upload
erhoehen (4, 5, …). Die sichtbare Version (`version = 1.2`) ist davon unabhaengig;
bei einem echten Release beide anheben (z. B. `1.3` / `4`).

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
  mit `mandatorySystemGestures` freigehalten. `android.display_cutout = shortEdges`
  erlaubt die Nutzung der Notch-Flaeche, der Ausschnitt kommt als oberer Rand zurueck.
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
keytool -printcert -jarfile bin/ps5prosearchagent-1.2-arm64-v8a-release.aab | head

# targetSdk im gebauten Bundle (aapt2 aus den Android build-tools)
aapt2 dump badging bin/ps5prosearchagent-1.2-arm64-v8a-release.aab | grep -E "sdkVersion|targetSdkVersion|package"
```

Erwartet: `targetSdkVersion:'36'`, Paket `de.ps5pro.ps5prosearchagent`,
`native-code: 'arm64-v8a'`.
