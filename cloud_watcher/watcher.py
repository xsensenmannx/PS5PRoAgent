"""Cloud-Waechter fuer PS Direct DE/AT.

Ein outbound-only Prozess fuer Fly.io oder einen Hetzner-Docker-Host. Er nutzt
die vorhandene Scan- und Alarmlogik aus ``scan_core`` und schreibt seinen
Zustand als JSON in ``WATCH_DATA_DIR`` (im Container ``/data``).

Sicherheitsregeln:

* Standard ist Schattenbetrieb: Es wird geprueft und protokolliert, aber nichts
  gesendet. ``WATCH_SHADOW=0`` schaltet erst nach Ablauf der beim ersten Start
  gesetzten Schattenfrist (Standard 48 h) scharf.
* Der erste gueltige Abruf eines Shops ist nur Baseline und loest keinen Alarm
  aus. Erst ein spaeterer Wechsel auf verfuegbar meldet.
* Webhook-URLs werden nie geloggt. ``redact_url`` zeigt hoechstens Schema und
  Host.
* Kein Captcha, keine Proxy-Rotation, kein Warenkorb, kein Retry gegen eine
  Sperre. Bei 403/429 wird der Shop 15 Minuten ausgesetzt.
"""

from __future__ import annotations

import glob
import json
import os
import signal
import sys
import threading
import time
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scan_core as core  # noqa: E402  (Pfad steht erst zur Laufzeit fest)

SCHEMA = 3
STATE_FILE = "cloud_watch_state.json"
STATUS_FILE = "watcher_status.json"
# NDJSON-Tageslogs: hoechstens drei Teile je Tag, 14 Tage Aufbewahrung.
LOG_PREFIX = "watcher-log-"
LOG_SUFFIX = ".ndjson"
LOG_MAX_BYTES = 4 * 1024 * 1024
LOG_MAX_PARTS = 3
LOG_KEEP_DAYS = 14
# Die Statusdatei wird haeufiger geschrieben als der Healthcheck prueft.
STATUS_TAKT = 15
# Der Lebenszeichen-Ping laeuft unabhaengig von faelligen Shops.
HEARTBEAT_TAKT = 60
CHALLENGE_TAKT = 900
# Nach drei Challenges in Folge bleibt der Shop eine Stunde aus.
CHALLENGE_LANG = 3600
CHALLENGE_LANG_NACH = 3
FEHLER_TAKT = 720
# Ab drei Parser-/Netzfehlern in Folge steht der Shop im Tagesbericht.
CANARY_FEHLER_SERIE = 3
# PS Direct wird bei knappem Minutenbudget zuerst bedient.
PRIORITY_SHOPS = ("PS Direct DE", "PS Direct AT")
# Die Tageszeile braucht nur die letzten Pruefungen fuer p50/p95.
TAG_MS_MAX = 500
# Outbox: Ereignisse werden vor dem ersten Versand im Zustand abgelegt.
# Der Backoff beginnt kurz; Treffer verfallen vorher (OUTBOX_MAX_AGE_HIT).
OUTBOX_MAX_ACTIVE = 20
OUTBOX_MAX_ITEMS = 50
OUTBOX_MAX_ATTEMPTS = 6
OUTBOX_BACKOFF_S = (30, 120, 600, 1800, 7200)
OUTBOX_SENT_KEEP_S = 7 * 86400
OUTBOX_FAILED_KEEP_S = 30 * 86400
OUTBOX_SENDING_STALE_S = 300
OUTBOX_DRAIN_MAX = 5
# Ein fehlgeschlagener Systemalarm wird nicht sofort aufgegeben.
OUTBOX_SYSTEM_ALARM_MAX = 3
OUTBOX_SYSTEM_ALARM_BACKOFF_S = (120, 600)
# Ein Treffer ist nach zehn Minuten nichts mehr wert: lieber verfallen lassen
# als eine Stunde spaeter "verfuegbar" zu melden. Gilt nur fuer Treffer-Alarme,
# nicht fuer den Testalarm.
OUTBOX_MAX_AGE_HIT = 600
# Tagesbericht: hoechstens drei Versuche im Abstand von fuenf Minuten.
TAG_BERICHT_MAX = 3
TAG_BERICHT_BACKOFF_S = 300
STOP = threading.Event()
_LOG_LOCK = threading.Lock()
_LOG_ZIEL = ""
_LOG_TZ = None
_LOG_TAG = ""
_LOG_TEIL = 0
_LOG_HANDLE = None
_LOG_GROESSE = 0
_LOG_VERWORFEN = 0


@dataclass(frozen=True)
class Konfig:
    """Vollstaendige Laufzeitkonfiguration, ausschliesslich aus der Umgebung."""

    shops: tuple
    data_dir: str
    tz_name: str
    shadow: bool
    shadow_hours: float
    takt: int
    takt_neben: int
    max_preis: float
    webhook_url: str
    webhook_preset: str
    ops_url: str
    ops_preset: str
    heartbeat_url: str
    max_req_min: int
    preis_toleranz: float

    def zeitzone(self):
        try:
            return ZoneInfo(self.tz_name)
        except Exception:
            # Ohne Zeitzonendaten laeuft der Container in seiner lokalen Zeit.
            return datetime.now().astimezone().tzinfo

    @classmethod
    def aus_env(cls, env=None):
        env = os.environ if env is None else env

        roh = str(
            env.get(
                "WATCH_SHOPS",
                "PS Direct DE,PS Direct AT,Alternate DE",
            )
            or ""
        )
        shops = tuple(x.strip() for x in roh.split(",") if x.strip())
        if not shops:
            raise ValueError("WATCH_SHOPS ist leer")
        bekannt = {h["name"] for h in core.HAENDLER}
        unbekannt = [n for n in shops if n not in bekannt]
        if unbekannt:
            raise ValueError("unbekannte Shops: " + ", ".join(unbekannt))

        url = str(env.get("WATCH_WEBHOOK_URL", "") or "").strip()
        preset = str(env.get("WATCH_WEBHOOK_PRESET", "") or "").strip()
        if preset not in core.WEBHOOK_PRESETS:
            preset = core.webhook_preset(url) if url else "generisch"

        # Optionaler, unabhaengiger Ops-Kanal nur fuer den Systemalarm.
        ops_url = str(env.get("WATCH_OPS_WEBHOOK_URL", "") or "").strip()
        ops_preset = core.webhook_preset(ops_url) if ops_url else "generisch"

        return cls(
            shops=shops,
            data_dir=str(env.get("WATCH_DATA_DIR", "/data") or "/data"),
            tz_name=str(env.get("WATCH_TZ", "Europe/Berlin") or "Europe/Berlin"),
            shadow=_wahr(env.get("WATCH_SHADOW"), True),
            shadow_hours=_zahl(env, "WATCH_SHADOW_HOURS", 48.0, 0.0, 720.0),
            # PS Direct laeuft im 15-s-Takt (2 Shops = 8 Anfragen/Minute).
            # Der Zusatztakt ist 30 s (2 Anfragen/Minute je Shop); mit einem
            # Zusatzshop sind das 10 von 12. Ein zweiter Zusatzshop waere
            # genau das Limit, ein dritter zu viel.
            takt=_ganz(env, "WATCH_TAKT", 15, 15, 3600),
            takt_neben=_ganz(env, "WATCH_TAKT_NEBEN", 30, 30, 3600),
            max_preis=_zahl(env, "WATCH_MAX_PREIS", 900.0, 100.0, 1500.0),
            webhook_url=url,
            webhook_preset=preset,
            ops_url=ops_url,
            ops_preset=ops_preset,
            heartbeat_url=str(env.get("WATCH_HEARTBEAT_URL", "") or "").strip(),
            max_req_min=_ganz(env, "WATCH_MAX_REQ_MIN", 12, 1, 60),
            preis_toleranz=_zahl(env, "WATCH_PREIS_TOLERANZ", 1.0, 0.0, 50.0),
        )


def _wahr(wert, standard=True):
    if wert is None or str(wert).strip() == "":
        return bool(standard)
    return str(wert).strip().lower() not in ("0", "false", "nein", "no", "off", "aus")


def _zahl(env, name, standard, minimum, maximum):
    try:
        wert = float(str(env.get(name, standard)).replace(",", "."))
    except (TypeError, ValueError):
        wert = float(standard)
    return max(float(minimum), min(float(maximum), wert))


def _ganz(env, name, standard, minimum, maximum):
    return int(round(_zahl(env, name, standard, minimum, maximum)))


def neuer_zustand(jetzt, shadow_hours):
    jetzt = float(jetzt)
    return {
        "schema": SCHEMA,
        "angelegt": jetzt,
        "schatten_bis": jetzt + max(0.0, float(shadow_hours)) * 3600.0,
        "shops": {},
        "runden": 0,
        "alarme_schatten": 0,
        "alarme_gesendet": 0,
        "letzte_runde": 0.0,
        "outbox": _outbox_leer(),
        "tag": _tag_leer(),
    }


def zustand_laden(pfad, jetzt, shadow_hours):
    """Zustand lesen; eine kaputte Datei startet sicher neu.

    Eine vorhandene Schattenfrist wird nie verkuerzt. Wer schneller scharf
    schalten will, muss die Datei bewusst loeschen - das ist Absicht.
    """
    daten = None
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = None
    if not isinstance(daten, dict):
        daten = neuer_zustand(jetzt, shadow_hours)

    try:
        schema = int(daten.get("schema") or 1)
    except (TypeError, ValueError):
        schema = 1
    if schema < SCHEMA:
        daten["schema"] = SCHEMA
    daten.setdefault("angelegt", float(jetzt))
    try:
        bis = float(daten.get("schatten_bis") or 0)
    except (TypeError, ValueError):
        bis = 0.0
    if bis <= 0:
        daten["schatten_bis"] = float(jetzt) + max(0.0, float(shadow_hours)) * 3600.0
    if not isinstance(daten.get("shops"), dict):
        daten["shops"] = {}
    # Alte Zustaende kennen noch keinen Alarmpreis; der letzte bekannte Preis
    # ist der beste Startpunkt, damit die Toleranz nicht bei null beginnt.
    for eintrag in daten["shops"].values():
        if (isinstance(eintrag, dict) and eintrag.get("alarm_preis") is None
                and eintrag.get("preis") is not None):
            eintrag["alarm_preis"] = eintrag.get("preis")
    for key in ("runden", "alarme_schatten", "alarme_gesendet"):
        try:
            daten[key] = int(daten.get(key) or 0)
        except (TypeError, ValueError):
            daten[key] = 0
    try:
        daten["letzte_runde"] = float(daten.get("letzte_runde") or 0)
    except (TypeError, ValueError):
        daten["letzte_runde"] = 0.0
    outbox_sicherstellen(daten)
    tag_sicherstellen(daten)
    if daten.get("tag_bericht") is not None and not isinstance(
            daten.get("tag_bericht"), dict):
        daten.pop("tag_bericht", None)
    return daten


def zustand_speichern(pfad, daten):
    """Atomar schreiben: ein Absturz hinterlaesst nie halbes JSON."""
    ordner = os.path.dirname(os.path.abspath(pfad)) or "."
    os.makedirs(ordner, exist_ok=True)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, pfad)


def _outbox_leer():
    return {"items": [], "gesamt": 0, "letzte_id": ""}


def _outbox_id(jetzt):
    try:
        stempel = datetime.fromtimestamp(float(jetzt)).strftime("%Y%m%dT%H%M%S")
    except Exception:
        stempel = "00000000T000000"
    return "ob_%s_%s" % (stempel, uuid.uuid4().hex[:8])


def _outbox_int(wert, standard=0):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return int(standard)


def _outbox_float(wert, standard=0.0):
    try:
        return float(wert)
    except (TypeError, ValueError):
        return float(standard)


def outbox_sicherstellen(daten):
    """Outbox-Feld laden und einzelne defekte Eintraege tolerieren."""
    if not isinstance(daten, dict):
        return _outbox_leer()
    box = daten.get("outbox")
    if not isinstance(box, dict):
        box = _outbox_leer()
        daten["outbox"] = box
    roh = box.get("items")
    items = []
    if isinstance(roh, list):
        for eintrag in roh:
            if not isinstance(eintrag, dict):
                continue
            item = dict(eintrag)
            item["id"] = str(item.get("id") or _outbox_id(item.get("created") or 0))
            item["status"] = str(item.get("status") or "pending")
            if item["status"] not in ("pending", "sending", "sent", "failed",
                                      "expired"):
                item["status"] = "pending"
            item["created"] = _outbox_float(item.get("created"), 0.0)
            item["next_ts"] = _outbox_float(item.get("next_ts"), item["created"])
            item["attempts"] = max(0, _outbox_int(item.get("attempts"), 0))
            item["shop"] = str(item.get("shop") or "?")
            item["event"] = str(item.get("event") or "new")
            item["restock"] = bool(item.get("restock")) or item["event"] == "restock"
            item.setdefault("last_error", None)
            item.setdefault("last_attempt_ts", None)
            item.setdefault("sent_ts", None)
            item.setdefault("failed_ts", None)
            item.setdefault("failed_grund", None)
            item.setdefault("system_alarm_ts", None)
            item.setdefault("system_alarm_ok", None)
            item.setdefault("system_alarm_kanal", None)
            item.setdefault("system_alarm_attempts", 0)
            item.setdefault("system_alarm_next_ts", None)
            item.setdefault("system_alarm_info", None)
            items.append(item)
    box["items"] = items
    box["gesamt"] = max(_outbox_int(box.get("gesamt"), 0), len(items))
    box["letzte_id"] = str(box.get("letzte_id") or (items[-1]["id"] if items else ""))
    return box


def outbox_prune(box, jetzt):
    """Alte Zustellungen begrenzen; pending/sending nie still verwerfen."""
    if not isinstance(box, dict):
        return
    jetzt = _outbox_float(jetzt, time.time())
    behalten = []
    for item in box.get("items") or []:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status == "sent":
            try:
                if jetzt - float(item.get("sent_ts") or item.get("created") or 0) > OUTBOX_SENT_KEEP_S:
                    continue
            except (TypeError, ValueError):
                pass
        elif status in ("failed", "expired"):
            try:
                if jetzt - float(item.get("failed_ts") or item.get("created") or 0) > OUTBOX_FAILED_KEEP_S:
                    continue
            except (TypeError, ValueError):
                pass
        behalten.append(item)

    # Gesamtobergrenze: zuerst alte Zustellungen, dann alte Fehler entfernen.
    while len(behalten) > OUTBOX_MAX_ITEMS:
        entfernt = False
        for status in ("sent", "failed"):
            for index, item in enumerate(behalten):
                if item.get("status") == status:
                    behalten.pop(index)
                    entfernt = True
                    break
            if entfernt:
                break
        if not entfernt:
            break
    box["items"] = behalten


def outbox_enqueue(r, event, zustand, jetzt, titel, text):
    """Neuen Alarm atomar vormerken. None = Outbox ist voll."""
    if not isinstance(zustand, dict) or not isinstance(r, dict):
        return None
    box = outbox_sicherstellen(zustand)
    jetzt = _outbox_float(jetzt, time.time())
    outbox_prune(box, jetzt)
    aktiv = sum(
        1 for item in box["items"] if item.get("status") in ("pending", "sending")
    )
    if aktiv >= OUTBOX_MAX_ACTIVE or len(box["items"]) >= OUTBOX_MAX_ITEMS:
        return None

    item = {
        "id": _outbox_id(jetzt),
        "created": jetzt,
        "next_ts": jetzt,
        "attempts": 0,
        "status": "pending",
        "shop": str(r.get("haendler") or "?"),
        "event": str(event or "new"),
        "price": r.get("preis"),
        "condition": r.get("condition"),
        "sofort": r.get("sofort"),
        "title": str(titel or "")[:240],
        "text": str(text or "")[:1000],
        "url": r.get("url"),
        "restock": bool(event == "restock"),
        "last_error": None,
        "last_attempt_ts": None,
        "sent_ts": None,
        "failed_ts": None,
        "failed_grund": None,
        "system_alarm_ts": None,
        "system_alarm_ok": None,
        "system_alarm_kanal": None,
        "system_alarm_attempts": 0,
        "system_alarm_next_ts": None,
        "system_alarm_info": None,
    }
    box["items"].append(item)
    box["gesamt"] = _outbox_int(box.get("gesamt"), 0) + 1
    box["letzte_id"] = item["id"]
    return item


def _outbox_state_save(pfad, zustand, aktion, item=None):
    """Persistieren ist Voraussetzung fuer den ersten Sendeversuch."""
    if not pfad:
        return False
    try:
        zustand_speichern(pfad, zustand)
        return True
    except Exception as e:
        log(
            {
                "typ": "outbox_fehler",
                "ts": round(time.time(), 3),
                "aktion": aktion,
                "id": (item or {}).get("id"),
                "info": type(e).__name__,
            }
        )
        return False


def _outbox_retrybar(info):
    """4xx ausser 408/425/429 ist endgueltig; 5xx/Timeout ist retrybar."""
    text = str(info or "")
    if text.startswith("HTTP "):
        try:
            code = int(text.split()[1])
        except (IndexError, ValueError):
            return True
        return not (400 <= code < 500 and code not in (408, 425, 429))
    return text not in ("nur HTTPS", "URL ungueltig", "kein Kanal")


def _outbox_safe_info(info, settings=None):
    """Fehlertext fuer Log/Zustand; keine Webhook-URL darf auftauchen."""
    text = str(info or "")
    settings = settings if isinstance(settings, dict) else {}
    for key in ("webhook_url", "ops_url"):
        url = str(settings.get(key) or "").strip()
        if url:
            text = text.replace(url, core.redact_url(url))
    return text[:120]


def _outbox_log(item, aktion, jetzt, ok=None, info="", versuch=None):
    daten = {
        "typ": "outbox",
        "ts": round(float(jetzt), 3),
        "id": item.get("id"),
        "shop": item.get("shop"),
        "event": item.get("event"),
        "aktion": aktion,
        "versuch": item.get("attempts") if versuch is None else versuch,
        "status": item.get("status"),
        "ok": ok,
        "info": str(info or "")[:120],
    }
    if item.get("next_ts"):
        daten["next_ts"] = round(float(item["next_ts"]), 3)
    log(daten)


def _https_ziel(url):
    """Nur eine vollstaendige HTTPS-URL ist ein brauchbares Ziel."""
    try:
        ziel = urlparse(str(url or "").strip())
    except Exception:
        return False
    return ziel.scheme == "https" and bool(ziel.hostname)


def _ops_ziel(settings):
    """Ziel fuer den Systemalarm: gueltiger Ops-Kanal, sonst Produkt-Webhook."""
    settings = settings if isinstance(settings, dict) else {}
    url = str(settings.get("ops_url") or "").strip()
    if not _https_ziel(url):
        return settings, "produkt"
    preset = str(settings.get("ops_preset") or "")
    if preset not in core.WEBHOOK_PRESETS:
        preset = core.webhook_preset(url)
    return {"webhook_url": url, "webhook_preset": preset}, "ops"


def outbox_systemalarm(item, zustand, settings, jetzt, pfad):
    """Einmalige Warnung, wenn ein Produktalarm endgueltig scheitert.

    Ist ``WATCH_OPS_WEBHOOK_URL`` gesetzt, geht nur der Systemalarm dorthin.
    Ein ausgefallener Produkt-Webhook blockiert die Warnung dann nicht; ohne
    Ops-Kanal bleibt der bisherige Weg ueber den Produkt-Webhook.
    """
    if not isinstance(item, dict) or item.get("system_alarm_ok"):
        return False
    jetzt = _outbox_float(jetzt, time.time())
    versuch = _outbox_int(item.get("system_alarm_attempts"), 0) + 1
    settings = settings if isinstance(settings, dict) else {}
    titel = "Waechter: Alarm nicht zugestellt"
    try:
        preis = core.format_preis(item.get("price"))
    except Exception:
        preis = str(item.get("price"))
    text = "%s: %s (%s), %d Versuche, %s" % (
        item.get("shop") or "?",
        item.get("event") or "?",
        preis,
        _outbox_int(item.get("attempts"), 0),
        _outbox_safe_info(
            item.get("last_error") or item.get("failed_grund") or "unbekannt",
            settings,
        )[:100],
    )
    ziel, kanal = _ops_ziel(settings)
    if not str(ziel.get("webhook_url") or "").strip():
        ok, info = False, "kein Kanal"
    else:
        try:
            erg = core.sende_webhook_alarm(
                {
                    "haendler": item.get("shop"),
                    "preis": item.get("price"),
                    "url": item.get("url"),
                    "_restock": bool(item.get("restock")),
                },
                ziel,
                titel,
                text,
                dedupe=False,
            )
            if erg is None:
                ok, info = False, "kein Kanal"
            else:
                ok, info = bool(erg[0]), str(erg[1] or "")
        except Exception as e:
            ok, info = False, type(e).__name__
    item["system_alarm_ts"] = jetzt
    item["system_alarm_ok"] = bool(ok)
    item["system_alarm_kanal"] = kanal
    item["system_alarm_attempts"] = versuch
    if ok or versuch >= OUTBOX_SYSTEM_ALARM_MAX:
        item["system_alarm_next_ts"] = None
    else:
        index = min(versuch - 1, len(OUTBOX_SYSTEM_ALARM_BACKOFF_S) - 1)
        item["system_alarm_next_ts"] = (
            jetzt + OUTBOX_SYSTEM_ALARM_BACKOFF_S[index]
        )
    info = _outbox_safe_info(info, settings)
    item["system_alarm_info"] = info
    _outbox_state_save(pfad, zustand, "systemalarm", item)
    log(
        {
            "typ": "systemalarm",
            "ts": round(jetzt, 3),
            "id": item.get("id"),
            "shop": item.get("shop"),
            "event": item.get("event"),
            "kanal": kanal,
            "versuch": versuch,
            "next_ts": item.get("system_alarm_next_ts"),
            "ok": bool(ok),
            "info": info,
        }
    )
    return bool(ok)


def systemalarm_faellig(item, jetzt):
    """True, wenn fuer den Eintrag ein Systemalarm erneut faellig ist."""
    if not isinstance(item, dict) or item.get("system_alarm_ok"):
        return False
    if not item.get("system_alarm_ts"):
        return True
    next_ts = item.get("system_alarm_next_ts")
    if next_ts is None:
        return False
    return _outbox_float(next_ts, 0.0) <= _outbox_float(jetzt, time.time())


def _outbox_zu_alt(item, jetzt):
    """True, wenn ein Treffer-Alarm die Frischefrist ueberschritten hat."""
    if not isinstance(item, dict):
        return False
    if item.get("test") or item.get("system"):
        return False
    if str(item.get("event") or "") not in ("new", "restock"):
        return False
    alter = _outbox_float(jetzt, 0.0) - _outbox_float(item.get("created"), 0.0)
    return alter > OUTBOX_MAX_AGE_HIT


def _outbox_verfallen_lassen(item, jetzt):
    """Einen zu alten Treffer als verfallen markieren, nicht mehr senden."""
    item["status"] = "expired"
    item["failed_ts"] = jetzt
    item["failed_grund"] = "zu_alt"
    item["last_error"] = "Treffer aelter als %d s" % OUTBOX_MAX_AGE_HIT


def outbox_verfallen(box, jetzt):
    """Alle faelligen Treffer-Alarme verfallen lassen; gibt die Liste zurueck."""
    if not isinstance(box, dict):
        return []
    jetzt = _outbox_float(jetzt, time.time())
    verfallen = []
    for item in box.get("items") or []:
        if not isinstance(item, dict) or item.get("status") != "pending":
            continue
        if not _outbox_zu_alt(item, jetzt):
            continue
        _outbox_verfallen_lassen(item, jetzt)
        verfallen.append(item)
    return verfallen


def _outbox_send_one(item, zustand, settings, jetzt, pfad):
    """Erst ``sending`` persistieren, dann senden, dann Ergebnis speichern."""
    if _outbox_zu_alt(item, jetzt):
        _outbox_verfallen_lassen(item, jetzt)
        _outbox_state_save(pfad, zustand, "verfallen", item)
        _outbox_log(item, "verfallen", jetzt, False, item.get("last_error") or "")
        return False
    item["attempts"] = _outbox_int(item.get("attempts"), 0) + 1
    item["status"] = "sending"
    item["last_attempt_ts"] = jetzt
    item["next_ts"] = jetzt
    if not _outbox_state_save(pfad, zustand, "sending", item):
        item["status"] = "pending"
        item["attempts"] = max(0, item["attempts"] - 1)
        return False

    r = {
        "haendler": item.get("shop"),
        "preis": item.get("price"),
        "url": item.get("url"),
        "_restock": bool(item.get("restock")),
    }
    try:
        erg = core.sende_webhook_alarm(
            r,
            settings,
            item.get("title") or "",
            item.get("text") or "",
            dedupe=False,
        )
    except Exception as e:
        erg = (False, type(e).__name__)
    if erg is None:
        ok, info = False, "kein Kanal"
    else:
        ok, info = bool(erg[0]), str(erg[1] or "")

    if ok:
        item["status"] = "sent"
        item["sent_ts"] = jetzt
        item["last_error"] = None
        item["failed_grund"] = None
        zustand["alarme_gesendet"] = _outbox_int(zustand.get("alarme_gesendet"), 0) + 1
        _outbox_state_save(pfad, zustand, "sent", item)
        _outbox_log(item, "gesendet", jetzt, True, info)
        return True

    info = _outbox_safe_info(info, settings)
    item["last_error"] = info
    retrybar = _outbox_retrybar(info)
    if not retrybar or item["attempts"] >= OUTBOX_MAX_ATTEMPTS:
        item["status"] = "failed"
        item["failed_ts"] = jetzt
        item["failed_grund"] = (
            "max_attempts" if retrybar else "config" if info == "kein Kanal"
            else "http_4xx"
        )
        _outbox_state_save(pfad, zustand, "failed", item)
        _outbox_log(item, "fehlgeschlagen", jetzt, False, info)
        outbox_systemalarm(item, zustand, settings, jetzt, pfad)
        return False

    item["status"] = "pending"
    index = min(max(0, item["attempts"] - 1), len(OUTBOX_BACKOFF_S) - 1)
    item["next_ts"] = jetzt + OUTBOX_BACKOFF_S[index]
    _outbox_state_save(pfad, zustand, "retry", item)
    _outbox_log(item, "retry", jetzt, False, info)
    return False


def outbox_drain(zustand, konfig, settings, tz, jetzt=None, pfad=None, schatten=False,
                 max_items=OUTBOX_DRAIN_MAX):
    """Faellige Outbox-Eintraege persistent und begrenzt zustellen."""
    if schatten or not isinstance(zustand, dict):
        return 0
    box = outbox_sicherstellen(zustand)
    jetzt = _outbox_float(jetzt, time.time())
    outbox_prune(box, jetzt)
    # Treffer, die zu alt sind, verfallen statt spaeter zuzustellen.
    verfallen = outbox_verfallen(box, jetzt)
    for item in verfallen:
        _outbox_log(item, "verfallen", jetzt, False,
                    item.get("last_error") or "")
    geaendert = bool(verfallen)

    # Ein Absturz zwischen ``sending`` und Ergebnis wird nach einer Karenz
    # erneut versucht; Duplikate sind bei at-least-once moeglich.
    for item in box["items"]:
        if item.get("status") == "sending":
            letzter = _outbox_float(item.get("last_attempt_ts"), 0.0)
            if jetzt - letzter > OUTBOX_SENDING_STALE_S:
                item["status"] = "pending"
                item["next_ts"] = jetzt
                geaendert = True

    # Fehlgeschlagene Eintraege ohne Systemalarm (z. B. nach Neustart) holen
    # ihre einmalige Warnung nach.
    for item in list(box["items"]):
        if item.get("status") == "failed" and systemalarm_faellig(item, jetzt):
            outbox_systemalarm(item, zustand, settings, jetzt, pfad)
            geaendert = True

    faellig = [
        item for item in box["items"]
        if item.get("status") == "pending"
        and _outbox_float(item.get("next_ts"), 0.0) <= jetzt
    ]
    faellig.sort(key=lambda item: (_outbox_float(item.get("next_ts"), 0.0),
                                  _outbox_float(item.get("created"), 0.0)))
    anzahl = 0
    for item in faellig[:max(0, int(max_items))]:
        _outbox_send_one(item, zustand, settings, jetzt, pfad)
        anzahl += 1

    outbox_prune(box, jetzt)
    if geaendert and not anzahl:
        _outbox_state_save(pfad, zustand, "recovery")
    return anzahl


def testalarm_senden(konfig, settings, pfad, jetzt=None):
    """Klar markierte Testnachricht durch den echten Outbox-Weg.

    Der Eintrag wird vorgemerkt, persistiert und ueber denselben Pfad wie ein
    Treffer gesendet. Er dedupliziert nicht, verfaellt nicht und laesst bei
    einem Fehlschlag keinen Retry in der Outbox stehen, damit der Test keine
    spaeteren Alarme vorfaelscht. Rueckgabe (ok, info).
    """
    jetzt = _outbox_float(jetzt, time.time())
    if not str(konfig.webhook_url or "").strip():
        return False, "kein Kanal"
    zustand = zustand_laden(pfad, jetzt, konfig.shadow_hours)
    item = outbox_enqueue(
        {"haendler": "Testalarm", "preis": None, "url": ""},
        "test",
        zustand,
        jetzt,
        "Waechter Testalarm (kein Treffer)",
        "Testnachricht: Dieser Alarm prueft den Alarmweg, "
        "es ist keine PS5 Pro Verfuegbarkeit.",
    )
    if item is None:
        return False, "Outbox voll"
    item["test"] = True
    if not _outbox_state_save(pfad, zustand, "testalarm", item):
        return False, "Zustand nicht speicherbar"
    ok = _outbox_send_one(item, zustand, settings, jetzt, pfad)
    if not ok:
        box = outbox_sicherstellen(zustand)
        box["items"] = [
            x for x in box["items"] if x.get("id") != item.get("id")
        ]
        # Kein Retry fuer einen Test: sonst taucht er spaeter als Alarm auf.
        _outbox_log(item, "verworfen", jetzt, False, "Testalarm, kein Retry")
        _outbox_state_save(pfad, zustand, "testalarm_aufraeumen")
        return False, str(item.get("last_error") or "nicht zugestellt")
    return True, "zugestellt"


def schatten_aktiv(zustand, jetzt, erzwingen):
    """True, solange nichts gesendet werden darf."""
    if erzwingen:
        return True
    try:
        bis = float((zustand or {}).get("schatten_bis") or 0)
    except (TypeError, ValueError):
        bis = 0.0
    return float(jetzt) < bis


def ist_sofort_treffer(r):
    """Nur ein bestaetigter, sofort kaufbarer, nicht gebrauchter Treffer.

    Ein unbestaetigter Treffer, eine Vorbestellung oder Gebrauchtware darf
    nicht als "schon verfuegbar" im Zustand landen: sonst wuerde der spaetere
    echte Restock als gewoehnlicher Preisvergleich verpuffen. Eine
    Vorbestellung setzt in ``scan_core`` bereits ``sofort=False``.
    """
    return bool(
        isinstance(r, dict)
        and r.get("klass") == "hit"
        and r.get("preis") is not None
        and r.get("verify") == "bestaetigt"
        and r.get("sofort") is not False
        and not core.ist_gebraucht(r.get("condition"))
    )


def alarm_preis(eintrag):
    """Referenzpreis der Toleranz: Preis beim letzten Alarm, sonst letzter Stand."""
    if not isinstance(eintrag, dict):
        return None
    wert = eintrag.get("alarm_preis")
    if wert is None:
        wert = eintrag.get("preis")
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def preis_signifikant(neu, letzter, toleranz=0.0):
    """True, wenn der neue Preis deutlich unter dem letzten liegt.

    ``toleranz`` daempft Cent-Rauschen und kurze Preisausschlaege. Ein
    Restock bleibt davon unberuehrt; die Toleranz gilt nur fuer ``new``.
    """
    try:
        neu = float(neu)
    except (TypeError, ValueError):
        return False
    if letzter is None:
        return True
    try:
        letzter = float(letzter)
        grenze = max(0.01, float(toleranz or 0.0))
    except (TypeError, ValueError):
        return False
    return neu < letzter - grenze


def ereignis(eintrag, r, toleranz=0.0):
    """Alarm-Ereignis oder None; nur bestaetigte, sofort kaufbare Treffer.

    Unbestaetigte Treffer, Vorbestellungen und Gebrauchtware erzeugen kein
    Ereignis. Sie duerfen den spaeteren echten Restock nicht verdecken und
    auch nicht als Schattenalarm im Log auftauchen. Ein neuer Preis wird erst
    ab der konfigurierten Preistoleranz gemeldet.
    """
    if not ist_sofort_treffer(r):
        return None
    if not isinstance(eintrag, dict) or not eintrag.get("initialisiert"):
        return None
    if eintrag.get("verfuegbar") is False:
        return "restock"
    if preis_signifikant(r.get("preis"), alarm_preis(eintrag), toleranz):
        return "new"
    return None


def alarm_entscheidung(eintrag, r, toleranz=0.0):
    """Ereignis bestimmen und bei Alarm den Referenzpreis nachziehen.

    Nur ein tatsaechlich gemeldeter Alarm verschiebt die Referenz. Ein Check
    unterhalb der Toleranz laesst sie stehen, damit sich kleine Senkungen
    summieren und nicht dauerhaft stumm bleiben.
    """
    event = ereignis(eintrag, r, toleranz)
    if event and isinstance(eintrag, dict) and r.get("preis") is not None:
        eintrag["alarm_preis"] = r["preis"]
    return event


def aktualisiere(eintrag, r, jetzt, tz=None):
    """Shop-Zustand fortschreiben. Fehler ueberschreiben keinen Preis."""
    if not isinstance(eintrag, dict):
        return
    status = str(r.get("klass") or "unknown")
    eintrag["status"] = status
    eintrag["ts"] = float(jetzt)
    try:
        eintrag["iso"] = datetime.fromtimestamp(float(jetzt), tz).isoformat(
            timespec="seconds"
        )
    except Exception:
        pass
    eintrag["fehler"] = r.get("fehler")
    try:
        eintrag["bytes"] = int(r.get("bytes") or 0)
    except (TypeError, ValueError):
        eintrag["bytes"] = 0
    try:
        eintrag["ms"] = int(round(float(r.get("dauer") or 0) * 1000))
    except (TypeError, ValueError):
        eintrag["ms"] = 0
    if r.get("fresh") is not None:
        eintrag["frisch"] = bool(r.get("fresh"))
    if r.get("verify"):
        eintrag["verify"] = str(r.get("verify"))
    if r.get("url"):
        eintrag["url"] = str(r.get("url"))

    if status == "challenge":
        eintrag["fail_streak"] = int(eintrag.get("fail_streak") or 0) + 1
        eintrag["challenge_serie"] = int(eintrag.get("challenge_serie") or 0) + 1
        # Eine Challenge ist kein Parser-/Netzfehler: die Canary-Serie reisst.
        eintrag["fehler_serie"] = 0
        eintrag["challenge_bis"] = float(jetzt) + challenge_takt(eintrag)
        return
    if status in ("error", "parser"):
        eintrag["fail_streak"] = int(eintrag.get("fail_streak") or 0) + 1
        eintrag["fehler_serie"] = int(eintrag.get("fehler_serie") or 0) + 1
        # Eine Fehlerzeile unterbricht die Challenge-Serie.
        eintrag["challenge_serie"] = 0
        return

    # Jeder fachlich gueltige Abruf beendet eine Fehlerserie. Als Bestand
    # zaehlt aber nur ein bestaetigter, sofort kaufbarer, nicht gebrauchter
    # Treffer. Unbestaetigte Treffer, Vorbestellungen und Gebrauchtware
    # bleiben "nicht verfuegbar", damit der spaetere echte Restock nicht
    # als "schon verfuegbar" verdeckt wird.
    eintrag["fail_streak"] = 0
    eintrag["fehler_serie"] = 0
    eintrag["challenge_bis"] = 0.0
    eintrag["challenge_serie"] = 0
    eintrag["initialisiert"] = True
    eintrag["letzter_erfolg"] = float(jetzt)
    eintrag["verfuegbar"] = ist_sofort_treffer(r)
    preis = r.get("preis")
    if preis is not None:
        try:
            preis = float(preis)
        except (TypeError, ValueError):
            preis = None
    if preis is not None:
        # Beim ersten gueltigen Abruf ist der Preis die Alarm-Referenz. Danach
        # verschiebt nur noch ein tatsaechlicher Alarm sie (alarm_entscheidung).
        if eintrag.get("alarm_preis") is None:
            eintrag["alarm_preis"] = preis
        eintrag["preis"] = preis
        tief = eintrag.get("tief")
        try:
            eintrag["tief"] = preis if tief is None else min(float(tief), preis)
        except (TypeError, ValueError):
            eintrag["tief"] = preis


def _jitter(name):
    """Stabiler Versatz von 0 bis +10 %, damit Shops nicht sekundengleich starten."""
    roh = zlib.crc32(str(name).encode("utf-8")) % 1001
    return roh / 1000.0 * 0.1


def takt_sekunden(name, eintrag, konfig, jetzt=None):
    """Naechster Abstand in Sekunden.

    PS Direct laeuft nur in einem belegten oder gelernten Auflegefenster im
    schnellen Takt (Default 15 s), sonst wie alle anderen Shops im Zusatztakt
    (Default 30 s), jeweils mit 0 bis +10 % Jitter. Die gelernten Fenster
    kommen aus den eigenen NDJSON-Logs; ohne ausreichende Daten gilt der
    Default aus ``scan_core.DROP_FENSTER``. Eine Bot-Sperre haelt der Shop
    selbst ueber ``challenge_bis`` ein; zwei Parser-/Netzfehler in Folge 12
    Minuten.
    """
    eintrag = eintrag if isinstance(eintrag, dict) else {}
    status = str(eintrag.get("status") or "")
    if status in ("error", "parser") and int(eintrag.get("fail_streak") or 0) >= 2:
        return FEHLER_TAKT
    im_fenster = (name in PRIORITY_SHOPS
                  and core.im_drop_fenster(name, jetzt))
    basis = konfig.takt if im_fenster else konfig.takt_neben
    return int(round(float(basis) * (1.0 + _jitter(name))))


def drop_fenster_lernen(konfig, tz, jetzt=None, pfad=None):
    """Gelernte Drop-Fenster aus den eigenen NDJSON-Logs setzen.

    Ohne ausreichende Treffer bleibt ein bereits gespeicherter Stand erhalten;
    ohne beides gilt der Default aus ``scan_core.DROP_FENSTER``. Die Datei
    liegt im Datenverzeichnis und wird beim Tageswechsel neu geschrieben.
    """
    jetzt = time.time() if jetzt is None else float(jetzt)
    pfad = pfad or os.path.join(konfig.data_dir, core.DROP_FENSTER_LERN_FILE)
    checks = []
    pfade = sorted(glob.glob(os.path.join(konfig.data_dir,
                                          "watcher-log-*.ndjson")))[-14:]
    for log_pfad in pfade:
        try:
            with open(log_pfad, "r", encoding="utf-8") as datei:
                for zeile in datei:
                    try:
                        daten = json.loads(zeile)
                    except ValueError:
                        continue
                    if isinstance(daten, dict) and daten.get("typ") == "check":
                        checks.append(daten)
        except OSError:
            continue
    gelernt = core.lerne_drop_fenster(checks, tz=tz)
    if not gelernt.get("shops"):
        alt = core.drop_fenster_laden(pfad)
        if isinstance(alt, dict) and alt.get("shops"):
            gelernt = alt
            gelernt["quelle"] = "datei"
        else:
            gelernt["quelle"] = "default"
    if gelernt.get("shops"):
        core.drop_fenster_speichern(pfad, gelernt)
    core.setze_drop_fenster(gelernt.get("shops") or {})
    log({
        "typ": "drop_fenster",
        "ts": round(jetzt, 3),
        "iso": iso_ts(jetzt, tz),
        "quelle": gelernt.get("quelle") or "default",
        "checks": len(checks),
        "shops": gelernt.get("shops") or {},
    })
    return gelernt


def naechste_faelligkeit(eintrag, jetzt, takt):
    try:
        sperre = float((eintrag or {}).get("challenge_bis") or 0)
    except (TypeError, ValueError):
        sperre = 0.0
    return max(float(jetzt) + float(takt), sperre)


def pruefe_shop(h, deckel, stop):
    """Einen Shop abrufen, Treffer zweitpruefen und Health fortschreiben."""
    r = core.scan_einen(h, cancel=stop)
    if not isinstance(r, dict):
        return None
    # scan_einen klassifiziert mit MAX_PREIS. Nur hit/expensive haengen vom
    # Preisdeckel ab; alle anderen Klassen bleiben unveraendert.
    if r.get("klass") in ("hit", "expensive"):
        r["klass"] = core.classify(
            True, r.get("preis"), core.preis_deckel(r.get("land"), deckel)
        )
    if r.get("klass") == "hit" and not core.ist_gebraucht(r.get("condition")):
        r = core.verify_treffer(h, r, cancel=stop)
    # JSON-LD liefert nicht immer ein eigenes "verfuegbar"-Feld. Der Zustand
    # folgt deshalb der strengeren Regel: bestaetigt, sofort kaufbar, nicht
    # gebraucht. Eine Vorbestellung ist kein Bestand.
    r["verfuegbar"] = ist_sofort_treffer(r)
    try:
        core.health().record(r)
    except Exception:
        pass
    return r


def _tag_datum(jetzt, tz):
    try:
        return datetime.fromtimestamp(float(jetzt), tz).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _tag_leer():
    return {
        "datum": "",
        "checks": 0,
        "treffer": 0,
        "fehler": 0,
        "parser": 0,
        "challenge": 0,
        "bytes": 0,
        "requests": 0,
        "alarme": 0,
        "schatten": 0,
        "luecken": 0,
        "luecke_s": 0,
        "luecke_max": 0,
        "canary": {},
        "drift": {},
        "ms": [],
    }


def tag_sicherstellen(zustand):
    """Tageszaehler laden; ein alter oder defekter Block startet bei null."""
    if not isinstance(zustand, dict):
        return _tag_leer()
    tag = zustand.get("tag")
    if not isinstance(tag, dict):
        tag = _tag_leer()
        zustand["tag"] = tag
    for key in ("checks", "treffer", "fehler", "parser", "challenge",
                "bytes", "requests", "alarme", "schatten", "luecken",
                "luecke_s", "luecke_max"):
        tag[key] = max(0, _outbox_int(tag.get(key), 0))
    for key in ("canary", "drift"):
        roh = tag.get(key)
        sauber = {}
        if isinstance(roh, dict):
            for shop, info in roh.items():
                if isinstance(info, dict):
                    sauber[str(shop)] = info
        tag[key] = sauber
    tag["datum"] = str(tag.get("datum") or "")
    ms = tag.get("ms")
    if not isinstance(ms, list):
        ms = []
    tag["ms"] = [max(0, _outbox_int(x, 0)) for x in ms[-TAG_MS_MAX:]]
    return tag


def _tag_tagesblock(zustand, jetzt, tz):
    """Tagesblock holen; bei Datumswechsel lieber neu zaehlen."""
    tag = tag_sicherstellen(zustand)
    datum = _tag_datum(jetzt, tz)
    if tag["datum"] and tag["datum"] != datum:
        # Ohne tageswechsel() wuerde eine Zeile fehlen; lieber neu zaehlen
        # als Zahlen zweier Tage zu vermischen.
        tag = _tag_leer()
        tag["datum"] = datum
        zustand["tag"] = tag
    elif not tag["datum"]:
        tag["datum"] = datum
    return tag


def tag_luecke(zustand, sekunden, jetzt, tz):
    """Eine Pruefluecke von mehr als zwei Takten im Tageszaehler festhalten."""
    tag = _tag_tagesblock(zustand, jetzt, tz)
    try:
        dauer = max(0, int(round(float(sekunden))))
    except (TypeError, ValueError):
        dauer = 0
    tag["luecken"] += 1
    tag["luecke_s"] += dauer
    tag["luecke_max"] = max(tag["luecke_max"], dauer)
    return tag


def tag_buchen(zustand, r, jetzt, tz):
    """Einen Check in die Tageszaehler uebernehmen."""
    tag = _tag_tagesblock(zustand, jetzt, tz)
    tag["checks"] += 1
    tag["requests"] += 1 + (1 if (r or {}).get("verify") else 0)
    tag["bytes"] += max(0, _outbox_int((r or {}).get("bytes"), 0))
    try:
        ms = max(0, int(round(float((r or {}).get("dauer") or 0) * 1000)))
    except (TypeError, ValueError):
        ms = 0
    tag["ms"].append(ms)
    if len(tag["ms"]) > TAG_MS_MAX:
        del tag["ms"][:-TAG_MS_MAX]
    klass = str((r or {}).get("klass") or "")
    if klass == "hit":
        tag["treffer"] += 1
    elif klass == "challenge":
        tag["challenge"] += 1
    elif klass in ("error", "parser"):
        tag["fehler"] += 1
        if klass == "parser":
            tag["parser"] += 1
    return tag


def _kaufbox_verwertbar(r):
    """Nur ein Abruf mit Preis und erkannter Seite darf den Fingerprint setzen."""
    if not isinstance(r, dict) or r.get("preis") is None:
        return False
    return str(r.get("klass") or "") in ("hit", "expensive", "unavail")


def canary_buchen(zustand, name, eintrag, r, jetzt, tz):
    """Fehlerserie und Kaufbox-Drift fuer den Tagesbericht vormerken.

    Der Fingerprint stammt aus der ohnehin geladenen Seite; hier loest nichts
    einen zusaetzlichen Abruf aus. Drift zaehlt nur, wenn derselbe Abruf noch
    einen Preis geliefert hat - sonst ist der Parser schon gebrochen und die
    Fehlerserie ist die richtige Meldung.
    """
    if not isinstance(eintrag, dict) or not isinstance(r, dict):
        return {}
    tag = _tag_tagesblock(zustand, jetzt, tz)
    ergebnis = {}
    serie = int(eintrag.get("fehler_serie") or 0)
    if serie >= CANARY_FEHLER_SERIE:
        tag["canary"][str(name)] = {
            "serie": serie,
            "status": str(r.get("klass") or ""),
            "ts": float(jetzt),
        }
        ergebnis["serie"] = serie
    neu = str(r.get("kaufbox") or "")
    if neu and _kaufbox_verwertbar(r):
        alt = str(eintrag.get("kaufbox") or "")
        schon_gemeldet = str(name) in tag["drift"]
        eintrag["kaufbox"] = neu
        eintrag["kaufbox_ts"] = float(jetzt)
        if alt and alt != neu:
            tag["drift"][str(name)] = {
                "alt": alt, "neu": neu, "ts": float(jetzt),
            }
            ergebnis["drift"] = (alt, neu)
            ergebnis["drift_neu"] = not schon_gemeldet
    return ergebnis


def _perzentil(werte, anteil):
    if not werte:
        return None
    sortiert = sorted(werte)
    index = int(round(float(anteil) * (len(sortiert) - 1)))
    return sortiert[max(0, min(len(sortiert) - 1, index))]


def tag_zusammenfassung(tag, box):
    """Kennzahlen einer Tageszeile; reine Funktion, ohne Log und Netz."""
    tag = tag if isinstance(tag, dict) else {}
    checks = _outbox_int(tag.get("checks"), 0)
    fehler = _outbox_int(tag.get("fehler"), 0)
    challenge = _outbox_int(tag.get("challenge"), 0)
    erfolge = max(0, checks - fehler - challenge)
    ms = tag.get("ms") if isinstance(tag.get("ms"), list) else []
    box = box if isinstance(box, dict) else {}
    items = box.get("items") if isinstance(box.get("items"), list) else []
    offen = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("status") in ("pending", "sending")
    )
    failed = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("status") == "failed"
    )
    verfallen = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("status") == "expired"
    )
    roh_canary = tag.get("canary")
    roh_canary = roh_canary if isinstance(roh_canary, dict) else {}
    roh_drift = tag.get("drift")
    roh_drift = roh_drift if isinstance(roh_drift, dict) else {}
    canary = [
        {"shop": str(shop), "serie": _outbox_int(info.get("serie"), 0),
         "status": str(info.get("status") or "")}
        for shop, info in sorted(roh_canary.items())
        if isinstance(info, dict)
    ]
    drift = [
        {"shop": str(shop), "alt": str(info.get("alt") or ""),
         "neu": str(info.get("neu") or "")}
        for shop, info in sorted(roh_drift.items())
        if isinstance(info, dict)
    ]
    return {
        "datum": str(tag.get("datum") or ""),
        "checks": checks,
        "treffer": _outbox_int(tag.get("treffer"), 0),
        "fehler": fehler,
        "parser": _outbox_int(tag.get("parser"), 0),
        "challenge": challenge,
        "quote": round(100.0 * erfolge / checks, 1) if checks else 0.0,
        "bytes": _outbox_int(tag.get("bytes"), 0),
        "requests": _outbox_int(tag.get("requests"), 0),
        "ms_p50": _perzentil(ms, 0.50),
        "ms_p95": _perzentil(ms, 0.95),
        "alarme": _outbox_int(tag.get("alarme"), 0),
        "schatten": _outbox_int(tag.get("schatten"), 0),
        "luecken": _outbox_int(tag.get("luecken"), 0),
        "luecke_s": _outbox_int(tag.get("luecke_s"), 0),
        "luecke_max": _outbox_int(tag.get("luecke_max"), 0),
        "canary": canary,
        "drift": drift,
        "outbox_offen": offen,
        "outbox_failed": failed,
        "outbox_verfallen": verfallen,
    }


def tageswechsel(zustand, jetzt, tz):
    """Beim lokalen Tageswechsel die Tageszeile liefern und neu zaehlen."""
    tag = tag_sicherstellen(zustand)
    datum = _tag_datum(jetzt, tz)
    if not tag["datum"]:
        tag["datum"] = datum
        return None
    if tag["datum"] == datum:
        return None
    zusammenfassung = tag_zusammenfassung(tag, outbox_sicherstellen(zustand))
    neu = _tag_leer()
    neu["datum"] = datum
    zustand["tag"] = neu
    return zusammenfassung


def tag_bericht_text(zusammenfassung):
    """Titel und Text des Tagesberichts; ohne URLs und ohne Kanaele."""
    z = zusammenfassung if isinstance(zusammenfassung, dict) else {}
    datum = str(z.get("datum") or "?")

    def _ms(wert):
        return "-" if wert is None else "%d ms" % int(wert)

    def _canary(zeilen):
        if not zeilen:
            return "unauffaellig"
        return "; ".join(
            "%s %d Fehler (%s)" % (
                z.get("shop"), _outbox_int(z.get("serie"), 0),
                z.get("status") or "?",
            )
            for z in zeilen[:8] if isinstance(z, dict)
        ) or "unauffaellig"

    def _drift(zeilen):
        if not zeilen:
            return "unauffaellig"
        return "; ".join(
            "%s %s>%s" % (z.get("shop"), z.get("alt") or "?",
                          z.get("neu") or "?")
            for z in zeilen[:8] if isinstance(z, dict)
        ) or "unauffaellig"

    text = (
        "Checks %d, Treffer %d, Challenges %d\n"
        "Fehler %d (davon Parser %d), Erfolgsquote %.1f %%\n"
        "Anfragen %d, p50 %s, p95 %s\n"
        "Luecken >2 Takt: %d, gesamt %d s, laengste %d s\n"
        "Alarme %d (%d im Schatten), Outbox %d offen / %d fehlerhaft / "
        "%d verfallen\n"
        "Canary: %s\n"
        "Kaufbox-Drift: %s"
        % (
            _outbox_int(z.get("checks"), 0),
            _outbox_int(z.get("treffer"), 0),
            _outbox_int(z.get("challenge"), 0),
            _outbox_int(z.get("fehler"), 0),
            _outbox_int(z.get("parser"), 0),
            float(z.get("quote") or 0.0),
            _outbox_int(z.get("requests"), 0),
            _ms(z.get("ms_p50")),
            _ms(z.get("ms_p95")),
            _outbox_int(z.get("luecken"), 0),
            _outbox_int(z.get("luecke_s"), 0),
            _outbox_int(z.get("luecke_max"), 0),
            _outbox_int(z.get("alarme"), 0),
            _outbox_int(z.get("schatten"), 0),
            _outbox_int(z.get("outbox_offen"), 0),
            _outbox_int(z.get("outbox_failed"), 0),
            _outbox_int(z.get("outbox_verfallen"), 0),
            _canary(z.get("canary") if isinstance(z.get("canary"), list)
                    else []),
            _drift(z.get("drift") if isinstance(z.get("drift"), list)
                   else []),
        )
    )
    return "Waechter Tagesbericht " + datum, text


def tag_bericht_senden(konfig, settings, zustand, jetzt, pfad=None,
                       zusammenfassung=None):
    """Tagesbericht einmal pro Tag ueber den Ops-Kanal zustellen.

    Der Bericht ist eine Statusmeldung, kein Produktalarm: er geht auch im
    Schattenmodus raus. Ziel ist ``WATCH_OPS_WEBHOOK_URL``; ohne Ops-Kanal
    faellt er auf den Produkt-Webhook zurueck. Drei Versuche im Abstand von
    fuenf Minuten, danach wird der Versuch im NDJSON-Log vermerkt.
    """
    if not isinstance(zustand, dict):
        return False
    geaendert = False
    if zusammenfassung is not None:
        titel, text = tag_bericht_text(zusammenfassung)
        zustand["tag_bericht"] = {
            "titel": titel,
            "text": text,
            "versuche": 0,
            "next_ts": _outbox_float(jetzt, time.time()),
        }
        geaendert = True
    bericht = zustand.get("tag_bericht")
    if not isinstance(bericht, dict):
        return False
    jetzt = _outbox_float(jetzt, time.time())
    if _outbox_float(bericht.get("next_ts"), 0.0) > jetzt:
        return False

    ziel, kanal = _ops_ziel(settings)
    url = str(ziel.get("webhook_url") or "").strip()
    versuch = _outbox_int(bericht.get("versuche"), 0) + 1
    if not url:
        ok, info = False, "kein Kanal"
    else:
        try:
            erg = core.webhook_senden(
                url,
                ziel.get("webhook_preset"),
                bericht.get("titel") or "",
                bericht.get("text") or "",
                timeout=10,
            )
            ok, info = bool(erg[0]), str(erg[1] or "")
        except Exception as e:
            ok, info = False, type(e).__name__
    info = _outbox_safe_info(info, settings)

    if ok:
        zustand.pop("tag_bericht", None)
        geaendert = True
        log({"typ": "tag_bericht", "ts": round(jetzt, 3), "ok": True,
             "kanal": kanal, "versuch": versuch, "info": info})
    else:
        bericht["versuche"] = versuch
        if versuch >= TAG_BERICHT_MAX or not url:
            zustand.pop("tag_bericht", None)
            log({"typ": "tag_bericht", "ts": round(jetzt, 3), "ok": False,
                 "kanal": kanal, "versuch": versuch, "aufgegeben": True,
                 "info": info})
        else:
            bericht["next_ts"] = jetzt + TAG_BERICHT_BACKOFF_S
            log({"typ": "tag_bericht", "ts": round(jetzt, 3), "ok": False,
                 "kanal": kanal, "versuch": versuch,
                 "next_ts": round(bericht["next_ts"], 3), "info": info})
        geaendert = True

    if geaendert and pfad:
        _outbox_state_save(pfad, zustand, "tag_bericht")
    return bool(ok)


def budget_rest(verlauf, jetzt, maximum):
    """Freie Abrufe im gleitenden 60-s-Fenster (mindestens ein Budget)."""
    maximum = max(1, _outbox_int(maximum, 12))
    if not isinstance(verlauf, list):
        return maximum
    jetzt = _outbox_float(jetzt, time.time())
    try:
        verlauf[:] = [t for t in verlauf if jetzt - float(t) < 60.0]
    except (TypeError, ValueError):
        verlauf[:] = []
    return max(0, maximum - len(verlauf))


def shop_vorrang(name):
    """PS Direct zuerst, danach alle uebrigen Shops."""
    return 0 if str(name or "") in PRIORITY_SHOPS else 1


def challenge_takt(eintrag):
    """15 Minuten Sperre, nach drei Challenges in Folge eine Stunde."""
    serie = _outbox_int((eintrag or {}).get("challenge_serie"), 0)
    return CHALLENGE_LANG if serie >= CHALLENGE_LANG_NACH else CHALLENGE_TAKT


def preflight(konfig, pfad=None):
    """Startpruefung ohne Netzzugriff: Verzeichnis, Kanal, Zustand, Zeitzone."""
    checks = []

    def _check(name, ok, info="", kritisch=True):
        checks.append({"name": name, "ok": bool(ok), "info": str(info)[:120],
                       "kritisch": bool(kritisch)})

    probe = os.path.join(konfig.data_dir, ".preflight")
    try:
        os.makedirs(konfig.data_dir, exist_ok=True)
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        _check("datenverzeichnis", True, konfig.data_dir)
    except OSError as e:
        _check("datenverzeichnis", False, type(e).__name__)

    try:
        ZoneInfo(konfig.tz_name)
        _check("zeitzone", True, konfig.tz_name, kritisch=False)
    except Exception:
        _check("zeitzone", False, "unbekannt: " + konfig.tz_name,
               kritisch=False)

    if konfig.shadow and not konfig.webhook_url:
        _check("webhook", True, "leer, Schattenmodus", kritisch=False)
    else:
        url = konfig.webhook_url
        _check("webhook", url.lower().startswith("https://"),
               core.redact_url(url) if url else "fehlt")

    if konfig.ops_url:
        _check("ops", konfig.ops_url.lower().startswith("https://"),
               core.redact_url(konfig.ops_url), kritisch=False)

    if pfad and os.path.exists(pfad):
        try:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            _check("zustand", isinstance(daten, dict),
                   "lesbar" if isinstance(daten, dict) else "kein Objekt",
                   kritisch=False)
        except Exception as e:
            _check("zustand", False, type(e).__name__, kritisch=False)
    else:
        _check("zustand", True, "neu", kritisch=False)

    return all(c["ok"] for c in checks if c["kritisch"]), checks


def settings_aus(konfig):
    """Minimale Einstellungen fuer Webhook und Preisdeckel.

    Der Waechter hat keine App-Einstellungen. Die Bestandsregel
    ``ist_sofort_treffer`` erzwingt Bestaetigung, Sofortkauf und Neuware;
    Ruhezeiten, Stummschaltung und Tiefstpreisfilter sind bewusst aus.
    """
    return {
        "webhook_url": konfig.webhook_url,
        "webhook_preset": konfig.webhook_preset,
        "ops_url": konfig.ops_url,
        "ops_preset": konfig.ops_preset,
        "max_preis": konfig.max_preis,
    }


def _log_pfad(tag, teil=1):
    name = LOG_PREFIX + str(tag)
    if teil > 1:
        name += ".%d" % int(teil)
    return os.path.join(_LOG_ZIEL, name + LOG_SUFFIX)


def _log_handle_schliessen():
    global _LOG_HANDLE
    handle = _LOG_HANDLE
    _LOG_HANDLE = None
    if handle is None:
        return
    try:
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
    except OSError:
        pass


def log_datei_schliessen():
    """Senke schliessen; danach geht das Log wieder nur auf stdout."""
    global _LOG_ZIEL
    with _LOG_LOCK:
        _log_handle_schliessen()
        _LOG_ZIEL = ""


def log_datei_oeffnen(daten_dir, jetzt=None, tz=None):
    """NDJSON-Senke im Datenverzeichnis vorbereiten und alte Tage loeschen."""
    global _LOG_ZIEL, _LOG_TZ, _LOG_TAG, _LOG_TEIL
    global _LOG_GROESSE, _LOG_VERWORFEN
    log_datei_schliessen()
    _LOG_ZIEL = str(daten_dir or "")
    _LOG_TZ = tz
    _LOG_TAG = ""
    _LOG_TEIL = 0
    _LOG_GROESSE = 0
    _LOG_VERWORFEN = 0
    if not _LOG_ZIEL:
        return
    try:
        os.makedirs(_LOG_ZIEL, exist_ok=True)
        log_aufraeumen(_LOG_ZIEL, jetzt, tz)
    except OSError:
        _LOG_ZIEL = ""


def _log_oeffnen(tag, teil):
    global _LOG_HANDLE, _LOG_GROESSE, _LOG_TAG, _LOG_TEIL
    pfad = _log_pfad(tag, teil)
    _LOG_HANDLE = open(pfad, "ab")
    _LOG_TAG = str(tag)
    _LOG_TEIL = int(teil)
    try:
        _LOG_GROESSE = os.path.getsize(pfad)
    except OSError:
        _LOG_GROESSE = 0


def _log_datei_schreiben(zeile, jetzt):
    """Eine Zeile an die Tagesdatei anhaengen; Fehler deaktivieren die Senke."""
    global _LOG_ZIEL, _LOG_TAG, _LOG_TEIL, _LOG_GROESSE, _LOG_VERWORFEN
    if not _LOG_ZIEL:
        return
    tag = _tag_datum(jetzt, _LOG_TZ)
    roh = (zeile + "\n").encode("utf-8")
    try:
        if _LOG_HANDLE is None or _LOG_TAG != tag:
            _log_handle_schliessen()
            _log_oeffnen(tag, 1)
            _LOG_VERWORFEN = 0
            log_aufraeumen(_LOG_ZIEL, jetzt, _LOG_TZ)
        if _LOG_GROESSE + len(roh) > LOG_MAX_BYTES:
            if _LOG_TEIL < LOG_MAX_PARTS:
                _log_handle_schliessen()
                _log_oeffnen(tag, _LOG_TEIL + 1)
            else:
                _LOG_VERWORFEN += 1
                if _LOG_VERWORFEN == 1:
                    print(
                        json.dumps(
                            {
                                "typ": "log_verworfen",
                                "ts": round(float(jetzt), 3),
                                "info": "Tagesdeckel erreicht",
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                return
        _LOG_HANDLE.write(roh)
        _LOG_HANDLE.flush()
        _LOG_GROESSE += len(roh)
    except OSError as e:
        _log_handle_schliessen()
        _LOG_ZIEL = ""
        print(
            json.dumps(
                {
                    "typ": "log_fehler",
                    "ts": round(float(jetzt), 3),
                    "info": type(e).__name__,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )


def log_dateien(daten_dir):
    """Sortierte NDJSON-Tagesdateien des Waechters."""
    try:
        namen = sorted(os.listdir(daten_dir))
    except OSError:
        return []
    return [
        os.path.join(daten_dir, name) for name in namen
        if name.startswith(LOG_PREFIX) and name.endswith(LOG_SUFFIX)
    ]


def log_aufraeumen(daten_dir, jetzt=None, tz=None):
    """Dateien ausserhalb der Aufbewahrungsfrist loeschen."""
    if not daten_dir:
        return 0
    jetzt = _outbox_float(jetzt, time.time())
    heute = datetime.strptime(_tag_datum(jetzt, tz), "%Y-%m-%d").date()
    entfernt = 0
    for pfad in log_dateien(daten_dir):
        name = os.path.basename(pfad)
        rest = name[len(LOG_PREFIX):-len(LOG_SUFFIX)]
        try:
            datum = datetime.strptime(rest[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if (heute - datum).days > LOG_KEEP_DAYS:
            try:
                os.remove(pfad)
                entfernt += 1
            except OSError:
                pass
    return entfernt


def log(daten, jetzt=None):
    zeile = json.dumps(daten, ensure_ascii=False, sort_keys=True)
    with _LOG_LOCK:
        print(zeile, flush=True)
        _log_datei_schreiben(zeile, time.time() if jetzt is None else jetzt)


def iso_ts(ts, tz):
    try:
        return datetime.fromtimestamp(float(ts), tz).isoformat(timespec="seconds")
    except Exception:
        return ""


def melde(r, event, konfig, zustand, schatten, settings, tz, pfad=None):
    """Alarm im Schatten protokollieren oder live persistent einreihen."""
    restock = event == "restock"
    titel = (
        "PS5 Pro 2 TB: wieder verfuegbar"
        if restock
        else "PS5 Pro 2 TB: " + core.format_preis(r.get("preis"))
    )
    text = r.get("haendler", "?") + (
        " - wieder verfuegbar" if restock else " - jetzt verfuegbar"
    )
    # sende_webhook_alarm nutzt das Flag fuer den Dedupe-Schluessel.
    r["_restock"] = restock
    jetzt = time.time()
    tag = tag_sicherstellen(zustand)
    tag["alarme"] += 1
    if schatten:
        tag["schatten"] += 1
    basis = {
        "typ": "alarm",
        "ts": round(jetzt, 3),
        "iso": iso_ts(jetzt, tz),
        "modus": "schatten" if schatten else "live",
        "shop": r.get("haendler"),
        "event": event,
        "preis": r.get("preis"),
        "titel": titel,
        "text": text,
        "url": r.get("url"),
        "preset": konfig.webhook_preset,
    }

    if schatten:
        if not core.webhook_dedupe(r.get("haendler"), r.get("preis"), restock):
            basis.update(
                {
                    "aktion": "unterdrueckt",
                    "grund": "dedupe",
                    "ok": None,
                    "info": "dedupe",
                }
            )
            log(basis)
            return
        zustand["alarme_schatten"] = int(zustand.get("alarme_schatten") or 0) + 1
        basis.update(
            {
                "aktion": "wuerde_senden",
                "ok": None,
                "info": "Schattenmodus, kein Versand",
            }
        )
        log(basis)
        return

    item = outbox_enqueue(r, event, zustand, jetzt, titel, text)
    if item is None:
        # Auch ein wegen Ueberlauf nicht aufgenommenes Ereignis darf nicht
        # still verschwinden: einmaliger Systemalarm ueber den Webhook.
        overflow = {
            "id": "overflow_" + _outbox_id(jetzt).split("_")[-1],
            "shop": r.get("haendler"),
            "event": event,
            "price": r.get("preis"),
            "attempts": 0,
            "last_error": "Outbox voll",
            "failed_grund": "overflow",
            "restock": restock,
            "url": r.get("url"),
        }
        outbox_systemalarm(overflow, zustand, settings, jetzt, pfad)
        basis.update(
            {
                "aktion": "nicht_aufgenommen",
                "grund": "outbox_voll",
                "ok": None,
                "info": "Outbox voll",
            }
        )
        log(basis)
        return
    if not _outbox_state_save(pfad, zustand, "enqueue", item):
        basis.update(
            {
                "aktion": "nicht_gesendet",
                "grund": "zustand_nicht_speicherbar",
                "outbox_id": item.get("id"),
                "ok": None,
                "info": "Ereignis nicht persistent",
            }
        )
        log(basis)
        return
    basis.update(
        {
            "aktion": "eingereiht",
            "outbox_id": item.get("id"),
            "versuch": 0,
            "ok": None,
            "info": "persistiert, Versand folgt",
        }
    )
    log(basis)


def outbox_stand(zustand):
    """Offene und fehlgeschlagene Outbox-Eintraege fuer den Status."""
    box = outbox_sicherstellen(zustand)
    items = box.get("items") or []
    offen = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("status") in ("pending", "sending")
    )
    failed = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("status") == "failed"
    )
    verfallen = sum(
        1 for item in items
        if isinstance(item, dict) and item.get("status") == "expired"
    )
    return {"offen": offen, "failed": failed, "verfallen": verfallen,
            "gesamt": _outbox_int(box.get("gesamt"), 0)}


def status_daten(zustand, konfig, jetzt, tz, budget_verbraucht=0):
    """Kompakter lokaler Status: Wachzeit, Runden, Outbox und Budget."""
    zustand = zustand if isinstance(zustand, dict) else {}
    jetzt = _outbox_float(jetzt, time.time())
    return {
        "schema": 1,
        "ts": round(jetzt, 3),
        "wach_ts": round(jetzt, 3),
        "iso": iso_ts(jetzt, tz),
        "pid": os.getpid(),
        "runden": _outbox_int(zustand.get("runden"), 0),
        "letzte_runde": round(
            _outbox_float(zustand.get("letzte_runde"), 0.0), 3
        ),
        "schatten": schatten_aktiv(zustand, jetzt, konfig.shadow),
        "schatten_bis": _outbox_float(zustand.get("schatten_bis"), 0.0),
        "outbox": outbox_stand(zustand),
        "budget": {
            "max": _outbox_int(konfig.max_req_min, 12),
            "verbraucht": max(0, _outbox_int(budget_verbraucht, 0)),
        },
    }


def status_schreiben(status, pfad):
    """Statusdatei atomar schreiben; ein Fehler stoppt den Loop nicht."""
    if not pfad or not isinstance(status, dict):
        return False
    try:
        zustand_speichern(pfad, status)
        return True
    except Exception as e:
        log({
            "typ": "status_fehler",
            "ts": round(time.time(), 3),
            "info": type(e).__name__,
        })
        return False


def heartbeat_faellig(letzte, jetzt, takt=HEARTBEAT_TAKT):
    """Der Ping laeuft im eigenen Takt, unabhaengig von faelligen Shops."""
    try:
        return float(jetzt) - float(letzte) >= float(takt)
    except (TypeError, ValueError):
        return True


def heartbeat(konfig, status=None):
    """Optionaler Lebenszeichen-Ping (z. B. healthchecks.io). Nie die URL loggen."""
    if not konfig.heartbeat_url:
        return
    text = "ok"
    if isinstance(status, dict):
        box = status.get("outbox")
        box = box if isinstance(box, dict) else {}
        budget = status.get("budget")
        budget = budget if isinstance(budget, dict) else {}
        text = "ok runden=%s offen=%s fehler=%s verfallen=%s budget=%s/%s" % (
            status.get("runden"),
            box.get("offen"),
            box.get("failed"),
            box.get("verfallen"),
            budget.get("verbraucht"),
            budget.get("max"),
        )
    try:
        ok, info = core.webhook_senden(
            konfig.heartbeat_url, "generisch", "", text, timeout=5
        )
    except Exception as e:
        ok, info = False, type(e).__name__
    log({"typ": "heartbeat", "ok": bool(ok), "info": str(info or "")[:120]})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    unbekannt = [a for a in argv if a != "--test-alarm"]
    if unbekannt:
        print(
            "Unbekannte Argumente: %s (erlaubt: --test-alarm)"
            % ", ".join(unbekannt),
            file=sys.stderr,
        )
        return 2
    STOP.clear()
    try:
        konfig = Konfig.aus_env()
    except ValueError as e:
        print("Konfiguration: %s" % e, file=sys.stderr)
        return 2
    if not konfig.shadow and not konfig.webhook_url:
        print(
            "WATCH_WEBHOOK_URL fehlt, obwohl WATCH_SHADOW=0. "
            "Erst Schatten laufen lassen, dann Kanal setzen.",
            file=sys.stderr,
        )
        return 2

    try:
        os.makedirs(konfig.data_dir, exist_ok=True)
    except OSError as e:
        print("Datenverzeichnis: %s" % e, file=sys.stderr)
        return 2
    core.set_data_dir(konfig.data_dir)
    core.reset_health()
    tz = konfig.zeitzone()

    pfad = os.path.join(konfig.data_dir, STATE_FILE)
    jetzt = time.time()
    log_datei_oeffnen(konfig.data_dir, jetzt, tz)
    preflight_ok, pruefungen = preflight(konfig, pfad)
    log(
        {
            "typ": "preflight",
            "ts": round(jetzt, 3),
            "ok": preflight_ok,
            "checks": pruefungen,
        }
    )
    if not preflight_ok:
        for pruefung in pruefungen:
            if pruefung.get("kritisch") and not pruefung.get("ok"):
                print(
                    "Preflight: %s - %s"
                    % (pruefung.get("name"), pruefung.get("info")),
                    file=sys.stderr,
                )
        log_datei_schliessen()
        return 2
    zustand = zustand_laden(pfad, jetzt, konfig.shadow_hours)
    if "--test-alarm" in argv:
        ok, info = testalarm_senden(konfig, settings_aus(konfig), pfad, jetzt)
        log({"typ": "testalarm", "ts": round(time.time(), 3),
             "ok": bool(ok), "info": str(info)[:120]})
        print("Testalarm: %s" % ("zugestellt" if ok else "fehlgeschlagen"))
        if info and not ok:
            print("Grund: %s" % info, file=sys.stderr)
        log_datei_schliessen()
        return 0 if ok else 1
    # Produkt-URLs: ein Cache im Datenverzeichnis hat Vorrang, sonst die
    # mitgelieferte Datei neben scan_core. Ohne das liefen Shops mit
    # Produkt-Override auf ihre Suchseite.
    config_anzahl = core.lade_shop_config()
    if not config_anzahl:
        config_anzahl = core.lade_shop_config_datei(
            os.path.join(ROOT, "shop_config.json")
        )
    nach_name = {h["name"]: h for h in core.HAENDLER}
    shops = [nach_name[n] for n in konfig.shops]
    settings = settings_aus(konfig)
    deckel = core.preis_deckel_aus(settings)
    next_due = {h["name"]: 0.0 for h in shops}
    schatten = schatten_aktiv(zustand, jetzt, konfig.shadow)
    drop_fenster = drop_fenster_lernen(konfig, tz, jetzt)

    log(
        {
            "typ": "start",
            "ts": round(jetzt, 3),
            "iso": iso_ts(jetzt, tz),
            "version": "p0",
            "schatten": schatten,
            "schatten_bis": iso_ts(zustand.get("schatten_bis"), tz),
            "schatten_rest_h": round(
                max(0.0, float(zustand.get("schatten_bis") or 0) - jetzt) / 3600.0, 2
            ),
            "shops": [h["name"] for h in shops],
            "shop_config": config_anzahl,
            "takt": konfig.takt,
            "takt_neben": konfig.takt_neben,
            "drop_fenster": drop_fenster.get("shops") or {},
            "drop_fenster_quelle": drop_fenster.get("quelle") or "default",
            "preset": konfig.webhook_preset,
            "budget_min": konfig.max_req_min,
            "preis_toleranz": konfig.preis_toleranz,
            "ops": bool(konfig.ops_url),
            "webhook": core.redact_url(konfig.webhook_url)
            if konfig.webhook_url
            else "-",
            "heartbeat": bool(konfig.heartbeat_url),
        }
    )

    # Bereits persistierte Alarme haben Vorrang vor neuen Scans. Im
    # Schattenmodus bleibt die Outbox absichtlich liegen.
    if not schatten:
        outbox_drain(
            zustand,
            konfig,
            settings,
            tz,
            jetzt=jetzt,
            pfad=pfad,
            schatten=False,
        )

    def _beenden(signum, frame):
        STOP.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _beenden)
        except (ValueError, OSError):
            pass

    request_verlauf = []
    status_pfad = os.path.join(konfig.data_dir, STATUS_FILE)
    letzte_status = 0.0
    letzte_heartbeat = 0.0
    # Sofort eine frische Datei, damit der Healthcheck nicht auf den ersten
    # Loop warten muss.
    status_schreiben(status_daten(zustand, konfig, jetzt, tz, 0), status_pfad)
    try:
        while not STOP.is_set():
            jetzt = time.time()
            schatten = schatten_aktiv(zustand, jetzt, konfig.shadow)
            abschluss = tageswechsel(zustand, jetzt, tz)
            if abschluss:
                log(dict(abschluss, typ="tag", ts=round(jetzt, 3)))
                drop_fenster_lernen(konfig, tz, jetzt)
            # Bericht nach dem Tageswechsel einreihen, danach Retries bedienen.
            tag_bericht_senden(konfig, settings, zustand, jetzt, pfad, abschluss)
            status = status_daten(
                zustand, konfig, jetzt, tz, len(request_verlauf)
            )
            # Der Ping misst den Loop, nicht die Faelligkeit der Shops.
            if heartbeat_faellig(letzte_heartbeat, jetzt):
                heartbeat(konfig, status)
                letzte_heartbeat = jetzt
            if jetzt - letzte_status >= STATUS_TAKT:
                if status_schreiben(status, status_pfad):
                    letzte_status = jetzt
            if not schatten:
                outbox_drain(
                    zustand,
                    konfig,
                    settings,
                    tz,
                    jetzt=jetzt,
                    pfad=pfad,
                    schatten=False,
                )
            faellig = [h for h in shops if next_due.get(h["name"], 0.0) <= jetzt]
            faellig.sort(
                key=lambda h: (
                    shop_vorrang(h["name"]),
                    float(next_due.get(h["name"], 0.0)),
                )
            )
            rest = budget_rest(request_verlauf, jetzt, konfig.max_req_min)
            if faellig and rest <= 0:
                # Minutenbudget voll: kurz warten statt heiss zu drehen.
                STOP.wait(2.0)
                continue
            faellig = faellig[:rest]
            if faellig:
                runde_start = time.time()
                for h in faellig:
                    request_verlauf.append(runde_start)
                ergebnisse = []
                ex = ThreadPoolExecutor(max_workers=max(1, min(2, len(faellig))))
                try:
                    futures = {
                        ex.submit(pruefe_shop, h, deckel, STOP): h for h in faellig
                    }
                    for fut in as_completed(futures):
                        h = futures[fut]
                        name = h["name"]
                        try:
                            r = fut.result()
                        except Exception as e:
                            log(
                                {
                                    "typ": "fehler",
                                    "ts": round(time.time(), 3),
                                    "shop": name,
                                    "info": type(e).__name__,
                                }
                            )
                            r = None
                        if not isinstance(r, dict):
                            continue
                        ergebnisse.append(r)
                        if r.get("verify"):
                            # Der zweite Abruf zaehlt ebenfalls als Request.
                            request_verlauf.append(time.time())
                        eintrag = zustand["shops"].setdefault(name, {})
                        try:
                            letzte = float(eintrag.get("ts") or 0)
                        except (TypeError, ValueError):
                            letzte = 0.0
                        if letzte:
                            abstand = time.time() - letzte
                            if abstand > 2 * takt_sekunden(name, eintrag,
                                                           konfig, jetzt):
                                tag_luecke(zustand, abstand, time.time(), tz)
                        event = alarm_entscheidung(eintrag, r,
                                                   konfig.preis_toleranz)
                        aktualisiere(eintrag, r, time.time(), tz)
                        tag_buchen(zustand, r, time.time(), tz)
                        canary = canary_buchen(zustand, name, eintrag, r,
                                               time.time(), tz)
                        if canary.get("drift") and canary.get("drift_neu"):
                            alt_fp, neu_fp = canary["drift"]
                            log({
                                "typ": "markup_drift",
                                "ts": round(time.time(), 3),
                                "iso": iso_ts(time.time(), tz),
                                "shop": name,
                                "alt": alt_fp,
                                "neu": neu_fp,
                                "info": "Kaufbox-Struktur geaendert",
                            })
                        if canary.get("serie") == CANARY_FEHLER_SERIE:
                            log({
                                "typ": "canary",
                                "ts": round(time.time(), 3),
                                "iso": iso_ts(time.time(), tz),
                                "shop": name,
                                "serie": canary["serie"],
                                "status": str(r.get("klass") or ""),
                            })
                        if r.get("klass") == "challenge":
                            serie = int(eintrag.get("challenge_serie") or 0)
                            heute = _tag_datum(time.time(), tz)
                            if (serie >= CHALLENGE_LANG_NACH
                                    and eintrag.get("challenge_info_tag") != heute):
                                eintrag["challenge_info_tag"] = heute
                                log(
                                    {
                                        "typ": "challenge",
                                        "ts": round(time.time(), 3),
                                        "shop": name,
                                        "serie": serie,
                                        "bis": iso_ts(
                                            eintrag.get("challenge_bis"), tz
                                        ),
                                        "info": "drei Challenges in Folge, "
                                                "60 Minuten Pause",
                                    }
                                )
                        if event:
                            melde(
                                r,
                                event,
                                konfig,
                                zustand,
                                schatten,
                                settings,
                                tz,
                                pfad,
                            )
                        log(
                            {
                                "typ": "check",
                                "ts": round(time.time(), 3),
                                "iso": iso_ts(time.time(), tz),
                                "shop": name,
                                "klass": r.get("klass"),
                                "preis": r.get("preis"),
                                "verfuegbar": r.get("verfuegbar"),
                                "status": r.get("status") or r.get("avail_state"),
                                "bytes": r.get("bytes"),
                                "ms": round(float(r.get("dauer") or 0) * 1000),
                                "frisch": r.get("fresh"),
                                "not_modified": r.get("not_modified"),
                                "verify": r.get("verify"),
                                "fehler": r.get("fehler"),
                                "event": event,
                            }
                        )
                finally:
                    ex.shutdown(wait=True, cancel_futures=True)

                try:
                    core.health().save()
                except Exception:
                    pass
                try:
                    core.flush_http_cache()
                except Exception:
                    pass

                jetzt_nach = time.time()
                for h in faellig:
                    eintrag = zustand["shops"].get(h["name"], {})
                    takt = takt_sekunden(h["name"], eintrag, konfig, jetzt)
                    # Ab Rundenstart rechnen, damit die Pruefdauer den Takt
                    # nicht zusaetzlich verlaengert.
                    next_due[h["name"]] = naechste_faelligkeit(
                        eintrag, jetzt, takt
                    )

                zustand["runden"] = int(zustand.get("runden") or 0) + 1
                zustand["letzte_runde"] = jetzt_nach
                try:
                    zustand_speichern(pfad, zustand)
                except Exception as e:
                    log(
                        {
                            "typ": "fehler",
                            "ts": round(time.time(), 3),
                            "info": "zustand: " + type(e).__name__,
                        }
                    )
                if status_schreiben(
                    status_daten(zustand, konfig, jetzt_nach, tz,
                                 len(request_verlauf)),
                    status_pfad,
                ):
                    letzte_status = jetzt_nach
                log(
                    {
                        "typ": "runde",
                        "ts": round(jetzt_nach, 3),
                        "geprueft": len(ergebnisse),
                        "treffer": sum(
                            1 for x in ergebnisse if x.get("klass") == "hit"
                        ),
                        "dauer_ms": round((jetzt_nach - runde_start) * 1000),
                        "schatten": schatten,
                        "runden": zustand["runden"],
                        "budget_verbraucht": len(request_verlauf),
                        "budget_max": konfig.max_req_min,
                    }
                )

            if STOP.is_set():
                break
            naechste = min(next_due.values()) if next_due else time.time() + 5
            warten = naechste - time.time()
            if warten > 0:
                # Kurze Schlafstuecke: SIGTERM und fällige Shops werden zuegig
                # bemerkt, ohne die CPU zu belasten.
                STOP.wait(min(float(warten), 2.0))
            else:
                # Budget voll oder faelliger Shop ohne freien Platz: nicht
                # heiss drehen, sondern kurz warten.
                STOP.wait(1.0)
    finally:
        try:
            zustand_speichern(pfad, zustand)
        except Exception:
            pass
        try:
            core.health().save()
        except Exception:
            pass
        try:
            core.flush_http_cache()
        except Exception:
            pass
        status_schreiben(
            status_daten(zustand, konfig, time.time(), tz,
                         len(request_verlauf)),
            status_pfad,
        )
        log(
            {
                "typ": "stop",
                "ts": round(time.time(), 3),
                "runden": int(zustand.get("runden") or 0),
                "alarme_schatten": int(zustand.get("alarme_schatten") or 0),
                "alarme_gesendet": int(zustand.get("alarme_gesendet") or 0),
            }
        )
        log_datei_schliessen()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
