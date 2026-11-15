# Store-Audit — PS5 Pro Search Agent – Hilfe

Stand: 15. November 2026. Geprüft wurden das Store-Paket, die App-Metadaten
und der tatsächliche KI-Code. **Kein Upload, kein Rollout, kein Play-Upload.**

## Kurzfazit

Die formalen Textgrenzen und die Pflicht-Assets sind vorhanden; Titel, Kurz-
und Vollbeschreibung passen. **Store-reif ist das Paket noch nicht.** Es gibt
noch vier harte Blocker und mehrere operative Punkte. Die wichtigsten sind
der noch nicht vollständig policy-konforme KI-Meldeweg, der Markenname im
Play-Titel und die finale Content-Rating-/Zielgruppenentscheidung. Die
PNG-Formate, der Ollama-Hinweis in Screenshot 05 sowie die Freebuff-,
Data-Safety- und Privacy-Widersprüche wurden am 15.11.2026 behoben. Die
In-App-Meldefunktion und der Moderationsablauf sind am 15.11.2026 ergänzt.

Die Data-Safety-Angaben sind für einen reinen **internen** Testtrack laut Play
nicht verpflichtend; für geschlossenen Test und Produktion müssen sie korrekt
sein. Der interne Test ist also kein Freibrief für die übrigen Blocker.

## 1. Formale Grenzen

| Prüfung | Ist-Stand | Play-Grenze | Bewertung |
|---|---|---|---|
| Listing-Titel | `PS5 Pro Search Agent – Hilfe`, **28 Zeichen** | 30 | Länge ok; Marke offen |
| App-Label | `PS5 Pro Search Agent - Hilfe`, **28 Zeichen** | – | Länge ok; Bindestrich statt Gedankenstrich |
| Kurzbeschreibung | **74 Zeichen** | 80 | ok |
| Vollbeschreibung | **2.751 Zeichen** | 4.000 | ok |
| Icon | 512×512, **80.695 B, 32-bit RGBA (color_type 6)** | 32-bit PNG **mit Alpha**, max. 1.024 KB | **behoben (B3)** |
| Feature-Grafik | 1024×500, 24-bit RGB, 88.481 B | JPEG oder 24-bit PNG ohne Alpha | Format ok; Marke in der Grafik |
| Screenshots | 5× 1620×2880, 9:16, **24-bit RGB**, 79–250 KB | 2–8, je Seite 320–3.840 px, max. 8 MB, **24-bit PNG/JPEG ohne Alpha** | **behoben (B4)** |
| Tablet-/Chromebook-Shots | nicht vorhanden | optional | kein Blocker |

Die Angaben in `README.md` (74 / 2.751 Zeichen, fünf Screenshots) stimmen mit
den Dateien überein. Icon und Screenshots wurden am 15.11.2026 auf die
geforderten Formate umgestellt: `icon-512.png` ist jetzt RGBA, die fünf
Screenshots sind RGB.

## 2. Inhaltliche Widersprüche

### 2.1 Freebuff-Kosten (behoben)

`listing.de.md` bezeichnete Freebuff indirekt als kostenlos, obwohl der
Standardanbieter laut `PRIVACY.md` und `support_app/ai_client.py` über das
**Guthaben des Freebuff-Accounts** abgerechnet wird. Das Listing nennt jetzt
Freebuff ausdrücklich guthabenpflichtig und nur OpenRouter, Groq, Google AI
Studio und Mistral als Anbieter mit kostenlosen Kontingenten.

### 2.2 Gesprächsverlauf (behoben)

`PRIVACY.md` und `DATA_SAFETY.md` behaupteten, der bisherige Gesprächsverlauf
werde mitgesendet. Der einzige Aufruf in `support_app/main.py` übergibt aber
nur `frage` und `kontext`; `verlauf` bleibt `None`:

```python
ai_client.chat(zustand, frage, kontext=support_core.kontext_text(frage))
```

Damit wird **kein** früherer Verlauf übertragen. Die Datenschutztexte
beschreiben jetzt den tatsächlichen Code: Die App sendet nur die aktuelle
Frage, Kontextkarten und den Modellnamen.

### 2.3 Ollama im Android-Screenshot (behoben)

`assets/phone/05-ki.png` zeigte den Satz „… oder dein lokales Ollama“. Die
Android-App blendet Ollama jedoch aus, weil `localhost` dort das Telefon wäre
(`main.py`: `_anbieter_namen` filtert `ollama` auf Android/iOS). Der
Screenshot-Generator setzt für die Store-Aufnahmen jetzt
`main.kivy_platform = "android"`; Screenshot 05 wurde neu erzeugt und enthält
keinen Ollama-Hinweis mehr. Ein echter Android-Gerätetest bleibt O3.

### 2.4 Kleinere Konsistenzpunkte

- Listing-Titel nutzt einen Gedankenstrich (`–`), das App-Label einen
  Bindestrich (`-`). Kein Play-Blocker, aber vor einem Rebranding angleichen.
- Die frühere Statuszeile „Store-Texte und Grafiken: fertig“ ist nach diesem
  Audit auf **teilweise** korrigiert.
- Die 16 Themenkarten im Listing stimmen mit `knowledge.ENTRIES` überein.
- Die Datenschutz-URL ist öffentlich erreichbar: HTTP 200,
  `text/html; charset=utf-8`, ohne Login geprüft.

## 3. Data Safety

| Feld | Aktueller Stand | Problem | Nötige Antwort |
|---|---|---|---|
| Collected or shared? | **Collected + Shared** | Daten verlassen das Gerät und gehen an einen Drittanbieter | korrigiert |
| Ephemeral? | **Nein** | Die KI-Anbieter können Logs/Retention haben; ohne Garantie nicht ephemeral | korrigiert |
| Gesprächsverlauf | **nicht übertragen** | wird vom Code nicht gesendet; Doku korrigiert | behoben |
| Linked to identity? | **Nein** | Der API-Key ist ein Zugangs-Token zum Anbieterkonto, kein Konto beim Entwickler | als Nein beantwortet; keine Verknüpfung mit einem Entwicklerkonto |
| Personal info → Other info | als Datentyp angegeben | Die API-Key-Übertragung ist der einzige Kandidat; Frage und Kontext sind eher „Messages“ | Datentyp begründen; keine unnötigen Angaben |
| Data sold / Ads / Analytics | Nein | durch Code und fehlende SDKs gedeckt | ok |
| Encryption in transit | Ja | alle Android-Anbieter nutzen HTTPS; Ollama gibt es auf Android nicht | ok |
| Account deletion | entfällt | keine Konten beim Entwickler | ok |

Zusätzlich: Der KI-Request enthält nach aktuellem Code Frage, zwei bis drei
Hilfe-Karten, Modellname und den API-Key im `Authorization`-Header. Es gibt
**keine** Geräte-ID, keinen Standort, keine Kontakte und keine Analyse-SDKs.

In-App-Meldungen werden lokal mit ID, Kategorie, Notiz, Frage, Antwort,
Anbieter, Modell und Version gespeichert; der API-Key gehört nicht dazu. Die
App sendet sie nicht automatisch. E-Mail und Kopieren sind ausdrückliche
Nutzeraktionen; der Entwickler erhält die Angaben erst mit dem Versand der
E-Mail. Das ist kein zusätzlicher automatischer Datenfluss, aber im Review und
in der Datenschutzerklärung erklärt.

## 4. Content Rating und Zielgruppe

- **Zielgruppe:** In `PLAY_INTERNAL_TEST.md` ist **18+** hinterlegt, keine
  Ausrichtung auf Kinder/Families. Das passt zu `PRIVACY.md` („nicht an
  Kinder“), ist aber eine Produktentscheidung und im Play-Formular noch nicht
  gesetzt.
- **Content Rating:** Die Antworten (keine Gewalt, keine sexualisierten
  Inhalte, keine Sprache, keine Drogen, kein Glücksspiel, keine
  Nutzer-zu-Nutzer-Interaktion, keine Käufe, keine Werbung) sind plausibel.
  Es gibt aber **keine finale IARC-Bewertung**; „ohne Altersbeschränkung“ ist
  nur eine Erwartung. Das Formular ist noch nicht ausgefüllt.
- **KI-Inhalte:** Die Aussage „keine Nutzer-zu-Nutzer-Interaktion“ ist für
  Nutzer untereinander richtig, deckt aber die generative KI nicht ab. Die
  KI kann beliebige Antworten des externen Modells anzeigen; eine
  KI-spezifische Bewertung/Finalisierung fehlt.
- **AI-Generated-Content-Policy:** Die Policy gilt auch für die optionale
  Text-zu-Text-KI. Apps müssen eine **In-App-Möglichkeit zum Melden oder
  Flaggen anstößiger Inhalte** bieten, die Meldungen an den Entwickler
  bringt, ohne die App zu verlassen; die Reports müssen in Filterung und
  Moderation einfließen (siehe Quellen).
  - Der KI-Reiter hat jetzt **MELDEN**: Kategorie, optionale Notiz, lokale
    Meldungs-ID und die Aktionen **E-MAIL** und **KOPIEREN**.
  - Die Meldung wird lokal gespeichert. **E-MAIL** öffnet einen vorbereiteten
    Bericht im Mailprogramm; der Nutzer sendet ihn selbst. Eine direkte
    Zustellung an einen eigenen Meldeserver fehlt, daher ist der von Play
    geforderte Weg "ohne Verlassen der App" noch nicht vollständig belegt.
  - Eine eigene Output-Moderation jenseits von System-Prompt und
    Anbieterfiltern gibt es weiterhin nicht; die Reports fließen in den in
    `MODERATION.md` beschriebenen manuellen Ablauf ein.
  - Das bleibt **Blocker B1** bis der Zustellweg geklärt ist.
- **Review-Zugang:** Play verlangt, dass Reviewer alle App-Funktionen erreichen
  und testen können. Die Offline-Funktionen sind ohne Anmeldung zugänglich;
  die KI verlangt aber einen eigenen Anbieter-Key. Ein Review-Key oder
  Demo-Modus ist nicht hinterlegt. Damit können Reviewer weder eine echte
  KI-Antwort noch den Meldedialog testen. Das bleibt **O2**; vor dem Upload
  muss ein separater, limitierter Test-Key in Play Console unter App access
  hinterlegt werden, mit englischer Anleitung. Der Key gehört nicht ins Repo.

## 5. Markenrechtlicher Play-Titel

Der Play-Titel **„PS5 Pro Search Agent – Hilfe“** enthält „PS5“ und „PS5 Pro“,
Marken von Sony Interactive Entertainment. Das App-Label, die Feature-Grafik
(„PS5 PRO SEARCH AGENT“) und Screenshot 02 („PS5 Pro 2 TB“) führen die Marke
ebenfalls. Der Disclaimer in der Vollbeschreibung und in `PRIVACY.md` klärt
die fehlende Verbindung, ersetzt aber keine Erlaubnis.

- **Package-Name:** `de.konsolenradar.support` ist neutral; das ist gut.
- **Produktionsblocker:** Ohne markenrechtliche Klärung oder neutralen Titel
  ist die Produktionsfreigabe nicht vertretbar. Ein neutraler Name wie
  „Konsolen-Radar – Hilfe“ müsste App-Label, Listing, Feature-Grafik,
  Screenshot 02 und das AAB (neue Version) mitziehen.
- **Interner Test:** Der bestehende Titel kann für einen internen Test
  weiterverwendet werden, bleibt aber ein Policy-/Markenrisiko. Das ist keine
  Rechtsberatung.

## 6. Restliche Blocker

### Harte Blocker

| ID | Blocker | Ort | Nötige Aktion |
|---|---|---|---|
| B1 | KI-Meldeweg noch nicht vollständig policy-konform: lokale Meldung + E-Mail, keine direkte Zustellung, keine eigene Output-Moderation | KI-Reiter, `MODERATION.md` | Zustellweg klären, Reports auswerten, Review-Key und Moderation nachweisen |
| B2 | Markenname im Play-Titel und in App-Label/Feature/Screenshot | Listing, `buildozer*.spec`, Assets | Titel neutralisieren oder Markenrechte klären; AAB und Assets neu bauen |
| B9 | Keine finale IARC-Bewertung; KI-Inhalte im Fragebogen nicht abgedeckt | Play Console | Content-Rating-Fragebogen inkl. KI ausfüllen und Ergebnis übernehmen |
| B10 | Zielgruppe 18+ nur im internen Dokument; Play-Formular und Abstimmung mit Rating fehlen | Play Console | Zielgruppe setzen, 18+ begründen und mit Content Rating abgleichen |

### Behobene Asset-Blocker (15.11.2026)

| ID | vorher | jetzt |
|---|---|---|
| B3 | Icon 24-bit RGB ohne Alpha | `icon-512.png` als 32-bit RGBA neu erzeugt (80.695 B); Generator liefert RGBA |
| B4 | Screenshots RGBA mit Alpha | Alle fünf Screenshots als 24-bit RGB neu gespeichert (79–250 KB) |
| B5 | Screenshot 05 zeigte Ollama auf Android | Screenshot 05 mit Android-UI-Pfad neu erzeugt, ohne Ollama-Hinweis |

### Behobene Store-Widersprüche (15.11.2026)

| ID | vorher | jetzt |
|---|---|---|
| B6 | Data Safety nur „Shared“ | **Collected + Shared** in `DATA_SAFETY.md`; Kurzfassung in `PLAY_INTERNAL_TEST.md` angepasst |
| B7 | „Ephemeral: Ja“ und übertragener Gesprächsverlauf | **Ephemeral: Nein**; `PRIVACY.md` und `DATA_SAFETY.md` nennen keinen übertragenen Verlauf mehr |
| B8 | Listing ließ Freebuff kostenlos erscheinen | Freebuff ist im Listing ausdrücklich guthabenpflichtig; übrige Anbieter behalten die kostenlosen Kontingente |

### Operative Blocker

| ID | Blocker | Nötige Aktion |
|---|---|---|
| O1 | Datenschutz-Link in der App fehlt (1.2.0) | Link in der App ergänzen; neue Version bauen |
| O2 | Kein Test-Key/Demo für den KI-Review | Temporären, limitierten Review-Key in Play Console hinterlegen; Anleitung in `MODERATION.md` |
| O3 | Screenshots vom Desktop, kein echter Android-Gerätetest | Auf Android prüfen und Shots neu erzeugen |
| O4 | Play-Console-App, Entwicklerkonto, Upload-Key-Zuordnung und Testerliste fehlen | Beim Entwickler; kein Upload in diesem Schritt |
| O5 | AAB-Artefakt aus Lauf #4 läuft nach 14 Tagen ab | Vor Upload neu bauen oder gültiges Artefakt verwenden |

## 7. Was bereits passt

- Titel, Kurz- und Vollbeschreibung liegen innerhalb der Play-Grenzen.
- Feature-Grafik 1024×500, fünf Screenshots 1620×2880 (9:16), alle unter 8 MB.
- Icon 512×512 als 32-bit RGBA; Screenshots als 24-bit RGB ohne Alpha.
- Screenshot 05 wurde mit Android-UI-Pfad erzeugt und enthält keinen Ollama-Hinweis;
  der echte Gerätetest bleibt O3.
- 16 Themenkarten im Listing entsprechen `knowledge.ENTRIES`.
- Paket `de.konsolenradar.support`, Version 1.2.0, versionCode 10200,
  minSdk 24, targetSdk 36 und nur `INTERNET` sind konsistent.
- Signiertes AAB aus Lauf #4 und Upload-Zertifikat sind dokumentiert; das AAB
  ist vor der Meldefunktion gebaut und muss vor einem Upload neu erzeugt werden.
- Datenschutz-URL ist öffentlich erreichbar; keine Telemetrie, keine Werbung,
  keine Analyse-SDKs, Key liegt nur im privaten App-Speicher.
- Data-Safety-Basics (kein Verkauf, TLS, keine Konten beim Entwickler) sind
  konsistent mit dem Code, soweit sie reichen.
- In-App-Meldungen haben eine ID, sechs Kategorien, eine optionale Notiz und
  werden lokal gespeichert; E-Mail und Kopieren sind nutzerinitiiert. Der
  Moderationsablauf ist in `MODERATION.md` dokumentiert.

## 8. Empfohlene Reihenfolge

1. **KI-Policy:** Meldeweg und Moderationsprotokoll sind vorhanden. Jetzt den
   direkten Zustellweg oder die E-Mail-Akzeptanz klären und einen temporären
   Review-Key hinterlegen (B1, O2).
2. **Marke:** neutralen Titel entscheiden oder Rechte klären; danach App-Label,
   AAB, Feature und Screenshots neu bauen (B2, O3).
3. **Assets:** Die PNG-Formate sind umgesetzt; bei einem Rebranding müssen
   Feature, Screenshot 02 und die Android-Aufnahmen erneut erzeugt werden.
4. **Texte/Data Safety:** Die Widersprüche sind umgesetzt; bei Änderungen an
   KI-Anbietern oder Payload müssen Listing und Data-Safety-Tabelle erneut
   abgeglichen werden.
5. **Konsolenfelder:** Content Rating inkl. KI und Zielgruppe ausfüllen (B9,
   B10).
6. **Vor Upload:** In-App-Datenschutzlink, Gerätetest, Play-Console-App und
   gültiges AAB (O1, O3–O5).

## Quellen

- Google Play Data safety:
  <https://support.google.com/googleplay/android-developer/answer/10787469>
- Google Play AI-Generated Content:
  <https://support.google.com/googleplay/android-developer/answer/13985936>
- Google Play: Understanding the AI-Generated Content policy:
  <https://support.google.com/googleplay/android-developer/answer/14094294>
- Google Play: Best Practices to Safeguard AI-Generated Content:
  <https://support.google.com/googleplay/android-developer/answer/16353813>
- Google Play: Requirements for providing sign in details for review:
  <https://support.google.com/googleplay/android-developer/answer/15748846>
- Google Play Console Requirements (review access, App access):
  <https://support.google.com/googleplay/android-developer/answer/10788890>
- Google Play Icon-Spezifikation:
  <https://developer.android.com/distribute/google-play/resources/icon-design-specifications>
- App-Code: `support_app/main.py`, `support_app/ai_client.py`,
  `support_app/meldungen.py`, `support_app/links.py`
- Store-Dateien: `listing.de.md`, `DATA_SAFETY.md`, `PRIVACY.md`,
  `MODERATION.md`, `PLAY_INTERNAL_TEST.md`, `assets/`
