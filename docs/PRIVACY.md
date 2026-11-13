# Datenschutzerklärung — Konsolen-Radar / PS5 Pro Search Agent

**Stand:** 13. November 2026

## 1. Verantwortlicher

Betreiber des Open-Source-Projekts „PS5 Pro Search Agent" / „Konsolen-Radar".
Kontakt: [github.com/xsensenmannx/PS5PRoAgent/issues](https://github.com/xsensenmannx/PS5PRoAgent/issues)

> Vor der Play-Store-Einreichung hier den bürgerlichen Namen und eine
> erreichbare E-Mail-Adresse ergänzen. Die Play-Konsole verlangt beides.

## 2. Kurzfassung

Die App erhebt **keine personenbezogenen Daten** und sendet nichts an den
Entwickler. Es gibt keine Konten, keine Werbung, keine Analyse-SDKs und kein
Tracking. Alle Einstellungen, Preisverläufe und Belege bleiben auf dem Gerät.

## 3. Welche Daten die App verarbeitet

**Lokal auf dem Gerät:**

* Einstellungen (aktive Händler, Preisgrenze, Alarmregeln, Schriftgröße,
  optional eine Webhook-URL),
* Preisverlauf und Verfügbarkeitsstatus der abgefragten Shops,
* Prüfstatus der Shops (Health), Absturzprotokoll,
* optional kurze Beleg-Ausschnitte zu Treffern (Preis, Stock-Text, Zeitstempel).

Diese Daten verlassen das Gerät nicht, außer der Nutzer exportiert sie
ausdrücklich oder konfiguriert einen Webhook.

**Beim Scan:** Die App ruft öffentlich erreichbare Produktseiten der Shops ab.
Dabei werden technisch notwendige Verbindungsdaten (IP-Adresse, User-Agent)
an den jeweiligen Shop übertragen. Das ist für den Abruf unvermeidbar und
unterliegt der Datenschutzerklärung des Shops.

**Webhook (optional):** Trägt der Nutzer eine Webhook-URL ein (z. B. ntfy,
Telegram, Discord), sendet die App bei einem Treffer Händlername, Preis,
Produkt-URL und Zeitstempel an genau dieses Ziel. Empfänger ist der vom Nutzer
gewählte Dienst; der Entwickler hat keinen Zugriff darauf. Die URL kann ein
Zugriffstoken enthalten und wird in der App maskiert sowie nicht protokolliert.

## 4. Berechtigungen

| Berechtigung | Zweck |
|---|---|
| Internet | Abruf der Shop-Seiten und optionaler Webhook |
| Benachrichtigungen | Treffer-Alarm und Status des Hintergrund-Scans |
| Foreground-Service | Scan bei geschlossener App, mit sichtbarer Dauerbenachrichtigung |
| Boot-Empfänger | Neustart des Dienstes nach einem Geräteneustart, nur wenn AUTO aktiv ist |
| Vibration | kurzes Feedback bei Treffern |

Die App fragt **keinen** Standort, keine Kontakte, keine Fotos, kein Mikrofon
und keinen Barrierefreiheitszugriff an.

## 5. Keine Weitergabe, keine Werbung, kein Tracking

Es gibt keine Werbenetzwerke, keine Analyse-, Crash- oder Attribution-SDKs.
Der Entwickler erhält keine Nutzungsdaten. Es werden keine Daten verkauft.

## 6. Speicherdauer und Löschung

Die Daten bleiben lokal, bis der Nutzer sie löscht oder die App deinstalliert.
Die Deinstallation entfernt die app-privaten Daten. Ein Export (falls angeboten)
erfolgt nur auf ausdrückliche Aktion des Nutzers.

## 7. Kinder

Die App richtet sich nicht an Kinder und ist nicht für die Familienfreigabe
bestimmt.

## 8. Hosting dieser Seite

Diese Datenschutzseite wird über GitHub Pages bereitgestellt. Beim Aufruf
verarbeitet GitHub technische Verbindungsdaten nach seiner eigenen
Datenschutzerklärung. Die App selbst kontaktiert diese Seite nicht.

## 9. Änderungen

Änderungen an dieser Erklärung werden im Repository veröffentlicht; das Datum
oben wird aktualisiert. Wesentliche Änderungen werden in den Release-Notes
genannt.

## 10. Kontakt

Fragen zum Datenschutz: [Issue im Repository](https://github.com/xsensenmannx/PS5PRoAgent/issues)
oder die im Play-Store-Eintrag angegebene Kontaktadresse.

---

# Privacy Policy — English

**Last updated:** 13 November 2026

The app collects **no personal data** and sends nothing to the developer.
There are no accounts, ads, analytics SDKs or tracking. Settings, price history
and evidence snippets stay on the device.

When scanning, the app requests public product pages from retailers; the
respective retailer receives the technically required connection data (IP
address, user agent) under its own privacy policy. If the user configures a
webhook (ntfy, Telegram, Discord or a custom HTTPS endpoint), the app sends the
shop name, price, product URL and timestamp to that endpoint. The recipient is
chosen by the user; the developer has no access. The URL may contain a token and
is masked in the app and never logged.

Permissions are used only for internet access, notifications, the foreground
scan service, restart after boot (only when AUTO is enabled) and vibration. The
app does not request location, contacts, photos, microphone or accessibility
access. Data remains on the device until the user deletes it or uninstalls the
app. The app is not directed at children.

Contact: [repository issues](https://github.com/xsensenmannx/PS5PRoAgent/issues).
