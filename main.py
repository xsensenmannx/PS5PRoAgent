"""PS5 Pro Search Agent v5.1 - PS1 Edition"""
import os, sys, json, re, time, math, random, queue, threading, hashlib
from datetime import datetime
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
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.animation import Animation
from kivy.utils import get_color_from_hex, platform

from scan_core import (
    HAENDLER, MAX_PREIS, BG_STATUS_FILE, format_preis, classify,
    _safe_scan, _res, WORKER, History, Settings, data_dir, Health, health, reset_health,
    alarm_erlaubt, alarm_ereignis, ist_gebraucht, install_crash_hook, read_crash_log,
    lade_shop_config, aktualisiere_shop_config, flush_http_cache,
)

# Nur fuer die Oberflaeche: Preislimit-Auswahl, Sortierung, Auto-Intervalle.
PRICE_OPTIONS = [700.0, 800.0, 900.0, None]
SORT_OPTIONS = ["Preis","H\u00e4ndler","Zeit"]
AUTO_INTERVALS = [(300,"5m"),(600,"10m"),(900,"15m"),(1800,"30m"),(3600,"60m")]
FONT_SCALES = [1.0,1.1,1.2]
# Abstand zwischen dem sichtbaren Radar und der darunterliegenden Trefferliste.
# Ohne diesen Puffer lagen die unteren Gradzahlen/der äußere Radarring genau
# auf der oberen Panelkante und wurden von ihr angeschnitten.
RADAR_PANEL_GAP = dp(12)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
try: os.makedirs(FONT_DIR, exist_ok=True)
except OSError: pass   # schreibgeschuetztes Installationsverzeichnis: Roboto bleibt
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
PS1_CYAN     = get_color_from_hex("#79d7ff")
PS1_ICE      = get_color_from_hex("#d8e7f2")

PS_TRIANGLE = (0.11,0.66,0.30,1)
PS_CIRCLE   = (0.90,0.10,0.10,1)
PS_CROSS    = (0.11,0.35,0.65,1)
PS_SQUARE   = (0.85,0.11,0.46,1)

STATUS_COLORS = {"hit":get_color_from_hex("#3ddc84"),"expensive":C_ORANGE,
                 "unknown":C_YELLOW,"unavail":C_GRAY,"error":C_RED,
                 "challenge":C_YELLOW,"parser":PS1_RED}
CARD_STATUS = {"hit":get_color_from_hex("#3ddc84"),"expensive":PS1_YELLOW,
               "unknown":get_color_from_hex("#9aa3ad"),
               "unavail":get_color_from_hex("#6b7280"),
               "error":get_color_from_hex("#ff5c5c"),
               "challenge":PS1_YELLOW,"parser":PS1_RED}

# Radar (PS1 BIOS blue instead of phosphor green)
RADAR_BG    = get_color_from_hex("#05070c")
RADAR_DISH  = get_color_from_hex("#0a1424")
RADAR_RING  = get_color_from_hex("#2a5f94")
RADAR_GRID  = get_color_from_hex("#183a5c")
RADAR_DIM   = get_color_from_hex("#122b45")
RADAR_TICK  = get_color_from_hex("#2f6fa8")
RADAR_SWEEP = get_color_from_hex("#5aa8ff")
RADAR_TXT   = get_color_from_hex("#4f86b8")

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

def open_app_settings():
    """Systemseite der App - dort liegen Akku-Optimierung und Benachrichtigungen."""
    if platform=="android":
        try:
            from jnius import autoclass
            PA=autoclass("org.kivy.android.PythonActivity")
            Intent=autoclass("android.content.Intent")
            Uri=autoclass("android.net.Uri")
            Settings=autoclass("android.provider.Settings")
            i=Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                     Uri.parse("package:"+PA.mActivity.getPackageName()))
            i.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            PA.mActivity.startActivity(i); return
        except Exception: pass
    try:
        import webbrowser
        webbrowser.open("https://support.google.com/android/answer/7664352")
    except Exception: pass

def consume_deep_link():
    """URL aus einer angetippten Benachrichtigung holen und danach entfernen."""
    if platform!="android": return None
    try:
        from jnius import autoclass
        act=autoclass("org.kivy.android.PythonActivity").mActivity
        intent=act.getIntent()
        if intent is None: return None
        u=intent.getStringExtra("ps5pro_url")
        if not u: return None
        # Extra entfernen, damit ein Resume/Rotation den Shop nicht erneut oeffnet.
        intent.removeExtra("ps5pro_url"); act.setIntent(intent)
        return u
    except Exception: return None

def haptic(d=0.05):
    if platform!="android": return
    try:
        from jnius import autoclass
        C=autoclass("android.content.Context"); PA=autoclass("org.kivy.android.PythonActivity")
        v=PA.mActivity.getSystemService(C.VIBRATOR_SERVICE)
        if v.hasVibrator(): v.vibrate(int(max(1,d*1000)))
    except Exception: pass

def share_text(text):
    """Text (z. B. Crash-Log) ueber den Android-Teilen-Dialog ausgeben."""
    if platform=="android":
        try:
            from jnius import autoclass
            PA=autoclass("org.kivy.android.PythonActivity")
            Intent=autoclass("android.content.Intent")
            i=Intent(Intent.ACTION_SEND); i.setType("text/plain")
            i.putExtra(Intent.EXTRA_TEXT,str(text))
            PA.mActivity.startActivity(Intent.createChooser(i,"Fehlerbericht teilen"))
            return True
        except Exception: pass
    try: print(text); return True
    except Exception: return False

_NOTIFY_SEQ=[int(time.time())%100000]

def _next_notify_id():
    _NOTIFY_SEQ[0]=(_NOTIFY_SEQ[0]+1)%100000
    return _NOTIFY_SEQ[0]

def notify(t,m,url=None):
    if platform=="android":
        try:
            from jnius import autoclass
            PA=autoclass("org.kivy.android.PythonActivity")
            C=autoclass("android.content.Context")
            NB=autoclass("android.app.Notification$Builder")
            a=PA.mActivity; b=NB(a); b.setContentTitle(t); b.setContentText(m)
            # Kleines Icon: die App-Icon-Ressource ist seit API 26 ein adaptives
            # Icon (XML) und als Small-Icon ungueltig - Android verwirft die Meldung
            # dann stillschweigend. Ein System-Drawable ist immer zulaessig.
            try:
                si=autoclass("android.R$drawable").stat_notify_chat
            except Exception:
                si=a.getApplicationInfo().icon
            b.setSmallIcon(si); b.setAutoCancel(True)
            b.setGroup("ps5pro_hits")
            try:
                Intent=autoclass("android.content.Intent")
                PendingIntent=autoclass("android.app.PendingIntent")
                intent=Intent(a,PA)
                intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                                Intent.FLAG_ACTIVITY_SINGLE_TOP)
                if url: intent.putExtra("ps5pro_url",url)
                b.setContentIntent(PendingIntent.getActivity(
                    a,_next_notify_id(),intent,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
            except Exception: pass
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
            # Ab Android 13 kann das Recht fehlen; notify() wirft dann nicht,
            # sondern die Meldung verschwindet. Der Aufrufer zeigt stattdessen
            # einen Toast, wenn hier False zurueckkommt.
            if not nm.areNotificationsEnabled(): return False
            nm.notify(_next_notify_id(),b.build()); return True
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

# ── Edge-to-Edge (Android 15+ / targetSdk 35+) ─────────────────────
def android_insets():
    """(oben, unten, links, rechts) in dp: Statusleiste, Notch und Gestenbereich.

    Ab targetSdk 35 zeichnet Android die App hinter Systemleisten. Kivy kennt
    keine Insets, deshalb werden die Bedienelemente hier um den gemeldeten
    Rand verschoben. Im Querformat sitzt die Navigationsleiste oft seitlich,
    deshalb werden auch linke und rechte Insets beruecksichtigt. Ohne Android
    oder ohne Activity bleibt alles bei 0.
    """
    if platform!="android": return (0.0,0.0,0.0,0.0)
    try:
        from jnius import autoclass
        act=autoclass("org.kivy.android.PythonActivity").mActivity
        ins=act.getWindow().getDecorView().getRootWindowInsets()
        if ins is None: return (0.0,0.0,0.0,0.0)
        d=act.getResources().getDisplayMetrics().density or 1.0
        if autoclass("android.os.Build$VERSION").SDK_INT>=30:
            T=autoclass("android.view.WindowInsets$Type")
            status=ins.getInsets(T.statusBars()); cut=ins.getInsets(T.displayCutout())
            nav=ins.getInsets(T.navigationBars())
            gest=ins.getInsets(T.mandatorySystemGestures())
            top=max(status.top,cut.top)
            # mandatorySystemGestures liegt auch bei ausgeblendeter Leiste an:
            # sonst sitzen die unteren Buttons im Zurueck-Gestenbereich.
            bot=max(nav.bottom,gest.bottom,cut.bottom)
            left=max(nav.left,gest.left,cut.left)
            right=max(nav.right,gest.right,cut.right)
        else:
            top=ins.getSystemWindowInsetTop()
            bot=ins.getSystemWindowInsetBottom()
            left=ins.getSystemWindowInsetLeft()
            right=ins.getSystemWindowInsetRight()
        return (max(0,int(top))/d,max(0,int(bot))/d,
                max(0,int(left))/d,max(0,int(right))/d)
    except Exception: return (0.0,0.0,0.0,0.0)

def android_prepare_window():
    """Helle Systemleisten-Symbole auf dunklem Hintergrund (Android 15+)."""
    if platform!="android": return
    try:
        from jnius import autoclass
        act=autoclass("org.kivy.android.PythonActivity").mActivity
        win=act.getWindow()
        if autoclass("android.os.Build$VERSION").SDK_INT>=30:
            WIC=autoclass("android.view.WindowInsetsController")
            # Maske 0 = keine "light bars" -> weisse Symbole.
            win.getInsetsController().setSystemBarsAppearance(
                0, WIC.APPEARANCE_LIGHT_STATUS_BARS|WIC.APPEARANCE_LIGHT_NAVIGATION_BARS)
    except Exception: pass

# ── Hintergrund-Scan (eigener Prozess) ──────────────────────────────
# Java-Klasse aus der Spec-Zeile services = ps5proscan:...:foreground
BG_SERVICE = "de.ps5pro.ps5prosearchagent.ServicePs5proscan"

def bg_service_start(interval):
    """Foreground-Service starten. Nur Android, sonst ein No-op."""
    if platform!="android": return False
    try:
        from jnius import autoclass
        PA=autoclass("org.kivy.android.PythonActivity")
        Svc=autoclass(BG_SERVICE)
        # data_dir mitgeben: der Service-Prozess hat keine Kivy-App und muss
        # dieselben Settings-/Verlaufsdateien lesen wie die Oberflaeche.
        arg=json.dumps({"interval":int(interval),"data_dir":data_dir()})
        Svc.start(PA.mActivity,"notify_icon","PS5 Pro Scan",
                  "Pr\u00fcft H\u00e4ndler im Hintergrund",arg)
        return True
    except Exception as e:
        print("[BG] Start:",e); return False

def bg_service_stop():
    if platform!="android": return
    try:
        from jnius import autoclass
        PA=autoclass("org.kivy.android.PythonActivity")
        autoclass(BG_SERVICE).stop(PA.mActivity)
    except Exception as e:
        print("[BG] Stop:",e)

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
RADAR_FPS_IDLE = 12.0   # Leerlauf: der Sweep dreht nur 30 Grad/s
RADAR_FPS_SCAN = 30.0   # waehrend eines Scans

def scan_fortschritt(done, total, treffer, sekunden):
    """Kompakte Fortschrittszeile fuer die Kopfleiste (ohne UI-Abhaengigkeit)."""
    if total <= 0:
        return "SCANNE"
    text = f"SCANNE {done}/{total}"
    if treffer:
        text += f" · {treffer} TREFFER"
    if 0 < done < total and sekunden >= 2:
        rest = max(1, int((sekunden / done) * (total - done)))
        text += f" · REST ~{rest}S"
    return text


def radar_flaeche(breite, hoehe, reserve_bottom, reserve_top):
    """Mittelpunkt und Radius der sichtbaren Radar-Scheibe.

    Gibt ``None`` zurueck, wenn der freie Bereich zu klein ist. Die Scheibe
    bleibt zwischen ``reserve_bottom`` und ``reserve_top``, liegt also nicht
    unter der Trefferliste.
    """
    uh = hoehe - reserve_bottom - reserve_top
    if uh < dp(40) or breite < dp(40):
        return None
    mr = min(breite/2.0, uh/2.0) - dp(16)
    if mr < dp(40):
        return None
    return {"cx": breite/2.0, "cy": reserve_bottom + uh/2.0, "mr": mr}


def radar_treffer_radius(mr):
    """Groesste Ausdehnung einer Treffer-Marke (Pulsring) in dp."""
    return min(dp(20), mr*0.11)


def radar_treffer_xy(blip, cx, cy, mr):
    """Position einer Treffer-Marke im Radar, immer innerhalb des Aussenrings.

    Pulsring und Zielmarke eines Treffers brauchen Platz. Ohne Begrenzung
    liegen Treffer am Rand auf dem Aussenring und den Gradzahlen; deshalb wird
    der Abstand auf ``mr - Marke - 2dp`` gekappt. Die Richtung bleibt gleich.
    """
    dx = blip["x"]*mr; dy = blip["y"]*mr
    d = math.hypot(dx, dy)
    grenze = max(0.0, mr - radar_treffer_radius(mr) - dp(2))
    if d > grenze and d > 0:
        k = grenze/d; dx *= k; dy *= k
    return cx + dx, cy + dy


def radar_frame_step(acc, dt, scanning, paused):
    """Reine Entscheidung, ob dieser Tick gezeichnet wird (testbar ohne Kivy).

    Rueckgabe ``(zeichnen, neuer_acc, step)``. ``step`` ist die seit dem letzten
    Bild verstrichene Zeit - Winkel und Symbolbewegung haengen daran, nicht an der
    Bildrate, damit die Optik bei 12 und 30 Bildern/s gleich schnell wirkt.
    Pausiert wird weder gezeichnet noch Zeit angesammelt.
    """
    if paused: return False, acc, 0.0
    acc += dt
    limit = 1.0/(RADAR_FPS_SCAN if scanning else RADAR_FPS_IDLE)
    if acc < limit: return False, acc, 0.0
    return True, 0.0, acc

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

        # HUD unten im sichtbaren Radarbereich: ruhig, aber eindeutig als
        # Systemanzeige lesbar. Die Labels liegen ueber dem Canvas und werden
        # bei jedem Frame mit der freien Radarflaeche synchronisiert.
        self._hud_l=Label(text="",color=RADAR_TICK,font_size=sp(8),
                          bold=True,font_name=SST_FONT,halign="left",valign="middle",
                          size_hint=(None,None),size=(dp(170),dp(12)),opacity=0)
        self._hud_r=Label(text="TARGET · 2 TB",color=RADAR_TXT,font_size=sp(8),
                          bold=True,font_name=SST_FONT,halign="right",valign="middle",
                          size_hint=(None,None),size=(dp(120),dp(12)),opacity=0)
        for _l in (self._hud_l,self._hud_r):
            _l.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            self.add_widget(_l)

        self._stars=[{"x":random.uniform(0.08,0.92),
                      "y":random.uniform(0.08,0.92),
                      "a":random.uniform(0.10,0.34),
                      "p":random.uniform(0,6.28)} for _ in range(18)]
        self._acc=0.0; self._paused=False
        Clock.schedule_interval(self._tick,1/30)

    def pause(self):
        """Im Hintergrund nicht weiterzeichnen - sonst rechnet das Radar im Akku-Betrieb weiter."""
        self._paused=True

    def resume(self):
        self._paused=False; self._acc=0.0; self._redraw()

    def _tick(self,dt):
        zeichnen,self._acc,step=radar_frame_step(self._acc,dt,self.scanning,self._paused)
        if not zeichnen: return True
        s=180.0 if self.scanning else 30.0
        self.angle=(self.angle+s*step)%360
        k=step*30.0
        for f in self._fl:
            f["x"]+=f["vx"]*k; f["y"]+=f["vy"]*k
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
        flaeche=radar_flaeche(self.width,self.height,
                              self.reserve_bottom,self.reserve_top)
        if flaeche is None:
            for _,l in self._bls: l.opacity=0
            self._hud_l.opacity=self._hud_r.opacity=0
            return
        cx=flaeche["cx"]; cy=flaeche["cy"]; mr=flaeche["mr"]
        now=time.time()
        with self.canvas:
            Color(*RADAR_BG); Rectangle(pos=(0,0),size=(self.width,self.height))
            Color(*RADAR_DISH); Ellipse(pos=(cx-mr,cy-mr),size=(mr*2,mr*2))
            # Sehr weicher Aussenring; gibt dem Radar Tiefe, ohne den Sweep
            # oder die Treffer zu ueberstrahlen.
            Color(0.16,0.38,0.62,0.12)
            Ellipse(pos=(cx-mr-dp(10),cy-mr-dp(10)),size=(mr*2+dp(20),mr*2+dp(20)))
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
            # Langsame Sonar-Pings: zwei weiche Ringe laufen nach aussen.
            # Waehrend eines Scans schneller, im Leerlauf kaum merklich.
            cycle=(now*(2.4 if self.scanning else 0.55))%1.0
            for off in (0.0,0.5):
                p=(cycle+off)%1.0
                rr=mr*(0.12+0.86*p)
                Color(0.32,0.65,1.0,0.22*(1.0-p))
                Line(circle=(cx,cy,rr),width=dp(1.1))
            for st in self._stars:
                sx=cx+(st["x"]-0.5)*mr*1.55; sy=cy+(st["y"]-0.5)*mr*1.55
                tw=0.65+0.35*math.sin(now*1.7+st["p"])
                Color(0.55,0.78,1.0,st["a"]*tw)
                Ellipse(pos=(sx-dp(1),sy-dp(1)),size=(dp(2),dp(2)))
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
                # Treffer bleiben innerhalb des Aussenrings: frueher lagen
                # Pulsring und Zielmarke am Rand auf Ring und Gradzahlen.
                bx,by=radar_treffer_xy(b,cx,cy,mr)
                co=STATUS_COLORS.get(b["klass"],C_FG_DIM)
                if b["klass"]=="hit":
                    # Groesse folgt der Scheibe, damit auch ein kleiner Radar
                    # keine Marken zeigt, die groesser als der Ring sind.
                    deco=radar_treffer_radius(mr)
                    pu=0.5+0.5*math.sin(now*4)
                    Color(co[0],co[1],co[2],0.30*pu)
                    Line(circle=(bx,by,deco*(0.6+0.4*pu)),width=dp(1.4))
                    Color(co[0],co[1],co[2],0.18)
                    Ellipse(pos=(bx-deco/2,by-deco/2),size=(deco,deco))
                    # Zielmarke: vier kurze Winkel um den Treffer.
                    d=deco*0.55; arm=deco*0.2
                    for sx,sy in ((1,1),(-1,1),(1,-1),(-1,-1)):
                        Color(co[0],co[1],co[2],0.75)
                        Line(points=[bx+sx*d,by+sy*d,bx+sx*(d-arm),by+sy*d],width=dp(1.1))
                        Line(points=[bx+sx*d,by+sy*d,bx+sx*d,by+sy*(d-arm)],width=dp(1.1))
                    r=deco*0.3
                else: r=min(dp(4),mr*0.022)
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
            # Reticle um das Zentrum: klar, technisch, nicht verspielt.
            for sx,sy in ((1,1),(-1,1),(1,-1),(-1,-1)):
                Color(0.62,0.82,1.0,0.55)
                Line(points=[cx+sx*dp(16),cy+sx*0+sy*dp(16),
                             cx+sx*dp(9),cy+sy*dp(9)],width=dp(1.0))
        for deg,l in self._bls:
            a=math.radians(90-deg)
            lx=cx+(mr+dp(11))*math.cos(a)-l.width/2
            ly=cy+(mr+dp(11))*math.sin(a)-l.height/2
            # Gradzahlen bleiben im Radar: sonst werden "90" und "270" am
            # Fensterrand abgeschnitten oder liegen auf der Trefferliste.
            lx=max(dp(1),min(lx,self.width-l.width-dp(1)))
            lo=self.reserve_bottom+dp(1)
            hi=self.height-self.reserve_top-l.height-dp(1)
            if hi>=lo: ly=max(lo,min(ly,hi))
            l.pos=(lx,ly); l.opacity=1
        self._hud_l.text=(f"SCANNING · {len(self.blips)}/{len(HAENDLER)}"
                          if self.scanning else f"{len(HAENDLER)} HÄNDLER · DE + AT")
        self._hud_l.pos=(self.x+dp(14), self.reserve_bottom+dp(8))
        self._hud_r.pos=(self.right-dp(14)-self._hud_r.width,
                         self.reserve_bottom+dp(8))
        self._hud_l.opacity=1; self._hud_r.opacity=1
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
        self.sub=Label(text="S E A R C H   A G E N T   ·   2 T B",color=PS1_GREY,
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
        Clock.schedule_interval(self._anim,1/10)

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
        # Der volle Schriftzug braucht auf schmalen Geraeten mehr Platz als der
        # Textkasten bietet. Dann bleibt "PS5 PRO" als kurze, vollstaendig
        # lesbare Marke stehen, statt den Schriftzug mit "..." abzuschneiden.
        compact = tw < dp(460)
        title_text = "[b]PS5 PRO[/b]" if compact else \
            "[b]PLAYSTATION[/b] [color=3f8cff][b]5 PRO[/b][/color]"
        sub_text = "SEARCH AGENT  ·  2 TB" if compact else \
            "S E A R C H   A G E N T   ·   2 T B"
        if self.title.text != title_text: self.title.text = title_text
        if self.sub.text != sub_text: self.sub.text = sub_text
        fs=max(sp(12),min(sp(19),tw*0.062))
        self.title.font_size=fs
        self.sub.font_size=max(sp(7),min(sp(10),fs*0.50))

    def _anim(self,dt):
        self._t+=dt
        a=0.35+0.55*(0.5+0.5*math.sin(self._t*2.0))
        self._c_led.rgba=(PS1_BLUE[0],PS1_BLUE[1],PS1_BLUE[2],a)

# ══════════ RESULT ROW (PS1 style, compact) ══════════

def tief_30(serie):
    """Niedrigster Preis der letzten 30 Tage aus [[iso_ts, preis], ...]."""
    if not serie: return None
    grenze=time.time()-30*86400; werte=[]
    for punkt in serie:
        try:
            ts=datetime.fromisoformat(str(punkt[0])).timestamp(); p=float(punkt[1])
        except (TypeError,ValueError): continue
        if ts>=grenze: werte.append(p)
    if werte: return min(werte)
    try: return min(float(p[1]) for p in serie)
    except (TypeError,ValueError,IndexError): return None

class Sparkline(Widget):
    """Kleine Preiskurve ohne zusaetzliche Abhaengigkeit."""
    def __init__(self,serie,color=(1,1,1,1),**kw):
        super().__init__(**kw)
        self.serie=serie or []; self.farbe=color
        self.bind(pos=self._draw,size=self._draw)
        Clock.schedule_once(self._draw,0)
    def _draw(self,*_):
        self.canvas.clear()
        werte=[]
        for p in self.serie:
            try: werte.append(float(p[1]))
            except (TypeError,ValueError,IndexError): continue
        if len(werte)<2 or self.width<=0 or self.height<=0: return
        mn,mx=min(werte),max(werte); span=max(0.01,mx-mn)
        schritt=self.width/(len(werte)-1)
        pts=[]
        for i,w in enumerate(werte):
            pts += [self.x+i*schritt,
                    self.y+dp(1)+(w-mn)/span*max(dp(1),self.height-dp(2))]
        with self.canvas:
            Color(self.farbe[0],self.farbe[1],self.farbe[2],0.85)
            Line(points=pts,width=dp(1.2))

class ResultCard(ButtonBehavior, BoxLayout):
    def __init__(self,result,is_new,prev,serie=None,detail_cb=None,best=False,
                 font_scale=1.0,**kw):
        super().__init__(**kw)
        self.result=result
        self._is_new=is_new; self._prev=prev; self._best=best
        try: self._font_scale=max(0.9,min(1.2,float(font_scale)))
        except (TypeError,ValueError): self._font_scale=1.0
        self._serie=serie or []
        self._down=None; self._moved=False
        self._detail_cb=detail_cb; self._long_event=None; self._long_done=False
        challenge=result.get("klass")=="challenge"
        self.orientation="vertical" if challenge else "horizontal"
        self.size_hint=(1,None)
        self.height=dp(80)*self._font_scale if challenge else dp(56)*self._font_scale
        self.padding=(dp(9),dp(6))
        self.spacing=dp(2 if challenge else 7)
        self._build()
        self.bind(pos=self._redraw,size=self._redraw,state=self._redraw)
        if is_new or result.get("_restock"):
            self.opacity=0
            Animation(opacity=1,d=0.28).start(self)
        Clock.schedule_once(self._redraw,0)

    def _redraw(self,*_):
        self.canvas.before.clear()
        if self.width<=0 or self.height<=0: return
        r=self.result
        co=CARD_STATUS.get(r["klass"],PS1_GREY)
        pressed=(getattr(self,"state","normal")=="down")
        top=PS1_CARD_HI
        with self.canvas.before:
            # Drop shadow plus a two-step metal gradient instead of a flat
            # rectangle. The contrast stays subtle, so the price remains king.
            Color(0,0,0,0.55)
            Rectangle(pos=(self.x-dp(1),self.y-dp(1)),
                      size=(self.width+dp(2),self.height+dp(2)))
            Color(*top); Rectangle(pos=(self.x,self.y+self.height*0.46),
                                   size=(self.width,self.height*0.54))
            Color(*PS1_CARD); Rectangle(pos=(self.x,self.y),
                                        size=(self.width,self.height*0.46))
            # 90s bevel
            Color(1,1,1,0.18 if self._best else 0.12)
            Line(points=[self.x,self.top-dp(1),self.right,self.top-dp(1)],width=dp(1))
            Color(0,0,0,0.55)
            Line(points=[self.x,self.y+dp(1),self.right,self.y+dp(1)],width=dp(1))
            # status edge
            Color(*co); Rectangle(pos=(self.x,self.y),size=(dp(3),self.height))
            if self._best:
                Color(*PS1_CYAN); Rectangle(pos=(self.x+dp(3),self.top-dp(2)),
                                             size=(self.width-dp(3),dp(2)))
            elif r.get("_restock"):
                Color(*PS1_CYAN); Rectangle(pos=(self.x+dp(3),self.top-dp(2)),
                                             size=(self.width-dp(3),dp(1)))
            if r["klass"]=="hit":
                Color(co[0],co[1],co[2],0.55)
                Line(rectangle=(self.x,self.y,self.width,self.height),width=dp(1))
            else:
                Color(1,1,1,0.10)
                Line(rectangle=(self.x,self.y,self.width,self.height),width=dp(1))

    def _build(self):
        r=self.result
        co=CARD_STATUS.get(r["klass"],PS1_GREY)
        s=self._font_scale
        fs=lambda base: sp(base*s)

        # Kompakte Zeile: Haendler/Meta/Status links, Preis rechts. Die alte
        # 156-dp-Karte zeigte auf dem Telefon nur einen Treffer pro Wisch.
        # Nur BOT-SCHUTZ braucht einen eigenen Container fuer die zweite Zeile.
        challenge=r["klass"]=="challenge"
        holder=BoxLayout(orientation="horizontal",spacing=dp(7)) if challenge else self

        info=BoxLayout(orientation="vertical",spacing=dp(0))
        name_str=re.sub(r"\s+(DE|AT)$","",r["haendler"]).strip()
        n=Label(text=f"[b]{name_str}[/b]",markup=True,color=PS1_TEXT,
                font_size=fs(12.5),font_name=SST_FONT,
                halign="left",valign="middle",
                size_hint_y=None,height=dp(17)*s,
                shorten=True,shorten_from="right")
        n.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        info.add_widget(n)

        meta_txt=f"{r['land']} · {r['zeit']}"
        if r.get("_restock"): meta_txt="WIEDER DA · "+meta_txt
        elif self._is_new: meta_txt="NEU · "+meta_txt
        elif ist_gebraucht(r.get("condition")): meta_txt="GEBRAUCHT · "+meta_txt
        elif r.get("sofort") is False: meta_txt="VORBEST. · "+meta_txt
        meta_row=BoxLayout(orientation="horizontal",size_hint_y=None,
                           height=dp(12)*s,spacing=dp(3))
        meta_row.add_widget(FlagWidget(r["land"],size=(dp(18)*s,dp(12)*s)))
        m=Label(text=meta_txt,color=PS1_GREY,font_size=fs(8.5),font_name=SST_FONT,
                halign="left",valign="middle",
                size_hint_y=None,height=dp(12)*s,
                shorten=True,shorten_from="right")
        m.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        meta_row.add_widget(m)
        info.add_widget(meta_row)

        # Status gehoert in die linke, breite Spalte. Rechts teilen sich
        # Preis und Delta/BEST den Platz; so bleibt "NICHT VERFÜGBAR" auch
        # auf 320 dp und bei 120 % Schrift vollständig lesbar.
        st_map={"hit":"VERFÜGBAR","expensive":"ZU TEUER","unknown":"PREIS OFFEN",
                "unavail":"NICHT VERFÜGBAR","error":"FEHLER","challenge":"BOT-SCHUTZ",
                "parser":"PARSER-FEHLER"}
        st=st_map.get(r["klass"],"?")
        st_lbl=Label(text=f"[b]{st}[/b]",markup=True,color=co,
                     font_size=fs(8.5),font_name=SST_FONT,
                     halign="left",valign="middle",
                     size_hint_y=None,height=dp(14)*s,
                     shorten=True,shorten_from="right")
        st_lbl.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        info.add_widget(st_lbl)

        holder.add_widget(info)

        right=BoxLayout(orientation="vertical",size_hint_x=None,
                        width=dp(134)*s,spacing=dp(0))
        if r["preis"] is not None:
            p_txt=format_preis(r["preis"]); p_col=PS1_ICE if self._best else PS1_TEXT
        else:
            p_txt="—"; p_col=PS1_GREY
        p=Label(text=f"[b]{p_txt}[/b]",markup=True,color=p_col,
                font_size=fs(16.5),font_name=SST_FONT,
                halign="right",valign="middle",
                size_hint_y=None,height=dp(28)*s)
        p.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        right.add_widget(p)

        srow=BoxLayout(orientation="horizontal",size_hint_y=None,
                       height=dp(14)*s,spacing=dp(2))
        if self._best:
            b=Label(text="BEST",color=PS1_CYAN,font_size=fs(7.5),bold=True,
                    font_name=SST_FONT,halign="right",valign="middle",
                    size_hint_x=None,width=dp(30)*s)
            b.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            srow.add_widget(b)

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
            d=Label(text=d_txt,color=d_col,font_size=fs(8),bold=True,
                    font_name=SST_FONT,halign="right",valign="middle",
                    size_hint_x=None,width=dp(44)*s)
            d.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            srow.add_widget(d)
        # Eine leere Zeile wuerde die Preisspalte unnoetig aufblaehen.
        if len(srow.children): right.add_widget(srow)
        holder.add_widget(right)

        # BOT-SCHUTZ ist kein Fehler der App: Der Shop verlangt eine
        # Challenge. Die App umgeht sie bewusst nicht. Der Hinweis bekommt
        # eine eigene Zeile, damit er auch auf schmalen Displays nicht
        # abgeschnitten wird und die Preisspalte unberuehrt bleibt.
        if challenge:
            self.add_widget(holder)
            hint=Label(text="BOT-SCHUTZ · APP UMGEHT SIE NICHT",
                       color=PS1_YELLOW,font_size=fs(10.0),font_name=SST_FONT,
                       halign="left",valign="middle",
                       shorten=True,shorten_from="right",
                       size_hint_y=None,height=dp(18)*s)
            hint.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            self.add_widget(hint)

    def on_touch_down(self,touch):
        if self.collide_point(*touch.pos):
            self._down=touch.pos; self._moved=False
            self._long_done=False
            if self._long_event is not None: Clock.unschedule(self._long_event)
            self._long_event=Clock.schedule_once(self._fire_long,0.55)
        return super().on_touch_down(touch)
    def _fire_long(self,dt):
        self._long_event=None
        if self._moved or not self._down: return
        self._long_done=True
        haptic(0.03)
        if self._detail_cb:
            try: self._detail_cb(self.result,self._serie)
            except Exception: pass
    def on_touch_move(self,touch):
        if self._down and (abs(touch.x-self._down[0])+abs(touch.y-self._down[1]))>dp(14):
            self._moved=True
            if self._long_event is not None:
                Clock.unschedule(self._long_event); self._long_event=None
        return super().on_touch_move(touch)
    def on_release(self):
        if self._long_event is not None:
            Clock.unschedule(self._long_event); self._long_event=None
        if self._moved or self._long_done: return
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


def layout_geometrie(w,h,top_in=0.0,bottom_in=0.0,left_in=0.0,right_in=0.0):
    """Berechnet die responsive Aufteilung ohne Kivy-Abhaengigkeit.

    Hochformat: Radar oben, Trefferleiste unten, Bedienung ganz unten.
    Querformat auf Tablet/Foldable: Treffer werden zu einer vertikalen Liste
    am rechten Rand, das Radar bleibt links. Die Funktion ist absichtlich
    klein und testbar; sie zeichnet nichts.
    """
    w=max(dp(1),float(w)); h=max(dp(1),float(h))
    left=max(0.0,float(left_in)); right=max(0.0,float(right_in))
    top=max(0.0,float(top_in)); bottom=max(0.0,float(bottom_in))
    usable_w=max(dp(1),w-left-right)

    if h<dp(500): lh,rh,ch=dp(56),dp(160),dp(42)
    elif h<dp(700): lh,rh,ch=dp(64),dp(178),dp(46)
    else: lh,rh,ch=dp(72),dp(190),dp(50)

    # Auch im Hochformat darf die Trefferleiste bei sehr kleinen Displays
    # nicht unter das Logo oder aus dem Fenster wachsen.
    verfuegbar=max(dp(120),h-top-lh-bottom-ch)
    rh=min(rh,verfuegbar)
    panel_w=usable_w; panel_x=left; panel_y=bottom+ch
    results_h=rh; logo_w=usable_w; wide=False

    # Ab 600 dp Breite ist genug Platz fuer zwei Spalten. Die Hoehe muss
    # ebenfalls reichen, damit ein Landscape-Handy nicht zur engen Liste wird.
    if (usable_w>=dp(600) and h>=dp(480) and usable_w>h*1.15):
        kandidat=min(dp(460),max(dp(320),usable_w*0.42))
        kandidat_x=w-right-kandidat
        kandidat_logo=kandidat_x-left
        kandidat_h=h-top-lh-bottom-ch
        if kandidat_logo>=dp(260) and kandidat_h>=dp(240):
            wide=True; panel_w=kandidat; panel_x=kandidat_x
            results_h=kandidat_h; logo_w=kandidat_logo

    # Der Puffer haelt Gradzahlen und Aussenring frei von der Trefferliste:
    # im Hochformat unter dem Radar, im Querformat zwischen Radar und der
    # Liste am rechten Rand. Ohne den Puffer lag der Rand der Scheibe auf der
    # Panelkante und die Trefferleiste schnitt den Radar an.
    radar_bottom=ch+bottom if wide else ch+results_h+bottom+RADAR_PANEL_GAP
    radar_w=max(dp(200),panel_x-RADAR_PANEL_GAP) if wide else w
    return {
        "wide":wide,"logo_h":lh,"logo_w":logo_w,"controls_h":ch,
        "results_h":results_h,"panel_w":panel_w,"panel_x":panel_x,
        "panel_y":panel_y,"usable_w":usable_w,
        "radar_w":radar_w,
        "radar_bottom":radar_bottom,
        "radar_top":lh+top,
    }


# ══════════ MAIN UI ══════════
class MainUI(FloatLayout):
    def __init__(self,**kw):
        super().__init__(**kw)
        self.scanning=False; self.scanned={}; self.settings=Settings()
        try: lade_shop_config()
        except Exception: pass
        saved=self.settings.get("active_haendler")
        if saved:
            self.active_haendler=set(saved)&{h["name"] for h in HAENDLER}
            if not self.active_haendler: self.active_haendler={h["name"] for h in HAENDLER}
        else:
            self.active_haendler={h["name"] for h in HAENDLER}
        self.filter_mode=self.settings.get("filter","verfuegbar")
        if self.filter_mode not in ("verfuegbar","alle"): self.filter_mode="verfuegbar"
        self.sort_mode=self.settings.get("sort","Preis")
        if self.sort_mode not in SORT_OPTIONS: self.sort_mode="Preis"
        mp=self.settings.get("max_preis",MAX_PREIS)
        try:
            self.max_preis=(None if mp is None else float(mp))
            if self.max_preis is not None and not (400<=self.max_preis<=1500):
                self.max_preis=MAX_PREIS
        except (TypeError,ValueError): self.max_preis=MAX_PREIS
        self.auto_scan=bool(self.settings.get("auto_scan",False))
        ai=self.settings.get("auto_interval",600)
        self.auto_interval=ai if ai in [x[0] for x in AUTO_INTERVALS] else 600
        self.next_scan_at=0.0; self._auto_event=None
        self.notify_enabled=bool(self.settings.get("notify",True))
        self.notify_low_only=bool(self.settings.get("notify_low_only",False))
        self.notify_sofort=bool(self.settings.get("notify_sofort",True))
        self.quiet_hours=bool(self.settings.get("quiet_hours",False))
        try: self.font_scale=float(self.settings.get("font_scale",1.0))
        except (TypeError,ValueError): self.font_scale=1.0
        if self.font_scale not in FONT_SCALES: self.font_scale=1.0
        self._known_hits=set(); self.queue=queue.Queue()
        self._bg_seen_ts=0.0; self._insets=(0.0,0.0,0.0,0.0)
        self._wide=False; self._results_mode_set=False
        self._scan_token=0; self._scan_cancel_event=None
        self.history=History(); self._scan_t0=0.0; self._scan_done=0
        self._scan_total=0; self._rerender_event=None; self._drain_event=None
        self._resize_event=None; self._placeholder=None; self._last_sig=None
        self._bg_warn_until=0.0
        self._bg_text=None; self._bg_text_at=0.0
        self._build_ui()
        try:
            threading.Thread(target=self._shop_config_bg,daemon=True).start()
        except Exception: pass
        Window.bind(size=self._on_window_size)
        Clock.schedule_once(lambda dt:self._apply_sizes(),0)
        Clock.schedule_once(lambda dt:self._apply_sizes(),0.2)
        # Insets erst nach dem ersten Frame: vorher gibt es keine RootWindowInsets.
        Clock.schedule_once(lambda dt:self._refresh_insets(),0.5)
        Clock.schedule_once(lambda dt:self._refresh_insets(),1.5)
        if not self.settings.get("onboarded",False):
            Clock.schedule_once(self._show_onboarding,1.0)
        if self.auto_scan: Clock.schedule_once(lambda dt:self._auto_start(),1.5)

    # ── Aufbau ──────────────────────────────────────────────────────
    def _build_ui(self):
        # Radar fullscreen
        self.radar=RadarWidget(size_hint=(1,1),pos_hint={"x":0,"y":0})
        self.add_widget(self.radar)

        # Radar-HUD: liegt bewusst ausserhalb des Radar-Canvas, damit es auf
        # jeder Displayhoehe lesbar bleibt und nicht hinter der Trefferleiste
        # verschwindet.
        self.radar_hud=BoxLayout(orientation="horizontal",size_hint=(None,None),
                                 height=dp(17),padding=(dp(5),0),spacing=dp(4))
        with self.radar_hud.canvas.before:
            Color(0.025,0.045,0.075,0.82); self._rhud_bg=Rectangle(pos=(0,0),size=(1,1))
            Color(RADAR_RING[0],RADAR_RING[1],RADAR_RING[2],0.55)
            self._rhud_line=Rectangle(pos=(0,0),size=(1,1))
        self.radar_hud.bind(pos=self._sync_radar_hud,size=self._sync_radar_hud)
        self.radar_hud_left=Label(text="",color=RADAR_TICK,font_size=sp(7.8),
                                  bold=True,font_name=SST_FONT,halign="left",
                                  valign="middle",shorten=True,shorten_from="right")
        self.radar_hud_right=Label(text="TARGET · 2 TB",color=RADAR_TXT,
                                   font_size=sp(7.8),bold=True,font_name=SST_FONT,
                                   halign="right",valign="middle",
                                   size_hint_x=None,width=dp(92))
        for _l in (self.radar_hud_left,self.radar_hud_right):
            _l.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        self.radar_hud.add_widget(self.radar_hud_left)
        self.radar_hud.add_widget(self.radar_hud_right)
        self.add_widget(self.radar_hud)

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
                                  halign="left",valign="middle",
                                  shorten=True,shorten_from="right")
        self.results_status.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        self.results_header.add_widget(self.results_status)

        self.results_count=Label(text="0/0",color=PS1_GREY,font_size=sp(9),
                                 bold=True,font_name=SST_FONT,
                                 halign="right",valign="middle",
                                 size_hint=(None,1),width=dp(52))
        self.results_count.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        self.results_header.add_widget(self.results_count)

        self.results_panel.add_widget(self.results_header)

        # Vertikale Trefferliste
        self.results_scroll=ScrollView(do_scroll_x=False,do_scroll_y=True,
                                       scroll_type=["bars","content"],
                                       bar_width=dp(3),bar_color=PS1_SILVER,
                                       bar_inactive_color=(0.28,0.29,0.33,0.55),
                                       bar_margin=dp(1))
        self.results_row=BoxLayout(orientation="vertical",
                                   size_hint=(1,None),
                                   spacing=dp(4),padding=(dp(8),dp(5)))
        self.results_row.bind(minimum_height=self._sync_row_height)
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

        self.rules_chip=Chip(text="REGELN",accent=PS1_PINK,width=dp(64))
        self.rules_chip.bind(on_release=lambda *_:self._open_alarm_rules())
        chips.add_widget(self.rules_chip)

        self.health_chip=Chip(text="SHOPS",accent=PS1_BLUE,width=dp(58))
        self.health_chip.bind(on_release=lambda *_:self._open_health())
        chips.add_widget(self.health_chip)

        self.max_preis_chip=Chip(text=self._max_text(),accent=PS1_RED,width=dp(80))
        self.max_preis_chip.bind(on_release=lambda *_:self._cycle_max_preis())
        chips.add_widget(self.max_preis_chip)

        self.sort_chip=Chip(text=self._sort_text(),accent=PS1_BLUE,width=dp(104))
        self.sort_chip.bind(on_release=lambda *_:self._cycle_sort())
        chips.add_widget(self.sort_chip)

        self.chip_scroll.add_widget(chips)
        self.controls.add_widget(self.chip_scroll)

        self.setup_btn=PS1Button(text="SETUP",accent=PS1_CYAN,
                                  size_hint=(None,1),width=dp(62),
                                  font_size=sp(9))
        self.setup_btn.bind(on_release=lambda *_:self._open_setup())
        self.controls.add_widget(self.setup_btn)
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
    def _sync_radar_hud(self,*_):
        if not hasattr(self,"_rhud_bg"): return
        self._rhud_bg.pos=self.radar_hud.pos
        self._rhud_bg.size=self.radar_hud.size
        self._rhud_line.pos=(self.radar_hud.x,self.radar_hud.y)
        self._rhud_line.size=(self.radar_hud.width,dp(1))
    def _update_radar_hud(self):
        if not hasattr(self,"radar_hud_left"): return
        if self.scanning:
            self.radar_hud_left.text=(f"SCANNING · {self._scan_done}/{self._scan_total}"
                                      if self._scan_total else "SCANNING")
            self.radar_hud_left.color=PS1_CYAN
        else:
            self.radar_hud_left.text=f"{len(HAENDLER)} HÄNDLER · DE + AT"
            self.radar_hud_left.color=RADAR_TICK

    def _on_window_size(self,*_):
        if self._resize_event is not None: Clock.unschedule(self._resize_event)
        self._resize_event=Clock.schedule_once(lambda dt:self._apply_sizes(),0.05)
    def _refresh_insets(self):
        try:
            self._insets=android_insets(); self._apply_sizes()
        except Exception as e: print(f"[Insets] {e}")
    def _sync_row_height(self,row,value):
        row.height=max(dp(1),value)
    def _set_results_mode(self,wide):
        """Immer eine kompakte vertikale Liste; wide nutzt nur mehr Breite."""
        wide=bool(wide)
        if self._results_mode_set and wide==self._wide: return
        self._wide=wide; self._results_mode_set=True
        self.results_scroll.do_scroll_x=False
        self.results_scroll.do_scroll_y=True
        self.results_scroll.scroll_x=0; self.results_scroll.scroll_y=1
        self.results_row.orientation="vertical"
        self.results_row.size_hint=(1,None)
        self.results_row.width=max(dp(1),self.results_panel.width)
        self._clear_results(); self._last_sig=None
        if self.scanning:
            self._show_placeholder("SCANNE...","TIPPE STOP ZUM ABBRECHEN")
        elif self.scanned:
            self._rerender()
        else:
            mp_txt="offen" if self.max_preis is None else f"{int(self.max_preis)} €"
            self._show_placeholder("SYSTEM BEREIT",f"PS5 PRO 2 TB · PREIS MAX {mp_txt}")
    def _apply_sizes(self):
        try:
            w,h=Window.width,Window.height
            if w<=0 or h<=0:
                Clock.schedule_once(lambda dt:self._apply_sizes(),0.15); return
            # android_insets() liefert dp; Fensterkoordinaten sind Pixel.
            top_in,bot_in,left_in,right_in=(dp(x) for x in self._insets)
            g=layout_geometrie(w,h,top_in,bot_in,left_in,right_in)
            self.logo.height=g["logo_h"]
            # pos_hint statt pos: FloatLayout haelt den Titel so auch bei
            # Drehung/Resize unterhalb der Statusleiste bzw. des Notch.
            self.logo.size_hint_x=None; self.logo.width=g["logo_w"]
            self.logo.pos_hint={"x":(left_in/w if w else 0),
                                "top":1.0-(top_in/h if h else 0)}
            self.controls.pos=(left_in,bot_in)
            self.controls.size=(g["usable_w"],g["controls_h"])
            self.results_panel.pos=(g["panel_x"],g["panel_y"])
            self.results_panel.size=(g["panel_w"],g["results_h"])
            if g["wide"]:
                self.radar_hud.pos=(left_in+dp(8),g["panel_y"]+dp(2))
                self.radar_hud.size=(max(dp(80),g["panel_x"]-dp(16)),dp(17))
            else:
                self.radar_hud.pos=(left_in+dp(8),g["panel_y"]+g["results_h"])
                self.radar_hud.size=(max(dp(80),g["usable_w"]-dp(16)),dp(17))
            self._update_radar_hud()
            if g["wide"]:
                self.radar.size_hint=(None,None)
                self.radar.pos=(0,0); self.radar.size=(max(dp(1),g["radar_w"]),h)
            else:
                self.radar.size_hint=(1,1); self.radar.size=(w,h)
            self.radar.reserve_bottom=g["radar_bottom"]
            self.radar.reserve_top=g["radar_top"]
            self._set_results_mode(g["wide"])
            self.results_row.width=max(dp(1),g["panel_w"])
        except Exception as e: print(f"[Sizes] {e}")

    # ── Bedienung ───────────────────────────────────────────────────
    def _set_filter(self,m):
        self.filter_mode=m
        self.chip_verf.state=("down" if m=="verfuegbar" else "normal")
        self.chip_all.state=("down" if m=="alle" else "normal")
        self.settings.set("filter",m); self._rerender()
    def _cycle_sort(self):
        try: i=SORT_OPTIONS.index(self.sort_mode)
        except ValueError: i=-1
        self.sort_mode=SORT_OPTIONS[(i+1)%len(SORT_OPTIONS)]
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
            if r["klass"] in ("error","challenge","unavail","parser"): continue
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
        if self.auto_scan:
            self._auto_start(); haptic(0.04)
            self._toast("AUTO AN \u00b7 AUCH IM HINTERGRUND",color=PS1_YELLOW)
        else:
            self._auto_stop()
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
            txt=f"NÄCHSTER SCAN IN {int(rem//60):02d}:{int(rem%60):02d}"
            bg=self._bg_last_text()
            self.results_status.text=txt+(f" · BG {bg}" if bg else "")
        return True
    def _cycle_font_scale(self):
        try: i=FONT_SCALES.index(self.font_scale)
        except ValueError: i=0
        self.font_scale=FONT_SCALES[(i+1)%len(FONT_SCALES)]
        self.settings.set("font_scale",self.font_scale)
        self._clear_results(); self._last_sig=None; self._rerender()

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
    def _maybe_notify(self,r):
        if not self.notify_enabled: return
        if not (r.get("_is_new") or r.get("_restock")): return
        name=r.get("haendler","?"); preis=r.get("preis")
        if preis is None: return
        # Dieselbe Regel wie im Hintergrund: keine Vorbestellung, keine
        # Gebrauchtware, keine stummgeschalteten Shops, ggf. Ruhezeit.
        if not alarm_erlaubt(r,self.history.get_tief(name),self.settings): return
        key=(name,round(preis,2),bool(r.get("_restock")))
        if key in self._known_hits: return
        self._known_hits.add(key)
        if len(self._known_hits)>200:
            self._known_hits=set(list(self._known_hits)[-100:])
        msg=f"{name}: {format_preis(preis)}"
        title=("PS5 PRO 2TB WIEDER VERFÜGBAR" if r.get("_restock")
               else "PS5 PRO 2TB VERFÜGBAR")
        # notify() kann auf Android Systemzeit kosten; das darf den Radar nicht
        # mitten im Treffer einfrieren. Der Fallback-Toast laeuft im UI-Thread.
        def send():
            try: ok=notify(title,msg,url=r.get("url"))
            except Exception: ok=False
            if not ok:
                try:
                    Clock.schedule_once(
                        lambda dt:self._toast(msg,color=CARD_STATUS["hit"]),0)
                except Exception: pass
        threading.Thread(target=send,daemon=True).start()

    def _send_test_alarm(self):
        try:
            ok=notify("PS5 PRO TESTALARM","Benachrichtigungen funktionieren.",
                      url="https://direct.playstation.com/de-de/buy-consoles/playstation5-pro-console-2-tb")
        except Exception: ok=False
        self._toast("TESTALARM GESENDET" if ok else "TESTALARM FEHLGESCHLAGEN",
                    color=CARD_STATUS["hit"] if ok else PS1_YELLOW)

    def _show_onboarding(self,*_):
        """Einmalige kurze Erklaerung der drei wichtigsten Gesten."""
        self.settings.set("onboarded",True)
        box=BoxLayout(orientation="vertical",spacing=dp(6),padding=dp(14))
        head=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(9))
        head.add_widget(PSMark(size_hint=(None,None),size=(dp(30),dp(30))))
        ht=BoxLayout(orientation="vertical",spacing=0)
        ht.add_widget(Label(text="[b]SYSTEM BEREIT[/b]",markup=True,color=PS1_ICE,
                            font_size=sp(17),font_name=SST_FONT,
                            size_hint_y=None,height=dp(22)))
        ht.add_widget(Label(text="PS5 PRO 2 TB  ·  LIMITED SEARCH AGENT",color=PS1_CYAN,
                            font_size=sp(7.8),bold=True,font_name=SST_FONT,
                            size_hint_y=None,height=dp(13)))
        head.add_widget(ht); box.add_widget(head)
        box.add_widget(PSShapesWidget(size=(dp(100),dp(18))))
        text=("[b]SCAN[/b]  fragt alle Shops gleichzeitig ab.\n"
              "[b]LANGES TIPPEN[/b]  zeigt Preisverlauf, Zustand und Verkäufer.\n"
              "[b]SHOPS[/b]  zeigt, welcher Händler gerade nicht erreichbar ist.\n"
              "[b]REGELN[/b]  steuert Tiefstpreis, Ruhezeit und Stummschaltung.")
        m=Label(text=text,markup=True,color=PS1_GREY,font_size=sp(9.5),
                font_name=SST_FONT,halign="left",valign="top")
        m.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); box.add_widget(m)
        row=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(6))
        # Drei Buttons nebeneinander: Auf sehr schmalen Displays braucht
        # "ALARM EINRICHTEN" eine kleinere Schrift, sonst wird das Label
        # abgeschnitten. Ab 360 dp bleibt die groessere Schrift erhalten.
        btn_fs=sp(8.2) if Window.width < dp(360) else sp(9.5)
        start=PS1Button(text="SCAN STARTEN",accent=PS1_GREEN,font_size=btn_fs)
        rules=PS1Button(text="ALARM EINRICHTEN",accent=PS1_PINK,font_size=btn_fs)
        later=PS1Button(text="SPÄTER",accent=PS1_SILVER,font_size=btn_fs)
        # Auch im kurzen Querformat darf der Dialog nicht ueber den Bildschirm
        # hinauswachsen. Der Inhalt wird dann scrollbar statt unten zu fehlen.
        box.size_hint=(1,None)
        box.bind(minimum_height=box.setter("height"))
        sv=ScrollView(bar_width=dp(4),do_scroll_x=False)
        sv.add_widget(box)
        p=Popup(title="",content=sv,size_hint=(None,None),
                width=min(dp(520),Window.width*0.93),
                height=min(dp(330),Window.height*0.9),
                background_color=(0.045,0.05,0.062,0.99),separator_height=0)
        def go(start_scan=False,open_rules=False):
            p.dismiss()
            if start_scan and not self.scanning: self._scan_start()
            if open_rules: self._open_alarm_rules()
        start.bind(on_release=lambda *_:go(True,False))
        rules.bind(on_release=lambda *_:go(False,True))
        later.bind(on_release=lambda *_:go())
        row.add_widget(start); row.add_widget(rules); row.add_widget(later)
        box.add_widget(row); p.open()

    def _open_setup(self):
        """Zentrale Systemkonfiguration - die ruhige Schaltzentrale."""
        haptic(0.02)
        box=BoxLayout(orientation="vertical",spacing=dp(6),padding=dp(10))
        head=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(8))
        mark=PSMark(size_hint=(None,None),size=(dp(30),dp(30)))
        head.add_widget(mark)
        titles=BoxLayout(orientation="vertical",spacing=0)
        t=Label(text="[b]SYSTEM CONFIG[/b]",markup=True,color=PS1_ICE,
                font_size=sp(15),font_name=SST_FONT,halign="left",valign="middle",
                size_hint_y=None,height=dp(22))
        sub=Label(text="PS5 PRO 2 TB · FINAL EDITION",color=PS1_CYAN,
                  font_size=sp(8),bold=True,font_name=SST_FONT,
                  halign="left",valign="middle",size_hint_y=None,height=dp(14))
        for x in (t,sub): x.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        titles.add_widget(t); titles.add_widget(sub); head.add_widget(titles)
        box.add_widget(head)

        summ=Label(text=(f"{len(self.active_haendler)}/{len(HAENDLER)} HÄNDLER AKTIV   ·   "
                          f"{self._max_text()}   ·   {self._sort_text()}"),
                   color=PS1_GREY,font_size=sp(8.5),font_name=SST_FONT,
                   halign="left",valign="middle",shorten=True,shorten_from="right",
                   size_hint_y=None,height=dp(16))
        summ.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); box.add_widget(summ)

        def section(title):
            l=Label(text=title,color=PS1_CYAN,font_size=sp(8.5),bold=True,
                    font_name=SST_FONT,halign="left",valign="middle",
                    size_hint_y=None,height=dp(18))
            l.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            box.add_widget(l)

        def action(label,value,cb,accent):
            b=PS1Button(text="",accent=accent,font_size=sp(9.5),
                        size_hint_y=None,height=dp(34))
            def sync():
                try: b.text=f"{label}   ·   {value()}"
                except Exception: b.text=label
            def go(*_):
                try: cb()
                except Exception as e: print("[Setup]",e)
                sync()
            b.bind(on_release=go); sync(); box.add_widget(b)
            return b

        ref={"p":None}
        section("SCAN")
        action("AUTO-SCAN",lambda: "AN" if self.auto_scan else "AUS",
               self._toggle_auto,PS1_GREEN)
        action("INTERVALL",self._interval_text,self._cycle_interval,PS1_PINK)
        action("ALARM",lambda: "AN" if self.notify_enabled else "AUS",
               self._toggle_notify,PS1_PINK)

        section("TREFFER")
        action("MAX-PREIS",lambda: ("OFFEN" if self.max_preis is None
                                     else f"{int(self.max_preis)} €"),
               self._cycle_max_preis,PS1_RED)
        action("SORTIERUNG",lambda: self.sort_mode.upper(),self._cycle_sort,PS1_BLUE)
        action("SCHRIFT",lambda: f"{int(self.font_scale*100)} %",
               self._cycle_font_scale,PS1_CYAN)

        section("SYSTEM")
        action("HÄNDLER",lambda: str(len(self.active_haendler)),
               lambda: (ref["p"] and ref["p"].dismiss(),
                        Clock.schedule_once(lambda dt:self._open_haendler_picker(),0.16)),
               PS1_BLUE)
        action("ALARM-REGELN",lambda: "ÖFFNEN",
               lambda: (ref["p"] and ref["p"].dismiss(),
                        Clock.schedule_once(lambda dt:self._open_alarm_rules(),0.16)),
               PS1_YELLOW)
        action("SHOP-HEALTH",lambda: "ÖFFNEN",
               lambda: (ref["p"] and ref["p"].dismiss(),
                        Clock.schedule_once(lambda dt:self._open_health(),0.16)),
               PS1_BLUE)
        action("TESTALARM",lambda: "SENDEN",self._send_test_alarm,PS1_CYAN)

        box.size_hint=(1,None)
        box.bind(minimum_height=box.setter("height"))
        sv=ScrollView(bar_width=dp(4),do_scroll_x=False)
        sv.add_widget(box)
        root=BoxLayout(orientation="vertical",spacing=dp(4),padding=dp(2))
        root.add_widget(sv)
        close=PS1Button(text="SCHLIESSEN",accent=PS1_SILVER,font_size=sp(10),
                        size_hint_y=None,height=dp(36))
        root.add_widget(close)
        p=Popup(title="",content=root,size_hint=(None,None),
                width=min(dp(560),Window.width*0.94),
                height=min(dp(620),Window.height*0.88),
                background_color=(0.045,0.05,0.062,0.99),separator_height=0)
        ref["p"]=p
        close.bind(on_release=lambda *_:p.dismiss())
        p.open()

    def _open_alarm_rules(self):
        box=BoxLayout(orientation="vertical",spacing=dp(5),padding=dp(9))
        t=Label(text="[b]ALARM-REGELN[/b]",markup=True,color=PS1_SILVER,
                font_size=sp(14),font_name=SST_FONT,size_hint_y=None,height=dp(26))
        box.add_widget(t)
        hint=Label(text="Gilt fuer Vordergrund und Hintergrund.",color=PS1_GREY,
                   font_size=sp(8.5),font_name=SST_FONT,size_hint_y=None,height=dp(18))
        box.add_widget(hint)

        def add_toggle(key,default,label_on,label_off,accent):
            b=PS1Button(text="",accent=accent,font_size=sp(10),
                        size_hint_y=None,height=dp(33))
            def sync():
                b.text=label_on if bool(self.settings.get(key,default)) else label_off
            def flip(*_):
                self.settings.set(key,not bool(self.settings.get(key,default)))
                sync(); haptic(0.02)
            b.bind(on_release=flip); sync(); box.add_widget(b)

        add_toggle("notify_sofort",True,"NUR SOFORT: AN","NUR SOFORT: AUS",PS1_GREEN)
        add_toggle("notify_low_only",False,"NUR TIEFSTPREIS: AN","NUR TIEFSTPREIS: AUS",PS1_YELLOW)
        add_toggle("quiet_hours",False,"RUHEZEIT 23-07: AN","RUHEZEIT 23-07: AUS",PS1_BLUE)

        row=BoxLayout(size_hint_y=None,height=dp(35),spacing=dp(5))
        ti=TextInput(text=("" if self.max_preis is None else str(int(self.max_preis))),
                     multiline=False,input_filter="float",font_size=sp(11),
                     halign="center",size_hint_x=1)
        sb=PS1Button(text="PREIS SETZEN",accent=PS1_RED,font_size=sp(9),
                     size_hint_x=None,width=dp(102))
        def set_preis(*_):
            try: p=float(str(ti.text).replace(",","."))
            except (TypeError,ValueError): p=None
            if p is None or not (400<=p<=1500):
                self._toast("PREIS 400-1500 EUR",color=PS1_YELLOW); return
            self.max_preis=p; self.max_preis_chip.text=self._max_text()
            self.settings.set("max_preis",p)
            self._reclassify_all(); self._rerender()
            self._toast(f"MAX {int(p)} EUR",color=PS1_GREEN)
        sb.bind(on_release=set_preis); row.add_widget(ti); row.add_widget(sb)
        box.add_widget(row)

        tb=PS1Button(text="TESTALARM SENDEN",accent=PS1_PINK,font_size=sp(10),
                     size_hint_y=None,height=dp(34))
        tb.bind(on_release=lambda *_:self._send_test_alarm()); box.add_widget(tb)

        stumm=self.settings.get("mute_haendler",[]) or []
        mb=PS1Button(text=f"STUMME SHOPS: {len(stumm)}  ·  LISTE LEEREN",accent=PS1_SILVER,
                     font_size=sp(9),size_hint_y=None,height=dp(30))
        def clear_mute(*_):
            self.settings.set("mute_haendler",[])
            mb.text="STUMME SHOPS: 0  ·  LISTE LEEREN"
            self._toast("STUMM-LISTE GELEERT",color=PS1_GREY)
        mb.bind(on_release=clear_mute); box.add_widget(mb)

        cb=PS1Button(text="SCHLIESSEN",accent=PS1_BLUE,font_size=sp(10),
                     size_hint_y=None,height=dp(34))
        # Auf kleinen Querformat-Displays ist der Inhalt hoeher als das Popup;
        # dann bleibt er wenigstens scrollbar statt unten abgeschnitten zu sein.
        box.size_hint=(1,None)
        box.bind(minimum_height=box.setter("height"))
        sv=ScrollView(bar_width=dp(4)); sv.add_widget(box)
        p=Popup(title="",content=sv,size_hint=(None,None),
                width=min(dp(560),Window.width*0.92),
                height=min(dp(440),Window.height*0.9),
                background_color=(0.08,0.08,0.09,1),separator_height=0)
        cb.bind(on_release=lambda *_:p.dismiss()); box.add_widget(cb)
        p.open()

    def _age_text(self,ts):
        try: s=max(0,int(time.time()-float(ts)))
        except (TypeError,ValueError): return "?"
        if s>=86400: return f"{s//86400}T"
        if s>=3600: return f"{s//3600}H"
        return f"{max(1,s//60)}M"

    def _open_health(self):
        daten=Health().all()
        fehler=[]; parser_fehler=[]
        for h in HAENDLER:
            e=daten.get(h["name"]) or {}
            if e.get("last_status") in ("error","challenge","unknown","parser"):
                fehler.append(h["name"])
            try: p_streak=int(e.get("parser_streak") or 0)
            except (TypeError,ValueError): p_streak=0
            if p_streak>0: parser_fehler.append((h["name"],p_streak))
        box=BoxLayout(orientation="vertical",spacing=dp(5),padding=dp(8))
        kopf=Label(text="[b]SHOP-HEALTH[/b]",markup=True,color=PS1_SILVER,
                   font_size=sp(12),font_name=SST_FONT,
                   size_hint_y=None,height=dp(22),
                   halign="left",valign="middle")
        kopf.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        box.add_widget(kopf)
        # Zaehler und Fehlerzahl in einer eigenen Zeile: Auch bei vielen
        # auffaelligen Shops bleibt der Kopf dadurch vollstaendig lesbar.
        summary=Label(text=f"{len(HAENDLER)} SHOPS · {len(fehler)} AUFFAELLIG",
                      color=PS1_CYAN,font_size=sp(9),font_name=SST_FONT,
                      size_hint_y=None,height=dp(14),
                      halign="left",valign="middle",shorten=True,
                      shorten_from="right")
        summary.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
        box.add_widget(summary)
        if parser_fehler:
            # Die Parser-Serie ist eine Zusatzinformation. Sie bekommt eine
            # eigene Zeile, damit der Titel auch auf 320 dp nicht abgeschnitten
            # wird; der Inhalt bleibt vollständig sichtbar.
            pser=Label(text=f"PARSER-SERIE {max(n for _,n in parser_fehler)}",
                       color=PS1_YELLOW,font_size=sp(8.5),font_name=SST_FONT,
                       size_hint_y=None,height=dp(14),
                       halign="left",valign="middle",shorten=True,
                       shorten_from="right")
            pser.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            box.add_widget(pser)
        sv=ScrollView(bar_width=dp(4))
        inner=BoxLayout(orientation="vertical",size_hint_y=None,spacing=dp(2))
        inner.bind(minimum_height=inner.setter("height"))
        order=sorted(HAENDLER,key=lambda h:(0 if h["name"] in fehler else 1,h["name"]))
        for h in order:
            e=daten.get(h["name"]) or {}; status=e.get("last_status") or "NOCH NICHT GEPRUEFT"
            ok=e.get("ok_ts"); last=e.get("last_ts")
            if status in ("error","challenge","parser","unknown"):
                age=("seit "+self._age_text(last)) if last else ""
            elif ok: age=self._age_text(ok)
            elif last: age="seit "+self._age_text(last)
            else: age=""
            row=BoxLayout(size_hint_y=None,height=dp(26),spacing=dp(4))
            farbe=(CARD_STATUS.get(status,PS1_GREY) if status in CARD_STATUS
                   else PS1_GREY)
            row.add_widget(Dot(farbe))
            lb=Label(text=h["name"],color=PS1_TEXT,font_size=sp(9.5),font_name=SST_FONT,
                     halign="left",valign="middle",shorten=True,shorten_from="right")
            lb.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); row.add_widget(lb)
            try: p_streak=int(e.get("parser_streak") or 0)
            except (TypeError,ValueError): p_streak=0
            status_txt=status.upper()
            if status=="parser":
                status_txt=f"PARSER {max(1,p_streak)}x"
            st=Label(text=f"{status_txt} {age}",color=farbe,font_size=sp(8),
                     font_name=SST_FONT,halign="right",valign="middle",
                     size_hint_x=None,width=dp(120))
            st.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); row.add_widget(st)
            inner.add_widget(row)
        sv.add_widget(inner); box.add_widget(sv)
        btns=BoxLayout(size_hint_y=None,height=dp(36),spacing=dp(5))
        rb=PS1Button(text="FEHLER PRUEFEN",accent=PS1_YELLOW,font_size=sp(9))
        lb=PS1Button(text="LOG TEILEN",accent=PS1_BLUE,font_size=sp(9))
        cb=PS1Button(text="ZU",accent=PS1_SILVER,font_size=sp(9))
        p=Popup(title="",content=box,size_hint=(None,None),
                width=min(dp(680),Window.width*0.92),
                height=min(dp(640),Window.height*0.82),
                background_color=(0.08,0.08,0.09,1),separator_height=0)
        def retry(*_):
            if not fehler:
                self._toast("ALLE SHOPS UNVERDAECHTIG",color=PS1_GREEN); return
            p.dismiss(); self._scan_start(nur=fehler)
        def log(*_):
            txt=read_crash_log()
            if not txt: self._toast("KEIN CRASH-LOG VORHANDEN",color=PS1_GREY); return
            share_text(txt)
        rb.bind(on_release=retry); lb.bind(on_release=log)
        cb.bind(on_release=lambda *_:p.dismiss())
        btns.add_widget(rb); btns.add_widget(lb); btns.add_widget(cb)
        box.add_widget(btns)
        cfg=PS1Button(text="REMOTE-CONFIG AKTUALISIEREN",accent=PS1_PINK,
                      font_size=sp(9),size_hint_y=None,height=dp(32))
        def load_cfg(*_):
            self._toast("REMOTE-CONFIG WIRD GELADEN...",color=PS1_BLUE)
            threading.Thread(target=self._shop_config_bg,args=(True,),daemon=True).start()
        cfg.bind(on_release=load_cfg); box.add_widget(cfg)
        p.open()

    def _shop_config_bg(self,force=False):
        try: n=aktualisiere_shop_config(force)
        except Exception: n=0
        if n:
            try:
                Clock.schedule_once(
                    lambda dt:self._toast(f"REMOTE-CONFIG: {n} SHOPS AKTIV",color=PS1_GREEN),0)
            except Exception: pass

    def _open_detail(self,r,serie):
        # Die Karte uebergibt normalerweise eine Liste; ein leerer oder
        # fehlender Verlauf darf die Detailansicht nicht mit len(None) beenden.
        serie=list(serie) if isinstance(serie,(list,tuple)) else []
        name=r.get("haendler","?")
        box=BoxLayout(orientation="vertical",spacing=dp(5),padding=dp(10))
        titel=name + (" · " + format_preis(r["preis"]) if r.get("preis") is not None else "")
        box.add_widget(Label(text=f"[b]{titel}[/b]",markup=True,color=PS1_TEXT,
                             font_size=sp(15),font_name=SST_FONT,
                             size_hint_y=None,height=dp(28)))
        cond=r.get("condition"); cond_txt=("GEBRAUCHT/REFURB" if ist_gebraucht(cond)
                                          else "NEU" if cond=="new" else "UNBEKANNT")
        sofort=r.get("sofort"); sofort_txt=("SOFORT" if sofort is True else
                                            "VORBESTELLUNG" if sofort is False else "UNBEKANNT")
        zeilen=[("ZUSTAND",cond_txt),("VERKAEUFER",r.get("seller") or "—"),
                ("LIEFERBAR",sofort_txt),("SIGNAL",str(r.get("signal") or "—").upper()),
                ("VERFUEGBARKEIT",str(r.get("verfuegbarkeit") or "—"))]
        hzustand=Health().all().get(name) or {}
        if hzustand.get("last_ts"):
            zeilen.append(("ZULETZT GEPRUEFT", self._age_text(hzustand["last_ts"])+" alt"))
        for k,v in zeilen:
            row=BoxLayout(size_hint_y=None,height=dp(20))
            a=Label(text=k,color=PS1_GREY,font_size=sp(8.5),font_name=SST_FONT,
                    halign="left",valign="middle")
            b=Label(text=str(v),color=PS1_TEXT,font_size=sp(8.5),font_name=SST_FONT,
                    halign="right",valign="middle",shorten=True,shorten_from="right")
            for x in (a,b): x.bind(size=lambda w,*_:setattr(w,"text_size",w.size))
            row.add_widget(a); row.add_widget(b); box.add_widget(row)
        tief30=tief_30(serie); allzeit=self.history.get_tief(name)
        info=Label(text=f"30-TAGE-TIEF: {format_preis(tief30) if tief30 else '—'}\n"
                         f"ALLZEIT-TIEF: {format_preis(allzeit) if allzeit else '—'}",
                   color=PS1_SILVER,font_size=sp(9),font_name=SST_FONT,
                   size_hint_y=None,height=dp(32),halign="left")
        box.add_widget(info)
        if len(serie)>=2:
            box.add_widget(Sparkline(serie,color=CARD_STATUS.get(r.get("klass"),PS1_GREEN),
                                     size_hint_y=None,height=dp(64)))
        else:
            box.add_widget(Label(text="Noch zu wenig Preisverlauf fuer eine Kurve.",
                                 color=PS1_GREY,font_size=sp(8.5),font_name=SST_FONT,
                                 size_hint_y=None,height=dp(24)))
        mute=set(self.settings.get("mute_haendler",[]) or [])
        mb=PS1Button(text=("HANDLER LAUT" if name in mute else "HANDLER STUMM"),
                     accent=PS1_YELLOW,font_size=sp(9),size_hint_y=None,height=dp(32))
        def toggle_mute(*_):
            if name in mute: mute.discard(name)
            else: mute.add(name)
            self.settings.set("mute_haendler",sorted(mute))
            mb.text="HANDLER LAUT" if name in mute else "HANDLER STUMM"
            self._toast("HANDLER STUMM" if name in mute else "HANDLER LAUT",
                        color=PS1_GREY)
        mb.bind(on_release=toggle_mute); box.add_widget(mb)
        row=BoxLayout(size_hint_y=None,height=dp(36),spacing=dp(5))
        ob=PS1Button(text="SHOP OEFFNEN",accent=PS1_GREEN,font_size=sp(9))
        cb=PS1Button(text="SCHLIESSEN",accent=PS1_SILVER,font_size=sp(9))
        box.size_hint=(1,None)
        box.bind(minimum_height=box.setter("height"))
        sv=ScrollView(bar_width=dp(4)); sv.add_widget(box)
        p=Popup(title="",content=sv,size_hint=(None,None),
                width=min(dp(560),Window.width*0.94),
                height=min(dp(420),Window.height*0.9),
                background_color=(0.08,0.08,0.09,1),separator_height=0)
        ob.bind(on_release=lambda *_: (p.dismiss(),open_url(r.get("url"))))
        cb.bind(on_release=lambda *_:p.dismiss())
        row.add_widget(ob); row.add_widget(cb); box.add_widget(row)
        p.open()
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
        p=Popup(title="",content=c,size_hint=(None,None),
                width=min(dp(560),Window.width*0.94),height=ph,
                pos_hint={"center_x":0.5,"y":0.02},
                background_color=(0.08,0.08,0.09,1),separator_height=0)
        ref["p"]=p; p.open()
    def _bg_merge(self):
        """Ergebnisse des Hintergrund-Service beim Zurueckkehren uebernehmen."""
        try:
            with open(os.path.join(data_dir(),BG_STATUS_FILE),"r",encoding="utf-8") as f:
                d=json.load(f)
        except Exception: return
        if not isinstance(d,dict): return
        try: ts=float(d.get("ts") or 0)
        except (TypeError,ValueError): ts=0.0
        if ts<=self._bg_seen_ts: return
        self._bg_seen_ts=ts
        self._bg_text_at=0.0
        # Der Service hat die Health-Datei fortgeschrieben; Singleton neu laden,
        # damit der naechste Speichervorgang die Hintergrunddaten nicht ueberschreibt.
        try: reset_health()
        except Exception: pass
        for r in d.get("results") or []:
            if not isinstance(r,dict) or not r.get("haendler"): continue
            try:
                if r.get("klass") not in ("error","challenge","unavail","parser"):
                    r["klass"]=classify(True,r.get("preis"),self.max_preis)
                self.scanned[r["haendler"]]=r
            except Exception: continue
        # Der Service hat die History bereits fortgeschrieben - neu einlesen,
        # damit die Sparkline den Stand des Hintergrund-Scans zeigt.
        try: self.history=History()
        except Exception: pass
        if self.scanned: self._rerender()
        # Der Service hat gerade gescannt - nicht sofort erneut loslegen.
        if ts>self.next_scan_at: self.next_scan_at=ts+self.auto_interval
        try: n=int(d.get("treffer") or 0); neu=int(d.get("neu") or 0)
        except (TypeError,ValueError): n=neu=0
        # Alte Meldungen nach einem Neustart nicht erneut als Neuigkeit zeigen.
        frisch=(time.time()-ts)<=max(7200,self.auto_interval*2)
        alter=self._bg_alter_text(ts)
        if n and frisch:
            self._toast("HINTERGRUND (%s): %d TREFFER%s"%(alter,n,(" \u00b7 %d NEU"%neu) if neu else ""),
                        color=PS1_YELLOW)
        elif d.get("geprueft"):
            self._toast("HINTERGRUND (%s): KEINE TREFFER"%alter,color=PS1_GREY)

    def _bg_alter_text(self,ts):
        try: s=max(0,int(time.time()-float(ts)))
        except (TypeError,ValueError): return "?"
        return f"{s//3600}H" if s>=3600 else f"{max(1,s//60)}M"

    def _bg_last_text(self):
        """Heartbeat fuer die Statuszeile - hoechstens einmal pro Minute von Platte."""
        jetzt=time.time()
        if jetzt-self._bg_text_at<60: return self._bg_text
        self._bg_text_at=jetzt; self._bg_text=None
        try:
            with open(os.path.join(data_dir(),BG_STATUS_FILE),"r",encoding="utf-8") as f:
                ts=float(json.load(f).get("ts") or 0)
            if ts>0: self._bg_text=self._bg_alter_text(ts)
        except Exception: pass
        return self._bg_text

    def _warn_if_bg_stale(self):
        """Ein toter Hintergrund-Service soll nicht still bleiben."""
        if not self.auto_scan: return
        try:
            with open(os.path.join(data_dir(),BG_STATUS_FILE),"r",encoding="utf-8") as f:
                d=json.load(f)
            ts=float(d.get("ts") or 0)
        except Exception: return
        if ts<=0: return
        alter=time.time()-ts
        grenze=max(1800,int(self.auto_interval)*2+600)
        if alter<=grenze or time.time()<self._bg_warn_until: return
        self._bg_warn_until=time.time()+6*3600
        txt=self._bg_alter_text(ts)
        self._toast(f"HINTERGRUND SEIT {txt} AUS",color=PS1_YELLOW)
        box=BoxLayout(orientation="vertical",spacing=dp(8),padding=dp(12))
        t=Label(text="[b]HINTERGRUND-SCAN PAUSIERT[/b]",markup=True,
                color=PS1_SILVER,font_size=sp(12),font_name=SST_FONT,
                halign="center",valign="middle",size_hint_y=None,height=dp(28))
        t.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); box.add_widget(t)
        m=Label(text=f"Letzter Lauf vor {txt}. Android oder der Akku-Manager\n"
                     "hat den Dienst beendet. In den App-Einstellungen\n"
                     "lassen sich Akku-Optimierung und Benachrichtigungen prüfen.",
                color=PS1_GREY,font_size=sp(9),font_name=SST_FONT,
                halign="center",valign="middle")
        m.bind(size=lambda w,*_:setattr(w,"text_size",w.size)); box.add_widget(m)
        row=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(8))
        b1=PS1Button(text="EINSTELLUNGEN",accent=PS1_BLUE,font_size=sp(10))
        b2=PS1Button(text="SPÄTER",accent=PS1_SILVER,font_size=sp(10))
        ref={"p":None}
        b1.bind(on_release=lambda *_: (ref["p"] and ref["p"].dismiss(),open_app_settings()))
        b2.bind(on_release=lambda *_: ref["p"] and ref["p"].dismiss())
        row.add_widget(b1); row.add_widget(b2); box.add_widget(row)
        p=Popup(title="",content=box,size_hint=(None,None),
                width=min(dp(520),Window.width*0.9),height=dp(220),
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
        if self._placeholder is not None and not self._wide:
            self._placeholder.width=max(dp(240),w)
    def _show_placeholder(self,titel,unter):
        self._clear_results()
        box=BoxLayout(orientation="vertical",size_hint=(1,None),
                      height=dp(180),spacing=dp(2),padding=dp(10))
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
               if self.filter_mode=="alle" or
               (self.scanned[n]["klass"]=="hit"
                and not ist_gebraucht(self.scanned[n].get("condition")))]
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
                   self.scanned[n].get("_is_new"),self.scanned[n].get("_restock"),
                   len(self.history.get_serie(n)),
                   self.scanned[n].get("condition"),self.scanned[n].get("sofort"))
                  for n in namen)
        if sig==self._last_sig and self._placeholder is None:
            return
        sx=self.results_scroll.scroll_x; sy=self.results_scroll.scroll_y
        self._clear_results()
        self._last_sig=sig
        preise=[self.scanned[n]["preis"] for n in namen
                if self.scanned[n]["klass"]=="hit" and
                self.scanned[n]["preis"] is not None]
        best=min(preise) if preise else None
        for n in namen:
            r=self.scanned[n]
            card=ResultCard(r,r.get("_is_new",False),r.get("_prev"),
                            self.history.get_serie(n),detail_cb=self._open_detail,
                            best=(r["klass"]=="hit" and best is not None and
                                  r["preis"]==best),
                            font_scale=self.font_scale)
            card.size_hint=(1,None)
            card.height=(dp(80) if r["klass"]=="challenge" else dp(56))*self.font_scale
            self.results_row.add_widget(card)
        if sx>0 or sy<1:
            Clock.schedule_once(lambda dt:(setattr(self.results_scroll,"scroll_x",sx),
                                          setattr(self.results_scroll,"scroll_y",sy)),0)

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
    def _scan_start(self,nur=None):
        if self.scanning: return
        if self._rerender_event is not None:
            Clock.unschedule(self._rerender_event); self._rerender_event=None
        namen=set(nur) if nur is not None else self.active_haendler
        aktive=[h for h in HAENDLER if h["name"] in namen]
        if not aktive:
            self._toast("MINDESTENS EINEN HÄNDLER WÄHLEN",PS1_YELLOW); return
        haptic(0.05); self.scanning=True
        # Ein Health-Retry soll die bereits sichtbaren Ergebnisse behalten und
        # nur die auffaelligen Shops neu abfragen.
        if nur is None: self.scanned={}
        self.results_scroll.scroll_y=1
        self._scan_token+=1; tok=self._scan_token
        cancel=threading.Event(); self._scan_cancel_event=cancel
        self._drain_stale()
        if nur is None: self.radar.blips=[]
        self.radar.scanning=True
        self._clear_results()
        self._show_placeholder("SCANNE...","TIPPE STOP ZUM ABBRECHEN")
        self.scan_btn.text="STOP"
        self._scan_t0=time.time(); self._scan_done=0
        self._scan_total=len(aktive)
        self._update_radar_hud()
        self.results_count.text=f"0/{len(aktive)}"
        self.results_count.color=PS1_GREY
        self.results_status.color=PS1_SILVER
        self.results_status.text=scan_fortschritt(0,len(aktive),0,0)
        threading.Thread(target=self._scan_worker,args=(aktive,tok,cancel),daemon=True).start()
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
        # Das Event erreicht die HTTP-Retry-Schleifen. Eine bereits laufende
        # Anfrage kann nicht abgebrochen werden, aber danach wird kein Retry
        # und kein weiterer Shop mehr gestartet.
        try:
            if self._scan_cancel_event is not None: self._scan_cancel_event.set()
        except Exception: pass
        haptic(0.03); self._scan_end(abgebrochen=True)
    def _scan_worker(self,hl,tok,cancel=None):
        # cancel_futures + wait=False: STOP wirkt sofort. Ein "with"-Block
        # wartet beim Verlassen auf alle laufenden Anfragen (bis zu TIMEOUT
        # pro Haendler) - und ein direkt danach gestarteter Scan laeuft dann
        # mit doppelt so vielen gleichzeitigen Verbindungen.
        ex=ThreadPoolExecutor(max_workers=WORKER)
        try:
            futs={ex.submit(_safe_scan,h,cancel):h for h in hl}
            for f in as_completed(futs):
                if tok!=self._scan_token or (cancel is not None and cancel.is_set()):
                    for fut in futs: fut.cancel()
                    break
                try: r=f.result()
                except Exception as e: r=_res(futs[f],None,"error",0,str(e)[:60])
                if r is None: continue
                self.queue.put((tok,r))
        finally:
            # Der Cache puffert 304-Ergebnisse waehrend des Scans; hier wird
            # die Datei genau einmal statt pro Shop geschrieben.
            try: flush_http_cache()
            except Exception: pass
            ex.shutdown(wait=False, cancel_futures=True)
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
        self._update_radar_hud()
        try:
            if r["klass"] not in ("error","challenge","unavail","parser"):
                r["klass"]=classify(True,r["preis"],self.max_preis)
            prev=self.history.get_last(name)
            vorher_av=self.history.get_verfuegbar(name)
            ereignis=alarm_ereignis(r,prev,vorher_av)
            r["_prev"]=prev
            r["_is_new"]=ereignis=="new"
            r["_restock"]=ereignis=="restock"
            self.scanned[name]=r
            self._update_blip(name,r["klass"])
            hits=sum(1 for x in self.scanned.values() if x["klass"]=="hit"
                     and not ist_gebraucht(x.get("condition")))
            self.results_status.text=scan_fortschritt(
                self._scan_done,self._scan_total,hits,time.time()-self._scan_t0)
            self.results_count.text=f"{hits}/{self._scan_done}" if self.filter_mode=="verfuegbar" else f"{self._scan_done}/{self._scan_total}"
            if ereignis:
                self._maybe_notify(r)
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
        self._update_radar_hud()
        self.scan_btn.text="SCAN"
        d=time.time()-self._scan_t0
        hits=[x for x in self.scanned.values() if x["klass"]=="hit"
              and not ist_gebraucht(x.get("condition"))]
        new=sum(1 for x in self.scanned.values() if x.get("_is_new"))
        back=sum(1 for x in self.scanned.values() if x.get("_restock"))
        try: health().save()
        except Exception: pass
        self.history.update(self.scanned.values())
        # Bei Treffern keinen kompletten Karten-Neubau mitten in den letzten
        # Radar-Frame legen; der geplante Throttle-Render uebernimmt.
        if hits: self._rerender_throttled()
        else: self._rerender()
        ts=datetime.now().strftime("%H:%M")
        if abgebrochen:
            self.results_status.text=(f"ABGEBROCHEN · {self._scan_done}/{self._scan_total}"
                                      f" GEPRÜFT · {ts}")
            self.results_status.color=PS1_YELLOW
            self._toast("SCAN ABGEBROCHEN",color=PS1_YELLOW)
        elif hits:
            preise=[x["preis"] for x in hits if x.get("preis") is not None]
            best_txt=(f" · BEST {int(min(preise))} €" if preise else "")
            self.results_status.text=f"{len(hits)} TREFFER{best_txt} · {ts}"
            self.results_status.color=CARD_STATUS["hit"]
            self.results_count.color=CARD_STATUS["hit"]
            haptic(0.12)
            if new>0: self._toast(f"{new} NEUE TREFFER",color=PS1_YELLOW)
            elif back>0: self._toast(f"{back} WIEDER VERFÜGBAR",color=CARD_STATUS["hit"])
            else: self._toast(f"{len(hits)} TREFFER",color=CARD_STATUS["hit"])
        else:
            self.results_status.text=f"KEINE TREFFER · {d:.0f}s · {ts}"
            self.results_status.color=PS1_GREY
            blk=sum(1 for x in self.scanned.values() if x["klass"]=="challenge")
            err=sum(1 for x in self.scanned.values() if x["klass"]=="error")
            prs=sum(1 for x in self.scanned.values() if x["klass"]=="parser")
            teile=[f"{len(self.scanned)} GEPRÜFT"]
            if blk: teile.append(f"{blk} BOT-SCHUTZ")
            if err: teile.append(f"{err} FEHLER")
            if prs: teile.append(f"{prs} PARSER")
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
    def on_start(self):
        # Kalter Start ueber eine Benachrichtigung: nach dem ersten Frame oeffnen.
        Clock.schedule_once(self._open_deep_link,0.8)
    def _open_deep_link(self,*_):
        u=consume_deep_link()
        if u: open_url(u)
    def build(self):
        install_crash_hook("app")
        Window.clearcolor=C_BG
        try:
            if platform in ("android","ios"): Window.fullscreen='auto'
        except Exception: pass
        request_android_permissions()
        android_prepare_window()
        self.root_layout=RootLayout(); return self.root_layout
    def on_pause(self):
        try: self.root_layout.main_ui.radar.pause()
        except Exception: pass
        try:
            ui=self.root_layout.main_ui
            # AUTO an = auch im Hintergrund weiterscannen (Foreground-Service).
            # Ein laufender Vordergrund-Scan wuerde sonst parallel dieselben
            # Shops abfragen; der Service uebernimmt nach dem Abbruch.
            if ui.scanning: ui._scan_cancel()
            if ui.auto_scan: bg_service_start(ui.auto_interval)
        except Exception: pass
        return True
    def on_resume(self):
        try:
            bg_service_stop()
            ui=self.root_layout.main_ui
            ui.radar.resume()
            ui._refresh_insets()
            ui._bg_merge()
            ui._warn_if_bg_stale()
            Clock.schedule_once(self._open_deep_link,0.3)
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
            c=ScrollView()
            l=Label(text=err,text_size=(dp(400),None),size_hint_y=None,markup=False)
            l.bind(texture_size=l.setter("size")); c.add_widget(l)
            Popup(title="Startup Error",content=c,size_hint=(0.95,0.85)).open()
        except Exception: pass
