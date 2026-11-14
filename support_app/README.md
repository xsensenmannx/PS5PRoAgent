# PS5 Pro Search Agent – Hilfe

Eigenständige Offline-Support-App für den PS5 Pro Search Agent (Konsolen-Radar).
Sie erklärt Einrichtung, Alarme, Webhooks, Konfidenz und Grenzen der Radar-App
und prüft einen eingefügten Diagnosebericht.

**Kein Netzwerk, kein Konto, keine Telemetrie.** Die App hat keine
Internet-Berechtigung; alle Antworten stammen aus `knowledge.py`.

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

## Was sie nicht kann

- **Sie liest keine Daten des Radars.** Android erlaubt keiner App den Zugriff
  auf den privaten Speicher einer anderen. Deshalb der Weg über den
  Diagnose-Text: kopieren, einfügen, prüfen.
- Keine Modell-Antworten, kein LLM, keine Internetquelle. Jede Antwort ist
  eine feste, prüfbare Karte.

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
├── main.py                    Kivy-Oberfläche (vier Reiter)
├── support_core.py            Fragen, Berichtsparser, Diagnose (ohne Kivy)
├── search_assistant.py        Suchwunsch → Einstellungen (ohne Kivy)
├── shops.py                   Die 42 Shops des Radars
├── knowledge.py               Wissensbasis
├── buildozer.spec             Android-Build, Paket de.konsolenradar.support
├── icon.png                   App-Icon
└── tests/test_support_core.py Tests ohne Kivy
```

## Tests

```bash
python -m unittest discover -s support_app/tests -v
```

Die Tests brauchen weder Kivy noch Android und laufen auch unter Windows.

## Android-APK bauen

Lokal braucht es Linux (oder WSL) mit Java 17, Android-SDK/NDK und Buildozer:

```bash
cd support_app
buildozer -v android debug
# Ergebnis: bin/*.apk
```

Gebaut wird für `arm64-v8a` und `armeabi-v7a`, also 64- und 32-Bit-ARM ab
Android 7 (API 24). Emulator/Chromebooks (x86_64) lassen sich in
`android.archs` ergänzen.

Auf diesem Windows-Rechner ist kein Buildozer/Java/SDK installiert. Der
vorgesehene Weg ist der Workflow `.github/workflows/support-apk.yml`
(manuell startbar, baut ein Debug-APK und lädt es als Artefakt hoch).

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

## Grenzen der Hilfe

Die Antworten beschreiben den Stand v1.4. Ändert sich das Produkt, müssen
`knowledge.py` und die Tests mitgezogen werden — der Test
`test_alle_eintraege_vollstaendig` prüft nur Struktur, nicht inhaltliche
Aktualität.
