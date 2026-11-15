# Interner Play-Test — Hilfe-App 1.2.0

Stand: 15. November 2026. **Vorbereitung, kein Upload.** Es wurde nichts in die
Play Console hochgeladen, kein Rollout gestartet und kein Release veröffentlicht.
Der interne Test bleibt ein reiner Testtrack; eine Produktionsfreigabe ist nicht
Teil dieses Schritts.

## 1. Ist-Stand

| Baustein | Status | Nachweis |
|---|---|---|
| AAB gebaut und signiert | **fertig** | Support-AAB-Lauf [#4](https://github.com/xsensenmannx/PS5PRoAgent/actions/runs/43723024167), `completed/success` |
| Paket / Version | **fertig** | `de.konsolenradar.support`, `versionName 1.2.0`, `versionCode 10200` |
| Signatur | **fertig** | Upload-Key, Zertifikat `f99782703ce8a45e55ebf6174611024e42128e169831fd57bc34614563f7042e` |
| Store-Texte und Grafiken | **teilweise** | Formate ok; Marken-/Listingblocker siehe `STORE_AUDIT.md` |
| Öffentliche Datenschutz-URL | **fertig** | GitHub-Link, siehe Abschnitt 2, HTTP 200 ohne Login |
| Play-Console-App | **offen** | muss einmalig angelegt werden |
| App-Inhalte / Data Safety | **vorbereitet, zu korrigieren** | Antworten in `DATA_SAFETY.md`; Abweichungen und Blocker siehe `STORE_AUDIT.md` |
| KI-Policy / In-App-Meldung | **offen** | keine Melde-/Flag-Funktion für KI-Inhalte; Play-Policy siehe `STORE_AUDIT.md` |
| Content Rating / Zielgruppe | **vorbereitet** | 18+ vorgesehen; finale IARC-Bewertung und Konsolenfelder fehlen |
| Datenschutz-Link in der App | **offen** | in 1.2.0 nicht vorhanden; vor Produktion ergänzen |
| Interner Test / Upload | **nicht ausgeführt** | bewusst zurückgestellt |

### AAB-Artefakt

- Lauf: `43723024167` (Support AAB #4)
- Artefakt: `ps5pro-search-agent-hilfe-aab`, 119.602.444 Bytes
- Enthält: `support-1.2.0-arm64-v8a_armeabi-v7a-release.aab` (39.747.908 Bytes),
  Universal-APK, `.apks`, `AAB-SHA256SUMS`, `buildozer.log`
- SHA-256 AAB: `c9bcf0154fbf9e2421fbc5970b2fcd28b2fe6843d0214f7d3d904184eefef645`
- Ablauf: Das Artefakt wird 14 Tage aufbewahrt. Ist es abgelaufen, den Lauf über
  **Actions → Support AAB → Run workflow** neu starten.

Download für den Upload:

```bash
gh run download 43723024167 -n ps5pro-search-agent-hilfe-aab
```

## 2. Öffentliche Datenschutz-URL

**URL für das Feld „Datenschutzerklärung“:**

<https://github.com/xsensenmannx/PS5PRoAgent/blob/main/store/hilfe/PRIVACY.md>

Am 15. November 2026 geprüft:

- HTTP **200**, `Content-Type: text/html; charset=utf-8`
- ohne Login und ohne Regionalsperre erreichbar
- klar als „Datenschutzerklärung — PS5 Pro Search Agent – Hilfe“ überschrieben
- nennt App und Entwickler `xsensenmannx` sowie einen Kontaktweg
- kein PDF; die URL liefert eine HTML-Seite
- für Besucher nicht editierbar

Die Datei liegt im öffentlichen Repository; es wurde **keine neue Seite
veröffentlicht**. Änderungen an `PRIVACY.md` auf `main` sind sofort über dieselbe
URL sichtbar.

Eine eigene GitHub-Pages-Seite ist bewusst **nicht** aktiviert. Das wäre eine
separate Veröffentlichung und ist für den internen Test nicht nötig. Sollte die
Play-Prüfung später eine eigene Seite verlangen, kann sie aus `docs/` ergänzt
werden; die Datenschutz-URL bleibt unabhängig davon ein Pflichtfeld.

## 3. Benötigte Konsolenfelder

### App anlegen

| Feld | Wert |
|---|---|
| App-Name | `PS5 Pro Search Agent – Hilfe` (28 Zeichen, max. 30) |
| Paketname | `de.konsolenradar.support` — **nicht änderbar**, muss zum AAB passen |
| Standardsprache | Deutsch (`de-DE`) |
| App oder Spiel | **App** |
| Kostenlos / kostenpflichtig | **Kostenlos** |
| Kategorie | **Tools** |
| Kontakt-E-Mail | `smiley.medical@gmail.com` |
| Website (optional) | `https://github.com/xsensenmannx/PS5PRoAgent` |
| Datenschutz-URL | siehe Abschnitt 2 |

> **Markenhinweis:** Der Titel nennt „PS5“. Für die Radar-Play-Version wurde
> bewusst auf „Konsolen-Radar“ umgestellt. Der interne Test kann mit dem
> bestehenden Titel laufen; vor einer Produktionsfreigabe den Titel
> markenrechtlich prüfen und gegebenenfalls App-Label und Listing auf einen
> neutralen Namen umstellen.

### Store-Eintrag

| Feld | Wert / Quelle |
|---|---|
| Kurzbeschreibung | 74 Zeichen aus `listing.de.md` |
| Vollbeschreibung | 2.689 Zeichen aus `listing.de.md` (max. 4.000) |
| App-Icon | `assets/icon-512.png` (512×512) |
| Feature-Grafik | `assets/feature-1024x500.png` (1024×500) |
| Telefon-Screenshots | `assets/phone/01-fragen.png` … `05-ki.png` (1620×2880) |
| App-Kategorie | Tools |

### App-Inhalte / Richtlinien

| Feld | Antwort |
|---|---|
| Datenschutzerklärung | URL aus Abschnitt 2 eintragen |
| Werbung | **Nein** |
| In-App-Käufe | **Nein** |
| App-Zugriff | **Alle Funktionen ohne Anmeldung**; die KI ist optional und braucht einen eigenen Anbieter-Key |
| Zielgruppe | **18+**, keine Ausrichtung auf Kinder/Families; Play-Formular noch nicht ausgefüllt |
| Content Rating | IARC-Fragebogen: keine Gewalt, keine sexualisierten Inhalte, keine Sprache, keine Drogen, kein Glücksspiel, keine Nutzer-zu-Nutzer-Interaktion, keine Standortfreigabe, keine Käufe, keine Werbung. KI-Inhalte ergänzen; Erwartung „ohne Altersbeschränkung“ ist nicht final. Endgültig entscheidet IARC. |
| News-App | **Nein** |
| COVID-19-Kontaktverfolgung | **Nein** |
| Regierungs-App | **Nein** |
| Finanzfunktionen | **Nein** |
| Gesundheitsfunktionen | **Nein** |
| Data Safety | Tabelle aus `DATA_SAFETY.md`, Variante **mit KI** |

Data-Safety-Kurzfassung:

- Es werden Daten **geteilt**: „Personal info → Other info“ und
  „Messages → Other in-app messages“.
- Zweck: **App functionality**; nur optional, wenn der Nutzer einen Anbieter
  wählt, einen eigenen Key einträgt und eine Frage sendet.
- **Ephemeral** ist derzeit nicht belegbar, solange die Retention der
  KI-Anbieter nicht geklärt ist; nicht mit der Identität verknüpft (zu prüfen),
  TLS-verschlüsselt, kein Verkauf, keine Werbe- oder Analyse-SDKs.
- Keine Konten beim Entwickler; Löschung lokal über Key entfernen oder
  Deinstallation. Beim gewählten KI-Anbieter gelten dessen Fristen.

### Interner Test

| Feld | Wert |
|---|---|
| Track | **Interner Test** (Internal testing) |
| Release-Name | `1.2.0 (10200) – intern` |
| AAB | siehe Abschnitt 1 |
| Testphase | nicht Produktion; kein geschlossener Test, keine 12-Tester-Frist |
| Tester | eigene E-Mail-Liste oder Google Group, max. 100 |
| Länder | Deutschland, Österreich, Schweiz (deutschsprachig) |
| Feedback | `smiley.medical@gmail.com` und GitHub-Issues |
| Release-Notes | „Erster interner Test: Offline-Hilfe, Suchplan, Diagnose und optionale KI mit eigenem Anbieter-Key.“ |

## 4. Checkliste

### Technisch vorbereitet

- [x] Signiertes AAB aus der Pipeline, Paket und Version geprüft
- [x] Upload-Zertifikat bekannt und dokumentiert
- [x] Store-Texte, Icon, Feature-Grafik und fünf Screenshots vorhanden
- [x] Öffentliche Datenschutz-URL erreichbar
- [x] Data-Safety- und Content-Rating-Antworten vorbereitet
- [x] Icon als 32-bit PNG mit Alpha, Screenshots als 24-bit RGB ohne Alpha
- [x] Screenshot 05 mit Android-UI-Pfad erzeugt (kein Ollama im Android-Listing)
- [ ] KI-Melde-/Flag-Funktion und Moderation ergänzen
- [ ] Listing-Freebuff-Kosten und Data-Safety-/Privacy-Verlauf korrigieren
- [ ] Finale IARC-Bewertung inkl. KI und Zielgruppe in der Konsole setzen
- [ ] Datenschutz-Link in der App ergänzen (vor Produktion, nicht Teil von 1.2.0)
- [ ] Markenrechtlichen Play-Titel prüfen (siehe Hinweis oben)
- [ ] Gerätetest auf einem echten Android-Gerät

### In der Play Console (noch nicht ausgeführt)

- [ ] Entwicklerkonto verifiziert, Zwei-Faktor-Anmeldung aktiv
- [ ] App mit Paket `de.konsolenradar.support` angelegt
- [ ] Store-Eintrag aus `listing.de.md` und den Assets befüllt
- [ ] Datenschutz-URL eingetragen
- [ ] App-Zugriff, Werbung, Zielgruppe und Content Rating beantwortet
- [ ] Data-Safety-Formular ausgefüllt
- [ ] Internen Testtrack angelegt und Tester eingetragen
- [ ] AAB hochgeladen, Release geprüft und Rollout gestartet
- [ ] Opt-in-Link an die Tester verschickt

### Bewusst nicht ausgeführt

- [ ] Kein AAB in die Play Console hochgeladen
- [ ] Kein Rollout in einen Test- oder Produktionstrack
- [ ] Keine Produktionsfreigabe beantragt
- [ ] Keine GitHub-Pages-Seite aktiviert

## 5. Reihenfolge für den eigentlichen Upload

1. AAB-Artefakt herunterladen und entpacken.
2. Play Console → **App anlegen**; Paketname exakt `de.konsolenradar.support`.
3. Store-Eintrag und Grafiken aus `store/hilfe/` übernehmen.
4. **App-Inhalte** vollständig beantworten; Datenschutz-URL und Data Safety
   eintragen.
5. **Testing → Interner Test → Neuen Release erstellen**, AAB hochladen,
   Release-Notes eintragen.
6. Release prüfen und **Rollout auf „Interner Test“** starten.
7. Tester-Liste anlegen, Opt-in-Link kopieren und verschicken.
8. Installation und die fünf Reiter auf einem echten Gerät prüfen.

Schritt 5–7 sind hier ausdrücklich **nicht** ausgeführt. Für den Testtrack ist
keine Produktionsprüfung nötig; die App bleibt trotzdem eine Vorabversion.
