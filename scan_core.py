"""Netz-, Preis- und Speicherlogik ohne Kivy.

Wird von der App (main.py) und vom Hintergrund-Service (service.py) benutzt.
Der Service laeuft in einem eigenen Prozess ohne UI - dort darf kein Kivy
importiert werden, deshalb liegt diese Logik hier getrennt.
"""
import os, json, re, time, random, threading
from datetime import datetime
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
HISTORY_FILE, SETTINGS_FILE = "ps5pro_history.json", "ps5pro_settings.json"
BG_STATUS_FILE = "ps5pro_bg.json"

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
PRODUKT_MUSTER = [re.compile(r"playstation[\s\-]?5[\s\-]?pro\b",re.I),
                  re.compile(r"\bps5[\s\-]?pro\b",re.I)]
PRODUKT_2TB = re.compile(r"\b2\s*(?:tb|terabyte)\b",re.I)
PRODUKT_AUSSCHLUSS = ["dualsense edge","edge controller","ps portal","portal remote",
    "pulse headset","pulse explore","psvr2","vr2 headset","faceplate","face plate",
    "disc drive","laufwerk"]

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

def extract_structured(html):
    res={"ist_konsole":False,"preis":None,"verfuegbar":None}
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
        if isinstance(off,list): off=off[0] if off else None
        if isinstance(off,dict):
            pv=parse_preis_str(off.get("price") or off.get("lowPrice"))
            # Plausibilitaet wie bei extract_meta_preis: 0,00 / 1,00 sind
            # Platzhalter aus Shop-Vorlagen und wuerden sonst als Treffer
            # gemeldet (Alarm fuer 0 Euro). Nach oben begrenzt gegen
            # Phantasiewerte aus kaputten Feeds.
            if pv is not None and MIN_PREIS<=pv<=5000: res["preis"]=pv
            av=str(off.get("availability","")).lower()
            if any(k in av for k in ("instock","preorder","backorder","instoreonly","limited")):
                res["verfuegbar"]=True
            elif any(k in av for k in ("outofstock","soldout","discontinued")):
                res["verfuegbar"]=False
        # Weitere Product-Eintraege ansehen, solange noch kein brauchbarer
        # Preis gefunden wurde: manche Shops liefern erst im zweiten Eintrag
        # ein Angebot (der erste ist dann z. B. eine Variante ohne offers).
        if res["preis"] is not None: break
    return res

def extract_meta_preis(html):
    pats = [
        r'<meta[^>]+property=["\']product:price:amount["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+itemprop=["\']price["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:price:amount["\'][^>]+content=["\']([^"\']+)',
        r'data-price=["\']([^"\']+)["\']',
        r'"price"\s*:\s*"?(\d+[.,]\d{2})"?',
        r'"priceValue"\s*:\s*"?(\d+[.,]\d{2})"?',
        r'((?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})\s*(?:€|EUR)',
        r'(?:€|EUR)\s*((?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})'
    ]
    for pat in pats:
        try:
            for m in re.finditer(pat,html,re.I):
                p=parse_preis_str(m.group(1))
                if p is not None and MIN_PREIS<=p<=1500: return p
        except re.error: continue
    return None

def detect_challenge(low): return any(p in low for p in CHALLENGE_PATTERNS)

def pruefe_nur_konsole(html, st):
    if st.get("ist_konsole"): return True
    # Beide Muster sind re.I - ein zusaetzliches html.lower() wuerde nur eine
    # zweite Kopie der Seite im Speicher anlegen (bei Shops leicht 2-6 MB).
    if not any(rx.search(html) for rx in PRODUKT_MUSTER): return False
    return bool(PRODUKT_2TB.search(html))

def pruefe_verfuegbar(html, st):
    if st.get("verfuegbar") is not None: return st["verfuegbar"]
    low=html.lower()
    neg=sum(1 for kw in AUSVERKAUFT if kw in low)
    pos=sum(1 for kw in POSITIV if kw in low)
    return False if neg>pos else True

def classify(v,p,m):
    if not v: return "unavail"
    if p is None: return "unknown"
    if m is None or p<=m: return "hit"
    return "expensive"

def _try_url(u, att, proxy=None):
    uu=u
    if att>0: uu+=("&" if "?" in uu else "?")+"_cb="+str(int(time.time()*1000))
    ua=UA_PROFILES[att%len(UA_PROFILES)]
    ref=REFERERS[att%len(REFERERS)]
    hd={**BASE_HEADERS,**ua,"Referer":ref}
    pr={"http":proxy,"https":proxy} if proxy else None
    try:
        sess=_session()
        if sess is not None:
            r=sess.get(uu,headers=hd,timeout=TIMEOUT,allow_redirects=True,proxies=pr)
            if r.status_code==429:
                # Retry-After respektieren, aber gedeckelt - ein Shop mit
                # "3600" soll den Scan nicht eine Stunde blockieren.
                try: ra=int(r.headers.get("Retry-After","8"))
                except (TypeError,ValueError): ra=8
                time.sleep(min(max(ra,1),15)); return None,"HTTP 429"
            if r.status_code>=400: return None,f"HTTP {r.status_code}"
            return r.text,None
        req=Request(uu,headers=hd)
        with urlopen(req,timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8",errors="replace"),None
    except HTTPError as e:
        # urlopen wirft bei 4xx/5xx; ohne diese Normalisierung greift die
        # 404/410-Abkürzung in fetch_html_multi nie und jeder umgezogene
        # Haendler kostet drei Versuche samt Wartezeit.
        return None,f"HTTP {e.code}"
    except Exception as e: return None,str(e)[:50]

def fetch_html_multi(urls):
    last=None
    proxy=os.environ.get("PS5_PROXY","").strip() or None
    for att in range(3):
        dauerhaft=False
        for u in urls:
            h,e=_try_url(u,att,proxy)
            if h:
                # Nur den Kopf pruefen - h.lower() auf einer 5-MB-Seite kostet
                # unnoetig Zeit und Speicher.
                if detect_challenge(h[:3000].lower()): last="Bot-Challenge"; continue
                return h,u
            last=e
            # 404/410 bleiben bei jedem User-Agent bestehen. Drei Versuche kosten
            # hier nur ~7 s Wartezeit pro umgezogenem Haendler, ohne Chance auf
            # Erfolg; alles andere (Timeout, 403, 429, 5xx) wird weiter probiert.
            if e in ("HTTP 404","HTTP 410"):
                if len(urls)==1:
                    dauerhaft=True; break
                continue
            time.sleep((0.4,2.0,5.0)[att]+random.uniform(0,1.0))
        if dauerhaft: break
    raise RuntimeError(last or "alle URLs fehlgeschlagen")

def _res(h,preis,klass,dauer,err,final_url=None):
    return {"haendler":h["name"],"url":final_url or h["urls"][0],"land":h["land"],
            "preis":preis,"klass":klass,"dauer":round(dauer,1),
            "zeit":datetime.now().strftime("%H:%M:%S"),"fehler":err}

def scan_einen(h):
    st=time.time()
    try:
        html,fu=fetch_html_multi(h["urls"]); d=time.time()-st
        if detect_challenge(html[:3000].lower()):
            return _res(h,None,"challenge",d,"Bot-Challenge",fu)
        s=extract_structured(html)
        if not pruefe_nur_konsole(html,s):
            return _res(h,None,"unknown",d,"nicht PS5 Pro 2TB",fu)
        v=pruefe_verfuegbar(html,s)
        p=(s.get("preis") or extract_meta_preis(html))
        return _res(h,p,classify(v,p,MAX_PREIS),d,None,fu)
    except Exception as e:
        return _res(h,None,"error",time.time()-st,str(e)[:60])

def _safe_scan(h):
    st=time.time()
    try: return scan_einen(h)
    except Exception as e: return _res(h,None,"error",time.time()-st,str(e)[:60])

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

def scan_alle(haendler, max_preis=None, fortschritt=None):
    """Alle Haendler parallel scannen - dieselbe Logik wie im Vordergrund."""
    mp = MAX_PREIS if max_preis is None else max_preis
    ergebnisse = []
    ex = ThreadPoolExecutor(max_workers=WORKER)
    try:
        futs = {ex.submit(_safe_scan, h): h for h in haendler}
        for f in as_completed(futs):
            r = f.result()
            if r.get("klass") not in ("error", "challenge", "unavail"):
                r["klass"] = classify(True, r.get("preis"), mp)
            ergebnisse.append(r)
            if fortschritt is not None:
                try: fortschritt(len(ergebnisse), len(haendler))
                except Exception: pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return ergebnisse

def treffer_aus(results):
    return [r for r in results if r.get("klass") == "hit" and r.get("preis") is not None]

def ist_neuer_treffer(preis, letzter):
    """True, wenn es noch keinen Preis gab oder der neue niedriger ist."""
    return letzter is None or preis < letzter - 0.01

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
    def get_last(self,n): return self.data.get(n,{}).get("preis")
    def update(self,results):
        now=datetime.now().isoformat(timespec="seconds")
        for r in results:
            if r["klass"]=="hit" and r["preis"] is not None:
                self.data[r["haendler"]]={"preis":r["preis"],"zeit":now}
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

