"""PS5 Pro Search Agent v27 - PS1 Edition"""
import os, sys, json, re, time, math, random, queue, threading, hashlib
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

IS_MOBILE = ('ANDROID_ARGUMENT' in os.environ or sys.platform in ('android','ios'))
try:
    from kivy.config import Config
    Config.set('graphics','multisamples','0')
    Config.set('graphics','resizable','0' if IS_MOBILE else '1')
    if IS_MOBILE: Config.set('graphics','fullscreen','auto')
    else:
        Config.set('graphics','width','420'); Config.set('graphics','height','820')
except Exception: pass

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import NumericProperty, ListProperty, BooleanProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.animation import Animation
from kivy.utils import get_color_from_hex, platform

try:
    import requests as _rq
except ImportError:
    _rq = None

_TLS = threading.local()

def _session():
    """Eine requests.Session pro Thread - ein geteiltes Session-Objekt ist nicht thread-sicher."""
    if _rq is None: return None
    s = getattr(_TLS, "session", None)
    if s is None:
        s = _rq.Session()
        s.headers.update({"Accept-Encoding":"gzip, deflate",
                          "Connection":"keep-alive","DNT":"1"})
        _TLS.session = s
    return s

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
os.makedirs(FONT_DIR, exist_ok=True)
SST_FONT = "Roboto"
for _fn in ("SST.ttf","Inter-Bold.ttf","Inter-Regular.ttf"):
    _fp = os.path.join(FONT_DIR,_fn)
    if os.path.exists(_fp):
        try:
            LabelBase.register(name="SST", fn_regular=_fp); SST_FONT="SST"; break
        except Exception: pass

# ── Farben ──────────────────────────────────────────────────────────
C_BG        = get_color_from_hex("#04080a")
C_CARD      = get_color_from_hex("#0e1a1f")
C_FG        = get_color_from_hex("#c8d6e5")
C_FG_DIM    = get_color_from_hex("#6a8088")
C_PHOSPHOR  = get_color_from_hex("#00ff41")
C_PHOSPHOR_M= get_color_from_hex("#1a8a35")
C_PHOSPHOR_D= get_color_from_hex("#0a4a1a")
C_ACCENT    = get_color_from_hex("#00d2ff")
C_YELLOW    = get_color_from_hex("#feca57")
C_ORANGE    = get_color_from_hex("#ff9f43")
C_RED       = get_color_from_hex("#ee5253")
C_GRAY      = get_color_from_hex("#576574")
C_WHITE     = get_color_from_hex("#e8fff0")
C_DARK_TEXT = get_color_from_hex("#04080a")

# ── PS1 Palette ─────────────────────────────────────────────────────
PS1_INK      = get_color_from_hex("#08090b")
PS1_BG       = get_color_from_hex("#0c0d10")
PS1_CARD     = get_color_from_hex("#1c1d21")
PS1_CARD_HI  = get_color_from_hex("#25262b")
PS1_PANEL    = get_color_from_hex("#2b2c31")
PS1_PANEL_HI = get_color_from_hex("#3b3c43")
PS1_EDGE     = get_color_from_hex("#4b4c55")
PS1_GREY     = get_color_from_hex("#8c8c8c")
PS1_SILVER   = get_color_from_hex("#cdcdcd")
PS1_TEXT     = get_color_from_hex("#f1f2f4")
PS1_DARK     = get_color_from_hex("#1c1c1c")
PS1_BLUE     = get_color_from_hex("#0055c4")
PS1_BLUE_HI  = get_color_from_hex("#3f8cff")
PS1_RED      = get_color_from_hex("#d80000")
PS1_GREEN    = get_color_from_hex("#00a04a")
PS1_PINK     = get_color_from_hex("#e83a8a")
PS1_YELLOW   = get_color_from_hex("#ffcc00")

PS_TRIANGLE = (0.11,0.66,0.30,1)
PS_CIRCLE   = (0.90,0.10,0.10,1)
PS_CROSS    = (0.11,0.35,0.65,1)
PS_SQUARE   = (0.85,0.11,0.46,1)

STATUS_COLORS = {"hit":get_color_from_hex("#3ddc84"),"expensive":C_ORANGE,
                 "unknown":C_YELLOW,"unavail":C_GRAY,"error":C_RED,
                 "challenge":C_YELLOW}
CARD_STATUS = {"hit":get_color_from_hex("#3ddc84"),"expensive":PS1_YELLOW,
               "unknown":get_color_from_hex("#9aa3ad"),
               "unavail":get_color_from_hex("#6b7280"),
               "error":get_color_from_hex("#ff5c5c"),
               "challenge":PS1_YELLOW}

# Radar (PS1 BIOS blue instead of phosphor green)
RADAR_BG    = get_color_from_hex("#05070c")
RADAR_DISH  = get_color_from_hex("#0a1424")
RADAR_RING  = get_color_from_hex("#2a5f94")
RADAR_GRID  = get_color_from_hex("#183a5c")
RADAR_DIM   = get_color_from_hex("#122b45")
RADAR_TICK  = get_color_from_hex("#2f6fa8")
RADAR_SWEEP = get_color_from_hex("#5aa8ff")
RADAR_TXT   = get_color_from_hex("#4f86b8")

BRAND_COLORS = {
    "ps direct":(0.00,0.44,0.82,1),"mediamarkt":(0.89,0.00,0.10,1),
    "saturn":(0.90,0.00,0.00,1),"amazon":(1.00,0.60,0.00,1),
    "otto":(0.90,0.00,0.10,1),"alternate":(1.00,0.40,0.00,1),
    "cyberport":(0.00,0.62,0.89,1),"euronics":(0.00,0.36,0.66,1),
    "expert":(0.89,0.02,0.07,1),"notebooksbilliger":(1.00,0.40,0.00,1),
    "coolblue":(0.00,0.34,0.72,1),"conrad":(0.00,0.20,0.63,1),
    "kaufland":(0.88,0.04,0.08,1),"gamestop":(0.90,0.00,0.07,1),
    "libro":(0.83,0.00,0.00,1),"alza":(0.78,0.06,0.18,1),
    "hartlauer":(0.90,0.00,0.49,1),"electronic4you":(0.89,0.00,0.10,1),
    "quelle":(0.90,0.00,0.49,1),"universal":(0.83,0.00,0.00,1),
    "mueller":(0.89,0.02,0.07,1),"proshop":(0.00,0.44,0.72,1),
    "computeruniverse":(0.00,0.55,0.85,1),"galaxus":(0.00,0.70,0.55,1),
    "gameware":(0.85,0.15,0.15,1),"geizhals":(0.00,0.60,0.80,1),
    "spielekauf":(0.80,0.20,0.40,1),"shoepping":(0.00,0.52,0.80,1),
    "aetka":(0.60,0.20,0.60,1),"computerexpert":(0.00,0.40,0.60,1),
}

MAX_PREIS, MIN_PREIS, MSRP_ZIEL = 900.0, 550.0, 799.99
PRICE_OPTIONS = [700.0, 800.0, 900.0, None]
AUTO_INTERVALS = [(300,"5m"),(600,"10m"),(900,"15m"),(1800,"30m"),(3600,"60m")]
TIMEOUT, WORKER = 20, 6
HISTORY_FILE, SETTINGS_FILE = "ps5pro_history.json", "ps5pro_settings.json"

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
    _h("Aetka AT","AT","https://aetka.de/suche?q=playstation+5+pro+2tb"),
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

# ── Helfer ──────────────────────────────────────────────────────────
def open_url(u):
    if not u: return
    if platform=="android":
        try:
            from jnius import autoclass
            Intent=autoclass("android.content.Intent"); Uri=autoclass("android.net.Uri")
            PA=autoclass("org.kivy.android.PythonActivity")
            PA.mActivity.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(u))); return
        except Exception: pass
    try:
        import webbrowser; webbrowser.open(u)
    except Exception: pass

def haptic(d=0.05):
    if platform!="android": return
    try:
        from jnius import autoclass
        C=autoclass("android.content.Context"); PA=autoclass("org.kivy.android.PythonActivity")
        v=PA.mActivity.getSystemService(C.VIBRATOR_SERVICE)
        if v.hasVibrator(): v.vibrate(int(max(1,d*1000)))
    except Exception: pass

def notify(t,m):
    if platform=="android":
        try:
            from jnius import autoclass
            PA=autoclass("org.kivy.android.PythonActivity")
            C=autoclass("android.content.Context")
            NB=autoclass("android.app.Notification$Builder")
            a=PA.mActivity; b=NB(a); b.setContentTitle(t); b.setContentText(m)
            b.setSmallIcon(a.getApplicationInfo().icon); b.setAutoCancel(True)
            # Android 8+: ohne NotificationChannel wird die Meldung verworfen
            try:
                if autoclass("android.os.Build$VERSION").SDK_INT>=26:
                    NM=autoclass("android.app.NotificationManager")
                    ch=autoclass("android.app.NotificationChannel")(
                        "ps5pro_hits","PS5 Pro Treffer",NM.IMPORTANCE_HIGH)
                    ch.setDescription("Verf\u00fcgbarkeit der PS5 Pro 2 TB")
                    a.getSystemService(C.NOTIFICATION_SERVICE).createNotificationChannel(ch)
                    b.setChannelId("ps5pro_hits")
            except Exception: pass
            nm=a.getSystemService(C.NOTIFICATION_SERVICE)
            nm.notify(int(time.time())%100000,b.build()); return True
        except Exception: pass
    try:
        from plyer import notification
        notification.notify(title=t,message=m,timeout=8); return True
    except Exception: return False

def request_android_permissions():
    if platform!="android": return
    try:
        from android.permissions import request_permissions, Permission
        p=[Permission.INTERNET,Permission.VIBRATE]
        if hasattr(Permission,"POST_NOTIFICATIONS"): p.append(Permission.POST_NOTIFICATIONS)
        request_permissions(p)
    except Exception: pass

def format_preis(p):
    return "{:,.2f}".format(p).replace(",","X").replace(".",",").replace("X",".")+" €"

def parse_preis_str(s):
    if s is None: return None
    s = re.sub(r"&nbsp;|\s|€|EUR|\$|£|USD|GBP","",str(s).strip(),flags=re.I)
    s = re.sub(r"[a-zA-Z]","",s)
    if not s: return None
    m = re.match(r"^(\d{1,3}(?:\.\d{3})*),(\d{1,2})$",s)
    if m:
        try: return float(m.group(1).replace(".","")+"."+m.group(2))
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
            if pv is not None: res["preis"]=pv
            av=str(off.get("availability","")).lower()
            if any(k in av for k in ("instock","preorder","backorder","instoreonly","limited")):
                res["verfuegbar"]=True
            elif any(k in av for k in ("outofstock","soldout","discontinued")):
                res["verfuegbar"]=False
        break
    return res

def extract_meta_preis(html):
    pats = [
        r'<meta[^>]+property=["\']product:price:amount["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+itemprop=["\']price["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:price:amount["\'][^>]+content=["\']([^"\']+)',
        r'data-price=["\']([^"\']+)["\']',
        r'"price"\s*:\s*"?(\d+[.,]\d{2})"?',
        r'"priceValue"\s*:\s*"?(\d+[.,]\d{2})"?',
        r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:€|EUR)',
        r'(?:€|EUR)\s*(\d{1,3}(?:\.\d{3})*,\d{2})'
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
    low=html.lower()
    if not any(rx.search(low) for rx in PRODUKT_MUSTER): return False
    return bool(PRODUKT_2TB.search(low))

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
            if r.status_code==429: time.sleep(8); return None,"HTTP 429"
            if r.status_code>=400: return None,f"HTTP {r.status_code}"
            return r.text,None
        req=Request(uu,headers=hd)
        with urlopen(req,timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8",errors="replace"),None
    except Exception as e: return None,str(e)[:50]

def fetch_html_multi(urls):
    last=None
    proxy=os.environ.get("PS5_PROXY","").strip() or None
    for att in range(3):
        for u in urls:
            h,e=_try_url(u,att,proxy)
            if h:
                if detect_challenge(h.lower()[:3000]): last="Bot-Challenge"; continue
                return h,u
            last=e
            time.sleep((0.4,2.0,5.0)[att]+random.uniform(0,1.0))
    raise RuntimeError(last or "alle URLs fehlgeschlagen")

def _res(h,preis,klass,dauer,err,final_url=None):
    return {"haendler":h["name"],"url":final_url or h["urls"][0],"land":h["land"],
            "preis":preis,"klass":klass,"dauer":round(dauer,1),
            "zeit":datetime.now().strftime("%H:%M:%S"),"fehler":err}

def scan_einen(h):
    st=time.time()
    try:
        html,fu=fetch_html_multi(h["urls"]); d=time.time()-st
        if detect_challenge(html.lower()[:3000]):
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

def _data_dir():
    try: return App.get_running_app().user_data_dir
    except Exception: return os.path.expanduser("~")

class History:
    def __init__(self):
        self.path=os.path.join(_data_dir(),HISTORY_FILE)
        try:
            with open(self.path,"r",encoding="utf-8") as f: self.data=json.load(f)
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
            with open(self.path,"r",encoding="utf-8") as f: self.data=json.load(f)
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

SPECIAL_INITIALS = {"ps direct":"PS","mediamarkt":"MM","amazon":"AM",
    "notebooksbilliger":"NB","electronic4you":"E4","computeruniverse":"CU",
    "galaxus":"GX","geizhals":"GH","spielekauf":"SK","computerexpert":"CX"}

def initials_for(name):
    base=re.sub(r"\s+(DE|AT)$","",name).strip()
    key=base.lower()
    if key in SPECIAL_INITIALS: return SPECIAL_INITIALS[key]
    parts=base.split()
    if len(parts)>=2: return (parts[0][0]+parts[1][0]).upper()
    return base[:2].upper() if len(base)>=2 else base[:1].upper()

def brand_color(name):
    base=re.sub(r"\s+(DE|AT)$","",name).strip().lower()
    if base in BRAND_COLORS: return BRAND_COLORS[base]
    h=int(hashlib.md5(name.encode()).hexdigest()[:6],16)
    pal=["#e60019","#c9661b","#003d8c","#007a3d","#3d7fbf","#a57d10","#c94b8c",
         "#1a8a35","#c74d4d","#2e8c85","#6f6ad4","#b89915","#a94f3a","#4a7fb8","#00a37f"]
    return get_color_from_hex(pal[h%len(pal)])

def text_on(c):
    lum=0.299*c[0]+0.587*c[1]+0.114*c[2]
    return C_DARK_TEXT if lum>0.62 else (1,1,1,1)
# ══════════ HORIZONTAL SCROLLVIEW ══════════
class HScrollView(ScrollView):
    """Horizontal list that also responds to touch drags (mobile) and wheel."""
    def __init__(self, **kw):
        kw.setdefault('do_scroll_x', True)
        kw.setdefault('do_scroll_y', False)
        kw.setdefault('scroll_type', ['bars', 'content'])
        kw.setdefault('scroll_timeout', 50)
        kw.setdefault('scroll_distance', dp(10))
        kw.setdefault('bar_width', dp(3))
        kw.setdefault('bar_color', PS1_SILVER)
        kw.setdefault('bar_inactive_color', (0.28, 0.29, 0.33, 0.55))
        kw.setdefault('bar_margin', dp(1))
        super().__init__(**kw)
    def on_touch_down(self, touch):
        if touch.is_mouse_scrolling and self.collide_point(*touch.pos):
            if touch.button in ('scrollup', 'scrollleft'):
                self.scroll_x = max(0.0, self.scroll_x - 0.12); return True
            elif touch.button in ('scrolldown', 'scrollright'):
                self.scroll_x = min(1.0, self.scroll_x + 0.12); return True
        return super().on_touch_down(touch)

# ══════════ PLAYSTATION SYMBOLS ══════════
class PSShapesWidget(Widget):
    def __init__(self, size=(dp(40), dp(12)), **kw):
        super().__init__(**kw)
        self.size_hint = (None, None)
        self.size = size
        with self.canvas:
            Color(*PS_TRIANGLE); self.t_line = Line(width=dp(1.2))
            Color(*PS_CIRCLE);   self.c_line = Line(width=dp(1.2))
            Color(*PS_CROSS);    self.x_line1 = Line(width=dp(1.2))
            self.x_line2 = Line(width=dp(1.2))
            Color(*PS_SQUARE);   self.s_line = Line(width=dp(1.2))
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        if self.width <= 0 or self.height <= 0: return
        step = self.width / 4
        cy = self.y + self.height / 2
        r = min(step, self.height) * 0.25

        cx1 = self.x + step * 0.5
        self.t_line.points = [cx1, cy+r, cx1-r, cy-r, cx1+r, cy-r, cx1, cy+r]

        cx2 = self.x + step * 1.5
        self.c_line.circle = (cx2, cy, r)

        cx3 = self.x + step * 2.5
        d = r * 0.8
        self.x_line1.points = [cx3-d, cy-d, cx3+d, cy+d]
        self.x_line2.points = [cx3-d, cy+d, cx3+d, cy-d]

        cx4 = self.x + step * 3.5
        self.s_line.points = [cx4-d, cy-d, cx4+d, cy-d, cx4+d, cy+d, cx4-d, cy+d, cx4-d, cy-d]

# ══════════ FLAG (Canvas) ══════════
class FlagWidget(Widget):
    def __init__(self, land, size=(dp(20),dp(13)), **kw):
        super().__init__(**kw)
        self.land=land; self.size_hint=(None,None); self.size=size
        self.bind(pos=self._redraw,size=self._redraw)
        Clock.schedule_once(self._redraw,0)
    def _redraw(self,*_):
        self.canvas.clear()
        w,h=self.width,self.height
        if w<=0 or h<=0: return
        x,y=self.x,self.y
        with self.canvas:
            if self.land=="DE":
                t=h/3
                Color(0.06,0.06,0.06,1); Rectangle(pos=(x,y+2*t),size=(w,t))
                Color(0.86,0,0,1); Rectangle(pos=(x,y+t),size=(w,t))
                Color(1,0.79,0,1); Rectangle(pos=(x,y),size=(w,t))
            elif self.land=="AT":
                t=h/3
                Color(0.78,0,0.12,1); Rectangle(pos=(x,y+2*t),size=(w,t))
                Color(1,1,1,1); Rectangle(pos=(x,y+t),size=(w,t))
                Color(0.78,0,0.12,1); Rectangle(pos=(x,y),size=(w,t))
            else:
                Color(*C_GRAY); Rectangle(pos=(x,y),size=(w,h))
            Color(0.15,0.15,0.15,1)
            Line(rectangle=(x,y,w,h),width=dp(0.8))

# ══════════ TOAST ══════════
class Toast(Label):
    def __init__(self,**kw):
        super().__init__(**kw)
        self.size_hint=(0.85,None); self.height=dp(40)
        self.pos_hint={"center_x":0.5,"y":0.1}
        self.halign="center"; self.valign="middle"
        self.markup=True; self.font_size=sp(12); self.color=PS1_TEXT
        self.opacity=0; self.bold=True; self.font_name=SST_FONT
        self.bind(size=lambda w,*_: setattr(w,"text_size",(w.width-dp(20),w.height-dp(6))))
        with self.canvas.before:
            Color(0.07,0.07,0.08,0.98)
            self._bg=RoundedRectangle(radius=[dp(2)])
            Color(*PS1_EDGE); self._bd=Line(width=dp(1))
        self.bind(pos=self._sync,size=self._sync)
    def _sync(self,*_):
        if hasattr(self,"_bg"):
            self._bg.pos=self.pos; self._bg.size=self.size
            self._bd.rectangle=(self.x,self.y,self.width,self.height)
    def show(self,text,color=None,dur=2.0):
        self.text=text; self.color=color or PS1_TEXT
        Animation.cancel_all(self,"opacity")
        Animation(opacity=1,d=0.15).start(self)
        Clock.schedule_once(lambda dt:self._hide(),dur)
    def _hide(self,*_): Animation(opacity=0,d=0.3).start(self)

# ══════════ RADAR (PS1 BIOS look) ══════════
class RadarWidget(Widget):
    angle=NumericProperty(0.0); blips=ListProperty([])
    scanning=BooleanProperty(False)
    reserve_bottom=NumericProperty(0); reserve_top=NumericProperty(0)
    def __init__(self,**kw):
        super().__init__(**kw); self._fl=[]
        st=["triangle","circle","cross","square"]
        cm={"triangle":PS_TRIANGLE,"circle":PS_CIRCLE,"cross":PS_CROSS,"square":PS_SQUARE}
        for _ in range(6):
            t=random.choice(st)
            self._fl.append({"x":random.uniform(0.2,0.8),"y":random.uniform(0.2,0.8),
                "vx":random.uniform(-0.0004,0.0004),"vy":random.uniform(-0.0004,0.0004),
                "type":t,"color":cm[t],"size":random.uniform(0.035,0.060),
                "alpha":random.uniform(0.20,0.40)})
        self._bls=[]
        for deg in range(0,360,30):
            major=(deg%90==0)
            l=Label(text=str(deg),font_size=sp(8 if major else 6),
                    bold=major,font_name=SST_FONT,
                    color=(RADAR_TICK if major else RADAR_TXT),
                    halign="center",valign="middle",
                    size_hint=(None,None),size=(dp(24),dp(10)),opacity=0)
            l.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            self.add_widget(l); self._bls.append((deg,l))
        Clock.schedule_interval(self._tick,1/30)
    def _tick(self,dt):
        s=180.0 if self.scanning else 30.0
        self.angle=(self.angle+s*dt)%360
        for f in self._fl:
            f["x"]+=f["vx"]; f["y"]+=f["vy"]
            if not (0.1<f["x"]<0.9): f["vx"]*=-1
            if not (0.1<f["y"]<0.9): f["vy"]*=-1
        self._redraw()
    def _sym(self,t,cx,cy,r,c):
        Color(*c); w=max(dp(1),min(dp(1.6),r*0.15))
        if t=="triangle":
            h=r*0.866
            Line(points=[cx,cy+r,cx-h,cy-r*0.5,cx+h,cy-r*0.5,cx,cy+r],width=w)
        elif t=="circle": Line(circle=(cx,cy,r*0.9),width=w)
        elif t=="cross":
            d=r*0.72
            Line(points=[cx-d,cy-d,cx+d,cy+d],width=w)
            Line(points=[cx-d,cy+d,cx+d,cy-d],width=w)
        elif t=="square":
            d=r*0.78
            Line(points=[cx-d,cy-d,cx+d,cy-d,cx+d,cy+d,cx-d,cy+d,cx-d,cy-d],width=w)
    def _redraw(self):
        self.canvas.clear()
        if self.width<=0 or self.height<=0: return
        uh=self.height-self.reserve_bottom-self.reserve_top
        if uh<dp(40) or self.width<dp(40):
            for _,l in self._bls: l.opacity=0
            return
        cx=self.width/2; cy=self.reserve_bottom+uh/2
        mr=min(self.width/2,uh/2)-dp(16)
        if mr<dp(40):
            for _,l in self._bls: l.opacity=0
            return
        now=time.time()
        with self.canvas:
            Color(*RADAR_BG); Rectangle(pos=(0,0),size=(self.width,self.height))
            Color(*RADAR_DISH); Ellipse(pos=(cx-mr,cy-mr),size=(mr*2,mr*2))
            Color(RADAR_RING[0],RADAR_RING[1],RADAR_RING[2],0.75)
            Line(circle=(cx,cy,mr+dp(4)),width=dp(1.5))
            Color(RADAR_RING[0],RADAR_RING[1],RADAR_RING[2],0.95)
            Line(circle=(cx,cy,mr),width=dp(2.5))
            for f in (0.25,0.5,0.75):
                Color(*RADAR_DIM); Line(circle=(cx,cy,mr*f),width=dp(1))
            Color(RADAR_GRID[0],RADAR_GRID[1],RADAR_GRID[2],0.75)
            for i in range(12):
                a=math.radians(i*30-90)
                Line(points=[cx,cy,cx+mr*math.cos(a),cy+mr*math.sin(a)],width=dp(0.8))
            for i in range(72):
                a=math.radians(i*5-90); mj=(i%18==0); md=(i%6==0)
                inn=mr-dp(12 if mj else (8 if md else 4))
                Color(RADAR_TICK[0],RADAR_TICK[1],RADAR_TICK[2],0.9 if mj else 0.45)
                Line(points=[cx+inn*math.cos(a),cy+inn*math.sin(a),
                             cx+mr*math.cos(a),cy+mr*math.sin(a)],
                     width=dp(1.8 if mj else (1.2 if md else 0.7)))
            for i in range(30):
                fr=(i+1)/30; a=math.radians(90.0-self.angle+fr*150); k=(1-fr)
                Color(0.24*k,0.55*k,0.95*k,0.45*k)
                Line(points=[cx,cy,cx+mr*math.cos(a),cy+mr*math.sin(a)],width=dp(1.8-fr))
            a=math.radians(90.0-self.angle)
            tx,ty=cx+mr*math.cos(a),cy+mr*math.sin(a)
            Color(*RADAR_SWEEP); Line(points=[cx,cy,tx,ty],width=dp(2.5))
            Color(RADAR_SWEEP[0],RADAR_SWEEP[1],RADAR_SWEEP[2],0.25)
            Ellipse(pos=(tx-dp(10),ty-dp(10)),size=(dp(20),dp(20)))
            Color(*PS1_TEXT); Ellipse(pos=(tx-dp(3),ty-dp(3)),size=(dp(6),dp(6)))
            for f in self._fl:
                fx=cx+(f["x"]-0.5)*mr*1.6; fy=cy+(f["y"]-0.5)*mr*1.6
                dx,dy=fx-cx,fy-cy
                if dx*dx+dy*dy<mr*mr*0.85:
                    sz=mr*(f["size"]*1.4); c=f["color"]
                    self._sym(f["type"],fx,fy,sz,(c[0],c[1],c[2],f["alpha"]))
            for b in self.blips:
                bx=cx+b["x"]*mr; by=cy+b["y"]*mr
                co=STATUS_COLORS.get(b["klass"],C_FG_DIM)
                if b["klass"]=="hit":
                    pu=0.5+0.5*math.sin(now*4)
                    Color(co[0],co[1],co[2],0.30*pu)
                    Line(circle=(bx,by,dp(12)+pu*dp(8)),width=dp(1.4))
                    Color(co[0],co[1],co[2],0.18)
                    Ellipse(pos=(bx-dp(10),by-dp(10)),size=(dp(20),dp(20)))
                    r=dp(6)
                else: r=dp(4)
                Color(co[0],co[1],co[2],b.get("intensity",1.0))
                Ellipse(pos=(bx-r,by-r),size=(r*2,r*2))
            for sym,col,deg in [("triangle",PS_TRIANGLE,0),("circle",PS_CIRCLE,90),
                                 ("cross",PS_CROSS,180),("square",PS_SQUARE,270)]:
                aa=math.radians(90-deg)
                mx=cx+mr*0.90*math.cos(aa); my=cy+mr*0.90*math.sin(aa)
                self._sym(sym,mx,my,dp(11),(col[0],col[1],col[2],0.9))
            pu=0.7+0.3*math.sin(now*2.5)
            Color(RADAR_RING[0],RADAR_RING[1],RADAR_RING[2],pu)
            Ellipse(pos=(cx-dp(10)*pu,cy-dp(10)*pu),size=(dp(20)*pu,dp(20)*pu))
            Color(*PS1_SILVER); Ellipse(pos=(cx-dp(3),cy-dp(3)),size=(dp(6),dp(6)))
            Color(*PS1_TEXT); Ellipse(pos=(cx-dp(1.5),cy-dp(1.5)),size=(dp(3),dp(3)))
        for deg,l in self._bls:
            a=math.radians(90-deg)
            l.pos=(cx+(mr+dp(11))*math.cos(a)-l.width/2,
                    cy+(mr+dp(11))*math.sin(a)-l.height/2); l.opacity=1
# ══════════ PS1 BUTTON ══════════
class PS1Button(Button):
    """Flat 90s console button with a bevel instead of Kivy's pillow theme."""
    def __init__(self,accent=None,**kw):
        kw.setdefault("background_normal","")
        kw.setdefault("background_down","")
        kw.setdefault("background_color",(0,0,0,0))
        kw.setdefault("font_name",SST_FONT)
        kw.setdefault("bold",True)
        kw.setdefault("color",PS1_SILVER)
        super().__init__(**kw)
        self._accent=accent or PS1_BLUE
        self.bind(state=self._redraw,pos=self._redraw,size=self._redraw)
        Clock.schedule_once(self._redraw,0)
    def _redraw(self,*_):
        self.canvas.before.clear()
        if self.width<=0 or self.height<=0: return
        pressed=(self.state=="down")
        bg=self._accent if pressed else PS1_PANEL
        self.color=(1,1,1,1) if pressed else PS1_SILVER
        with self.canvas.before:
            Color(0,0,0,0.85)
            Rectangle(pos=(self.x-dp(1),self.y-dp(1)),
                      size=(self.width+dp(2),self.height+dp(2)))
            Color(*bg); Rectangle(pos=self.pos,size=self.size)
            Color(*(PS1_BLUE_HI if pressed else PS1_EDGE))
            Line(rectangle=(self.x,self.y,self.width,self.height),width=dp(1))

# ══════════ CHIP ══════════
class Chip(ToggleButton):
    def __init__(self,accent=None,**kw):
        super().__init__(**kw)
        self.background_normal=""; self.background_down=""
        self.background_color=(0,0,0,0); self.color=PS1_SILVER
        self.font_size=sp(9.5); self.font_name=SST_FONT; self.bold=True
        self.size_hint=(None,1)
        self._accent=accent or PS1_BLUE
        self.bind(state=self._redraw,pos=self._redraw,size=self._redraw)
        Clock.schedule_once(self._redraw,0)
    def _redraw(self,*_):
        self.canvas.before.clear()
        on=(self.state=="down")
        if on:
            bg=self._accent; bd=self._accent; self.color=(1,1,1,1)
        else:
            bg=PS1_PANEL; bd=PS1_EDGE; self.color=PS1_SILVER
        if self.width<=0 or self.height<=0: return
        with self.canvas.before:
            Color(0,0,0,0.7); Rectangle(pos=(self.x,self.y-dp(1)),
                                         size=(self.width,self.height+dp(1)))
            Color(*bg); Rectangle(pos=self.pos,size=self.size)
            Color(*bd); Line(rectangle=(self.x,self.y,self.width,self.height),width=dp(1))

# ══════════ SMALL PARTS ══════════
class Dot(Widget):
    def __init__(self,color,**kw):
        super().__init__(**kw)
        self._c=color
        self.size_hint=(None,None); self.size=(dp(8),dp(8))
        self.bind(pos=self._redraw,size=self._redraw)
        Clock.schedule_once(self._redraw,0)
    def _redraw(self,*_):
        self.canvas.clear()
        if self.width<=0 or self.height<=0: return
        with self.canvas:
            Color(0,0,0,0.8); Rectangle(pos=(self.x-dp(1),self.y-dp(1)),
                                        size=(self.width+dp(2),self.height+dp(2)))
            Color(*self._c); Rectangle(pos=self.pos,size=self.size)
            Color(1,1,1,0.25); Line(points=[self.x,self.top-dp(1),self.right-dp(1),self.top-dp(1)],width=dp(1))

class Tag(Widget):
    def __init__(self,text,bg,fg=(0,0,0,1),**kw):
        super().__init__(**kw)
        self.size_hint=(None,None); self.size=(dp(30),dp(14))
        self._bg=bg
        self._lbl=Label(text=text,bold=True,color=fg,font_size=sp(8),
                        font_name=SST_FONT,halign="center",valign="middle")
        self.add_widget(self._lbl)
        self.bind(pos=self._redraw,size=self._redraw)
        Clock.schedule_once(self._redraw,0)
    def _redraw(self,*_):
        self.canvas.before.clear()
        if self.width<=0 or self.height<=0: return
        with self.canvas.before:
            Color(*self._bg); Rectangle(pos=self.pos,size=self.size)
            Color(1,1,1,0.3); Line(points=[self.x,self.top-dp(1),self.right,self.top-dp(1)],width=dp(1))
            Color(0,0,0,0.4); Line(points=[self.x,self.y,self.right,self.y],width=dp(1))
        self._lbl.pos=self.pos; self._lbl.size=self.size
        self._lbl.text_size=self.size

class BrandTile(Widget):
    """Square retailer tile, PS1 memory-card style."""
    def __init__(self,name,**kw):
        super().__init__(**kw)
        self._color=brand_color(name)
        self._lbl=Label(text=f"[b]{initials_for(name)}[/b]",markup=True,
                        color=text_on(self._color),font_size=sp(11),
                        font_name=SST_FONT,halign="center",valign="middle")
        self.add_widget(self._lbl)
        self.bind(pos=self._redraw,size=self._redraw)
        Clock.schedule_once(self._redraw,0)
    def _redraw(self,*_):
        self.canvas.before.clear()
        s=min(self.width,self.height)
        if s<=0: return
        x=self.x+(self.width-s)/2; y=self.y+(self.height-s)/2
        with self.canvas.before:
            Color(0,0,0,0.9); Rectangle(pos=(x-dp(1),y-dp(1)),
                                       size=(s+dp(2),s+dp(2)))
            Color(*self._color); Rectangle(pos=(x,y),size=(s,s))
            Color(1,1,1,0.28)
            Line(points=[x+dp(1),y+s-dp(1),x+s-dp(1),y+s-dp(1)],width=dp(1))
            Color(1,1,1,0.12)
            Line(points=[x+dp(1),y+dp(1),x+dp(1),y+s-dp(1)],width=dp(1))
            Color(0,0,0,0.45)
            Line(points=[x+dp(1),y+dp(1),x+s-dp(1),y+dp(1)],width=dp(1))
        self._lbl.font_size=max(dp(9),s*0.36)
        self._lbl.pos=(x,y); self._lbl.size=(s,s)
        self._lbl.text_size=(s,s)

class PSMark(Widget):
    """Silver PS monogram badge."""
    def __init__(self,**kw):
        super().__init__(**kw)
        self._lbl=Label(text="PS",bold=True,color=PS1_SILVER,font_name=SST_FONT,
                        halign="center",valign="middle")
        self.add_widget(self._lbl)
        self.bind(pos=self._redraw,size=self._redraw)
        Clock.schedule_once(self._redraw,0)
    def _redraw(self,*_):
        self.canvas.before.clear()
        s=min(self.width,self.height)
        if s<=0: return
        x=self.x+(self.width-s)/2; y=self.y+(self.height-s)/2
        with self.canvas.before:
            Color(0,0,0,0.9); Rectangle(pos=(x-dp(1),y-dp(1)),
                                       size=(s+dp(2),s+dp(2)))
            Color(0.80,0.80,0.82,1); Rectangle(pos=(x,y),size=(s,s))
            Color(1,1,1,0.55)
            Line(points=[x+dp(1),y+s-dp(1),x+s-dp(1),y+s-dp(1)],width=dp(2))
            Color(1,1,1,0.22)
            Line(points=[x+dp(1),y+dp(1),x+dp(1),y+s-dp(1)],width=dp(1))
            Color(0,0,0,0.45)
            Line(points=[x+dp(1),y+dp(1),x+s-dp(1),y+dp(1)],width=dp(2))
            Color(0,0,0,0.28)
            Line(points=[x+s-dp(1),y+dp(1),x+s-dp(1),y+s-dp(1)],width=dp(1))
            Color(0.09,0.09,0.10,1)
            Rectangle(pos=(x+dp(4),y+dp(4)),size=(s-dp(8),s-dp(8)))
            Color(0.18,0.18,0.20,1)
            Line(points=[x+dp(4),y+s-dp(4),x+s-dp(4),y+s-dp(4)],width=dp(1))
        self._lbl.font_size=max(dp(12),s*0.42)
        self._lbl.pos=(x,y); self._lbl.size=(s,s)
        self._lbl.text_size=(s,s)

# ══════════ PS1 TITLE BAR ══════════
class LogoWidget(FloatLayout):
    def __init__(self,**kw):
        super().__init__(**kw)
        self.size_hint=(1,None); self.height=dp(72)
        self._t=0.0
        with self.canvas.before:
            self._c_bg=Color(0.062,0.064,0.074,1)
            self._bg=Rectangle(pos=(0,0),size=(0,0))
            self._c_top=Color(0.30,0.31,0.35,1)
            self._top=Rectangle(pos=(0,0),size=(0,0))
            self._c_bot=Color(0,0,0,1)
            self._bot=Rectangle(pos=(0,0),size=(0,0))
            self._c_led=Color(*PS1_BLUE)
            self._led=Rectangle(pos=(0,0),size=(0,0))

        self.mark=PSMark(size_hint=(None,None),size=(dp(46),dp(46)))
        self.add_widget(self.mark)

        self.textbox=BoxLayout(orientation="vertical",size_hint=(None,None),
                               spacing=dp(1),padding=0)
        self.title=Label(markup=True,
                         text="[b]PLAYSTATION[/b] [color=3f8cff][b]5 PRO[/b][/color]",
                         color=PS1_SILVER,font_size=sp(18),font_name=SST_FONT,
                         halign="left",valign="middle",
                         shorten=True,shorten_from="right")
        self.sub=Label(text="S E A R C H   A G E N T",color=PS1_GREY,
                       font_size=sp(8.5),font_name=SST_FONT,bold=True,
                       halign="left",valign="middle")
        self.title.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        self.sub.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        self.textbox.add_widget(self.title); self.textbox.add_widget(self.sub)
        self.add_widget(self.textbox)

        self.symbols=PSShapesWidget(size=(dp(58),dp(13)))
        self.add_widget(self.symbols)

        self.bind(pos=self._sync,size=self._sync)
        Clock.schedule_once(self._sync,0)
        Clock.schedule_interval(self._anim,1/20)

    def _sync(self,*_):
        w,h=self.width,self.height
        if w<=0 or h<=0: return
        self._bg.pos=self.pos; self._bg.size=self.size
        self._top.pos=(self.x,self.top-dp(1)); self._top.size=(w,dp(1))
        self._bot.pos=(self.x,self.y); self._bot.size=(w,dp(2))
        self._led.pos=(self.x,self.top-dp(3)); self._led.size=(w,dp(2))

        ms=max(dp(30),min(dp(48),h-dp(20)))
        self.mark.size=(ms,ms)
        self.mark.pos=(self.x+dp(10),self.y+(h-ms)/2)

        symw=dp(58) if w>dp(340) else dp(44)
        symh=dp(13)
        self.symbols.size=(symw,symh)
        self.symbols.pos=(self.right-dp(10)-symw,self.y+(h-symh)/2)

        tx=self.mark.right+dp(10)
        tw=max(dp(100),self.right-dp(10)-symw-dp(10)-tx)
        th=max(dp(34),h-dp(16))
        self.textbox.pos=(tx,self.y+(h-th)/2); self.textbox.size=(tw,th)
        self.sub.size_hint_y=None; self.sub.height=dp(13)
        fs=max(sp(12),min(sp(19),tw*0.062))
        self.title.font_size=fs
        self.sub.font_size=max(sp(7),min(sp(10),fs*0.50))

    def _anim(self,dt):
        self._t+=dt
        a=0.35+0.55*(0.5+0.5*math.sin(self._t*2.0))
        self._c_led.rgba=(PS1_BLUE[0],PS1_BLUE[1],PS1_BLUE[2],a)

# ══════════ RESULT CARD (PS1 style, horizontal) ══════════
CARD_W = dp(246)

class ResultCard(ButtonBehavior, BoxLayout):
    def __init__(self,result,is_new,prev,**kw):
        super().__init__(**kw)
        self.result=result
        self._is_new=is_new; self._prev=prev
        self._down=None; self._moved=False
        self.orientation="vertical"
        self.size_hint=(None,1)
        self.width=CARD_W
        self.padding=(dp(11),dp(10))
        self.spacing=dp(3)
        self._build()
        self.bind(pos=self._redraw,size=self._redraw,state=self._redraw)
        if is_new:
            self.opacity=0
            Animation(opacity=1,d=0.25).start(self)
        Clock.schedule_once(self._redraw,0)

    def _redraw(self,*_):
        self.canvas.before.clear()
        if self.width<=0 or self.height<=0: return
        r=self.result
        co=CARD_STATUS.get(r["klass"],PS1_GREY)
        pressed=(getattr(self,"state","normal")=="down")
        bg=PS1_CARD_HI if pressed else PS1_CARD
        with self.canvas.before:
            # drop shadow
            Color(0,0,0,0.55)
            Rectangle(pos=(self.x-dp(1),self.y-dp(1)),
                      size=(self.width+dp(2),self.height+dp(2)))
            Color(*bg); Rectangle(pos=self.pos,size=self.size)
            # 90s bevel
            Color(1,1,1,0.12 if not pressed else 0.18)
            Line(points=[self.x,self.top-dp(1),self.right,self.top-dp(1)],width=dp(1))
            Color(0,0,0,0.55)
            Line(points=[self.x,self.y+dp(1),self.right,self.y+dp(1)],width=dp(1))
            # status edge
            Color(*co); Rectangle(pos=(self.x,self.y),size=(dp(3),self.height))
            if r["klass"]=="hit":
                Color(co[0],co[1],co[2],0.55)
                Line(rectangle=(self.x,self.y,self.width,self.height),width=dp(1))
            else:
                Color(1,1,1,0.10)
                Line(rectangle=(self.x,self.y,self.width,self.height),width=dp(1))

    def _build(self):
        r=self.result
        co=CARD_STATUS.get(r["klass"],PS1_GREY)

        # ── head: brand + readable retailer title
        head=BoxLayout(orientation="horizontal",size_hint_y=None,
                       height=dp(32),spacing=dp(8))
        head.add_widget(BrandTile(r["haendler"],size_hint=(None,None),
                                  size=(dp(30),dp(30))))
        info=BoxLayout(orientation="vertical",spacing=dp(0))
        name_str=re.sub(r"\s+(DE|AT)$","",r["haendler"]).strip()
        n=Label(text=f"[b]{name_str}[/b]",markup=True,color=PS1_TEXT,
                font_size=sp(13.5),font_name=SST_FONT,
                halign="left",valign="middle",
                shorten=True,shorten_from="right")
        n.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        info.add_widget(n)
        meta=BoxLayout(orientation="horizontal",size_hint_y=None,
                       height=dp(13),spacing=dp(4))
        meta.add_widget(FlagWidget(r["land"],size=(dp(16),dp(11))))
        m=Label(text=f"{r['land']} · PS5 PRO 2 TB · {r['zeit']}",
                color=PS1_GREY,font_size=sp(8.5),font_name=SST_FONT,
                halign="left",valign="middle",
                shorten=True,shorten_from="right")
        m.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        meta.add_widget(m)
        info.add_widget(meta)
        head.add_widget(info)
        self.add_widget(head)

        # ── price + difference to last scan
        prow=BoxLayout(orientation="horizontal",size_hint_y=1,spacing=dp(4))
        if r["preis"] is not None:
            p_txt=format_preis(r["preis"]); p_col=PS1_TEXT
        else:
            p_txt="—"; p_col=PS1_GREY
        p=Label(text=f"[b]{p_txt}[/b]",markup=True,color=p_col,
                font_size=sp(23),font_name=SST_FONT,
                halign="left",valign="middle")
        p.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        prow.add_widget(p)

        d_txt=""; d_col=PS1_GREY
        if r["preis"] is not None and self._prev is not None:
            diff=float(self._prev)-float(r["preis"])
            if diff>0.005:
                d_txt="-"+format_preis(abs(diff)); d_col=CARD_STATUS["hit"]
            elif diff<-0.005:
                d_txt="+"+format_preis(abs(diff)); d_col=CARD_STATUS["error"]
            else:
                d_txt="STABIL"; d_col=PS1_GREY
        if d_txt:
            d=Label(text=d_txt,color=d_col,font_size=sp(9),bold=True,
                    font_name=SST_FONT,halign="right",valign="middle",
                    size_hint_x=None,width=dp(62))
            d.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            prow.add_widget(d)
        self.add_widget(prow)

        # ── status line
        st_map={"hit":"VERFÜGBAR","expensive":"ZU TEUER","unknown":"PREIS OFFEN",
                "unavail":"NICHT VERFÜGBAR","error":"FEHLER","challenge":"BOT-SCHUTZ"}
        st=st_map.get(r["klass"],"?")
        bottom=BoxLayout(orientation="horizontal",size_hint_y=None,
                         height=dp(20),spacing=dp(5))
        bottom.add_widget(Dot(co))
        s=Label(text=f"[b]{st}[/b]",markup=True,color=co,
                font_size=sp(9),font_name=SST_FONT,
                halign="left",valign="middle",
                shorten=True,shorten_from="right")
        s.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        bottom.add_widget(s)
        if self._is_new:
            bottom.add_widget(Tag("NEU",PS1_YELLOW))
        bottom.add_widget(Widget())
        self.add_widget(bottom)

    def on_touch_down(self,touch):
        if self.collide_point(*touch.pos):
            self._down=touch.pos; self._moved=False
        return super().on_touch_down(touch)
    def on_touch_move(self,touch):
        if self._down and (abs(touch.x-self._down[0])+abs(touch.y-self._down[1]))>dp(14):
            self._moved=True
        return super().on_touch_move(touch)
    def on_release(self):
        if self._moved: return
        haptic(0.02); open_url(self.result["url"])
# ══════════ PICKER ══════════
class HandlerPickerContent(BoxLayout):
    def __init__(self,current,on_apply,**kw):
        super().__init__(**kw)
        self.orientation="vertical"; self.spacing=dp(6); self.padding=dp(8)
        self._on_apply=on_apply; self._cb={}
        with self.canvas.before:
            Color(0.055,0.058,0.066,1); self._bg=Rectangle(pos=(0,0),size=(0,0))
            Color(*PS1_EDGE); self._bd=Line(width=dp(1))
        self.bind(pos=self._sync,size=self._sync)

        self.add_widget(Label(text="[b]HÄNDLER AUSWÄHLEN[/b]",markup=True,
                              color=PS1_SILVER,font_size=sp(14),font_name=SST_FONT,
                              size_hint_y=None,height=dp(32)))
        q=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(5))
        for txt,fn in [("ALLE",lambda:self._all(True)),("KEINE",lambda:self._all(False)),
                       ("DE",lambda:self._land("DE")),("AT",lambda:self._land("AT"))]:
            b=PS1Button(text=txt,accent=PS1_BLUE,font_size=sp(10))
            b.bind(on_release=lambda _,f=fn:f()); q.add_widget(b)
        self.add_widget(q)

        sv=ScrollView(bar_width=dp(4),bar_color=PS1_SILVER,
                      bar_inactive_color=(0.3,0.3,0.34,0.5))
        inner=BoxLayout(orientation="vertical",size_hint_y=None,
                        spacing=dp(1),padding=(dp(2),dp(2)))
        inner.bind(minimum_height=inner.setter("height"))
        for h in HAENDLER:
            row=BoxLayout(size_hint_y=None,height=dp(34),spacing=dp(6))
            cb=CheckBox(active=(h["name"] in current),size_hint_x=None,
                        width=dp(34),color=PS1_SILVER)
            self._cb[h["name"]]=cb
            row.add_widget(cb)
            row.add_widget(FlagWidget(h["land"],size=(dp(18),dp(12))))
            lb=Label(text=h["name"],color=PS1_TEXT,font_size=sp(11.5),font_name=SST_FONT,
                     halign="left",valign="middle")
            lb.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            row.add_widget(lb); inner.add_widget(row)
        sv.add_widget(inner); self.add_widget(sv)

        ft=BoxLayout(size_hint_y=None,height=dp(44),spacing=dp(6))
        c=PS1Button(text="ABBRECHEN",accent=PS1_RED,font_size=sp(10))
        c.bind(on_release=lambda *_:self._on_apply(None,"cancelled")); ft.add_widget(c)
        a=PS1Button(text="ÜBERNEHMEN",accent=PS1_BLUE,font_size=sp(10))
        a.bind(on_release=lambda *_:self._do()); ft.add_widget(a)
        self.add_widget(ft)

    def _sync(self,*_):
        if not hasattr(self,"_bg"): return
        self._bg.pos=self.pos; self._bg.size=self.size
        self._bd.rectangle=(self.x,self.y,self.width,self.height)
    def _all(self,v):
        for cb in self._cb.values(): cb.active=v
    def _land(self,l):
        mp={h["name"]:h["land"] for h in HAENDLER}
        for n,cb in self._cb.items(): cb.active=(mp.get(n)==l)
    def _do(self):
        s={n for n,cb in self._cb.items() if cb.active}
        if not s: self._on_apply(None,"empty")
        else: self._on_apply(s,None)

# ══════════ MAIN UI ══════════
class MainUI(FloatLayout):
    def __init__(self,**kw):
        super().__init__(**kw)
        self.scanning=False; self.scanned={}; self.settings=Settings()
        saved=self.settings.get("active_haendler")
        if saved:
            self.active_haendler=set(saved)&{h["name"] for h in HAENDLER}
            if not self.active_haendler: self.active_haendler={h["name"] for h in HAENDLER}
        else:
            self.active_haendler={h["name"] for h in HAENDLER}
        self.filter_mode=self.settings.get("filter","verfuegbar")
        self.sort_mode=self.settings.get("sort","Preis")
        mp=self.settings.get("max_preis",MAX_PREIS)
        self.max_preis=mp if mp in PRICE_OPTIONS else MAX_PREIS
        self.auto_scan=bool(self.settings.get("auto_scan",False))
        ai=self.settings.get("auto_interval",600)
        self.auto_interval=ai if ai in [x[0] for x in AUTO_INTERVALS] else 600
        self.next_scan_at=0.0; self._auto_event=None
        self.notify_enabled=bool(self.settings.get("notify",True))
        self._known_hits=set(); self.queue=queue.Queue()
        self._scan_token=0
        self.history=History(); self._scan_t0=0.0; self._scan_done=0
        self._scan_total=0; self._rerender_event=None; self._drain_event=None
        self._resize_event=None; self._placeholder=None; self._last_sig=None
        self._build_ui()
        Window.bind(size=self._on_window_size)
        Clock.schedule_once(lambda dt:self._apply_sizes(),0)
        Clock.schedule_once(lambda dt:self._apply_sizes(),0.2)
        if self.auto_scan: Clock.schedule_once(lambda dt:self._auto_start(),1.5)

    # ── Aufbau ──────────────────────────────────────────────────────
    def _build_ui(self):
        # Radar fullscreen
        self.radar=RadarWidget(size_hint=(1,1),pos_hint={"x":0,"y":0})
        self.add_widget(self.radar)

        # PS1 title bar
        self.logo=LogoWidget(); self.logo.pos_hint={"x":0,"top":1}
        self.add_widget(self.logo)

        # Results panel
        self.results_panel=BoxLayout(orientation="vertical",
                                     size_hint=(None,None),spacing=0,padding=0)
        with self.results_panel.canvas.before:
            Color(0.055,0.058,0.066,0.96)
            self._rp_bg=Rectangle(pos=(0,0),size=(1,1))
            Color(*PS1_EDGE); self._rp_top=Rectangle(pos=(0,0),size=(1,1))
        self.results_panel.bind(pos=self._sync_rp,size=self._sync_rp)

        # Header: status, count, scroll arrows
        self.results_header=BoxLayout(orientation="horizontal",size_hint_y=None,
                                      height=dp(28),padding=(dp(6),dp(2)),
                                      spacing=dp(4))
        with self.results_header.canvas.before:
            Color(0.085,0.089,0.100,1)
            self._rh_bg=Rectangle(pos=(0,0),size=(1,1))
            Color(*PS1_EDGE); self._rh_top=Rectangle(pos=(0,0),size=(1,1))
            Color(0,0,0,1); self._rh_bot=Rectangle(pos=(0,0),size=(1,1))
        self.results_header.bind(pos=self._sync_header,size=self._sync_header)

        self.results_status=Label(text="BEREIT ZUM SCANNEN",
                                  color=PS1_SILVER,font_size=sp(9),
                                  bold=True,font_name=SST_FONT,
                                  halign="left",valign="middle")
        self.results_status.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        self.results_header.add_widget(self.results_status)

        self.results_count=Label(text="0/0",color=PS1_GREY,font_size=sp(9),
                                 bold=True,font_name=SST_FONT,
                                 halign="right",valign="middle",
                                 size_hint=(None,1),width=dp(52))
        self.results_count.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        self.results_header.add_widget(self.results_count)

        self.prev_btn=PS1Button(text="<",accent=PS1_BLUE,font_size=sp(11),
                                size_hint=(None,1),width=dp(24))
        self.prev_btn.bind(on_release=lambda *_:self._scroll_step(-1))
        self.results_header.add_widget(self.prev_btn)
        self.next_btn=PS1Button(text=">",accent=PS1_BLUE,font_size=sp(11),
                                size_hint=(None,1),width=dp(24))
        self.next_btn.bind(on_release=lambda *_:self._scroll_step(1))
        self.results_header.add_widget(self.next_btn)
        self.results_panel.add_widget(self.results_header)

        # Horizontal hit list
        self.results_scroll=HScrollView()
        self.results_row=BoxLayout(orientation="horizontal",
                                   size_hint=(None,1),
                                   spacing=dp(8),padding=(dp(8),dp(6)))
        self.results_row.bind(minimum_width=self.results_row.setter("width"))
        self.results_scroll.add_widget(self.results_row)
        self.results_scroll.bind(width=lambda w,v:self._resize_placeholder(v))
        self.results_panel.add_widget(self.results_scroll)
        self.add_widget(self.results_panel)

        # Controls
        self.controls=BoxLayout(orientation="horizontal",
                                size_hint=(None,None),spacing=dp(4),
                                padding=(dp(4),dp(4)))
        with self.controls.canvas.before:
            Color(*PS1_PANEL); self._ctrl_bg=Rectangle(pos=(0,0),size=(1,1))
            Color(*PS1_EDGE); self._ctrl_top=Rectangle(pos=(0,0),size=(1,1))
            Color(0,0,0,1); self._ctrl_bot=Rectangle(pos=(0,0),size=(1,1))
        self.controls.bind(pos=self._sync_ctrl,size=self._sync_ctrl)

        self.scan_btn=PS1Button(text="SCAN",accent=PS1_BLUE,
                                 size_hint=(None,1),width=dp(64),
                                 font_size=sp(11))
        self.scan_btn.bind(on_release=lambda *_:self._scan_toggle())
        self.controls.add_widget(self.scan_btn)

        self.chip_scroll=ScrollView(do_scroll_x=True,do_scroll_y=False,
                                     bar_width=0,scroll_type=["content"])
        chips=BoxLayout(orientation="horizontal",size_hint=(None,1),spacing=dp(4))
        chips.bind(minimum_width=chips.setter("width"))

        self.haendler_btn=PS1Button(text=f"HÄNDLER {len(self.active_haendler)}",
                                     accent=PS1_BLUE,size_hint=(None,1),width=dp(84),
                                     font_size=sp(9.5))
        self.haendler_btn.bind(on_release=lambda *_:self._open_haendler_picker())
        chips.add_widget(self.haendler_btn)

        self.chip_verf=Chip(text="TREFFER",accent=PS1_GREEN,
                             state="down" if self.filter_mode=="verfuegbar" else "normal",
                             width=dp(68))
        self.chip_all=Chip(text="ALLE",accent=PS1_YELLOW,
                            state="down" if self.filter_mode=="alle" else "normal",
                            width=dp(50))
        self.chip_verf.bind(on_release=lambda *_:self._set_filter("verfuegbar"))
        self.chip_all.bind(on_release=lambda *_:self._set_filter("alle"))
        chips.add_widget(self.chip_verf); chips.add_widget(self.chip_all)

        self.auto_chip=Chip(text="AUTO",accent=PS1_YELLOW,
                             state="down" if self.auto_scan else "normal",
                             width=dp(52))
        self.auto_chip.bind(on_release=lambda *_:self._toggle_auto())
        chips.add_widget(self.auto_chip)

        self.interval_chip=Chip(text=self._interval_text(),accent=PS1_PINK,width=dp(56))
        self.interval_chip.bind(on_release=lambda *_:self._cycle_interval())
        chips.add_widget(self.interval_chip)

        self.notify_chip=Chip(text="ALARM",accent=PS1_PINK,
                               state="down" if self.notify_enabled else "normal",
                               width=dp(58))
        self.notify_chip.bind(on_release=lambda *_:self._toggle_notify())
        chips.add_widget(self.notify_chip)

        self.max_preis_chip=Chip(text=self._max_text(),accent=PS1_RED,width=dp(80))
        self.max_preis_chip.bind(on_release=lambda *_:self._cycle_max_preis())
        chips.add_widget(self.max_preis_chip)

        self.sort_chip=Chip(text=self._sort_text(),accent=PS1_BLUE,width=dp(104))
        self.sort_chip.bind(on_release=lambda *_:self._cycle_sort())
        chips.add_widget(self.sort_chip)

        self.chip_scroll.add_widget(chips)
        self.controls.add_widget(self.chip_scroll)
        self.add_widget(self.controls)

        mp_txt="offen" if self.max_preis is None else f"{int(self.max_preis)} €"
        self._show_placeholder("SYSTEM BEREIT",
                               f"PS5 PRO 2 TB · PREIS MAX {mp_txt}")

    # ── Text-Helfer ─────────────────────────────────────────────────
    def _interval_text(self):
        lbl=next((l for s,l in AUTO_INTERVALS if s==self.auto_interval),"10m")
        return lbl.replace("m"," MIN").upper()
    def _max_text(self):
        return "MAX OFFEN" if self.max_preis is None else f"MAX {int(self.max_preis)} €"
    def _sort_text(self):
        return f"SORT: {self.sort_mode.upper()}"

    # ── Canvas-Sync ─────────────────────────────────────────────────
    def _sync_rp(self,*_):
        if not hasattr(self,"_rp_bg"): return
        self._rp_bg.pos=self.results_panel.pos
        self._rp_bg.size=self.results_panel.size
        self._rp_top.pos=(self.results_panel.x,self.results_panel.top-dp(1))
        self._rp_top.size=(self.results_panel.width,dp(1))
    def _sync_header(self,*_):
        if not hasattr(self,"_rh_bg"): return
        self._rh_bg.pos=self.results_header.pos
        self._rh_bg.size=self.results_header.size
        self._rh_top.pos=(self.results_header.x,self.results_header.top-dp(1))
        self._rh_top.size=(self.results_header.width,dp(1))
        self._rh_bot.pos=(self.results_header.x,self.results_header.y)
        self._rh_bot.size=(self.results_header.width,dp(1))
    def _sync_ctrl(self,*_):
        if not hasattr(self,"_ctrl_bg"): return
        self._ctrl_bg.pos=self.controls.pos
        self._ctrl_bg.size=self.controls.size
        self._ctrl_top.pos=(self.controls.x,self.controls.top-dp(1))
        self._ctrl_top.size=(self.controls.width,dp(1))
        self._ctrl_bot.pos=(self.controls.x,self.controls.y)
        self._ctrl_bot.size=(self.controls.width,dp(1))

    def _on_window_size(self,*_):
        if self._resize_event is not None: Clock.unschedule(self._resize_event)
        self._resize_event=Clock.schedule_once(lambda dt:self._apply_sizes(),0.05)
    def _apply_sizes(self):
        try:
            w,h=Window.width,Window.height
            if w<=0 or h<=0:
                Clock.schedule_once(lambda dt:self._apply_sizes(),0.15); return
            if h<dp(500): lh,rh,ch=dp(56),dp(160),dp(42)
            elif h<dp(700): lh,rh,ch=dp(64),dp(178),dp(46)
            else: lh,rh,ch=dp(72),dp(190),dp(50)
            self.logo.height=lh
            self.controls.pos=(0,0); self.controls.size=(w,ch)
            self.results_panel.pos=(0,ch); self.results_panel.size=(w,rh)
            self.radar.reserve_bottom=ch+rh; self.radar.reserve_top=lh
        except Exception as e: print(f"[Sizes] {e}")

    # ── Bedienung ───────────────────────────────────────────────────
    def _scroll_step(self,direction):
        row_w=self.results_row.width; view_w=self.results_scroll.width
        span=row_w-view_w
        if span<=dp(2): return
        cur=self.results_scroll.scroll_x*span
        target=min(max(0.0,cur+direction*max(dp(120),view_w*0.8)),span)
        Animation.cancel_all(self.results_scroll,"scroll_x")
        Animation(scroll_x=target/span,d=0.18,transition="out_quad").start(self.results_scroll)

    def _set_filter(self,m):
        self.filter_mode=m
        self.chip_verf.state=("down" if m=="verfuegbar" else "normal")
        self.chip_all.state=("down" if m=="alle" else "normal")
        self.settings.set("filter",m); self._rerender()
    def _cycle_sort(self):
        o=["Preis","Händler","Zeit"]
        self.sort_mode=o[(o.index(self.sort_mode)+1)%3]
        self.sort_chip.text=self._sort_text()
        self.settings.set("sort",self.sort_mode); self._rerender()
    def _cycle_max_preis(self):
        try: idx=PRICE_OPTIONS.index(self.max_preis)
        except ValueError: idx=PRICE_OPTIONS.index(MAX_PREIS)
        self.max_preis=PRICE_OPTIONS[(idx+1)%len(PRICE_OPTIONS)]
        self.max_preis_chip.text=self._max_text()
        self.settings.set("max_preis",self.max_preis)
        self._reclassify_all(); self._rerender()
    def _reclassify_all(self):
        for r in self.scanned.values():
            if r["klass"] in ("error","challenge","unavail"): continue
            if r["preis"] is None: r["klass"]="unknown"
            elif self.max_preis is None or r["preis"]<=self.max_preis: r["klass"]="hit"
            else: r["klass"]="expensive"
        nb=[]
        for b in self.radar.blips:
            n=b.get("name")
            nb.append({**b,"klass":self.scanned[n]["klass"]} if n and n in self.scanned else b)
        self.radar.blips=nb
    def _toggle_auto(self):
        self.auto_scan=not self.auto_scan
        self.auto_chip.state=("down" if self.auto_scan else "normal")
        self.settings.set("auto_scan",self.auto_scan)
        if self.auto_scan: self._auto_start()
        else: self._auto_stop()
    def _auto_start(self):
        haptic(0.05); self.next_scan_at=time.time()+self.auto_interval
        if self._auto_event is None:
            self._auto_event=Clock.schedule_interval(self._auto_tick,1.0)
        self._toast("AUTO AKTIV",color=CARD_STATUS["hit"])
        if not self.scanning: self._scan_start()
    def _auto_stop(self):
        if self._auto_event is not None:
            Clock.unschedule(self._auto_event); self._auto_event=None
        self.next_scan_at=0; self._toast("AUTO GESTOPPT",color=PS1_YELLOW)
    def _auto_tick(self,dt):
        if not self.auto_scan: return False
        rem=self.next_scan_at-time.time()
        if rem<=0 and not self.scanning:
            self.next_scan_at=time.time()+self.auto_interval; self._scan_start()
        elif rem>0 and not self.scanning:
            self.results_status.text=f"NÄCHSTER SCAN IN {int(rem//60):02d}:{int(rem%60):02d}"
        return True
    def _cycle_interval(self):
        iv=[x[0] for x in AUTO_INTERVALS]
        try: i=iv.index(self.auto_interval)
        except ValueError: i=1
        self.auto_interval=iv[(i+1)%len(iv)]
        self.interval_chip.text=self._interval_text()
        self.settings.set("auto_interval",self.auto_interval)
        if self.auto_scan: self.next_scan_at=time.time()+self.auto_interval
    def _toggle_notify(self):
        self.notify_enabled=not self.notify_enabled
        self.notify_chip.state=("down" if self.notify_enabled else "normal")
        self.settings.set("notify",self.notify_enabled)
    def _maybe_notify(self,name,preis,is_new):
        if not self.notify_enabled: return
        key=(name,round(preis,2))
        if key in self._known_hits: return
        self._known_hits.add(key)
        if len(self._known_hits)>200:
            self._known_hits=set(list(self._known_hits)[-100:])
        msg=f"{name}: {format_preis(preis)}"
        try: ok=notify("PS5 PRO 2TB VERFÜGBAR",msg)
        except Exception: ok=False
        if not ok:
            try: self._toast(msg,color=CARD_STATUS["hit"])
            except Exception: pass
    def _open_haendler_picker(self):
        haptic(0.02); ref={"p":None}
        def on_apply(sel,err):
            if err=="cancelled":
                if ref["p"]: ref["p"].dismiss()
                return
            if err=="empty":
                self._toast("MINDESTENS EINEN HÄNDLER WÄHLEN",PS1_YELLOW); return
            self.active_haendler=sel
            self.haendler_btn.text=f"HÄNDLER {len(self.active_haendler)}"
            self.settings.set("active_haendler",list(sel))
            if ref["p"]: ref["p"].dismiss()
        c=HandlerPickerContent(current=self.active_haendler,on_apply=on_apply)
        ph=max(dp(260),min(Window.height*0.7,Window.height-dp(80)))
        p=Popup(title="",content=c,size_hint=(0.94,None),height=ph,
                pos_hint={"center_x":0.5,"y":0.02},
                background_color=(0.08,0.08,0.09,1),separator_height=0)
        ref["p"]=p; p.open()
    def _toast(self,text,color=None):
        app=App.get_running_app()
        if app and hasattr(app,"root_layout") and hasattr(app.root_layout,"toast"):
            app.root_layout.toast.show(text,color=color)

    # ── Liste ───────────────────────────────────────────────────────
    def _clear_results(self):
        self.results_row.clear_widgets()
        self._placeholder=None; self._last_sig=None
    def _resize_placeholder(self,w):
        if self._placeholder is not None:
            self._placeholder.width=max(dp(240),w)
    def _show_placeholder(self,titel,unter):
        self._clear_results()
        w=(self.results_scroll.width if self.results_scroll.width>dp(20)
           else Window.width-dp(16))
        box=BoxLayout(orientation="vertical",size_hint=(None,1),
                      width=max(dp(240),w),
                      spacing=dp(2),padding=dp(10))
        box.add_widget(Widget())
        symrow=BoxLayout(orientation="horizontal",size_hint_y=None,height=dp(20))
        symrow.add_widget(Widget())
        symrow.add_widget(PSShapesWidget(size=(dp(86),dp(18))))
        symrow.add_widget(Widget())
        box.add_widget(symrow)
        t=Label(text=f"[b]{titel}[/b]",markup=True,color=PS1_SILVER,
                font_size=sp(13),font_name=SST_FONT,
                halign="center",valign="middle",
                size_hint_y=None,height=dp(26))
        t.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); box.add_widget(t)
        if unter:
            u=Label(text=unter,color=PS1_GREY,font_size=sp(9),
                    font_name=SST_FONT,halign="center",valign="middle",
                    size_hint_y=None,height=dp(18))
            u.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); box.add_widget(u)
        box.add_widget(Widget())
        self._placeholder=box
        self.results_row.add_widget(box)

    def _rerender(self):
        if not self.scanned:
            self.results_count.text="0/0"
            self._show_placeholder("SYSTEM BEREIT","TIPPE AUF SCAN"); return
        namen=[n for n in self.scanned
               if self.filter_mode=="alle" or self.scanned[n]["klass"]=="hit"]
        self.results_count.text=f"{len(namen)}/{len(self.scanned)}"
        if not namen:
            if self.filter_mode=="alle":
                msg=f"{len(self.scanned)} GEPRÜFT · KEINE TREFFER"
            else:
                msg=f"{len(self.scanned)} GEPRÜFT · 'ALLE' FÜR DETAILS"
            self._show_placeholder("KEINE TREFFER",msg); return
        if self.sort_mode=="Preis":
            namen.sort(key=lambda n:(self.scanned[n]["preis"]
                                     if self.scanned[n]["preis"] is not None
                                     else 99999))
        elif self.sort_mode=="Händler":
            namen.sort(key=lambda n:n.lower())
        else:
            namen.sort(key=lambda n:self.scanned[n]["zeit"],reverse=True)

        sig=tuple((n,self.scanned[n]["klass"],self.scanned[n]["preis"],
                   self.scanned[n].get("_is_new")) for n in namen)
        if sig==self._last_sig and self._placeholder is None:
            return
        sx=self.results_scroll.scroll_x
        self._clear_results()
        self._last_sig=sig
        for n in namen:
            r=self.scanned[n]
            self.results_row.add_widget(
                ResultCard(r,r.get("_is_new",False),r.get("_prev")))
        if sx>0:
            Clock.schedule_once(lambda dt:setattr(self.results_scroll,"scroll_x",sx),0)

    def _rerender_throttled(self):
        if self._rerender_event is None:
            self._rerender_event=Clock.schedule_once(lambda dt:self._do_throttled(),0.2)
    def _do_throttled(self,*_):
        self._rerender_event=None
        if self.scanned: self._rerender()

    # ── Scan ────────────────────────────────────────────────────────
    def _scan_toggle(self):
        if self.scanning: self._scan_cancel()
        else: self._scan_start()
    def _scan_start(self):
        if self.scanning: return
        aktive=[h for h in HAENDLER if h["name"] in self.active_haendler]
        if not aktive:
            self._toast("MINDESTENS EINEN HÄNDLER WÄHLEN",PS1_YELLOW); return
        haptic(0.05); self.scanning=True; self.scanned={}
        self._scan_token+=1; tok=self._scan_token
        self._drain_stale()
        self.radar.blips=[]; self.radar.scanning=True
        self._clear_results()
        self._show_placeholder("SCANNE...","TIPPE STOP ZUM ABBRECHEN")
        self.scan_btn.text="STOP"
        self._scan_t0=time.time(); self._scan_done=0
        self._scan_total=len(aktive)
        self.results_count.text=f"0/{len(aktive)}"
        self.results_status.text=f"SCANNE 0 / {len(aktive)}"
        threading.Thread(target=self._scan_worker,args=(aktive,tok),daemon=True).start()
        if self._drain_event is not None: Clock.unschedule(self._drain_event)
        self._drain_event=Clock.schedule_interval(self._drain_queue,0.08)
    def _drain_stale(self):
        """Ergebnisse eines abgebrochenen Scans darf der nächste Lauf nicht erben."""
        while True:
            try: self.queue.get_nowait()
            except queue.Empty: break
    def _scan_cancel(self):
        if not self.scanning: return
        self._scan_token+=1
        haptic(0.03); self._scan_end(abgebrochen=True)
    def _scan_worker(self,hl,tok):
        with ThreadPoolExecutor(max_workers=WORKER) as ex:
            futs={ex.submit(_safe_scan,h):h for h in hl}
            for f in as_completed(futs):
                if tok!=self._scan_token: return
                try: r=f.result()
                except Exception as e: r=_res(futs[f],None,"error",0,str(e)[:60])
                self.queue.put((tok,r))
    def _drain_queue(self,dt):
        while True:
            try: tok,r=self.queue.get_nowait()
            except queue.Empty: break
            if tok==self._scan_token and self.scanning:
                try: self._process(r)
                except Exception as e: print(f"[Scan] {r.get('haendler','?')}: {e}")
        if not self.scanning: self._drain_event=None; return False
        return True
    def _process(self,r):
        if not self.scanning: return
        self._scan_done+=1; name=r.get("haendler","?")
        try:
            if r["klass"] not in ("error","challenge","unavail"):
                r["klass"]=classify(True,r["preis"],self.max_preis)
            prev=self.history.get_last(name); r["_prev"]=prev
            r["_is_new"]=(r["klass"]=="hit" and r["preis"] is not None
                         and (prev is None or r["preis"]<prev-0.01))
            self.scanned[name]=r
            self._update_blip(name,r["klass"])
            hits=sum(1 for x in self.scanned.values() if x["klass"]=="hit")
            self.results_status.text=(f"SCANNE {self._scan_done}/{self._scan_total}"
                                      + (f" · {hits} TREFFER" if hits else ""))
            self.results_count.text=f"{hits}/{self._scan_done}" if self.filter_mode=="verfuegbar" else f"{self._scan_done}/{self._scan_total}"
            if r["klass"]=="hit" and r["preis"] is not None:
                self._maybe_notify(name,r["preis"],r["_is_new"])
            self._rerender_throttled()
        except Exception as e:
            print(f"[Scan] {name}: {e}")
        if self._scan_done>=self._scan_total: self._scan_end()
    def _update_blip(self,name,klass):
        h=int(hashlib.md5(name.encode()).hexdigest()[:8],16)
        ang=math.radians(h%360); dist=0.25+(h%60)/100.0
        self.radar.blips=([b for b in self.radar.blips if b["name"]!=name]
            +[{"name":name,"x":dist*math.cos(ang),"y":dist*math.sin(ang),
               "klass":klass,"intensity":1.0}])
    def _scan_end(self,abgebrochen=False):
        if not self.scanning: return
        self.scanning=False; self.radar.scanning=False
        self.scan_btn.text="SCAN"
        d=time.time()-self._scan_t0
        hits=[x for x in self.scanned.values() if x["klass"]=="hit"]
        new=sum(1 for x in self.scanned.values() if x.get("_is_new"))
        self._rerender(); self.history.update(self.scanned.values())
        ts=datetime.now().strftime("%H:%M")
        if abgebrochen:
            self.results_status.text=(f"ABGEBROCHEN · {self._scan_done}/{self._scan_total}"
                                      f" GEPRÜFT · {ts}")
            self._toast("SCAN ABGEBROCHEN",color=PS1_YELLOW)
        elif hits:
            self.results_status.text=f"{len(hits)} TREFFER · {d:.0f}s · {ts}"
            haptic(0.12)
            if new>0: self._toast(f"{new} NEUE TREFFER",color=PS1_YELLOW)
            else: self._toast(f"{len(hits)} TREFFER",color=CARD_STATUS["hit"])
        else:
            self.results_status.text=f"KEINE TREFFER · {d:.0f}s · {ts}"
            blk=sum(1 for x in self.scanned.values() if x["klass"]=="challenge")
            err=sum(1 for x in self.scanned.values() if x["klass"]=="error")
            teile=[f"{len(self.scanned)} GEPRÜFT"]
            if blk: teile.append(f"{blk} BOT-SCHUTZ")
            if err: teile.append(f"{err} FEHLER")
            self._show_placeholder("KEINE TREFFER"," · ".join(teile))
        if self.auto_scan: self.next_scan_at=time.time()+self.auto_interval
# ══════════ ROOT + APP ══════════
class RootLayout(FloatLayout):
    def __init__(self,**kw):
        super().__init__(**kw)
        self.main_ui=MainUI(); self.add_widget(self.main_ui)
        self.toast=Toast(); self.add_widget(self.toast)

class PS5ProApp(App):
    title="Playstation 5 Pro Search Agent"
    def build(self):
        Window.clearcolor=C_BG
        try:
            if platform in ("android","ios"): Window.fullscreen='auto'
        except Exception: pass
        request_android_permissions()
        self.root_layout=RootLayout(); return self.root_layout
    def on_pause(self): return True
    def on_resume(self):
        try:
            ui=self.root_layout.main_ui
            if ui.auto_scan and not ui.scanning:
                if time.time()>=ui.next_scan_at: ui._scan_start()
        except Exception: pass

if __name__=="__main__":
    import traceback
    try: PS5ProApp().run()
    except Exception:
        err=traceback.format_exc()
        print("\n\n=== STARTUP CRASH ===\n"+err+"\n=====================\n")
        try:
            from kivy.uix.popup import Popup
            c=ScrollView()
            l=Label(text=err,text_size=(dp(400),None),size_hint_y=None,markup=False)
            l.bind(texture_size=l.setter("size")); c.add_widget(l)
            Popup(title="Startup Error",content=c,size_hint=(0.95,0.85)).open()
        except Exception: pass
