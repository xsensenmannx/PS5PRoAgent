#!/usr/bin/env python3
"""Wertet die NDJSON-Tageslogs des Cloud-Waechters aus.

Aufruf:
    python tools/watcher_report.py --dir cloud_watcher/data
    python tools/watcher_report.py --dir /data --kosten 4.40 --json

Gelesen werden nur Dateien nach dem Muster ``watcher-log-*.ndjson``.
Das Tool aendert nichts und nutzt ausschliesslich die Standardbibliothek.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime

LOG_MUSTER = "watcher-log-*.ndjson"
KOSTEN_MONAT = 4.40
TAGE_MONAT = 30.0
STUNDEN_TAG = 24.0


def log_dateien(daten_dir):
    """Sortierte Logdateien im Datenverzeichnis."""
    return sorted(glob.glob(os.path.join(daten_dir, LOG_MUSTER)))


def lade_zeilen(pfade):
    """Alle lesbaren JSON-Zeilen; defekte Zeilen werden uebersprungen."""
    for pfad in pfade:
        try:
            with open(pfad, "r", encoding="utf-8") as datei:
                for zeile in datei:
                    zeile = zeile.strip()
                    if not zeile:
                        continue
                    try:
                        daten = json.loads(zeile)
                    except ValueError:
                        continue
                    if isinstance(daten, dict):
                        yield daten
        except OSError:
            continue


def perzentil(werte, anteil):
    """Lineares Perzentil ohne Interpolation; None bei leerer Liste."""
    if not werte:
        return None
    anteil = max(0.0, min(1.0, float(anteil)))
    sortiert = sorted(werte)
    index = int(round(anteil * (len(sortiert) - 1)))
    return sortiert[max(0, min(len(sortiert) - 1, index))]


def _zahl(wert, standard=0.0):
    try:
        return float(wert)
    except (TypeError, ValueError):
        return float(standard)


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return "?"


def bericht(zeilen, kosten_monat=KOSTEN_MONAT):
    """Kennzahlen aus den Logzeilen berechnen.

    Als nuetzlicher Alarm zaehlt ein Alarmereignis, das nicht unterdrueckt
    und nicht wegen einer vollen Outbox verworfen wurde. Im Schattenmodus
    sind das die ``wuerde_senden``-Eintraege, live die ``eingereiht``-Eintraege.
    """
    checks = []
    alarme = 0
    restock = 0
    neu = 0
    unterdrueckt = 0
    zugestellt = 0
    klassen = {}
    zeiten = []

    for daten in zeilen:
        if not isinstance(daten, dict):
            continue
        ts = daten.get("ts")
        if ts is not None:
            zeiten.append(_zahl(ts))
        typ = daten.get("typ")
        if typ == "check":
            checks.append(daten)
            klasse = str(daten.get("klass") or "?")
            klassen[klasse] = klassen.get(klasse, 0) + 1
        elif typ == "alarm":
            aktion = str(daten.get("aktion") or "")
            if aktion == "unterdrueckt":
                unterdrueckt += 1
            elif aktion in ("wuerde_senden", "eingereiht"):
                alarme += 1
                event = str(daten.get("event") or "")
                if event == "restock":
                    restock += 1
                elif event == "new":
                    neu += 1
        elif typ == "outbox" and str(daten.get("aktion") or "") == "gesendet":
            zugestellt += 1

    ms = [max(0.0, _zahl(daten.get("ms"))) for daten in checks]
    bytes_ = [max(0.0, _zahl(daten.get("bytes"))) for daten in checks]
    frisch = sum(1 for daten in checks if daten.get("frisch") is True)
    cache = sum(1 for daten in checks if daten.get("frisch") is False)
    antworten = frisch + cache
    # Ein 304 kann auch im JSON-Fastpath auftreten und wird dort nach einem
    # erzwungenen Neuladen als frischer 200er geloggt. Massgeblich ist daher
    # das eigene Flag, nicht nur frisch=false.
    not_modified = sum(1 for daten in checks if daten.get("not_modified") is True)
    if not any("not_modified" in daten for daten in checks):
        not_modified = cache
    verifikationen = sum(1 for daten in checks if daten.get("verify"))
    traffic = int(sum(bytes_))

    von = min(zeiten) if zeiten else 0.0
    bis = max(zeiten) if zeiten else 0.0
    tage = max((bis - von) / 86400.0, 1.0 / STUNDEN_TAG)
    kosten_monat = max(0.0, _zahl(kosten_monat, KOSTEN_MONAT))
    kosten_zeitraum = kosten_monat / TAGE_MONAT * tage
    alarme_monat = alarme / tage * TAGE_MONAT

    return {
        "zeitraum": {
            "von_ts": round(von, 3),
            "bis_ts": round(bis, 3),
            "von_iso": _iso(von),
            "bis_iso": _iso(bis),
            "tage": round(tage, 2),
        },
        "checks": len(checks),
        "antworten": antworten,
        "frisch": frisch,
        "cache": cache,
        "not_modified": not_modified,
        "rate_304": round(100.0 * not_modified / antworten, 1)
        if antworten
        else 0.0,
        "ms": {
            "p50": perzentil(ms, 0.50),
            "p95": perzentil(ms, 0.95),
            "max": max(ms) if ms else None,
        },
        "bytes": traffic,
        "bytes_pro_check": round(traffic / len(checks)) if checks else 0,
        "verifikationen": verifikationen,
        "alarme": alarme,
        "restock": restock,
        "neu": neu,
        "unterdrueckt": unterdrueckt,
        "zugestellt": zugestellt,
        "klassen": klassen,
        "kosten": {
            "monat": round(kosten_monat, 2),
            "zeitraum": round(kosten_zeitraum, 2),
            "alarme_pro_monat": round(alarme_monat, 1),
            "pro_alarm": round(kosten_monat / alarme_monat, 2)
            if alarme_monat > 0
            else None,
        },
    }


def _text(daten):
    z = daten["zeitraum"]
    ms = daten["ms"]
    kosten = daten["kosten"]
    p50 = "-" if ms["p50"] is None else "%d ms" % ms["p50"]
    p95 = "-" if ms["p95"] is None else "%d ms" % ms["p95"]
    maximum = "-" if ms["max"] is None else "%d ms" % ms["max"]
    pro_alarm = (
        "- (kein Alarm)"
        if kosten["pro_alarm"] is None
        else "%.2f EUR" % kosten["pro_alarm"]
    )
    return "\n".join(
        [
            "Zeitraum: %s bis %s (%.2f Tage)"
            % (z["von_iso"], z["bis_iso"], z["tage"]),
            "Checks: %d | Treffer: %d | Chance: %d | Challenge: %d | Parser: %d"
            % (
                daten["checks"],
                daten["klassen"].get("hit", 0),
                daten["klassen"].get("chance", 0),
                daten["klassen"].get("challenge", 0),
                daten["klassen"].get("parser", 0),
            ),
            "Pruefdauer: p50 %s | p95 %s | max %s" % (p50, p95, maximum),
            "304-Quote: %.1f %% (%d von %d gueltigen Antworten, %d aus Cache)"
            % (
                daten["rate_304"],
                daten["not_modified"],
                daten["antworten"],
                daten["cache"],
            ),
            "Traffic: %.2f MB | %.0f KB pro Check | %d Verifikationen"
            % (
                daten["bytes"] / (1024.0 * 1024.0),
                daten["bytes_pro_check"] / 1024.0,
                daten["verifikationen"],
            ),
            "Alarme: %d (restock %d, neu %d, unterdrueckt %d, zugestellt %d)"
            % (
                daten["alarme"],
                daten["restock"],
                daten["neu"],
                daten["unterdrueckt"],
                daten["zugestellt"],
            ),
            "Kosten: %.2f EUR/Monat | Zeitraum %.2f EUR | pro Alarm %s"
            % (kosten["monat"], kosten["zeitraum"], pro_alarm),
            "Hochrechnung: %.1f Alarme/Monat" % kosten["alarme_pro_monat"],
        ]
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="NDJSON-Logs des Cloud-Waechters auswerten."
    )
    parser.add_argument(
        "--dir",
        default=os.environ.get("WATCH_DATA_DIR") or os.path.join("cloud_watcher", "data"),
        help="Datenverzeichnis mit watcher-log-*.ndjson",
    )
    parser.add_argument(
        "--kosten",
        type=float,
        default=KOSTEN_MONAT,
        help="Fixkosten pro Monat in Euro (Standard: %.2f)" % KOSTEN_MONAT,
    )
    parser.add_argument("--json", action="store_true", help="Kennzahlen als JSON")
    args = parser.parse_args(argv)

    pfade = log_dateien(args.dir)
    if not pfade:
        print("Keine Waechter-Logs in %s" % args.dir, file=sys.stderr)
        return 1
    zeilen = list(lade_zeilen(pfade))
    if not zeilen:
        print("Keine lesbaren Zeilen in %s" % args.dir, file=sys.stderr)
        return 1
    daten = bericht(zeilen, args.kosten)
    if args.json:
        print(json.dumps(daten, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(_text(daten))
    return 0


if __name__ == "__main__":
    sys.exit(main())
