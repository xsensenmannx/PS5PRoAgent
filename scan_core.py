"""Netz-, Preis- und Speicherlogik ohne Kivy.

Wird von der App (main.py) und vom Hintergrund-Service (service.py) benutzt.
Der Service laeuft in einem eigenen Prozess ohne UI - dort darf kein Kivy
importiert werden, deshalb liegt diese Logik hier getrennt.
"""
import os, sys, json, re, time, random, threading, traceback, hashlib, zlib
import html as _html
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed

_RQ = None
_RQ_TRIED = False

def _requests():
    """requests erst beim ersten Netzaufruf importieren (Kaltstart).

    Der Import zieht urllib3, idna und charset-normalizer mit. Auf Android kostet
    das beim Start spuerbar Zeit, bevor das erste Bild steht - gebraucht wird es
    aber erst beim ersten Scan. Faellt die Bibliothek aus, bleibt der urllib-Pfad.
    """
    global _RQ, _RQ_TRIED
    if not _RQ_TRIED:
        _RQ_TRIED = True
        try:
            import requests as _m
            _RQ = _m
        except ImportError:
            _RQ = None
    return _RQ

_TLS = threading.local()

def _session():
    """Eine requests.Session pro Thread - ein geteiltes Session-Objekt ist nicht thread-sicher."""
    rq = _requests()
    if rq is None: return None
    s = getattr(_TLS, "session", None)
    if s is None:
        s = rq.Session()
        s.headers.update({"Accept-Encoding":"gzip, deflate",
                          "Connection":"keep-alive","DNT":"1"})
        _TLS.session = s
    return s

MAX_PREIS, MIN_PREIS, MSRP_ZIEL = 900.0, 550.0, 799.99
# Absolute Plausibilitaetsgrenze fuer einen PS5-Pro-Preis. Der Deckel
# (MAX_PREIS) bleibt davon getrennt: Auch bei offenem Deckel ist ein Preis
# ausserhalb dieses Bereichs kein Treffer, sondern ein Parser-/Seitenfehler.
PREIS_PLAUSIBEL_MAX = 5000.0
# Grenzen fuer einen gewaehlten Deckel. 400 EUR ist unter jedem realistischen
# Preis fuer die 2-TB-Konsole, 1500 EUR deckt die teuersten AT-Angebote ab.
DECKEL_MIN, DECKEL_MAX = 400.0, 1500.0
PRICE_OPTIONS = [700.0, 800.0, 900.0, None]
SORT_OPTIONS = ["Preis","Händler","Zeit"]
AUTO_INTERVALS = [(300,"5m"),(600,"10m"),(900,"15m"),(1800,"30m"),(3600,"60m")]
TIMEOUT, WORKER = 20, 6
# Ein Shop darf den Scan nicht mit einem sehr langen Retry-After blockieren.
# Bis zu diesem Wert wird der Server-Wunsch respektiert, danach wird der Shop
# als Rate-Limit gewertet und der naechste Shop gescannt.
RETRY_AFTER_MAX = 15
HISTORY_FILE, SETTINGS_FILE = "ps5pro_history.json", "ps5pro_settings.json"
HTTP_CACHE_FILE = "ps5pro_http_cache.json"
# Kaufprotokoll: Haendler, Preis, Zeitpunkt. Bewusst klein und ohne URL -
# es beantwortet nur "was habe ich wann fuer wie viel gekauft".
KAEUFE_FILE = "ps5pro_kaeufe.json"
MAX_KAEUFE = 50
KAUF_STUMM_S = 24 * 3600
# Obergrenze fuer eine HTML-Antwort. Manche Shops liefern riesige Kategorieseiten;
# alles darueber ist fuer die Preiserkennung nutzlos und kostet nur Traffic.
MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_SERIE_PUNKTE = 120
# Ein 304 darf keinen beliebig alten Stand konservieren. Nach sechs Stunden
# wird die Seite einmal unbedingt neu geladen; danach greift wieder ETag/304.
CACHE_MAX_ALTER = 6 * 3600
# Belege sind kleine, redigierte Ausschnitte - kein HTML, keine Tokens.
EVIDENCE_FILE = "ps5pro_evidence.json"
MAX_BELEGE = 200

# Nur Zustaende, die sich unterschiedlich verhalten. OnlineOnly und
# LimitedAvailability sind kaufbar wie InStock und werden dort eingereiht.
CHANCE_STATES = frozenset(("pickup_only", "lottery", "invite"))
BUNDLE_MUSTER = re.compile(
    r"\b(bundle|im\s+set|set\s+mit|inkl\.?\s+controller|mit\s+controller|"
    r"controller\s+bundle|zubehoer\s+inkl\.?)\b", re.I)
# Nur spezifische Marker. "Gewinnspiel" steht zu oft in Fusszeilen und wuerde
# einen echten Treffer faelschlich zur Chance machen.
CHANCE_PATTERNS = (
    ("lottery", ("lotterie", "verlosung", "teilnahmeschluss")),
    ("invite", ("nur mit einladung", "nur auf einladung", "invite only",
                "invitation only", "einladung erforderlich")),
    ("pickup_only", ("nur im markt", "nur zur abholung", "click & collect",
                     "click and collect", "abholung im markt", "im markt abholbar")),
)
# Webhook-Alarme: ein Versuch plus ein Retry, danach ist der Kanal fuer diesen
# Treffer erledigt. App und Dienst laufen in getrennten Prozessen; der Anspruch
# auf eine Meldung steht deshalb in einer gemeinsamen Datei, der Prozess-Cache
# ist nur der Rueckfall, wenn die Datei nicht schreibbar ist.
WEBHOOK_TIMEOUT = 8
WEBHOOK_COOLDOWN = 600
WEBHOOK_DEDUPE_FILE = "ps5pro_webhook_dedupe.json"
# Letzte Zustellung (ok oder Fehler) - die Quelle fuer die Anzeige in SETUP.
WEBHOOK_STATUS_FILE = "ps5pro_webhook_status.json"
WEBHOOK_PRESETS = ("ntfy","telegram","discord","generisch")
# Shops, die fuer den Schnell-Modus zuerst geprueft werden. Alle Namen muessen
# in HAENDLER vorkommen; unbekannte werden ignoriert.
HOT_SHOPS = ["Amazon DE","MediaMarkt DE","Saturn DE","Otto DE",
             "Cyberport DE","Coolblue DE"]
# ── Schneller JSON-LD-Pfad ──────────────────────────────────────────
# Diese Shops liefern Preis und Verfuegbarkeit in einem Product-/BuyAction-
# JSON-LD-Block in den ersten ~200 KB der Produktseite. Dann reicht ein
# Teilabruf, der danach abbricht; der Rest der Seite wird nicht geladen.
# Das ist derselbe oeffentliche GET wie bisher - kein separater API-Pfad,
# keine Umgehung. Shops ohne belegten Block bleiben beim HTML-Pfad.
#   MediaMarkt/Saturn: BuyAction.object (ProductGroup) bei ~3,5 KB
#   PS Direct DE/AT:   Product bei ~33 KB (nach dem Redirect); 64 KB genuegen
#   Alternate DE:      Product bei ~7 KB
FAST_JSON_SHOPS = frozenset(("MediaMarkt DE", "Saturn DE",
                             "PS Direct DE", "PS Direct AT",
                             "Alternate DE"))
FAST_JSON_BYTES = 192 * 1024
# PS Direct braucht den grossen Puffer nicht: Der Product-Block steht bei
# ~33 KB. 64 KB sind rund doppelt so viel Luft und sparen den Seitenrest.
FAST_JSON_64_SHOPS = frozenset(("PS Direct DE", "PS Direct AT"))
FAST_JSON_BYTES_PSDIRECT = 64 * 1024


def fast_json_limit(name):
    """Byte-Grenze des JSON-LD-Teilabrufs; PS Direct kommt mit 64 KB aus."""
    return (FAST_JSON_BYTES_PSDIRECT if str(name or "") in FAST_JSON_64_SHOPS
            else FAST_JSON_BYTES)
# ── Live-Taktung ────────────────────────────────────────────────────
# "Live" heisst hier nicht Push (kein Shop bietet einen Kanal), sondern:
# faellige Shops in kurzen Runden. Ein Shop, der zuletzt kaufbar war, wird
# alle 30 s geprueft, ein stiller alle 4 Minuten, ein gestoerter erst nach
# der Ruhepause. Das Drehbuch steht in docs/RELEASE_1_5.md, Abschnitt 2.
LIVE_TAKT = 20              # Sekunden zwischen zwei Live-Runden (Vordergrund)
LIVE_TAKT_MOBIL = 60        # ohne WLAN: seltener, aber nicht aus
LIVE_HEISS_S = 30           # letzter Zustand kaufbar -> dran bleiben
LIVE_NORMAL_S = 240         # unauffaellig -> 4 Minuten
LIVE_GESTOERT_S = 720       # Fehlerserie -> 12 Minuten
LIVE_RUHE_S = 600           # Circuit Breaker nach Bot-Schutz/Rate-Limit
LIVE_JITTER = 0.2           # +/- 20 %, damit nicht alle gleichzeitig aufschlagen
LIVE_BUDGET = 40            # Obergrenze Requests pro Minute im Vordergrund
# Aus dem Minutenbudget und dem Takt folgt die Rundengroesse (40 / 3 Runden).
LIVE_RUNDE_MAX = 12
LIVE_RUNDE_FENSTER = 6      # 10-s-Runden: 6 * 6 = 36 < 40 Requests/Minute
# ── Drop-Fenster ────────────────────────────────────────────────────
# Nur belegte Zeiten eintragen - geraten wird hier nichts. Zeiten sind lokale
# Ortszeit, minutengenau, Ende inklusive. Herkunft, Stand 17.11.2026:
#
#   * PlayStation Direct: Sony schaltet Kontingente "in unregelmaessigen
#     Abstaenden" frei (merkur.de, 10.11.2026). Der Stempel-Feed eines
#     Ueberwachungsdienstes zeigt Freischaltungen ueber den Tag verteilt
#     (bestell.bar, Produktseite PS5 Pro: 17.11. 09:31 Uhr, 13.11. 10:28-10:35
#     Uhr, jeweils "1 Min. verfuegbar"); Community-Beobachtungen streuen von
#     08:57 bis 17:36 Uhr (foraum.de, 11.11.2026). Belegt ist also ein breites
#     Tagesfenster, KEINE feste 10-Uhr-Zeit. Ein frueheres Fenster
#     09:50-10:25 war Annahme aus dem PS5-Start 2020 und liess den ganzen
#     Nachmittag unbeobachtet.
#   * MediaMarkt/Saturn: Presse und Leitfaeden nennen nur "Schuebe" ohne
#     Uhrzeit (bestell.bar-Leitfaden; pcgames.de, 22.09.2026: "hatten
#     zwischendurch immer wieder Kontingente"). Fuer sie ist kein Zeitfenster
#     belegbar - deshalb bewusst keins: lieber der normale Takt als 10 s rund
#     um die Uhr.
#
# Ein Fenster ist eine Wahrscheinlichkeit, keine Garantie: ausserhalb bleibt
# der Shop im normalen Takt und wird nicht ignoriert.
LIVE_FENSTER_S = 10         # Takt innerhalb eines Drop-Fensters
LIVE_TAKT_FENSTER = 10      # Rundentakt, solange ein Fenster offen ist
DROP_FENSTER = {
    "PS Direct DE": ((9, 0, 18, 0),),
    "PS Direct AT": ((9, 0, 18, 0),),
}
# Gelernte Fenster aus den Check-Zeilen der Waechter-Logs. Ohne ausreichende
# Daten bleibt der Default oben aktiv; ein einzelner Treffer um 03:00 darf
# kein dauerhaftes Nachtband erzeugen.
DROP_FENSTER_LERN_FILE = "ps5pro_drop_fenster.json"
DROP_FENSTER_MIN_HITS = 6
DROP_FENSTER_MIN_TAGE = 2
DROP_FENSTER_MAX_BAENDER = 3
DROP_FENSTER_STUNDE_MIN = 2
_DROP_FENSTER_GELERNT = {}
# ── Hintergrund-Hot-Shop ────────────────────────────────────────────
# Im belegten PS-Direct-Fenster prueft der Dienst diese zwei Shops zusaetzlich
# alle 45 s; die volle Runde bleibt bei 15 Minuten. Ausserhalb des Fensters
# gibt es keine Extra-Abrufe, und eine Sperre schaltet den Hot-Takt ab.
BG_HOT_SHOPS = ("PS Direct DE", "PS Direct AT")
BG_HOT_TAKT = 45
BG_STATUS_FILE = "ps5pro_bg.json"
HEALTH_FILE = "ps5pro_health.json"
# Letzte Pruefungen je Shop fuer die Zuordnung verpasster Fenster:
# Zeit, Status, Fehlertext und Dauer. Klein halten, die Datei wird oft
# geschrieben und enthaelt nur lokale Diagnose, keinen Verlauf fuer immer.
HEALTH_VERLAUF_MAX = 30
CRASH_FILE = "ps5pro_crash.log"
SHOP_CONFIG_FILE = "ps5pro_shop_config.json"
SHOP_CONFIG_URL = "https://raw.githubusercontent.com/xsensenmannx/PS5PRoAgent/main/shop_config.json"
SHOP_CONFIG_MAX_BYTES = 128 * 1024
SHOP_CONFIG_MAX_ALTER = 86400
SHOP_CONFIG_MAX_URLS = 3
SHOP_CONFIG_MAX_MARKER = 120
SHOP_CONFIG_MAX_PRICE_MARKER = 160
SHOP_CONFIG_MAX_MARKERS = 24

# ── Händler ─────────────────────────────────────────────────────────
def _h(n,l,u): return {"name":n,"land":l,"urls":[u]}
HAENDLER = [
    # Die alte direct.playstation.com-URL leitet seit Oktober 2026 per 301
    # auf playstation.com/de-de/ps5/ps5-pro/buy-now/ um. Das Ziel direkt
    # abrufen spart pro Pruefung einen Request und eine Redirect-Runde.
    # Geprueft 20.11.2026: 200 ohne Redirect, Canonical und og:url zeigen
    # auf genau diese URL, Product-JSON-LD mit 899,99 EUR und OutOfStock.
    _h("PS Direct DE","DE","https://www.playstation.com/de-de/ps5/ps5-pro/buy-now/"),
    _h("Amazon DE","DE","https://www.amazon.de/dp/B0FRYBZR91"),
    _h("MediaMarkt DE","DE","https://www.mediamarkt.de/de/product/_sony-playstationr5-pro-2-tb-konsole-3018022.html"),
    _h("Saturn DE","DE","https://www.saturn.de/de/product/_sony-playstationr5-pro-2-tb-konsole-3018022.html"),
    _h("Alternate DE","DE","https://www.alternate.de/Sony-Interactive-Entertainment/PlayStation-5-Pro-2-TB-E-Chassis-Spielkonsole/html/product/100160951"),
    _h("Otto DE","DE","https://www.otto.de/suche/playstation-5-pro-2tb/"),
    _h("Cyberport DE","DE","https://www.cyberport.de/?query=playstation+5+pro+2tb"),
    _h("Euronics","DE","https://www.euronics.de/search?q=playstation+5+pro+2tb"),
    _h("Expert","DE","https://www.expert.de/shop/suche?q=playstation+5+pro+2tb"),
    _h("Mueller","DE","https://www.mueller.de/suche/?q=playstation+5+pro+konsole"),
    _h("Notebooksbilliger","DE","https://www.notebooksbilliger.de/produkte/playstation+5+pro+2tb"),
    _h("Coolblue DE","DE","https://www.coolblue.de/suche?query=playstation+5+pro+2tb"),
    _h("Conrad DE","DE","https://www.conrad.de/de/search.html?search=playstation+5+pro+2tb"),
    _h("Kaufland","DE","https://www.kaufland.de/s/?search_value=playstation+5+pro+2tb"),
    _h("GameStop DE","DE","https://www.gamestop.de/search?q=playstation+5+pro+konsole"),
    _h("Proshop DE","DE","https://www.proshop.de/Search?s=playstation+5+pro+2tb"),
    _h("Computeruniverse","DE","https://www.computeruniverse.net/de/search?q=playstation+5+pro+2tb"),
    _h("Galaxus DE","DE","https://www.galaxus.de/de/search?q=playstation+5+pro+2tb"),
    _h("Alza DE","DE","https://www.alza.de/search.htm?exps=playstation+5+pro+2tb"),
    _h("Spielekauf.de","DE","https://www.spielekauf.de/ps5/konsolen/pro/"),
    _h("Geizhals DE","DE","https://geizhals.de/sony-playstation-5-pro-2tb-weiss-a3298140.html"),
    _h("PS Direct AT","AT","https://www.playstation.com/de-at/ps5/ps5-pro/buy-now/"),
    _h("MediaMarkt AT","AT","https://www.mediamarkt.at/de/product/_sony-playstationr5-pro-2-tb-2049935.html"),
    _h("Saturn AT","AT","https://www.saturn.at/de/search.html?query=playstation+5+pro+2tb"),
    _h("Libro AT","AT","https://www.libro.at/suche?q=playstation+5+pro+konsole"),
    _h("Alza AT","AT","https://www.alza.at/search.htm?exps=playstation+5+pro+2tb"),
    _h("Cyberport AT","AT","https://www.cyberport.at/?query=playstation+5+pro+2tb"),
    _h("Hartlauer AT","AT","https://www.hartlauer.at/search?q=playstation+5+pro+konsole"),
    _h("Electronic4you","AT","https://www.electronic4you.at/suche?q=playstation+5+pro+konsole"),
    _h("Coolblue AT","AT","https://www.coolblue.at/suche?query=playstation+5+pro+2tb"),
    _h("Conrad AT","AT","https://www.conrad.at/de/search.html?search=playstation+5+pro+2tb"),
    _h("Quelle AT","AT","https://www.quelle.at/suche?q=playstation+5+pro+konsole"),
    _h("Universal AT","AT","https://www.universal.at/suche?q=playstation+5+pro+konsole"),
    # Ersatz fuer "Otto AT": www.otto.at gehoert OTTO Immobilien, der Haendler
    # OTTO hat keinen AT-Shop. e-tec ist ein oesterreichischer Haendler mit
    # eigener Produktseite (JSON-LD, gemessen 17.11.2026).
    _h("e-tec AT","AT","https://www.e-tec.at/de/shop/produkt/142611/sony-playstation-5-pro-digital-2tb-weiss-e-chassis.html"),
    _h("GameStop AT","AT","https://www.gamestop.at/search?q=playstation+5+pro+konsole"),
    _h("Proshop AT","AT","https://www.proshop.at/Search?s=playstation+5+pro+2tb"),
    _h("Amazon AT","AT","https://www.amazon.at/dp/B0FRYBZR91"),
    _h("Gameware AT","AT","https://www.gameware.at/suche?q=playstation+5+pro+konsole"),
    _h("shöpping.at","AT","https://www.shoepping.at/suche?q=playstation+5+pro+2tb"),
    _h("Geizhals AT","AT","https://geizhals.at/sony-playstation-5-pro-2tb-weiss-a3298140.html"),
    _h("Computerexpert AT","AT","https://shop.computerexpert.at/suche?q=playstation+5+pro+2tb"),
    _h("Aetka DE","DE","https://aetka.de/suche?q=playstation+5+pro+2tb"),
]

# Unveraenderliche Basis fuer Remote-Overrides. So kann eine spaetere
# Konfiguration eine URL oder Regel wieder entfernen, statt nur zu ueberschreiben.
HAENDLER_BASIS = {h["name"]: list(h["urls"]) for h in HAENDLER}

def _host(u):
    try:
        p=urlparse(str(u))
        return (p.hostname or "").lower()
    except Exception: return ""

def _erlaubte_hosts():
    # Bewusst aus der unveraenderlichen Basis: Eine bereits angewendete
    # Remote-Datei darf den erlaubten Host-Kreis nicht erweitern.
    return {_host(u) for urls in HAENDLER_BASIS.values() for u in urls if _host(u)}

def _sauber_marker(v, max_len, erlaube_leer=False):
    """Ein literaler Marker - keine Regexe, kein Code, keine Steuerzeichen."""
    if not isinstance(v,str) or len(v)>max_len: return None
    if not erlaube_leer and not v.strip(): return None
    if any(ord(c)<32 or 127<=ord(c)<=159 for c in v): return None
    return v

def _validiere_url(u, erlaubt):
    """Nur absolute HTTPS-URLs auf bereits eingebauten Shop-Hosts."""
    if not isinstance(u,str) or not (1<=len(u)<=500): return False
    if any(ord(c)<32 or 127<=ord(c)<=159 or c.isspace() or c=="\\" for c in u): return False
    try:
        p=urlparse(u)
        port=p.port
        hostname=(p.hostname or "").lower()
    except (TypeError,ValueError,UnicodeError): return False
    if p.scheme!="https" or not hostname: return False
    if port not in (None,443): return False
    if p.username or p.password or p.fragment: return False
    if hostname not in erlaubt: return False
    return True

def _validiere_parser(parser):
    """Validiert die deklarativen Parser-Regeln einer Shop-Konfiguration.

    Bewusst keine freien Regexe: Ein ReDoS-Muster aus einer Remote-Datei
    koennte den Scan-Thread und die UI blockieren. Die Regeln bestehen nur aus
    begrenzten literalen Markern; die Preisfelder bilden ein Paar, zwischen dem
    der vorhandene, getestete Preisparser laeuft.
    """
    if not isinstance(parser,dict) or not parser: return None
    erlaubt={"price_before","price_after","in_stock","out_of_stock",
             "preorder","immediate"}
    if set(parser)-erlaubt: return None
    out={}
    before=parser.get("price_before"); after=parser.get("price_after")
    if (before is None)!=(after is None): return None
    if before is not None:
        before=_sauber_marker(before,SHOP_CONFIG_MAX_PRICE_MARKER)
        after=_sauber_marker(after,SHOP_CONFIG_MAX_PRICE_MARKER)
        if before is None or after is None or before==after: return None
        out["price_before"]=before; out["price_after"]=after
    gesamt=0
    for key in ("in_stock","out_of_stock","preorder","immediate"):
        if key not in parser: continue
        liste=parser[key]
        if not isinstance(liste,list) or not (1<=len(liste)<=8): return None
        sauber=[]; gesehen=set()
        for marker in liste:
            marker=_sauber_marker(marker,SHOP_CONFIG_MAX_MARKER)
            if marker is None: return None
            norm=marker.lower()
            if norm in gesehen: return None
            gesehen.add(norm); sauber.append(marker)
        gesamt+=len(sauber)
        if gesamt>SHOP_CONFIG_MAX_MARKERS: return None
        out[key]=sauber
    return out or None

def validiere_shop_config(data):
    """Validiert Remote-URLs und Parser-Regeln streng und vollstaendig.

    Schema 1 bleibt kompatibel: alte Clients lesen weiterhin nur `urls`, neue
    Clients duerfen zusaetzlich ein optionales `parser`-Objekt auswerten. Bei
    einem einzigen Fehler wird die gesamte Datei verworfen; die eingebaute
    Haendlerliste bleibt dann aktiv.
    """
    if not isinstance(data,dict): return None
    if set(data)-{"schema","updated","shops"}: return None
    if type(data.get("schema")) is not int or data.get("schema")!=1: return None
    if "updated" in data and _sauber_marker(data["updated"],40) is None: return None
    shops=data.get("shops")
    if not isinstance(shops,dict) or len(shops)>len(HAENDLER): return None
    namen={h["name"] for h in HAENDLER}; erlaubt=_erlaubte_hosts()
    out={}
    for name,eintrag in shops.items():
        if not isinstance(name,str) or name not in namen: return None
        parser=None
        if isinstance(eintrag,dict):
            if set(eintrag)-{"urls","parser"}: return None
            urls=eintrag.get("urls")
            if "parser" in eintrag:
                parser=_validiere_parser(eintrag.get("parser"))
                if parser is None: return None
            if urls is None and parser is None: return None
        else:
            urls=eintrag
        if isinstance(urls,str): urls=[urls]
        sauber=[]
        if urls is not None:
            if not isinstance(urls,list) or not (1<=len(urls)<=SHOP_CONFIG_MAX_URLS): return None
            for u in urls:
                if not _validiere_url(u,erlaubt): return None
                if u in sauber: return None
                sauber.append(u)
        eintrag_neu={}
        if sauber: eintrag_neu["urls"]=sauber
        if parser is not None: eintrag_neu["parser"]=parser
        out[name]=eintrag_neu
    return out

def _cache_fuer_urls_loeschen(urls):
    """Nach einer Regel-/URL-Aenderung darf ein alter 304-Treffer nicht gelten."""
    try:
        cache=http_cache()
        for u in set(urls): cache.drop(u)
    except Exception: pass

def wende_shop_config(shops):
    """Wendet Overrides an und stellt entfernte Overrides auf die Basis zurueck.

    Die Konfiguration ist autoritativ: fehlt ein Shop oder ein Feld, gilt wieder
    die eingebaute URL bzw. der eingebaute Parser. Namen, Laender und Anzahl der
    Haendler bleiben unveraendert.
    """
    if not isinstance(shops,dict): return 0
    by={h["name"]:h for h in HAENDLER}; n=0
    for name,h in by.items():
        alt_urls=list(h.get("urls") or [])
        alt_parser=h.get("parser")
        h["urls"]=list(HAENDLER_BASIS.get(name,alt_urls))
        h.pop("parser",None)
        eintrag=shops.get(name)
        if isinstance(eintrag,dict):
            if eintrag.get("urls"): h["urls"]=list(eintrag["urls"])
            if isinstance(eintrag.get("parser"),dict): h["parser"]=dict(eintrag["parser"])
            n+=1
        if h["urls"]!=alt_urls or h.get("parser")!=alt_parser:
            _cache_fuer_urls_loeschen(set(alt_urls)|set(h["urls"]))
    return n

def lade_shop_config_datei(pfad):
    """Explizite Konfigurationsdatei laden (z. B. die mitgelieferte)."""
    try:
        with open(pfad,"r",encoding="utf-8") as f:
            d=json.load(f)
        shops=validiere_shop_config(d)
        return wende_shop_config(shops) if shops is not None else 0
    except Exception: return 0

def lade_shop_config():
    """Lokalen Cache laden; ohne Cache bleibt die eingebaute Liste aktiv."""
    try:
        with open(os.path.join(_data_dir(),SHOP_CONFIG_FILE),"r",encoding="utf-8") as f:
            d=json.load(f)
        shops=validiere_shop_config(d.get("config") if isinstance(d,dict) else None)
        return wende_shop_config(shops) if shops is not None else 0
    except Exception: return 0

def aktualisiere_shop_config(force=False):
    """Einmal pro Tag die veroeffentlichte URL-Liste holen (ETag/304 inklusive)."""
    pfad=os.path.join(_data_dir(),SHOP_CONFIG_FILE)
    cached=None
    try:
        with open(pfad,"r",encoding="utf-8") as f: cached=json.load(f)
        ts=float(cached.get("ts") or 0)
        if not force and time.time()-ts<SHOP_CONFIG_MAX_ALTER:
            shops=validiere_shop_config(cached.get("config"))
            return wende_shop_config(shops) if shops is not None else 0
    except Exception: pass
    try:
        html,_u,_cached,_meta=fetch_mit_cache([SHOP_CONFIG_URL])
        if not html or len(html)>SHOP_CONFIG_MAX_BYTES: raise ValueError("Config zu gross")
        data=json.loads(html); shops=validiere_shop_config(data)
        if shops is None: raise ValueError("Config ungueltig")
        tmp=pfad+".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump({"ts":time.time(),"config":data},f,ensure_ascii=False)
        os.replace(tmp,pfad)
        return wende_shop_config(shops)
    except Exception:
        if isinstance(cached,dict):
            shops=validiere_shop_config(cached.get("config"))
            if shops is not None: return wende_shop_config(shops)
        return 0

UA_PROFILES = [
    {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
    {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"},
    {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
]
BASE_HEADERS = {"Accept":"text/html,application/xhtml+xml,*/*;q=0.9",
                "Accept-Language":"de-DE,de;q=0.9,en;q=0.8","Upgrade-Insecure-Requests":"1"}
REFERERS = ["https://www.google.de/","https://www.google.at/","https://duckduckgo.com/"]
CHALLENGE_PATTERNS = ["just a moment","checking your browser","pardon our interruption",
    "unusual traffic","verify you are human","access denied","cf-challenge",
    "ddos protection","captcha","attention required",
    # Kasada (Otto) antwortet auf 4xx mit einem KPSDK-Fingerprint-Script statt
    # einer Seite; Cloudflare liefert cf-chl/_cf_chl_opt. Ohne diese Marker
    # stand bei Otto "HTTP 400" - das sieht nach kaputtem Parser aus, ist aber
    # Bot-Schutz (gemessen 17.11.2026, otto.de/suche und otto.de/p).
    "kpsdk","cf-chl","_cf_chl_opt","cdn-cgi/challenge-platform"]
AUSVERKAUFT = ["nicht verfügbar","derzeit nicht verfügbar","ausverkauft","out of stock",
    "bald wieder verfügbar","nicht auf lager","liefertermin unbekannt","sold out",
    "currently unavailable","nicht bestellbar"]
POSITIV = ["in den warenkorb","add to cart","jetzt kaufen","buy now","jetzt bestellen",
    "lieferung in","auf lager","sofort lieferbar","in stock","available","jetzt vorbestellen"]
PRODUKT_MUSTER = [re.compile(r"playstation[\s\-®™]*5[\s\-®™]*pro\b",re.I),
                  re.compile(r"\bps5[\s\-®™]*pro\b",re.I)]
PRODUKT_2TB = re.compile(r"\b2\s*(?:tb|terabyte)\b",re.I)
PRODUKT_AUSSCHLUSS = ["dualsense edge","edge controller","ps portal","portal remote",
    "pulse headset","pulse explore","psvr2","vr2 headset","faceplate","face plate",
    "disc drive","laufwerk","zubehör","zubehoer"]
VORBESTELL_MUSTER = ["vorbestell","vorbestellung","preorder","pre-order","backorder",
                     "back-order","reservier"]
GEBRAUCHT_MUSTER = ["usedcondition","used condition","refurbished","refurb",
                    "gebraucht","generalüberholt","generalueberholt","b-ware","b ware"]


def _name_ist_konsole(name):
    """Nennt dieser Produktname die PS5 Pro 2 TB - ohne Zubehoermarker?"""
    if not any(rx.search(name) for rx in PRODUKT_MUSTER): return False
    if not PRODUKT_2TB.search(name): return False
    low = name.lower()
    return not any(a in low for a in PRODUKT_AUSSCHLUSS)

def format_preis(p):
    return "{:,.2f}".format(p).replace(",","X").replace(".",",").replace("X",".")+" €"

def parse_preis_str(s):
    if s is None: return None
    s = re.sub(r"&nbsp;|\s|€|EUR|\$|£|USD|GBP","",str(s).strip(),flags=re.I)
    # Shops schreiben "799,00 €*", "(799,00 €)", "1.299,–" oder "799,-".
    # Fuer den Preis zaehlen nur Ziffern, Punkt, Komma und Bindestrich - Sternchen,
    # Klammern, Fuellwoerter und der Halbgeviertstrich fliegen raus. Ohne das landete
    # eine voellig normale Preisangabe mit Fussnote als "PREIS OFFEN".
    s = s.replace("–","-").replace("—","-")
    s = re.sub(r"[^0-9.,\-]","",s)
    if not s: return None
    # "799,-" / "1.299,--" = ganze Euro ohne Nachkommastellen
    m = re.match(r"^(\d{1,3}(?:\.\d{3})+|\d+),-+$",s)
    if m:
        try: return float(m.group(1).replace(".",""))
        except ValueError: pass
    # Komma ist das Dezimaltrennzeichen - mit oder ohne Tausenderpunkt.
    # "1.234,56" und "1234,56" (vierstellig, ohne Punkt) landen hier beide richtig.
    m = re.match(r"^(\d{1,3}(?:\.\d{3})+|\d+),(\d{1,2})$",s)
    if m:
        try: return float(m.group(1).replace(".","")+"."+m.group(2))
        except ValueError: pass
    # "1.099" = Tausenderpunkt ohne Nachkommastellen. Nicht mit "1.5" verwechseln:
    # die Gruppen muessen exakt drei Ziffern haben.
    m = re.match(r"^(\d{1,3}(?:\.\d{3})+)$",s)
    if m:
        try: return float(m.group(1).replace(".",""))
        except ValueError: pass
    try: return float(s.replace(",",""))
    except ValueError: return None

def extract_jsonld(html):
    out=[]
    for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                          html,re.DOTALL|re.I):
        try:
            raw=m.group(1).strip()
            if raw: out.append(json.loads(raw))
        except Exception: continue
    return out

def walk_products(node, acc):
    if isinstance(node,dict):
        t=node.get("@type"); types=t if isinstance(t,list) else [t] if t else []
        # ProductGroup deckt MediaMarkt/Saturn ab: Dort steht das Produkt
        # als BuyAction.object, nicht als eigenstaendiges Product.
        if "Product" in types or "ProductGroup" in types: acc.append(node)
        for v in node.values(): walk_products(v,acc)
    elif isinstance(node,list):
        for i in node: walk_products(i,acc)

def _condition_norm(v):
    s=str(v or "").lower()
    if "used" in s: return "used"
    if "refurb" in s: return "refurbished"
    if "damaged" in s: return "damaged"
    if "new" in s: return "new"
    return None

def _seller_name(v):
    if isinstance(v,dict): return str(v.get("name") or "").strip()
    if isinstance(v,str): return v.strip()
    return ""

def availability_state(av):
    """schema.org-Verfuegbarkeit auf die Zustaende reduzieren, die zaehlen.

    ``OnlineOnly`` und ``LimitedAvailability`` sind kaufbar wie ``InStock``
    und werden dort eingereiht; ``Discontinued`` ist ausverkauft. Nur
    Marktabholung, Vorbestellung/Nachbestellung und echte Chancen bleiben
    eigene Zustaende.
    """
    a=str(av or "").lower()
    if not a: return None
    if "instoreonly" in a: return "pickup_only"
    if any(k in a for k in ("preorder", "presale")): return "preorder"
    if "backorder" in a: return "backorder"
    if any(k in a for k in ("outofstock", "soldout", "discontinued")): return "sold_out"
    if any(k in a for k in ("instock", "onlineonly", "limited")): return "in_stock"
    return None


def _availability_flags(av):
    """(verfuegbar, sofort) - kompatibel fuer die vorhandenen Aufrufer."""
    state=availability_state(av)
    if state=="in_stock": return True, True
    if state in ("preorder", "backorder") or state in CHANCE_STATES: return True, False
    if state=="sold_out": return False, False
    return None, None


def chance_aus_text(html):
    """Lotterie/Einladung/Marktabholung aus sichtbaren Markern erkennen.

    Bewusst nur sehr spezifische Formulierungen: ``Verlosung`` in einer
    Fusszeile ist selten, ``Gewinnspiel`` dagegen haeufig - deshalb werden
    die Marker nur auf der bereits als PS5-Pro-Seite erkannten Seite geprueft.
    """
    low=(html or "").lower()
    for state, muster in CHANCE_PATTERNS:
        if any(m in low for m in muster): return state
    return None

def _offer_specs(off):
    """priceSpecification kann ein Objekt oder eine Liste sein."""
    specs = off.get("priceSpecification") if isinstance(off, dict) else None
    if isinstance(specs, dict): return [specs]
    if isinstance(specs, list): return [s for s in specs if isinstance(s, dict)]
    return []


def _offer_preis(off):
    """Preis aus Offer, AggregateOffer oder verschachtelter priceSpecification."""
    if not isinstance(off, dict): return None
    for key in ("price", "lowPrice"):
        p = parse_preis_str(off.get(key))
        if p is not None and MIN_PREIS <= p <= 5000: return p
    for spec in _offer_specs(off):
        p = parse_preis_str(spec.get("price") or spec.get("lowPrice"))
        if p is not None and MIN_PREIS <= p <= 5000: return p
    return None


def _offer_waehrung(off):
    """Leere Waehrung erlauben, fremde Waehrungen aber nicht als Euro zaehlen."""
    if not isinstance(off, dict): return ""
    for quelle in [off] + _offer_specs(off):
        c = quelle.get("priceCurrency")
        if c: return str(c).strip().upper()
    return ""


def _offer_verfuegbarkeit(off):
    if not isinstance(off, dict): return ""
    for quelle in [off] + _offer_specs(off):
        a = quelle.get("availability")
        if a: return str(a)
    return ""


def extract_structured(html):
    res={"ist_konsole":False,"preis":None,"verfuegbar":None,
         "signal":"jsonld","condition":None,"seller":None,
         "verfuegbarkeit":None,"sofort":None,"state":None,
         "gtin":None,"sku":None,"bundle":False,"produkt_url":None}
    try: jl=extract_jsonld(html)
    except Exception: jl=[]
    prods=[]
    for j in jl: walk_products(j,prods)
    for p in prods:
        name=str(p.get("name",""))
        if not _name_ist_konsole(name): continue
        if BUNDLE_MUSTER.search(name):
            res["bundle"]=True
            continue
        res["ist_konsole"]=True
        # Eigene Produktadresse aus dem Datensatz: der Link soll auf das
        # Angebot zeigen, nicht auf die Suchseite, ueber die gescannt wurde.
        eigene=str(p.get("url") or "").strip()
        if eigene.startswith("http") and not res["produkt_url"]:
            res["produkt_url"]=eigene[:400]
        # GTIN/EAN oder SKU sind der stabilste Produktbeweis. Der Name bleibt
        # fuer Shops ohne strukturierte Daten der Fallback.
        for key in ("gtin13", "gtin12", "gtin14", "gtin", "sku", "mpn"):
            wert=p.get(key)
            if wert and not res["gtin"]:
                res["gtin"]=str(wert).strip()[:40]
            if key == "sku" and wert and not res["sku"]:
                res["sku"]=str(wert).strip()[:60]
        off=p.get("offers")
        offers=off if isinstance(off,list) else [off]
        # Bei mehreren Angeboten gewinnt das guenstigste neue Angebot; nur
        # wenn es keines gibt, wird Gebrauchtware genommen. So wird ein
        # vorhandenes neues 800-Euro-Angebot nicht von einem alten 500-Euro-
        # Gebrauchtangebot verdraengt.
        neu=None; sonst=None
        for angebot in offers:
            if not isinstance(angebot,dict): continue
            waehrung=_offer_waehrung(angebot)
            if waehrung and waehrung not in ("EUR","€"): continue
            pv=_offer_preis(angebot)
            cond=_condition_norm(angebot.get("itemCondition") or p.get("itemCondition"))
            av=_offer_verfuegbarkeit(angebot)
            seller=(_seller_name(angebot.get("seller")) or _seller_name(p.get("seller")))
            kandidat=(pv,av,cond,seller)
            if pv is not None and not ist_gebraucht(cond):
                if neu is None or pv<neu[0]: neu=kandidat
            elif sonst is None:
                sonst=kandidat
        wahl=neu or sonst
        if wahl:
            pv,av,cond,seller=wahl
            # Plausibilitaet wie bei extract_meta_preis: 0,00 / 1,00 sind
            # Platzhalter aus Shop-Vorlagen und wuerden sonst als Treffer
            # gemeldet (Alarm fuer 0 Euro). Nach oben begrenzt gegen
            # Phantasiewerte aus kaputten Feeds.
            if pv is not None: res["preis"]=pv
            res["verfuegbarkeit"]=av or None
            state=availability_state(av)
            if state: res["state"]=state
            v,sofort=_availability_flags(av)
            if v is not None: res["verfuegbar"]=v
            if sofort is not None: res["sofort"]=sofort
            if cond: res["condition"]=cond
            if seller: res["seller"]=seller
        # Weitere Product-Eintraege ansehen, solange noch kein brauchbarer
        # Preis gefunden wurde: manche Shops liefern erst im zweiten Eintrag
        # ein Angebot (der erste ist dann z. B. eine Variante ohne offers).
        if res["preis"] is not None and not ist_gebraucht(res.get("condition")): break
    return res

# Nur diese beiden Meta-Felder beschreiben laut Spezifikation das Produkt
# *dieser* Seite. `itemprop=price`, `data-price` und ein beliebiges
# `"price":` im Skript stehen dagegen auch auf jeder Produktkarte einer
# Ergebnisseite und sind ohne DOM-Bereich keinem Angebot zuzuordnen.
# Gemessen am 25.11.2026 lieferte keine erreichbare Ergebnisseite ein
# Produkt-Meta; die falschen Preise kamen aus dem Seitentext (Amazon 625,20
# EUR, Geizhals 799,00 EUR, Proshop 702,44 EUR).
META_PREIS_FELDER = (
    r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\']',
)


def extract_meta_preis(html):
    """Preis aus dem Produkt-Meta der Seite (product:price / og:price).

    Eine Euro-Zahl aus dem sichtbaren Text oder aus Kartenmarkup wird bewusst
    nicht genommen: sie gehoerte auf den geprueften Seiten nie zur Konsole,
    sondern zu irgendeinem Artikel der Seite. Fehlt das Feld, bleibt der Preis
    offen und der Scan meldet "Parser: kein Preis".
    """
    for pat in META_PREIS_FELDER:
        try:
            for m in re.finditer(pat, html or "", re.I):
                p = parse_preis_str(m.group(1))
                if p is not None and MIN_PREIS <= p <= 5000: return p
        except re.error: continue
    return None
# Kaufbox-/Preisstruktur als Fingerprint: nur die Reihenfolge der Marker,
# keine Preise, Tokens oder Textinhalte. Aendert ein Shop sein Markup, aendert
# sich der Hash auch dann, wenn der Parser noch einen Preis findet.
KAUFBOX_MARKER = (
    "corePrice_feature_div", "corePriceDisplay_desktop_feature_div",
    "apex_desktop", "priceToPay", "a-price-whole", "a-price-fraction",
    "a-price-symbol", "a-offscreen", "availability", "addToCart",
    "ld+json", 'itemprop="price"', "og:price:amount",
)


def kaufbox_fingerprint(html):
    """Kurzer Hash der Preisstruktur einer bereits geladenen Seite.

    Bewusst nur die Reihenfolge der Marker: Preise, Bestand und Tokens
    wechseln staendig und wuerden jeden Vergleich unbrauchbar machen.
    """
    text = html or ""
    treffer = []
    for marker in KAUFBOX_MARKER:
        pos = text.find(marker)
        if pos >= 0:
            treffer.append((pos, marker))
    if not treffer:
        return None
    treffer.sort()
    roh = "|".join(marker for _, marker in treffer)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:12]


# ── Amazon ───────────────────────────────────────────────────────────
# Amazon liefert kein Product-JSON-LD: gemessen am 17.11.2026 auf amazon.de
# und amazon.at jeweils 0 ld+json-Bloecke, dafuer 2,4 MB HTML. Preis und
# Bestand stehen nur in der Kaufbox. Der generische Preis-Regex griff deshalb
# irgendeine Euro-Zahl der Seite - gemessen 1.488,00 EUR aus einem
# Fremdangebot, waehrend die Kaufbox 1.469,98 EUR zeigte. Dieser Pfad liest
# ausschliesslich innerhalb der Kaufbox und laesst sonst den Preis offen.
AMAZON_HOSTS = ("amazon.de", "amazon.at")
AMAZON_PREIS_ANKER = ('id="corePrice_feature_div"',
                      'id="corePriceDisplay_desktop_feature_div"',
                      'id="apex_desktop"', 'id="buybox"')
AMAZON_BESTAND_ANKER = 'id="availability"'
# Gleiche Plausibilitaetsgrenze wie extract_meta_preis. Der Preisdeckel des
# Scans (default 900 EUR) entscheidet danach ueber hit/expensive; ein eigener
# Amazon-Deckel von 1500 EUR machte aus einem echten 1.837,99-EUR-Angebot
# (26.11.2026) einen Parserfehler ohne Preis.
AMAZON_PREIS_MAX = 5000


def ist_amazon(url):
    host = _host(url)
    return any(host == a or host.endswith("." + a) for a in AMAZON_HOSTS)


def extract_amazon(html):
    """Preis und Bestand aus der Amazon-Kaufbox (kein JSON-LD vorhanden).

    Rueckgabe mit ``None`` fuer alles, was die Seite nicht hergibt - ein
    ausverkaufter oder gesperrter Artikel darf nicht als Preis geraten werden.
    """
    res = {"preis": None, "verfuegbar": None, "state": None}
    text = html or ""
    seg = ""
    for anker in AMAZON_PREIS_ANKER:
        i = text.find(anker)
        if i >= 0:
            seg = text[i:i + 4000]
            break
    if seg:
        p = None
        m = re.search(r'a-offscreen">([^<]{2,24})<', seg)
        if m:
            p = parse_preis_str(m.group(1))
        if p is None:
            # Ohne a-offscreen stehen Ganzzahl und Nachkommateil getrennt.
            ganz = re.search(r'a-price-whole">([\d.]+)', seg)
            bruch = re.search(r'a-price-fraction">(\d{1,2})', seg)
            if ganz:
                p = parse_preis_str(ganz.group(1).replace(".", "") + ","
                                    + (bruch.group(1) if bruch else "00"))
        if p is not None and MIN_PREIS <= p <= AMAZON_PREIS_MAX:
            res["preis"] = p
    i = text.find(AMAZON_BESTAND_ANKER)
    if i >= 0:
        roh = re.sub(r"<[^>]+>", " ", text[i:i + 1200])
        v, explizit = _verfuegbarkeit_aus_text(roh)
        if explizit:
            res["verfuegbar"] = v
            res["state"] = "in_stock" if v else "sold_out"
    return res


def _meta_availability_raw(html):
    pats = [
        r"""<meta[^>]+(?:property|name)=["'](?:og|product):availability["'][^>]+content=["']([^"']+)""",
        r"""<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["'](?:og|product):availability["']""",
        r"""<link[^>]+itemprop=["']availability["'][^>]+href=["']([^"']+)""",
        r"""<meta[^>]+itemprop=["']availability["'][^>]+content=["']([^"']+)""",
    ]
    for pat in pats:
        for m in re.finditer(pat,html,re.I):
            return m.group(1)
    return None


def extract_meta_verfuegbarkeit(html):
    """schema.org-Verfuegbarkeit aus Meta-Tags oder Microdata."""
    raw=_meta_availability_raw(html)
    if raw is None: return None,None
    return _availability_flags(raw)


def extract_meta_state(html):
    # None bedeutet: kein verwertbarer Meta-Wert. So kann danach noch der
    # Text-Fallback greifen, statt an einem "unknown" haengen zu bleiben.
    return availability_state(_meta_availability_raw(html))


def detect_challenge(low): return any(p in low for p in CHALLENGE_PATTERNS)

# Drei Namen, die eine Seite fuer ihr Produkt traegt; einer mit
# Konsolennamen genuegt. Die h1 ist noetig fuer Shops, deren <title> nur
# den Shop nennt - und fuer Remote-Parser-Seiten ohne head.
_TITEL_MUSTER = (
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I),
    re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I),
)
_TAG_MUSTER = re.compile(r"<[^>]+>")


def produkt_titel(html):
    """Seitenname aus og:title, <title> und erster h1, entitaetenaufgeloest."""
    namen = []
    for muster in _TITEL_MUSTER:
        treffer = muster.search(html or "")
        if not treffer: continue
        roh = _TAG_MUSTER.sub(" ", treffer.group(1))
        name = " ".join(_html.unescape(roh).split())[:300]
        if name: namen.append(name)
    return namen


def titel_ist_konsole(titel):
    """Nennt dieser Seitenname die PS5 Pro 2 TB - und kein Bundle?"""
    return bool(titel) and _name_ist_konsole(titel) and not BUNDLE_MUSTER.search(titel)


def pruefe_nur_konsole(html, st):
    """Ist diese Seite die Konsole selbst - oder nur ein Zubehoerartikel?

    Frueher genuegte ein Begriff irgendwo im HTML. Damit galten Such- und
    Zubehoerseiten als Treffer, die die Konsole nur erwaehnen; der Preis kam
    dann vom ersten Euro-Betrag der Seite. Jetzt muss ein Seitenname
    (og:title, <title> oder erste h1) die Konsole nennen; ohne Namen bleibt
    die Seite unbestaetigt - lieber ein Treffer weniger als ein Alarm fuer
    den falschen Artikel.
    """
    if st.get("ist_konsole"): return True
    # Nur ein Bundle erkannt: nicht ueber den HTML-Fallback doch als Konsole
    # durchwinken, sonst landet der Bundle-Preis als Konsolen-Treffer.
    if st.get("bundle"): return False
    return any(titel_ist_konsole(t) for t in produkt_titel(html))




def _verfuegbarkeit_aus_text(html):
    """(verfuegbar, explizit) aus sichtbaren Stock-Markern.

    Der bisherige Fallback lieferte ohne jeden Marker pauschal ``True``.
    Fuer die Unterscheidung "echt ausverkauft" vs. "Parser kaputt" ist das
    zu grob: Nur ein gefundener Negativ- oder Positivmarker ist Evidenz.
    ``explizit=False`` bedeutet deshalb "keine Aussage auf der Seite", nicht
    "verfuegbar".
    """
    low=(html or "").lower()
    neg=sum(1 for kw in AUSVERKAUFT if kw in low)
    pos=sum(1 for kw in POSITIV if kw in low)
    if neg>pos: return False,True
    if pos>neg: return True,True
    return True,False

def pruefe_verfuegbar(html, st):
    if st.get("verfuegbar") is not None: return st["verfuegbar"]
    return _verfuegbarkeit_aus_text(html)[0]

def _remote_preis(html, parser):
    """Holt einen Preis zwischen zwei literalen Markern aus der Remote-Regel.

    Kein Regex: nur `str.find` und der bereits getestete Preisparser. Dadurch
    kann eine Remote-Datei weder Code ausfuehren noch den Regex-Engine mit einem
    bösartigen Muster blockieren.
    """
    before=parser.get("price_before") if isinstance(parser,dict) else None
    after=parser.get("price_after") if isinstance(parser,dict) else None
    if not isinstance(html,str) or not before or not after: return None
    pos=0
    for _ in range(32):
        start=html.find(before,pos)
        if start<0: break
        wert_start=start+len(before)
        ende=html.find(after,wert_start)
        if ende<0: break
        if 0<ende-wert_start<=120:
            p=parse_preis_str(html[wert_start:ende])
            if p is not None and MIN_PREIS<=p<=5000: return p
        pos=max(start+1,wert_start)
    return None

def _remote_verfuegbarkeit(html, parser):
    """Deklarative Verfuegbarkeits-Marker; Ausverkauft gewinnt konservativ."""
    if not isinstance(html,str) or not isinstance(parser,dict): return None,None
    keys=("in_stock","out_of_stock","preorder","immediate")
    if not any(parser.get(k) for k in keys): return None,None
    low=html.lower()
    def hat(key):
        marker=parser.get(key)
        return bool(marker) and any(str(m).lower() in low for m in marker)
    aus=hat("out_of_stock"); vor=hat("preorder")
    da=hat("in_stock"); sofort=hat("immediate")
    if aus: return False,False
    if vor: return True,False
    if da:
        return True, True if sofort else None
    if sofort: return None,True
    return None,None

def _remote_state(html, parser):
    """Zustand aus denselben literalen Markern wie die Remote-Verfuegbarkeit."""
    if not isinstance(html,str) or not isinstance(parser,dict): return None
    low=html.lower()
    def hat(key):
        marker=parser.get(key)
        return bool(marker) and any(str(m).lower() in low for m in marker)
    if hat("out_of_stock"): return "sold_out"
    if hat("preorder"): return "preorder"
    if hat("in_stock"): return "in_stock"
    return None

def remote_parser_ergebnis(html, parser):
    """Wendet die optionalen Remote-Regeln auf eine bereits geladene Seite an."""
    out={}
    if not isinstance(parser,dict): return out
    p=_remote_preis(html,parser)
    if p is not None: out["preis"]=p
    v,sofort=_remote_verfuegbarkeit(html,parser)
    if v is not None: out["verfuegbar"]=v
    if sofort is not None: out["sofort"]=sofort
    state=_remote_state(html,parser)
    if state is not None: out["state"]=state
    return out

def ist_sofort_verfuegbar(html):
    """Text-Fallback: Vorbestellung/Backorder ist keine sofortige Verfuegbarkeit."""
    low=html.lower()
    if any(k in low for k in VORBESTELL_MUSTER): return False
    if any(k in low for k in POSITIV): return True
    return None

def ist_gebraucht(condition):
    return str(condition or "").lower() in ("used","refurbished","damaged")

def _marketplace(seller, haendler):
    """Heuristik: ein fremder Verkaeufer ist kein Erstverkauf des Shops."""
    s=re.sub(r"[^a-z0-9]","",str(seller or "").lower())
    h=re.sub(r"[^a-z0-9]","",str(haendler or "").lower())
    if not s: return False
    if s in h or h in s: return False
    return True


def berechne_konfidenz(r):
    """0-100 aus nachvollziehbaren Signalen, keine Zufallszahl.

    Ein ungepruefter Treffer kann hoechstens 60 erreichen; erst der zweite
    Abruf bringt die 40 Punkte fuer ``verify == bestaetigt``. Damit ist die
    Standard-Schwelle 70 ohne Verifikation unerreichbar.
    """
    if not isinstance(r,dict) or r.get("klass") not in ("hit","chance"):
        return 0
    p=r.get("preis")
    if p is None or not preis_plausibel(p): return 0
    punkte=0
    if r.get("verify")=="bestaetigt": punkte+=40
    try:
        if MIN_PREIS<=float(p)<=1100: punkte+=10
    except (TypeError,ValueError): pass
    if r.get("avail_state") not in (None,"unknown") and \
            r.get("stock_source") in ("remote","jsonld","meta","text"):
        punkte+=15
    # Nur belegte Signale zaehlen. Ein unbekannter Zustand oder eine fehlende
    # Frischeangabe darf die Konfidenz nicht kuenstlich auf 100 heben.
    if r.get("condition")=="new": punkte+=10
    if r.get("marketplace") is False: punkte+=10
    if r.get("gtin"): punkte+=5
    if r.get("fresh") is True: punkte+=10
    punkte=min(100,punkte)
    # Ohne zweiten Abruf bleibt es bei 60 - die Schwelle 70 ist dann bewusst
    # nicht erreichbar, auch wenn alle anderen Signale passen.
    if r.get("verify")!="bestaetigt": punkte=min(60,punkte)
    if r.get("klass")=="chance": punkte=min(60,punkte)
    return punkte


def _sichtbarer_text(html):
    """Reduziert HTML auf sichtbaren Text - fuer den kleinen Beleg-Ausschnitt."""
    s=re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>"," ",html or "")
    s=re.sub(r"(?s)<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",s).strip()


def beleg_erzeugen(html, preis, state="unknown"):
    """Kleiner, redigierter Beweis: Preis, Zustand, Zeitstempel und Hash.

    Bewusst kein HTML und keine Tokens: maximal 120 Zeichen sichtbarer Text
    rund um den Preis. Der Hash macht den Ausschnitt spaeter pruefbar.
    """
    text=_sichtbarer_text(html)
    if not text: return None
    kandidaten=[]
    if preis is not None:
        kandidaten=[format_preis(preis).replace(" €",""),
                    ("%.2f"%float(preis)).replace(".",","),
                    str(int(float(preis)))]
    pos=-1
    for k in kandidaten:
        pos=text.find(k)
        if pos>=0: break
    if pos<0:
        for label in ("lager", "verfuegbar", "verfügbar", "lieferbar"):
            pos=text.lower().find(label)
            if pos>=0: break
    if pos<0: pos=0
    ausschnitt=text[max(0,pos-80):pos+100].strip()[:120]
    if not ausschnitt: return None
    return {"ts": datetime.now().isoformat(timespec="seconds"),
            "preis": preis, "state": state, "excerpt": ausschnitt,
            "hash": hashlib.sha256(ausschnitt.encode("utf-8")).hexdigest()[:16]}


class Evidence:
    """Maximal 200 kleine Belege, neueste pro Shop, FIFO bei Ueberlauf."""
    def __init__(self, path=None):
        self.path=path or os.path.join(_data_dir(),EVIDENCE_FILE)
        try:
            with open(self.path,"r",encoding="utf-8") as f:
                data=json.load(f)
            self.data=data if isinstance(data,dict) else {}
        except Exception: self.data={}
    def put(self, haendler, beleg):
        if not haendler or not isinstance(beleg,dict): return False
        self.data[str(haendler)]=dict(beleg)
        if len(self.data)>MAX_BELEGE:
            order=sorted(self.data.items(), key=lambda kv: str(kv[1].get("ts") or ""))
            for name,_ in order[:len(self.data)-MAX_BELEGE]:
                self.data.pop(name,None)
        try:
            tmp=self.path+".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(self.data,f,ensure_ascii=False,indent=1)
            os.replace(tmp,self.path)
            return True
        except Exception: return False
    def get(self, haendler):
        e=self.data.get(str(haendler or ""))
        return dict(e) if isinstance(e,dict) else None

def beleg_speichern(haendler, beleg):
    try: return Evidence().put(haendler,beleg)
    except Exception: return False

def preis_plausibel(preis):
    """Nur Preise, die als PS5-Pro-Preis durchgehen koennen.

    Dieselbe Grenze wie in den Extraktoren: unter ``MIN_PREIS`` ist es kein
    Konsolenpreis, ueber ``PREIS_PLAUSIBEL_MAX`` ein Parser- oder Seitenfehler.
    Das gilt unabhaengig vom gewaehlten Deckel.
    """
    try:
        p=float(preis)
    except (TypeError,ValueError):
        return False
    return MIN_PREIS<=p<=PREIS_PLAUSIBEL_MAX


def preis_guard_grund(preis):
    """Grund, warum ein Preis nicht als plausibel gilt; sonst ``ok``.

    ``nicht_erkannt`` heisst: kein Preis oder kein parsebarer Preis. Die
    Extraktoren verwerfen 0/1 EUR und >5000 EUR bereits; der Waechter zaehlt
    diese Faelle damit trotzdem im Tagesbericht.
    """
    if preis is None:
        return "nicht_erkannt"
    try:
        p=float(preis)
    except (TypeError,ValueError):
        return "nicht_erkannt"
    if p<MIN_PREIS: return "zu_niedrig"
    if p>PREIS_PLAUSIBEL_MAX: return "zu_hoch"
    return "ok"


def classify(v,p,m,state=None):
    if state in CHANCE_STATES: return "chance"
    if state=="sold_out": return "unavail"
    if not v: return "unavail"
    if p is None: return "unknown"
    try: p=float(p)
    except (TypeError,ValueError): return "unknown"
    if not preis_plausibel(p): return "unknown"
    if m is None or p<=m: return "hit"
    return "expensive"


def deckel_wert(v,ersatz=MAX_PREIS):
    """Deckel als Zahl; ``None`` heisst "kein Deckel", Unsinn ergibt ``ersatz``.

    Die Grenze DECKEL_MIN..DECKEL_MAX steht nur hier - App, Dienst und
    Einstellungsdatei pruefen damit dieselbe Regel.
    """
    if v is None: return None
    try: p=float(v)
    except (TypeError,ValueError): return ersatz
    return p if DECKEL_MIN<=p<=DECKEL_MAX else ersatz


def preis_deckel(land,max_preis=None):
    """Preis-Deckel fuer das Land eines Treffers.

    ``max_preis`` ist eine Zahl (gilt fuer alle Laender), ``None`` (Standard
    MAX_PREIS) oder ein Dict je Land; ein Land ohne Eintrag gilt als Standard.
    """
    if not isinstance(max_preis,dict):
        return MAX_PREIS if max_preis is None else deckel_wert(max_preis)
    return deckel_wert(max_preis.get(str(land or "").upper(),MAX_PREIS))


def preis_deckel_aus(settings):
    """Deckel je Land aus den Einstellungen: DE global, AT optional.

    AT erbt den DE-Wert, solange kein eigener gesetzt ist - ohne dass
    bestehende Einstellungen sich aendern. Ein unsinniger AT-Wert erbt
    ebenfalls, statt mit einem stillen Standard zu ueberraschen.
    """
    de=deckel_wert(_setting(settings,"max_preis",MAX_PREIS))
    at=deckel_wert(_setting(settings,"max_preis_at"),de)
    return {"DE":de,"AT":de if at is None else at}

# Toleranz, um die ein beobachteter Regalpreis den Deckel anhebt. PS Direct
# listet die Konsole mit 899,99 EUR; bei Deckel 900 wuerde jede kleine
# Preiserhoehung verfuegbaren Bestand still als "expensive" durchfallen lassen.
SHOP_DECKEL_TOLERANZ = 0.02


def shop_deckel(deckel, beobachtet, toleranz=SHOP_DECKEL_TOLERANZ,
                maximum=DECKEL_MAX):
    """Deckel eines Shops, verankert an seinem beobachteten Regalpreis.

    ``deckel`` bleibt die Untergrenze. Liegt der Shop mit seinem eigenen Preis
    darueber, hebt dieser Preis den Deckel um ``toleranz`` an. ``maximum``
    (``DECKEL_MAX``) verhindert, dass ein Marktplatz-Aufschlag den Deckel
    beliebig hoch zieht; ``None`` (offener Deckel) bleibt offen.
    """
    if deckel is None:
        return None
    basis = deckel_wert(deckel)
    if basis is None:
        return None
    try:
        preis = float(beobachtet)
    except (TypeError, ValueError):
        return basis
    if not preis_plausibel(preis):
        return basis
    try:
        faktor = 1.0 + max(0.0, float(toleranz))
    except (TypeError, ValueError):
        faktor = 1.0
    return min(float(maximum), max(basis, preis * faktor))


def shop_deckel_fuer(land, deckel, eintrag):
    """Deckel fuer einen Shop aus seinem beobachteten Regalpreis.

    Regalpreis ist der Preis, den der Shop selbst fuer die Konsole nennt,
    waehrend sie nicht kaufbar ist (``status == unavail``). Ein
    ``in_stock``-Preis kann einen Marktplatz-Aufschlag tragen und darf den
    Deckel nicht heben, sonst wuerden Scalper-Angebote zu Treffern.
    """
    grenze = preis_deckel(land, deckel)
    if not isinstance(eintrag, dict):
        return grenze
    regal = eintrag.get("regal_preis")
    if regal is None and str(eintrag.get("status") or "") == "unavail":
        regal = eintrag.get("preis")
    return shop_deckel(grenze, regal)

def _read_capped(resp):
    """Liest hoechstens MAX_HTML_BYTES und meldet, ob die Antwort zu gross war."""
    stuecke=[]; gesamt=0
    for stueck in resp.iter_content(65536):
        if not stueck: continue
        gesamt+=len(stueck)
        if gesamt>MAX_HTML_BYTES:
            try: resp.close()
            except Exception: pass
            return None,True
        stuecke.append(stueck)
    return b"".join(stuecke),False


def _read_bis(resp, limit):
    """Liest hoechstens ``limit`` Bytes und schliesst die Antwort danach.

    Fuer den JSON-LD-Teilabruf: Der Block steht am Seitenanfang, der Rest
    (Bewertungen, Empfehlungen, Fusszeile) wird nicht mehr uebertragen.
    Ein Byte mehr wird gelesen, um ``truncated`` ehrlich zu setzen.
    """
    try: ziel=max(1,int(limit))
    except (TypeError,ValueError): ziel=FAST_JSON_BYTES
    stuecke=[]; gesamt=0; roh=b""
    try:
        for stueck in resp.iter_content(65536):
            if not stueck: continue
            rest=ziel+1-gesamt
            if len(stueck)>=rest:
                stuecke.append(stueck[:rest]); gesamt+=rest; break
            stuecke.append(stueck); gesamt+=len(stueck)
    finally:
        try: resp.close()
        except Exception: pass
    roh=b"".join(stuecke)
    if len(roh)>ziel: return roh[:ziel],True
    return roh,False


class HttpCache:
    """ETag/Last-Modified plus das letzte Extraktionsergebnis pro URL.

    Gespeichert wird nur das kompakte Ergebnis (Preis/Verfuegbarkeit), nicht das
    HTML: die Datei bleibt klein und der naechste Scan kann einen 304 direkt
    beantworten, ohne die Seite erneut zu parsen.
    """
    def __init__(self,pfad=None):
        self.path=pfad or os.path.join(_data_dir(),HTTP_CACHE_FILE)
        self._lock=threading.Lock()
        self._dirty=False
        try:
            with open(self.path,"r",encoding="utf-8") as f: data=json.load(f)
            self.data=data if isinstance(data,dict) else {}
        except Exception: self.data={}
    def get(self,u):
        with self._lock:
            e=self.data.get(u)
            return dict(e) if isinstance(e,dict) else None
    def put(self,u,result,etag=None,last_modified=None,persist=True):
        """Ergebnis merken. Waehrend eines Scans reicht persist=False.

        Dann bleibt die Aenderung im Speicher und wird mit ``flush()`` einmal
        am Scan-Ende geschrieben, statt fuer jeden der 42 Shops die komplette
        Cache-Datei neu zu serialisieren.
        """
        with self._lock:
            self.data[u]={"ts":time.time(),"etag":etag,
                           "last_modified":last_modified,"result":result}
            self._dirty=True
            if persist: self._save_locked()
    def drop(self,u):
        with self._lock:
            if self.data.pop(u,None) is not None:
                self._dirty=True
                self._save_locked()
    def flush(self):
        """Offene Cache-Aenderungen einmalig auf Platte schreiben."""
        with self._lock:
            if not self._dirty: return False
            return self._save_locked()
    def _save_locked(self):
        try:
            tmp=self.path+".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(self.data,f,ensure_ascii=False,indent=1)
            os.replace(tmp,self.path)
            self._dirty=False
            return True
        except Exception: return False

_HTTP_CACHE=None
_HTTP_CACHE_LOCK=threading.Lock()

def http_cache():
    global _HTTP_CACHE
    with _HTTP_CACHE_LOCK:
        if _HTTP_CACHE is None: _HTTP_CACHE=HttpCache()
        return _HTTP_CACHE

def reset_http_cache():
    """Nur fuer Tests: naechster Zugriff liest die Datei neu ein."""
    global _HTTP_CACHE
    with _HTTP_CACHE_LOCK: _HTTP_CACHE=None

def flush_http_cache():
    """Gepufferte Cache-Aenderungen einmal pro Scan sichern."""
    try: return http_cache().flush()
    except Exception: return False


class ScanAbgebrochen(Exception):
    """Der Benutzer hat den Scan abgebrochen; Retries und Parser entfallen."""


def _abgebrochen(cancel):
    """True, wenn ein optionales threading.Event gesetzt wurde."""
    try:
        return bool(cancel is not None and cancel.is_set())
    except Exception:
        return False


def _warte(sekunden, cancel):
    """Unterbrechbare Retry-Pause; True bedeutet abgebrochen."""
    if cancel is None:
        time.sleep(sekunden)
        return False
    try:
        return bool(cancel.wait(sekunden))
    except Exception:
        time.sleep(sekunden)
        return _abgebrochen(cancel)


def _retry_after(wert, jetzt=None):
    """Sekunden aus Retry-After (Zahl oder HTTP-Datum), sonst 8."""
    try:
        return max(0, int(float(str(wert).strip())))
    except (TypeError, ValueError):
        pass
    try:
        dt = parsedate_to_datetime(str(wert))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        jetzt = jetzt or datetime.now(timezone.utc)
        if jetzt.tzinfo is None:
            jetzt = jetzt.replace(tzinfo=timezone.utc)
        return max(0, int((dt - jetzt).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return 8


def fehler_klasse(fehler):
    """Netzfehler, die eine Sperre sind, werden wie Bot-Schutz angezeigt."""
    text = str(fehler or "")
    return ("challenge" if text.startswith(("Rate-Limit", "Bot-Schutz", "Bot-Challenge"))
            else "error")


def _try_url(u, att, proxy=None, force=False, limit=None):
    """Eine Anfrage. Rueckgabe (html, fehler, meta).

    meta["not_modified"] signalisiert einen 304. Bedingte Header gehen nur beim
    ersten Versuch mit: ein Cache-Buster im Retry wuerde den Cache ohnehin
    umgehen, und ein 304 auf einen Retry waere wertlos. ``force`` ueberspringt
    die Validatoren komplett - die Verifikation eines Treffers braucht den
    echten aktuellen Stand, keinen 304 aus dem letzten Scan. ``limit`` beendet
    den Abruf nach so vielen dekomprimierten Bytes (JSON-LD-Teilabruf).
    """
    uu=u
    if att>0: uu+=("&" if "?" in uu else "?")+"_cb="+str(int(time.time()*1000))
    ua=UA_PROFILES[att%len(UA_PROFILES)]
    ref=REFERERS[att%len(REFERERS)]
    hd={**BASE_HEADERS,**ua,"Referer":ref}
    meta={"not_modified":False,"etag":None,"last_modified":None}
    # Nur der erste Versuch ist bedingt; der Cache ist prozessweit, weil die
    # Scan-Threads dieselbe Datei teilen und _try_url so kompatibel bleibt.
    cache=http_cache() if (att==0 and not force) else None
    eintrag=cache.get(u) if cache is not None else None
    if eintrag:
        if eintrag.get("etag"): hd["If-None-Match"]=eintrag["etag"]
        if eintrag.get("last_modified"): hd["If-Modified-Since"]=eintrag["last_modified"]
    pr={"http":proxy,"https":proxy} if proxy else None
    try:
        sess=_session()
        if sess is not None:
            r=sess.get(uu,headers=hd,timeout=TIMEOUT,allow_redirects=True,
                       proxies=pr,stream=True)
            meta["etag"]=r.headers.get("ETag"); meta["last_modified"]=r.headers.get("Last-Modified")
            if r.status_code==304:
                meta["not_modified"]=True; r.close(); return None,"HTTP 304",meta
            if r.status_code==429:
                # Nicht hier schlafen: fetch_mit_cache wartet unterbrechbar
                # und entscheidet, ob ein einziger Retry noch sinnvoll ist.
                meta["retry_after"]=_retry_after(r.headers.get("Retry-After"))
                r.close(); return None,"HTTP 429",meta
            if r.status_code>=400:
                # Kasada und Cloudflare verpacken ihre Sperre in eine kurze
                # 4xx-Antwort. Nur bei diesen Codes den Anfang lesen, sonst
                # bleibt es beim reinen Status - und ohne den Blick in den
                # Body hiess es bei Otto "HTTP 400" statt "Bot-Schutz".
                if r.status_code in (400,401,403,451,503):
                    try:
                        kopf=next(r.iter_content(2048),b"").decode(
                            r.encoding or "utf-8",errors="replace")
                    except Exception: kopf=""
                    if kopf and detect_challenge(kopf[:3000].lower()):
                        r.close()
                        return None,"Bot-Schutz (HTTP %d)"%r.status_code,meta
                r.close(); return None,f"HTTP {r.status_code}",meta
            if limit is not None:
                roh,gekuerzt=_read_bis(r,limit)
                meta["partial"]=bool(gekuerzt)
            else:
                roh,zu_gross=_read_capped(r)
                if zu_gross: return None,"Antwort zu gross",meta
                meta["partial"]=False
            meta["bytes"]=len(roh)
            # UTF-8 zuerst: requests faellt fuer text/html ohne charset im
            # Header auf ISO-8859-1 zurueck und zerlegt damit Umlaute (e-tec,
            # gemessen 17.11.2026: "weiÃ" statt "weiß"). Erst wenn striktes
            # UTF-8 scheitert, gilt die deklarierte Kodierung.
            try: return roh.decode("utf-8"),None,meta
            except UnicodeDecodeError: pass
            enc=r.encoding or "utf-8"
            try: return roh.decode(enc,errors="replace"),None,meta
            except LookupError: return roh.decode("utf-8",errors="replace"),None,meta
        req=Request(uu,headers=hd)
        with urlopen(req,timeout=TIMEOUT) as resp:
            meta["etag"]=resp.headers.get("ETag"); meta["last_modified"]=resp.headers.get("Last-Modified")
            if limit is not None:
                roh=resp.read(int(limit)+1)
                meta["partial"]=len(roh)>int(limit)
                if meta["partial"]: roh=roh[:int(limit)]
            else:
                roh=resp.read(MAX_HTML_BYTES+1)
                if len(roh)>MAX_HTML_BYTES: return None,"Antwort zu gross",meta
                meta["partial"]=False
            meta["bytes"]=len(roh)
            return roh.decode("utf-8",errors="replace"),None,meta
    except HTTPError as e:
        # urlopen wirft bei 4xx/5xx; ohne diese Normalisierung greift die
        # 404/410-Abkürzung in fetch_html_multi nie und jeder umgezogene
        # Haendler kostet drei Versuche samt Wartezeit.
        if e.code==304:
            meta["not_modified"]=True
            meta["etag"]=e.headers.get("ETag") if e.headers else None
            meta["last_modified"]=e.headers.get("Last-Modified") if e.headers else None
            return None,"HTTP 304",meta
        if e.code==429:
            meta["retry_after"]=_retry_after(e.headers.get("Retry-After") if e.headers else None)
        return None,f"HTTP {e.code}",meta
    except Exception as e: return None,str(e)[:50],meta

def fetch_mit_cache(urls, cancel=None, force=False, limit=None):
    """Wie fetch_html_multi, liefert zusaetzlich ein 304-Ergebnis aus dem Cache.

    ``cancel`` ist ein optionales threading.Event. Es wird vor jedem Versuch
    und vor jeder Retry-Pause geprueft; ein laufender HTTP-Request selbst kann
    nicht unterbrochen werden, aber danach wird kein weiterer Versuch gestartet.
    ``force`` laedt die Seite ohne ETag/Last-Modified neu (Treffer-Verifikation).
    ``limit`` liest nur den Seitenanfang und beendet die Verbindung danach.
    """
    last=None
    not_modified_gesehen=False
    proxy=os.environ.get("PS5_PROXY","").strip() or None
    cache=http_cache()
    for att in range(3):
        if _abgebrochen(cancel): raise ScanAbgebrochen
        dauerhaft=False
        rate_limited=False
        for u in urls:
            if _abgebrochen(cancel): raise ScanAbgebrochen
            # ``force`` nur weiterreichen, wenn es gesetzt ist: Tests ersetzen
            # _try_url durch ein einfaches Lambda mit drei Argumenten.
            if limit is not None:
                h,e,meta=(_try_url(u,att,proxy,force=True,limit=limit) if force
                          else _try_url(u,att,proxy,limit=limit))
            else:
                h,e,meta=(_try_url(u,att,proxy,force=True) if force
                          else _try_url(u,att,proxy))
            if _abgebrochen(cancel): raise ScanAbgebrochen
            if meta.get("not_modified"):
                not_modified_gesehen=True
                if force:
                    cache.drop(u); last="HTTP 304"; continue
                eintrag=cache.get(u)
                if eintrag and isinstance(eintrag.get("result"),dict):
                    try:
                        alter=time.time()-float(eintrag.get("ts") or 0)
                    except (TypeError,ValueError):
                        alter=CACHE_MAX_ALTER+1
                    if alter>CACHE_MAX_ALTER:
                        # Ein 304 auf einen beliebig alten Stand ist kein
                        # frischer Treffer. Einmal unbedingt neu laden.
                        cache.drop(u); last="HTTP 304 (zu alt)"; continue
                    meta["not_modified_gesehen"]=not_modified_gesehen
                    return "",u,dict(eintrag["result"]),meta
                # Cache-Eintrag geloescht: Validatoren verwerfen und ohne
                # Bedingung erneut laden, statt den Haendler als Fehler zu werten.
                cache.drop(u); last="HTTP 304"; continue
            if h:
                # Nur den Kopf pruefen - h.lower() auf einer 5-MB-Seite kostet
                # unnoetig Zeit und Speicher. Eine Challenge-Seite ist keine
                # temporaere Netzstoerung: kein zweiter Versuch mit anderem UA.
                if detect_challenge(h[:3000].lower()):
                    last="Bot-Challenge"; dauerhaft=True; break
                meta["not_modified_gesehen"]=not_modified_gesehen
                return h,u,None,meta
            last=e
            # Bot-Schutz schon im 4xx-Body erkannt (Kasada/Cloudflare): kein
            # zweiter Versuch mit anderem User-Agent, das waere nur Last.
            if e.startswith("Bot-Schutz"):
                dauerhaft=True; break
            # 429: genau eine Chance, und nur wenn der Server nicht mehr als
            # RETRY_AFTER_MAX verlangt. Die Pause ist ueber STOP abrechbar.
            if e == "HTTP 429":
                last = "Rate-Limit (HTTP 429)"
                try: ra = int(meta.get("retry_after", 8))
                except (TypeError, ValueError): ra = 8
                if att == 0 and ra <= RETRY_AFTER_MAX:
                    if _warte(max(1, ra), cancel): raise ScanAbgebrochen
                    rate_limited=True; break
                dauerhaft=True; break
            # 403/401/451 sind keine temporaeren Aussetzer. Weitere Versuche
            # mit anderem User-Agent oder Cache-Buster waeren nur Last und
            # wuerden eine Bot-Sperre nicht legitim aufheben.
            if e in ("HTTP 403", "HTTP 401", "HTTP 451"):
                last = "Bot-Schutz (HTTP 403)" if e == "HTTP 403" else e
                dauerhaft=True; break
            # 404/410 bleiben bei jedem User-Agent bestehen. Drei Versuche kosten
            # hier nur ~7 s Wartezeit pro umgezogenem Haendler, ohne Chance auf
            # Erfolg; Timeouts/5xx werden dagegen weiter probiert.
            if e in ("HTTP 404","HTTP 410","Antwort zu gross"):
                if len(urls)==1:
                    dauerhaft=True; break
                continue
            # Nach dem letzten Versuch gibt es keinen naechsten Versuch mehr,
            # auf den man warten koennte. Der alte Sleep kostete bei jedem
            # endgueltig fehlgeschlagenen Shop noch einmal bis zu ~6 s.
            if att<2:
                if _warte((0.4,2.0,5.0)[att]+random.uniform(0,1.0), cancel):
                    raise ScanAbgebrochen
        if dauerhaft: break
        if rate_limited: continue
    raise RuntimeError(last or "alle URLs fehlgeschlagen")

def fetch_html_multi(urls, cancel=None):
    """Kompatible Fassung fuer Aufrufer, die nur HTML und URL brauchen."""
    h,u,_cached,_meta=fetch_mit_cache(urls, cancel=cancel)
    return h,u

def _produkt_ziel(produkt_url,ersatz):
    """Link auf das Angebot statt auf die Suchseite.

    Viele Shops sind mit einer Suchadresse konfiguriert; der Treffer zeigte
    deshalb bisher auf die Ergebnisliste. Nennt der Produkt-Datensatz eine
    Adresse auf demselben Host, ist das der bessere Link. Fremde Hosts werden
    nicht uebernommen.
    """
    if isinstance(produkt_url,str) and produkt_url.startswith("http"):
        host=_host(produkt_url)
        if host and host==_host(ersatz): return produkt_url
    return ersatz


def _res(h,preis,klass,dauer,err,final_url=None,signal=None,condition=None,
         seller=None,verfuegbarkeit=None,sofort=None,produkt_url=None,**extra):
    jetzt=datetime.now()
    r={"haendler":h["name"],"url":_produkt_ziel(produkt_url,final_url or h["urls"][0]),
       "land":h["land"],
       "preis":preis,"klass":klass,"dauer":round(dauer,1),
       "zeit":jetzt.strftime("%H:%M:%S"),
       # Der Wechsel wird mit der Zeit des Abrufs journalisiert, nicht erst
       # am Ende einer ganzen Runde. Sonst teilen sich alle Shops denselben
       # spaeten Zeitstempel und der Erfolgs-Feed wirkt traeger als er ist.
       "erkannt":jetzt.isoformat(timespec="seconds"),"fehler":err,
       "signal":signal or "unbekannt","condition":condition,"seller":seller,
       "verfuegbarkeit":verfuegbarkeit,"sofort":sofort}
    r.update(extra)
    return r

def _scan_einen_json(h, cancel=None):
    """Teilabruf mit JSON-LD; ``None`` bedeutet: HTML-Pfad versuchen.

    Der Block steht bei den vorgesehenen Shops in den ersten 192 KB, bei
    PS Direct in den ersten 64 KB. Ist er unvollstaendig, fehlt die
    Verfuegbarkeit oder passt das Produkt nicht, wird bewusst ``None``
    zurueckgegeben - dann laedt der normale Pfad die Seite. Ein Fehler hier
    ist kein Shop-Fehler.
    """
    st=time.time()
    try:
        if _abgebrochen(cancel): raise ScanAbgebrochen
        html,fu,_cached,meta=fetch_mit_cache(
            h["urls"], cancel=cancel, force=True,
            limit=fast_json_limit(h.get("name")))
        if _abgebrochen(cancel): raise ScanAbgebrochen
        if not html:
            return None
        if detect_challenge(html[:3000].lower()):
            return _res(h,None,"challenge",time.time()-st,"Bot-Challenge",fu,
                        avail_state="unknown",stock_source="challenge")
        s=extract_structured(html)
        # Ohne Preis oder ohne ausdrueckliche Verfuegbarkeit ist der
        # Teilabruf keine Entscheidungsgrundlage; der HTML-Pfad sieht mehr.
        if not s.get("ist_konsole") or s.get("preis") is None:
            return None
        if s.get("verfuegbar") is None and s.get("state") is None:
            return None
        p=s["preis"]; state=s.get("state") or "unknown"; v=s.get("verfuegbar")
        if state in CHANCE_STATES: v=True
        res=_res(h,p,classify(v,p,MAX_PREIS,state),time.time()-st,None,fu,
                 produkt_url=s.get("produkt_url"),
                 signal="jsonld",condition=s.get("condition"),
                 seller=s.get("seller"),verfuegbarkeit=s.get("verfuegbarkeit"),
                 sofort=s.get("sofort"),avail_state=state,
                 stock_source="jsonld",gtin=s.get("gtin"),sku=s.get("sku"),
                 bundle=bool(s.get("bundle")),
                 marketplace=_marketplace(s.get("seller"),h["name"]))
        res["fresh"]=True
        res["not_modified"]=bool(meta.get("not_modified_gesehen"))
        res["confidence"]=berechne_konfidenz(res)
        res["bytes"]=int(meta.get("bytes") or 0)
        res["_fast"]=True
        # Ein Beleg entsteht nur fuer echte Treffer/Chancen, wie im HTML-Pfad.
        if res["klass"] in ("hit","chance"):
            try:
                beleg=beleg_erzeugen(html,p,state)
                if beleg:
                    res["beleg"]=beleg
                    beleg_speichern(h["name"],beleg)
            except Exception: pass
        return res
    except ScanAbgebrochen:
        return None
    except Exception as e:
        # Netz-/Sperrfehler nicht als "kein JSON-LD" behandeln: sonst wuerde
        # der HTML-Pfad denselben gesperrten Shop sofort noch einmal abrufen.
        err=str(e)[:60]
        return _res(h,None,fehler_klasse(err),time.time()-st,err,
                    avail_state="unknown",stock_source="error")


def scan_einen(h, cancel=None, force=False):
    """Ein Shop: erst der JSON-LD-Teilabruf, sonst die ganze Seite."""
    if h.get("name") in FAST_JSON_SHOPS:
        r=_scan_einen_json(h, cancel=cancel)
        if r is not None:
            return r
    return _scan_einen_html(h, cancel=cancel, force=force)


def _scan_einen_html(h, cancel=None, force=False):
    st=time.time()
    try:
        if _abgebrochen(cancel): raise ScanAbgebrochen
        html,fu,cached,meta=fetch_mit_cache(h["urls"], cancel=cancel, force=force); d=time.time()-st
        if _abgebrochen(cancel): raise ScanAbgebrochen
        if cached is not None:
            p=cached.get("preis"); v=bool(cached.get("verfuegbar"))
            state=cached.get("avail_state") or cached.get("state") or "unknown"
            res=_res(h,p,classify(v,p,MAX_PREIS,state),d,None,fu,
                     signal=cached.get("signal"),condition=cached.get("condition"),
                     seller=cached.get("seller"),
                     verfuegbarkeit=cached.get("verfuegbarkeit"),
                     sofort=cached.get("sofort"),
                     avail_state=state,stock_source=cached.get("stock_source"),
                     gtin=cached.get("gtin"),sku=cached.get("sku"),
                     bundle=bool(cached.get("bundle")),
                     marketplace=bool(cached.get("marketplace")),
                     beleg=cached.get("beleg"))
            # Ein 304 ist ein gueltiger Stand, aber keine frische Antwort.
            res["fresh"]=False
            res["not_modified"]=True
            res["confidence"]=berechne_konfidenz(res)
            res["bytes"]=int(meta.get("bytes") or 0)
            if cached.get("kaufbox"): res["kaufbox"]=cached.get("kaufbox")
            res["_cache"]=True
            return res
        if detect_challenge(html[:3000].lower()):
            return _res(h,None,"challenge",d,"Bot-Challenge",fu,
                        avail_state="unknown",stock_source="challenge")
        s=extract_structured(html)
        if not pruefe_nur_konsole(html,s):
            return _res(h,None,"unknown",d,"nicht PS5 Pro 2TB",fu,
                        avail_state="unknown",stock_source="text")
        amz = extract_amazon(html) if ist_amazon(fu or h["urls"][0]) else {}
        remote=remote_parser_ergebnis(html,h.get("parser"))
        meta_v,meta_sofort=extract_meta_verfuegbarkeit(html)
        meta_state=extract_meta_state(html)
        v=remote.get("verfuegbar")
        state=remote.get("state")
        quelle="remote" if state else None
        # Strukturierte Daten (JSON-LD) haben Vorrang vor einem eventuell
        # veralteten Meta-Tag; erst danach greifen Meta und Text-Fallback.
        v_explizit=v is not None
        if v is None:
            v=s.get("verfuegbar"); v_explizit=v is not None
            if state is None and s.get("state"):
                state=s["state"]; quelle="jsonld"
        if v is None and amz.get("verfuegbar") is not None:
            v=amz["verfuegbar"]; v_explizit=True
            if state is None and amz.get("state"):
                state=amz["state"]; quelle="amazon"
        if v is None:
            v=meta_v; v_explizit=v is not None
            if state is None and meta_state:
                state=meta_state; quelle="meta"
        # Chance-Marker vor dem Text-Fallback pruefen: "Nur im Markt" steht
        # oft neben "In den Warenkorb" und darf nicht als normaler Treffer
        # durchgehen.
        if state is None:
            chance=chance_aus_text(html)
            if chance:
                state=chance; quelle="text"; v=True; v_explizit=True
        if v is None:
            v,v_explizit=_verfuegbarkeit_aus_text(html)
            if state is None and v_explizit:
                state="sold_out" if v is False else "in_stock"
                quelle="text"
        if state is None:
            state="unknown"; quelle=quelle or "text"
        if state in CHANCE_STATES:
            v=True; v_explizit=True
        p=remote.get("preis")
        if p is None: p=s.get("preis")
        if p is None: p=amz.get("preis")
        if p is None:
            # Nur das Produkt-Meta der Seite; eine Euro-Zahl aus dem Seitentext
            # oder aus Kartenmarkup gehoert zu keinem bestimmten Artikel.
            p=extract_meta_preis(html)
        # HTTP 200, Produkt erkannt, aber kein Preis: Das ist ein Parserfehler,
        # solange die Seite nicht ausdruecklich "nicht verfuegbar" sagt. Eine
        # ausverkaufte Produktseite bleibt damit unavail und wird nicht als
        # kaputter Parser gezaehlt.
        if p is None and not (v_explizit and v is False):
            return _res(h,None,"parser",d,"Parser: kein Preis",fu,
                        signal="parser",condition=s.get("condition"),
                        seller=s.get("seller"),
                        verfuegbarkeit=s.get("verfuegbarkeit"),
                        sofort=s.get("sofort"),avail_state=state,
                        stock_source=quelle,gtin=s.get("gtin"),sku=s.get("sku"),
                        bundle=bool(s.get("bundle")))
        signal=("remote" if remote.get("preis") is not None else
                "jsonld" if s.get("preis") is not None else
                "amazon" if amz.get("preis") is not None else
                "meta" if p is not None else "text")
        sofort=remote.get("sofort")
        if sofort is None: sofort=s.get("sofort")
        if sofort is None: sofort=meta_sofort
        if sofort is None and v: sofort=ist_sofort_verfuegbar(html)
        if state in CHANCE_STATES: sofort=False
        if _abgebrochen(cancel): raise ScanAbgebrochen
        res=_res(h,p,classify(v,p,MAX_PREIS,state),d,None,fu,
                 produkt_url=s.get("produkt_url"),
                 signal=signal,condition=s.get("condition"),seller=s.get("seller"),
                 verfuegbarkeit=s.get("verfuegbarkeit"),sofort=sofort,
                 avail_state=state,stock_source=quelle,gtin=s.get("gtin"),
                 sku=s.get("sku"),bundle=bool(s.get("bundle")),
                 marketplace=_marketplace(s.get("seller"),h["name"]))
        res["fresh"]=True
        res["not_modified"]=bool(meta.get("not_modified_gesehen"))
        res["confidence"]=berechne_konfidenz(res)
        res["bytes"]=int(meta.get("bytes") or 0)
        # Fingerprint der Preisstruktur aus derselben Antwort: kein Extra-Abruf.
        fp=kaufbox_fingerprint(html)
        if fp: res["kaufbox"]=fp
        # Ein Beleg entsteht nur fuer echte Treffer/Chancen, nicht fuer jede
        # der 42 Seiten. Der Ausschnitt ist klein und enthaelt keine Tokens.
        if res["klass"] in ("hit","chance"):
            try:
                beleg=beleg_erzeugen(html,p,state)
                if beleg:
                    res["beleg"]=beleg
                    beleg_speichern(h["name"],beleg)
            except Exception: pass
        # Auch "nicht verfuegbar" cachen: der naechste 304 spart die Seite
        # komplett, und die Verfuegbarkeit stammt aus demselben Abruf. Parser-
        # Fehler werden nicht gecacht, sonst wuerde ein 304 den Fehler als
        # vermeintlich gueltiges Ergebnis konservieren.
        try:
            http_cache().put(fu or h["urls"][0],
                             {"preis":p,"verfuegbar":bool(v),"signal":signal,
                              "condition":s.get("condition"),"seller":s.get("seller"),
                              "verfuegbarkeit":s.get("verfuegbarkeit"),"sofort":sofort,
                              "avail_state":state,"stock_source":quelle,
                              "gtin":s.get("gtin"),"sku":s.get("sku"),
                              "bundle":bool(s.get("bundle")),
                              "marketplace":_marketplace(s.get("seller"),h["name"]),
                              "kaufbox":res.get("kaufbox"),
                              "beleg":res.get("beleg")},
                             meta.get("etag"),meta.get("last_modified"),persist=False)
        except Exception: pass
        return res
    except ScanAbgebrochen:
        return None
    except Exception as e:
        err=str(e)[:60]
        return _res(h,None,fehler_klasse(err),time.time()-st,err,
                    avail_state="unknown",stock_source="error")


def _safe_scan(h, cancel=None):
    st=time.time()
    try: r=scan_einen(h,cancel=cancel)
    except Exception as e: r=_res(h,None,"error",time.time()-st,str(e)[:60])
    if r is None: return None
    try: health().record(r)
    except Exception: pass
    return r

_DATA_DIR = None

def set_data_dir(p):
    """Datenverzeichnis der App uebernehmen (Service laeuft im eigenen Prozess)."""
    global _DATA_DIR, _EVENTS
    _DATA_DIR = p or None
    _EVENTS = None

def _data_dir():
    if _DATA_DIR: return _DATA_DIR
    # Im App-Prozess ist ANDROID_PRIVATE das files-Verzeichnis, das Kivy auch
    # als user_data_dir liefert - beide Prozesse lesen so dieselben Dateien.
    p = os.environ.get("ANDROID_PRIVATE")
    if p: return p
    return os.path.expanduser("~")

def data_dir():
    return _data_dir()

def scan_alle(haendler, max_preis=None, fortschritt=None, cancel=None):
    """Alle Haendler parallel scannen - dieselbe Logik wie im Vordergrund.

    ``max_preis`` ist eine Zahl, ein Dict je Land (siehe ``preis_deckel``) oder
    None fuer den Standard.
    """
    ergebnisse = []
    ex = ThreadPoolExecutor(max_workers=WORKER)
    try:
        futs = {ex.submit(_safe_scan, h, cancel): h for h in haendler}
        for f in as_completed(futs):
            if _abgebrochen(cancel):
                for fut in futs: fut.cancel()
                break
            r = f.result()
            if r is None: continue
            if r.get("klass") not in ("error", "challenge", "unavail", "parser", "chance"):
                r["klass"] = classify(True, r.get("preis"),
                                      preis_deckel(r.get("land"), max_preis))
            ergebnisse.append(r)
            if fortschritt is not None:
                try: fortschritt(len(ergebnisse), len(haendler))
                except Exception: pass
    finally:
        try: health().save()
        except Exception: pass
        # Alle Shop-Ergebnisse in einem Rutsch sichern. scan_einen() puffert
        # die Eintraege bewusst, damit nicht jeder Thread die Cache-Datei
        # gleichzeitig neu schreibt.
        try: flush_http_cache()
        except Exception: pass
        ex.shutdown(wait=False, cancel_futures=True)
    return ergebnisse

def treffer_aus(results):
    return [r for r in results if r.get("klass") == "hit"
            and preis_plausibel(r.get("preis"))
            and not ist_gebraucht(r.get("condition"))]

def ist_neuer_treffer(preis, letzter):
    """True, wenn es noch keinen Preis gab oder der neue niedriger ist."""
    return letzter is None or preis < letzter - 0.01

def alarm_ereignis(r, letzter, vorher_verfuegbar):
    """Gemeinsames Alarm-Ereignis fuer App und Hintergrunddienst.

    ``restock`` hat Vorrang: ein wieder verfuegbarer Treffer ist auch dann
    meldenswert, wenn der Preis nicht unter dem letzten Preis liegt.
    """
    if not isinstance(r,dict) or r.get("klass")!="hit" or \
            not preis_plausibel(r.get("preis")):
        return None
    if vorher_verfuegbar is False: return "restock"
    if ist_neuer_treffer(r["preis"],letzter): return "new"
    return None

# ── Webhook-Alarme ─────────────────────────────────────────────────
def webhook_preset(url):
    """Erkennt den Kanal an der URL. Unbekannte Ziele bekommen neutrales JSON."""
    try: host=(urlparse(str(url)).hostname or "").lower()
    except Exception: return "generisch"
    if host=="ntfy.sh" or host.endswith(".ntfy.sh"): return "ntfy"
    if host=="api.telegram.org": return "telegram"
    if host in ("discord.com","discordapp.com","ptb.discord.com","canary.discord.com"):
        return "discord"
    return "generisch"

def redact_url(url):
    """Nur Schema und Host - Tokens im Pfad oder Query duerfen nie ins Log."""
    try:
        p=urlparse(str(url))
        if not p.scheme or not p.hostname: return "—"
        return f"{p.scheme}://{p.hostname}/…"
    except Exception: return "—"

def webhook_nachricht(preset, titel, text, ziel_url=None):
    """Body und Header fuer den gewaehlten Kanal. Reine Funktion, testbar."""
    titel=str(titel or ""); text=str(text or "")
    if preset=="ntfy":
        hd={"Content-Type":"text/plain; charset=utf-8","Title":titel,
            "Priority":"high"}
        if ziel_url: hd["Click"]=str(ziel_url)
        return (titel+"\n"+text if titel else text),hd
    if preset=="telegram":
        return (json.dumps({"text":(titel+"\n"+text) if titel else text,
                            "disable_web_page_preview":True},
                           ensure_ascii=False),
                {"Content-Type":"application/json; charset=utf-8"})
    if preset=="discord":
        inhalt=(titel+"\n"+text) if titel else text
        if ziel_url: inhalt=inhalt+"\n"+str(ziel_url)
        return (json.dumps({"content":inhalt},ensure_ascii=False),
                {"Content-Type":"application/json; charset=utf-8"})
    return (json.dumps({"titel":titel,"text":text,"url":ziel_url or ""},
                       ensure_ascii=False),
            {"Content-Type":"application/json; charset=utf-8"})

def webhook_senden(url, preset=None, titel="", text="", ziel_url=None,
                   timeout=WEBHOOK_TIMEOUT, pause=3.0, post=None):
    """Sendet eine Meldung. Rueckgabe (ok, status).

    Nur HTTPS. 4xx wird nicht wiederholt (URL oder Token falsch), 5xx und
    Zeitueberschreitungen genau einmal. ``post`` und ``pause`` sind fuer Tests.
    """
    try: p=urlparse(str(url))
    except Exception: return False,"URL ungueltig"
    if p.scheme!="https" or not p.hostname: return False,"nur HTTPS"
    if preset not in WEBHOOK_PRESETS: preset=webhook_preset(url)
    body,headers=webhook_nachricht(preset,titel,text,ziel_url)
    if post is None: post=_requests().post
    letzter="kein Versuch"
    for versuch in range(2):
        try:
            r=post(str(url),data=body.encode("utf-8"),headers=headers,timeout=timeout)
            code=int(getattr(r,"status_code",0) or 0)
            if 200<=code<300: return True,f"HTTP {code}"
            letzter=f"HTTP {code}"
            if 400<=code<500: return False,letzter
        except Exception as e:
            letzter=str(e)[:60]
        if versuch==0 and pause:
            time.sleep(pause)
    return False,letzter

_WEBHOOK_SEEN={}
_WEBHOOK_LOCK=threading.Lock()


def _json_lesen(pfad):
    try:
        with open(pfad,"r",encoding="utf-8") as f: return json.load(f)
    except Exception: return None


def _json_schreiben(pfad,daten):
    tmp=pfad+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(daten,f,ensure_ascii=False,indent=1)
    os.replace(tmp,pfad)


class _Sperrdatei:
    """Kurze Sperre fuer eine Datei, die auch ueber Prozesse gilt.

    Angelegt per O_EXCL auf ``<datei>.lock``. Bleibt eine Sperre nach einem
    Absturz liegen, wird sie nach ``veraltet`` Sekunden uebernommen. Ist das
    Verzeichnis nicht schreibbar, laeuft der Aufrufer ohne Sperre weiter:
    lieber eine kleine Restchance auf doppelt als gar kein Alarm.
    """
    def __init__(self,pfad,geduld=2.0,veraltet=10.0):
        self.pfad=pfad; self.geduld=geduld; self.veraltet=veraltet
        self.ok=False
    def __enter__(self):
        ende=time.time()+self.geduld
        while True:
            try:
                os.close(os.open(self.pfad,os.O_CREAT|os.O_EXCL|os.O_WRONLY))
                self.ok=True; return self
            except FileExistsError:
                pass
            except OSError:
                return self
            try:
                if time.time()-os.path.getmtime(self.pfad)>self.veraltet:
                    os.remove(self.pfad); continue
            except OSError: pass
            if time.time()>=ende: return self
            time.sleep(0.02)
    def __exit__(self,*_):
        if self.ok:
            try: os.remove(self.pfad)
            except OSError: pass
        return False


def _webhook_dedupe_datei():
    return os.path.join(_data_dir(),WEBHOOK_DEDUPE_FILE)


def webhook_dedupe(haendler,preis,restock=False,jetzt=None,cooldown=WEBHOOK_COOLDOWN):
    """True, wenn dieser Treffer noch nicht gemeldet wurde.

    Der Anspruch steht in einer gemeinsamen Datei, damit App und
    Hintergrunddienst denselben Treffer nur einmal melden: wer ihn zuerst
    schreibt, sendet; der andere sieht ihn und schweigt. Eintraege aelter als
    ``cooldown`` fallen dabei raus. Ohne schreibbare Datei entscheidet der
    Prozess-Cache wie bisher.
    """
    jetzt=time.time() if jetzt is None else jetzt
    # Schluessel: Haendler, Preis und Restock-Art.
    try: p=float(preis or 0)
    except (TypeError,ValueError): p=0.0
    key="%s\t%.2f\t%d" % (str(haendler or "?"),p,int(bool(restock)))
    with _WEBHOOK_LOCK:
        pfad=_webhook_dedupe_datei()
        try:
            with _Sperrdatei(pfad+".lock"):
                alt=_json_lesen(pfad)
                if not isinstance(alt,dict): alt={}
                frisch=dict((k,t) for k,t in alt.items()
                            if isinstance(t,(int,float)) and jetzt-t<=cooldown)
                if key in frisch: return False
                frisch[key]=jetzt
                _json_schreiben(pfad,frisch)
            return True
        except (OSError,ValueError):
            for k in [k for k,t in _WEBHOOK_SEEN.items() if jetzt-t>cooldown]:
                _WEBHOOK_SEEN.pop(k,None)
            if key in _WEBHOOK_SEEN: return False
            _WEBHOOK_SEEN[key]=jetzt
            return True

def reset_webhook_dedupe():
    """Nur fuer Tests."""
    with _WEBHOOK_LOCK:
        _WEBHOOK_SEEN.clear()
        try: os.remove(_webhook_dedupe_datei())
        except OSError: pass


def webhook_status_merken(ok,status,haendler=None):
    """Letzte Zustellung festhalten - gemeinsam fuer App und Dienst.

    Ein Fehlschlag im Hintergrund darf nicht unsichtbar bleiben, nur weil die
    App den Treffer selbst nie gesehen hat; SETUP liest diesen Eintrag.
    """
    daten={"ok":bool(ok),"status":str(status or "")[:80],
           "ts":datetime.now().replace(microsecond=0).isoformat(),
           "haendler":str(haendler or "")}
    try:
        _json_schreiben(os.path.join(_data_dir(),WEBHOOK_STATUS_FILE),daten)
    except (OSError,ValueError): pass
    return daten


def webhook_status_lesen():
    """Letzte Zustellung oder None; eine kaputte Datei zaehlt als keine."""
    daten=_json_lesen(os.path.join(_data_dir(),WEBHOOK_STATUS_FILE))
    return dict(daten) if isinstance(daten,dict) else None


def sende_webhook_alarm(r, settings, titel, text, tester=False, dedupe=True):
    """Webhook fuer einen Treffer. None = kein Kanal oder schon gemeldet.

    ``dedupe=False`` uebernimmt die Outbox: sie hat den Treffer bereits
    persistent vorgemerkt und darf nicht an der gemeinsamen 10-Minuten-Sperre
    scheitern. App und Testalarm behalten die bisherige Dedupe-Regel.
    """
    url=str(_setting(settings,"webhook_url","") or "").strip()
    if not url: return None
    preset=_setting(settings,"webhook_preset","")
    if preset not in WEBHOOK_PRESETS: preset=webhook_preset(url)
    if dedupe and not tester and not webhook_dedupe(r.get("haendler"),r.get("preis"),
                                                    bool(r.get("_restock"))):
        return None
    ok,info=webhook_senden(url,preset,titel,text,r.get("url"))
    # Ergebnis auch bei Fehler merken: der Dienst meldet damit genauso
    # sichtbar wie die App (SETUP zeigt "LETZTE ZUSTELLUNG").
    webhook_status_merken(ok,info,r.get("haendler"))
    return ok,info

# ── Treffer-Verifikation ───────────────────────────────────────────
def verify_entscheidung(erster,zweiter):
    """Vergleicht den Treffer mit dem zweiten Abruf. Reine Funktion."""
    if not isinstance(erster,dict) or erster.get("klass")!="hit": return None
    if not isinstance(zweiter,dict): return "unbestaetigt"
    if zweiter.get("klass")=="unavail": return "weg"
    if zweiter.get("klass")=="chance": return "chance"
    if zweiter.get("preis") is not None and zweiter.get("klass") in ("hit","expensive"):
        try:
            if abs(float(zweiter["preis"])-float(erster.get("preis") or 0))<=0.005:
                return "bestaetigt"
        except (TypeError,ValueError): pass
        return "geaendert"
    return "unbestaetigt"

def verify_treffer(h, erster, cancel=None, pause=2.0):
    """Bestaetigt einen Treffer mit einem zweiten, unbedingten Abruf.

    Nur Treffer kosten diesen Extraschritt. Ein 403/429 beim zweiten Abruf
    wird nicht wiederholt und als ``unbestaetigt`` markiert. Ist der Shop
    inzwischen ausverkauft, wird der Treffer auf ``unavail`` zurueckgestuft -
    lieber kein Alarm als ein falscher.
    """
    if not isinstance(erster,dict) or erster.get("klass")!="hit": return erster
    if pause:
        try:
            if cancel is not None:
                if cancel.wait(pause):
                    erster["verify"]="unbestaetigt"; return erster
            else: time.sleep(pause)
        except Exception:
            time.sleep(pause)
    if _abgebrochen(cancel):
        erster["verify"]="unbestaetigt"; return erster
    try: zweiter=scan_einen(h,cancel=cancel,force=True)
    except Exception: zweiter=None
    if _abgebrochen(cancel):
        erster["verify"]="unbestaetigt"; return erster
    entscheidung=verify_entscheidung(erster,zweiter)
    erster["verify"]=entscheidung
    if entscheidung=="geaendert":
        erster["verify_preis"]=zweiter.get("preis")
    elif entscheidung=="weg":
        erster["klass"]="unavail"; erster["verify_preis"]=None
    elif entscheidung=="chance":
        # Der zweite Abruf zeigt Marktabholung/Lotterie/Einladung: kein
        # kaufbarer Treffer mehr, also auch kein Verfuegbarkeitsalarm.
        erster["klass"]="chance"; erster["sofort"]=False
        erster["avail_state"]=zweiter.get("avail_state") or "pickup_only"
    try: erster["confidence"]=berechne_konfidenz(erster)
    except Exception: pass
    return erster

def schnellscan_haendler(haendler, aktiv=None, hot=None):
    """Hot-Shops, die auch in der aktiven Auswahl stehen."""
    namen=set(hot or HOT_SHOPS)
    if aktiv: namen &= set(aktiv)
    return [h for h in haendler if h.get("name") in namen]

def bg_intervall(sekunden, minimum=900):
    """Akku-freundlich: im Hintergrund nie oefter als alle 15 Minuten."""
    try: s = int(sekunden)
    except (TypeError, ValueError): s = minimum
    return max(minimum, s)


def bg_wachhund(status, jetzt=None, intervall=None):
    """Zustand des Hintergrunddienstes fuer die App.

    ``wach_ts`` schreibt der Dienst nach jeder Runde - auch wenn er wegen
    WLAN-/Ladeoption pausiert. Eine frische Pause ist kein toter Dienst und
    darf deshalb keinen Fehlalarm ausloesen.
    """
    jetzt = time.time() if jetzt is None else float(jetzt)
    if not isinstance(status, dict):
        return {"zustand": "unbekannt", "alter": None, "grund": ""}
    try: wach = float(status.get("wach_ts") or status.get("ts") or 0)
    except (TypeError, ValueError): wach = 0.0
    if wach <= 0:
        return {"zustand": "unbekannt", "alter": None, "grund": ""}
    try: iv = max(60, int(intervall or status.get("intervall") or 900))
    except (TypeError, ValueError): iv = 900
    alter = int(max(0.0, jetzt - wach))
    grenze = max(1800, iv * 2 + 600)
    grund = str(status.get("pausiert") or "")
    if status.get("wach_status") == "pausiert" and grund and alter <= grenze:
        return {"zustand": "pausiert", "alter": alter, "grund": grund}
    return {"zustand": "tot" if alter > grenze else "ok",
            "alter": alter, "grund": grund}


def _als_datetime(jetzt=None):
    """Akzeptiert datetime, Zeitstempel oder None (dann Ortszeit jetzt)."""
    if jetzt is None: return datetime.now()
    if isinstance(jetzt, datetime): return jetzt
    try: return datetime.fromtimestamp(float(jetzt))
    except (TypeError, ValueError, OSError, OverflowError): return datetime.now()


def im_drop_fenster(name, jetzt=None):
    """True, wenn dieser Shop gerade in einem Auflegefenster liegt.

    Ein gelerntes Fenster ersetzt den Default, sobald es gesetzt ist. Ein
    Fenster ueber Mitternacht ist erlaubt, wird hier aber nicht gebraucht.
    """
    name = str(name or "")
    fenster = _DROP_FENSTER_GELERNT.get(name) or DROP_FENSTER.get(name)
    if not fenster: return False
    d = _als_datetime(jetzt)
    minute = d.hour * 60 + d.minute
    for sh, sm, eh, em in fenster:
        von, bis = sh * 60 + sm, eh * 60 + em
        if (von <= minute <= bis) if von <= bis else (minute >= von or minute <= bis):
            return True
    return False


def naechste_fenster_ts(jetzt=None):
    """Naechster Beginn eines belegten Auflegefensters (Ortszeit).

    Der Dienst schlaeft ausserhalb des Fensters bis zu diesem Zeitpunkt,
    statt jede Minute nachzusehen - die 15-Minuten-Runde laeuft weiter.
    """
    d = _als_datetime(jetzt)
    treffer = []
    for fenster in DROP_FENSTER.values():
        for sh, sm, eh, em in fenster:
            start = d.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if start <= d:
                start = start + timedelta(days=1)
            treffer.append(start.timestamp())
    if treffer: return min(treffer)
    # Kein Fenster konfiguriert: nicht in eine Sofortschleife laufen.
    return (time.time() if jetzt is None else float(jetzt)) + 60


def _drop_fenster_stunde(zeile, tz=None):
    """Stunde eines Checks: bevorzugt der ISO-Zeitstempel mit Offset."""
    iso = zeile.get("iso")
    if iso:
        try:
            return datetime.fromisoformat(str(iso)).hour
        except (TypeError, ValueError):
            pass
    try:
        ts = float(zeile.get("ts"))
        return datetime.fromtimestamp(ts, tz).hour if tz else datetime.fromtimestamp(ts).hour
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def lerne_drop_fenster(checks, tz=None, min_hits=DROP_FENSTER_MIN_HITS,
                       min_tage=DROP_FENSTER_MIN_TAGE,
                       max_baender=DROP_FENSTER_MAX_BAENDER):
    """Aus ``hit``-Checks zeitliche Baender ableiten.

    Nur Shops mit einem Default-Fenster kommen infrage. Zu wenige Hits oder
    zu wenige verschiedene Tage ergeben bewusst kein Fenster: dann bleibt der
    Default aktiv, statt aus einem Zufallstreffer ein 03:00-Band zu machen.
    Eine Stunde zaehlt nur mit mindestens zwei Treffern.
    """
    pro_shop = {}
    for zeile in checks or []:
        if not isinstance(zeile, dict) or zeile.get("klass") != "hit":
            continue
        name = str(zeile.get("shop") or "")
        if name not in DROP_FENSTER:
            continue
        stunde = _drop_fenster_stunde(zeile, tz)
        if stunde is None:
            continue
        eintrag = pro_shop.setdefault(name, {"stunden": {}, "tage": set()})
        eintrag["stunden"][stunde] = eintrag["stunden"].get(stunde, 0) + 1
        tag = None
        iso = zeile.get("iso")
        if iso:
            try:
                tag = datetime.fromisoformat(str(iso)).date()
            except (TypeError, ValueError):
                tag = None
        if tag is None:
            try:
                ts = float(zeile.get("ts"))
                tag = (datetime.fromtimestamp(ts, tz) if tz
                       else datetime.fromtimestamp(ts)).date()
            except (TypeError, ValueError, OSError, OverflowError):
                tag = None
        if tag is not None:
            eintrag["tage"].add(tag)

    shops = {}
    for name, eintrag in pro_shop.items():
        hits = sum(eintrag["stunden"].values())
        if hits < int(min_hits) or len(eintrag["tage"]) < int(min_tage):
            continue
        aktiv = sorted(h for h, n in eintrag["stunden"].items()
                       if n >= DROP_FENSTER_STUNDE_MIN)
        if not aktiv:
            continue
        baender = []
        start = prev = aktiv[0]
        for stunde in aktiv[1:]:
            if stunde - prev <= 1:
                prev = stunde
                continue
            baender.append((start, prev + 1))
            start = prev = stunde
        baender.append((start, prev + 1))
        # Die dichtesten Baender zuerst, danach wieder in Zeitreihenfolge.
        baender.sort(
            key=lambda b: (sum(eintrag["stunden"].get(h, 0)
                               for h in range(b[0], b[1])), b[0]),
            reverse=True,
        )
        baender = sorted(baender[:max(0, int(max_baender))])
        shops[name] = {
            "fenster": [[a, 0, b, 0] for a, b in baender],
            "hits": hits,
            "tage": len(eintrag["tage"]),
        }
    return {"schema": 1, "gelernt_ts": time.time(),
            "quelle": "watcher-log", "shops": shops}


def setze_drop_fenster(shops):
    """Gelernte Fenster global setzen; leere Map aktiviert den Default."""
    global _DROP_FENSTER_GELERNT
    neu = {}
    for name, eintrag in (shops or {}).items():
        if not isinstance(eintrag, dict):
            continue
        roh = eintrag.get("fenster")
        if not isinstance(roh, list):
            continue
        fenster = []
        for band in roh:
            if not isinstance(band, (list, tuple)) or len(band) != 4:
                continue
            try:
                a, b, c, d = (int(x) for x in band)
            except (TypeError, ValueError):
                continue
            if 0 <= a <= 24 and 0 <= c <= 24:
                fenster.append((a, b, c, d))
        if fenster:
            neu[str(name)] = tuple(fenster)
    _DROP_FENSTER_GELERNT = neu
    return dict(_DROP_FENSTER_GELERNT)


def reset_gelernte_drop_fenster():
    """Nur fuer Tests und einen bewussten Neustart."""
    setze_drop_fenster({})


def drop_fenster_laden(pfad=None):
    pfad = pfad or os.path.join(_data_dir(), DROP_FENSTER_LERN_FILE)
    try:
        with open(pfad, "r", encoding="utf-8") as datei:
            daten = json.load(datei)
        return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError):
        return {}


def drop_fenster_speichern(pfad, daten):
    try:
        tmp = pfad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as datei:
            json.dump(daten, datei, ensure_ascii=False)
        os.replace(tmp, pfad)
        return True
    except (OSError, ValueError, TypeError):
        return False


def live_takt(haendler, aktiv=None, jetzt=None):
    """Rundentakt: im Drop-Fenster 10 s, sonst ``LIVE_TAKT``.

    Das Fenster ist eine Information ueber den Shop, keine Regel ueber die
    Uhr: ohne aktiven Shop in einem Fenster bleibt es beim normalen Takt.
    """
    namen = set(aktiv) if aktiv else None
    for h in haendler or []:
        name = h.get("name")
        if not name or (namen is not None and name not in namen): continue
        if im_drop_fenster(name, jetzt): return LIVE_TAKT_FENSTER
    return LIVE_TAKT


def live_runden_max(takt):
    """Rundengroesse, die das Minutenbudget nicht ueberschreitet.

    Ohne diese Kopplung wuerde ein 10-s-Takt bei 12 Shops je Runde 72
    Requests/Minute erzeugen - fast das Doppelte des Budgets.
    """
    try: takt = max(1, int(takt))
    except (TypeError, ValueError): takt = LIVE_TAKT
    return LIVE_RUNDE_FENSTER if takt <= LIVE_TAKT_FENSTER else LIVE_RUNDE_MAX


def meldebereit(r):
    """Treffer mit strukturiertem Beleg darf ohne Warten auf die Verifikation melden.

    Der zweite Abruf bleibt Pflicht und laeuft direkt danach; er kann den
    Treffer zurueckstufen (``verify == "weg"``). Gemeldet wird vorher nur,
    was aus JSON-LD oder einer belegten Remote-Regel stammt, ausdruecklich
    ``in_stock`` ist und einen plausiblen Preis hat. Text-Marker allein warten
    wie bisher — ein Alarm muss stimmen.
    """
    if not isinstance(r, dict) or r.get("klass") != "hit": return False
    if r.get("preis") is None or ist_gebraucht(r.get("condition")): return False
    if r.get("avail_state") != "in_stock": return False
    if r.get("stock_source") not in ("jsonld", "remote"): return False
    try: return bool(MIN_PREIS <= float(r["preis"]) <= 1500)
    except (TypeError, ValueError): return False


def _jitter(name):
    """Stabiler Versatz pro Shop (-20 % .. +20 %).

    Bewusst crc32 statt ``hash``: Pythons String-Hash ist pro Prozess
    randomisiert, die Taktung waere dann zwischen App und Dienst verschieden
    und Tests nicht reproduzierbar.
    """
    try: roh = zlib.crc32(str(name).encode("utf-8")) % 2001
    except Exception: roh = 0
    return (roh / 1000.0 - 1.0) * LIVE_JITTER


def shop_gesperrt(health_eintrag):
    """Sperre oder zwei Fehler in Folge: gerade nicht dicht abfragen."""
    e = health_eintrag if isinstance(health_eintrag, dict) else {}
    status = str(e.get("last_status") or "")
    if status == "challenge": return True
    if status in ("parser", "error"):
        try: return int(e.get("fail_streak") or 0) >= 2
        except (TypeError, ValueError): return False
    return False


def bg_hot_shops(haendler, aktiv=None, health_daten=None, jetzt=None):
    """PS Direct DE/AT fuer die kurze Hintergrundrunde im Fenster.

    Ausserhalb des Fensters, ohne aktive Auswahl oder bei Sperre/Fehlerserie
    bleibt die Liste leer - dann laeuft nur die normale 15-Minuten-Runde.
    """
    jetzt = time.time() if jetzt is None else float(jetzt)
    namen = set(aktiv) if aktiv else None
    daten = health_daten if isinstance(health_daten, dict) else {}
    out = []
    for h in haendler or []:
        name = h.get("name")
        if not name or name not in BG_HOT_SHOPS: continue
        if namen is not None and name not in namen: continue
        if not im_drop_fenster(name, jetzt): continue
        e = daten.get(name) if isinstance(daten.get(name), dict) else {}
        if shop_gesperrt(e): continue
        out.append(h)
    return out


def shop_intervall(name, health_daten=None, jetzt=None):
    """Sekunden bis zur naechsten Pruefung - aus Zustand und Stoerung.

    Die Reihenfolge ist Absicht: eine Sperre schlaegt den Trefferzustand,
    sonst wuerde ein 403-Shop im 30-s-Takt weiter angeklopft.
    """
    e = health_daten.get(name) if isinstance(health_daten, dict) else None
    e = e if isinstance(e, dict) else {}
    status = str(e.get("last_status") or "")
    if shop_gesperrt(e):
        soll = LIVE_RUHE_S if status == "challenge" else LIVE_GESTOERT_S
    elif im_drop_fenster(name, jetzt):
        soll = LIVE_FENSTER_S
    elif status in ("hit", "expensive"):
        soll = LIVE_HEISS_S
    else:
        soll = LIVE_NORMAL_S
    return max(5, int(round(soll * (1.0 + _jitter(name)))))


def faellige_haendler(haendler, health_daten=None, jetzt=None,
                      budget=None, aktiv=None):
    """Shops der naechsten Live-Runde - die ueberfaelligsten zuerst.

    Shops in einem belegten Auflegefenster stehen immer vorn: Sonst
    verdraengen ueberfaellige Shops sie aus dem kleinen 10-s-Budget. Eine
    Sperre oder Fehlerserie hebt den Vorrang auf.

    ``budget`` ist die Rundengroesse, nicht das Minutenbudget: eine Runde
    startet hoechstens alle ``LIVE_TAKT`` Sekunden. Weil absteigend nach
    Ueberfaelligkeit sortiert und dann abgeschnitten wird, verhungert kein
    Shop - was heute nicht dran war, steht in der naechsten Runde oben.
    """
    jetzt = time.time() if jetzt is None else float(jetzt)
    namen = set(aktiv) if aktiv else None
    daten = health_daten if isinstance(health_daten, dict) else {}
    vorrang, faellig = [], []
    for h in haendler or []:
        name = h.get("name")
        if not name: continue
        if namen is not None and name not in namen: continue
        e = daten.get(name) if isinstance(daten.get(name), dict) else {}
        if im_drop_fenster(name, jetzt) and not shop_gesperrt(e):
            vorrang.append((name, h)); continue
        try: letzte = float(e.get("last_ts") or 0)
        except (TypeError, ValueError): letzte = 0.0
        alter = max(0.0, jetzt - letzte)
        soll = shop_intervall(name, daten, jetzt)
        # 0.5 s Toleranz: ein gerundetes Intervall soll nicht eine Runde warten.
        if alter + 0.5 >= soll:
            faellig.append((alter - soll, name, h))
    vorrang.sort(key=lambda t: t[0])
    faellig.sort(key=lambda t: (-t[0], t[1]))
    out = [h for _, h in vorrang] + [h for _, _, h in faellig]
    if budget is not None:
        try: out = out[:max(1, int(budget))]
        except (TypeError, ValueError): pass
    return out


def health_uebersicht(health_daten=None, jetzt=None):
    """Kompakte Auswertung pro Shop: Quote, Fehlerserie, Alter der Pruefung.

    Rein lokal, kein Versand. Was hier fehlt, ist unbekannt - nicht gesund.
    """
    daten = health_daten if isinstance(health_daten, dict) else health().all()
    jetzt = time.time() if jetzt is None else float(jetzt)
    out = {}
    for name, e in (daten or {}).items():
        if not isinstance(e, dict): continue
        try: letzte = float(e.get("last_ts") or 0)
        except (TypeError, ValueError): letzte = 0.0
        checks = int(e.get("checks") or 0)
        erfolge = int(e.get("successes") or 0)
        out[name] = {"status": e.get("last_status") or "unknown",
                     "checks": checks, "erfolge": erfolge,
                     "quote": round(100.0 * erfolge / checks, 1) if checks else 0.0,
                     "fail_streak": int(e.get("fail_streak") or 0),
                     "alter": int(max(0.0, jetzt - letzte)) if letzte else None}
    return out


EVENTS_FILE="ps5pro_events.jsonl"
EVENTS_LEGACY_FILE="ps5pro_events.json"
# Das Journal haelt die letzten 5000 Wechsel ueber hoechstens fuenf Dateien.
# Eine aktive Datei rotiert nach 1000 Zeilen oder 512 KB; aeltere Segmente
# bleiben als .1 bis .4 erhalten. So waechst der Speicher nicht unbegrenzt.
MAX_EVENTS=5000
EVENTS_MAX_LINES=1000
EVENTS_MAX_BYTES=512*1024
EVENTS_MAX_SEGMENTS=5
EVENTS_LOCK_TIMEOUT=10.0
EVENTS_LOCK_STALE=30.0
# Ein offenes Fenster gilt nur als aktuell, wenn der letzte verfuegbar-Wechsel
# hoechstens einen Scan-Takt plus Kulanz zurueckliegt. ERFOLG_OFFEN_MAX bleibt
# die Obergrenze fuer den 60-Minuten-Takt. Ein frischer, erfolgreicher Scan
# desselben Shops bestaetigt den Stand auch ohne neues Ereignis.
ERFOLG_OFFEN_MAX=3600
ERFOLG_OFFEN_MIN=120
ERFOLG_OFFEN_KULANZ=120
# Nur diese Scan-Ergebnisse belegen Verfuegbarkeit. Ein erfolgreicher Abruf
# mit "unavail" darf ein offenes Fenster nicht wieder als OFFEN bestaetigen.
ERFOLG_SCAN_GUELTIG=frozenset(("hit","expensive","chance","unknown"))
# Abdeckung: Ein Treffer oder ein sauberer "nicht verfuegbar"-Scan belegt,
# dass der Shop in diesem Zeitraum tatsaechlich angesehen wurde. Fehler-,
# Challenge- und Parser-Scans sind keine Beobachtung des Bestands.
ABDECKUNG_GUT=frozenset(("hit","expensive","unavail","chance","unknown"))
ABDECKUNG_TOLERANZ=2


def erfolg_offen_max(intervall=None):
    """Frische-Fenster aus dem eingestellten Scan-Takt in Sekunden.

    Ein 5-Minuten-Takt ergibt 7 Minuten, ein 60-Minuten-Takt bleibt bei der
    Stunde gedeckelt. Ungueltige oder fehlende Taktwerte fallen auf 10 Minuten
    zurueck, das ist der Standard in den Einstellungen.
    """
    try: takt=int(intervall)
    except (TypeError,ValueError): takt=600
    if takt<=0: takt=600
    return max(ERFOLG_OFFEN_MIN, min(ERFOLG_OFFEN_MAX, takt+ERFOLG_OFFEN_KULANZ))


def erfolg_letzte_scans(health_daten=None):
    """Letzter Scan je Shop, der Verfuegbarkeit bestaetigt (Epoch-Sekunden)."""
    out={}
    if not isinstance(health_daten,dict): return out
    for name,e in health_daten.items():
        if not isinstance(e,dict): continue
        if e.get("last_status") not in ERFOLG_SCAN_GUELTIG: continue
        try: ts=float(e.get("ok_ts"))
        except (TypeError,ValueError): continue
        if ts>0: out[str(name)]=ts
    return out


def dauer_text(sekunden):
    """Fensterdauer lesbar: 45 S · 12 MIN · 1 STD 5 MIN."""
    try: s=int(max(0.0,float(sekunden)))
    except (TypeError,ValueError): return "—"
    if s<60: return f"{s} S"
    if s<3600: return f"{s//60} MIN"
    std,rest=divmod(s,3600); minuten=rest//60
    return f"{std} STD" if not minuten else f"{std} STD {minuten} MIN"


def offen_seit_text(start, jetzt=None):
    """OFFEN SEIT plus Alter; Tage bleiben lesbar statt „49 STD“."""
    alter=_alter_sekunden(start,jetzt)
    if alter is None: return "OFFEN SEIT ?"
    if alter<60: return "OFFEN SEIT GERADE"
    if alter<86400: return "OFFEN SEIT "+dauer_text(alter)
    tage=alter//86400
    return "OFFEN SEIT 1 TAG" if tage==1 else f"OFFEN SEIT {tage} TAGEN"


def preis_badge_text(preis):
    """Kompakter Preis-Badge-Text; fehlender Preis bleibt sichtbar."""
    try: p=float(preis)
    except (TypeError,ValueError): return "PREIS —"
    return "PREIS "+format_preis(p)


def deckel_badge_text(deckel):
    """Kompakter Deckel-Badge-Text; None heisst bewusst „kein Deckel“."""
    if deckel is None: return "DECKEL OFFEN"
    try: d=float(deckel)
    except (TypeError,ValueError): return "DECKEL OFFEN"
    return f"DECKEL {int(round(d))} €"


def preis_unter_deckel(preis, deckel):
    """True/False fuer die Badge-Farbe; None, wenn kein Preis vorliegt."""
    try: p=float(preis)
    except (TypeError,ValueError): return None
    if deckel is None: return True
    try: return p<=float(deckel)+0.005
    except (TypeError,ValueError): return True


def _iso_dt(iso):
    """ISO-Zeitstempel als datetime; eine Stelle fuer alle Anzeigeformate."""
    try: return datetime.fromisoformat(str(iso))
    except (TypeError,ValueError): return None


def kurz_zeit(iso):
    """ISO-Zeitstempel als '13.11., 10:35'; leer, wenn unbrauchbar."""
    dt=_iso_dt(iso)
    return dt.strftime("%d.%m., %H:%M") if dt else ""


def kurz_tag(iso):
    """Nur '13.11.' fuer enge Zeilen, sonst leer."""
    dt=_iso_dt(iso)
    return dt.strftime("%d.%m.") if dt else ""


def tages_key(iso):
    """Stabiler Tagesschluessel fuer Gruppen; leer bei unbrauchbarem Datum."""
    dt=_iso_dt(iso)
    return dt.strftime("%Y-%m-%d") if dt else ""


def tages_label(iso, jetzt=None):
    """Tagesueberschrift: HEUTE, GESTERN oder 13.11./13.11.2025."""
    dt=_iso_dt(iso)
    if dt is None: return "OHNE DATUM"
    if isinstance(jetzt,datetime): heute=jetzt.date()
    else:
        j=_iso_dt(jetzt) if jetzt is not None else None
        heute=(j or datetime.now()).date()
    if dt.date()==heute: return "HEUTE"
    if dt.date()==heute-timedelta(days=1): return "GESTERN"
    return (dt.strftime("%d.%m.%Y") if dt.year!=heute.year
            else dt.strftime("%d.%m."))


def zeitraum_text(start, ende):
    """'13.11., 10:35 – 10:36'; bei Tageswechsel mit zweitem Datum.

    Das Datum steht nur einmal: vorher wurde dasselbe Datum zweimal
    formatiert und die Zeile brach in der Detailansicht um.
    """
    a,b=_iso_dt(start),_iso_dt(ende)
    if a is None and b is None: return ""
    if a is None or b is None: return "?"
    if a.date()==b.date(): return f"{a:%d.%m., %H:%M} – {b:%H:%M}"
    return f"{a:%d.%m., %H:%M} – {b:%d.%m., %H:%M}"


def event_zeile(e):
    """Eine Ticker-Zeile: '13.11., 10:35 · WEG · MediaMarkt · FENSTER 1 MIN'."""
    if not isinstance(e,dict): return ""
    shop=str(e.get("haendler") or "?")
    zeit=kurz_zeit(e.get("ts"))
    if e.get("typ")=="verfuegbar":
        text=f"VERFÜGBAR · {shop}"
    elif e.get("typ")=="ausverkauft":
        text=f"WEG · {shop}"
        if e.get("dauer") is not None:
            text=text+f" · FENSTER {dauer_text(e['dauer'])}"
    else:
        text=f"{str(e.get('typ') or 'EREIGNIS').upper()} · {shop}"
    return f"{zeit} · {text}" if zeit else text


def _fenster_dauer(start, ende):
    """Sekunden zwischen zwei ISO-Zeitstempeln; None, wenn unbrauchbar."""
    a, b = _iso_dt(start), _iso_dt(ende)
    if a is None or b is None:
        return None
    try:
        return max(0, int((b - a).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def _alter_sekunden(iso, jetzt=None):
    """Sekunden seit einem ISO-Zeitstempel; None, wenn unbrauchbar."""
    dt = _iso_dt(iso)
    if dt is None:
        return None
    if jetzt is None:
        jetzt = datetime.now()
    elif not isinstance(jetzt, datetime):
        jetzt = _iso_dt(jetzt)
    if jetzt is None:
        return None
    try:
        return max(0, int((jetzt - dt).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def _alter_scan(ts, jetzt=None):
    """Sekunden seit einem Scan-Zeitstempel (Epoch oder ISO)."""
    try: epoch=float(ts)
    except (TypeError,ValueError): return _alter_sekunden(ts, jetzt)
    if isinstance(jetzt, datetime): jetzt=jetzt.timestamp()
    elif jetzt is None: jetzt=time.time()
    else:
        dt=_iso_dt(jetzt)
        if dt is None: return None
        jetzt=dt.timestamp()
    try: return max(0,int(jetzt-epoch))
    except (TypeError,ValueError,OverflowError): return None


def _ts_zu_epoch(ts):
    """ISO-Zeitstempel oder Epoch-Sekunden als float; None bei Unbrauchbarem."""
    if ts is None: return None
    if isinstance(ts,(int,float)):
        try: return float(ts)
        except (TypeError,ValueError): return None
    dt=_iso_dt(ts)
    return dt.timestamp() if dt else None


def _jetzt_epoch(jetzt=None):
    if jetzt is None: return time.time()
    if isinstance(jetzt,datetime):
        try: return jetzt.timestamp()
        except (TypeError,ValueError,OverflowError): return None
    return _ts_zu_epoch(jetzt)


def _takt_sekunden(takt):
    try: t=int(takt)
    except (TypeError,ValueError): return None
    return t if t>0 else None


def _health_verlauf(health_daten, shop):
    """Health.verlauf eines Shops; alte Dateien haben nur last_ts/last_status."""
    if not isinstance(health_daten,dict): return []
    e=health_daten.get(shop)
    if not isinstance(e,dict): return []
    verlauf=e.get("verlauf")
    if isinstance(verlauf,list):
        return [x for x in verlauf if isinstance(x,dict)]
    if e.get("last_ts") is not None and e.get("last_status"):
        return [{"ts":e.get("last_ts"),"status":e.get("last_status")}]
    return []


def _drop_fenster_tag(zeile, tz=None):
    """Tag eines Checks; ISO-Zeit zuerst, danach ein Zeitstempel."""
    iso = zeile.get("iso")
    if iso:
        try:
            return datetime.fromisoformat(str(iso)).date()
        except (TypeError, ValueError):
            pass
    try:
        ts = float(zeile.get("ts"))
        return (datetime.fromtimestamp(ts, tz) if tz
                else datetime.fromtimestamp(ts)).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _drop_fenster_zeile(shop, status, ts):
    zeile = {"shop": shop, "klass": status}
    if isinstance(ts, str):
        zeile["iso"] = ts
    else:
        zeile["ts"] = ts
    return zeile


def lerne_drop_fenster_aus_lokal(health_daten=None, event_liste=None, tz=None):
    """Drop-Fenster aus eigenen Health-Scans und Verfuegbarkeits-Events.

    Health liefert die breite Scan-Historie, Events die genauen Wechsel.
    Ein Event in derselben Stunde am selben Tag wie ein Health-Hit wird nicht
    doppelt gezaehlt; Events in anderen Stunden ergaenzen die Historie. Ohne
    Cloud-Kopplung und ohne zusaetzliche Requests.
    """
    health=[]
    for shop in (health_daten or {}):
        for eintrag in _health_verlauf(health_daten, shop):
            health.append(_drop_fenster_zeile(shop, eintrag.get("status"),
                                              eintrag.get("ts")))
    events=[]
    for eintrag in event_liste or []:
        if not isinstance(eintrag, dict):
            continue
        if str(eintrag.get("typ") or "") != "verfuegbar":
            continue
        shop=str(eintrag.get("haendler") or eintrag.get("shop") or "")
        if not shop:
            continue
        events.append(_drop_fenster_zeile(shop, "hit", eintrag.get("ts")))
    health_keys=set()
    for zeile in health:
        if zeile.get("klass") != "hit":
            continue
        stunde=_drop_fenster_stunde(zeile, tz)
        tag=_drop_fenster_tag(zeile, tz)
        if stunde is not None and tag is not None:
            health_keys.add((zeile["shop"], tag, stunde))
    combined=list(health)
    for zeile in events:
        stunde=_drop_fenster_stunde(zeile, tz)
        tag=_drop_fenster_tag(zeile, tz)
        if (stunde is not None and tag is not None
                and (zeile["shop"], tag, stunde) in health_keys):
            continue
        combined.append(zeile)
    return lerne_drop_fenster(combined, tz=tz)


def lerne_drop_fenster_aus_health(health_daten, tz=None):
    """Kompatibilitaet: nur der lokale Health-Verlauf."""
    return lerne_drop_fenster_aus_lokal(health_daten=health_daten, tz=tz)


def _abdeckung_fuer_zeitraum(shop,start,ende,health_daten=None,takt=None,
                             dauer=None,offen=False,jetzt=None):
    """Abdeckung und Herkunft aus den Health-Scans im Zeitraum.

    ``gesehen`` verlangt einen erfolgreichen Scan innerhalb des Fensters.
    Ohne Health-Eintrag ist die Abdeckung ``unbekannt`` - das ist ehrlicher
    als eine Luecke zu behaupten, wenn der 30er-Ring den Zeitraum nicht mehr
    abdeckt. ``kurz`` markiert nur abgeschlossene Fenster, deren Dauer unter
    dem eingestellten Takt liegt.
    """
    if health_daten is None: return {}
    start_ts=_ts_zu_epoch(start)
    if start_ts is None: return {}
    ende_ts=(_jetzt_epoch(jetzt) if ende is None else _ts_zu_epoch(ende))
    if ende_ts is None or ende_ts<start_ts: return {}
    verlauf=_health_verlauf(health_daten,shop)
    gesehen=False
    for e in verlauf:
        ts=_ts_zu_epoch(e.get("ts"))
        if ts is None: continue
        if ts<start_ts-ABDECKUNG_TOLERANZ or ts>ende_ts+ABDECKUNG_TOLERANZ:
            continue
        if str(e.get("status") or "") in ABDECKUNG_GUT:
            gesehen=True; break
    if gesehen:
        abdeckung,herkunft="gesehen","scan"
    elif verlauf:
        abdeckung,herkunft="luecke","ereignis"
    else:
        abdeckung,herkunft="unbekannt","ereignis"
    if dauer is None and not offen and ende is not None:
        dauer=_fenster_dauer(start,ende)
    try: dauer=int(dauer) if dauer is not None else None
    except (TypeError,ValueError): dauer=None
    takt=_takt_sekunden(takt)
    kurz=bool(not offen and dauer is not None and takt is not None
              and dauer<takt)
    return {"abdeckung":abdeckung,"herkunft":herkunft,
            "takt":takt,"kurz":kurz}


def abdeckung_labels(abdeckung,herkunft=None,kurz=False):
    """Kurze, sichtbare Labels fuer Abdeckung und Herkunft."""
    teile=[]
    if abdeckung=="gesehen": teile.append("GESEHEN")
    elif abdeckung=="luecke": teile.append("LÜCKE")
    elif abdeckung=="unbekannt": teile.append("OHNE DATEN")
    if herkunft=="scan": teile.append("SCAN")
    elif herkunft=="ereignis": teile.append("EREIGNIS")
    if kurz: teile.append("FENSTER KÜRZER ALS TAKT")
    return " · ".join(teile)


def erfolg_abdeckung_text(f):
    if not isinstance(f,dict) or "abdeckung" not in f: return ""
    return abdeckung_labels(f.get("abdeckung"),f.get("herkunft"),
                             bool(f.get("kurz")))


def ereignis_abdeckung(e,health_daten=None,takt=None,ende=None,jetzt=None):
    """Abdeckung eines Verlaufs-Eintrags; ``ende`` ist der naechste Wechsel."""
    if not isinstance(e,dict) or health_daten is None: return {}
    shop=str(e.get("haendler") or "")
    if not shop: return {}
    typ=e.get("typ")
    if typ=="ausverkauft":
        start=e.get("start") or e.get("ts")
        return _abdeckung_fuer_zeitraum(
            shop,start,e.get("ts"),health_daten,takt,
            dauer=e.get("dauer"),jetzt=jetzt)
    if typ=="verfuegbar":
        start=e.get("start") or e.get("ts")
        return _abdeckung_fuer_zeitraum(
            shop,start,ende,health_daten,takt,
            offen=ende is None,jetzt=jetzt)
    return {}


def ereignis_abdeckung_text(e,health_daten=None,takt=None,ende=None,
                            jetzt=None):
    info=ereignis_abdeckung(e,health_daten,takt,ende,jetzt)
    if not info: return ""
    return abdeckung_labels(info.get("abdeckung"),info.get("herkunft"),
                            bool(info.get("kurz")))


def erfolgs_fenster(ereignisse, jetzt=None, max_alter=ERFOLG_OFFEN_MAX,
                    letzte_scans=None, health_daten=None, takt=None):
    """Verfuegbarkeitsfenster aus dem Event-Ticker.

    Paart jeden Wechsel auf ``verfuegbar`` mit dem naechsten Wechsel auf
    ``ausverkauft`` desselben Shops. Rueckgabe neueste zuerst.

    ``offen: True`` traegt nur ein Fenster ohne Abschluss, dessen letzter
    ``verfuegbar``-Wechsel hoechstens ``max_alter`` Sekunden zurueckliegt -
    oder dessen Shop laut ``letzte_scans`` seither erfolgreich als verfuegbar
    geprueft wurde (Shop -> Epoch- oder ISO-Zeitstempel). Aeltere offene
    Fenster tragen ``veraltet: True``, ``letzter_stand`` und keine Dauer; sie
    zeigen also den letzten bekannten Stand.
    """
    try: max_alter=max(0,int(max_alter))
    except (TypeError,ValueError): max_alter=ERFOLG_OFFEN_MAX
    scans=letzte_scans if isinstance(letzte_scans,dict) else {}
    offen = {}
    fenster = []
    for e in ereignisse or []:
        if not isinstance(e, dict):
            continue
        shop = str(e.get("haendler") or "")
        typ = e.get("typ")
        if not shop or typ not in ("verfuegbar", "ausverkauft"):
            continue
        if typ == "verfuegbar":
            # Ein zweites verfuegbar ohne Abschluss verschiebt den Start nicht.
            alt = offen.get(shop) or {}
            offen[shop] = {
                "haendler": shop,
                "start": alt.get("start") or e.get("ts") or e.get("start"),
                "gesehen": e.get("ts") or alt.get("gesehen"),
                "ende": None,
                "dauer": None,
                "preis": e.get("preis") if e.get("preis") is not None else alt.get("preis"),
                "url": e.get("url") or alt.get("url"),
                "offen": True,
            }
            continue
        alt = offen.pop(shop, None) or {}
        start = alt.get("start") or e.get("start")
        if not start:
            continue
        dauer = e.get("dauer")
        if dauer is None:
            dauer = _fenster_dauer(start, e.get("ts"))
        try:
            dauer = max(0, int(dauer)) if dauer is not None else None
        except (TypeError, ValueError):
            dauer = None
        preis = alt.get("preis")
        if preis is None:
            preis = e.get("preis")
        f={
            "haendler": shop,
            "start": start,
            "ende": e.get("ts"),
            "dauer": dauer,
            "preis": preis,
            "url": alt.get("url") or e.get("url"),
            "offen": False,
        }
        if health_daten is not None:
            f.update(_abdeckung_fuer_zeitraum(
                shop,start,e.get("ts"),health_daten,takt,dauer=dauer))
        fenster.append(f)
    for f in offen.values():
        stand = f.get("gesehen") or f.get("start")
        alter = _alter_sekunden(stand, jetzt)
        if alter is not None:
            # Ein frischer Erfolgs-Scan bestaetigt den Stand, auch wenn seit
            # dem Wechsel kein neues Ereignis geschrieben wurde.
            scan_alter=_alter_scan(scans.get(f.get("haendler")), jetzt)
            if scan_alter is not None:
                alter=min(alter,scan_alter)
        if alter is not None and alter <= max_alter:
            f["offen"] = True
        else:
            # Kein Abschluss, aber zu alt fuer eine Aussage ueber jetzt.
            f["offen"] = False
            f["veraltet"] = True
            f["letzter_stand"] = stand
        f.pop("gesehen", None)
        if health_daten is not None:
            f.update(_abdeckung_fuer_zeitraum(
                f.get("haendler"),f.get("start"),None,health_daten,takt,
                offen=True,jetzt=jetzt))
        fenster.append(f)

    def _sortiert(f):
        dt = _iso_dt(f.get("start"))
        return dt.timestamp() if dt else 0.0

    return sorted(fenster, key=_sortiert, reverse=True)


def erfolg_zeile(f):
    """Eine Erfolgszeile: '13.11., 10:35 · Shop · 899,00 € · FENSTER 1 MIN'."""
    if not isinstance(f, dict):
        return ""
    teile = []
    zeit = kurz_zeit(f.get("start"))
    if zeit:
        teile.append(zeit)
    teile.append(str(f.get("haendler") or "?"))
    preis = f.get("preis")
    if preis is not None:
        try:
            teile.append(format_preis(float(preis)))
        except (TypeError, ValueError):
            pass
    if f.get("offen"):
        teile.append("OFFEN")
    elif f.get("veraltet"):
        teile.append("LETZTER STAND")
    elif f.get("dauer") is not None:
        teile.append("FENSTER " + dauer_text(f["dauer"]))
    return " · ".join(teile)


class Events:
    """Append-only-Journal der Zustandswechsel, aelteste zuerst.

    Eine Zeile ist ein JSON-Objekt. Normale Schreiber haengen nur hinten an;
    bei Erreichen der Zeilen- oder Groessengrenze rotiert die aktive Datei
    nach ``.1``. Der Lock schuetzt App und Hintergrunddienst. ``clear()`` ist
    die bewusste Ausnahme: Es leert Journal und Archive gemeinsam.
    """
    def __init__(self,path=None,max_events=None,max_lines=None,
                 max_bytes=None,max_segments=None):
        self.path=path or os.path.join(_data_dir(),EVENTS_FILE)
        self.max_events=max(1,int(max_events or MAX_EVENTS))
        self.max_lines=max(1,int(max_lines or EVENTS_MAX_LINES))
        self.max_bytes=max(1024,int(max_bytes or EVENTS_MAX_BYTES))
        self.max_segments=max(2,int(max_segments or EVENTS_MAX_SEGMENTS))
        self._lock_path=self.path+".lock"
        self.data=[]
        self._hashes=set()
        self._active_zeilen=0
        self._active_bytes=0
        self._stamp=None
        ordner=os.path.dirname(self.path)
        if ordner:
            try: os.makedirs(ordner,exist_ok=True)
            except OSError: pass
        # Beim ersten Start darf nur ein Prozess migrieren. Ist der Lock
        # gerade belegt, wird wenigstens der vorhandene Stand gelesen.
        if not self._mit_lock(self._initialisieren): self._laden()
    def _initialisieren(self):
        self._migrieren()
        self._laden()
        return True
    def _legacy_pfad(self):
        """Alte JSON-Array-Datei neben dem neuen Journal, sonst None."""
        if not self.path.endswith(".jsonl"): return None
        if os.path.basename(self.path)==EVENTS_FILE:
            return os.path.join(os.path.dirname(self.path),EVENTS_LEGACY_FILE)
        return os.path.splitext(self.path)[0]+".json"
    def _migrieren(self):
        """Einmalige Migration von ps5pro_events.json nach JSONL."""
        if os.path.exists(self.path): return
        alt=self._legacy_pfad()
        if not alt or not os.path.exists(alt): return
        tmp=self.path+".tmp"
        try:
            with open(alt,"r",encoding="utf-8") as f: daten=json.load(f)
            if not isinstance(daten,list): return
            with open(tmp,"w",encoding="utf-8",newline="\n") as f:
                for e in daten:
                    if not isinstance(e,dict): continue
                    f.write(json.dumps(e,ensure_ascii=False,
                                       separators=(",",":"))+"\n")
            os.replace(tmp,self.path)
            try: os.replace(alt,alt+".migrated")
            except OSError: pass
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
    def _segmente(self):
        """Aeltestes Archiv zuerst, aktive Datei zuletzt."""
        return ([self.path+f".{i}" for i in range(self.max_segments-1,0,-1)]
                +[self.path])
    def _datei_stamp(self):
        stamp=[]
        for p in self._segmente():
            try:
                s=os.stat(p); stamp.append((p,s.st_mtime_ns,s.st_size))
            except OSError: pass
        return tuple(stamp)
    @staticmethod
    def _fingerprint(ereignis):
        roh=json.dumps(ereignis,ensure_ascii=False,sort_keys=True,
                       separators=(",",":"))
        return hashlib.sha256(roh.encode("utf-8")).hexdigest()
    @staticmethod
    def _aktiver_stand(pfad):
        try: bytes_=os.path.getsize(pfad)
        except OSError: bytes_=0
        try:
            with open(pfad,"r",encoding="utf-8") as f:
                zeilen=sum(1 for _ in f)
        except OSError: zeilen=0
        return zeilen,bytes_
    def _laden(self):
        daten=[]; hashes=set()
        for p in self._segmente():
            try:
                with open(p,"r",encoding="utf-8") as f:
                    for zeile in f:
                        zeile=zeile.strip()
                        if not zeile: continue
                        try: e=json.loads(zeile)
                        except ValueError: continue
                        if not isinstance(e,dict): continue
                        try: fp=self._fingerprint(e)
                        except (TypeError,ValueError): continue
                        # Dedupe auch ueber Rotationsgrenzen hinweg.
                        if fp in hashes: continue
                        daten.append(e); hashes.add(fp)
            except OSError: pass
        if len(daten)>self.max_events:
            daten=daten[-self.max_events:]
            hashes=set(self._fingerprint(e) for e in daten)
        self.data=daten; self._hashes=hashes
        self._active_zeilen,self._active_bytes=self._aktiver_stand(self.path)
        self._stamp=self._datei_stamp()
        return daten
    def reload(self):
        """Journal nur neu lesen, wenn sich eine Datei geaendert hat.

        SETUP-Zaehler, Detailansicht und Ticker fragen bei jedem Oeffnen; der
        Hintergrunddienst schreibt in einem eigenen Prozess. Vorher wurde die
        Datei dabei jedes Mal neu geparst.
        """
        stamp=self._datei_stamp()
        if stamp==self._stamp: return self
        self._laden()
        return self
    def _lock_erwerben(self):
        ende=time.time()+EVENTS_LOCK_TIMEOUT
        while True:
            try:
                fd=os.open(self._lock_path,
                           os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                try:
                    os.write(fd,(str(os.getpid())+"\n").encode("ascii"))
                finally:
                    os.close(fd)
                return True
            except FileExistsError:
                try:
                    if time.time()-os.path.getmtime(self._lock_path)>EVENTS_LOCK_STALE:
                        os.unlink(self._lock_path)
                        continue
                except OSError: pass
                if time.time()>=ende: return False
                time.sleep(0.01)
            except OSError as e:
                # Windows meldet beim gleichzeitigen Anlegen/Loeschen der
                # Lock-Datei sporadisch eine Sharing Violation (32/33). Nur
                # dieser Race wird wiederholt; ein echter Rechte- oder
                # Pfadfehler scheitert sofort statt 10 s zu blockieren.
                if getattr(e,"winerror",None) not in (32,33): return False
                if time.time()>=ende: return False
                time.sleep(0.01)
    def _mit_lock(self,aktion):
        if not self._lock_erwerben(): return None
        try: return aktion()
        finally:
            try: os.unlink(self._lock_path)
            except OSError: pass
    def _anhaengen(self,ereignis):
        """Eine Zeile append-only schreiben, danach ggf. rotieren."""
        try:
            # Ein abgebrochener Schreibvorgang darf die naechste Zeile nicht
            # mit seiner halben Zeile verbinden.
            if os.path.exists(self.path):
                with open(self.path,"rb") as f:
                    f.seek(0,2)
                    if f.tell():
                        f.seek(-1,2)
                        if f.read(1)!=b"\n":
                            with open(self.path,"ab") as a: a.write(b"\n")
                            self._active_zeilen+=1
            zeile=json.dumps(ereignis,ensure_ascii=False,
                             separators=(",",":"))+"\n"
            with open(self.path,"a",encoding="utf-8",newline="\n") as f:
                f.write(zeile)
                f.flush()
                os.fsync(f.fileno())
            self._active_zeilen+=1
            self._active_bytes=os.path.getsize(self.path)
            if (self._active_zeilen>=self.max_lines or
                    self._active_bytes>=self.max_bytes):
                self._rotieren()
            return True
        except Exception:
            return False
    def _rotieren(self):
        """Aktive Datei nach .1 schieben; aeltestes Archiv faellt weg."""
        archive=self.max_segments-1
        if archive<1: return
        try: os.unlink(self.path+f".{archive}")
        except OSError: pass
        for i in range(archive-1,0,-1):
            src=self.path+f".{i}"; dst=self.path+f".{i+1}"
            if os.path.exists(src):
                try: os.replace(src,dst)
                except OSError: pass
        if os.path.exists(self.path):
            try: os.replace(self.path,self.path+".1")
            except OSError: pass
        self._active_zeilen=0; self._active_bytes=0
    def add(self,ereignis):
        if not isinstance(ereignis,dict): return False
        ereignis=dict(ereignis)
        try: fp=self._fingerprint(ereignis)
        except (TypeError,ValueError): return False
        def _schreiben():
            # Fremden Stand unter Lock uebernehmen: nach einem LEEREN im
            # anderen Prozess darf dieser Prozess nichts Altes zurueckholen.
            self.reload()
            if fp in self._hashes: return False
            if not self._anhaengen(ereignis): return False
            self.data.append(ereignis); self._hashes.add(fp)
            if len(self.data)>self.max_events:
                self.data=self.data[-self.max_events:]
                self._hashes=set(self._fingerprint(e) for e in self.data)
            self._stamp=self._datei_stamp()
            return True
        return bool(self._mit_lock(_schreiben))
    def all(self):
        return [dict(e) for e in self.data]
    def letzte(self,n=20):
        try: n=max(1,int(n))
        except (TypeError,ValueError): n=20
        return [dict(e) for e in self.data[-n:]][::-1]
    def fuer_shop(self,name):
        return [dict(e) for e in self.data if e.get("haendler")==name]
    def letztes(self,name):
        """Juengstes Ereignis eines Shops oder None."""
        for e in reversed(self.data):
            if e.get("haendler")==name: return dict(e)
        return None
    def clear(self):
        """Journal und alle Rotationen unter Lock leeren."""
        def _leeren():
            alt=self._legacy_pfad()
            dateien=self._segmente()
            if alt: dateien=dateien+[alt,alt+".migrated"]
            for p in dateien:
                try: os.unlink(p)
                except OSError: pass
            tmp=self.path+".tmp"
            try:
                with open(tmp,"w",encoding="utf-8") as f:
                    f.flush(); os.fsync(f.fileno())
                os.replace(tmp,self.path)
            except Exception:
                try: os.unlink(tmp)
                except OSError: pass
                return False
            self.data=[]; self._hashes=set()
            self._active_zeilen=0; self._active_bytes=0
            self._stamp=self._datei_stamp()
            return True
        # Wie bisher ohne Rueckgabewert: Aufrufer pruefen den Zustand ueber
        # ``all()``; ein fehlgeschlagener Lock darf die UI nicht ausnehmen.
        self._mit_lock(_leeren)


_EVENTS=None


def events():
    """Prozessweiter Zugriff auf das Ereignis-Journal."""
    global _EVENTS
    if _EVENTS is None: _EVENTS=Events()
    return _EVENTS


def reset_events():
    """Nach einem Wechsel des Datenverzeichnisses neu aufsetzen (Tests)."""
    global _EVENTS
    _EVENTS=None
    return events()


class History:
    def __init__(self):
        self.path=os.path.join(_data_dir(),HISTORY_FILE)
        self._dirty=False
        try:
            with open(self.path,"r",encoding="utf-8") as f: data=json.load(f)
            self.data=data if isinstance(data,dict) else {}
        except Exception: self.data={}
        # Alte Dateien haben nur den letzten Preis. Daraus einen Startpunkt der
        # Serie machen, damit die Sparkline ohne Wartezeit etwas anzeigen kann.
        for n,e in list(self.data.items()):
            if not isinstance(e,dict):
                self.data.pop(n,None); continue
            serie=self._saubere_serie(e.get("serie"))
            if not serie and e.get("zeit") is not None and e.get("preis") is not None:
                try: serie=[[str(e["zeit"]),float(e["preis"])]]
                except (TypeError,ValueError): serie=[]
            e["serie"]=serie
    def get_last(self,n): return self.data.get(n,{}).get("preis")
    def get_verfuegbar(self,n):
        """Letzter bekannter Verfuegbarkeitszustand: True, False oder None."""
        e=self.data.get(n)
        if not isinstance(e,dict) or "verfuegbar" not in e: return None
        v=e.get("verfuegbar")
        return v if isinstance(v,bool) else None
    def get_zuletzt_verfuegbar(self,n):
        """Zeitpunkt des letzten 'verfuegbar' (ISO) oder None.

        Bleibt beim Wechsel auf ausverkauft stehen; nur so laesst sich die
        Dauer des abgelaufenen Fensters und 'zuletzt verfuegbar am' zeigen.
        """
        e=self.data.get(n)
        if not isinstance(e,dict): return None
        ts=e.get("verfuegbar_zeit")
        return str(ts) if ts else None
    @staticmethod
    def _sekunden_seit(iso):
        dt=_iso_dt(iso)
        if dt is None: return None
        try: return max(0,int((datetime.now()-dt).total_seconds()))
        except (TypeError,ValueError): return None
    def get_serie(self,n):
        e=self.data.get(n)
        return self._saubere_serie(e.get("serie")) if isinstance(e,dict) else []
    def get_tief(self,n):
        """Niedrigster je gespeicherter Preis einer Serie (nicht nur letzter Scan)."""
        serie=self.get_serie(n)
        if serie: return min(p for _,p in serie)
        return self.get_last(n)
    def _saubere_serie(self,serie):
        out=[]
        if not isinstance(serie,list): return out
        for punkt in serie:
            try:
                ts=str(punkt[0]); preis=float(punkt[1])
            except (TypeError,ValueError,IndexError): continue
            if not ts: continue
            out.append([ts,preis])
        return out[-MAX_SERIE_PUNKTE:]
    def update(self,results,persist=True):
        """Ergebnisse uebernehmen; standardmaessig sofort auf Platte sichern.

        ``persist=False`` haelt die Aenderung nur im Speicher. Die App nutzt
        das fuer jeden einzelnen Shop waehrend einer Runde und schreibt die
        Datei am Rundenende einmal; das Event-Journal wird trotzdem sofort
        fortgeschrieben. ``erkannt`` aus dem Abruf ist der Zeitstempel des
        Wechsels, nicht das Ende der ganzen Runde.
        """
        default_now=datetime.now().isoformat(timespec="seconds")
        for r in results:
            if not isinstance(r,dict) or not r.get("haendler"): continue
            name=r["haendler"]
            now=str(r.get("erkannt") or default_now)
            if _iso_dt(now) is None: now=default_now
            alt=dict(self.data.get(name) or {})
            serie=self._saubere_serie(alt.get("serie"))
            # Verfuegbarkeit auch ohne Preis festhalten: nur so laesst sich
            # ein spaeterer Restock von einem gewoehnlichen Scan unterscheiden.
            av=True if r.get("klass") in ("hit","expensive") else (
                False if r.get("klass")=="unavail" else None)
            vorher=alt.get("verfuegbar") if isinstance(alt.get("verfuegbar"),bool) else None
            if av is not None:
                alt["verfuegbar"]=av
                # Ein neues Fenster startet jetzt; beim Zurueckspringen bleibt
                # der Start stehen, sonst waere die Dauer verloren. Die Uhrzeit
                # des Endes steckt bereits im Ereignis (start + ts).
                if av: alt["verfuegbar_zeit"]=now
            if r.get("preis") is not None:
                try: preis=float(r["preis"])
                except (TypeError,ValueError): preis=None
                if preis is not None:
                    # Nur echte Aenderungen anhaengen, sonst wird die Serie bei
                    # jedem 15-Minuten-Scan mit identischen Preisen geflutet.
                    if not serie or abs(serie[-1][1]-preis)>0.005:
                        serie.append([now,preis])
                    else:
                        serie[-1][0]=now
                    alt["preis"]=preis; alt["zeit"]=now
                    alt["serie"]=serie[-MAX_SERIE_PUNKTE:]
            # Detail A: nur echte Wechsel landen im Ticker; beim Wechsel auf
            # ausverkauft kommt die Dauer des abgelaufenen Fensters mit.
            if av is not None and vorher is not None and av!=vorher:
                start=alt.get("verfuegbar_zeit") if not av else now
                verlauf_ereignis={"typ":"verfuegbar" if av else "ausverkauft",
                                  "haendler":name,"ts":now,"start":start,
                                  "dauer":None if av else _fenster_dauer(start,now),
                                  "preis":alt.get("preis"),
                                  "url":r.get("url")}
                events().add(verlauf_ereignis)
            if alt: self.data[name]=alt
        self._dirty=True
        if persist: self._speichern()
    def _speichern(self):
        """Aktuellen Stand atomar schreiben; Fehler bleiben still wie bisher."""
        try:
            tmp=self.path+".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(self.data,f,ensure_ascii=False,indent=1)
            os.replace(tmp,self.path)
            self._dirty=False
        except Exception: pass
    def flush(self):
        """Offene, nicht persistierte Aenderungen einmalig schreiben."""
        if not self._dirty: return False
        self._speichern()
        return not self._dirty

class Kaeufe:
    """Kaufprotokoll: Haendler, Preis und Zeitpunkt der "Gekauft"-Markierung."""
    def __init__(self,path=None):
        self.path=path or os.path.join(_data_dir(),KAEUFE_FILE)
        self.data=self._laden()
    def _laden(self):
        try:
            with open(self.path,"r",encoding="utf-8") as f: data=json.load(f)
        except Exception: return []
        return [dict(e) for e in data if isinstance(e,dict)] if isinstance(data,list) else []
    def alle(self): return [dict(e) for e in self.data]
    def letzter(self,haendler):
        for e in reversed(self.data):
            if str(e.get("haendler") or "")==str(haendler or ""): return dict(e)
        return None
    def merken(self,r,jetzt=None):
        """Einen Kauf festhalten. Rueckgabe des Eintrags oder None."""
        if not isinstance(r,dict): return None
        ts=jetzt if isinstance(jetzt,datetime) else datetime.now()
        try: preis=None if r.get("preis") is None else float(r["preis"])
        except (TypeError,ValueError): preis=None
        eintrag={"haendler":str(r.get("haendler") or "?"),"preis":preis,
                 "ts":ts.replace(microsecond=0).isoformat()}
        self.data=(self.data+[eintrag])[-MAX_KAEUFE:]
        try: _json_schreiben(self.path,self.data)
        except Exception: pass
        return eintrag


def stumm_bis(settings,haendler,jetzt=None):
    """Ende der zeitlichen Stummschaltung (epoch) oder None, wenn abgelaufen."""
    bis=_setting(settings,"mute_bis",{}) or {}
    if not isinstance(bis,dict): return None
    try: ende=float(bis.get(str(haendler or "")) or 0)
    except (TypeError,ValueError): return None
    jetzt=time.time() if jetzt is None else jetzt
    return ende if ende>jetzt else None


class Settings:
    def __init__(self):
        self.path=os.path.join(_data_dir(),SETTINGS_FILE)
        try:
            with open(self.path,"r",encoding="utf-8") as f: data=json.load(f)
            self.data=data if isinstance(data,dict) else {}
        except Exception: self.data={}
    def get(self,k,d=None): return self.data.get(k,d)
    def set(self,k,v): self.data[k]=v; self.save()
    def save(self):
        try:
            tmp=self.path+".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(self.data,f,ensure_ascii=False,indent=1)
            os.replace(tmp,self.path)
        except Exception: pass


def _setting(settings,k,d=None):
    try: return settings.get(k,d)
    except Exception: return d

def alarm_erlaubt(r,tief,settings,jetzt=None):
    """Zentrale Alarm-Regel fuer App und Service.

    Ein Treffer darf nur melden, wenn er neu, sofort lieferbar, kein
    Gebraucht-/Refurbished-Angebot und nicht stummgeschaltet ist. Optional
    zaehlen nur echte Tiefstpreise und es gelten Ruhezeiten.
    """
    if not isinstance(r,dict) or r.get("preis") is None: return False
    # Chance ist eine Information, kein Verfuegbarkeitsalarm. Lotterie,
    # Einladung und Marktabholung melden bewusst nie "jetzt kaufen".
    if r.get("klass")=="chance": return False
    if ist_gebraucht(r.get("condition")): return False
    try:
        schwelle=float(_setting(settings,"confidence_min",0) or 0)
        if schwelle>0 and float(r.get("confidence",100))<schwelle: return False
    except (TypeError,ValueError): pass
    # "Nur bestaetigte Treffer" heisst genau das: ohne zweiten Abruf kein Alarm.
    if _setting(settings,"alarm_nur_bestaetigt",False) and r.get("verify")!="bestaetigt":
        return False
    if _setting(settings,"notify_sofort",True) and r.get("sofort") is False:
        return False
    stumm=_setting(settings,"mute_haendler",[]) or []
    try:
        if r.get("haendler") in set(stumm): return False
    except TypeError: pass
    # "Gekauft" schaltet den Shop 24 Stunden stumm: nach dem Kauf ist jede
    # weitere Meldung fuer denselben Shop nur Laerm.
    if stumm_bis(settings,r.get("haendler")): return False
    if _setting(settings,"quiet_hours",False):
        try:
            start=int(_setting(settings,"quiet_start",23)); end=int(_setting(settings,"quiet_end",7))
            h=(jetzt or datetime.now()).hour
            in_ruhe=(start<=h<end) if start<end else (h>=start or h<end)
            if in_ruhe: return False
        except (TypeError,ValueError): pass
    if _setting(settings,"notify_low_only",False) and tief is not None:
        try:
            preis=float(r["preis"]); grenze=float(tief)
            # Ein Restock auf dem bisherigen Tief ist kein neuer Tiefstpreis,
            # aber trotzdem die wichtigste Meldung des Tages.
            if not (r.get("_restock") and preis<=grenze+0.005) and preis>=grenze-0.005:
                return False
        except (TypeError,ValueError): pass
    return True


class Health:
    """Letzter Zustand pro Shop - macht stille Parser-Ausfaelle sichtbar."""
    def __init__(self,pfad=None):
        self.path=pfad or os.path.join(_data_dir(),HEALTH_FILE)
        self._lock=threading.Lock()
        try:
            with open(self.path,"r",encoding="utf-8") as f: data=json.load(f)
            self.data=data if isinstance(data,dict) else {}
        except Exception: self.data={}
    def record(self,r):
        name=r.get("haendler")
        if not name: return
        ts=time.time(); status=r.get("klass") or "unknown"
        fehler=bool(status in ("error","challenge","parser"))
        try: dauer=round(float(r.get("dauer")),1)
        except (TypeError,ValueError): dauer=None
        with self._lock:
            e=dict(self.data.get(name) or {})
            e["last_ts"]=ts; e["last_status"]=status
            e["last_error"]=r.get("fehler")
            e["checks"]=int(e.get("checks") or 0)+1
            if fehler:
                e["fail_streak"]=int(e.get("fail_streak") or 0)+1
                if status == "parser":
                    e["parser_streak"]=int(e.get("parser_streak") or 0)+1
                    e["parser_total"]=int(e.get("parser_total") or 0)+1
                else:
                    e["parser_streak"]=0
            else:
                e["ok_ts"]=ts; e["fail_streak"]=0
                e["successes"]=int(e.get("successes") or 0)+1
                e["parser_streak"]=0
            # Ringpuffer: aelteste zuerst, damit die zeitliche Reihenfolge
            # beim Lesen der Datei sofort erkennbar ist.
            verlauf=e.get("verlauf")
            verlauf=list(verlauf) if isinstance(verlauf,list) else []
            verlauf.append({"ts": datetime.now().isoformat(timespec="seconds"),
                            "status": status, "fehler": r.get("fehler"),
                            "dauer": dauer})
            e["verlauf"]=verlauf[-HEALTH_VERLAUF_MAX:]
            self.data[name]=e
    def save(self):
        """Einmal pro Scan schreiben statt 42-mal (Flash/Akku)."""
        with self._lock: self._save_locked()
    def all(self):
        with self._lock: return {k:dict(v) for k,v in self.data.items() if isinstance(v,dict)}
    def _save_locked(self):
        try:
            tmp=self.path+".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(self.data,f,ensure_ascii=False,indent=1)
            os.replace(tmp,self.path)
        except Exception: pass

_HEALTH=None
_HEALTH_LOCK=threading.Lock()

def health():
    global _HEALTH
    with _HEALTH_LOCK:
        if _HEALTH is None: _HEALTH=Health()
        return _HEALTH

def reset_health():
    global _HEALTH
    with _HEALTH_LOCK: _HEALTH=None


def _lies_bg_status():
    """Letzten BG-Status lesen; fehlt die Datei, ist das kein Fehler."""
    try:
        with open(os.path.join(_data_dir(),BG_STATUS_FILE),"r",encoding="utf-8") as f:
            d=json.load(f)
        return d if isinstance(d,dict) else None
    except Exception: return None


def health_export(health_daten=None, event_liste=None, bg_status=None, jetzt=None):
    """Health, Ereignisse und BG-Status als ein JSON-Objekt.

    Reine Leseansicht: Die Dateien werden nicht veraendert. Zeitstempel bleiben
    roh, damit sie sich mit externen Stempeln (bestell.bar) vergleichen lassen;
    ``exportiert`` und ``zeitzone`` liefern den Bezugspunkt.
    """
    jetzt=time.time() if jetzt is None else float(jetzt)
    if health_daten is None: health_daten=Health().all()
    if event_liste is None: event_liste=events().reload().all()
    if bg_status is None: bg_status=_lies_bg_status()
    if isinstance(bg_status,dict):
        bg_status=dict(bg_status)
        try:
            bg_status["ts_iso"]=datetime.fromtimestamp(
                float(bg_status.get("ts"))).isoformat(timespec="seconds")
        except (TypeError,ValueError): pass
    return {"schema":1,
            "exportiert":datetime.fromtimestamp(jetzt).isoformat(timespec="seconds"),
            "exportiert_ts":round(jetzt,3),
            "zeitzone":time.strftime("%z"),
            "dateien":{"health":HEALTH_FILE,"events":EVENTS_FILE,
                       "bg":BG_STATUS_FILE},
            "health":health_daten if isinstance(health_daten,dict) else {},
            "events":event_liste if isinstance(event_liste,list) else [],
            "bg":bg_status if isinstance(bg_status,dict) else None}


def health_export_json(**kwargs):
    """Export als Text fuer den Android-Teilen-Dialog."""
    return json.dumps(health_export(**kwargs),ensure_ascii=False,indent=1)


def _crash_schreiben(context,text):
    try:
        p=os.path.join(_data_dir(),CRASH_FILE)
        alt=""
        try:
            if os.path.exists(p):
                with open(p,"r",encoding="utf-8") as f: alt=f.read()[-40000:]
        except Exception: pass
        neu=alt+("\n\n=== %s %s ===\n"%(context,datetime.now().isoformat(timespec="seconds"))+
                 str(text)[-30000:])
        with open(p,"w",encoding="utf-8") as f: f.write(neu[-60000:])
    except Exception: pass

def install_crash_hook(context="app"):
    """Python-Ausnahmen landen sonst nur im Logcat und nicht in Play Vitals."""
    if getattr(sys,"_ps5pro_crash_hook",False): return
    sys._ps5pro_crash_hook=True
    alt=sys.excepthook
    def hook(typ,wert,tb):
        try: _crash_schreiben(context,"".join(traceback.format_exception(typ,wert,tb)))
        except Exception: pass
        try: alt(typ,wert,tb)
        except Exception: pass
    sys.excepthook=hook
    alt_t=threading.excepthook
    def thread_hook(args):
        try:
            _crash_schreiben(context,"Thread %s\n%s"%(getattr(args.thread,"name","?"),
                "".join(traceback.format_exception(args.exc_type,args.exc_value,args.exc_traceback))))
        except Exception: pass
        try: alt_t(args)
        except Exception: pass
    threading.excepthook=thread_hook

def read_crash_log(max_chars=12000):
    try:
        with open(os.path.join(_data_dir(),CRASH_FILE),"r",encoding="utf-8") as f:
            return f.read()[-max_chars:]
    except Exception: return ""

def clear_crash_log():
    try: os.remove(os.path.join(_data_dir(),CRASH_FILE))
    except Exception: pass

