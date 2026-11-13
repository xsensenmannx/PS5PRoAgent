"""Netz-, Preis- und Speicherlogik ohne Kivy.

Wird von der App (main.py) und vom Hintergrund-Service (service.py) benutzt.
Der Service laeuft in einem eigenen Prozess ohne UI - dort darf kein Kivy
importiert werden, deshalb liegt diese Logik hier getrennt.
"""
import os, sys, json, re, time, random, threading, traceback
from datetime import datetime, timezone
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
# Obergrenze fuer eine HTML-Antwort. Manche Shops liefern riesige Kategorieseiten;
# alles darueber ist fuer die Preiserkennung nutzlos und kostet nur Traffic.
MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_SERIE_PUNKTE = 120
# Webhook-Alarme: ein Versuch plus ein Retry, danach ist der Kanal fuer diesen
# Treffer erledigt. Der Cooldown verhindert Doppelmeldungen aus App und Dienst.
WEBHOOK_TIMEOUT = 8
WEBHOOK_COOLDOWN = 600
WEBHOOK_PRESETS = ("ntfy","telegram","discord","generisch")
# Shops, die fuer den Schnell-Modus zuerst geprueft werden. Alle Namen muessen
# in HAENDLER vorkommen; unbekannte werden ignoriert.
HOT_SHOPS = ["Amazon DE","MediaMarkt DE","Saturn DE","Otto DE",
             "Cyberport DE","Coolblue DE"]
BG_STATUS_FILE = "ps5pro_bg.json"
HEALTH_FILE = "ps5pro_health.json"
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
    _h("PS Direct DE","DE","https://direct.playstation.com/de-de/buy-consoles/playstation5-pro-console-2-tb"),
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
    _h("PS Direct AT","AT","https://direct.playstation.com/de-at/buy-consoles/playstation5-pro-console-2-tb"),
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
    _h("Otto AT","AT","https://www.otto.at/suche/playstation-5-pro-2tb/"),
    _h("GameStop AT","AT","https://www.gamestop.at/search?q=playstation+5+pro+konsole"),
    _h("Proshop AT","AT","https://www.proshop.at/Search?s=playstation+5+pro+2tb"),
    _h("Amazon AT","AT","https://www.amazon.at/s?k=playstation+5+pro+2tb"),
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
    "ddos protection","captcha","attention required"]
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
    "disc drive","laufwerk"]
VORBESTELL_MUSTER = ["vorbestell","vorbestellung","preorder","pre-order","backorder",
                     "back-order","reservier"]
GEBRAUCHT_MUSTER = ["usedcondition","used condition","refurbished","refurb",
                    "gebraucht","generalüberholt","generalueberholt","b-ware","b ware"]

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
        if "Product" in types: acc.append(node)
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

def _availability_flags(av):
    """(verfuegbar, sofort) aus einem schema.org-availability-Wert."""
    a=str(av or "").lower()
    if any(k in a for k in ("preorder","backorder","presale")): return True,False
    if any(k in a for k in ("instock","instoreonly","limited","onlineonly")): return True,True
    if any(k in a for k in ("outofstock","soldout","discontinued")): return False,False
    return None,None

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
         "verfuegbarkeit":None,"sofort":None}
    try: jl=extract_jsonld(html)
    except Exception: jl=[]
    prods=[]
    for j in jl: walk_products(j,prods)
    for p in prods:
        name=str(p.get("name",""))
        if not any(rx.search(name) for rx in PRODUKT_MUSTER): continue
        if not PRODUKT_2TB.search(name): continue
        low=name.lower()
        if any(ex in low for ex in PRODUKT_AUSSCHLUSS): continue
        res["ist_konsole"]=True
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

def extract_meta_preis(html):
    pats = [
        r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\']',
        r'<meta[^>]+itemprop=["\']price["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+itemprop=["\']price["\']',
        r'<[^>]+itemprop=["\']price["\'][^>]+(?:content|data-price)=["\']([^"\']+)',
        r'<[^>]+(?:content|data-price)=["\']([^"\']+)["\'][^>]+itemprop=["\']price["\']',
        r'<[^>]+itemprop=["\'](?:price|lowPrice)["\'][^>]*>([^<]{1,40})</',
        r'data-price=["\']([^"\']+)["\']',
        r'"(?:price|priceValue)"\s*:\s*"?((?:\d{1,3}(?:\.\d{3})+|\d+)[.,]\d{2})"?',
        r'((?:\d{1,3}(?:\.\d{3})+|\d+)[.,]\d{2})\s*(?:€|EUR|&euro;|&#8364;)',
        r'(?:€|EUR|&euro;|&#8364;)\s*((?:\d{1,3}(?:\.\d{3})+|\d+)[.,]\d{2})'
    ]
    for pat in pats:
        try:
            for m in re.finditer(pat,html,re.I):
                p=parse_preis_str(m.group(1))
                if p is not None and MIN_PREIS<=p<=1500: return p
        except re.error: continue
    return None

def extract_meta_verfuegbarkeit(html):
    """schema.org-Verfuegbarkeit aus Meta-Tags oder Microdata."""
    pats = [
        r'<meta[^>]+(?:property|name)=["\'](?:og|product):availability["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og|product):availability["\']',
        r'<link[^>]+itemprop=["\']availability["\'][^>]+href=["\']([^"\']+)',
        r'<meta[^>]+itemprop=["\']availability["\'][^>]+content=["\']([^"\']+)',
    ]
    for pat in pats:
        for m in re.finditer(pat,html,re.I):
            v,sofort=_availability_flags(m.group(1))
            if v is not None: return v,sofort
    return None,None


def detect_challenge(low): return any(p in low for p in CHALLENGE_PATTERNS)

def pruefe_nur_konsole(html, st):
    if st.get("ist_konsole"): return True
    # Beide Muster sind re.I - ein zusaetzliches html.lower() wuerde nur eine
    # zweite Kopie der Seite im Speicher anlegen (bei Shops leicht 2-6 MB).
    if not any(rx.search(html) for rx in PRODUKT_MUSTER): return False
    return bool(PRODUKT_2TB.search(html))

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

def remote_parser_ergebnis(html, parser):
    """Wendet die optionalen Remote-Regeln auf eine bereits geladene Seite an."""
    out={}
    if not isinstance(parser,dict): return out
    p=_remote_preis(html,parser)
    if p is not None: out["preis"]=p
    v,sofort=_remote_verfuegbarkeit(html,parser)
    if v is not None: out["verfuegbar"]=v
    if sofort is not None: out["sofort"]=sofort
    return out

def ist_sofort_verfuegbar(html):
    """Text-Fallback: Vorbestellung/Backorder ist keine sofortige Verfuegbarkeit."""
    low=html.lower()
    if any(k in low for k in VORBESTELL_MUSTER): return False
    if any(k in low for k in POSITIV): return True
    return None

def ist_gebraucht(condition):
    return str(condition or "").lower() in ("used","refurbished","damaged")

def classify(v,p,m):
    if not v: return "unavail"
    if p is None: return "unknown"
    if m is None or p<=m: return "hit"
    return "expensive"

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
            self.data[u]={"etag":etag,"last_modified":last_modified,"result":result}
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


def _try_url(u, att, proxy=None, force=False):
    """Eine Anfrage. Rueckgabe (html, fehler, meta).

    meta["not_modified"] signalisiert einen 304. Bedingte Header gehen nur beim
    ersten Versuch mit: ein Cache-Buster im Retry wuerde den Cache ohnehin
    umgehen, und ein 304 auf einen Retry waere wertlos. ``force`` ueberspringt
    die Validatoren komplett - die Verifikation eines Treffers braucht den
    echten aktuellen Stand, keinen 304 aus dem letzten Scan.
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
                r.close(); return None,f"HTTP {r.status_code}",meta
            roh,zu_gross=_read_capped(r)
            if zu_gross: return None,"Antwort zu gross",meta
            enc=r.encoding or "utf-8"
            try: return roh.decode(enc,errors="replace"),None,meta
            except LookupError: return roh.decode("utf-8",errors="replace"),None,meta
        req=Request(uu,headers=hd)
        with urlopen(req,timeout=TIMEOUT) as resp:
            meta["etag"]=resp.headers.get("ETag"); meta["last_modified"]=resp.headers.get("Last-Modified")
            roh=resp.read(MAX_HTML_BYTES+1)
            if len(roh)>MAX_HTML_BYTES: return None,"Antwort zu gross",meta
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

def fetch_mit_cache(urls, cancel=None, force=False):
    """Wie fetch_html_multi, liefert zusaetzlich ein 304-Ergebnis aus dem Cache.

    ``cancel`` ist ein optionales threading.Event. Es wird vor jedem Versuch
    und vor jeder Retry-Pause geprueft; ein laufender HTTP-Request selbst kann
    nicht unterbrochen werden, aber danach wird kein weiterer Versuch gestartet.
    ``force`` laedt die Seite ohne ETag/Last-Modified neu (Treffer-Verifikation).
    """
    last=None
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
            h,e,meta=(_try_url(u,att,proxy,force=True) if force
                      else _try_url(u,att,proxy))
            if _abgebrochen(cancel): raise ScanAbgebrochen
            if meta.get("not_modified"):
                if force:
                    cache.drop(u); last="HTTP 304"; continue
                eintrag=cache.get(u)
                if eintrag and isinstance(eintrag.get("result"),dict):
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
                return h,u,None,meta
            last=e
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

def _res(h,preis,klass,dauer,err,final_url=None,signal=None,condition=None,
         seller=None,verfuegbarkeit=None,sofort=None):
    return {"haendler":h["name"],"url":final_url or h["urls"][0],"land":h["land"],
            "preis":preis,"klass":klass,"dauer":round(dauer,1),
            "zeit":datetime.now().strftime("%H:%M:%S"),"fehler":err,
            "signal":signal or "unbekannt","condition":condition,"seller":seller,
            "verfuegbarkeit":verfuegbarkeit,"sofort":sofort}

def scan_einen(h, cancel=None, force=False):
    st=time.time()
    try:
        if _abgebrochen(cancel): raise ScanAbgebrochen
        html,fu,cached,meta=fetch_mit_cache(h["urls"], cancel=cancel, force=force); d=time.time()-st
        if _abgebrochen(cancel): raise ScanAbgebrochen
        if cached is not None:
            p=cached.get("preis"); v=bool(cached.get("verfuegbar"))
            res=_res(h,p,classify(v,p,MAX_PREIS),d,None,fu,
                     signal=cached.get("signal"),condition=cached.get("condition"),
                     seller=cached.get("seller"),
                     verfuegbarkeit=cached.get("verfuegbarkeit"),
                     sofort=cached.get("sofort"))
            res["_cache"]=True
            return res
        if detect_challenge(html[:3000].lower()):
            return _res(h,None,"challenge",d,"Bot-Challenge",fu)
        s=extract_structured(html)
        if not pruefe_nur_konsole(html,s):
            return _res(h,None,"unknown",d,"nicht PS5 Pro 2TB",fu)
        remote=remote_parser_ergebnis(html,h.get("parser"))
        meta_v,meta_sofort=extract_meta_verfuegbarkeit(html)
        v=remote.get("verfuegbar")
        # Strukturierte Daten (JSON-LD) haben Vorrang vor einem eventuell
        # veralteten Meta-Tag; erst danach greifen Meta und Text-Fallback.
        v_explizit=v is not None
        if v is None:
            v=s.get("verfuegbar"); v_explizit=v is not None
        if v is None:
            v=meta_v; v_explizit=v is not None
        if v is None:
            v,v_explizit=_verfuegbarkeit_aus_text(html)
        p=remote.get("preis")
        if p is None: p=s.get("preis")
        if p is None: p=extract_meta_preis(html)
        # HTTP 200, Produkt erkannt, aber kein Preis: Das ist ein Parserfehler,
        # solange die Seite nicht ausdruecklich "nicht verfuegbar" sagt. Eine
        # ausverkaufte Produktseite bleibt damit unavail und wird nicht als
        # kaputter Parser gezaehlt.
        if p is None and not (v_explizit and v is False):
            return _res(h,None,"parser",d,"Parser: kein Preis",fu,
                        signal="parser",condition=s.get("condition"),
                        seller=s.get("seller"),
                        verfuegbarkeit=s.get("verfuegbarkeit"),
                        sofort=s.get("sofort"))
        signal=("remote" if remote else
                "jsonld" if s.get("preis") is not None else
                "meta" if p is not None else "text")
        sofort=remote.get("sofort")
        if sofort is None: sofort=s.get("sofort")
        if sofort is None: sofort=meta_sofort
        if sofort is None and v: sofort=ist_sofort_verfuegbar(html)
        if _abgebrochen(cancel): raise ScanAbgebrochen
        res=_res(h,p,classify(v,p,MAX_PREIS),d,None,fu,
                 signal=signal,condition=s.get("condition"),seller=s.get("seller"),
                 verfuegbarkeit=s.get("verfuegbarkeit"),sofort=sofort)
        # Auch "nicht verfuegbar" cachen: der naechste 304 spart die Seite
        # komplett, und die Verfuegbarkeit stammt aus demselben Abruf. Parser-
        # Fehler werden nicht gecacht, sonst wuerde ein 304 den Fehler als
        # vermeintlich gueltiges Ergebnis konservieren.
        try:
            http_cache().put(fu or h["urls"][0],
                             {"preis":p,"verfuegbar":bool(v),"signal":signal,
                              "condition":s.get("condition"),"seller":s.get("seller"),
                              "verfuegbarkeit":s.get("verfuegbarkeit"),"sofort":sofort},
                             meta.get("etag"),meta.get("last_modified"),persist=False)
        except Exception: pass
        return res
    except ScanAbgebrochen:
        return None
    except Exception as e:
        err=str(e)[:60]
        return _res(h,None,fehler_klasse(err),time.time()-st,err)

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
    global _DATA_DIR
    _DATA_DIR = p or None

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
    """Alle Haendler parallel scannen - dieselbe Logik wie im Vordergrund."""
    mp = MAX_PREIS if max_preis is None else max_preis
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
            if r.get("klass") not in ("error", "challenge", "unavail", "parser"):
                r["klass"] = classify(True, r.get("preis"), mp)
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
            and r.get("preis") is not None and not ist_gebraucht(r.get("condition"))]

def ist_neuer_treffer(preis, letzter):
    """True, wenn es noch keinen Preis gab oder der neue niedriger ist."""
    return letzter is None or preis < letzter - 0.01

def alarm_ereignis(r, letzter, vorher_verfuegbar):
    """Gemeinsames Alarm-Ereignis fuer App und Hintergrunddienst.

    ``restock`` hat Vorrang: ein wieder verfuegbarer Treffer ist auch dann
    meldenswert, wenn der Preis nicht unter dem letzten Preis liegt.
    """
    if not isinstance(r,dict) or r.get("klass")!="hit" or r.get("preis") is None:
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

def webhook_dedupe(haendler,preis,restock=False,jetzt=None,cooldown=WEBHOOK_COOLDOWN):
    """True, wenn dieser Treffer noch nicht gemeldet wurde.

    Der Key ist Haendler + Preis + Restock-Flag. App und Dienst laufen in
    getrennten Prozessen; der Cooldown wirkt deshalb pro Prozess.
    """
    jetzt=time.time() if jetzt is None else jetzt
    key=(str(haendler or "?"),round(float(preis or 0),2),bool(restock))
    with _WEBHOOK_LOCK:
        for k in [k for k,t in _WEBHOOK_SEEN.items() if jetzt-t>cooldown]:
            _WEBHOOK_SEEN.pop(k,None)
        if key in _WEBHOOK_SEEN: return False
        _WEBHOOK_SEEN[key]=jetzt
        return True

def reset_webhook_dedupe():
    """Nur fuer Tests."""
    with _WEBHOOK_LOCK: _WEBHOOK_SEEN.clear()

def sende_webhook_alarm(r, settings, titel, text, tester=False):
    """Webhook fuer einen Treffer. None = kein Kanal oder schon gemeldet."""
    url=str(_setting(settings,"webhook_url","") or "").strip()
    if not url: return None
    preset=_setting(settings,"webhook_preset","")
    if preset not in WEBHOOK_PRESETS: preset=webhook_preset(url)
    if not tester and not webhook_dedupe(r.get("haendler"),r.get("preis"),
                                        bool(r.get("_restock"))):
        return None
    return webhook_senden(url,preset,titel,text,r.get("url"))

# ── Treffer-Verifikation ───────────────────────────────────────────
def verify_entscheidung(erster,zweiter):
    """Vergleicht den Treffer mit dem zweiten Abruf. Reine Funktion."""
    if not isinstance(erster,dict) or erster.get("klass")!="hit": return None
    if not isinstance(zweiter,dict): return "unbestaetigt"
    if zweiter.get("klass")=="unavail": return "weg"
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
class History:
    def __init__(self):
        self.path=os.path.join(_data_dir(),HISTORY_FILE)
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
    def update(self,results):
        now=datetime.now().isoformat(timespec="seconds")
        for r in results:
            if not isinstance(r,dict) or not r.get("haendler"): continue
            name=r["haendler"]
            alt=dict(self.data.get(name) or {})
            serie=self._saubere_serie(alt.get("serie"))
            # Verfuegbarkeit auch ohne Preis festhalten: nur so laesst sich
            # ein spaeterer Restock von einem gewoehnlichen Scan unterscheiden.
            av=True if r.get("klass") in ("hit","expensive") else (
                False if r.get("klass")=="unavail" else None)
            if av is not None:
                alt["verfuegbar"]=av; alt["verfuegbar_zeit"]=now
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
            if alt: self.data[name]=alt
        try:
            tmp=self.path+".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(self.data,f,ensure_ascii=False,indent=1)
            os.replace(tmp,self.path)
        except Exception: pass

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
    if ist_gebraucht(r.get("condition")): return False
    # "Nur bestaetigte Treffer" heisst genau das: ohne zweiten Abruf kein Alarm.
    if _setting(settings,"alarm_nur_bestaetigt",False) and r.get("verify")!="bestaetigt":
        return False
    if _setting(settings,"notify_sofort",True) and r.get("sofort") is False:
        return False
    stumm=_setting(settings,"mute_haendler",[]) or []
    try:
        if r.get("haendler") in set(stumm): return False
    except TypeError: pass
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

