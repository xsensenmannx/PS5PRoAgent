"""Lokale Meldungen für anstößige KI-Antworten.

Die App speichert eine Meldung nur auf dem Gerät. Sie verschickt sie nicht
automatisch: Der Nutzer kann den vollständigen Bericht kopieren oder im
Mailprogramm an den Entwickler senden. Die Meldungs-ID macht den Vorgang
nachvollziehbar, ohne einen Server oder eine Telemetrie einzubauen.

Der API-Key wird nie gespeichert. Gespeichert werden nur die Angaben, die für
die Moderation nötig sind: Kategorie, optionale Notiz, Frage, Antwort,
Anbieter, Modell und App-Version.
"""
from datetime import datetime, timezone
import json
import os
import secrets
from urllib.parse import quote

DATEI = "meldungen.json"
KONTAKT = "smiley.medical@gmail.com"
MAX_MELDUNGEN = 50
MAX_NOTIZ = 500
MAX_FRAGE = 4000
MAX_ANTWORT = 4000
MAX_MAIL = 6000

KATEGORIEN = (
    ("sexuell", "Sexuelle Inhalte"),
    ("gewalt", "Gewalt oder Drohung"),
    ("hass", "Hass oder Diskriminierung"),
    ("selbstverletzung", "Selbstverletzung"),
    ("illegal", "Illegale Inhalte"),
    ("sonstiges", "Sonstiges"),
)
KATEGORIE_LABEL = dict(KATEGORIEN)


def pfad(ordner):
    """Pfad der lokalen Meldungsdatei im privaten App-Verzeichnis."""
    return os.path.join(ordner, DATEI)


def _zeitpunkt(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).replace(microsecond=0)


def neue_id(now=None):
    """Eindeutige, lesbare ID; das Datum hilft bei der zeitlichen Zuordnung."""
    zeit = _zeitpunkt(now).strftime("%Y%m%d-%H%M%S")
    return "M-%s-%s" % (zeit, secrets.token_hex(3).upper())


def _kuerze(text, grenze):
    return str(text or "").strip()[:grenze]


def erstelle(kategorie, notiz="", frage="", antwort="", anbieter="", modell="",
             version="", now=None):
    """Baut einen Meldungsdatensatz; unbekannte Kategorien werden abgelehnt."""
    if kategorie not in KATEGORIE_LABEL:
        raise ValueError("Unbekannte Meldekategorie.")
    zeitpunkt = _zeitpunkt(now)
    return {
        "id": neue_id(zeitpunkt),
        "zeit": zeitpunkt.isoformat().replace("+00:00", "Z"),
        "kategorie": kategorie,
        "kategorie_label": KATEGORIE_LABEL[kategorie],
        "notiz": _kuerze(notiz, MAX_NOTIZ),
        "frage": _kuerze(frage, MAX_FRAGE),
        "antwort": _kuerze(antwort, MAX_ANTWORT),
        "anbieter": _kuerze(anbieter, 80),
        "modell": _kuerze(modell, 160),
        "version": _kuerze(version, 40),
        "status": "neu",
    }


def laden(pfad_):
    """Liest lokale Meldungen; eine kaputte Datei blockiert die App nicht."""
    try:
        with open(pfad_, "r", encoding="utf-8") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return []
    if not isinstance(daten, list):
        return []
    return [eintrag for eintrag in daten
            if isinstance(eintrag, dict) and eintrag.get("id")]


def _schreibe(pfad_, daten):
    ordner = os.path.dirname(pfad_) or "."
    os.makedirs(ordner, exist_ok=True)
    zwischen = pfad_ + ".tmp"
    with open(zwischen, "w", encoding="utf-8") as datei:
        json.dump(daten, datei, ensure_ascii=False, indent=2)
    try:
        os.chmod(zwischen, 0o600)
    except OSError:
        # Windows kennt keine POSIX-Rechte; der App-Ordner ist privat.
        pass
    os.replace(zwischen, pfad_)


def speichern(pfad_, eintrag):
    """Hängt eine Meldung an und behält höchstens die letzten 50 Einträge."""
    daten = laden(pfad_)
    if any(alt.get("id") == eintrag.get("id") for alt in daten):
        return daten
    daten.append(dict(eintrag))
    daten = daten[-MAX_MELDUNGEN:]
    _schreibe(pfad_, daten)
    return daten


def entfernen(pfad_, meldungs_id):
    """Löscht eine lokale Meldung; Rückgabe: Anzahl der verbleibenden."""
    daten = [eintrag for eintrag in laden(pfad_)
             if eintrag.get("id") != meldungs_id]
    _schreibe(pfad_, daten)
    return len(daten)


def leeren(pfad_):
    """Löscht alle lokalen Meldungen (bereits gesendete E-Mails nicht)."""
    _schreibe(pfad_, [])
    return 0


def als_text(eintrag):
    """Vollständiger, kopierbarer Bericht ohne API-Key."""
    zeilen = [
        "KI-Meldung %s" % eintrag.get("id", ""),
        "Zeit: %s" % eintrag.get("zeit", ""),
        "Kategorie: %s" % eintrag.get("kategorie_label", ""),
        "App-Version: %s" % eintrag.get("version", ""),
        "Anbieter: %s" % eintrag.get("anbieter", ""),
        "Modell: %s" % eintrag.get("modell", ""),
        "",
        "Frage:",
        eintrag.get("frage", ""),
        "",
        "Antwort:",
        eintrag.get("antwort", ""),
    ]
    notiz = eintrag.get("notiz", "")
    if notiz:
        zeilen.extend(["", "Notiz:", notiz])
    return "\n".join(zeilen).strip()


def mailto_url(eintrag, empfaenger=KONTAKT):
    """Mail-Entwurf mit Betreff und Bericht; der Nutzer sendet ihn selbst."""
    betreff = "Hilfe-App: KI-Antwort melden %s" % eintrag.get("id", "")
    text = als_text(eintrag)
    if len(text) > MAX_MAIL:
        text = text[:MAX_MAIL].rstrip() + "\n… (Bericht gekürzt)"
    return "mailto:%s?subject=%s&body=%s" % (
        quote(str(empfaenger), safe=""),
        quote(betreff, safe=""),
        quote(text, safe=""),
    )
