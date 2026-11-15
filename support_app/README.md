# PS5 Pro Search Agent – Hilfe

Eigenständige Offline-Support-App für den PS5 Pro Search Agent (Konsolen-Radar).
Sie erklärt Einrichtung, Alarme, Webhooks, Konfidenz und Grenzen der Radar-App
und prüft einen eingefügten Diagnosebericht.

**Standard ist offline: kein Konto, keine Telemetrie, kein eingebauter Key.**
Alle Antworten stammen aus `knowledge.py`. Optional lässt sich unter „KI“ ein
eigener Freebuff-API-Key eintragen; nur dann spricht die App mit dem Netz,
und der Key bleibt im privaten App-Speicher.

## Warum eigenes Projekt?

- Der Radar bleibt unverändert — kein Risiko für laufende Releases.
- Eigenes Paket `de.konsolenradar.support`, parallel installierbar.
- Die Hilfe ist auch dann nutzbar, wenn der Radar selbst nicht startet.

## Was sie kann

| Bereich | Inhalt |
|---|---|
| Fragen | Freitextfragen gegen 16 Themenkarten, umlaut- und umgangssprachfest |
| Suche | Wunsch wie „unter 700, nur Amazon, nur neu“ wird zu Einstellungen, Schritten und Hinweisen — mit den echten Schlüsseln des Radars |
| Diagnose | Füge den Diagnose-Text aus dem Radar ein: Shops, letzter Scan, Treffer, Konfidenz, Webhook-Fehler, 403/429 |
| Themen | Alle Karten als Liste, ein Tipp öffnet die Antwort im Chat |
| KI | Optional: Freitext an ein Modell der Freebuff-API, mit eigenem Key; passende Karten gehen als Beleg mit, Antworten sind kurz |

## Was sie nicht kann

- **Sie liest keine Daten des Radars.** Android erlaubt keiner App den Zugriff
  auf den privaten Speicher einer anderen. Deshalb der Weg über den
  Diagnose-Text: kopieren, einfügen, prüfen.
- Ohne Key keine Modell-Antworten: Jede Antwort ist dann eine feste,
  prüfbare Karte.
- Kein eingebauter Key und keine Telemetrie. Die KI kostet Guthaben des
  eigenen Accounts; Fragen verlassen dabei das Gerät.

## Online-KI (optional)

Reiter „KI“, oben rechts „KEY“:

1. Freebuff-API-Key eintragen (bleibt lokal, wird nur maskiert angezeigt).
2. „MODELLE“ lädt die verfügbaren Modelle des Accounts, eines auswählen.
3. Speichern. Fragen gehen direkt an `https://freebuff.com/api/v1/paid`.

Zu jeder Frage schickt die App zwei bis drei passende Karten aus
`knowledge.py` als Kontext mit (`support_core.kontext_text`), damit das Modell
keine Einstellungen erfindet. Die Antwort ist auf `max_tokens = 450` begrenzt
und wird zur Sicherheit bei 1.400 Zeichen gekürzt.

Ohne Key oder ohne Verbindung fällt die App auf die Offline-Karten zurück;
ein Fehler wird angezeigt, nicht verschluckt. Jede Anfrage kostet Guthaben
des Accounts, in dem der Key angelegt wurde.

## Suchassistent

Der Reiter „Suche“ übersetzt einen Wunsch in einen prüfbaren Plan:

```
unter 700, nur Amazon, nur neu
→ Preisgrenze (max_preis): 700 €
→ Händler (active_haendler): nur Amazon DE (1 von 42)
→ Schritte: Händler wählen, Preis setzen, Scan starten …
```

Er setzt **nichts** selbst und ruft **keine** Shops ab — die Hilfe-App ist vom
Radar getrennt. Was der Radar nicht als Einstellung kennt (etwa „nur neu“),
steht als Hinweis im Plan, nicht als erfundener Schalter.

## Aufbau

```
support_app/
├── main.py                    Kivy-Oberfläche (fünf Reiter)
├── support_core.py            Fragen, Berichtsparser, Diagnose (ohne Kivy)
├── search_assistant.py        Suchwunsch → Einstellungen (ohne Kivy)
├── ai_client.py               KI-Aufruf und Key-Speicher (ohne Kivy)
├── shops.py                   Die 42 Shops des Radars
├── knowledge.py               Wissensbasis
├── buildozer.spec             Android-Build, Paket de.konsolenradar.support
├── make_icon.py               erzeugt Icon, adaptive Ebenen und ICO
├── icon.png                   512er Icon (Store/Launcher)
├── icon_fg.png / icon_bg.png  adaptives Icon (432er Ebenen)
├── icon.ico                   Windows-Icon
└── tests/                     79 Tests ohne Kivy (Kern, Suche, KI-Client)
```

## Tests

```bash
python -m unittest discover -s support_app/tests -v
```

Die 79 Tests brauchen weder Kivy noch Android und laufen auch unter Windows.

## Signierung (Release-APK)

Die App wird **nur noch als signiertes Release-APK** gebaut. Ein Debug-APK
gibt es nicht mehr als Download: es lässt sich nicht aktualisieren und wirkt
beim Sideload wie eine Bastelversion.

Der Workflow erwartet diese Repository-Secrets:

| Secret | Pflicht | Inhalt |
|---|---|---|
| `HILFE_KEYSTORE_BASE64` | ja | die `.p12`-Datei, base64-kodiert (eine Zeile) |
| `HILFE_KEYSTORE_PASSWORD` | ja | Passwort des Keystores |
| `HILFE_KEY_ALIAS` | nein | Key-Alias, Standard `hilfe` |
| `HILFE_KEY_PASSWORD` | nein | Key-Passwort, Standard = Keystore-Passwort |
| `HILFE_CERT_SHA256` | nein | erwarteter Zertifikats-Fingerabdruck; der Build bricht ab, wenn ein anderer Key signiert |

Fehlt `HILFE_KEYSTORE_BASE64`, baut der Workflow **kein** APK (der Job bleibt
grün und weist per Notice darauf hin). Die Windows-EXE ist davon unberührt.

### Keystore einmalig erzeugen

Auf einem Rechner mit JDK 17 (Windows: Git Bash oder PowerShell):

```bash
keytool -genkeypair -v -keystore hilfe-release.p12 -storetype PKCS12 \
  -alias hilfe -keyalg RSA -keysize 4096 -validity 10000 \
  -dname "CN=PS5 Pro Hilfe, O=Konsolenradar, C=DE"
# Passwort zweimal eingeben; danach die Datei sicher aufbewahren.
```

Base64 für das Secret (PowerShell):

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("hilfe-release.p12")) |
  Set-Content -NoNewline hilfe-release.b64
gh secret set HILFE_KEYSTORE_BASE64 < hilfe-release.b64
gh secret set HILFE_KEYSTORE_PASSWORD
gh secret set HILFE_KEY_ALIAS --body hilfe
```

`hilfe-release.p12` und `hilfe-release.b64` **niemals committen** (stehen in
`.gitignore`). Ohne diesen Schlüssel sind spätere Updates nicht mehr möglich —
Backup anlegen.

Der Fingerabdruck steht nach dem ersten Lauf in `bin/CERT-SHA256.txt` und in
den Release-Notes; als `HILFE_CERT_SHA256` hinterlegen, damit ein falscher Key
auffällt.

**Wichtig:** Das bisherige Debug-APK ist mit einem anderen Zertifikat
signiert. Android lässt es sich nicht durch das Release-APK überschreiben —
alte Version vorher deinstallieren.

## Android-APK bauen

Lokal braucht es Linux (oder WSL) mit Java 17, Android-SDK/NDK und Buildozer:

```bash
cd support_app
export P4A_RELEASE_KEYSTORE=~/keystores/hilfe-release.p12
export P4A_RELEASE_KEYSTORE_PASSWD='…'
export P4A_RELEASE_KEYALIAS=hilfe
export P4A_RELEASE_KEYALIAS_PASSWD='…'
buildozer -v android release
# Ergebnis: bin/*arm64-v8a_armeabi-v7a-release.apk (Universal, beide ABIs)
```

Gebaut wird für `arm64-v8a` und `armeabi-v7a`, also 64- und 32-Bit-ARM ab
Android 7 (API 24). Emulator/Chromebooks (x86_64) lassen sich in
`android.archs` ergänzen.

Der Workflow leitet aus der Universal-APK zusätzlich eine reine
`arm64-v8a`-Fassung ab (32-Bit-Bibliotheken entfernt, neu signiert). Sie ist
rund ein Drittel kleiner und reicht für alle Geräte der letzten Jahre; die
Universal-APK bleibt für alte 32-Bit-Geräte im Release.

Auf diesem Windows-Rechner ist kein Buildozer/Java/SDK installiert. Gebaut wird
über `.github/workflows/support-apk.yml`: Bei einem Push entsteht ein
release-signiertes APK als Artefakt, bei einem Tag `hilfe-v*` zusätzlich das
GitHub-Release mit APK und EXE. Ohne Keystore baut der Job bewusst kein APK.

## Windows-Version bauen

Die Oberfläche ist reines Kivy, deshalb läuft dieselbe App unter Windows.
PyInstaller packt sie in eine einzelne EXE:

```bash
cd support_app
python -m venv .venv-win
.venv-win/Scripts/python.exe -m pip install kivy==2.3.2 pyinstaller==6.22.3
.venv-win/Scripts/pyinstaller.exe --noconfirm --onefile --windowed \
  --name "PS5ProSearchAgent-Hilfe" main.py
# Ergebnis: dist/PS5ProSearchAgent-Hilfe.exe
```

Die EXE ist nicht signiert; Windows SmartScreen zeigt beim ersten Start
deshalb eine Warnung. Ein Selbsttest ohne Fenster:

```bash
dist/PS5ProSearchAgent-Hilfe.exe --selftest   # Exitcode 0 = ok
```

## Store-Paket

Beschreibung, Screenshots, Icon, Feature-Grafik, Datenschutztext und
Data-Safety-Antworten liegen unter `store/hilfe/`; die Upload-Reihenfolge steht
in `store/hilfe/README.md`. Veröffentlicht ist davon nichts.

## Grenzen der Hilfe

Die Antworten beschreiben den Stand v1.4. Ändert sich das Produkt, müssen
`knowledge.py` und die Tests mitgezogen werden — der Test
`test_alle_eintraege_vollstaendig` prüft nur Struktur, nicht inhaltliche
Aktualität.
