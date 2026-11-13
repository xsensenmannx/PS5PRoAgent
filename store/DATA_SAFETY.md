# Data Safety — Antworten für die Play Console

Stand: November 2026. Grundlage: `docs/PRIVACY.md`.

## Empfohlene Antwort (Entwickler erhält keine Daten)

| Frage | Antwort |
|---|---|
| Does your app collect or share any of the required user data types? | **No** |
| Is all of the user data collected by your app encrypted in transit? | Ja (nur HTTPS) |
| Do you provide a way for users to request that their data is deleted? | Entfällt — keine Konten, keine serverseitige Speicherung |
| Does your app use advertising or analytics SDKs? | Nein |
| Is data linked to the user's identity? | Nein |

Begründung: Einstellungen, Preisverlauf, Health und Belege bleiben lokal. Der
Entwickler betreibt keinen Server und erhält keine Nutzungsdaten. Es gibt keine
Konten, keine Werbe-IDs und keine Analyse-SDKs.

## Konservative Variante (falls Google den Webhook als „Sharing" wertet)

| Frage | Antwort |
|---|---|
| Data type | **App activity → Other actions** |
| Collected or shared? | **Shared** |
| Purpose | App functionality |
| Optional? | Ja, nur wenn der Nutzer eine Webhook-URL einträgt |
| Ephemeral? | Ja (keine Speicherung beim Empfänger durch den Entwickler) |
| Linked to identity? | Nein |
| Encrypted in transit? | Ja |

Inhalt der Übertragung: Händlername, Preis, Produkt-URL, Zeitstempel — keine
personenbezogenen Daten, kein Standort, keine Geräte-ID. Empfänger ist der vom
Nutzer gewählte Dienst (ntfy, Telegram, Discord oder eigener Endpunkt).

**Entscheidung vor dem Upload:** Die konservative Variante ist die sichere Wahl,
wenn ein Reviewer den Webhook als Datenweitergabe einstuft. Sie kostet im Listing
nichts und verhindert eine Ablehnung wegen falscher Angaben. Im Zweifel diese
Variante wählen und in der Beschreibung offen erklären.

## Nicht zutreffend

Standort, Kontakte, Kalender, SMS, Fotos, Videos, Audio, Dateien, Gesundheitsdaten,
Finanzdaten, Web-Browsing-Verlauf, Geräte- oder andere IDs, Crash-Logs an Dritte,
Werbe-ID: **nein**.
