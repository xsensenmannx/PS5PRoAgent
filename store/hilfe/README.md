# Store-Paket — PS5 Pro Search Agent – Hilfe

Stand: November 2026. **Nichts davon ist veröffentlicht.**

## Inhalt

| Datei | Zweck | Vorgabe |
|---|---|---|
| `listing.de.md` | Kurz- (74 Zeichen) und Vollbeschreibung (2.689 Zeichen) | 80 / 4.000 |
| `assets/icon-512.png` | App-Icon im Store | 512×512, 32-bit PNG |
| `assets/feature-1024x500.png` | Feature-Grafik | 1024×500, PNG/JPEG |
| `assets/phone/01-fragen.png` … `05-ki.png` | Screenshots | 1620×2880, 9:16, 2–8 Stück |
| `PRIVACY.md` | Datenschutzerklärung inkl. optionaler KI | öffentliche URL nötig |
| `DATA_SAFETY.md` | Antworten für „Data safety" | konservativ, mit KI-Variante |

Screenshots und Grafiken werden erzeugt, nicht von Hand bearbeitet:

```bash
python tools/hilfe_screenshots.py     # fünf echte App-Aufnahmen
python tools/hilfe_store_assets.py    # Icon 512 + Feature-Grafik
```

## Reihenfolge im Play Console

1. **App anlegen** (Paketname `de.konsolenradar.support`, darf nie wechseln).
2. **Store-Eintrag:** Kurz-/Vollbeschreibung aus `listing.de.md`, Icon, Feature-Grafik,
   Screenshots in der Reihenfolge 01–05.
3. **Datenschutz:** URL der veröffentlichten `PRIVACY.md` eintragen; im
   Data-Safety-Formular die Tabelle aus `DATA_SAFETY.md` übernehmen (Variante mit KI).
4. **Content rating:** Fragebogen ausfüllen — keine Gewalt, keine Käufe, keine
   Werbung, Nutzerinteraktion nur mit eigenem API-Anbieter.
5. **App-Inhalte:** Zielgruppe, keine Nachrichtenfunktion zwischen Nutzern,
   keine Standortfreigabe.
6. **Testing:** interner Test → geschlossener Test (bei neuen Privatkonten
   Pflicht, mindestens 12 Tester/14 Tage) → Produktion.

## Noch offen vor dem ersten Upload

- **AAB statt APK:** Play verlangt ein Android App Bundle. Für den Radar
  existiert `buildozer.play.spec` + `play-aab.yml`; für die Hilfe fehlt das
  Gegenstück (eigener Upload-Key, eigenes Paket).
- **Öffentliche Datenschutz-URL:** `PRIVACY.md` muss gehostet werden
  (GitHub Pages oder eine eigene Seite); die URL kommt in Listing und Console.
- **Play-Entwicklerkonto:** Konto, Identitätsprüfung und Testphase liegen beim
  Entwickler, nicht im Repo.
- **Gerätetest:** Die Screenshots stammen vom Desktop-Build; vor dem Upload
  einmal auf einem echten Android-Gerät gegenprüfen (Layout, Icon, KI-Key).

## Nicht Teil des Pakets

Inhaltsbewertung als Datei, Marketingtexte für andere Sprachen, Pressemappe.
