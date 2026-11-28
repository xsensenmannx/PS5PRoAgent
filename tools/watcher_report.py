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
from datetime import datetime, timedelta

LOG_MUSTER = "watcher-log-*.ndjson"
KOSTEN_MONAT = 4.40
TAGE_MONAT = 30.0
STUNDEN_TAG = 24.0
# Ein Alarm wird nur mit einem hit-Check gepaart, der hoechstens so alt ist.
MAX_ALARM_LATENZ_S = 300.0
ZUSTELL_AKTIONEN = ("gesendet", "retry", "fehlgeschlagen", "verworfen")
# Ein Alarm gilt als widerlegt, wenn der naechste Check desselben Shops
# innerhalb dieses Fensters ``unavail`` meldet.
FEHLALARM_FENSTER_S = 600.0
# Ein Shop gilt als still, wenn er laenger als zwei Stunden keinen Check
# mehr hatte. Der Waechter prueft im 15-/30-s-Takt; zwei Stunden sind ein
# echter Ausfall, keine normale Taktluecke.
STILLE_SHOP_S = 2 * 3600.0
# Abstand, ab dem eine Beobachtung endet. Der Waechter prueft im 15-/30-s-Takt;
# zehn Minuten ohne Check sind eine Luecke (Prozess weg, Rechner aus) und keine
# Beobachtungszeit.
ABDECKUNG_SITZUNG_S = 600.0
# Feste Abnahme des 48-h-Laufs. Die Schwellen stehen hier und nicht im
# Kopf des Auswerters, damit nach dem Lauf nicht ueber die Definition
# verhandelt wird.
ABNAHME_BEOBACHTET_H = 47.5
ABNAHME_MAX_LUECKE_S = 300.0
ABNAHME_UEBERSPRUNGEN_PCT = 5.0
ABNAHME_BUDGET_VOLL = 0
ABNAHME_CANARY_MIN_TAGE = 2
# Nur diese Klassen belegen eine Bestandsbeobachtung. ``chance``
# (Lotterie, Marktabholung, Einladung) ist keine Verfuegbarkeitsaussage.
GUELTIGE_KLASSEN = ("hit", "expensive", "unavail", "unknown")
# Je Shop hoechstens 5 % Challenge-/Fehler-Checks im gesamten Lauf.
ABNAHME_SHOP_QUOTE_PCT = 5.0
# Muss zu scan_core.preis_plausibel passen. Der Report bleibt bewusst
# eigenstaendig und importiert den Scan-Kern nicht.
MIN_PREIS = 550.0
PREIS_PLAUSIBEL_MAX = 5000.0


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


def _takt_je_shop(checks_nach_shop, runde_zeilen, budget_zeilen):
    """Erreichter Takt und verhungerte Runden je Shop.

    ``faellig`` steht in jeder Runde, ``uebersprungen`` sind die Shops, die das
    Minutenbudget nicht mehr bedient hat. Ohne diese Zahl sieht ein volles
    Budget wie ein stiller Shop aus. Eine Runde mit vollem Budget zaehlt auf
    beiden Seiten gleich: Die Shops waren faellig und wurden nicht bedient.
    """
    def _leer():
        return {"checks": 0, "p50_s": None, "p95_s": None, "max_s": None,
                "faellig": 0, "uebersprungen": 0, "budget_voll": 0}

    daten = {}
    for shop, checks in checks_nach_shop.items():
        eintrag = _leer()
        eintrag["checks"] = len(checks)
        zeiten = sorted(t for t in (_check_ts(c) for c in checks) if t is not None)
        abstaende = [b - a for a, b in zip(zeiten, zeiten[1:]) if b >= a]
        if abstaende:
            eintrag["p50_s"] = round(perzentil(abstaende, 0.50), 1)
            eintrag["p95_s"] = round(perzentil(abstaende, 0.95), 1)
            eintrag["max_s"] = round(max(abstaende), 1)
        daten[shop] = eintrag

    def _zaehle(zeilen, feld, ziel):
        for zeile in zeilen:
            namen = zeile.get(feld)
            if not isinstance(namen, list):
                continue
            for name in namen:
                daten.setdefault(str(name), _leer())[ziel] += 1

    # Eine Runde mit vollem Budget hat die Shops faellig gemacht und nicht
    # bedient: Sie zaehlt auf beiden Seiten gleich, sonst schoent sie die Quote.
    _zaehle(runde_zeilen, "faellig", "faellig")
    _zaehle(budget_zeilen, "faellig", "faellig")
    _zaehle(runde_zeilen, "uebersprungen", "uebersprungen")
    _zaehle(budget_zeilen, "faellig", "uebersprungen")
    _zaehle(budget_zeilen, "faellig", "budget_voll")
    return {name: daten[name] for name in sorted(daten)}


def _wechsel_uebersicht(wechsel_zeilen):
    """Zustandswechsel je Paar, plus die letzten Eintraege im Klartext."""
    paare = {}
    liste = []
    for zeile in wechsel_zeilen:
        von = str(zeile.get("von") or "?")
        nach = str(zeile.get("nach") or "?")
        paar = "%s->%s" % (von, nach)
        paare[paar] = paare.get(paar, 0) + 1
        liste.append({
            "ts": round(_zahl(zeile.get("ts")), 3),
            "iso": _iso(zeile.get("ts")),
            "shop": str(zeile.get("shop") or ""),
            "von": von,
            "nach": nach,
            "von_preis": zeile.get("von_preis"),
            "nach_preis": zeile.get("nach_preis"),
        })
    return {"gesamt": len(liste), "paare": paare, "liste": liste[-20:]}


def _alarm_canary(zeilen):
    """Ergebnis des synthetischen Alarmtests, getrennt von echten Alarmen.

    Die Laeufe werden nach Kalendertag gruppiert. Fuer die Abnahme zaehlt je
    erwartetem Tag mindestens ein erfolgreicher Lauf; weitere Laeufe am selben
    Tag sind erlaubt, ersetzen aber keinen fehlenden Tag.
    """
    ok = sum(1 for z in zeilen if z.get("ok") is True)
    tage = {}
    for z in zeilen:
        dt = _check_dt(z)
        if dt is None:
            continue
        datum = dt.date().isoformat()
        tag = tage.setdefault(
            datum, {"datum": datum, "gesamt": 0, "ok": 0}
        )
        tag["gesamt"] += 1
        if z.get("ok") is True:
            tag["ok"] += 1
    geordnet = [tage[d] for d in sorted(tage)]
    for tag in geordnet:
        tag["bestanden"] = tag["ok"] > 0
    letzte = [
        {"iso": str(z.get("iso") or ""), "ok": z.get("ok") is True,
         "event": z.get("event")}
        for z in zeilen[-5:]
    ]
    return {
        "gesamt": len(zeilen),
        "ok": ok,
        "fehlgeschlagen": len(zeilen) - ok,
        "tage_gesamt": len(geordnet),
        "tage_ok": sum(1 for t in geordnet if t["bestanden"]),
        "tage": geordnet,
        "letzte": letzte,
    }


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
    alarme_zeilen = []
    outbox_zeilen = []
    checks_nach_shop = {}
    konfigurierte_shops = set()
    runde_zeilen = []
    budget_zeilen = []
    wechsel_zeilen = []
    alarm_canary_zeilen = []

    for daten in zeilen:
        if not isinstance(daten, dict):
            continue
        ts = daten.get("ts")
        if ts is not None:
            zeiten.append(_zahl(ts))
        typ = daten.get("typ")
        if typ == "check":
            checks.append(daten)
            checks_nach_shop.setdefault(str(daten.get("shop") or ""), []).append(daten)
            klasse = str(daten.get("klass") or "?")
            klassen[klasse] = klassen.get(klasse, 0) + 1
        elif typ == "start":
            for shop in daten.get("shops") or []:
                if shop:
                    konfigurierte_shops.add(str(shop))
        elif typ == "runde":
            runde_zeilen.append(daten)
        elif typ == "budget":
            budget_zeilen.append(daten)
        elif typ == "wechsel":
            wechsel_zeilen.append(daten)
        elif typ == "alarm_canary":
            alarm_canary_zeilen.append(daten)
        elif typ == "alarm":
            # Der synthetische Canary laeuft durch dieselbe melde()-Kette,
            # darf aber keine echte Alarmquote verfaelschen.
            if daten.get("canary") is True:
                continue
            alarme_zeilen.append(daten)
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
        elif typ == "outbox":
            outbox_zeilen.append(daten)
            if str(daten.get("aktion") or "") == "gesendet":
                zugestellt += 1

    alarm_latenz = _alarm_latenz(alarme_zeilen, checks_nach_shop, outbox_zeilen)
    fehlalarme = _fehlalarme(alarme_zeilen, checks_nach_shop)
    jetzt = max(zeiten) if zeiten else 0.0
    stille_shops = _stille_shops(checks_nach_shop, jetzt,
                                 konfigurierte_shops=konfigurierte_shops)
    abdeckung = _abdeckung_stunden(checks, konfigurierte_shops)
    shop_takt = _takt_je_shop(checks_nach_shop, runde_zeilen, budget_zeilen)
    shop_qualitaet = _shop_qualitaet(checks_nach_shop)
    wechsel = _wechsel_uebersicht(wechsel_zeilen)
    preise = _preis_telemetrie(checks)
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

    ergebnis = {
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
        "alarm_latenz": alarm_latenz,
        "fehlalarme": fehlalarme,
        "stille_shops": stille_shops,
        "abdeckung_stunden": abdeckung,
        "shop_takt": shop_takt,
        "shop_qualitaet": shop_qualitaet,
        "wechsel": wechsel,
        "alarm_canary": _alarm_canary(alarm_canary_zeilen),
        "preis_telemetrie": preise,
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
    ergebnis["abnahme"] = _abnahme(ergebnis)
    return ergebnis


def _alarm_latenz(alarme, checks_nach_shop, outbox):
    """Erkennung bis erster Zustellversuch, in Millisekunden.

    Paart jeden Alarm mit dem letzten ``hit``-Check desselben Shops davor
    (hoechstens ``MAX_ALARM_LATENZ_S``) und mit der ersten Outbox-Zeile seiner
    ``outbox_id``. Im Schattenmodus gibt es keine Outbox-Zeile: Dort ist die
    ``wuerde_senden``-Zeile selbst der simulierte Zustellversuch. So misst die
    Kennzahl in beiden Modi denselben Weg und braucht keinen neuen Abruf.
    """
    outbox_nach_id = {}
    for zeile in outbox:
        if zeile.get("aktion") not in ZUSTELL_AKTIONEN:
            continue
        oid = zeile.get("id")
        if not oid:
            continue
        ts = _zahl(zeile.get("ts"), 0.0)
        if oid not in outbox_nach_id or ts < outbox_nach_id[oid]:
            outbox_nach_id[oid] = ts

    werte = []
    ohne_check = 0
    ohne_versuch = 0
    for alarm in alarme:
        if alarm.get("aktion") not in ("wuerde_senden", "eingereiht"):
            continue
        ts = _zahl(alarm.get("ts"), 0.0)
        shop = str(alarm.get("shop") or "")
        erkennung = None
        for pruefung in checks_nach_shop.get(shop, []):
            if pruefung.get("klass") != "hit":
                continue
            cts = _zahl(pruefung.get("ts"), 0.0)
            if cts <= ts and ts - cts <= MAX_ALARM_LATENZ_S:
                if erkennung is None or cts > erkennung:
                    erkennung = cts
        if erkennung is None:
            ohne_check += 1
            continue

        oid = alarm.get("outbox_id")
        if oid:
            versuch = outbox_nach_id.get(oid)
            if versuch is None:
                ohne_versuch += 1
                continue
        else:
            # Schattenmodus: die simulierte Zustellung ist der Alarm selbst.
            versuch = ts
        latenz = max(0.0, versuch - erkennung)
        if latenz <= MAX_ALARM_LATENZ_S:
            werte.append(latenz)
        else:
            ohne_versuch += 1

    return {
        "p50": _ms(perzentil(werte, 0.50)),
        "p95": _ms(perzentil(werte, 0.95)),
        "max": _ms(max(werte)) if werte else None,
        "gemessen": len(werte),
        "ohne_check": ohne_check,
        "ohne_versuch": ohne_versuch,
    }


def _fehlalarme(alarme, checks_nach_shop):
    """Alarme, die der naechste Check binnen zehn Minuten widerlegt.

    Massgeblich ist der erste Check desselben Shops nach dem Alarm. Nur
    ``unavail`` widerlegt; ``hit``/``expensive`` bestaetigen; ``parser``,
    ``error``, ``challenge`` und ``chance`` sind keine Aussage und bleiben
    unklar. Ohne Check im Fenster bleibt der Alarm offen. Die Quote bezieht
    sich nur auf Alarme mit klarem Gegencheck, damit offene Zeilen sie nicht
    kuenstlich druecken.
    """
    widerlegt = bestaetigt = unklar = offen = 0
    for alarm in alarme:
        if alarm.get("aktion") not in ("wuerde_senden", "eingereiht"):
            continue
        ts = _zahl(alarm.get("ts"), 0.0)
        shop = str(alarm.get("shop") or "")
        naechster = None
        for pruefung in checks_nach_shop.get(shop, []):
            cts = _zahl(pruefung.get("ts"), 0.0)
            if cts <= ts or cts - ts > FEHLALARM_FENSTER_S:
                continue
            if naechster is None or cts < naechster[0]:
                naechster = (cts, pruefung)
        if naechster is None:
            offen += 1
            continue
        klasse = str(naechster[1].get("klass") or "")
        if klasse == "unavail":
            widerlegt += 1
        elif klasse in ("hit", "expensive"):
            bestaetigt += 1
        else:
            unklar += 1
    geprueft = widerlegt + bestaetigt
    return {
        "widerlegt": widerlegt,
        "bestaetigt": bestaetigt,
        "unklar": unklar,
        "offen": offen,
        "gesamt": widerlegt + bestaetigt + unklar + offen,
        "geprueft": geprueft,
        "quote": round(100.0 * widerlegt / geprueft, 1) if geprueft else None,
    }


def _check_ts(daten):
    try:
        return float(daten.get("ts"))
    except (TypeError, ValueError):
        return None


def _stille_shops(checks_nach_shop, jetzt, schwelle=STILLE_SHOP_S,
                  konfigurierte_shops=None):
    """Shops ohne Check innerhalb der Schwelle, mit plausibler Ursache.

    ``keine_checks`` ist der wichtigste Fall: Der Shop steht im Start-Log,
    taucht aber im gesamten Zeitraum mit keinem Check auf. ``keine_daten``
    bedeutet Check-Zeilen ohne brauchbaren Zeitstempel.
    """
    stille = []
    alle = set(checks_nach_shop) | set(konfigurierte_shops or ())
    for shop in alle:
        checks = checks_nach_shop.get(shop, [])
        if not checks:
            stille.append({
                "shop": shop,
                "letzter_check_ts": None,
                "letzter_check_iso": "?",
                "alter_s": None,
                "checks": 0,
                "ursache": "keine_checks",
            })
            continue
        zeiten = [t for t in (_check_ts(c) for c in checks) if t is not None]
        if not zeiten:
            stille.append({
                "shop": shop,
                "letzter_check_ts": None,
                "letzter_check_iso": "?",
                "alter_s": None,
                "checks": len(checks),
                "ursache": "keine_daten",
            })
            continue
        letzte = max(zeiten)
        alter = max(0.0, float(jetzt) - letzte)
        if alter <= schwelle:
            continue
        letzte_klassen = [str(c.get("klass") or "") for c in checks[-5:]]
        if letzte_klassen and all(k == "challenge" for k in letzte_klassen):
            ursache = "nur_challenge"
        elif letzte_klassen and all(
            k in ("error", "parser") for k in letzte_klassen
        ):
            ursache = "nur_fehler"
        elif letzte_klassen and all(k == "unavail" for k in letzte_klassen):
            ursache = "nur_unavail"
        else:
            ursache = "gemischt"
        stille.append({
            "shop": shop,
            "letzter_check_ts": round(letzte, 3),
            "letzter_check_iso": _iso(letzte),
            "alter_s": int(alter),
            "checks": len(checks),
            "ursache": ursache,
        })
    stille.sort(key=lambda e: (
        0 if e["ursache"] in ("keine_checks", "keine_daten") else 1,
        -(e["alter_s"] or 0),
    ))
    return {
        "schwelle_s": int(schwelle),
        "gesamt": len(alle),
        "stille": stille,
    }


def _check_dt(daten):
    """Lokale Zeit eines Checks: ISO zuerst, sonst Unix-Zeitstempel."""
    iso = daten.get("iso")
    if iso:
        try:
            return datetime.fromisoformat(str(iso))
        except (TypeError, ValueError):
            pass
    ts = _check_ts(daten)
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts)
    except (OSError, OverflowError, ValueError):
        return None


def _beobachtete_sekunden(zeiten):
    """Summe der Abstaende, die innerhalb einer Sitzung liegen.

    Eine Stunde zwischen zwei Checks ist keine Beobachtungszeit, sondern eine
    Luecke. Gezaehlt wird nur, was im Takt liegt (``ABDECKUNG_SITZUNG_S``).
    """
    zeiten = sorted(zeiten)
    return float(sum(
        b - a for a, b in zip(zeiten, zeiten[1:])
        if 0.0 <= b - a <= ABDECKUNG_SITZUNG_S
    ))


def _abdeckung_stunden(checks, konfigurierte_shops=()):
    """Abdeckung je Kalendertag, je Shop und beobachtete Zeit.

    Fuer Abdeckung, Sitzungen und Beobachtungszeit zaehlen ausschliesslich
    gueltige Bestandsbeobachtungen (``GUELTIGE_KLASSEN``). Challenge-, Fehler-
    und Parser-Checks sowie ``chance`` belegen keinen Bestand; sie erzeugen
    aber weiterhin einen Tag, damit ein dauerhaft geblockter Shop als
    ``0/24`` sichtbar bleibt und nicht aus der Auswertung verschwindet.
    Zusaetzlich muss jeder Shop in jeder erwarteten Stunde mindestens einen
    gueltigen Check haben; ein einzelner Check am Rand fuellt keinen Tag.
    Konfigurierte Shops ohne Check erscheinen mit 0 Stunden.
    Randtage zaehlen mit ihrem tatsaechlichen Fenster; ein Check exakt auf
    der Stundengrenze am Ende zaehlt die neue Stunde nicht mit.
    """
    def _leerer_tag(datum):
        return {"datum": datum, "stunden": [0] * 24, "checks": 0,
                "checks_gueltig": 0, "zeiten": []}

    tage = {}
    stunden_je_shop = {}
    zeiten_je_shop = {}
    zeitpunkte = []
    gueltig = 0
    for daten in checks:
        dt = _check_dt(daten)
        if dt is None:
            continue
        tag = dt.date().isoformat()
        shop = str(daten.get("shop") or "?")
        shop_stunden = stunden_je_shop.setdefault(shop, {})
        eintrag = tage.setdefault(tag, _leerer_tag(tag))
        eintrag["checks"] += 1
        if str(daten.get("klass") or "") not in GUELTIGE_KLASSEN:
            continue
        gueltig += 1
        eintrag["checks_gueltig"] += 1
        eintrag["stunden"][dt.hour] += 1
        shop_stunden.setdefault(tag, set()).add(dt.hour)
        ts = _check_ts(daten)
        if ts is not None:
            eintrag["zeiten"].append(ts)
            zeitpunkte.append(ts)
            zeiten_je_shop.setdefault(shop, []).append(ts)

    # Tage ohne einen einzigen Check ebenfalls aufnehmen: Ein Ausfall ueber
    # einen ganzen Kalendertag muss als 0/24 sichtbar sein und darf nicht
    # stillschweigend aus der Tagesliste verschwinden.
    if tage:
        vorhandene = sorted(tage)
        erster_datum = datetime.fromisoformat(vorhandene[0]).date()
        letzter_datum = datetime.fromisoformat(vorhandene[-1]).date()
        tag = erster_datum
        while tag <= letzter_datum:
            schluessel = tag.isoformat()
            tage.setdefault(schluessel, _leerer_tag(schluessel))
            tag += timedelta(days=1)

    # Erstes und letztes Check-Zeitfenster bestimmen. Randtage werden mit
    # ihrem tatsaechlichen Fenster gewertet: Ein Lauf ab 12:00 hat am ersten
    # Tag 12 erwartete Stunden, keine 12 fehlenden. Ein fehlender Check in
    # einer erwarteten Stunde bleibt dagegen ein Fehler.
    mit_ts = [c for c in checks if _check_ts(c) is not None]
    erste = min(mit_ts, key=_check_ts) if mit_ts else None
    letzte = max(mit_ts, key=_check_ts) if mit_ts else None
    erste_dt = _check_dt(erste) if erste is not None else None
    letzte_dt = _check_dt(letzte) if letzte is not None else None
    erster_tag = erste_dt.date().isoformat() if erste_dt else None
    letzter_tag = letzte_dt.date().isoformat() if letzte_dt else None
    erste_stunde = erste_dt.hour if erste_dt else 0
    letzte_stunde = letzte_dt.hour if letzte_dt else 23
    letzte_am_rand = bool(
        letzte_dt is not None
        and letzte_dt.minute == 0
        and letzte_dt.second == 0
        and letzte_dt.microsecond == 0
    )

    pro_tag = []
    fenster = {}
    for datum in sorted(tage):
        eintrag = tage[datum]
        sekunden = _beobachtete_sekunden(eintrag["zeiten"])
        start = erste_stunde if datum == erster_tag else 0
        ende = letzte_stunde if datum == letzter_tag else 23
        # Ein Check exakt auf der Endstundengrenze belegt die neue Stunde
        # nicht mehr; am einzigen Tag bleibt mindestens die Startstunde.
        if (datum == letzter_tag and letzte_am_rand
                and (datum != erster_tag or ende > start)):
            ende -= 1
        erwartet = list(range(start, ende + 1)) if start <= ende else []
        fenster[datum] = erwartet
        fehlend = [h for h in erwartet if eintrag["stunden"][h] == 0]
        pro_tag.append({
            "datum": datum,
            "checks": eintrag["checks"],
            "checks_gueltig": eintrag["checks_gueltig"],
            "beobachtet_s": int(round(sekunden)),
            "beobachtet_h": round(sekunden / 3600.0, 2),
            "erwartet_h": len(erwartet),
            "abgedeckt_im_fenster": len(erwartet) - len(fehlend),
            "fehlende_stunden": fehlend,
            "randtag": 0 < len(erwartet) < 24,
            "bestanden": not fehlend,
        })

    for shop in konfigurierte_shops:
        stunden_je_shop.setdefault(str(shop), {})
    erwartet_gesamt = sum(len(h) for h in fenster.values())
    shops = {}
    for shop in sorted(stunden_je_shop):
        belegt = stunden_je_shop[shop]
        fehlende_h = 0
        erste_fehlende = None
        for datum, stunden in fenster.items():
            for h in stunden:
                if h in belegt.get(datum, ()):
                    continue
                fehlende_h += 1
                if erste_fehlende is None:
                    erste_fehlende = "%s %02d" % (datum, h)
        shop_zeiten = sorted(zeiten_je_shop.get(shop, []))
        luecke = max(
            (b - a for a, b in zip(shop_zeiten, shop_zeiten[1:])),
            default=0.0,
        )
        shops[shop] = {
            "erwartet_h": erwartet_gesamt,
            "abgedeckt_h": erwartet_gesamt - fehlende_h,
            "fehlende_h": fehlende_h,
            "erste_fehlende": erste_fehlende,
            "luecke_max_s": int(round(luecke)),
            "bestanden": (
                erwartet_gesamt > 0
                and fehlende_h == 0
                and luecke <= ABNAHME_MAX_LUECKE_S
            ),
        }

    beobachtet = _beobachtete_sekunden(zeitpunkte)
    zeiten = sorted(zeitpunkte)
    sitzungen = 1 if zeiten else 0
    for a, b in zip(zeiten, zeiten[1:]):
        if b - a > ABDECKUNG_SITZUNG_S:
            sitzungen += 1
    luecke_max = max(
        (b - a for a, b in zip(zeiten, zeiten[1:])),
        default=0.0,
    )
    return {
        "checks_gesamt": len(checks),
        "checks_gueltig": gueltig,
        "ungueltig": len(checks) - gueltig,
        "beobachtet_s": int(round(beobachtet)),
        "beobachtet_h": round(beobachtet / 3600.0, 2),
        "luecke_max_s": int(round(luecke_max)),
        "sitzungen": sitzungen,
        "schwelle_s": int(ABDECKUNG_SITZUNG_S),
        "tage": pro_tag,
        "shops": shops,
    }


def _preis_telemetrie(checks):
    """Wie oft ein Check einen plausiblen Preis hatte.

    Die Extraktoren verwerfen 0/1 EUR und >5000 EUR bereits; sie landen
    als ``preis=None`` im Log. Diese Zahl macht den stillen Verlust sichtbar.
    """
    gueltig = ohne = unplausibel = 0
    for daten in checks:
        preis = daten.get("preis")
        if preis is None:
            ohne += 1
            continue
        try:
            preis = float(preis)
        except (TypeError, ValueError):
            ohne += 1
            continue
        if MIN_PREIS <= preis <= PREIS_PLAUSIBEL_MAX:
            gueltig += 1
        else:
            unplausibel += 1
    gesamt = gueltig + ohne + unplausibel
    return {
        "gueltig": gueltig,
        "ohne_preis": ohne,
        "unplausibel": unplausibel,
        "gesamt": gesamt,
        "anteil_ohne": round(
            100.0 * (ohne + unplausibel) / gesamt, 1
        ) if gesamt else 0.0,
    }


def _ms(wert):
    return None if wert is None else int(round(float(wert) * 1000.0))


def _tage_wort(n):
    return "Tag" if int(n) == 1 else "Tage"


def _shop_qualitaet(checks_nach_shop):
    """Challenge-/Fehlerquote je Shop ueber den gesamten Lauf.

    ``quote`` zaehlt Challenge sowie Netz-/Parserfehler. ``ungueltig_quote``
    zaehlt zusaetzlich jede andere Nicht-Beobachtung (insbesondere
    ``chance``), weil auch sie keinen Bestand belegt.
    """
    daten = {}
    for shop, checks in checks_nach_shop.items():
        gesamt = len(checks)
        zaehler = {"challenge": 0, "error": 0, "parser": 0, "chance": 0}
        gueltig = 0
        for pruefung in checks:
            klasse = str(pruefung.get("klass") or "")
            if klasse in zaehler:
                zaehler[klasse] += 1
            if klasse in GUELTIGE_KLASSEN:
                gueltig += 1
        fehler = zaehler["error"] + zaehler["parser"]
        quote = 100.0 * (zaehler["challenge"] + fehler) / gesamt if gesamt else None
        ungueltig = gesamt - gueltig
        ungueltig_quote = 100.0 * ungueltig / gesamt if gesamt else None
        # ungueltig enthaelt Challenge und Fehler bereits; eine zweite
        # Schwelle auf quote waere daher immer redundant. Vergleich auf
        # ungerundeten Prozentwerten, die Anzeige rundet erst.
        bestanden = (
            ungueltig_quote is not None
            and ungueltig_quote < ABNAHME_SHOP_QUOTE_PCT
        )
        daten[shop] = {
            "checks": gesamt,
            "challenge": zaehler["challenge"],
            "fehler": fehler,
            "chance": zaehler["chance"],
            "quote": round(quote, 2) if quote is not None else None,
            "ungueltig": ungueltig,
            "ungueltig_quote": round(ungueltig_quote, 2)
            if ungueltig_quote is not None else None,
            "bestanden": bestanden,
        }
    return daten


def _abnahme(daten):
    """Feste Bestanden-Kriterien fuer den 48-h-Lauf.

    Abdeckung: jeder Kalendertag im Beobachtungsfenster hat in jeder
    erwarteten Stunde mindestens einen Check; Randtage zaehlen mit ihrem
    tatsaechlichen Fenster, volle Tage mit 24 Stunden. Jeder Shop muss
    zusaetzlich jede erwartete Stunde selbst abdecken und dabei seine eigene
    groesste Luecke von 5 min einhalten, damit sich Shops nicht gegenseitig
    fuellen und zwei Checks am Stundenrand keinen Ausfall verdecken.
    Zusaetzlich muessen mindestens 47,5 h beobachtet sein und die groesste
    Luecke ueber alle Shops darf 5 min nicht ueberschreiten.
    Die groesste Luecke von 5 min deckt die fruehere Sitzungspruefung ab:
    Jede Unterbrechung ueber 10 min erzeugt eine groessere Luecke; eine eigene
    Sitzungszahl waere nur ein zweiter Name fuer dieselbe Bedingung.
    Uebersprungen: unter 5 % aller faelligen Shops.
    Budget voll: kein einziger Fall. Canary: fuer jeden Kalendertag mindestens
    ein erfolgreicher Lauf, mindestens zwei Tage; weitere Laeufe am selben Tag
    sind erlaubt. Stille Shops: keiner.
    Je Shop muss der Anteil ungueltiger Checks unter 5 % liegen; Challenge
    und Fehler sind darin enthalten. Damit faellt ein dauerhaft geblockter
    Shop durch, auch wenn andere Shops die Stunden fuellen. Abdeckung und
    Beobachtungszeit zaehlen nur gueltige Bestandsbeobachtungen.
    """
    ab = daten.get("abdeckung_stunden") or {}
    tage = list(ab.get("tage") or [])
    shops = dict(ab.get("shops") or {})
    beobachtet_h = float(ab.get("beobachtet_h") or 0.0)
    luecke_max_s = int(ab.get("luecke_max_s") or 0)
    vollstaendig = sum(1 for t in tage if t.get("bestanden"))
    shops_voll = sum(1 for e in shops.values() if e.get("bestanden"))
    abdeckung_ok = (
        bool(tage)
        and vollstaendig == len(tage)
        and bool(shops)
        and shops_voll == len(shops)
        and beobachtet_h >= ABNAHME_BEOBACHTET_H
        and luecke_max_s <= ABNAHME_MAX_LUECKE_S
    )
    abdeckung_wert = (
        "%d %s, %d/%d vollstaendig, %.2f h, max. Luecke %d s, "
        "%d/%d Shops vollstaendig"
        % (len(tage), _tage_wort(len(tage)), vollstaendig, len(tage),
           beobachtet_h, luecke_max_s, shops_voll, len(shops))
        if tage else "keine Tagesdaten"
    )
    abdeckung_detail = [
        "%s %d/%d%s%s"
        % (
            str(t.get("datum") or "?"),
            int(t.get("abgedeckt_im_fenster") or 0),
            int(t.get("erwartet_h") or 0),
            " (Randtag)" if t.get("randtag") else "",
            " fehlt: " + ",".join(
                "%02d" % h for h in (t.get("fehlende_stunden") or [])
            ) if t.get("fehlende_stunden") else "",
        )
        for t in tage
    ]
    for name, e in sorted(shops.items()):
        zeile = "%s: %d/%d h, Luecke %d s" % (
            name,
            int(e.get("abgedeckt_h") or 0),
            int(e.get("erwartet_h") or 0),
            int(e.get("luecke_max_s") or 0),
        )
        fehlende_h = int(e.get("fehlende_h") or 0)
        if fehlende_h:
            zeile += " (fehlt %d h, zuerst %s)" % (
                fehlende_h, e.get("erste_fehlende") or "?")
        abdeckung_detail.append(zeile)

    takt = daten.get("shop_takt") or {}
    faellig = sum(int(e.get("faellig") or 0) for e in takt.values())
    uebersprungen = sum(int(e.get("uebersprungen") or 0) for e in takt.values())
    quote = 100.0 * uebersprungen / faellig if faellig else None
    ueber_ok = quote is not None and quote < ABNAHME_UEBERSPRUNGEN_PCT
    ueber_wert = (
        "%d von %d (%.1f %%)" % (uebersprungen, faellig, quote)
        if quote is not None else "keine Runden"
    )

    budget_voll = sum(int(e.get("budget_voll") or 0) for e in takt.values())
    budget_ok = faellig > 0 and budget_voll == ABNAHME_BUDGET_VOLL
    budget_wert = str(budget_voll) if faellig else "keine Runden"

    canary = daten.get("alarm_canary") or {}
    canary_gesamt = int(canary.get("gesamt") or 0)
    canary_ok_n = int(canary.get("ok") or 0)
    canary_nach_tag = {
        str(t.get("datum")): t for t in (canary.get("tage") or [])
    }
    canary_erwartet = [str(t.get("datum")) for t in tage]
    canary_fehlt = [
        d for d in canary_erwartet
        if not (canary_nach_tag.get(d) or {}).get("bestanden")
    ]
    canary_ok = (
        len(canary_erwartet) >= ABNAHME_CANARY_MIN_TAGE
        and not canary_fehlt
    )
    canary_wert = "%d/%d Tage ok (%d %s, %d fehlgeschlagen)" % (
        len(canary_erwartet) - len(canary_fehlt), len(canary_erwartet),
        canary_gesamt,
        "Lauf" if canary_gesamt == 1 else "Laeufe",
        canary_gesamt - canary_ok_n,
    )
    canary_detail = []
    for datum in canary_erwartet:
        eintrag = canary_nach_tag.get(datum)
        if not eintrag:
            canary_detail.append("%s fehlt" % datum)
            continue
        laeufe = int(eintrag.get("gesamt") or 0)
        canary_detail.append(
            "%s %s (%d %s)"
            % (datum, "ok" if eintrag.get("bestanden") else "kein Erfolg",
               laeufe, "Lauf" if laeufe == 1 else "Laeufe")
        )

    stille = daten.get("stille_shops") or {}
    stille_n = len(stille.get("stille") or [])
    stille_gesamt = int(stille.get("gesamt") or 0)
    stille_ok = stille_gesamt > 0 and stille_n == 0

    qualitaet = daten.get("shop_qualitaet") or {}
    qualitaet_ok = bool(qualitaet) and all(
        bool(e.get("bestanden")) for e in qualitaet.values()
    )
    if qualitaet:
        max_quote = max(float(e.get("quote") or 0.0) for e in qualitaet.values())
        max_uquote = max(float(e.get("ungueltig_quote") or 0.0)
                         for e in qualitaet.values())
        qualitaet_wert = (
            "max. %.2f %% Challenge/Fehler, %.2f %% ungueltig (%d Shops)"
            % (max_quote, max_uquote, len(qualitaet))
        )
    else:
        qualitaet_wert = "keine Shops"
    qualitaet_detail = [
        "%s: %d/%d Challenge/Fehler (%.2f %%), ungueltig %.2f %% "
        "(Chance %d)"
        % (
            name,
            int(e.get("challenge") or 0) + int(e.get("fehler") or 0),
            int(e.get("checks") or 0),
            float(e.get("quote") or 0.0),
            float(e.get("ungueltig_quote") or 0.0),
            int(e.get("chance") or 0),
        )
        for name, e in sorted(qualitaet.items())
    ]

    kriterien = [
        {"name": "abdeckung", "label": "Abdeckung",
         "ok": abdeckung_ok, "wert": abdeckung_wert,
         "soll": "24/24 je Tag und Shop, >= %.1f h, Luecke <= %d s"
                 % (ABNAHME_BEOBACHTET_H, int(ABNAHME_MAX_LUECKE_S)),
         "detail": abdeckung_detail},
        {"name": "shop_qualitaet", "label": "Shop-Quote",
         "ok": qualitaet_ok, "wert": qualitaet_wert,
         "soll": "< %.1f %% ungueltig je Shop" % ABNAHME_SHOP_QUOTE_PCT,
         "detail": qualitaet_detail},
        {"name": "uebersprungen", "label": "Uebersprungen",
         "ok": ueber_ok, "wert": ueber_wert,
         "soll": "< %.1f %%" % ABNAHME_UEBERSPRUNGEN_PCT},
        {"name": "budget_voll", "label": "Budget voll",
         "ok": budget_ok, "wert": budget_wert, "soll": "0"},
        {"name": "canary", "label": "Alarm-Canary",
         "ok": canary_ok, "wert": canary_wert,
         "detail": canary_detail,
         "soll": "je Tag >= 1 Erfolg, mind. %d Tage"
                 % ABNAHME_CANARY_MIN_TAGE},
        {"name": "stille_shops", "label": "Stille Shops",
         "ok": stille_ok, "wert": "%d von %d" % (stille_n, stille_gesamt),
         "soll": "0"},
    ]
    fehlgeschlagen = [k["name"] for k in kriterien if not k["ok"]]
    return {
        "bestanden": not fehlgeschlagen,
        "kriterien": kriterien,
        "fehlgeschlagen": fehlgeschlagen,
    }


def _abnahme_text(abnahme):
    status = "BESTANDEN" if abnahme.get("bestanden") else "NICHT BESTANDEN"
    zeilen = ["Abnahme 48 h: %s" % status]
    for k in abnahme.get("kriterien") or []:
        zeilen.append(
            "  [%s] %s: %s (Soll: %s)"
            % ("ok" if k.get("ok") else "FEHLT", k.get("label"),
               k.get("wert"), k.get("soll"))
        )
        if k.get("name") in ("abdeckung", "shop_qualitaet", "canary"):
            for detail in k.get("detail") or []:
                zeilen.append("      " + detail)
    if abnahme.get("fehlgeschlagen"):
        zeilen.append(
            "  Nicht bestanden: " + ", ".join(abnahme["fehlgeschlagen"])
        )
    return "\n".join(zeilen)


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
    lat = daten.get("alarm_latenz") or {}
    latenz = (
        "Alarm-Latenz: p50 %s | p95 %s | max %s "
        "(%d gemessen, %d ohne Check, %d ohne Versuch)"
        % (
            "-" if lat.get("p50") is None else "%d ms" % lat["p50"],
            "-" if lat.get("p95") is None else "%d ms" % lat["p95"],
            "-" if lat.get("max") is None else "%d ms" % lat["max"],
            int(lat.get("gemessen") or 0),
            int(lat.get("ohne_check") or 0),
            int(lat.get("ohne_versuch") or 0),
        )
    )
    abdeckung = daten.get("abdeckung_stunden") or {}
    stille = daten.get("stille_shops") or {}
    preise = daten.get("preis_telemetrie") or {}
    tage = abdeckung.get("tage") or []
    tage_text = " | ".join(
        "%s %d/%d%s, %.2f h, %d/%d Checks gueltig"
        % (
            str(t.get("datum") or "?"),
            int(t.get("abgedeckt_im_fenster") or 0),
            int(t.get("erwartet_h") or 0),
            " (Randtag)" if t.get("randtag") else "",
            float(t.get("beobachtet_h") or 0.0),
            int(t.get("checks_gueltig") or 0),
            int(t.get("checks") or 0),
        )
        for t in tage
    ) or "keine"
    vollstaendige_tage = sum(1 for t in tage if t.get("bestanden"))
    abdeckung_text = (
        "Abdeckung: %d/%d %s vollstaendig"
        % (vollstaendige_tage, len(tage),
           "Tag" if len(tage) == 1 else "Tage")
        if tage else "Abdeckung: keine Tagesdaten"
    )
    takt = daten.get("shop_takt") or {}
    takt_text = " | ".join(
        "%s p95 %s, %d von %d Runden uebersprungen"
        % (
            name,
            "-" if e.get("p95_s") is None else "%d s" % int(round(e["p95_s"])),
            int(e.get("uebersprungen") or 0),
            int(e.get("faellig") or 0),
        )
        for name, e in takt.items()
    ) or "keine"
    wechsel_daten = daten.get("wechsel") or {}
    wechsel_text = ", ".join(
        "%s %d" % (paar, anzahl)
        for paar, anzahl in sorted((wechsel_daten.get("paare") or {}).items())
    ) or "keine"
    canary_daten = daten.get("alarm_canary") or {}
    canary_text = "Alarm-Canary: %d/%d Tage ok (%d %s, %d fehlgeschlagen)" % (
        int(canary_daten.get("tage_ok") or 0),
        int(canary_daten.get("tage_gesamt") or 0),
        int(canary_daten.get("gesamt") or 0),
        "Lauf" if int(canary_daten.get("gesamt") or 0) == 1 else "Laeufe",
        int(canary_daten.get("fehlgeschlagen") or 0),
    )
    if canary_daten.get("gesamt"):
        letzter = (canary_daten.get("letzte") or [{}])[-1]
        canary_text += " (zuletzt %s: %s)" % (
            str(letzter.get("iso") or "?"),
            "ok" if letzter.get("ok") else "kein Ereignis",
        )
    def _stille_text(e):
        if e.get("ursache") in ("keine_checks", "keine_daten"):
            return "%s (ohne Check)" % e.get("shop")
        return "%s (%dh)" % (
            e.get("shop"), int(e.get("alter_s") or 0) // 3600
        )

    stille_liste = ", ".join(
        _stille_text(e) for e in (stille.get("stille") or [])[:5]
    ) or "keine"
    fq = daten.get("fehlalarme") or {}
    fehlalarm_text = (
        "Fehlalarme: %d von %d geprueft (%s), %d bestaetigt, %d unklar, %d offen"
        % (
            int(fq.get("widerlegt") or 0),
            int(fq.get("geprueft") or 0),
            "-" if fq.get("quote") is None else "%.1f %%" % fq["quote"],
            int(fq.get("bestaetigt") or 0),
            int(fq.get("unklar") or 0),
            int(fq.get("offen") or 0),
        )
    )
    abnahme = daten.get("abnahme") or _abnahme(daten)
    return _abnahme_text(abnahme) + "\n\n" + "\n".join(
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
            latenz,
            fehlalarm_text,
            abdeckung_text,
            "Gueltige Beobachtungen: %d von %d Checks (%d ungueltig)"
            % (
                int(abdeckung.get("checks_gueltig") or 0),
                int(abdeckung.get("checks_gesamt") or 0),
                int(abdeckung.get("ungueltig") or 0),
            ),
            "Beobachtet: %.2f h in %d Sitzungen (Abstand > %d min gilt als Luecke)"
            % (
                float(abdeckung.get("beobachtet_h") or 0.0),
                int(abdeckung.get("sitzungen") or 0),
                int(abdeckung.get("schwelle_s") or 0) // 60,
            ),
            "Abdeckung je Tag: %s" % tage_text,
            "Shop-Takt: %s" % takt_text,
            canary_text,
            "Zustandswechsel: %d (%s)"
            % (int(wechsel_daten.get("gesamt") or 0), wechsel_text),
            "Stille Shops: %d von %d (Schwelle %dh): %s"
            % (
                len(stille.get("stille") or []),
                int(stille.get("gesamt") or 0),
                int(stille.get("schwelle_s") or 0) // 3600,
                stille_liste,
            ),
            "Preise: %d gueltig, %d ohne Preis, %d unplausibel "
            "(%.1f %% ohne plausiblen Preis)"
            % (
                int(preise.get("gueltig") or 0),
                int(preise.get("ohne_preis") or 0),
                int(preise.get("unplausibel") or 0),
                float(preise.get("anteil_ohne") or 0.0),
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
