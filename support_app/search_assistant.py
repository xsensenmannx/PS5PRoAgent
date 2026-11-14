"""Übersetzt einen Suchwunsch in prüfbare Radar-Einstellungen.

Kein Modell, kein Netz, kein Scraping: Der Assistent liest Preis, Shops,
Zustand, Filter und Intervall aus dem Text und gibt einen Plan aus, den man
im Radar einträgt. Er setzt nichts selbst — die Hilfe-App ist vom Radar
getrennt und darf dessen Einstellungen nicht schreiben.

Nur echte Einstellungen werden vorgeschlagen. Was der Radar nicht kennt
(etwa „nur neu“ als harte Regel), steht als Hinweis im Plan.
"""
import re

import support_core
from shops import SHOPS

# Grenzen aus main.py: max_preis wird dort auf 400–1500 geprüft.
PREIS_MIN, PREIS_MAX = 400.0, 1500.0
# AUTO_INTERVALS aus scan_core.
INTERVALLE = (300, 600, 900, 1800, 3600)

HINWEIS_UNKLAR = (
    "Daraus kann ich keinen Suchauftrag bauen. Nenne mir mindestens eines: "
    "Preis („unter 700“), Shop („nur Amazon“), Filter („nur verfügbar“) oder "
    "Intervall („alle 15 Minuten“)."
)

# Zahl mit Tausenderpunkt: nach dem Normalisieren bleibt "1.000" als "1 000".
_ZAHL = r"(\d{1,3}(?:\s\d{3})+|\d{3,4})"
_PREIS_WORT = re.compile(r"(?:unter|bis|max(?:imal)?|hoechstens)\s*" + _ZAHL)
_PREIS_EURO = re.compile(_ZAHL + r"\s*(?:eur|euro)\b")
_SORTIEREN = re.compile(r"sortier\w*\s+(?:nach\s+)?(\w+)")
_SORT_WORTE = {"preis": "Preis", "haendler": "Händler", "zeit": "Zeit"}

_ALIASE = {}
for _name in SHOPS:
    _basis = _name.removesuffix(" DE").removesuffix(" AT")
    _basis = _basis.removesuffix(".de").removesuffix(".at")
    _ALIASE.setdefault(support_core.normalize(_basis), []).append(_name)


def _waehle_land(namen, land):
    """Ländervariante bevorzugen, sonst Deutschland, sonst was es gibt."""
    for endung in (land, "DE"):
        if not endung:
            continue
        passend = [n for n in namen if n.endswith(" " + endung)]
        if passend:
            return passend
    return [n for n in namen if not n.endswith((" DE", " AT"))] or list(namen)


def parse_query(text):
    """Liest den Suchwunsch. Gibt immer ein vollständiges Filter-Dict zurück."""
    # "€" vor dem Normalisieren zu einem Wort machen, sonst geht das Zeichen
    # verloren und "800 €" wäre nicht als Preis erkennbar.
    q = support_core.normalize(str(text or "").replace("€", " euro "))
    tokens = set(q.split())
    warnungen = []

    preis = None
    treffer = _PREIS_WORT.search(q) or _PREIS_EURO.search(q)
    if treffer:
        wert = float(treffer.group(1).replace(" ", ""))
        if PREIS_MIN <= wert <= PREIS_MAX:
            preis = wert
        else:
            warnungen.append(
                "%.0f € liegt außerhalb des Bereichs, den der Radar annimmt "
                "(%.0f–%.0f €). Der Wert würde beim Start auf 900 € "
                "zurückfallen." % (wert, PREIS_MIN, PREIS_MAX)
            )

    land = None
    if "oesterreich" in q or "at" in tokens:
        land = "AT"
    elif "deutschland" in q or "de" in tokens:
        land = "DE"

    # Längste Aliase zuerst, damit "computerexpert" nicht "expert" trifft.
    # Sortiert wird nach Position im Text, also in der Reihenfolge der Nennung.
    shops = []
    gefunden = []
    gepolstert = " %s " % q
    for alias in sorted(_ALIASE, key=len, reverse=True):
        position = gepolstert.find(" %s " % alias)
        if position >= 0:
            for name in _waehle_land(_ALIASE[alias], land):
                gefunden.append((position, name))
    for _, name in sorted(gefunden, key=lambda paar: paar[0]):
        if name not in shops:
            shops.append(name)

    zustand = None
    if "gebraucht" in tokens:
        zustand = "gebraucht"
    elif "neu" in tokens:
        zustand = "neu"

    nur_bestaetigt = bool(tokens & {"bestaetigt", "bestaetigte"})

    filter_mode = None
    if "verfuegbar" in tokens:
        filter_mode = "verfuegbar"
    elif re.search(r"\balle\s+(?:shops?|haendler)\b", q):
        filter_mode = "alle"

    sort = None
    sortier_wunsch = _SORTIEREN.search(q)
    if sortier_wunsch and sortier_wunsch.group(1) in _SORT_WORTE:
        sort = _SORT_WORTE[sortier_wunsch.group(1)]
    elif tokens & {"guenstigste", "guenstig"}:
        sort = "Preis"

    intervall = None
    intervall_treffer = re.search(r"alle\s+(\d{1,3})\s*(?:min|minuten)", q)
    if intervall_treffer:
        gewuenscht = int(intervall_treffer.group(1)) * 60
        intervall = min(INTERVALLE, key=lambda x: abs(x - gewuenscht))

    schnellscan = bool(tokens & {"schnell", "schnellmodus"})

    return {
        "preis": preis,
        "shops": shops,
        "zustand": zustand,
        "nur_bestaetigt": nur_bestaetigt,
        "filter": filter_mode,
        "sort": sort,
        "intervall": intervall,
        "schnellscan": schnellscan,
        "warnungen": warnungen,
        "leer": not any((preis, shops, zustand, nur_bestaetigt, filter_mode,
                         sort, intervall, schnellscan)),
    }


def build_plan(text):
    """Plan mit Einstellungen, Schritten und Hinweisen."""
    f = parse_query(text)
    if f["leer"]:
        return {"kind": "unklar", "text": HINWEIS_UNKLAR, "filters": f,
                "einstellungen": [], "schritte": [], "hinweise": [],
                "zusammenfassung": ""}

    einstellungen = []
    schritte = []
    hinweise = list(f["warnungen"])

    if f["shops"]:
        einstellungen.append((
            "Händler (active_haendler)",
            "nur " + ", ".join(f["shops"]) + " (%d von %d)"
            % (len(f["shops"]), len(SHOPS)),
        ))
        schritte.append(
            "Öffne im Radar „HÄNDLER“ und aktiviere nur: %s."
            % ", ".join(f["shops"])
        )
    else:
        einstellungen.append((
            "Händler (active_haendler)", "alle %d (Standard)" % len(SHOPS)))

    if f["preis"] is not None:
        einstellungen.append(("Preisgrenze (max_preis)", "%.0f €" % f["preis"]))
        schritte.append("Setze die Preisgrenze auf %.0f €." % f["preis"])

    if f["nur_bestaetigt"]:
        einstellungen.append(("Nur bestätigte (alarm_nur_bestaetigt)", "AN"))
        schritte.append("Schalte „NUR BESTÄTIGTE“ ein.")

    if f["filter"]:
        einstellungen.append(("Trefferfilter (filter)", f["filter"]))
        schritte.append("Wähle den Filter „%s“." % f["filter"])

    if f["sort"]:
        einstellungen.append(("Sortierung (sort)", f["sort"]))
        schritte.append("Sortiere nach %s." % f["sort"])

    if f["intervall"]:
        einstellungen.append((
            "Scan-Intervall (auto_interval)",
            "%d Minuten" % (f["intervall"] // 60),
        ))
        schritte.append(
            "Stelle den automatischen Scan auf %d Minuten."
            % (f["intervall"] // 60)
        )

    if f["schnellscan"]:
        einstellungen.append(("Schnellmodus (schnellscan)", "AN"))
        schritte.append("Aktiviere den Schnellmodus für die heißen Shops.")

    if f["zustand"]:
        hinweise.append(
            "„%s“ ist im Radar keine harte Einstellung, sondern steht im "
            "Treffer-Detail. Eine Nur-%s-Regel gibt es nicht."
            % (f["zustand"], f["zustand"])
        )

    if any(name.startswith("PS Direct") for name in f["shops"]):
        hinweise.append(
            "PS Direct ist eine manuelle Quelle: Die Nutzungsbedingungen "
            "erlauben kein automatisiertes Auslesen. Rechne dort nicht mit "
            "automatischen Treffern."
        )

    if f["preis"] is not None and f["preis"] < 550:
        hinweise.append(
            "Unter 550 € liegt außerhalb der Preisspanne, die der Radar als "
            "plausibel ansieht (MIN_PREIS = 550 €)."
        )

    schritte.append(
        "Starte einen Scan und prüfe jeden Treffer im Detail: Beleg, "
        "Konfidenz und Zustand."
    )

    teile = ["PS5 Pro 2 TB"]
    if f["preis"] is not None:
        teile.append("bis %.0f €" % f["preis"])
    if f["shops"]:
        teile.append(", ".join(f["shops"]))
    if f["zustand"]:
        teile.append(f["zustand"])
    if f["nur_bestaetigt"]:
        teile.append("nur bestätigte")
    if f["filter"]:
        teile.append("Filter " + f["filter"])
    if f["sort"]:
        teile.append("Sortierung " + f["sort"])
    if f["intervall"]:
        teile.append("alle %d Minuten" % (f["intervall"] // 60))

    return {
        "kind": "plan",
        "filters": f,
        "einstellungen": einstellungen,
        "schritte": schritte,
        "hinweise": hinweise,
        "zusammenfassung": " · ".join(teile),
    }


def format_plan(plan):
    """Plan als reiner Text für die Oberfläche."""
    if plan["kind"] != "plan":
        return plan["text"]
    zeilen = ["SUCHAUFTRAG", plan["zusammenfassung"], "",
              "EINSTELLUNGEN IM RADAR"]
    for name, wert in plan["einstellungen"]:
        zeilen.append("• %s: %s" % (name, wert))
    if plan["schritte"]:
        zeilen.extend(("", "SCHRITTE"))
        for nummer, schritt in enumerate(plan["schritte"], 1):
            zeilen.append("%d. %s" % (nummer, schritt))
    if plan["hinweise"]:
        zeilen.extend(("", "HINWEISE"))
        for hinweis in plan["hinweise"]:
            zeilen.append("• " + hinweis)
    return "\n".join(zeilen)
