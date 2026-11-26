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
    """Ergebnis des synthetischen Alarmtests, getrennt von echten Alarmen."""
    ok = sum(1 for z in zeilen if z.get("ok") is True)
    letzte = [
        {"iso": str(z.get("iso") or ""), "ok": z.get("ok") is True,
         "event": z.get("event")}
        for z in zeilen[-5:]
    ]
    return {
        "gesamt": len(zeilen),
        "ok": ok,
        "fehlgeschlagen": len(zeilen) - ok,
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
    abdeckung = _abdeckung_stunden(checks)
    shop_takt = _takt_je_shop(checks_nach_shop, runde_zeilen, budget_zeilen)
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
        "alarm_latenz": alarm_latenz,
        "fehlalarme": fehlalarme,
        "stille_shops": stille_shops,
        "abdeckung_stunden": abdeckung,
        "shop_takt": shop_takt,
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


def _check_stunde(daten):
    iso = daten.get("iso")
    if iso:
        try:
            return datetime.fromisoformat(str(iso)).hour
        except (TypeError, ValueError):
            pass
    ts = _check_ts(daten)
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts).hour
    except (OSError, OverflowError, ValueError):
        return None


def _check_tag(daten):
    iso = daten.get("iso")
    if iso:
        try:
            return datetime.fromisoformat(str(iso)).date().isoformat()
        except (TypeError, ValueError):
            pass
    ts = _check_ts(daten)
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts).date().isoformat()
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


def _abdeckung_stunden(checks):
    """Stunden-Buckets plus Abdeckung je Tag und beobachtete Zeit.

    Die 24 Stunden zaehlen ueber alle Tage. Ohne die Tageswerte liest sich
    "6 von 24" wie ein Polling-Fehler, obwohl in Wahrheit nur 5 Stunden lang
    ein Prozess lief. ``beobachtet_s`` summiert deshalb nur Abstaende im Takt
    und ``sitzungen`` zaehlt die zusammenhaengenden Laeufe.
    """
    stunden = [0] * 24
    tage = {}
    zeitpunkte = []
    for daten in checks:
        stunde = _check_stunde(daten)
        if stunde is None or not 0 <= stunde < 24:
            continue
        stunden[stunde] += 1
        tag = _check_tag(daten) or "?"
        eintrag = tage.setdefault(
            tag, {"datum": tag, "stunden": [0] * 24, "checks": 0, "zeiten": []}
        )
        eintrag["stunden"][stunde] += 1
        eintrag["checks"] += 1
        ts = _check_ts(daten)
        if ts is not None:
            eintrag["zeiten"].append(ts)
            zeitpunkte.append(ts)

    pro_tag = []
    for datum in sorted(tage):
        eintrag = tage[datum]
        sekunden = _beobachtete_sekunden(eintrag["zeiten"])
        tag_luecken = [h for h, n in enumerate(eintrag["stunden"]) if n == 0]
        pro_tag.append({
            "datum": datum,
            "abgedeckt": 24 - len(tag_luecken),
            "luecken": tag_luecken,
            "checks": eintrag["checks"],
            "beobachtet_s": int(round(sekunden)),
            "beobachtet_h": round(sekunden / 3600.0, 2),
        })

    beobachtet = _beobachtete_sekunden(zeitpunkte)
    zeiten = sorted(zeitpunkte)
    sitzungen = 1 if zeiten else 0
    for a, b in zip(zeiten, zeiten[1:]):
        if b - a > ABDECKUNG_SITZUNG_S:
            sitzungen += 1
    luecken = [h for h, n in enumerate(stunden) if n == 0]
    return {
        "stunden": stunden,
        "abgedeckt": 24 - len(luecken),
        "luecken": luecken,
        "checks": sum(stunden),
        "beobachtet_s": int(round(beobachtet)),
        "beobachtet_h": round(beobachtet / 3600.0, 2),
        "sitzungen": sitzungen,
        "schwelle_s": int(ABDECKUNG_SITZUNG_S),
        "tage": pro_tag,
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
    luecken = abdeckung.get("luecken") or []
    luecken_text = ", ".join("%02d" % h for h in luecken) or "keine"
    tage_text = " | ".join(
        "%s %d/24 Std, %.2f h, %d Checks"
        % (
            str(t.get("datum") or "?"),
            int(t.get("abgedeckt") or 0),
            float(t.get("beobachtet_h") or 0.0),
            int(t.get("checks") or 0),
        )
        for t in (abdeckung.get("tage") or [])
    ) or "keine"
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
    canary_text = "Alarm-Canary: %d/%d ok" % (
        int(canary_daten.get("ok") or 0),
        int(canary_daten.get("gesamt") or 0),
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
            latenz,
            fehlalarm_text,
            "Abdeckung: %d von 24 Stunden mit Checks; Luecken: %s"
            % (int(abdeckung.get("abgedeckt") or 0), luecken_text),
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
