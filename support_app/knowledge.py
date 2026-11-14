"""Wissensbasis der Offline-Hilfe.

Jeder Eintrag ist eine Karte: Titel, Stichwörter, kurze Antwort, optionale
Schritte und ein Hinweis. Die Stichwörter sind bewusst Alltagssprache
("geht nicht", "kein Alarm"), damit der Kern auch umgangssprachliche Fragen
trifft. Verglichen wird über ``support_core.normalize`` (klein, ohne Umlaute).
"""

ENTRIES = [
    {
        "id": "erste-schritte",
        "title": "Erster Alarm in drei Schritten",
        "keywords": [
            "erste schritte", "einrichten", "start", "anfang", "testalarm",
            "alarm einrichten", "installation", "neu installiert", "loslegen",
        ],
        "answer": (
            "Die App braucht kein Konto. Du setzt eine Preisgrenze, wählst die "
            "Alarme und lässt den Radar laufen. Ein Testalarm zeigt sofort, ob "
            "Benachrichtigungen auf diesem Gerät überhaupt ankommen."
        ),
        "steps": [
            "Preisgrenze setzen (Standard 900 €, fair ist alles bis 799,99 €).",
            "Alarm-Regeln öffnen und „Testalarm“ tippen — die Meldung muss erscheinen.",
            "Akku-Optimierung für die App freigeben, sonst beendet Android den Hintergrunddienst.",
        ],
        "note": "Ohne Akku-Freigabe kommt im Hintergrund oft nichts an.",
    },
    {
        "id": "alarm-kommt-nicht",
        "title": "Kein Alarm trotz Treffer",
        "keywords": [
            "kein alarm", "alarm kommt nicht", "benachrichtigung", "keine meldung",
            "stumm", "kein ton", "meldet nicht", "nichts passiert", "vibration",
        ],
        "answer": (
            "Drei Ursachen decken fast alle Fälle ab: Akku-Optimierung, ein "
            "Filter, der den Treffer aussperrt, oder eine Stummschaltung. "
            "Prüfe zuerst den Testalarm aus den Alarm-Regeln."
        ),
        "steps": [
            "Testalarm senden: kommt er an, liegt es am Filter — nicht am Gerät.",
            "Akku-Optimierung und Autostart für die App freigeben.",
            "„Nur bestätigte“, Konfidenz-Schwelle sowie Ruhezeit und Stummschaltung prüfen.",
        ],
        "note": "Der Hintergrunddienst läuft nur, wenn „Automatischer Scan“ aktiv ist.",
    },
    {
        "id": "webhook",
        "title": "Webhook: ntfy, Telegram, Discord",
        "keywords": [
            "webhook", "ntfy", "telegram", "discord", "bot token", "chat id",
            "401", "404", "nachricht kommt nicht an", "push", "fremdkanal",
        ],
        "answer": (
            "Webhooks gehen an ntfy, Telegram, Discord oder eine eigene URL. "
            "Fehler 401/403 heißt fast immer: Token falsch oder abgelaufen. "
            "404 bedeutet meist eine falsche Topic- oder Chat-ID."
        ),
        "steps": [
            "Preset wählen und URL samt Token neu einfügen (keine Leerzeichen).",
            "Testalarm senden und im Dienst prüfen, ob er ankommt.",
            "Bei eigener URL: JSON-Aufbau und erwarteten Statuscode kontrollieren.",
        ],
        "note": "Tokens bleiben lokal und werden in der App maskiert. Ohne Webhook bleibt es bei der lokalen Meldung.",
    },
    {
        "id": "keine-treffer",
        "title": "Keine Treffer gefunden",
        "keywords": [
            "keine treffer", "nichts gefunden", "0 treffer", "leer", "findet nichts",
            "keine ergebnisse", "nichts da",
        ],
        "answer": (
            "Kein Treffer ist meistens korrekt: Die App meldet nur, was sie "
            "belegen kann. Prüfe Preisgrenze (Standard 900 €), Konfidenz-Schwelle "
            "und ob „nur bestätigte“ aktiv ist."
        ),
        "steps": [
            "Preisgrenze anheben oder „nur bestätigte“ kurz ausschalten.",
            "Konfidenz-Schwelle auf 0 setzen und beobachten, was gemeldet wird.",
            "Schnellmodus für die sechs heißen Shops aktivieren.",
            "Shop-Health prüfen: dauerhafte 403/429 sind keine Trefferquelle.",
        ],
        "note": "Ein Treffer braucht einen zweiten bestätigten Abruf — das kostet Zeit, verhindert aber Falschalarme.",
    },
    {
        "id": "bot-schutz",
        "title": "403, 429 und Bot-Schutz",
        "keywords": [
            "403", "429", "blockiert", "bot schutz", "captcha", "gesperrt",
            "rate limit", "vpn", "proxy", "verboten", "forbidden",
        ],
        "answer": (
            "403 und 429 sind Bot-Schutz oder Rate-Limit. Die App umgeht das "
            "nicht: kein Proxy, kein Captcha-Löser, keine Warteschlange. Mehr "
            "Requests bringen hier keine Treffer, sondern längere Sperren."
        ),
        "steps": [
            "Scan 10–30 Minuten pausieren und das Intervall auf 15–30 Minuten stellen.",
            "VPN oder Proxy ausschalten — geteilte IPs werden schneller gesperrt.",
            "Betroffene Shops im Health-Verlauf beobachten, nicht manuell nachfeuern.",
        ],
        "note": "Liefert ein Shop dauerhaft 403, ist er für die App faktisch nicht erreichbar. Das ist kein Fehler, den du beheben kannst.",
    },
    {
        "id": "konfidenz",
        "title": "Konfidenz und Schwelle",
        "keywords": [
            "konfidenz", "schwelle", "bestaetigt", "nur bestaetigte", "92",
            "vertrauen", "sicher", "prozent",
        ],
        "answer": (
            "Die Konfidenz (0–100) zählt Signale: zweiter Abruf, plausibler "
            "Preis, expliziter Stock-Beleg, neuer Zustand, frische Antwort. "
            "Unter der Schwelle (Standard 70) bleibt der Alarm still."
        ),
        "steps": [
            "Treffer öffnen und die Signale einzeln lesen.",
            "Schwelle nur senken, wenn du Falschalarme in Kauf nehmen willst.",
            "Beleg-Ausschnitt und Zeitstempel prüfen.",
        ],
        "note": "Konfidenz ist eine Schätzung, keine Garantie.",
    },
    {
        "id": "chance",
        "title": "Lotterie, Einladung, nur im Markt",
        "keywords": [
            "lotterie", "verlosung", "einladung", "invite", "nur im markt",
            "abholung", "click and collect", "chance", "gewinnspiel",
        ],
        "answer": (
            "Lotterie, Einladung und „nur im Markt“ sind Chancen, keine Treffer. "
            "Sie kommen als eigene Meldung ohne „VERFÜGBAR“. Die App nimmt an "
            "keiner Verlosung teil und kauft nichts."
        ),
        "steps": [
            "Chance-Alarme in den Alarm-Regeln einschalten.",
            "Meldung lesen: Teilnahmeschluss bzw. Markt steht im Text.",
            "Selbst teilnehmen oder abholen — die App tut das nicht für dich.",
        ],
    },
    {
        "id": "akku-hintergrund",
        "title": "Akku, Hintergrunddienst, Neustart",
        "keywords": [
            "akku", "hintergrund", "service", "boot", "neustart", "schlaft",
            "doze", "optimierung", "stoppt", "beendet",
        ],
        "answer": (
            "Android beendet Hintergrundarbeit aggressiv. Ohne Akku-Ausnahme und "
            "Autostart-Freigabe scannt die App nur im Vordergrund."
        ),
        "steps": [
            "Einstellungen → Akku → für die App „nicht optimieren“ wählen.",
            "Autostart erlauben (Hersteller-UI, z. B. Xiaomi/Samsung).",
            "Die Dauer-Benachrichtigung des Dienstes nicht wegwischen.",
        ],
        "note": "Der Start nach Neustart greift nur, wenn „Automatischer Scan“ aktiv ist.",
    },
    {
        "id": "play-vs-sideload",
        "title": "Play-App und Sideload-App",
        "keywords": [
            "play store", "sideload", "paket", "version", "update", "zwei apps",
            "konsolenradar", "ps5prosearchagent",
        ],
        "answer": (
            "Es gibt zwei Linien mit getrennten Paketen: die Play-App "
            "(de.konsolenradar.app) und die Sideload-App "
            "(de.ps5pro.ps5prosearchagent). Beide können parallel installiert "
            "sein, teilen aber keine Daten."
        ),
        "steps": [
            "Version im Setup-Screen prüfen.",
            "Updates nur aus der jeweiligen Quelle installieren.",
            "Beim Wechsel die Einstellungen neu setzen.",
        ],
    },
    {
        "id": "daten",
        "title": "Wo liegen meine Daten?",
        "keywords": [
            "daten", "verlauf", "speicher", "backup", "export", "loeschen",
            "json", "privat", "telemetrie", "konto",
        ],
        "answer": (
            "Alles bleibt lokal: Einstellungen, Verlauf, Belege und Health liegen "
            "als JSON im App-Speicher. Kein Konto, keine Telemetrie, kein Server."
        ),
        "steps": [
            "Für eine Kopie den Export im Diagnose-Screen nutzen.",
            "App-Daten löschen entfernt Verlauf und Einstellungen vollständig.",
            "Belege werden auf 200 Stück begrenzt, danach fällt der älteste heraus.",
        ],
    },
    {
        "id": "scan-intervall",
        "title": "Wie oft wird gescannt?",
        "keywords": [
            "intervall", "wie oft", "5 minuten", "schnellmodus", "scan dauer",
            "zu langsam", "haeufigkeit", "60 minuten",
        ],
        "answer": (
            "5 bis 60 Minuten sind einstellbar, dazu ein Schnellmodus für sechs "
            "heiße Shops im Minutentakt. Kürzer heißt nicht besser: Shops "
            "begrenzen Requests, und Sperren kosten mehr Zeit als sie sparen."
        ),
        "steps": [
            "15 Minuten ist ein guter Kompromiss für den Alltag.",
            "Schnellmodus nur bei akutem Bedarf einschalten.",
            "Health beobachten, bevor du das Intervall weiter verkürzt.",
        ],
    },
    {
        "id": "preis-filter",
        "title": "Preisgrenze, Bundles, Zustand",
        "keywords": [
            "preis", "preisgrenze", "900", "zubehoer", "bundle", "gebraucht",
            "falscher preis", "set", "controller",
        ],
        "answer": (
            "Der Radar filtert nach Preisgrenze, Zustand und Zubehör. Bundles "
            "und Controller-Sets werden erkannt und getrennt, damit kein "
            "1.100-€-Set als Treffer zählt."
        ),
        "steps": [
            "Preisgrenze passend zum Budget setzen.",
            "Zwischen neu und gebraucht wählen.",
            "Bundle-Hinweis im Detail lesen, bevor du klickst.",
        ],
        "note": "Fremdwährungen werden nicht als Euro-Treffer gewertet.",
    },
    {
        "id": "ps-direct",
        "title": "PS Direct und offizielle Quellen",
        "keywords": [
            "ps direct", "playstation direct", "direkt", "offiziell", "sony",
            "direktlink", "warum nicht",
        ],
        "answer": (
            "PS Direct schützt seine Seiten und erlaubt laut Nutzungsbedingungen "
            "kein automatisiertes Auslesen. Die App umgeht nichts — deshalb kann "
            "PS Direct ausbleiben. Der offizielle Direktlink bleibt der saubere Weg."
        ),
        "steps": [
            "Direktlink im Shop-Detail öffnen und selbst prüfen.",
            "Nicht auf „garantiert verfügbar“ verlassen — das kann niemand zusagen.",
        ],
    },
    {
        "id": "fehlerbericht",
        "title": "Guten Fehlerbericht schreiben",
        "keywords": [
            "fehler melden", "bericht", "log", "diagnose", "support", "bug",
            "melden", "problem schildern",
        ],
        "answer": (
            "Für einen guten Bericht reichen: Paket und Version, letzter Scan, "
            "Anzahl Shops, Treffer, Konfidenz, Webhook-Fehler und die Shops mit "
            "403/429. Genau diese Zeilen liest die Diagnose hier ein."
        ),
        "steps": [
            "Im Radar den Diagnose-Screen öffnen.",
            "Text kopieren und hier im Reiter „Diagnose“ einfügen.",
            "Befund prüfen und bei Bedarf an den Support weitergeben.",
        ],
    },
    {
        "id": "was-nicht",
        "title": "Was die App bewusst nicht tut",
        "keywords": [
            "kauf bot", "automatisch kaufen", "warenkorb", "bestellt", "garantie",
            "greift die app ein", "reserviert",
        ],
        "answer": (
            "Die App kauft nicht, legt keine Konten an, löst keine Captchas und "
            "umgeht keine Warteschlange. Sie beobachtet öffentliche Seiten und "
            "meldet, was sie belegen kann."
        ),
        "note": "Wer mehr verspricht, riskiert Sperren und rechtliche Probleme.",
    },
    {
        "id": "suchassistent",
        "title": "Suchauftrag in Einstellungen übersetzen",
        "keywords": [
            "suchauftrag", "suchassistent", "suche bauen", "filter setzen",
            "wie suche ich", "suchagent", "nur amazon", "unter 700",
        ],
        "answer": (
            "Im Reiter „Suche“ baue ich aus einem Wunsch einen konkreten Plan: "
            "Preisgrenze, Shops, Filter, Sortierung und Intervall — mit den "
            "echten Namen aus dem Radar. Abgerufen wird nichts automatisch."
        ),
        "steps": [
            "Reiter „Suche“ öffnen und den Wunsch eintippen, z. B. „unter 700, nur Amazon, nur neu“.",
            "Plan prüfen: Einstellungen, Schritte und Hinweise.",
            "Werte im Radar eintragen und einen Scan starten.",
        ],
        "note": "Der Assistent setzt nichts selbst und ruft keine Shops ab — er übersetzt nur.",
    },
]
