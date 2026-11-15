# Moderation von KI-Antworten — Hilfe-App

Stand: 15. November 2026. Gilt für die optionale KI im Reiter „KI“ der
Hilfe-App `de.konsolenradar.support`. Die Offline-Karten sind nicht Teil dieses
Meldewegs.

## 1. Meldeweg in der App

1. Nach einer KI-Antwort im Reiter **KI** auf **MELDEN** tippen.
2. Eine Kategorie wählen: sexuelle Inhalte, Gewalt oder Drohung, Hass oder
   Diskriminierung, Selbstverletzung, illegale Inhalte oder Sonstiges.
3. Optional eine kurze Notiz ergänzen.
4. **E-MAIL** speichert die Meldung lokal und öffnet das Mailprogramm mit einem
   vorbereiteten Bericht an `smiley.medical@gmail.com`. **KOPIEREN** speichert
   die Meldung lokal und legt den vollständigen Bericht in die Zwischenablage.

Die App überträgt eine Meldung **nicht automatisch** und betreibt keinen
Meldeserver. Der Entwickler erhält sie erst, wenn der Nutzer die vorbereitete
E-Mail im Mailprogramm absendet oder den kopierten Text selbst sendet.

Jede Meldung erhält eine ID im Format `M-JJJJMMTT-HHMMSS-XXXXXX`. Diese ID steht
im Bericht und in der App-Bestätigung. Sie ist der gemeinsame Schlüssel für
E-Mail, lokale Datei und Moderationsprotokoll.

## 2. Lokal gespeicherte Angaben

Die App speichert höchstens 50 Meldungen in `meldungen.json` im privaten
App-Datenverzeichnis. Gespeichert werden:

- Meldungs-ID und UTC-Zeitpunkt,
- Kategorie und optionale Notiz,
- die gemeldete Frage und Antwort,
- Anbieter, Modell und App-Version,
- Status `neu`.

Der API-Key wird **nicht** gespeichert. Die Meldung bleibt lokal, bis die App
deinstalliert wird; eine Meldung wird nicht automatisch an Dritte übertragen.
Der Nutzer kann den Bericht vor dem Versand im Mailprogramm prüfen und dort
bearbeiten oder abbrechen.

## 3. Triage und Fristen

Der Entwickler prüft Meldungen, die per E-Mail eingehen, anhand von ID und
Kategorie. Zielzeiten für den internen Test:

| Stufe | Beispiele | Erstreaktion | Maßnahme |
|---|---|---|---|
| **Kritisch** | CSAM, glaubhafte Gewaltdrohung, konkrete Anleitung zu schwerer Selbst- oder Fremdverletzung | innerhalb von 24 Stunden | betroffenen Anbieter/Modell sofort deaktivieren, Beweise sichern, Anbieter informieren; bei gesetzlicher Pflicht Behörden einschalten |
| **Hoch** | sexualisierte Inhalte, Hass, Belästigung, illegale Anleitung | 3 Werktage | Modell/Anbieter prüfen, Filter oder Prompt korrigieren, bei Bedarf Anbieter deaktivieren |
| **Mittel** | herabwürdigende oder irreführende Antwort ohne akute Gefahr | 7 Werktage | Prompt/Kontext korrigieren, Wiederholung testen, dokumentieren |
| **Niedrig** | sonstige Beschwerde, Fehlklassifikation | 14 Werktage | prüfen, Antwort oder Hilfe-Karte korrigieren |

Kritische Meldungen haben Vorrang vor allen anderen Arbeiten. Die Fristen sind
interne Ziele, keine Rechtsberatung und keine Zusage gegenüber Nutzern.

## 4. Moderationsschritte

1. **Eingang:** E-Mail und ID prüfen; bei fehlender ID die Angaben aus dem
   Bericht übernehmen und eine ID nachtragen.
2. **Reproduzieren:** Anbieter und Modell aus der Meldung verwenden, wenn ein
   eigener Testzugang vorhanden ist. Keine fremden Keys oder Konten nutzen.
3. **Bewerten:** Kategorie, Kontext, Wiederholbarkeit und Schweregrad festlegen.
   Bei akuter Gefahr zuerst sperren, dann dokumentieren.
4. **Handeln:** Eine oder mehrere Maßnahmen umsetzen:
   - System-Prompt oder Kontextkarten korrigieren,
   - Anbieter/Modell in der App deaktivieren oder aus der Auswahl entfernen,
   - den Anbieter über den Vorfall informieren,
   - einen Fix veröffentlichen und die Version im Protokoll nennen.
5. **Abschließen:** Ergebnis und Wirksamkeit prüfen, Reporter informieren, wenn
   eine Antwortadresse vorliegt, und den Vorgang im Protokoll schließen.

## 5. Moderationsprotokoll

Für jeden eingegangenen Bericht wird eine Zeile ergänzt. Die ID ist die
Meldungs-ID aus der App; ohne ID wird eine eigene Vorgangsnummer vergeben.
Keine API-Keys, vollständigen E-Mail-Header oder unnötigen personenbezogenen
Daten eintragen.

| Meldungs-ID | Eingang | Kategorie | Stufe | Maßnahme | Status | Abgeschlossen |
|---|---|---|---|---|---|---|
| `M-…` | TT.MM.JJJJ | … | … | … | offen / erledigt | TT.MM.JJJJ |

Aufbewahrung: E-Mail und Protokolleintrag nach Abschluss längstens 90 Tage
aufbewahren, danach löschen; gesetzliche Aufbewahrungspflichten bleiben
unberührt. Lokale Meldungen auf dem Gerät werden durch die Deinstallation
entfernt.

## 6. Abgleich mit der Play-AI-Policy

Google Play verlangt für Apps, die Inhalte mit generativer KI erzeugen, eine
**In-App-Möglichkeit zum Melden oder Flaggen anstößiger Inhalte**, ohne die App
zu verlassen, und die Nutzung dieser Rückmeldungen für Filterung und Moderation.
Die KI ist hier optional, aber die Policy gilt auch für optionale Funktionen.

Aktueller Stand:

- Die Meldeoberfläche und Kategorien sind **in der App** vorhanden.
- Die Meldung wird lokal gespeichert und kann aus der App per E-Mail oder
  Zwischenablage an den Entwickler gehen. Der eigentliche Versand erfolgt im
  Mailprogramm; eine direkte Serverzustellung aus der App gibt es nicht.
- Der Moderationsablauf mit ID, Triage, Maßnahmen und Protokoll ist in diesem
  Dokument festgelegt.
- Es gibt weiterhin keinen automatischen Output-Filter oder Klassifikator;
  Moderation stützt sich auf System-Prompt, Anbieterfilter und eingehende
  Meldungen.

Der E-Mail-Schritt ist ein bewusster Datenschutz-Kompromiss: Ohne Server
verlassen Daten das Gerät erst nach einer Nutzeraktion. Ob Play den E-Mail-Weg
als „ohne Verlassen der App“ akzeptiert, ist vor dem Review zu klären; falls
nicht, ist eine direkte, authentifizierte Zustellung an einen Meldeserver nötig.

## 7. Review-Zugang

Play muss die KI-Funktion im Review vollständig testen können. Die App hat keine
Anmeldung; die Offline-Funktionen sind direkt erreichbar. Die KI verlangt jedoch
einen eigenen Anbieter-Key. Ohne einen **temporären Review-Key** können Reviewer
weder eine echte KI-Antwort noch den Meldedialog testen.

Vor dem Upload:

1. Einen separaten, limitierten Test-Key bei einem Anbieter anlegen (kein
   Produktions-Key, kein Key im Repository).
2. In Play Console unter **App access** die englische Anleitung hinterlegen:
   KI öffnen → KEY → Anbieter/Modell → Test-Key eintragen → Frage senden →
   MELDEN → Kategorie wählen → E-MAIL oder KOPIEREN.
3. Den Key während des Reviews gültig halten und danach sperren.
4. Keine echten Nutzerdaten oder produktiven Keys in der Anleitung nennen.

Englische Review-Anleitung (in Play Console unter **App access** eintragen):

```text
No sign-in is required. All offline features are available immediately.
To test the optional AI feature:
1. Open the KI tab and tap KEY.
2. Select the provider, paste the review key, load the models, and save.
3. Send a question. The answer appears in the KI tab.
4. Tap MELDEN, choose a category, and tap E-MAIL or KOPIEREN.
5. E-MAIL opens the mail app with a prepared report; send it to complete
   the user-initiated report. KOPIEREN copies the same report.
The app does not send the report automatically. Use only the test key
provided for review.
```

Der Review-Key ist ein offener Betriebspunkt (O2), solange er nicht in Play
Console hinterlegt ist. Der E-Mail-Schritt der Meldung ist im Review als
manueller, nutzerinitiierter Versand zu erklären.

## Quellen

- Google Play AI-Generated Content:
  <https://support.google.com/googleplay/android-developer/answer/13985936>
- Google Play: Understanding the AI-Generated Content policy:
  <https://support.google.com/googleplay/android-developer/answer/14094294>
- Google Play: Best Practices to Safeguard AI-Generated Content:
  <https://support.google.com/googleplay/android-developer/answer/16353813>
- Google Play: Requirements for providing sign in details for review:
  <https://support.google.com/googleplay/android-developer/answer/15748846>
