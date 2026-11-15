# Store-Paket — PS5 Pro Search Agent – Hilfe

Stand: 15. November 2026. **Nichts davon ist im Play Store veröffentlicht.**
Die Datenschutzerklärung ist als Teil des öffentlichen Repositorys abrufbar.

## Inhalt

| Datei | Zweck | Vorgabe |
|---|---|---|
| `listing.de.md` | Kurz- (74 Zeichen) und Vollbeschreibung (2.689 Zeichen) | 80 / 4.000 |
| `assets/icon-512.png` | App-Icon im Store | 512×512, 32-bit PNG |
| `assets/feature-1024x500.png` | Feature-Grafik | 1024×500, PNG/JPEG |
| `assets/phone/01-fragen.png` … `05-ki.png` | Screenshots | 1620×2880, 9:16, 2–8 Stück |
| `PRIVACY.md` | Datenschutzerklärung inkl. optionaler KI | öffentliche URL, siehe Checkliste |
| `DATA_SAFETY.md` | Antworten für „Data safety" | konservativ, mit KI-Variante |
| `PLAY_INTERNAL_TEST.md` | Checkliste, Konsolenfelder und Datenschutz-URL für den internen Test | kein Upload enthalten |

Screenshots und Grafiken werden erzeugt, nicht von Hand bearbeitet:

```bash
python tools/hilfe_screenshots.py     # fünf echte App-Aufnahmen
python tools/hilfe_store_assets.py    # Icon 512 + Feature-Grafik
```

## Reihenfolge im Play Console

1. **App anlegen** (Paketname `de.konsolenradar.support`, darf nie wechseln).
2. **Store-Eintrag:** Kurz-/Vollbeschreibung aus `listing.de.md`, Icon, Feature-Grafik,
   Screenshots in der Reihenfolge 01–05.
3. **Datenschutz:** öffentliche URL aus `PLAY_INTERNAL_TEST.md` eintragen; im
   Data-Safety-Formular die Tabelle aus `DATA_SAFETY.md` übernehmen (Variante mit KI).
4. **Content rating:** Fragebogen ausfüllen — keine Gewalt, keine Käufe, keine
   Werbung, Nutzerinteraktion nur mit eigenem API-Anbieter.
5. **App-Inhalte:** Zielgruppe, keine Nachrichtenfunktion zwischen Nutzern,
   keine Standortfreigabe.
6. **Testing:** interner Test → geschlossener Test (bei neuen Privatkonten
   Pflicht, mindestens 12 Tester/14 Tage) → Produktion.

## Noch offen vor dem ersten Upload

- **AAB:** Signiertes AAB ist gebaut (Support-AAB-Lauf #4) und als Artefakt
  verfügbar. Der Upload in die Play Console und die Zuordnung des Upload-Keys
  stehen noch aus; die Checkliste steht in `PLAY_INTERNAL_TEST.md`.
- **Öffentliche Datenschutz-URL:** Die GitHub-URL der `PRIVACY.md` ist aktiv und
  ohne Login erreichbar. Eine eigene Pages-Seite ist bewusst nicht aktiviert.
- **Datenschutz-Link in der App:** In 1.2.0 nicht vorhanden; vor der Produktion
  ergänzen, damit die Erklärung auch aus der App erreichbar ist.
- **Play-Entwicklerkonto:** Konto, Identitätsprüfung und Testphase liegen beim
  Entwickler, nicht im Repo.
- **Gerätetest:** Die Screenshots stammen vom Desktop-Build; vor dem Upload
  einmal auf einem echten Android-Gerät gegenprüfen (Layout, Icon, KI-Key).

## Nicht Teil des Pakets

Inhaltsbewertung als Datei, Marketingtexte für andere Sprachen, Pressemappe.
