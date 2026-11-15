# Datenschutzerklärung — PS5 Pro Search Agent – Hilfe

Stand: 15. November 2026. Gilt für die Android-App
`de.konsolenradar.support` und die Windows-Version derselben Hilfe.

## Kurzfassung

Die Hilfe-App arbeitet ohne Konto, ohne Werbung, ohne Analyse und ohne
Telemetrie. Solange du die optionale KI nicht nutzt, verlässt keine Anfrage dein
Gerät. Für die KI brauchst du deinen eigenen API-Key bei einem Anbieter deiner
Wahl; gesendet wird nur deine Frage an genau diesen Anbieter. Der Entwickler
betreibt keinen Server und erhält von normalen KI-Anfragen nichts. Eine
freiwillige Meldung wird nur nach deiner ausdrücklichen E-Mail-Aktion
übermittelt (siehe unten).

## Verantwortlich

Entwickler der App ist xsensenmannx. Kontakt für Datenschutzfragen:
<https://github.com/xsensenmannx/PS5PRoAgent/issues>.

## Welche Daten auf dem Gerät bleiben

- **KI-Zugang:** je Anbieter ein eigener API-Key und das gewählte Modell in
  `ki.json` im privaten App-Speicher (Android: App-Datenverzeichnis, Windows:
  `%APPDATA%`). Die Datei ist für andere Apps nicht lesbar; unter Android ist
  die Cloud-Sicherung deaktiviert. Alte Keys aus früheren Versionen werden
  übernommen.
- **Kein Gesprächsverlauf:** Fragen und Antworten werden nicht als Verlauf
  gespeichert. Sie stehen nur im Arbeitsspeicher, solange der Reiter geöffnet
  ist. Eine ausdrücklich gemeldete Antwort wird ausschließlich als lokale
  Meldung gespeichert (siehe unten).
- **Meldungen:** Wenn du eine KI-Antwort meldest, speichert die App ID,
  Zeitpunkt, Kategorie, optionale Notiz, Frage, Antwort, Anbieter, Modell und
  App-Version in `meldungen.json` im privaten App-Speicher. Der API-Key wird
  nicht gespeichert. Es bleiben höchstens 50 Meldungen lokal.
- **Keine Kennungen:** Die App liest keine Geräte-ID, keinen Standort, keine
  Kontakte, keine Dateien und keine installierten Apps aus.

Diese lokalen Daten verlassen das Gerät nicht. Eine Meldung wird nur dann an
den Entwickler übertragen, wenn du sie im Mailprogramm selbst absendest; ohne
diese Aktion erhält der Entwickler nichts. Löschen: Key im KI-Dialog entfernen,
Meldungen durch Deinstallation der App entfernen.

## Berechtigungen

Die Android-Version fordert nur `INTERNET` an. Sie wird ausschließlich für die
optionale KI gebraucht. Ohne Key baut die App keine Verbindung auf.

## Optionale KI (nur mit eigenem Key)

Im Reiter „KI“ wählst du den Anbieter und trägst dort deinen eigenen Key ein.
Erst wenn du eine Frage sendest, überträgt die App an **genau diesen Anbieter**:

- den Text deiner Frage,
- zwei bis drei passende Hilfe-Karten als Kontext,
- den Namen des gewählten Modells,
- deinen API-Key als `Authorization: Bearer …`.

Empfänger ist der von dir gewählte Betreiber:

| Anbieter | Adresse |
|---|---|
| Freebuff (Standard) | `https://freebuff.com/api/v1/paid` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Google AI Studio | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Mistral | `https://api.mistral.ai/v1` |
| Ollama (lokal, nur Windows) | `http://localhost:11434/v1` |

Bei Ollama bleibt alles auf deinem Rechner; die App spricht nur mit dem lokal
installierten Modell. Auf Android wird Ollama nicht angeboten, weil `localhost`
dort das Telefon selbst wäre.

Freebuff rechnet über das Guthaben deines Accounts ab. OpenRouter, Groq, Google
AI Studio und Mistral haben kostenlose Kontingente mit Tages- oder Monatslimit;
Einzelheiten stehen bei deinem Anbieter. Ollama kostet nichts. Bei den anderen Anbietern gelten deren Datenschutzhinweise
und die Bedingungen deines dortigen Accounts. OpenRouter kennzeichnet kostenlose
Modelle mit `:free`; Kosten und Limits richten sich nach deinem Account.
Zweck ist ausschließlich die Erzeugung der Antwort. Die Nutzung ist freiwillig.
Ohne Key oder ohne Internet bleibt die App offline und antwortet aus den
mitgelieferten Themenkarten.

Der Entwickler:

- betreibt keinen eigenen Server für die App,
- protokolliert keine normalen Fragen, Antworten oder Keys,
- hat keinen Zugriff auf deinen Account oder dein Guthaben,
- verkauft keine Daten und gibt sie nicht zu Werbezwecken weiter.

## Meldungen zu KI-Antworten

Im Reiter „KI“ kannst du die zuletzt erhaltene Antwort über **MELDEN**
melden. Die App speichert die Meldung zunächst nur auf dem Gerät. Sie sendet
sie **nicht automatisch** und betreibt keinen Meldeserver.

- **E-MAIL** öffnet dein Mailprogramm mit einem vorbereiteten Bericht an
  `smiley.medical@gmail.com`. Erst wenn du die Nachricht dort absendest, erhält
  der Entwickler die Angaben.
- **KOPIEREN** legt den Bericht in die Zwischenablage; du entscheidest, ob und
  an wen du ihn sendest.
- Der Bericht enthält die gemeldete Frage und Antwort, damit die Antwort
  nachvollzogen werden kann. Prüfe ihn im Mailprogramm, bevor du ihn sendest.

Per E-Mail eingegangene Meldungen verarbeitet der Entwickler ausschließlich zur
Moderation, deaktiviert bei akuter Gefahr den betroffenen Anbieter oder das
Modell in einem Update und löscht den Vorgang nach Abschluss, spätestens nach
90 Tagen. Lokale Meldungen verschwinden mit der Deinstallation der App. Der
vollständige Ablauf steht in `MODERATION.md`.

## Keine Werbung, keine Analyse, keine Crash-Berichte

Die App enthält keine Werbe- oder Analyse-SDKs, keine Werbe-ID und keine
automatischen Fehlerberichte an Dritte. Abstürze bleiben auf dem Gerät.

## Kinder

Die App richtet sich nicht an Kinder und erhebt wissentlich keine Daten von
Kindern. Die KI-Funktion setzt einen eigenen Zugang bei einem API-Anbieter
voraus (oder ein lokal betriebenes Ollama).

## Deine Rechte

Da beim Entwickler keine normalen Fragen oder Verläufe gespeichert werden,
gibt es dort dazu nichts, worüber Auskunft erteilt werden könnte. Für Daten, die
du selbst an den von dir gewählten KI-Anbieter sendest, wende dich an diesen
Betreiber. Eine per E-Mail gesendete Meldung kannst du über die im Bericht
genannte Adresse löschen lassen. Lokale Daten entfernst du durch Löschen des
Keys oder Deinstallation der App.

## Änderungen

Wird die App um Funktionen mit Datenübertragung erweitert, wird diese
Erklärung vor dem Update angepasst und mit dem neuen Stand veröffentlicht.

## Marken

„PlayStation“, „PS5“ und „PS5 Pro“ sind Marken von Sony Interactive
Entertainment. Diese App ist ein unabhängiges Hilfsmittel und steht in keiner
Verbindung zu Sony, den genannten Händlern oder ihren Tochtergesellschaften.
