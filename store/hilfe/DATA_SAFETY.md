# Data Safety — Antworten für die Play Console (Hilfe-App)

Stand: November 2026. Grundlage: `store/hilfe/PRIVACY.md`.

> **Stand 15.11.2026:** Die Tabelle ist auf **Collected + Shared** und
> **Ephemeral = Nein** korrigiert. Der Gesprächsverlauf wird nicht mehr als
> übertragen dokumentiert; die App sendet nur die aktuelle Frage, Kontext und
> Modellname. Siehe `STORE_AUDIT.md`.

Die Hilfe-App hat zwei Betriebsarten. Für die Data-Safety-Angaben zählt die
weiteste: die optionale KI. Wer sie nicht nutzt, erzeugt keinen Netzwerkverkehr.

## Empfohlene Antwort (konservativ, mit KI)

| Frage | Antwort |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| Data type 1 | **Personal info → Other info** |
| Data type 2 | **Messages → Other in-app messages** |
| Collected or shared? | **Collected + Shared** — Daten verlassen das Gerät und gehen an den gewählten Anbieter |
| Purpose | **App functionality** |
| Optional? | **Ja** — nur wenn der Nutzer einen Anbieter wählt, einen eigenen Key einträgt und sendet |
| Ephemeral? | **Nein** — der Entwickler speichert nichts, aber die Retention des Anbieters ist nicht garantiert |
| Linked to the user's identity? | **Nein** (der Key ist ein Zugangstoken, kein Konto bei uns) |
| Encrypted in transit? | **Ja** (HTTPS/TLS) |
| Data sold? | **Nein** |
| Advertising or analytics SDKs? | **Nein** |
| Account deletion? | **Entfällt** — keine Konten beim Entwickler |

**Was übertragen wird:** ausschließlich der Text, den der Nutzer in die KI-Zeile
tippt, zwei bis drei passende Hilfe-Karten als Kontext und der Modellname.
Ein Gesprächsverlauf wird nicht mitgesendet. Empfänger ist der vom Nutzer
gewählte Anbieter: Freebuff, OpenRouter, Groq, Google AI Studio oder Mistral —
jeweils mit dem eigenen Key des Nutzers. Wählt der Nutzer Ollama auf seinem PC,
verlassen die Daten den Rechner nicht. Der Entwickler betreibt keinen Server, protokolliert
nichts und hat keinen Zugriff auf Fragen oder Antworten.

**Löschung:** Der Key liegt nur im privaten App-Speicher und verschwindet mit
„Key löschen“ oder der Deinstallation. Beim API-Anbieter gelten dessen
Löschfristen; der Nutzer kann sie über sein dortiges Konto steuern.

## Variante ohne KI (falls die KI für die Play-Version entfernt wird)

| Frage | Antwort |
|---|---|
| Does your app collect or share any of the required user data types? | **No** |
| Encrypted in transit? | Entfällt — keine Übertragung |
| Deletion request? | Entfällt — keine Speicherung außerhalb des Geräts |
| Ads/Analytics? | Nein |

Dann entfallen `INTERNET`-Berechtigung, der KI-Reiter und dieser gesamte
Abschnitt; die App ist vollständig offline.

## Nicht zutreffend

Standort, Kontakte, Kalender, SMS, Fotos, Videos, Audio, Dateien,
Gesundheitsdaten, Finanzdaten, Web-Browsing-Verlauf, Geräte- oder andere IDs,
Crash-Logs an Dritte, Werbe-ID: **nein**.

## Entscheidungshinweis

Play bewertet auch optionale Funktionen. Die App bringt eine feste Liste
OpenAI-kompatibler Anbieter mit, zwischen denen der Nutzer wählt; ein eigener
Server des Entwicklers ist nicht beteiligt. Weil Nutzerdaten dabei an einen
Dritten gehen können, ist **„Collected + Shared“** die sichere Angabe —
dieselbe Logik wie beim Webhook der Radar-App. Die Angabe kostet im Listing
nichts und verhindert eine Ablehnung wegen unvollständiger Deklaration.
