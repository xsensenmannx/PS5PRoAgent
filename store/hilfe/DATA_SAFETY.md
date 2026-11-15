# Data Safety — Antworten für die Play Console (Hilfe-App)

Stand: November 2026. Grundlage: `store/hilfe/PRIVACY.md`.

Die Hilfe-App hat zwei Betriebsarten. Für die Data-Safety-Angaben zählt die
weiteste: die optionale KI. Wer sie nicht nutzt, erzeugt keinen Netzwerkverkehr.

## Empfohlene Antwort (konservativ, mit KI)

| Frage | Antwort |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| Data type 1 | **Personal info → Other info** |
| Data type 2 | **Messages → Other in-app messages** |
| Collected or shared? | **Shared** |
| Purpose | **App functionality** |
| Optional? | **Ja** — nur wenn der Nutzer einen eigenen Key einträgt und sendet |
| Ephemeral? | **Ja** — der Entwickler speichert nichts |
| Linked to the user's identity? | **Nein** (der Key ist ein Zugangstoken, kein Konto bei uns) |
| Encrypted in transit? | **Ja** (HTTPS/TLS) |
| Data sold? | **Nein** |
| Advertising or analytics SDKs? | **Nein** |
| Account deletion? | **Entfällt** — keine Konten beim Entwickler |

**Was übertragen wird:** ausschließlich der Text, den der Nutzer in die KI-Zeile
tippt, der bisherige Gesprächsverlauf dieses Reiters und der Modellname. Empfänger
ist die Freebuff-API (`freebuff.com`), die der Nutzer mit seinem eigenen Key
ansteuert. Der Entwickler betreibt keinen Server, protokolliert nichts und hat
keinen Zugriff auf Fragen oder Antworten.

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

Play bewertet auch optionale Funktionen. Weil der Endpunkt fest in der App steht
und nicht vom Nutzer gewählt wird, ist „Shared“ die sichere Angabe — dieselbe
Logik wie beim Webhook der Radar-App. Die Angabe kostet im Listing nichts und
verhindert eine Ablehnung wegen unvollständiger Deklaration.
