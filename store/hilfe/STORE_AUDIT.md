# Store-Audit — PS5 Pro Search Agent – Hilfe

Stand: 15. November 2026. Geprüft wurden das Store-Paket, die App-Metadaten
und der tatsächliche KI-Code. **Kein Upload, kein Rollout, kein Play-Upload.**

## Kurzfazit

Die formalen Textgrenzen und die Pflicht-Assets sind vorhanden; Titel, Kurz-
und Vollbeschreibung passen. **Store-reif ist das Paket noch nicht.** Es gibt
noch sieben harte Blocker und mehrere operative Punkte. Die wichtigsten sind
die fehlende In-App-Meldung für KI-Inhalte und der Markenname im Play-Titel
und in den Grafiken. Die PNG-Formate von Icon und Screenshots sowie der
Ollama-Hinweis in Screenshot 05 wurden am 15.11.2026 behoben.

Die Data-Safety-Angaben sind für einen reinen **internen** Testtrack laut Play
nicht verpflichtend; für geschlossenen Test und Produktion müssen sie korrekt
sein. Der interne Test ist also kein Freibrief für die übrigen Blocker.

## 1. Formale Grenzen

| Prüfung | Ist-Stand | Play-Grenze | Bewertung |
|---|---|---|---|
| Listing-Titel | `PS5 Pro Search Agent – Hilfe`, **28 Zeichen** | 30 | Länge ok; Marke offen |
| App-Label | `PS5 Pro Search Agent - Hilfe`, **28 Zeichen** | – | Länge ok; Bindestrich statt Gedankenstrich |
| Kurzbeschreibung | **74 Zeichen** | 80 | ok |
| Vollbeschreibung | **2.689 Zeichen** | 4.000 | ok |
| Icon | 512×512, **80.695 B, 32-bit RGBA (color_type 6)** | 32-bit PNG **mit Alpha**, max. 1.024 KB | **behoben (B3)** |
| Feature-Grafik | 1024×500, 24-bit RGB, 88.481 B | JPEG oder 24-bit PNG ohne Alpha | Format ok; Marke in der Grafik |
| Screenshots | 5× 1620×2880, 9:16, **24-bit RGB**, 79–250 KB | 2–8, je Seite 320–3.840 px, max. 8 MB, **24-bit PNG/JPEG ohne Alpha** | **behoben (B4)** |
| Tablet-/Chromebook-Shots | nicht vorhanden | optional | kein Blocker |

Die Angaben in `README.md` (74 / 2.689 Zeichen, fünf Screenshots) stimmen mit
den Dateien überein. Icon und Screenshots wurden am 15.11.2026 auf die
geforderten Formate umgestellt: `icon-512.png` ist jetzt RGBA, die fünf
Screenshots sind RGB.

## 2. Inhaltliche Widersprüche

### 2.1 Freebuff-Kosten

`listing.de.md` sagt nach der Anbieterliste:

> „OpenRouter hat einen kostenlosen Free-Router, die anderen Anbieter
> kostenlose Kontingente.“

Freebuff ist der Standardanbieter, wird aber laut `PRIVACY.md` und
`support_app/ai_client.py` über das **Guthaben des Freebuff-Accounts**
abgerechnet. Die Aussage ist damit falsch bzw. mindestens missverständlich.
Korrektur: Freebuff ausdrücklich als guthabenpflichtig nennen; nur OpenRouter,
Groq, Google AI Studio und Mistral als kostenlose Kontingente bezeichnen.

### 2.2 Gesprächsverlauf

`PRIVACY.md` und `DATA_SAFETY.md` behaupten, der bisherige Gesprächsverlauf
werde mitgesendet. Der einzige Aufruf in `support_app/main.py` übergibt aber
nur `frage` und `kontext`; `verlauf` bleibt `None`:

```python
ai_client.chat(zustand, frage, kontext=support_core.kontext_text(frage))
```

Damit wird aktuell **kein** früherer Verlauf übertragen. Entweder müssen die
Datenschutztexte den tatsächlichen Code beschreiben, oder der Verlauf muss
bewusst implementiert und dann korrekt deklariert werden. Bis dahin ist die
Angabe ein Widerspruch (Blocker B7).

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
| Collected or shared? | **Shared** | Die Frage wird je Datentyp gestellt; Daten verlassen das Gerät **und** gehen an einen Drittanbieter | **Collected + Shared** |
| Ephemeral? | **Ja**, weil der Entwickler nichts speichert | Play verlangt, dass Daten nur im Speicher und nicht länger als für die Anfrage gehalten werden. Die vom Nutzer gewählten KI-Anbieter können Logs/Retention haben; ohne deren Garantie nicht belegbar | **Nein**, sofern keine Retention-Garantie vorliegt |
| Gesprächsverlauf | als übertragen dokumentiert | wird vom Code nicht gesendet | Doku korrigieren oder Code erweitern |
| Linked to identity? | **Nein** | Der API-Key ist ein Zugangs-Token zum Anbieterkonto; das ist kein Konto beim Entwickler, aber die Verknüpfung sollte begründet werden | Prüfen und konservativ beantworten |
| Personal info → Other info | als Datentyp angegeben | Die API-Key-Übertragung ist der einzige Kandidat; Frage und Kontext sind eher „Messages“ | Datentyp begründen; keine unnötigen Angaben |
| Data sold / Ads / Analytics | Nein | durch Code und fehlende SDKs gedeckt | ok |
| Encryption in transit | Ja | alle Android-Anbieter nutzen HTTPS; Ollama gibt es auf Android nicht | ok |
| Account deletion | entfällt | keine Konten beim Entwickler | ok |

Zusätzlich: Der KI-Request enthält nach aktuellem Code Frage, zwei bis drei
Hilfe-Karten, Modellname und den API-Key im `Authorization`-Header. Es gibt
**keine** Geräte-ID, keinen Standort, keine Kontakte und keine Analyse-SDKs.

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
- **AI-Generated-Content-Policy:** Apps, die Inhalte mit KI erzeugen, müssen
  eine **In-App-Möglichkeit zum Melden/Flaggen anstößiger Inhalte** bieten,
  ohne die App zu verlassen. Die App hat keine solche Funktion; GitHub-Issues
  oder E-Mail liegen außerhalb der App und erfüllen das nicht. Zusätzlich
  fehlt eine eigene Output-Moderation jenseits des System-Prompts. Das ist
  **Blocker B1** und gilt spätestens vor geschlossenem Test/Produktion.
- **Review-Zugang:** Für KI-Features verlangt Play im Review regelmäßig
  Zugang zu den Funktionen. Die App verlangt einen eigenen Anbieter-Key; ein
  Test-Key oder Demo-Modus ist nicht dokumentiert. Das ist ein Review-Risiko,
  kein automatischer formaler Blocker.

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
| B1 | Keine In-App-Meldung/Flag für anstößige KI-Inhalte; keine eigene Output-Moderation | KI-Reiter | Melde-/Flag-Funktion in der App ergänzen, Reports auswerten, Moderation dokumentieren |
| B2 | Markenname im Play-Titel und in App-Label/Feature/Screenshot | Listing, `buildozer*.spec`, Assets | Titel neutralisieren oder Markenrechte klären; AAB und Assets neu bauen |
| B6 | Data Safety nur „Shared“ statt „Collected + Shared“ | `DATA_SAFETY.md` | Beide Kategorien für die übertragenen Daten angeben |
| B7 | „Ephemeral: Ja“ und „Gesprächsverlauf“ nicht durch Code/Anbieter gedeckt | `DATA_SAFETY.md`, `PRIVACY.md` | Ephemeral auf Nein korrigieren; Verlauf aus Doku entfernen oder implementieren |
| B8 | Listing bezeichnet Freebuff indirekt als kostenlos | `listing.de.md` | Freebuff als guthabenpflichtig, übrige Anbieter als kostenlos formulieren |
| B9 | Keine finale IARC-Bewertung; KI-Inhalte im Fragebogen nicht abgedeckt | Play Console | Content-Rating-Fragebogen inkl. KI ausfüllen und Ergebnis übernehmen |
| B10 | Zielgruppe 18+ nur im internen Dokument; Play-Formular und Abstimmung mit Rating fehlen | Play Console | Zielgruppe setzen, 18+ begründen und mit Content Rating abgleichen |

### Behobene Asset-Blocker (15.11.2026)

| ID | vorher | jetzt |
|---|---|---|
| B3 | Icon 24-bit RGB ohne Alpha | `icon-512.png` als 32-bit RGBA neu erzeugt (80.695 B); Generator liefert RGBA |
| B4 | Screenshots RGBA mit Alpha | Alle fünf Screenshots als 24-bit RGB neu gespeichert (79–250 KB) |
| B5 | Screenshot 05 zeigte Ollama auf Android | Screenshot 05 mit Android-UI-Pfad neu erzeugt, ohne Ollama-Hinweis |

### Operative Blocker

| ID | Blocker | Nötige Aktion |
|---|---|---|
| O1 | Datenschutz-Link in der App fehlt (1.2.0) | Link in der App ergänzen; neue Version bauen |
| O2 | Kein Test-Key/Demo für den KI-Review | Review-Zugang ohne echten Nutzer-Key ermöglichen |
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
- Signiertes AAB und Upload-Zertifikat sind dokumentiert; kein Play-Upload.
- Datenschutz-URL ist öffentlich erreichbar; keine Telemetrie, keine Werbung,
  keine Analyse-SDKs, Key liegt nur im privaten App-Speicher.
- Data-Safety-Basics (kein Verkauf, TLS, keine Konten beim Entwickler) sind
  konsistent mit dem Code, soweit sie reichen.

## 8. Empfohlene Reihenfolge

1. **KI-Policy:** In-App-Melde-/Flag-Funktion und Moderation ergänzen;
   Review-Zugang klären (B1, O2).
2. **Marke:** neutralen Titel entscheiden oder Rechte klären; danach App-Label,
   AAB, Feature und Screenshots neu bauen (B2, O3).
3. **Assets:** Die PNG-Formate sind umgesetzt; bei einem Rebranding müssen
   Feature, Screenshot 02 und die Android-Aufnahmen erneut erzeugt werden.
4. **Texte/Data Safety:** Freebuff-Kosten, Verlauf, Collected + Shared und
   Ephemeral korrigieren (B6–B8).
5. **Konsolenfelder:** Content Rating inkl. KI und Zielgruppe ausfüllen (B9,
   B10).
6. **Vor Upload:** In-App-Datenschutzlink, Gerätetest, Play-Console-App und
   gültiges AAB (O1, O3–O5).

## Quellen

- Google Play Data safety:
  <https://support.google.com/googleplay/android-developer/answer/10787469>
- Google Play AI-Generated Content:
  <https://support.google.com/googleplay/android-developer/answer/13985936>
- Google Play Icon-Spezifikation:
  <https://developer.android.com/distribute/google-play/resources/icon-design-specifications>
- App-Code: `support_app/main.py`, `support_app/ai_client.py`
- Store-Dateien: `listing.de.md`, `DATA_SAFETY.md`, `PRIVACY.md`,
  `PLAY_INTERNAL_TEST.md`, `assets/`
