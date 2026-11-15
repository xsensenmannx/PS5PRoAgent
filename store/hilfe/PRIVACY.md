# Datenschutzerklärung — PS5 Pro Search Agent – Hilfe

Stand: 15. November 2026. Gilt für die Android-App
`de.konsolenradar.support` und die Windows-Version derselben Hilfe.

## Kurzfassung

Die Hilfe-App arbeitet ohne Konto, ohne Werbung, ohne Analyse und ohne
Telemetrie. Solange du die optionale KI nicht nutzt, verlässt keine Anfrage dein
Gerät. Für die KI brauchst du deinen eigenen API-Key; gesendet wird nur deine
Frage an die Freebuff-API. Der Entwickler erhält davon nichts.

## Verantwortlich

Entwickler der App ist xsensenmannx. Kontakt für Datenschutzfragen:
<https://github.com/xsensenmannx/PS5PRoAgent/issues>.

## Welche Daten auf dem Gerät bleiben

- **KI-Zugang:** API-Key und gewähltes Modell in `ki.json` im privaten
  App-Speicher (Android: App-Datenverzeichnis, Windows: `%APPDATA%`). Die Datei
  ist für andere Apps nicht lesbar; unter Android ist die Cloud-Sicherung
  deaktiviert.
- **Kein Verlauf:** Fragen und Antworten werden nicht gespeichert. Sie stehen nur
  im Arbeitsspeicher, solange der Reiter geöffnet ist.
- **Keine Kennungen:** Die App liest keine Geräte-ID, keinen Standort, keine
  Kontakte, keine Dateien und keine installierten Apps aus.

Diese Daten verlassen das Gerät nicht und werden nicht an den Entwickler
übertragen. Löschen: Key im KI-Dialog entfernen oder die App deinstallieren.

## Berechtigungen

Die Android-Version fordert nur `INTERNET` an. Sie wird ausschließlich für die
optionale KI gebraucht. Ohne Key baut die App keine Verbindung auf.

## Optionale KI (nur mit eigenem Key)

Wenn du im Reiter „KI“ einen Key einträgst und eine Frage sendest, überträgt die
App über HTTPS an die Freebuff-API (`https://freebuff.com/api/v1/paid`):

- den Text deiner Frage,
- den bisherigen Gesprächsverlauf dieses Reiters (nur zur Laufzeit),
- den Namen des gewählten Modells,
- deinen API-Key als `Authorization: Bearer …`.

Zweck ist ausschließlich die Erzeugung der Antwort. Empfänger ist der
API-Betreiber Freebuff; es gelten dessen Datenschutzhinweise und die Bedingungen
deines dortigen Accounts. Die Nutzung ist freiwillig und kostenpflichtig
(Guthaben deines Accounts). Ohne Key oder ohne Internet bleibt die App offline
und antwortet aus den mitgelieferten Themenkarten.

Der Entwickler:

- betreibt keinen eigenen Server für die App,
- protokolliert keine Fragen, Antworten oder Keys,
- hat keinen Zugriff auf deinen Account oder dein Guthaben,
- verkauft keine Daten und gibt sie nicht zu Werbezwecken weiter.

## Keine Werbung, keine Analyse, keine Crash-Berichte

Die App enthält keine Werbe- oder Analyse-SDKs, keine Werbe-ID und keine
automatischen Fehlerberichte an Dritte. Abstürze bleiben auf dem Gerät.

## Kinder

Die App richtet sich nicht an Kinder und erhebt wissentlich keine Daten von
Kindern. Die KI-Funktion setzt einen eigenen Account bei einem API-Anbieter
voraus.

## Deine Rechte

Da beim Entwickler keine personenbezogenen Daten gespeichert werden, gibt es
dort nichts, worüber Auskunft erteilt werden könnte. Für Daten, die du selbst an
die Freebuff-API sendest, wende dich an den dortigen Anbieter. Lokale Daten
entfernst du durch Löschen des Keys oder Deinstallation der App.

## Änderungen

Wird die App um Funktionen mit Datenübertragung erweitert, wird diese
Erklärung vor dem Update angepasst und mit dem neuen Stand veröffentlicht.

## Marken

„PlayStation“, „PS5“ und „PS5 Pro“ sind Marken von Sony Interactive
Entertainment. Diese App ist ein unabhängiges Hilfsmittel und steht in keiner
Verbindung zu Sony, den genannten Händlern oder ihren Tochtergesellschaften.
