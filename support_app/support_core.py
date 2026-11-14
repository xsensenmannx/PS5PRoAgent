"""Offline-Kern der Konsolen-Radar-Hilfe.

Kein Kivy, kein Netzwerk, keine Dateizugriffe. Der Kern beantwortet Fragen aus
``knowledge.py`` und liest einen eingefügten Diagnosebericht. Dadurch läuft
derselbe Code in der App, in den Tests und auf dem Desktop.

Bewusst ohne Modell: Die Antworten sind nachvollziehbar, wiederholbar und
funktionieren ohne Internet und ohne Schlüssel.
"""
from __future__ import annotations

import re
import unicodedata

from knowledge import ENTRIES

MAX_TREFFER = 3
_SCHWELLE = 3.0

# Nur echte Füllwörter. "nicht" bleibt drin, weil es Fragen umdreht.
_STOPP = frozenset((
    "der", "die", "das", "und", "oder", "ein", "eine", "einen", "einem",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "mir", "mich", "mein",
    "ist", "sind", "war", "bei", "mit", "fuer", "von", "zu", "im", "in",
    "am", "auf", "als", "auch", "mal", "denn", "doch", "bitte", "hilfe",
    "problem", "frage", "habe", "hab", "kann", "muss", "soll", "wie", "was",
    "wo", "wenn", "dann", "noch", "schon", "sehr", "mehr", "tut", "tun",
))

_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}

FALLBACK = (
    "Dazu habe ich keine Regel. Ich kenne Einrichtung, Alarme, Webhooks, "
    "Konfidenz, Chancen, Akku/Hintergrund, Daten, Preisfilter und die "
    "Diagnose. Formuliere die Frage mit einem dieser Stichworte — oder öffne "
    "den Reiter „Themen“."
)

_VORSCHLAG_IDS = ("erste-schritte", "alarm-kommt-nicht", "webhook")

# Ein realistischer Bericht, wie ihn der Radar im Diagnose-Screen zeigt.
BEISPIEL_BERICHT = (
    "KONSOLEN-RADAR · DIAGNOSE\n"
    "Paket: de.konsolenradar.app\n"
    "Shops: 42\n"
    "Letzter Scan: 12:04\n"
    "Treffer: 0\n"
    "Konfidenz: 62\n"
    "Webhook: Fehler 401\n"
    "403 bei: MediaMarkt DE, Saturn DE\n"
    "429 bei: Amazon DE\n"
)

_STUFE_RANG = {"hoch": 0, "mittel": 1, "info": 2}


def normalize(text):
    """Klein, umlautfrei, ohne Akzente, Whitespace geglättet."""
    text = str(text or "").lower()
    for zeichen, ersatz in _UMLAUTE.items():
        text = text.replace(zeichen, ersatz)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text):
    """Wortliste ohne Stoppwörter."""
    return [t for t in normalize(text).split() if t and t not in _STOPP]


def _score(entry, frage_norm, frage_tokens):
    score = 0.0
    for stichwort in entry.get("keywords", ()):
        k = normalize(stichwort)
        if k and k in frage_norm:
            score += 3.0 + min(len(k), 24) * 0.15
    titel = set(tokenize(entry.get("title", "")))
    score += 1.5 * len(titel & frage_tokens)
    stich = set()
    for stichwort in entry.get("keywords", ()):
        stich.update(tokenize(stichwort))
    score += 0.75 * len(stich & frage_tokens)
    return score


def search(frage, limit=MAX_TREFFER):
    """Beste Karten zur Frage, absteigend nach Punktzahl."""
    frage_norm = normalize(frage)
    if not frage_norm:
        return []
    frage_tokens = set(tokenize(frage))
    treffer = []
    for entry in ENTRIES:
        punkte = _score(entry, frage_norm, frage_tokens)
        if punkte >= _SCHWELLE:
            treffer.append((punkte, entry))
    treffer.sort(key=lambda paar: (-paar[0], paar[1]["title"]))
    return [{"entry": e, "score": round(s, 2)} for s, e in treffer[:limit]]


def _vorschlaege():
    nach_id = {e["id"]: e for e in ENTRIES}
    return [nach_id[i]["title"] for i in _VORSCHLAG_IDS if i in nach_id]


def answer(frage):
    """Antwortkarte oder Fallback mit Themenvorschlägen."""
    treffer = search(frage)
    if treffer:
        return {
            "kind": "antwort",
            "entry": treffer[0]["entry"],
            "score": treffer[0]["score"],
            "related": [t["entry"]["title"] for t in treffer[1:]],
        }
    return {"kind": "fallback", "text": FALLBACK, "suggestions": _vorschlaege()}


def format_entry(entry):
    """Karte als reiner Text für die Chatblase."""
    teile = [entry["title"].upper(), "", entry["answer"]]
    schritte = entry.get("steps") or ()
    if schritte:
        teile.append("")
        for nummer, schritt in enumerate(schritte, 1):
            teile.append("%d. %s" % (nummer, schritt))
    hinweis = entry.get("note")
    if hinweis:
        teile.extend(("", "Hinweis: " + hinweis))
    return "\n".join(teile)


def format_answer(ergebnis):
    """Antwortergebnis als Text, inklusive Querverweisen."""
    if ergebnis["kind"] == "fallback":
        text = ergebnis["text"]
        if ergebnis["suggestions"]:
            text += "\n\nVielleicht hilft: " + " · ".join(ergebnis["suggestions"])
        return text
    text = format_entry(ergebnis["entry"])
    if ergebnis.get("related"):
        text += "\n\nSiehe auch: " + " · ".join(ergebnis["related"])
    return text


# ── Diagnosebericht ────────────────────────────────────────────────
def _erste_zahl(muster, text):
    treffer = re.search(muster, text, re.I)
    return int(treffer.group(1)) if treffer else None


def _webhook_zeile(text):
    for zeile in text.splitlines():
        klein = zeile.lower()
        if "webhook" in klein and any(
            wort in klein
            for wort in ("fehler", "error", "401", "403", "404", "timeout",
                         "fehlgeschlagen", "failed")
        ):
            return zeile.strip()[:160]
    return None


def parse_report(text):
    """Liest die wichtigsten Zeilen eines eingefügten Diagnoseberichts."""
    text = str(text or "")
    shops = _erste_zahl(
        r"(?:shops?|h(?:ae|ä)ndler)\s*[:\-]?\s*(\d{1,3})", text
    )
    if shops is None:
        shops = _erste_zahl(
            r"(\d{1,3})\s*(?:shops?|h(?:ae|ä)ndler)", text
        )
    treffer = _erste_zahl(r"(?:treffer|hits?)\s*[:\-]?\s*(\d{1,3})", text)
    konfidenz = _erste_zahl(
        r"(?:konfidenz|confidence)\s*[:\-]?\s*(\d{1,3})", text
    )
    letzter_scan = None
    scan_treffer = re.search(
        r"(?:letzter\s+scan|zuletzt|letzte\s+pr(?:ue|ü)fung)"
        r"\s*[:\-]?\s*(\d{1,2}:\d{2})",
        text,
        re.I,
    )
    if scan_treffer:
        letzter_scan = scan_treffer.group(1)

    paket_treffer = re.search(
        r"(de\.konsolenradar\.app|de\.ps5pro\.ps5prosearchagent)", text
    )
    paket = paket_treffer.group(1) if paket_treffer else None

    bericht = {
        "shops": shops,
        "treffer": treffer,
        "konfidenz": konfidenz,
        "letzter_scan": letzter_scan,
        "paket": paket,
        "webhook_fehler": _webhook_zeile(text),
        "anzahl_403": len(re.findall(r"(?<!\d)403(?!\d)", text)),
        "anzahl_429": len(re.findall(r"(?<!\d)429(?!\d)", text)),
        "zeilen": len([z for z in text.splitlines() if z.strip()]),
    }
    bericht["leer"] = (
        shops is None
        and treffer is None
        and konfidenz is None
        and letzter_scan is None
        and paket is None
        and bericht["webhook_fehler"] is None
        and bericht["anzahl_403"] == 0
        and bericht["anzahl_429"] == 0
    )
    return bericht


def diagnose(bericht):
    """Befunde mit Stufe, Titel und konkretem nächsten Schritt."""
    if not isinstance(bericht, dict) or bericht.get("leer"):
        return [{
            "stufe": "mittel",
            "titel": "Bericht unvollständig",
            "text": (
                "Ich konnte keine verwertbaren Zeilen finden. Füge den "
                "Diagnose-Block aus dem Radar ein — er enthält Shops, letzten "
                "Scan, Treffer, Konfidenz und Fehlercodes."
            ),
        }]

    befunde = []

    if bericht["anzahl_403"] or bericht["anzahl_429"]:
        teile = []
        if bericht["anzahl_403"]:
            teile.append("%d× 403 (Bot-Schutz)" % bericht["anzahl_403"])
        if bericht["anzahl_429"]:
            teile.append("%d× 429 (Rate-Limit)" % bericht["anzahl_429"])
        befunde.append({
            "stufe": "hoch",
            "titel": "Shops blockieren den Scan",
            "text": (
                "%s. Die App umgeht das bewusst nicht. Pausiere den Scan "
                "10–30 Minuten, stelle das Intervall auf 15–30 Minuten und "
                "schalte VPN oder Proxy aus. Weitere Versuche verlängern die "
                "Sperre nur." % " · ".join(teile)
            ),
        })

    if bericht["webhook_fehler"]:
        befunde.append({
            "stufe": "hoch",
            "titel": "Webhook wird abgelehnt",
            "text": (
                "Der Bericht nennt „%s“. Prüfe Token und URL im Webhook-Preset; "
                "401/403 heißt meist falscher oder abgelaufener Token, 404 eine "
                "falsche Topic- oder Chat-ID. Ein Testalarm zeigt es sofort."
                % bericht["webhook_fehler"]
            ),
        })

    if bericht["shops"] is not None and bericht["shops"] < 30:
        befunde.append({
            "stufe": "mittel",
            "titel": "Scan war unvollständig",
            "text": (
                "Nur %d Shops geprüft. Der Radar kennt 42 Shops in DE und AT. "
                "Bricht der Scan regelmäßig früh ab, liegt es meist an "
                "Zeitüberschreitungen oder daran, dass Android den Dienst beendet."
                % bericht["shops"]
            ),
        })

    if bericht["konfidenz"] is not None and 0 < bericht["konfidenz"] < 70:
        befunde.append({
            "stufe": "info",
            "titel": "Konfidenz unter der Alarmschwelle",
            "text": (
                "%d liegt unter 70. Solche Treffer werden bewusst nicht "
                "gemeldet. Senke die Schwelle nur, wenn du Falschalarme "
                "akzeptierst — oder prüfe den Beleg im Detail." % bericht["konfidenz"]
            ),
        })

    if bericht["treffer"] == 0:
        befunde.append({
            "stufe": "info",
            "titel": "Kein Treffer im letzten Scan",
            "text": (
                "Das ist kein Fehler. Prüfe Preisgrenze (Standard 900 €), "
                "Konfidenz-Schwelle und „nur bestätigte“. Erst wenn dieselben "
                "Shops über Tage 403/429 liefern, ist die Abdeckung das Problem."
            ),
        })

    if bericht["paket"] == "de.ps5pro.ps5prosearchagent":
        befunde.append({
            "stufe": "info",
            "titel": "Sideload-Linie erkannt",
            "text": (
                "Dies ist die Sideload-App. Updates kommen nicht über den Play "
                "Store, und die Play-App hat ein eigenes Paket mit getrennten "
                "Daten."
            ),
        })

    befunde.sort(key=lambda b: _STUFE_RANG.get(b["stufe"], 9))
    return befunde


def summarize(bericht):
    """Kurzzeile über dem Befund, damit man den Bericht wiedererkennt."""
    if not isinstance(bericht, dict) or bericht.get("leer"):
        return "Kein verwertbarer Bericht erkannt."
    teile = []
    if bericht["shops"] is not None:
        teile.append("%d Shops" % bericht["shops"])
    if bericht["letzter_scan"]:
        teile.append("Scan %s" % bericht["letzter_scan"])
    if bericht["treffer"] is not None:
        teile.append("%d Treffer" % bericht["treffer"])
    if bericht["konfidenz"] is not None:
        teile.append("Konfidenz %d" % bericht["konfidenz"])
    if bericht["paket"]:
        teile.append(bericht["paket"])
    return " · ".join(teile) if teile else "Bericht erkannt."
