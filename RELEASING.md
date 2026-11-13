# Release bauen

Die APK entsteht ausschließlich im GitHub-Workflow **Release** bei einem Tag.
Ein lokaler Android-Build ist nicht nötig (und auf Windows nicht vorgesehen).

## Einmalig

* Repository-Secrets unter **Settings → Secrets and variables → Actions**:
  * `ANDROID_KEYSTORE_BASE64` – Base64 der PKCS#12-Datei
  * `ANDROID_KEYSTORE_PASSWORD` – Passwort des Keystores
* Keystore und Passwort offline sichern. Gehen sie verloren, lassen sich keine
  Updates mehr über bestehende Installationen legen.

## Ablauf

1. **Version setzen:** in `buildozer.spec` `version = X.Y` und
   `android.numeric_version = X*10000 + Y*100` eintragen; `tools/selftest.py`
   prüft, dass beides zusammenpasst.
2. **Commit + Push** auf `main`, CI abwarten (Logiktests und Smoke-Matrix).
3. **Tag setzen** und pushen:

   ```bash
   git tag -a vX.Y -m "vX.Y"
   git push origin vX.Y
   ```

   Der Tag muss auf `vMAJOR.MINOR[.PATCH]` passen; `tools/set_version_from_tag.sh`
   leitet daraus `versionName` und `versionCode` ab und bricht bei ungültigen
   Tags ab.
4. **Workflow beobachten.** Ein voller Build dauert rund 70 Minuten; der Cache
   wird bei jeder Versionsänderung verworfen. Die Reihenfolge ist:
   Secrets/Signatur prüfen → Tests → Version aus Tag → Build → aapt2-Gate →
   Signieren → Umbenennen → Release-Notes → Upload → alte Assets entfernen.
5. **Ergebnis prüfen** (siehe unten).

## Prüfliste nach dem Lauf

* Genau **ein** APK-Asset, Name `ps5prosearchagent-X.Y-arm64-v8a.apk`;
  das alte `-debug.apk` ist verschwunden.
* Release-Notes nennen „Release-APK", Größe und SHA-256.
* Die APK meldet `versionName X.Y`, `versionCode X*10000+Y*100` und **kein**
  `application-debuggable` (macht der aapt2-Schritt automatisch).
* Signatur stimmt mit dem hinterlegten Zertifikat überein:
  `apksigner verify --print-certs` → SHA-256
  `63:E5:1D:83:8B:FE:14:38:C6:D6:14:3D:F9:7D:46:D5:73:55:BC:D3:83:3A:BB:44:A2:31:BE:CF:D5:C5:70:DD`
* Installation über die Vorversion legt sich ohne Deinstallation darüber
  (gleicher Schlüssel).
* Auf einem Gerät: Start, Scan, Drehen, flaches Querformat (620×380) –
  optional automatisiert mit `tools/adb_layout_check.sh`.

## Wenn etwas fehlschlägt

| Schritt | Ursache | Lösung |
|---|---|---|
| „Secrets … fehlen" | Secrets nicht gesetzt | Secrets anlegen, Tag erneut pushen |
| Keystore-Fingerprint weicht ab | falsche Datei/Passwort | Keystore prüfen; **nicht** veröffentlichen |
| aapt2: `application-debuggable` | Debug-Build gebaut | `android.release_artifact = apk` und `ci_build.sh` prüfen |
| Build bricht nach Minuten ab | Cache von falschem Runner-Image | Cache-Key in `release.yml` mitziehen |
| Asset existiert | erneuter Lauf | `overwrite_files` räumt auf; alte Assets entfernt der letzte Schritt |

Ein fehlgeschlagener Lauf veröffentlicht nichts: Der Upload ist der letzte
Schritt vor dem Aufräumen.
