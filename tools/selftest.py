"""Logiktests fuer main.py - laufen ohne Kivy und ohne Android.

Prueft die Teile, die ueber richtig/falsch entscheiden: Preis-Parsing, JSON-LD,
Verfuegbarkeit, Bot-Schutz, Klassifizierung, Haendlerdaten.

    python3 tools/selftest.py

Exit-Code 0 = alles gruen. Wird im Release-Workflow als Gate vor dem
APK-Build ausgefuehrt, damit ein kaputtes Parsing nie in die APK geht.
"""
import configparser
import json
import math
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class _W:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def bind(self, **kw):
        pass


class _Label(_W):
    pass


class _Button(_W):
    state = "normal"


class _ToggleButton(_Button):
    pass


class _ButtonBehavior:
    pass


class _Clock:
    @staticmethod
    def schedule_once(*a, **k):
        return True

    @staticmethod
    def schedule_interval(*a, **k):
        return True

    @staticmethod
    def unschedule(*a, **k):
        return None


class _Animation:
    def __init__(self, **kw):
        pass

    def start(self, *a, **k):
        return self

    @staticmethod
    def cancel_all(*a, **k):
        pass


class _LabelBase:
    @staticmethod
    def register(**kw):
        pass


def _get_color_from_hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)


def _stub_kivy():
    """Minimal-Stubs, damit main.py ohne Kivy-Installation importierbar ist."""
    _mod("kivy")
    _mod("kivy.config", Config=types.SimpleNamespace(set=lambda *a, **k: None))
    _mod("kivy.app", App=type("App", (_W,), {"get_running_app": staticmethod(lambda: None)}))
    _mod("kivy.clock", Clock=_Clock)
    _mod("kivy.core")
    _mod("kivy.core.window", Window=types.SimpleNamespace(
        width=420, height=820, bind=lambda **k: None, clearcolor=None, fullscreen=None))
    _mod("kivy.core.text", LabelBase=_LabelBase)
    _mod("kivy.graphics", Color=_W, Ellipse=_W, Line=_W, RoundedRectangle=_W, Rectangle=_W)
    _mod("kivy.metrics", dp=lambda x: x, sp=lambda x: x)
    _mod("kivy.properties", NumericProperty=lambda *a, **k: None,
         ListProperty=lambda *a, **k: None, BooleanProperty=lambda *a, **k: None)
    _mod("kivy.uix")
    _mod("kivy.uix.behaviors", ButtonBehavior=_ButtonBehavior)
    _mod("kivy.uix.boxlayout", BoxLayout=_W)
    _mod("kivy.uix.button", Button=_Button)
    _mod("kivy.uix.checkbox", CheckBox=_W)
    _mod("kivy.uix.floatlayout", FloatLayout=_W)
    _mod("kivy.uix.label", Label=_Label)
    _mod("kivy.uix.popup", Popup=_W)
    _mod("kivy.uix.scrollview", ScrollView=_W)
    _mod("kivy.uix.textinput", TextInput=_W)
    _mod("kivy.uix.togglebutton", ToggleButton=_ToggleButton)
    _mod("kivy.uix.widget", Widget=_W)
    _mod("kivy.animation", Animation=_Animation)
    _mod("kivy.utils", get_color_from_hex=_get_color_from_hex, platform="linux")


_stub_kivy()
import main  # noqa: E402
import scan_core as core  # noqa: E402

FAILS = []
COUNT = 0


def check(name, got, want):
    global COUNT
    COUNT += 1
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: {got!r} (erwartet {want!r})")
        FAILS.append(name)


HTML_PARSER = ("<html><head><title>PlayStation 5 Pro 2 TB</title></head>"
               "<body>PlayStation 5 Pro 2 TB · Auf Lager</body></html>")
HTML_UNAVAIL = ("<html><head><title>PlayStation 5 Pro 2 TB</title></head>"
                 "<body>PlayStation 5 Pro 2 TB · derzeit nicht verfügbar</body></html>")

HTML_OK = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product",
 "name":"Sony PlayStation 5 Pro 2 TB (E-Chassis)",
 "offers":{"@type":"Offer","price":"799,99","priceCurrency":"EUR",
           "availability":"https://schema.org/InStock"}}
</script></head><body>In den Warenkorb</body></html>"""


def main_tests():
    # Preis-Parsing und Formatierung
    check("parse 1.299,00", core.parse_preis_str("1.299,00 €"), 1299.0)
    check("parse 799,99", core.parse_preis_str("799,99"), 799.99)
    check("parse EUR 1.199,00", core.parse_preis_str("EUR 1.199,00"), 1199.0)
    check("parse 1.299,5", core.parse_preis_str("1.299,5"), 1299.5)
    check("parse 1099,00 vierstellig", core.parse_preis_str("1099,00 €"), 1099.0)
    check("parse 1.099 Tausenderpunkt", core.parse_preis_str("1.099 €"), 1099.0)
    check("parse 2.099,90", core.parse_preis_str("2.099,90"), 2099.9)
    check("parse 1.5 bleibt dezimal", core.parse_preis_str("1.5"), 1.5)
    check("parse 799,- ohne Cent", core.parse_preis_str("799,-"), 799.0)
    check("parse 799,– Halbgeviertstrich", core.parse_preis_str("799,–"), 799.0)
    check("parse 1.299,-- ohne Cent", core.parse_preis_str("1.299,--"), 1299.0)
    check("parse 1.299,00 mit Sternchen", core.parse_preis_str("1.299,00 €*"), 1299.0)
    check("parse (799,00 €) in Klammern", core.parse_preis_str("(799,00 €)"), 799.0)
    check("parse ohne Zahl", core.parse_preis_str("n/a"), None)
    check("format 1299.5", core.format_preis(1299.5), "1.299,50 €")
    check("format 799", core.format_preis(799.0), "799,00 €")

    # Klassifizierung
    check("classify unavail", core.classify(False, 799, 900), "unavail")
    check("classify unknown", core.classify(True, None, 900), "unknown")
    check("classify hit", core.classify(True, 899, 900), "hit")
    check("classify expensive", core.classify(True, 901, 900), "expensive")
    check("classify max offen", core.classify(True, 5000, None), "hit")

    # JSON-LD
    st = core.extract_structured(HTML_OK)
    check("jsonld ist_konsole", st["ist_konsole"], True)
    check("jsonld preis", st["preis"], 799.99)
    check("jsonld verfuegbar", st["verfuegbar"], True)
    check("pruefe_nur_konsole", core.pruefe_nur_konsole(HTML_OK, st), True)
    check("pruefe_verfuegbar", core.pruefe_verfuegbar(HTML_OK, st), True)
    check("jsonld outofstock", core.extract_structured(
        HTML_OK.replace("InStock", "OutOfStock"))["verfuegbar"], False)
    check("jsonld ausschluss zubehoer", core.extract_structured(
        HTML_OK.replace("(E-Chassis)", "DualSense Edge Controller"))["ist_konsole"], False)
    # Platzhalterpreise aus Shop-Vorlagen duerfen keinen Alarm ausloesen.
    check("jsonld platzhalter 0,00", core.extract_structured(
        HTML_OK.replace('"799,99"', '"0,00"'))["preis"], None)
    check("jsonld preis unter minimum", core.extract_structured(
        HTML_OK.replace('"799,99"', '"1,00"'))["preis"], None)
    _zwei = ('<script type="application/ld+json">['
             '{"@type":"Product","name":"Sony PlayStation 5 Pro 2 TB"},'
             '{"@type":"Product","name":"Sony PlayStation 5 Pro 2 TB",'
             '"offers":{"@type":"Offer","price":"799,00",'
             '"availability":"InStock"}}]</script>')
    check("jsonld zweiter eintrag preis",
          core.extract_structured(_zwei)["preis"], 799.0)
    _verschachtelt = ('<script type="application/ld+json">'
                     '{"@type":"Product","name":"Sony PlayStation 5 Pro 2 TB",'
                     '"offers":{"@type":"Offer","priceSpecification":'
                     '{"price":"799,00","priceCurrency":"EUR"},'
                     '"availability":"InStock"}}</script>')
    check("jsonld verschachtelter preis",
          core.extract_structured(_verschachtelt)["preis"], 799.0)
    _neu_gebraucht = ('<script type="application/ld+json">'
                      '{"@type":"Product","name":"Sony PlayStation 5 Pro 2 TB",'
                      '"offers":['
                      '{"@type":"Offer","price":"500,00",'
                      '"itemCondition":"https://schema.org/UsedCondition",'
                      '"availability":"InStock"},'
                      '{"@type":"Offer","price":"799,00",'
                      '"itemCondition":"https://schema.org/NewCondition",'
                      '"availability":"InStock"}]}</script>')
    _neu = core.extract_structured(_neu_gebraucht)
    check("jsonld neues angebot gewinnt", _neu["preis"], 799.0)
    check("jsonld zustand neu", _neu["condition"], "new")
    _usd = HTML_OK.replace('"799,99"', '"799,99"').replace(
        '"priceCurrency":"EUR"', '"priceCurrency":"USD"')
    check("jsonld fremdwaehrung ignoriert", core.extract_structured(_usd)["preis"], None)
    check("jsonld marke erkannt", core.pruefe_nur_konsole(
        "<html>PlayStation®5 Pro 2 TB</html>", {}), True)

    # urllib-Fallback: HTTPError muss als "HTTP 404" ankommen, sonst greift
    # die Schnellabschaltung fuer umgezogene Haendler nicht.
    import urllib.error as _ue
    _alt_rq, _alt_tried = core._RQ, core._RQ_TRIED
    core._RQ, core._RQ_TRIED = None, True
    def _boom(*_a, **_k):
        raise _ue.HTTPError("http://x", 404, "Not Found", None, None)
    _alt_urlopen = core.urlopen; core.urlopen = _boom
    try:
        check("urllib 404 normalisiert", core._try_url("http://x", 0)[1], "HTTP 404")
    finally:
        core.urlopen = _alt_urlopen; core._RQ, core._RQ_TRIED = _alt_rq, _alt_tried
    check("nur_konsole ohne product", core.pruefe_nur_konsole(
        "<html><body>PlayStation 5 Pro 2 TB Uebersicht</body></html>", {}), True)
    check("nur_konsole fremdprodukt", core.pruefe_nur_konsole("<html>xbox</html>", {}), False)
    # Ohne Android/Activity duerfen die Insets nichts verschieben.
    check("insets ohne android", main.android_insets(), (0.0, 0.0, 0.0, 0.0))

    # Meta-Preis-Fallback
    check("meta preis", core.extract_meta_preis(
        '<meta property="product:price:amount" content="899,00">'), 899.0)
    check("meta preis im text", core.extract_meta_preis("<p>Preis: 1.049,00 €</p>"), 1049.0)
    check("meta preis unter minimum", core.extract_meta_preis("<p>Preis: 99,00 €</p>"), None)
    check("meta preis vierstellig", core.extract_meta_preis(
        "<p>Preis: 1099,00 €</p>"), 1099.0)
    check("meta preis attributreihenfolge", core.extract_meta_preis(
        '<meta content="899,00" property="product:price:amount">'), 899.0)
    check("meta preis microdata", core.extract_meta_preis(
        '<span itemprop="price" content="849,00"></span>'), 849.0)
    check("meta preis microdata text", core.extract_meta_preis(
        '<span itemprop="price">799,00 €</span>'), 799.0)
    check("meta preis punktdezimal", core.extract_meta_preis(
        '<p>Preis: 799.00 €</p>'), 799.0)
    check("meta verfuegbar", core.extract_meta_verfuegbarkeit(
        '<meta property="og:availability" content="https://schema.org/InStock">'),
        (True, True))
    check("meta ausverkauft", core.extract_meta_verfuegbarkeit(
        '<meta property="og:availability" content="https://schema.org/OutOfStock">'),
        (False, False))

    # Bot-Schutz und Verfuegbarkeit
    check("challenge erkannt", core.detect_challenge("just a moment..."), True)
    check("kein challenge", core.detect_challenge("<html>shop</html>"), False)
    check("verfuegbar negativ", core.pruefe_verfuegbar(
        "nicht verfügbar ausverkauft", {"verfuegbar": None}), False)
    check("verfuegbar positiv", core.pruefe_verfuegbar(
        "in den warenkorb jetzt kaufen", {"verfuegbar": None}), True)
    check("verfuegbarkeit ohne Marker explizit",
          core._verfuegbarkeit_aus_text("<html>Produktseite</html>"), (True, False))

    # Haendlerdaten
    names = [h["name"] for h in core.HAENDLER]
    check("haendler eindeutig", len(names), len(set(names)))
    check("haendler https", all(u.startswith("https://")
                                for h in core.HAENDLER for u in h["urls"]), True)
    check("haendler feld vollstaendig", all(
        h.get("name") and h.get("land") in ("DE", "AT") and h.get("urls")
        for h in core.HAENDLER), True)
    # Land und Domain muessen zusammenpassen. "Aetka AT" auf aetka.de war genau
    # so ein Datenfehler: der AT-Filter zeigte damit einen deutschen Shop.
    # Ausnahmen mit Grund: PS Direct fuehrt DE und AT unter derselben .com-Domain,
    # Computeruniverse ist ein deutscher Shop auf .net.
    ausnahmen = ("direct.playstation.com", "www.playstation.com",
                 "www.computeruniverse.net")
    falsch = []
    for h in core.HAENDLER:
        host = h["urls"][0].split("/")[2].lower()
        if host.startswith(ausnahmen):
            continue
        if h["land"] == "DE" and not host.endswith(".de"):
            falsch.append(h["name"])
        if h["land"] == "AT" and not host.endswith(".at"):
            falsch.append(h["name"])
    check("land passt zur Domain", falsch, [])


def retry_tests():
    """Dauerhafte Fehler duerfen keine Wartezeit kosten, temporaere schon.

    404/410 und 403 sind dauerhaft; dafuer darf kein Retry bezahlt werden.
    Bei 429 wird Retry-After respektiert, aber hoechstens einmal wiederholt.
    5xx/Timeout muessen dagegen weiter probiert werden.
    """
    echt = core._try_url
    echt_zeit = core.time
    # Nur sleep ersetzen, damit der Test nicht wirklich wartet.
    sleeps = []
    core.time = types.SimpleNamespace(sleep=lambda s: sleeps.append(s))
    try:
        calls = []
        core._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 404", {}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"])
            fehler = None
        except RuntimeError as e:
            fehler = str(e)
        check("404 Fehlertext", fehler, "HTTP 404")
        check("404 nur ein Versuch", len(calls), 1)

        calls.clear()
        core._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 500", {}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"])
        except RuntimeError:
            pass
        check("500 dreimal probiert", len(calls), 3)

        calls.clear()
        core._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 403", {}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"])
        except RuntimeError as e:
            fehler403 = str(e)
        check("403 nur ein Versuch", len(calls), 1)
        check("403 als Bot-Schutz gemeldet", fehler403, "Bot-Schutz (HTTP 403)")

        # Eine HTML-Challenge darf ebenfalls nicht mit neuen UAs wiederholt werden.
        calls.clear()
        core._try_url = lambda u, a, p=None: (
            calls.append(a), ("<html>Just a moment...</html>", None, {}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"])
        except RuntimeError as e:
            fehler_challenge = str(e)
        check("challenge nur ein Versuch", len(calls), 1)
        check("challenge Fehlertext", fehler_challenge, "Bot-Challenge")

        # 429: der Server bestimmt die Pause; danach genau ein Retry.
        calls.clear(); sleeps.clear()
        core._try_url = lambda u, a, p=None: (
            calls.append(a), (None, "HTTP 429", {"retry_after": 2}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"])
        except RuntimeError as e:
            fehler429 = str(e)
        check("429 Fehlertext", fehler429, "Rate-Limit (HTTP 429)")
        check("429 genau zwei Versuche", len(calls), 2)
        check("429 wartet Retry-After", sleeps, [2])

        # STOP waehrend der 429-Wartezeit: _warte() liefert True, danach darf
        # kein zweiter Request mehr starten. Das Event setzt sich beim Warten,
        # damit der Test deterministisch bleibt.
        class CancelImWait(threading.Event):
            def __init__(self):
                super().__init__(); self.waits = []
            def wait(self, sekunden=None):
                self.waits.append(sekunden); self.set(); return True

        calls.clear(); sleeps.clear()
        ev_wait = CancelImWait()
        core._try_url = lambda u, a, p=None: (
            calls.append(a), (None, "HTTP 429", {"retry_after": 5}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"], cancel=ev_wait)
            abbruch = None
        except core.ScanAbgebrochen:
            abbruch = "abgebrochen"
        check("429 Cancel waehrend Wartezeit", abbruch, "abgebrochen")
        check("429 Cancel kein zweiter Versuch", len(calls), 1)
        check("429 Cancel wartet Retry-After", ev_wait.waits, [5])
        check("429 Cancel Event gesetzt", ev_wait.is_set(), True)

        # Ein sehr langes Retry-After blockiert den Scan nicht.
        calls.clear(); sleeps.clear()
        core._try_url = lambda u, a, p=None: (
            calls.append(a), (None, "HTTP 429", {"retry_after": 3600}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"])
        except RuntimeError:
            pass
        check("langes Retry-After nur ein Versuch", len(calls), 1)
        check("langes Retry-After keine Wartezeit", sleeps, [])

        check("retry-after sekunden", core._retry_after("12"), 12)
        check("retry-after datum", core._retry_after(
            "Thu, 12 Nov 2026 12:00:10 GMT",
            core.datetime(2026, 11, 12, 12, 0, 0, tzinfo=core.timezone.utc)), 10)
        check("retry-after fallback", core._retry_after("spaeter"), 8)
        check("rate-limit klasse", core.fehler_klasse("Rate-Limit (HTTP 429)"), "challenge")
        check("challenge klasse", core.fehler_klasse("Bot-Challenge"), "challenge")
        check("timeout klasse", core.fehler_klasse("timed out"), "error")

        # Nach dem letzten Versuch gibt es keinen Retry mehr. Ein Sleep dort
        # kostete pro endgueltig fehlgeschlagenem Shop noch bis zu ~6 Sekunden.
        calls.clear(); sleeps.clear()
        core._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 503", {}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"])
        except RuntimeError:
            pass
        check("503 drei Versuche", len(calls), 3)
        check("503 kein Sleep nach letztem Versuch", len(sleeps), 2)

        # STOP/Pause setzt das Event; danach darf kein neuer Versuch starten.
        calls.clear(); sleeps.clear()
        ev = threading.Event(); ev.set()
        core._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 503", {}))[1]
        try:
            core.fetch_html_multi(["https://example.invalid"], cancel=ev)
            abbruch = None
        except core.ScanAbgebrochen:
            abbruch = "abgebrochen"
        check("Abbruch vor erstem Versuch", len(calls), 0)
        check("Abbruch wird gemeldet", abbruch, "abgebrochen")
        # Der Scan misst seine Dauer mit time.time(); dafuer wieder das echte
        # time-Modul einsetzen (nur sleep war oben ersetzt).
        core.time = echt_zeit
        check("scan_einen respektiert Abbruch",
              core.scan_einen({"name": "X", "land": "DE",
                               "urls": ["https://example.invalid"]}, cancel=ev), None)
    finally:
        core._try_url = echt
        core.time = echt_zeit


def scan_status_tests():
    """scan_einen muss Sperren wirklich als challenge zurueckgeben.

    Die Hilfsfunktion fehler_klasse allein reicht nicht: der Fehler entsteht
    in fetch_mit_cache und wird erst in scan_einen in eine Ergebnisklasse
    uebersetzt. Beide Pfade werden deshalb durch scan_einen geprueft.
    """
    alt = core._try_url
    try:
        core.reset_http_cache()
        core._try_url = lambda u, a, p=None: (None, "HTTP 403", {})
        r403 = core.scan_einen({"name": "Test 403", "land": "DE",
                                "urls": ["https://example.invalid/403"]})
        check("scan_einen HTTP 403 ist challenge",
              (r403 or {}).get("klass"), "challenge")

        core.reset_http_cache()
        core._try_url = lambda u, a, p=None: (
            "<html><title>Just a moment...</title></html>", None, {})
        rchallenge = core.scan_einen({"name": "Test Challenge", "land": "DE",
                                      "urls": ["https://example.invalid/challenge"]})
        check("scan_einen HTML-Challenge ist challenge",
              (rchallenge or {}).get("klass"), "challenge")

        # HTTP 200 mit erkannter PS5-Pro-Seite, aber ohne Preis: Das ist ein
        # Parserfehler, nicht automatisch "nicht verfuegbar".
        core.reset_http_cache()
        core._try_url = lambda u, a, p=None: (HTML_PARSER, None, {})
        rparser = core.scan_einen({"name": "Test Parser", "land": "DE",
                                   "urls": ["https://example.invalid/parser"]})
        check("scan_einen HTTP 200 Parserfehler",
              (rparser or {}).get("klass"), "parser")
        check("scan_einen Parserfehler meldet Grund",
              (rparser or {}).get("fehler"), "Parser: kein Preis")
        check("scan_einen Parserfehler nicht gecacht",
              core.http_cache().get("https://example.invalid/parser"), None)

        # Ausdruecklich ausverkauft bleibt echte Nicht-Verfuegbarkeit.
        core.reset_http_cache()
        core._try_url = lambda u, a, p=None: (HTML_UNAVAIL, None, {})
        runavail = core.scan_einen({"name": "Test Unavail", "land": "DE",
                                    "urls": ["https://example.invalid/unavail"]})
        check("scan_einen ausverkauft ist unavail",
              (runavail or {}).get("klass"), "unavail")
    finally:
        core._try_url = alt


def radar_tests():
    """Bildraten-Logik des Radars - die einzige Optimierung ohne Netz und ohne UI.

    Geprueft wird die reine Funktion: 12 Bilder/s im Leerlauf, 30 beim Scan,
    Pause zeichnet nie, und die Bewegungszeit bleibt unabhaengig von der Bildrate
    (sonst liefe der Sweep bei 12 Bildern/s sichtbar langsamer).
    """
    def lauf(sekunden, dt, scanning, paused=False):
        acc, bilder, zeit = 0.0, 0, 0.0
        for _ in range(int(round(sekunden / dt))):
            zeichnen, acc, step = main.radar_frame_step(acc, dt, scanning, paused)
            if zeichnen:
                bilder += 1
                zeit += step
        return bilder, zeit, acc

    # 60 Ticks zu 1/60 s = genau 1 Sekunde
    bilder, zeit, rest = lauf(1.0, 1/60.0, scanning=False)
    check("radar 12 fps im Leerlauf", bilder, 12)
    check("radar Leerlauf volle Sekunde gezeichnet", round(zeit, 6), 1.0)

    bilder, zeit, rest = lauf(1.0, 1/60.0, scanning=True)
    check("radar 30 fps beim Scan", bilder, 30)
    check("radar Scan volle Sekunde gezeichnet", round(zeit, 6), 1.0)

    # Pause: nie zeichnen und keine Zeit ansammeln
    bilder, zeit, rest = lauf(1.0, 1/60.0, scanning=True, paused=True)
    check("radar Pause zeichnet nicht", bilder, 0)
    check("radar Pause sammelt keine Zeit", rest, 0.0)

    # Pause mitten im Intervall darf den Rest nicht verlieren
    z, acc, step = main.radar_frame_step(0.0, 0.05, False, False)   # 0,05 < 1/12
    check("radar unter Schwelle zeichnet nicht", (z, step), (False, 0.0))
    check("radar sammelt Zwischenzeit", round(acc, 6), 0.05)
    z, acc2, step = main.radar_frame_step(acc, 0.05, False, False)  # 0,10 >= 1/12
    check("radar zeichnet nach Schwelle", (z, round(step, 6)), (True, 0.1))
    check("radar acc nach Bild zurueckgesetzt", acc2, 0.0)
    z, acc, step = main.radar_frame_step(0.05, 0.05, False, True)
    check("radar Pause behaelt Zwischenzeit", (z, acc, step), (False, 0.05, 0.0))


def progress_tests():
    """Die Kopfzeile bleibt kompakt, zeigt aber Fortschritt und Restzeit."""
    check("progress start", main.scan_fortschritt(0, 42, 0, 0), "SCANNE 0/42")
    check("progress mit Treffer und Restzeit",
          main.scan_fortschritt(7, 42, 2, 14), "SCANNE 7/42 · 2 TREFFER · REST ~70S")
    check("progress am Ende ohne Restzeit",
          main.scan_fortschritt(42, 42, 2, 80), "SCANNE 42/42 · 2 TREFFER")


def service_tests():
    """Hintergrund-Service: Intervall-Untergrenze und Treffer-Deduplizierung."""
    check("bg intervall 5m wird 15m", core.bg_intervall(300), 900)
    check("bg intervall 30m bleibt", core.bg_intervall(1800), 1800)
    check("bg intervall ungueltig", core.bg_intervall("x"), 900)
    check("bg intervall leer", core.bg_intervall(None), 900)

    # Hot-Runde: nur PS Direct DE/AT, nur im Fenster, nie gegen eine Sperre.
    def bg_ts(h, m):
        return time.mktime((2026, 11, 16, h, m, 0, 0, 0, -1))
    check("bg hot takt im band", 30 <= core.BG_HOT_TAKT <= 60, True)
    bg_shops = [{"name": "PS Direct DE"}, {"name": "PS Direct AT"},
                {"name": "Amazon DE"}]
    check("bg hot im fenster",
          [h["name"] for h in core.bg_hot_shops(bg_shops, jetzt=bg_ts(10, 0))],
          ["PS Direct DE", "PS Direct AT"])
    check("bg hot ausserhalb",
          core.bg_hot_shops(bg_shops, jetzt=bg_ts(19, 0)), [])
    check("bg hot respektiert auswahl",
          [h["name"] for h in core.bg_hot_shops(
              bg_shops, aktiv={"PS Direct AT"}, jetzt=bg_ts(10, 0))],
          ["PS Direct AT"])
    check("bg hot sperre",
          [h["name"] for h in core.bg_hot_shops(
              bg_shops,
              health_daten={"PS Direct DE": {"last_status": "challenge"}},
              jetzt=bg_ts(10, 0))],
          ["PS Direct AT"])
    check("bg naechstes fenster heute",
          int(core.naechste_fenster_ts(bg_ts(8, 0))), int(bg_ts(9, 0)))
    check("bg naechstes fenster morgen",
          int(core.naechste_fenster_ts(bg_ts(10, 0))),
          int(time.mktime((2026, 11, 17, 9, 0, 0, 0, 0, -1))))

    # Wachhund: frische Pause ist kein toter Dienst.
    check("Wachhund frisch", core.bg_wachhund(
        {"ts": bg_ts(10, 0) - 60, "wach_ts": bg_ts(10, 0) - 60},
        bg_ts(10, 0), 900), {"zustand": "ok", "alter": 60, "grund": ""})
    check("Wachhund tot", core.bg_wachhund(
        {"ts": bg_ts(10, 0) - 4000, "wach_ts": bg_ts(10, 0) - 4000},
        bg_ts(10, 0), 900)["zustand"], "tot")
    check("Wachhund pausiert", core.bg_wachhund(
        {"ts": bg_ts(10, 0) - 4000, "wach_ts": bg_ts(10, 0) - 30,
         "wach_status": "pausiert", "pausiert": "KEIN WLAN"},
        bg_ts(10, 0), 900),
        {"zustand": "pausiert", "alter": 30, "grund": "KEIN WLAN"})
    check("Wachhund leer",
          core.bg_wachhund({}, bg_ts(10, 0), 900)["zustand"], "unbekannt")

    # Statusdatei: Hot-Runde und volle Runde duerfen sich nicht ueberschreiben.
    if not os.environ.get("ANDROID_PRIVATE"):
        import service as svc
        alt_dir = core._data_dir()
        tmp_bg = tempfile.mkdtemp(prefix="ps5pro-bgstatus-")
        try:
            core.set_data_dir(tmp_bg)
            pfad = os.path.join(tmp_bg, svc.STATUS_DATEI)
            svc._status_schreiben([{"haendler": "A", "klass": "unavail"}], [],
                                  intervall=900)
            with open(pfad, encoding="utf-8") as f:
                d = json.load(f)
            check("BG Status volle Runde", d.get("geprueft"), 1)
            check("BG Status Wachhund ok", d.get("wach_status"), "ok")
            svc._status_schreiben([{"haendler": "PS Direct DE",
                                    "klass": "hit", "preis": 899.0}], [],
                                  hot=True)
            with open(pfad, encoding="utf-8") as f:
                d = json.load(f)
            check("BG Status Hot getrennt", d.get("hot_geprueft"), 1)
            check("BG Status volle Runde bleibt", d.get("geprueft"), 1)
            check("BG Status Hot-Stempel", bool(d.get("hot_ts")), True)
            svc._status_schreiben([], [], intervall=900, pausiert="KEIN WLAN")
            with open(pfad, encoding="utf-8") as f:
                d = json.load(f)
            check("BG Status Pause", d.get("pausiert"), "KEIN WLAN")
            check("BG Status Pause behaelt Hot", d.get("hot_geprueft"), 1)
        finally:
            core.set_data_dir(alt_dir)
            shutil.rmtree(tmp_bg, ignore_errors=True)

    check("neuer treffer ohne vorgabe", core.ist_neuer_treffer(799.0, None), True)
    check("gleicher preis ist nicht neu", core.ist_neuer_treffer(799.0, 799.0), False)
    check("guenstiger ist neu", core.ist_neuer_treffer(750.0, 799.0), True)
    check("teurer ist nicht neu", core.ist_neuer_treffer(850.0, 799.0), False)
    check("cent-toleranz", core.ist_neuer_treffer(798.995, 799.0), False)

    roh = [{"klass": "expensive", "preis": 950.0},
           {"klass": "hit", "preis": 800.0},
           {"klass": "hit", "preis": None},
           {"klass": "error"}]
    check("treffer_aus filtert", [r["preis"] for r in core.treffer_aus(roh)], [800.0])

    # scan_alle nutzt dieselbe Klassifizierung wie die App.
    alt = core._safe_scan
    def fake(h, cancel=None):
        return {"haendler": h["name"], "preis": 800.0 if h["name"] == "A" else 950.0,
                "klass": "hit", "url": h["urls"][0], "land": h["land"],
                "dauer": 0.1, "zeit": "10:00", "fehler": None}
    core._safe_scan = fake
    try:
        rs = core.scan_alle([{"name": "A", "land": "DE", "urls": ["https://a.de"]},
                             {"name": "B", "land": "DE", "urls": ["https://b.de"]}], 900.0)
    finally:
        core._safe_scan = alt
    check("scan_alle klassifiziert", sorted(r["klass"] for r in rs),
          ["expensive", "hit"])
    check("scan_alle liefert alle", len(rs), 2)

    # Deckel je Land: derselbe Preis ist in AT ein Treffer, in DE zu teuer.
    core._safe_scan = fake
    try:
        rs = core.scan_alle([{"name": "C", "land": "DE", "urls": ["https://c.de"]},
                             {"name": "D", "land": "AT", "urls": ["https://d.at"]}],
                            {"DE": 900.0, "AT": 1000.0})
    finally:
        core._safe_scan = alt
    check("scan_alle Deckel je Land",
          {r["haendler"]: r["klass"] for r in rs},
          {"C": "expensive", "D": "hit"})


def spec_tests():
    """Der Build-Pin entscheidet ueber Erfolg oder Abbruch - deshalb geprueft.

    p4a baut ohne Pin CPython 3.14; Cython 0.29.36 (fest im p4a-Recipe) und
    Kivy 2.3 koennen nur bis 3.12. Ausserdem verlangt p4a, dass python3 und
    hostpython3 exakt dieselbe Version haben.
    """
    c = configparser.ConfigParser()
    c.read(os.path.join(ROOT, "buildozer.spec"), encoding="utf-8")
    req = c.get("app", "requirements")
    # Negative Lookbehind: sonst trifft "python3==" auch in "hostpython3==".
    m = re.search(r"(?<![a-z0-9])python3==([0-9][0-9.]*)", req)
    h = re.search(r"hostpython3==([0-9][0-9.]*)", req)
    check("spec python3 gepinnt", bool(m), True)
    check("spec hostpython3 gepinnt", bool(h), True)
    check("spec pins identisch",
          m.group(1) if m else None, h.group(1) if h else None)
    ver = m.group(1) if m else ""
    check("spec python <= 3.12", ver[:5] in ("3.10.", "3.11.", "3.12."), True)
    check("spec kivy 2.3.1", "kivy==2.3.1" in req, True)
    # 2.3.0 bricht mit NDK 28c/clang 20 in cgl_gl.c ab: dort steht
    # "const GLchar**" gegen "const GLchar* const *" der GLES-Header.
    check("spec kivy nicht 2.3.0", "kivy==2.3.0" in req, False)
    # Play verlangt seit 31.08.2026 API 36 fuer neue Apps und Updates.
    check("spec api 36", c.get("app", "android.api"), "36")
    # versionCode muss zur Anzeige-Version passen: vMAJOR.MINOR[.PATCH]
    # ergibt MAJOR*10000 + MINOR*100 + PATCH (wie tools/set_version_from_tag.sh).
    version = (c.get("app", "version") or "").strip()
    code = (c.get("app", "android.numeric_version") or "").strip()
    teile = version.split(".")
    version_ok = len(teile) in (2, 3) and all(t.isdigit() for t in teile)
    check("spec version Format", version_ok, True)
    if version_ok:
        zahlen = [int(t) for t in teile] + [0]
        check("spec versionCode passt zur Version", code,
              str(zahlen[0] * 10000 + zahlen[1] * 100 + zahlen[2]))
    else:
        check("spec versionCode lesbar", code.isdigit(), True)
    check("spec cutout", c.get("app", "android.display_cutout"), "shortEdges")
    # Hintergrund-Scan: ohne foregroundServiceType startet Android 14 den
    # Dienst nicht, ohne die Rechte schon gar nicht.
    check("spec hintergrund-service", c.get("app", "services"),
          "ps5proscan:service.py:foreground:sticky:foregroundServiceType=specialUse")
    perms = c.get("app", "android.permissions")
    check("spec foreground-recht", "FOREGROUND_SERVICE" in perms, True)
    check("spec specialUse-recht", "FOREGROUND_SERVICE_SPECIAL_USE" in perms, True)
    # Ohne dieses normale Recht liefert ConnectivityManager keine Antwort und
    # die WLAN-Option wuerde still nichts tun.
    check("spec netzstatus-recht", "ACCESS_NETWORK_STATE" in perms, True)
    check("spec notify-icon",
          "drawable/notify_icon.png" in c.get("app", "android.add_resources"), True)
    # specialUse braucht den Subtyp im Manifest; der p4a-Hook traegt ihn ein.
    check("spec p4a-hook", c.get("app", "p4a.hook"), "tools/p4a_hook.py")
    check("hook-datei vorhanden", os.path.exists(os.path.join(ROOT, "tools", "p4a_hook.py")), True)


def feature_tests():
    """Cache, Groessenlimit und Preisverlauf - die Zutaten fuer 1.1."""
    alt_dir = core._data_dir()
    tmp = tempfile.mkdtemp(prefix="ps5pro-test-")

    class _Antwort:
        def __init__(self, stuecke):
            self.stuecke = stuecke; self.closed = False
        def iter_content(self, n):
            for s in self.stuecke: yield s
        def close(self): self.closed = True

    alt_max = core.MAX_HTML_BYTES
    try:
        core.set_data_dir(tmp); core.reset_http_cache()
        core.MAX_HTML_BYTES = 10
        roh, gross = core._read_capped(_Antwort([b"123456", b"78901"]))
        check("Antwort-Limit greift", gross, True)
        check("Antwort-Limit liefert nichts", roh, None)
        roh, gross = core._read_capped(_Antwort([b"12345"]))
        check("kleine Antwort bleibt", (roh, gross), (b"12345", False))
        core.MAX_HTML_BYTES = alt_max

        # UTF-8 zuerst: ohne Charset im Header dekodiert requests als
        # ISO-8859-1, Umlaute kaemen als "weiÃY" an (e-tec, 17.11.2026).
        class _Seite:
            status_code = 200
            headers = {}
            encoding = "iso-8859-1"
            def __init__(self, body): self.body = body
            def iter_content(self, n): yield self.body
            def close(self): pass
        class _SeiteSession:
            def __init__(self, seite): self.seite = seite
            def get(self, *a, **k): return self.seite

        alt_session = core._session
        try:
            core._session = lambda: _SeiteSession(
                _Seite("<title>PS5 Pro wei\u00df</title>".encode("utf-8")))
            html, fehler, _ = core._try_url("https://shop/utf8", 0)
            check("HTML UTF-8 ohne Charset", (html, fehler),
                  ("<title>PS5 Pro wei\u00df</title>", None))
            core._session = lambda: _SeiteSession(
                _Seite("Preis gr\u00fcn".encode("iso-8859-1")))
            html, fehler, _ = core._try_url("https://shop/latin1", 0)
            check("HTML deklarierte Kodierung", (html, fehler), ("Preis gr\u00fcn", None))
        finally:
            core._session = alt_session

        pfad = os.path.join(tmp, "cache.json")
        c = core.HttpCache(pfad)
        c.put("https://shop/x", {"preis": 799.0, "verfuegbar": True}, "etag-1", None)
        c2 = core.HttpCache(pfad)
        check("Cache ueberlebt Neuladen", c2.get("https://shop/x")["result"]["preis"], 799.0)
        check("Cache speichert ETag", c2.get("https://shop/x")["etag"], "etag-1")
        c2.drop("https://shop/x")
        check("Cache loescht Eintrag", core.HttpCache(pfad).get("https://shop/x"), None)

        # Waehrend eines Scans wird nur im Speicher gepuffert; ein Flush am
        # Ende schreibt alle 42 Eintraege in einem Rutsch.
        batch_pfad = os.path.join(tmp, "batch-cache.json")
        batch = core.HttpCache(batch_pfad)
        batch.put("https://shop/batch", {"preis": 777.0}, persist=False)
        check("Cache puffert ohne Schreiben", core.HttpCache(batch_pfad).get(
            "https://shop/batch"), None)
        check("Cache Flush schreibt", batch.flush(), True)
        check("Cache Flush sichtbar", core.HttpCache(batch_pfad).get(
            "https://shop/batch")["result"]["preis"], 777.0)
        check("Cache Flush nur bei Aenderung", batch.flush(), False)

        # 304 ohne erneutes Parsen: fetch_mit_cache liefert das gespeicherte Ergebnis.
        core.http_cache().put("https://shop/304", {"preis": 749.0, "verfuegbar": True}, "e", None)
        echt = core._try_url
        core._try_url = lambda u, a, p=None: (None, "HTTP 304", {"not_modified": True})
        try:
            _h, _u, cached, _m = core.fetch_mit_cache(["https://shop/304"])
            check("304 nutzt Cache", cached["preis"], 749.0)
        finally:
            core._try_url = echt

        # 304 im force-Pfad: erst 304, dann 200. Das Flag bleibt fuer die
        # 304-Quote erhalten, obwohl die Antwort danach frisch geladen wird.
        aufrufe = {"n": 0}
        def _erst_304(*args, **kwargs):
            aufrufe["n"] += 1
            if aufrufe["n"] == 1:
                return None, "HTTP 304", {"not_modified": True}
            return "<html>ok</html>", None, {"bytes": 4}
        core._try_url = _erst_304
        try:
            _h, _u, _c, meta = core.fetch_mit_cache(
                ["https://shop/304-force"], force=True)
            check("304 force flag", meta.get("not_modified_gesehen"), True)
        finally:
            core._try_url = echt

        # Alter Eintrag ohne Serie wird migriert, gleiche Preise fluten nicht.
        with open(os.path.join(tmp, core.HISTORY_FILE), "w", encoding="utf-8") as f:
            json.dump({"Shop A": {"preis": 800.0, "zeit": "2026-01-01T10:00:00"}}, f)
        hist = core.History()
        check("Serie migriert", len(hist.get_serie("Shop A")), 1)
        hist.update([{"haendler": "Shop A", "klass": "hit", "preis": 800.0}])
        check("gleicher Preis kein Punkt", len(hist.get_serie("Shop A")), 1)
        hist.update([{"haendler": "Shop A", "klass": "hit", "preis": 749.0}])
        check("Preiswechsel neuer Punkt", len(hist.get_serie("Shop A")), 2)
        check("letzter Serienpreis", hist.get_serie("Shop A")[-1][1], 749.0)
        hist.data["Shop A"]["serie"] = [["2026-01-01T10:00:00", 700.0 + i]
                                         for i in range(130)]
        hist.update([{"haendler": "Shop A", "klass": "hit", "preis": 999.0}])
        check("Serie gedeckelt", len(hist.get_serie("Shop A")), core.MAX_SERIE_PUNKTE)

        # Verfuegbarkeit wird auch ohne Preis gespeichert; daraus entsteht der
        # Restock-Alarm, wenn der Shop spaeter wieder liefert.
        hist.update([{"haendler": "Shop B", "klass": "unavail", "preis": None}])
        check("Verfuegbarkeit ausverkauft", hist.get_verfuegbar("Shop B"), False)
        hist.update([{"haendler": "Shop B", "klass": "hit", "preis": 799.0}])
        check("Verfuegbarkeit wieder da", hist.get_verfuegbar("Shop B"), True)
        check("Restock-Ereignis",
              core.alarm_ereignis({"klass": "hit", "preis": 799.0}, 799.0, False),
              "restock")

        # ── Detail A/B: Fensterdauer, Ereignis-Ticker, zuletzt verfuegbar ──
        check("Dauer 0 s", core.dauer_text(0), "0 S")
        check("Dauer 59 s", core.dauer_text(59), "59 S")
        check("Dauer 60 s", core.dauer_text(60), "1 MIN")
        check("Dauer 125 s", core.dauer_text(125), "2 MIN")
        check("Dauer 1 Std", core.dauer_text(3600), "1 STD")
        check("Dauer 1 Std 5 Min", core.dauer_text(3900), "1 STD 5 MIN")
        check("Dauer ohne Wert", core.dauer_text(None), "—")
        check("Dauer unbrauchbar", core.dauer_text("x"), "—")
        check("Kurzzeit", core.kurz_zeit("2026-11-13T10:35:00"), "13.11., 10:35")
        check("Kurzzeit leer", core.kurz_zeit(None), "")
        check("Kurztag", core.kurz_tag("2026-11-13T10:35:00"), "13.11.")
        check("Kurztag unbrauchbar", core.kurz_tag("kaputt"), "")
        # Ein Datum, zwei Zeiten: sonst stand der Tag zweimal in einer Zeile.
        check("Zeitraum gleicher Tag", core.zeitraum_text(
            "2026-11-13T10:35:00", "2026-11-13T10:36:35"),
            "13.11., 10:35 – 10:36")
        check("Zeitraum Tageswechsel", core.zeitraum_text(
            "2026-11-13T23:50:00", "2026-11-14T00:05:00"),
            "13.11., 23:50 – 14.11., 00:05")
        check("Zeitraum ohne Ende",
              core.zeitraum_text("2026-11-13T10:35:00", None), "?")
        check("Zeitraum ohne Werte", core.zeitraum_text(None, None), "")

        # Nur echte Zustandswechsel kommen in den Ringpuffer; beim Wechsel auf
        # ausverkauft traegt der Eintrag die Dauer des abgelaufenen Fensters.
        core.reset_events()
        ev = core.events(); ev.clear()
        hist.update([{"haendler": "Shop E", "klass": "unavail", "preis": None}])
        check("Erstes Sehen ohne Ereignis", ev.all(), [])
        hist.update([{"haendler": "Shop E", "klass": "hit", "preis": 799.0}])
        check("Wechsel zu verfuegbar", [e["typ"] for e in ev.all()], ["verfuegbar"])
        check("Fensterstart notiert", bool(hist.get_zuletzt_verfuegbar("Shop E")), True)
        hist.update([{"haendler": "Shop E", "klass": "hit", "preis": 799.0}])
        check("Kein Ereignis ohne Wechsel", len(ev.all()), 1)
        from datetime import datetime as _dt, timedelta as _td
        hist.data["Shop E"]["verfuegbar_zeit"] = (
            _dt.now() - _td(seconds=95)).isoformat(timespec="seconds")
        hist.update([{"haendler": "Shop E", "klass": "unavail", "preis": None}])
        letzte = ev.all()[-1]
        check("Wechsel zu weg", letzte["typ"], "ausverkauft")
        check("Fensterdauer rund 95 s", abs(int(letzte["dauer"]) - 95) <= 3, True)
        check("Fensterstart im Ereignis", letzte["start"],
              hist.data["Shop E"]["verfuegbar_zeit"])
        check("Zuletzt verfuegbar bleibt stehen",
              hist.get_zuletzt_verfuegbar("Shop E"),
              hist.data["Shop E"]["verfuegbar_zeit"])
        check("Kein ungenutztes Weg-Feld",
              "verfuegbar_weg_zeit" in hist.data["Shop E"], False)
        zeile = core.event_zeile(letzte)
        check("Ticker nennt den Abgang", "WEG · Shop E" in zeile, True)
        check("Ticker nennt die Fensterdauer", "FENSTER 1 MIN" in zeile, True)
        check("Ticker ohne Zeitstempel", core.event_zeile(
            {"typ": "verfuegbar", "haendler": "Shop E"}), "VERFÜGBAR · Shop E")
        hist.update([{"haendler": "Shop E", "klass": "unavail", "preis": 899.0}])
        check("Preis ohne Zustand kein Ereignis", len(ev.all()), 2)

        check("Verlauf je Shop", len(ev.fuer_shop("Shop E")), 2)
        for i in range(core.MAX_EVENTS + 5):
            ev.add({"typ": "verfuegbar", "haendler": f"Ring {i}",
                    "ts": "2026-11-13T10:00:00"})
        check("Ringpuffer gedeckelt", len(ev.all()), core.MAX_EVENTS)
        check("Ringpuffer verwirft die aeltesten", ev.all()[0]["haendler"], "Ring 5")
        check("Neueste zuerst", ev.letzte(1)[0]["haendler"],
              f"Ring {core.MAX_EVENTS + 4}")
        check("Verlauf ueberlebt Neuladen", len(core.Events().all()), core.MAX_EVENTS)
        check("Alte Eintraege fallen aus dem Ring", ev.fuer_shop("Shop E"), [])
        ev.clear()
        check("Verlauf leeren", core.Events().all(), [])
        # Zwei Prozesse: der Dienst schreibt, die App liest nur bei Aenderung.
        a, b = core.Events(), core.Events()
        b.add({"typ": "verfuegbar", "haendler": "Shop Z",
               "ts": "2026-11-13T10:00:00"})
        check("Reload sieht fremdes Ereignis", len(a.reload().all()), 1)
        b.clear()
        a.add({"typ": "verfuegbar", "haendler": "Shop Y",
               "ts": "2026-11-13T10:01:00"})
        check("Add schreibt kein geleertes Ereignis zurueck",
              [e["haendler"] for e in a.all()], ["Shop Y"])
        a.clear()

        # Health: ein Fehler erhoeht den Zaehler, ein Erfolg setzt ihn zurueck.
        core.reset_health()
        hh = core.health()
        hh.record({"haendler": "Shop A", "klass": "challenge",
                   "fehler": "Bot", "dauer": 1.25})
        hh.record({"haendler": "Shop A", "klass": "error", "fehler": "Timeout"})
        check("Health Fehlerzaehler", hh.all()["Shop A"]["fail_streak"], 2)
        check("Health Parserzaehler anfangs leer",
              hh.all()["Shop A"].get("parser_streak", 0), 0)
        hh.record({"haendler": "Shop A", "klass": "parser", "fehler": "Parser"})
        hh.record({"haendler": "Shop A", "klass": "parser", "fehler": "Parser"})
        check("Health wiederholte Parserfehler",
              hh.all()["Shop A"]["parser_streak"], 2)
        check("Health Parserfehler gesamt",
              hh.all()["Shop A"]["parser_total"], 2)
        check("Health Parser zaehlt als Fehler",
              hh.all()["Shop A"]["fail_streak"], 4)
        hh.record({"haendler": "Shop A", "klass": "hit", "preis": 799.0})
        check("Health Erfolg setzt zurueck", hh.all()["Shop A"]["fail_streak"], 0)
        check("Health Parser-Serie nach Erfolg",
              hh.all()["Shop A"]["parser_streak"], 0)
        # Ringpuffer je Shop: Zeit, Status, Fehler und Dauer fuer die
        # nachtraegliche Zuordnung eines verpassten Fensters.
        verlauf = hh.all()["Shop A"]["verlauf"]
        check("Health Verlauf sammelt Pruefungen", len(verlauf), 5)
        check("Health Verlauf Zeitstempel", bool(verlauf[-1].get("ts")), True)
        check("Health Verlauf letzter Status", verlauf[-1].get("status"), "hit")
        check("Health Verlauf Fehlertext", verlauf[0].get("fehler"), "Bot")
        check("Health Verlauf Dauer", verlauf[0].get("dauer"), 1.2)
        check("Health Verlauf Erfolg ohne Fehler", verlauf[-1].get("fehler"),
              None)
        for i in range(core.HEALTH_VERLAUF_MAX + 3):
            hh.record({"haendler": "Shop Ring", "klass": "unavail",
                       "fehler": None, "dauer": i})
        ring = hh.all()["Shop Ring"]["verlauf"]
        check("Health Verlauf gedeckelt", len(ring), core.HEALTH_VERLAUF_MAX)
        check("Health Verlauf verwirft die aeltesten", ring[0]["dauer"], 3.0)
        check("Health Verlauf neueste zuletzt", ring[-1]["dauer"],
              float(core.HEALTH_VERLAUF_MAX + 2))
        hh.save()
        check("Health Verlauf ueberlebt Neuladen",
              len(core.Health(hh.path).all()["Shop Ring"]["verlauf"]),
              core.HEALTH_VERLAUF_MAX)
        core._crash_schreiben("test", "Traceback: Testfehler")
        check("Crash-Log schreibbar", "Testfehler" in core.read_crash_log(), True)
        core.clear_crash_log()

        # Remote-Shop-Liste: nur HTTPS auf bekannten Hosts, Cache wird angewendet.
        alt_urls = {h["name"]: list(h["urls"]) for h in core.HAENDLER}
        alt_parser = {h["name"]: h.get("parser") for h in core.HAENDLER}
        try:
            cfg = {"schema": 1, "shops": {"Amazon DE": {
                "urls": ["https://www.amazon.de/dp/REMOTE-TEST"]}}}
            geprueft = core.validiere_shop_config(cfg)
            check("Remote-Config gueltig", geprueft is not None, True)
            check("Remote-Config wendet URL an",
                  core.wende_shop_config(geprueft), 1)
            amazon = next(h for h in core.HAENDLER if h["name"] == "Amazon DE")
            check("Remote-Config URL gesetzt", amazon["urls"][0].endswith("REMOTE-TEST"), True)
            check("Remote-Config http abgelehnt", core.validiere_shop_config(
                {"schema": 1, "shops": {"Amazon DE": {"urls": ["http://www.amazon.de/x"]}}}), None)
            check("Remote-Config fremder Host abgelehnt", core.validiere_shop_config(
                {"schema": 1, "shops": {"Amazon DE": {"urls": ["https://evil.example/x"]}}}), None)

            # Parser-Regeln: nur literale Marker, kein Regex/Code. Eine Regel
            # darf einen kaputten Preis/Status korrigieren, ohne neues APK.
            regel_cfg = {"schema": 1, "updated": "2026-11-12", "shops": {
                "Amazon DE": {
                    "urls": ["https://www.amazon.de/dp/REMOTE-RULES"],
                    "parser": {
                        "price_before": "data-ps5-price=\"",
                        "price_after": "\"",
                        "in_stock": ["Auf Lager"],
                        "out_of_stock": ["Ausverkauft"],
                        "preorder": ["Vorbestellung"],
                        "immediate": ["Sofort lieferbar"]}}}}
            regel = core.validiere_shop_config(regel_cfg)
            check("Remote-Parser gueltig", regel is not None, True)
            core.wende_shop_config(regel)
            amazon = next(h for h in core.HAENDLER if h["name"] == "Amazon DE")
            rules = amazon.get("parser") or {}
            check("Remote-Parser angewendet", rules.get("price_before"), "data-ps5-price=\"")
            check("Remote-Parser Stock", rules.get("in_stock"), ["Auf Lager"])
            html_rules = ("<h1>PlayStation 5 Pro 2 TB</h1>"
                          "<span data-ps5-price=\"799,00 €\"></span>"
                          "<span>Auf Lager</span>")
            rr = core.remote_parser_ergebnis(html_rules, rules)
            check("Remote-Parser Preis", rr.get("preis"), 799.0)
            check("Remote-Parser verfuegbar", rr.get("verfuegbar"), True)
            check("Remote-Parser Vorbestellung", core.remote_parser_ergebnis(
                html_rules + " Vorbestellung", rules).get("sofort"), False)
            check("Remote-Parser ausverkauft gewinnt", core.remote_parser_ergebnis(
                html_rules + " Ausverkauft", rules).get("verfuegbar"), False)
            check("Remote-Parser sofort", core.remote_parser_ergebnis(
                html_rules + " Sofort lieferbar", rules).get("sofort"), True)
            check("Remote-Parser ohne Treffer", core.remote_parser_ergebnis(
                "<html>nichts</html>", rules), {})

            # Parser-only darf die eingebaute URL nicht veraendern.
            parser_only = core.validiere_shop_config({"schema": 1, "shops": {
                "Amazon DE": {"parser": {"in_stock": ["Lieferbar"]}}}})
            check("Remote-Parser-only gueltig", parser_only is not None, True)
            core.wende_shop_config(parser_only)
            check("Remote-Parser-only URL bleibt", amazon["urls"],
                  core.HAENDLER_BASIS["Amazon DE"])
            core.wende_shop_config({})
            check("Remote-Parser entfernt", amazon.get("parser"), None)

            # Ein geaendertes Regelwerk muss den alten 304-Treffer verwerfen.
            core.reset_http_cache()
            cache = core.http_cache()
            cache.put("https://www.amazon.de/dp/REMOTE-RULES", {"preis": 999.0})
            core.wende_shop_config(regel)
            check("Remote-Parser Cache verworfen",
                  core.http_cache().get("https://www.amazon.de/dp/REMOTE-RULES"), None)

            # End-to-End: scan_einen nutzt die Remote-Regel vor dem Fallback.
            alt_fetch = core.fetch_mit_cache
            try:
                core.fetch_mit_cache = lambda urls, cancel=None, force=False: (html_rules, urls[0], None, {})
                core.reset_http_cache()
                hrr = {"name": "Amazon DE", "land": "DE",
                       "urls": ["https://www.amazon.de/dp/REMOTE-RULES"],
                       "parser": rules}
                srr = core.scan_einen(hrr)
            finally:
                core.fetch_mit_cache = alt_fetch
            check("Remote-Parser Scan-Preis", srr.get("preis"), 799.0)

            # JSON-LD "ausverkauft" darf nicht von einem alten Meta-Tag
            # "InStock" ueberstimmt werden.
            html_meta_konflikt = ('<script type="application/ld+json">'
                                  '{"@type":"Product","name":"Sony PlayStation 5 Pro 2 TB",'
                                  '"offers":{"@type":"Offer","price":"799,00",'
                                  '"availability":"https://schema.org/OutOfStock"}}'
                                  '</script>'
                                  '<meta property="og:availability" '
                                  'content="https://schema.org/InStock">')
            alt_fetch = core.fetch_mit_cache
            try:
                core.fetch_mit_cache = lambda urls, cancel=None, force=False: (
                    html_meta_konflikt, urls[0], None, {})
                core.reset_http_cache()
                r_meta = core.scan_einen({"name": "Amazon DE", "land": "DE",
                                          "urls": ["https://www.amazon.de/dp/META"]})
            finally:
                core.fetch_mit_cache = alt_fetch
            check("JSON-LD vor Meta-Verfuegbarkeit", r_meta.get("klass"), "unavail")
            check("Remote-Parser Scan-Signal", srr.get("signal"), "remote")
            check("Remote-Parser Scan-Treffer", srr.get("klass"), "hit")

            # Grenzen und Struktur: ein Fehler verwirft die ganze Datei.
            ungueltig = [
                ("Parser-Regex abgelehnt", {"schema": 1, "shops": {
                    "Amazon DE": {"parser": {"price_regex": "(.*)"}}}}),
                ("Parser halbes Preisfeld", {"schema": 1, "shops": {
                    "Amazon DE": {"parser": {"price_before": "x"}}}}),
                ("Parser leer", {"schema": 1, "shops": {
                    "Amazon DE": {"parser": {}}}}),
                ("Parser Steuerzeichen", {"schema": 1, "shops": {
                    "Amazon DE": {"parser": {"in_stock": ["x\n"]}}}}),
                ("Parser Marke zu lang", {"schema": 1, "shops": {
                    "Amazon DE": {"parser": {"in_stock": ["x" * 121]}}}}),
                ("Shop unbekanntes Feld", {"schema": 1, "shops": {
                    "Amazon DE": {"urls": ["https://www.amazon.de/x"],
                                  "code": "eval"}}}),
                ("URL mit Port", {"schema": 1, "shops": {
                    "Amazon DE": {"urls": ["https://www.amazon.de:444/x"]}}}),
                ("URL mit Login", {"schema": 1, "shops": {
                    "Amazon DE": {"urls": ["https://u:p@www.amazon.de/x"]}}}),
                ("URL mit Fragment", {"schema": 1, "shops": {
                    "Amazon DE": {"urls": ["https://www.amazon.de/x#frag"]}}}),
                ("URL doppelt", {"schema": 1, "shops": {
                    "Amazon DE": {"urls": ["https://www.amazon.de/x",
                                             "https://www.amazon.de/x"]}}}),
                ("Shop unbekannt", {"schema": 1, "shops": {
                    "Unbekannt": {"urls": ["https://www.amazon.de/x"]}}}),
                ("Schema Bool", {"schema": True, "shops": {}}),
                ("Top-Level unbekannt", {"schema": 1, "shops": {}, "exec": "x"}),
            ]
            for label, bad in ungueltig:
                check("Remote-Config %s" % label,
                      core.validiere_shop_config(bad), None)

            with open(os.path.join(tmp, core.SHOP_CONFIG_FILE), "w", encoding="utf-8") as f:
                json.dump({"ts": 1, "config": cfg}, f)
            check("Remote-Config Cache geladen", core.lade_shop_config(), 1)
        finally:
            for h in core.HAENDLER:
                h["urls"] = alt_urls[h["name"]]
                if alt_parser[h["name"]] is None: h.pop("parser", None)
                else: h["parser"] = alt_parser[h["name"]]

        # Alarm-Regeln: Vorbestellung, Gebrauchtware, Mute, Tiefstpreis, Ruhezeit.
        neu = {"haendler": "Shop A", "preis": 799.0, "condition": "new", "sofort": True}
        check("Alarm normal", core.alarm_erlaubt(neu, None, {}), True)
        check("Alarm Vorbestellung", core.alarm_erlaubt(
            {**neu, "sofort": False}, None, {}), False)
        check("Alarm Gebrauchtware", core.alarm_erlaubt(
            {**neu, "condition": "used"}, None, {}), False)
        check("Alarm Mute", core.alarm_erlaubt(
            neu, None, {"mute_haendler": ["Shop A"]}), False)
        check("Alarm nur Tiefstpreis", core.alarm_erlaubt(
            neu, 749.0, {"notify_low_only": True}), False)
        check("Alarm neuer Tiefstpreis", core.alarm_erlaubt(
            neu, 749.0, {"notify_low_only": False}), True)
        check("Alarm Restock am Tief", core.alarm_erlaubt(
            {**neu, "_restock": True}, 799.0, {"notify_low_only": True}), True)
        check("Alarm-Ereignis neu",
              core.alarm_ereignis({"klass": "hit", "preis": 799.0}, None, None),
              "new")
        check("Alarm-Ereignis gleicher Preis",
              core.alarm_ereignis({"klass": "hit", "preis": 799.0}, 799.0, True),
              None)
        check("Alarm-Ereignis kein Treffer",
              core.alarm_ereignis({"klass": "unavail", "preis": None}, 799.0, False),
              None)
        check("Alarm Ruhezeit", core.alarm_erlaubt(
            neu, None, {"quiet_hours": True}, __import__("datetime").datetime(2026, 1, 1, 23, 30)), False)

        service_q = open(os.path.join(ROOT, "service.py"), encoding="utf-8").read()
        check("Heartbeat next_ts", '"next_ts"' in service_q, True)
        check("Dienst prueft Hot-Shops", "bg_hot_shops" in service_q, True)
        check("Dienst respektiert WLAN-Option", "bg_wlan_only" in service_q, True)
        check("Dienst respektiert Lade-Option", "bg_laden_only" in service_q, True)
        check("Dienst schreibt Wachhund", '"wach_ts"' in service_q, True)
        check("Notification Deep-Link", 'ps5pro_url' in service_q, True)
        check("Notification Gruppe", "setGroupSummary" in service_q, True)
        main_q = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
        check("Deep-Link gelesen", "consume_deep_link" in main_q, True)
        check("Sparkline vorhanden", "class Sparkline" in main_q, True)
        check("30-Tage-Tief", "def tief_30" in main_q, True)
    finally:
        core.MAX_HTML_BYTES = alt_max
        core.set_data_dir(alt_dir); core.reset_http_cache()
        core.reset_health()
        shutil.rmtree(tmp, ignore_errors=True)


def fixture_tests():
    """Kleine, lizenzfreie HTML-Ausschnitte statt kompletter Shop-Seiten."""
    ordner = os.path.join(ROOT, "tools", "fixtures")
    namen = sorted(n for n in os.listdir(ordner) if n.endswith(".json"))
    shop_namen = {h["name"] for h in core.HAENDLER}
    shop_urls = {h["name"]: h["urls"] for h in core.HAENDLER}
    gesehen = []
    check("Fixtures vorhanden", len(namen) >= 5 + len(shop_namen), True)
    for name in namen:
        with open(os.path.join(ordner, name), encoding="utf-8") as f:
            fx = json.load(f)
        if not isinstance(fx, dict) or not isinstance(fx.get("html"), str) \
                or not isinstance(fx.get("expect"), dict):
            check("fixture %s schema" % name, False, True)
            continue
        html, exp = fx["html"], fx["expect"]
        if fx.get("shop") is not None:
            check("fixture %s shop bekannt" % name,
                  fx.get("shop") in shop_namen, True)
            check("fixture %s name passt" % name, fx.get("name"),
                  os.path.splitext(name)[0])
            # Die Fixture muss auf eine aktuell konfigurierte Shop-URL zeigen.
            # Sonst bleibt eine umgezogene URL unbemerkt gruen.
            check("fixture %s URL aktuell" % name,
                  fx.get("url") in shop_urls.get(fx.get("shop"), ()), True)
            gesehen.append(fx.get("shop"))
        if exp.get("challenge"):
            check("fixture %s challenge" % name, core.detect_challenge(html.lower()), True)
            continue
        st = core.extract_structured(html)
        check("fixture %s ist konsole" % name, core.pruefe_nur_konsole(html, st), True)
        # Amazon hat kein JSON-LD; dort prueft die Fixture denselben Pfad wie
        # der Scan (extract_amazon), nicht den generischen Preis-Regex.
        amz = (core.extract_amazon(html)
               if core.ist_amazon(fx.get("url") or "") else {})
        for feld in ("preis", "condition", "seller", "verfuegbar", "sofort"):
            if feld not in exp: continue
            if feld == "verfuegbar":
                wert = (amz["verfuegbar"] if amz.get("verfuegbar") is not None
                        else core.pruefe_verfuegbar(html, st))
            elif feld == "preis" and amz.get("preis") is not None:
                wert = amz["preis"]
            elif feld == "preis" and st.get("preis") is None:
                wert = core.extract_meta_preis(html)
            elif feld == "sofort" and st.get("sofort") is None:
                wert = core.ist_sofort_verfuegbar(html)
            else:
                wert = st.get(feld)
            check("fixture %s %s" % (name, feld), wert, exp[feld])
    check("Fixtures alle Shops", set(gesehen), shop_namen)
    check("Fixtures Shop-Duplikate", len(gesehen), len(set(gesehen)))


def capture_helper_tests():
    """Der Capture-Helfer bleibt offline testbar und schreibt keine Netzdateien."""
    import importlib.util
    pfad = os.path.join(ROOT, "tools", "capture_fixture.py")
    spec = importlib.util.spec_from_file_location("capture_fixture_test", pfad)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    check("Capture Slug", helper.slug("shöpping.at"), "shopping-at")
    slugs = [helper.slug(h["name"]) for h in core.HAENDLER]
    check("Capture Slugs eindeutig", len(slugs), len(set(slugs)))
    shop = next(h for h in core.HAENDLER if h["name"] == "Amazon DE")
    check("Capture Dateiname", helper.fixture_dateiname(shop),
          "shop-amazon-de.json")
    check("Capture URL bekannt", helper.url_erlaubt(shop["urls"][0]), True)
    check("Capture URL fremd", helper.url_erlaubt("https://evil.example/x"), False)

    mini = helper.minimiere_html(HTML_OK)
    check("Capture minimiert JSON-LD", "application/ld+json" in mini, True)
    check("Capture minimiert Preis", helper.erwartung(mini).get("preis"), 799.99)
    fixture = helper.baue_fixture(shop, HTML_OK, shop["urls"][0],
                                  captured="2026-01-01")
    check("Capture Fixture Shop", fixture.get("shop"), "Amazon DE")
    check("Capture Fixture Preis", fixture.get("expect", {}).get("preis"), 799.99)
    check("Capture Fixture Datum", fixture.get("captured"), "2026-01-01")
    check("Capture Fixtures vollstaendig", helper.pruefe_fixtures(), 0)


def adaptive_boot_tests():
    """Responsive Geometrie und Boot-Receiver ohne Android pruefen."""
    g = main.layout_geometrie(420, 820)
    check("Layout Hochformat", g["wide"], False)
    check("Layout Hochformat Panel", g["panel_w"], 420)
    check("Layout Hochformat Panel-Position", g["panel_x"], 0)
    check("Layout Radar-Abstand zur Trefferliste",
          g["radar_bottom"] - (g["panel_y"] + g["results_h"]),
          main.RADAR_PANEL_GAP)

    # Auch auf einem kurzen Telefon muss der Puffer erhalten bleiben.
    g_kurz = main.layout_geometrie(420, 480)
    check("Layout Radar-Abstand kurz",
          g_kurz["radar_bottom"] - (g_kurz["panel_y"] + g_kurz["results_h"]),
          main.RADAR_PANEL_GAP)

    g = main.layout_geometrie(1280, 800)
    check("Layout Tablet quer", g["wide"], True)
    check("Layout Tablet zwei Spalten", g["panel_x"] + g["panel_w"], 1280)
    check("Layout Tablet Panel gedeckelt", g["panel_w"] <= 460, True)
    check("Layout Tablet Trefferflaeche", g["results_h"] >= 240, True)

    # Im Querformat muss zwischen Radar und Trefferliste derselbe Puffer
    # liegen wie im Hochformat; sonst schneidet die Liste den Radar an.
    check("Layout Tablet Radar-Abstand zur Liste",
          g["panel_x"] - g["radar_w"], main.RADAR_PANEL_GAP)
    fl = main.radar_flaeche(g["radar_w"], 800, g["radar_bottom"], g["radar_top"])
    check("Layout Tablet Radar-Scheibe", fl is not None, True)
    if fl is not None:
        # Aussenring, Gradzahl (11 dp Abstand) und halbe Labelbreite (12 dp)
        # bleiben links von der Trefferliste.
        check("Layout Tablet Radar frei von der Liste",
              fl["cx"] + fl["mr"] + main.dp(11) + main.dp(12) <=
              g["panel_x"] + 0.5, True)

    # Treffer-Marken bleiben im Radar: Pulsring und Zielmarke duerfen den
    # Aussenring und die Gradzahlen nicht beruehren.
    for mr in (main.dp(46), main.dp(90), main.dp(180), main.dp(320)):
        marke = main.radar_treffer_radius(mr)
        for bx0, by0 in ((0.0, 0.0), (0.84, 0.0), (0.6, 0.6),
                         (-0.84, 0.0), (0.0, -0.84), (0.3, -0.7)):
            bx, by = main.radar_treffer_xy({"x": bx0, "y": by0}, 0.0, 0.0, mr)
            abstand = math.hypot(bx, by)
            check(f"Radar-Treffer {int(mr)}dp ({bx0}/{by0}) im Ring",
                  abstand <= mr - marke - main.dp(2) + 0.01, True)
            if abstand > 0.5:
                check(f"Radar-Treffer {int(mr)}dp ({bx0}/{by0}) Richtung",
                      round(math.degrees(math.atan2(by, bx)), 6),
                      round(math.degrees(math.atan2(by0, bx0)), 6))

    check("Layout Foldable quer", main.layout_geometrie(884, 700)["wide"], True)
    check("Layout Tablet hoch bleibt einspaltig",
          main.layout_geometrie(800, 1280)["wide"], False)

    # Flaches Querformat unter 480 dp Hoehe (z. B. 620x380): Radar und
    # Trefferliste muessen beide sichtbar bleiben. Vorher lag die Scheibe
    # unter Logo und Leiste und verschwand komplett.
    for lw, lh in ((620, 380), (640, 360), (720, 360), (800, 360), (720, 480)):
        name = f"{lw}x{lh}"
        bg = main.layout_geometrie(lw, lh)
        check(f"Layout {name}: zwei Spalten", bg["wide"], True)
        check(f"Layout {name}: Liste hoch genug", bg["results_h"] >= main.dp(200), True)
        fl = main.radar_flaeche(bg["radar_w"], lh, bg["radar_bottom"], bg["radar_top"])
        check(f"Layout {name}: Radar sichtbar", fl is not None, True)
        if fl is not None:
            check(f"Layout {name}: Radar-Radius", fl["mr"] >= main.dp(60), True)
            check(f"Layout {name}: Radar frei von der Liste",
                  fl["cx"] + fl["mr"] + main.dp(11) + main.dp(12) <=
                  bg["panel_x"] + 0.5, True)

    # Auf dem Geraet kosten Status- und Navigationsleiste zusaetzlich Hoehe.
    # Auch damit muss das flache Querformat zweispaltig bleiben und die
    # Radarflaeche gross genug sein.
    for lw, lh, ti, bi in ((620, 380, 24, 24), (640, 360, 32, 32),
                           (800, 360, 24, 24)):
        name = f"{lw}x{lh}+{ti}/{bi}"
        bg = main.layout_geometrie(lw, lh, top_in=ti, bottom_in=bi)
        check(f"Layout {name}: zwei Spalten", bg["wide"], True)
        check(f"Layout {name}: Liste im Fenster",
              bg["panel_y"] + bg["results_h"] <= lh + 0.5, True)
        fl = main.radar_flaeche(bg["radar_w"], lh, bg["radar_bottom"], bg["radar_top"])
        check(f"Layout {name}: Radar sichtbar", fl is not None, True)
        if fl is not None:
            check(f"Layout {name}: Radar-Radius", fl["mr"] >= main.dp(60), True)

    # Kleine Displays und Querformat: Panel, Logo, Bedienleiste und Radar
    # duerfen sich nicht ueberlagern; im Hochformat bleibt der Radar-Puffer
    # auch bei der kuerzesten unterstuetzten Hoehe erhalten.
    for lw, lh in ((320, 240), (320, 480), (360, 640), (420, 480),
                    (480, 320), (620, 380), (640, 360), (720, 360), (800, 360),
                    (420, 820), (884, 700)):
        bg = main.layout_geometrie(lw, lh)
        name = f"{lw}x{lh}"
        rechts = bg["panel_x"] + bg["panel_w"]
        oben = bg["panel_y"] + bg["results_h"]
        check(f"Layout {name}: Panel im Fenster",
              bg["panel_x"] >= 0 and rechts <= lw + 0.5 and
              bg["panel_y"] >= bg["controls_h"] - 0.5 and oben <= lh + 0.5,
              True)
        if bg["wide"]:
            logo_frei = bg["panel_x"] >= bg["logo_w"] - 0.5
        else:
            logo_frei = oben <= lh - bg["logo_h"] + 0.5
        check(f"Layout {name}: Panel ueberlappt Logo nicht", logo_frei, True)
        if not bg["wide"]:
            check(f"Layout {name}: Radar-Abstand",
                  bg["radar_bottom"] - oben, main.RADAR_PANEL_GAP)
        else:
            check(f"Layout {name}: Radar-Abstand zur Liste",
                  bg["panel_x"] - bg["radar_w"], main.RADAR_PANEL_GAP)

    g = main.layout_geometrie(1280, 800, top_in=40, bottom_in=20,
                              left_in=30, right_in=50)
    check("Layout rechte Insets", g["panel_x"] + g["panel_w"], 1230)
    check("Layout linke Insets", g["panel_x"] >= 30, True)

    spec = open(os.path.join(ROOT, "buildozer.spec"), encoding="utf-8").read()
    check("Boot-Permission", "RECEIVE_BOOT_COMPLETED" in spec, True)
    check("Boot-Java-Quelle", "android.add_src = android_src" in spec, True)
    check("Querformat erlaubt", "orientation = all" in spec, True)
    java = open(os.path.join(ROOT, "android_src", "de", "ps5pro",
                             "ps5prosearchagent", "BootReceiver.java"),
                encoding="utf-8").read()
    check("BootReceiver-Klasse",
          "public class BootReceiver extends BroadcastReceiver" in java, True)
    check("BootReceiver-Action", "ACTION_BOOT_COMPLETED" in java, True)
    check("BootReceiver-Service", "ServicePs5proscan.start" in java, True)
    check("BootReceiver-AUTO-Guard", 'optBoolean("auto_scan", false)' in java, True)
    check("BootReceiver-Update", "ACTION_MY_PACKAGE_REPLACED" in java, True)

    # Hook wirklich gegen ein synthetisches Manifest laufen lassen: so faellt
    # ein ungueltiger Receiver-Eintrag vor dem 40-Minuten-Build auf.
    import importlib.util
    import xml.etree.ElementTree as ET
    hp = os.path.join(ROOT, "tools", "p4a_hook.py")
    hs = importlib.util.spec_from_file_location("p4a_hook_test", hp)
    hook = importlib.util.module_from_spec(hs); hs.loader.exec_module(hook)
    manifest = (
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        '<application>'
        '<service android:name="de.ps5pro.ps5prosearchagent.ServicePs5proscan" />'
        '</application></manifest>')
    neu = hook.erweitere_manifest(manifest)
    ET.fromstring(neu)
    check("Manifest BootReceiver", ".BootReceiver" in neu, True)
    check("Manifest BootAction", "android.intent.action.BOOT_COMPLETED" in neu, True)
    check("Manifest specialUse", "PROPERTY_SPECIAL_USE_FGS_SUBTYPE" in neu, True)
    check("Manifest idempotent", hook.erweitere_manifest(neu).count(".BootReceiver"), 1)


def v13_tests():
    """Webhook-Alarme, Treffer-Verifikation und Schnell-Modus (v1.3)."""
    check("Webhook erkennt ntfy", core.webhook_preset("https://ntfy.sh/mein-topic"), "ntfy")
    check("Webhook erkennt Telegram",
          core.webhook_preset("https://api.telegram.org/botT/sendMessage?chat_id=1"),
          "telegram")
    check("Webhook erkennt Discord",
          core.webhook_preset("https://discord.com/api/webhooks/1/abc"), "discord")
    check("Webhook unbekannt generisch",
          core.webhook_preset("https://example.com/hook"), "generisch")

    # Tokens stecken in Pfad oder Query und duerfen nie im Log/Toast landen.
    geheim = core.redact_url("https://ntfy.sh/geheimer-topic-123")
    check("Webhook-Redaction Host", geheim, "https://ntfy.sh/…")
    check("Webhook-Redaction ohne Token", "geheimer" in geheim, False)
    check("Webhook-Redaction mit Query",
          core.redact_url("https://example.com/a?token=abc"), "https://example.com/…")

    body, hd = core.webhook_nachricht("ntfy", "TITEL", "TEXT", "https://shop/x")
    check("ntfy Body", body, "TITEL\nTEXT")
    check("ntfy Title", hd.get("Title"), "TITEL")
    check("ntfy Click", hd.get("Click"), "https://shop/x")
    body, hd = core.webhook_nachricht("discord", "T", "X", "https://shop/x")
    check("Discord JSON", json.loads(body)["content"], "T\nX\nhttps://shop/x")
    check("Discord Header", "application/json" in hd.get("Content-Type", ""), True)
    body, _ = core.webhook_nachricht("generisch", "T", "X", "https://shop/x")
    check("Generisch JSON", json.loads(body), {"titel": "T", "text": "X",
                                                "url": "https://shop/x"})

    class _Resp:
        def __init__(self, code): self.status_code = code
    calls = []
    def post_ok(url, data=None, headers=None, timeout=None):
        calls.append(url); return _Resp(204)
    ok, info = core.webhook_senden("https://ntfy.sh/t", titel="T", text="X",
                                   pause=0, post=post_ok)
    check("Webhook sendet", ok, True)
    check("Webhook Status", info, "HTTP 204")
    calls.clear()
    ok, info = core.webhook_senden("http://ntfy.sh/t", pause=0, post=post_ok)
    check("Webhook nur HTTPS", ok, False)
    check("Webhook HTTPS Text", info, "nur HTTPS")
    calls.clear()
    ok, info = core.webhook_senden("https://ntfy.sh/t", pause=0,
                                   post=lambda *a, **k: (calls.append(1), _Resp(400))[1])
    check("Webhook 4xx kein Retry", (ok, len(calls)), (False, 1))
    calls.clear()
    ok, info = core.webhook_senden("https://ntfy.sh/t", pause=0,
                                   post=lambda *a, **k: (calls.append(1), _Resp(503))[1])
    check("Webhook 5xx ein Retry", (ok, len(calls)), (False, 2))

    core.reset_webhook_dedupe()
    check("Webhook Dedupe erst", core.webhook_dedupe("Amazon DE", 799), True)
    check("Webhook Dedupe zweit", core.webhook_dedupe("Amazon DE", 799), False)
    check("Webhook Dedupe anderer Preis", core.webhook_dedupe("Amazon DE", 819), True)
    check("Webhook Dedupe Restock", core.webhook_dedupe("Amazon DE", 799, True), True)
    check("Webhook Dedupe abgelaufen",
          core.webhook_dedupe("Amazon DE", 799, jetzt=time.time() + 601), True)
    core.reset_webhook_dedupe()

    treffer = {"klass": "hit", "preis": 799.0, "haendler": "Amazon DE"}
    check("Verify gleicher Preis",
          core.verify_entscheidung(treffer, {"klass": "hit", "preis": 799.0}),
          "bestaetigt")
    check("Verify anderer Preis",
          core.verify_entscheidung(treffer, {"klass": "hit", "preis": 819.0}),
          "geaendert")
    check("Verify ausverkauft",
          core.verify_entscheidung(treffer, {"klass": "unavail", "preis": None}), "weg")
    check("Verify Bot-Schutz",
          core.verify_entscheidung(treffer, {"klass": "challenge", "preis": None}),
          "unbestaetigt")
    check("Verify ohne Antwort", core.verify_entscheidung(treffer, None), "unbestaetigt")
    check("Verify kein Treffer", core.verify_entscheidung({"klass": "unavail"}, treffer), None)

    alt_scan = core.scan_einen
    gesehen = {}
    try:
        def fake_scan(h, cancel=None, force=False):
            gesehen["force"] = force
            return {"klass": "unavail", "preis": None}
        core.scan_einen = fake_scan
        r = dict(treffer)
        core.verify_treffer({"name": "Amazon DE", "urls": ["https://x"]}, r, pause=0)
        check("Verify zweiter Abruf ohne Cache", gesehen.get("force"), True)
        check("Verify stuft weg", (r.get("klass"), r.get("verify")), ("unavail", "weg"))
        core.scan_einen = lambda h, cancel=None, force=False: {"klass": "hit", "preis": 799.0}
        r = dict(treffer)
        core.verify_treffer({"name": "Amazon DE", "urls": ["https://x"]}, r, pause=0)
        check("Verify bestaetigt", r.get("verify"), "bestaetigt")
    finally:
        core.scan_einen = alt_scan

    class _S:
        def __init__(self, **kw): self.d = kw
        def get(self, k, d=None): return self.d.get(k, d)
    r = {"klass": "hit", "preis": 799.0, "haendler": "Amazon DE",
         "sofort": True, "condition": "new"}
    s_aus = _S(alarm_nur_bestaetigt=False)
    s_an = _S(alarm_nur_bestaetigt=True)
    check("Alarm ohne Verifikation erlaubt", core.alarm_erlaubt(dict(r), None, s_aus), True)
    check("Alarm nur bestaetigt blockt ungeprueft",
          core.alarm_erlaubt(dict(r), None, s_an), False)
    check("Alarm nur bestaetigt laesst bestaetigt durch",
          core.alarm_erlaubt({**r, "verify": "bestaetigt"}, None, s_an), True)
    check("Alarm nur bestaetigt blockt weg",
          core.alarm_erlaubt({**r, "verify": "weg"}, None, s_an), False)

    aktiv = {"Amazon DE", "Otto DE", "PS Direct DE", "Unbekannt"}
    hot = core.schnellscan_haendler(core.HAENDLER, aktiv)
    check("Schnellscan nur aktive Hot-Shops",
          sorted(h["name"] for h in hot), ["Amazon DE", "Otto DE"])
    check("Schnellscan ohne Auswahl",
          len(core.schnellscan_haendler(core.HAENDLER)), len(core.HOT_SHOPS))
    check("Schnellscan unbekannter Shop ignoriert",
          all(h["name"] in {x["name"] for x in core.HAENDLER}
              for h in core.schnellscan_haendler(core.HAENDLER)), True)

    main_q = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    svc_q = open(os.path.join(ROOT, "service.py"), encoding="utf-8").read()
    check("App sendet Webhook", "sende_webhook_alarm" in main_q, True)
    check("App verifiziert Treffer", "verify_treffer(futs[f]" in main_q, True)
    check("App zeigt Verifikation", "VERIFIKATION" in main_q, True)
    check("App hat Schnellscan", "SCHNELLSCAN" in main_q, True)
    check("App teilt Health-Export", "health_export_json" in main_q, True)
    check("Health-Export Knopf", "JSON TEILEN" in main_q, True)
    check("Dienst sendet Webhook", "sende_webhook_alarm" in svc_q, True)
    check("Dienst verifiziert Treffer", "verify_treffer" in svc_q, True)


def v14_tests():
    """Verfuegbarkeitszustaende, Konfidenz und Beleg - die v1.4-Basis."""
    check("v1.4 state InStock", core.availability_state("https://schema.org/InStock"),
          "in_stock")
    check("v1.4 state InStoreOnly",
          core.availability_state("https://schema.org/InStoreOnly"), "pickup_only")
    check("v1.4 state OnlineOnly wie InStock",
          core.availability_state("https://schema.org/OnlineOnly"), "in_stock")
    check("v1.4 state LimitedAvailability wie InStock",
          core.availability_state("https://schema.org/LimitedAvailability"), "in_stock")
    check("v1.4 state Discontinued wie SoldOut",
          core.availability_state("https://schema.org/Discontinued"), "sold_out")
    check("v1.4 state PreOrder",
          core.availability_state("https://schema.org/PreOrder"), "preorder")
    check("v1.4 state BackOrder",
          core.availability_state("https://schema.org/BackOrder"), "backorder")
    check("v1.4 state SoldOut",
          core.availability_state("https://schema.org/SoldOut"), "sold_out")
    check("v1.4 InStoreOnly nicht sofort",
          core._availability_flags("https://schema.org/InStoreOnly"), (True, False))
    check("v1.4 Chance-Klasse", core.classify(True, 799.0, 900.0, "pickup_only"),
          "chance")
    check("v1.4 InStock bleibt Treffer",
          core.classify(True, 799.0, 900.0, "in_stock"), "hit")
    check("v1.4 Lotterie erkannt",
          core.chance_aus_text("Teilnahme nur per Lotterie moeglich"), "lottery")
    check("v1.4 Gewinnspiel allein keine Chance",
          core.chance_aus_text("Gewinnspiel im Footer"), None)
    check("v1.4 Vorbestellung bleibt Treffer",
          core.classify(True, 799.0, 900.0, "preorder"), "hit")
    check("v1.4 2. Abruf wird Chance",
          core.verify_entscheidung(
              {"klass":"hit","preis":799.0},
              {"klass":"chance","preis":799.0,"avail_state":"pickup_only"}),
          "chance")
    check("v1.4 Einladung erkannt",
          core.chance_aus_text("Nur mit Einladung bestellbar"), "invite")
    check("v1.4 Marktabholung erkannt",
          core.chance_aus_text("Nur im Markt abholbar"), "pickup_only")

    st = core.extract_structured(HTML_OK.replace("InStock", "InStoreOnly"))
    check("v1.4 JSON-LD Zustand", st.get("state"), "pickup_only")
    check("v1.4 JSON-LD Markt nicht sofort", st.get("sofort"), False)
    st_gtin = core.extract_structured(HTML_OK.replace(
        '"name":', '"gtin13":"0711719570280","name":'))
    check("v1.4 GTIN gelesen", st_gtin.get("gtin"), "0711719570280")
    check("v1.4 Bundle abgelehnt", core.extract_structured(
        HTML_OK.replace("(E-Chassis)", "Bundle mit Controller"))["ist_konsole"], False)

    basis = {"klass": "hit", "preis": 799.0, "avail_state": "in_stock",
             "stock_source": "jsonld", "condition": "new", "marketplace": False,
             "gtin": "0711719570280", "fresh": True}
    check("v1.4 Konfidenz ungeprueft", core.berechne_konfidenz(dict(basis)), 60)
    ohne_zustand={k:v for k,v in basis.items() if k!="condition"}
    check("v1.4 Konfidenz ohne Zustand",
          core.berechne_konfidenz(ohne_zustand), 50)
    check("v1.4 Konfidenz bestaetigt",
          core.berechne_konfidenz({**basis, "verify": "bestaetigt"}), 100)
    check("v1.4 Chance gedeckelt",
          core.berechne_konfidenz({**basis, "klass": "chance"}), 60)

    beleg = core.beleg_erzeugen("<html><body>PS5 Pro 2 TB · 799,00 € · Auf Lager</body></html>",
                                799.0, "in_stock")
    check("v1.4 Beleg Preis", beleg.get("preis"), 799.0)
    check("v1.4 Beleg Hash", len(beleg.get("hash") or ""), 16)
    check("v1.4 Beleg Ausschnitt", "799,00" in (beleg.get("excerpt") or ""), True)
    check("v1.4 Beleg kurz", len(beleg.get("excerpt") or "") <= 120, True)

    tmp = tempfile.mkdtemp(prefix="ps5pro-v14-")
    try:
        ev = core.Evidence(os.path.join(tmp, "evidence.json"))
        ev.put("Shop A", beleg)
        check("v1.4 Beleg gespeichert", ev.get("Shop A").get("hash"), beleg["hash"])
        c = core.HttpCache(os.path.join(tmp, "cache.json"))
        c.put("https://shop/v14", {"preis": 799.0}, "etag", None)
        check("v1.4 Cache Zeitstempel", float(c.get("https://shop/v14")["ts"]) > 0, True)

        alt_dir = core._data_dir()
        alt_try = core._try_url
        try:
            core.set_data_dir(tmp); core.reset_http_cache()
            chance_html = HTML_OK.replace("InStock", "InStoreOnly")
            core._try_url = lambda u, a, p=None: (chance_html, None, {})
            r = core.scan_einen({"name": "Markt Shop", "land": "DE",
                                 "urls": ["https://example.invalid/markt"]})
            check("v1.4 Scan Chance", (r or {}).get("klass"), "chance")
            check("v1.4 Scan Zustand", (r or {}).get("avail_state"), "pickup_only")
            check("v1.4 Scan nicht sofort", (r or {}).get("sofort"), False)
            check("v1.4 Scan Beleg", bool((r or {}).get("beleg")), True)
        finally:
            core._try_url = alt_try; core.set_data_dir(alt_dir)

        class _S:
            def __init__(self, **kw): self.d = kw
            def get(self, k, d=None): return self.d.get(k, d)
        chance = {"klass": "chance", "preis": 799.0, "haendler": "Markt Shop"}
        check("v1.4 Chance kein Alarm",
              core.alarm_erlaubt(chance, None, _S()), False)
        ruhig = {"klass": "hit", "preis": 799.0, "haendler": "Shop A",
                 "sofort": True, "condition": "new", "confidence": 60}
        check("v1.4 Konfidenz-Schwelle blockt",
              core.alarm_erlaubt(ruhig, None, _S(confidence_min=70)), False)
        check("v1.4 Konfidenz-Schwelle laesst durch",
              core.alarm_erlaubt({**ruhig, "confidence": 90}, None,
                                 _S(confidence_min=70)), True)
        vor = {"klass": "hit", "preis": 799.0, "haendler": "Shop V",
               "sofort": False, "condition": "new", "avail_state": "preorder"}
        check("v1.4 Vorbestellung mit NUR SOFORT AUS",
              core.alarm_erlaubt(vor, None, _S(notify_sofort=False)), True)
        check("v1.4 Vorbestellung standardmaessig still",
              core.alarm_erlaubt(vor, None, _S()), False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def play_rebrand_tests():
    """Play-Kanal getrennt vom Sideload-Kanal pruefen."""
    import branding

    sid = configparser.ConfigParser(interpolation=None)
    sid.read(os.path.join(ROOT, "buildozer.spec"), encoding="utf-8")
    play = configparser.ConfigParser(interpolation=None)
    play.read(os.path.join(ROOT, "buildozer.play.spec"), encoding="utf-8")

    check("Sideload-Titel unveraendert", sid.get("app", "title"),
          "PS5 Pro Search Agent")
    check("Sideload-Package unveraendert",
          sid.get("app", "package.domain") + "." + sid.get("app", "package.name"),
          "de.ps5pro.ps5prosearchagent")
    check("Play-Titel neutral", play.get("app", "title"),
          "Konsolen-Radar – Preisalarm")
    check("Play-Package neutral",
          play.get("app", "package.domain") + "." + play.get("app", "package.name"),
          "de.konsolenradar.app")
    check("Play-AAB aktiv", play.get("app", "android.release_artifact"), "aab")
    check("Play-BootReceiver", os.path.isfile(os.path.join(
        ROOT, "android_src_play", "de", "konsolenradar", "app",
        "BootReceiver.java")), True)
    check("Play-Branding-Paket", branding.PLAY_PACKAGE, "de.konsolenradar.app")
    check("Play-Branding-Titel", branding.PLAY_TITLE, "Konsolen-Radar – Preisalarm")
    check("Sideload-Service bleibt alt",
          branding.labels("sideload")["channel_id"], "ps5pro_hits")
    check("Play-Service neutral",
          branding.labels("play")["channel_id"], "console_radar_hits")

    from struct import unpack

    def size(rel):
        with open(os.path.join(ROOT, rel), "rb") as f:
            kopf = f.read(24)
        return unpack(">II", kopf[16:24])

    check("Store-Icon 512", size("store/assets/icon-512.png"), (512, 512))
    check("Feature-Grafik", size("store/assets/feature-1024x500.png"), (1024, 500))
    shots = sorted(os.listdir(os.path.join(ROOT, "store", "assets", "phone")))
    shots = [n for n in shots if n.lower().endswith(".png")]
    check("Store-Screenshots", len(shots) >= 2, True)


def live_tests():
    """Live-Taktung (v1.5): Intervalle, Faelligkeit, Budget, Fairness."""
    # 20:00 Ortszeit: ausserhalb aller Drop-Fenster, sonst kippt der Takt.
    jetzt = time.mktime((2026, 11, 16, 20, 0, 0, 0, 0, -1))

    def nah(wert, ziel):
        return abs(wert - ziel) <= ziel * core.LIVE_JITTER + 1

    daten = {
        "Heiss DE": {"last_status": "hit", "last_ts": jetzt - 40,
                     "checks": 10, "successes": 9, "fail_streak": 0},
        "Still DE": {"last_status": "unavail", "last_ts": jetzt - 10,
                     "checks": 5, "successes": 5, "fail_streak": 0},
        "Sperre DE": {"last_status": "challenge", "last_ts": jetzt - 60,
                      "checks": 4, "successes": 3, "fail_streak": 1},
        "Kaputt DE": {"last_status": "parser", "last_ts": jetzt - 100,
                      "checks": 6, "successes": 4, "fail_streak": 2},
        "Einmal DE": {"last_status": "parser", "last_ts": jetzt - 100,
                      "checks": 2, "successes": 1, "fail_streak": 1},
    }
    check("Live heiss 30 s",
          nah(core.shop_intervall("Heiss DE", daten, jetzt), core.LIVE_HEISS_S), True)
    check("Live normal 240 s",
          nah(core.shop_intervall("Still DE", daten, jetzt), core.LIVE_NORMAL_S), True)
    check("Live Sperre 600 s",
          nah(core.shop_intervall("Sperre DE", daten, jetzt), core.LIVE_RUHE_S), True)
    check("Live Fehlerserie 720 s",
          nah(core.shop_intervall("Kaputt DE", daten, jetzt), core.LIVE_GESTOERT_S), True)
    check("Live einzelner Parserfehler bleibt normal",
          nah(core.shop_intervall("Einmal DE", daten, jetzt), core.LIVE_NORMAL_S), True)
    check("Live unbekannter Shop normal",
          nah(core.shop_intervall("Nirgends DE", daten, jetzt), core.LIVE_NORMAL_S), True)
    check("Live Sperre schlaegt Trefferzustand",
          core.shop_intervall("Sperre DE",
                              {"Sperre DE": {"last_status": "challenge",
                                             "last_ts": jetzt, "fail_streak": 0}},
                              jetzt) > core.LIVE_HEISS_S, True)
    check("Live Jitter stabil",
          core.shop_intervall("Heiss DE", daten, jetzt),
          core.shop_intervall("Heiss DE", daten, jetzt))
    alle = [core.shop_intervall(h["name"], {}, jetzt) for h in core.HAENDLER]
    check("Live Jitter im Band",
          all(core.LIVE_NORMAL_S * (1 - core.LIVE_JITTER) <= v
              <= core.LIVE_NORMAL_S * (1 + core.LIVE_JITTER) + 1 for v in alle), True)

    sh = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    due = {"A": {"last_status": "unavail", "last_ts": jetzt - 1000},
           "B": {"last_status": "unavail", "last_ts": jetzt - 300},
           "C": {"last_status": "unavail", "last_ts": jetzt - 5}}
    check("Live nur faellige Shops",
          [h["name"] for h in core.faellige_haendler(sh, due, jetzt)], ["A", "B"])
    check("Live ueberfaelligste zuerst",
          [h["name"] for h in core.faellige_haendler(sh, due, jetzt)][0], "A")
    check("Live Rundengroesse deckelt",
          [h["name"] for h in core.faellige_haendler(sh, due, jetzt, budget=1)], ["A"])
    check("Live Auswahl filtert",
          [h["name"] for h in core.faellige_haendler(sh, due, jetzt, aktiv={"B"})],
          ["B"])
    check("Live ohne Health alle faellig",
          len(core.faellige_haendler(sh, {}, jetzt)), 3)
    check("Live Budget null wird eins",
          len(core.faellige_haendler(sh, {}, jetzt, budget=0)), 1)

    # Fairness: 42 Shops, 5 pro Runde, 20-s-Takt - kein Shop bleibt liegen.
    gesund = {}
    gesehen = set()
    t = jetzt
    for _ in range(60):
        for h in core.faellige_haendler(core.HAENDLER, gesund, t, budget=5):
            gesehen.add(h["name"])
            e = gesund.setdefault(h["name"], {"checks": 0, "successes": 0})
            e["last_status"] = "unavail"; e["last_ts"] = t
            e["checks"] += 1; e["successes"] += 1
        t += core.LIVE_TAKT
    check("Live kein Shop verhungert", len(gesehen), len(core.HAENDLER))

    ueb = core.health_uebersicht(daten, jetzt)
    check("Health-Quote", ueb["Heiss DE"]["quote"], 90.0)
    check("Health-Status", ueb["Sperre DE"]["status"], "challenge")
    check("Health-Alter", ueb["Heiss DE"]["alter"], 40)
    check("Health kennt nur Gesehenes", "Nirgends DE" in ueb, False)

    # Export fuer den Abgleich mit bestell.bar: Health, Ereignisse und
    # BG-Status in einem JSON, rein lesend und ohne Scan.
    export_ts = time.mktime((2026, 11, 16, 9, 2, 0, 0, 0, -1))
    export_daten = core.health_export(
        health_daten=daten,
        event_liste=[{"typ": "verfuegbar", "haendler": "Heiss DE",
                      "ts": "2026-11-16T09:02:00"}],
        bg_status={"ts": export_ts, "zeit": "09:02", "geprueft": 42,
                   "results": []},
        jetzt=export_ts)
    check("Export Schema", export_daten["schema"], 1)
    check("Export Health", export_daten["health"]["Heiss DE"]["last_status"],
          "hit")
    check("Export Events", len(export_daten["events"]), 1)
    check("Export BG", export_daten["bg"]["geprueft"], 42)
    check("Export BG Zeit lesbar", export_daten["bg"].get("ts_iso"),
          "2026-11-16T09:02:00")
    check("Export Zeitstempel", export_daten["exportiert"],
          "2026-11-16T09:02:00")
    check("Export Quellen", export_daten["dateien"]["bg"], core.BG_STATUS_FILE)
    roh = core.health_export_json(health_daten=daten, event_liste=[],
                                  bg_status={}, jetzt=export_ts)
    geparst = json.loads(roh)
    check("Export JSON parsebar", geparst["schema"], 1)
    check("Export JSON Zeitzone", bool(geparst["zeitzone"]), True)
    check("Export JSON BG ohne Zeit", geparst["bg"].get("ts_iso"), None)

    # ── Drop-Fenster ────────────────────────────────────────────────
    # Belegt ist nur ein breites Tagesfenster fuer PS Direct (09:00-18:00);
    # fuer MediaMarkt/Saturn gibt es keine belastbare Uhrzeit.
    def ts(h, m):
        return time.mktime((2026, 11, 16, h, m, 0, 0, 0, -1))

    check("Fenster PS Direct 09:30", core.im_drop_fenster("PS Direct DE", ts(9, 30)), True)
    check("Fenster PS Direct 08:30 davor", core.im_drop_fenster("PS Direct DE", ts(8, 30)), False)
    check("Fenster PS Direct 18:00 Rand", core.im_drop_fenster("PS Direct DE", ts(18, 0)), True)
    check("Fenster PS Direct 18:30 danach", core.im_drop_fenster("PS Direct DE", ts(18, 30)), False)
    check("Fenster PS Direct AT wie DE",
          core.im_drop_fenster("PS Direct AT", ts(14, 0)), True)
    check("Fenster MM ohne belegte Uhrzeit", "MediaMarkt DE" not in core.DROP_FENSTER, True)
    check("Fenster MM 09:30 kein Takt",
          core.im_drop_fenster("MediaMarkt DE", ts(9, 30)), False)
    check("Fenster Saturn kein Takt", core.im_drop_fenster("Saturn AT", ts(9, 30)), False)
    check("Fenster Shop ohne Zeitplan", core.im_drop_fenster("Amazon DE", ts(10, 0)), False)
    check("Fenster unbekannter Shop", core.im_drop_fenster("Nirgends DE", ts(10, 0)), False)
    try:
        core.DROP_FENSTER["Nacht DE"] = ((23, 30, 0, 30),)
        check("Fenster ueber Mitternacht", core.im_drop_fenster("Nacht DE", ts(23, 50)), True)
        check("Fenster ueber Mitternacht frueh", core.im_drop_fenster("Nacht DE", ts(0, 10)), True)
        check("Fenster ueber Mitternacht aussen", core.im_drop_fenster("Nacht DE", ts(1, 0)), False)
    finally:
        core.DROP_FENSTER.pop("Nacht DE", None)

    im_fenster = {"PS Direct DE": {"last_status": "hit", "last_ts": ts(9, 59)}}
    check("Intervall im Fenster 10 s",
          nah(core.shop_intervall("PS Direct DE", im_fenster, ts(10, 0)),
              core.LIVE_FENSTER_S), True)
    check("Intervall nachmittags im Fenster",
          nah(core.shop_intervall("PS Direct DE", im_fenster, ts(15, 0)),
              core.LIVE_FENSTER_S), True)
    check("Intervall ausserhalb Fenster 30 s",
          nah(core.shop_intervall("PS Direct DE", im_fenster, ts(19, 0)),
              core.LIVE_HEISS_S), True)
    check("Sperre schlaegt Fenster",
          nah(core.shop_intervall("PS Direct DE",
                                  {"PS Direct DE": {"last_status": "challenge",
                                                    "last_ts": ts(9, 0)}}, ts(10, 0)),
              core.LIVE_RUHE_S), True)
    check("Rundentakt im Fenster",
          core.live_takt(core.HAENDLER, {"PS Direct DE"}, ts(10, 0)),
          core.LIVE_TAKT_FENSTER)
    check("Rundentakt ausserhalb",
          core.live_takt(core.HAENDLER, {"PS Direct DE"}, ts(19, 0)), core.LIVE_TAKT)
    check("Rundentakt respektiert Auswahl",
          core.live_takt(core.HAENDLER, {"Amazon DE"}, ts(10, 0)), core.LIVE_TAKT)

    # Rundengroesse haelt das Minutenbudget auch im 10-s-Takt
    check("Runden im Fenster kleiner", core.live_runden_max(core.LIVE_TAKT_FENSTER),
          core.LIVE_RUNDE_FENSTER)
    check("Runden normal", core.live_runden_max(core.LIVE_TAKT), core.LIVE_RUNDE_MAX)
    check("Runden unbekannter Takt", core.live_runden_max("x"), core.LIVE_RUNDE_MAX)
    check("Fensterbudget haelt 40 pro Minute",
          core.LIVE_RUNDE_FENSTER * (60 // core.LIVE_TAKT_FENSTER) <= core.LIVE_BUDGET,
          True)
    check("Normalbudget haelt 40 pro Minute", core.LIVE_RUNDE_MAX * (60 // core.LIVE_TAKT) <= core.LIVE_BUDGET, True)

    # Im Fenster sind PS Direct DE/AT in jeder kurzen Runde dabei - auch dann,
    # wenn sie gerade eben geprueft wurden und andere Shops ueberfaellig sind.
    # Das Budget bleibt bei LIVE_RUNDE_FENSTER.
    runde_shops = ([{"name": "PS Direct DE"}, {"name": "PS Direct AT"}] +
                   [{"name": "Shop %02d" % i} for i in range(10)])
    runde_daten = {h["name"]: {"last_status": "unavail", "last_ts": ts(10, 0) - 500}
                   for h in runde_shops}
    for name in ("PS Direct DE", "PS Direct AT"):
        runde_daten[name] = {"last_status": "unavail", "last_ts": ts(10, 0)}
    runde = [h["name"] for h in core.faellige_haendler(
        runde_shops, runde_daten, ts(10, 0), budget=core.LIVE_RUNDE_FENSTER)]
    check("Fenster: PS Direct DE in jeder Runde", "PS Direct DE" in runde, True)
    check("Fenster: PS Direct AT in jeder Runde", "PS Direct AT" in runde, True)
    check("Fenster: Rundengroesse bleibt", len(runde), core.LIVE_RUNDE_FENSTER)
    check("Fenster: Vorrang zuerst", runde[:2], ["PS Direct AT", "PS Direct DE"])
    # Eine Sperre hebt den Vorrang auf: kein 10-s-Anklopfen gegen Bot-Schutz.
    block_daten = dict(runde_daten)
    block_daten["PS Direct DE"] = {"last_status": "challenge",
                                   "last_ts": ts(10, 0)}
    block = [h["name"] for h in core.faellige_haendler(
        runde_shops, block_daten, ts(10, 0), budget=core.LIVE_RUNDE_FENSTER)]
    check("Fenster: Sperre schlaegt Vorrang", "PS Direct DE" in block, False)
    # Ausserhalb des Fensters bleibt die Reihenfolge rein nach Ueberfaelligkeit.
    aussen_daten = {h["name"]: {"last_status": "unavail",
                                "last_ts": ts(19, 0) - 500}
                    for h in runde_shops}
    for name in ("PS Direct DE", "PS Direct AT"):
        aussen_daten[name] = {"last_status": "unavail", "last_ts": ts(19, 0)}
    aussen = [h["name"] for h in core.faellige_haendler(
        runde_shops, aussen_daten, ts(19, 0), budget=core.LIVE_RUNDE_FENSTER)]
    check("Ausserhalb: kein Vorrang", "PS Direct DE" in aussen, False)
    check("Ausserhalb: Runde bleibt gefuellt", len(aussen),
          core.LIVE_RUNDE_FENSTER)
    check("Ausserhalb: nur ueberfaellige Shops",
          all(name.startswith("Shop ") for name in aussen), True)

    # ── Sofortmeldung bei belegtem Treffer ──────────────────────────
    belegt = {"klass": "hit", "preis": 899.99, "avail_state": "in_stock",
              "stock_source": "jsonld", "condition": "new"}
    check("Sofortmeldung JSON-LD", core.meldebereit(dict(belegt)), True)
    check("Sofortmeldung Remote-Regel",
          core.meldebereit({**belegt, "stock_source": "remote"}), True)
    check("Sofortmeldung nur Text",
          core.meldebereit({**belegt, "stock_source": "text"}), False)
    check("Sofortmeldung ohne Zustand",
          core.meldebereit({**belegt, "avail_state": "unknown"}), False)
    check("Sofortmeldung Marktabholung",
          core.meldebereit({**belegt, "avail_state": "pickup_only"}), False)
    check("Sofortmeldung Gebrauchtware",
          core.meldebereit({**belegt, "condition": "used"}), False)
    check("Sofortmeldung ohne Preis", core.meldebereit({**belegt, "preis": None}), False)
    check("Sofortmeldung kein Treffer",
          core.meldebereit({**belegt, "klass": "unavail"}), False)

    main_q = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    check("App taktet live", "faellige_haendler" in main_q, True)
    check("App nutzt LIVE_TAKT", "LIVE_TAKT" in main_q, True)
    check("App ohne fixe 60-s-Runde", "jetzt+60" not in main_q, True)
    check("App ohne Hot-Shop-Fixliste", "_schnell_shops" not in main_q, True)
    check("App zeigt faellige Shops", "F\u00c4LLIG" in main_q, True)
    check("App meldet belegte Treffer sofort", "meldebereit" in main_q, True)
    check("App kennt Drop-Fenster", "live_takt" in main_q, True)
    check("App startet Schnellscan im Fenster", "_fenster_pruefen" in main_q, True)
    check("App beendet nur die Automatik", "_fast_auto" in main_q, True)
    check("App kennt Wachhund", "bg_wachhund" in main_q, True)
    check("App bietet WLAN-Option", "BG NUR WLAN" in main_q, True)
    check("App bietet Lade-Option", "BG NUR LADEN" in main_q, True)
    check("App zaehlt Nachtrag nicht doppelt", "self._process(r,nach)" in main_q, True)


def webhook_tests():
    """Alarmzuverlaessigkeit: gemeinsame Dedupe-Datei und sichtbarer Fehler."""
    alt_dir = core._data_dir()
    tmp = tempfile.mkdtemp(prefix="ps5pro-webhook-")
    try:
        core.set_data_dir(tmp)
        core.reset_webhook_dedupe()
        check("Dedupe: erster Anspruch", core.webhook_dedupe("Amazon DE", 799), True)
        pfad = os.path.join(tmp, core.WEBHOOK_DEDUPE_FILE)
        check("Dedupe: gemeinsame Datei", os.path.exists(pfad), True)
        # Frischer Prozessspeicher, dieselbe Datei: der Anspruch bleibt. Genau
        # das fehlte, als App und Dienst denselben Treffer doppelt meldeten.
        with core._WEBHOOK_LOCK:
            core._WEBHOOK_SEEN.clear()
        check("Dedupe: gilt ueber Prozesse",
              core.webhook_dedupe("Amazon DE", 799), False)
        check("Dedupe: Haendler zaehlt", core.webhook_dedupe("Saturn DE", 799), True)
        check("Dedupe: Preis zaehlt", core.webhook_dedupe("Amazon DE", 819), True)
        check("Dedupe: Restock zaehlt",
              core.webhook_dedupe("Amazon DE", 799, True), True)
        check("Dedupe: nach Cooldown frei",
              core.webhook_dedupe("Amazon DE", 799, jetzt=time.time() + 601), True)
        daten = core._json_lesen(pfad) or {}
        check("Dedupe: alte Ansprueche fallen raus", len(daten), 1)

        # Ohne beschreibbares Verzeichnis darf der Alarm nicht sterben.
        core.set_data_dir(os.path.join(tmp, "fehlt"))
        with core._WEBHOOK_LOCK:
            core._WEBHOOK_SEEN.clear()
        check("Dedupe: Rueckfall ohne Datei", core.webhook_dedupe("Shop Q", 700), True)
        check("Dedupe: Rueckfall zweit", core.webhook_dedupe("Shop Q", 700), False)

        core.set_data_dir(tmp)
        check("Status: noch keiner", core.webhook_status_lesen(), None)
        core.webhook_status_merken(False, "HTTP 401", "Otto DE")
        st = core.webhook_status_lesen() or {}
        check("Status: Fehler gemerkt",
              (st.get("ok"), st.get("status"), st.get("haendler")),
              (False, "HTTP 401", "Otto DE"))
        check("Status: Zeit anzeigbar", core.kurz_zeit(st.get("ts")) != "", True)

        # sende_webhook_alarm schreibt das Ergebnis, damit auch ein Fehlschlag
        # des Dienstes in SETUP auftaucht.
        alt_send = core.webhook_senden
        core.webhook_senden = lambda *a, **k: (False, "HTTP 403")
        try:
            core.sende_webhook_alarm({"haendler": "Otto DE", "preis": 799.0,
                                      "url": "https://shop/x"},
                                     {"webhook_url": "https://ntfy.sh/t"}, "T", "X")
        finally:
            core.webhook_senden = alt_send
        st = core.webhook_status_lesen() or {}
        check("Status: Alarm meldet Fehlschlag",
              (st.get("ok"), st.get("status")), (False, "HTTP 403"))
    finally:
        with core._WEBHOOK_LOCK:
            core._WEBHOOK_SEEN.clear()
        core.set_data_dir(alt_dir)
        shutil.rmtree(tmp, ignore_errors=True)


def deckel_tests():
    """Preis-Deckel je Land: AT darf einen eigenen Wert haben."""
    check("Deckel Zahl", core.preis_deckel("DE", 900.0), 900.0)
    check("Deckel ohne Angabe", core.preis_deckel("DE", None), core.MAX_PREIS)
    check("Deckel offen", core.preis_deckel("DE", {"DE": None}), None)
    check("Deckel Dict DE", core.preis_deckel("DE", {"DE": 900.0, "AT": 1000.0}), 900.0)
    check("Deckel Dict AT", core.preis_deckel("AT", {"DE": 900.0, "AT": 1000.0}), 1000.0)
    check("Deckel Dict klein geschrieben", core.preis_deckel("at", {"AT": 1000.0}), 1000.0)
    check("Deckel Land ohne Eintrag", core.preis_deckel("CH", {"DE": 900.0}),
          core.MAX_PREIS)
    check("Deckel Unsinn faellt zurueck", core.preis_deckel("DE", 12), core.MAX_PREIS)
    check("Deckel Grenze", core.deckel_wert(core.DECKEL_MAX), core.DECKEL_MAX)
    check("Deckel ausserhalb", core.deckel_wert(core.DECKEL_MAX + 1), core.MAX_PREIS)
    check("Deckel Ersatzwert", core.deckel_wert("x", None), None)

    class _S:
        def __init__(self, d): self.d = d
        def get(self, k, d=None): return self.d.get(k, d)

    check("Deckel aus Einstellungen erbt",
          core.preis_deckel_aus(_S({"max_preis": 900.0})),
          {"DE": 900.0, "AT": 900.0})
    check("Deckel aus Einstellungen mit AT",
          core.preis_deckel_aus(_S({"max_preis": 900.0, "max_preis_at": 1000.0})),
          {"DE": 900.0, "AT": 1000.0})
    check("Deckel aus Einstellungen offen",
          core.preis_deckel_aus(_S({"max_preis": None})),
          {"DE": None, "AT": None})
    check("Deckel aus Einstellungen unsinniges AT erbt",
          core.preis_deckel_aus(_S({"max_preis": 850.0, "max_preis_at": 99})),
          {"DE": 850.0, "AT": 850.0})


def kauf_tests():
    """"Gekauft": Protokoll mit Preis/Zeit und 24 Stunden Stumm-Schaltung."""
    alt_dir = core._data_dir()
    tmp = tempfile.mkdtemp(prefix="ps5pro-kauf-")
    try:
        core.set_data_dir(tmp)
        k = core.Kaeufe()
        check("Kauf: Protokoll leer", k.alle(), [])
        e = k.merken({"haendler": "Amazon DE", "preis": 799.0, "land": "DE"})
        check("Kauf: Haendler", e.get("haendler"), "Amazon DE")
        check("Kauf: Preis", e.get("preis"), 799.0)
        check("Kauf: Zeitpunkt lesbar", core.kurz_zeit(e.get("ts")) != "", True)
        check("Kauf: auf Platte", core.Kaeufe().letzter("Amazon DE").get("preis"),
              799.0)
        k.merken({"haendler": "Saturn DE", "preis": 819.0})
        check("Kauf: letzter je Shop", core.Kaeufe().letzter("Amazon DE").get("preis"),
              799.0)
        check("Kauf: zwei Eintraege", len(core.Kaeufe().alle()), 2)
        check("Kauf: ohne Preis",
              core.Kaeufe().merken({"haendler": "Otto DE"}).get("preis"), None)

        # 24 Stunden stumm: innerhalb der Frist kein Alarm, danach wieder.
        jetzt = time.time()
        settings = {"mute_bis": {"Amazon DE": jetzt + 3600}}
        treffer = {"haendler": "Amazon DE", "preis": 799.0, "klass": "hit",
                   "condition": "new", "sofort": True}
        check("Gekauft: stumm", core.alarm_erlaubt(treffer, None, settings), False)
        check("Gekauft: Ende bekannt",
              core.stumm_bis(settings, "Amazon DE") is not None, True)
        check("Gekauft: nach Ablauf wieder laut",
              core.alarm_erlaubt(treffer, None,
                                 {"mute_bis": {"Amazon DE": jetzt - 1}}), True)
        check("Gekauft: anderer Shop bleibt laut",
              core.alarm_erlaubt(dict(treffer, haendler="Saturn DE"), None, settings),
              True)
    finally:
        core.set_data_dir(alt_dir)
        shutil.rmtree(tmp, ignore_errors=True)


def amazon_tests():
    """Amazon ohne JSON-LD: nur die Kaufbox zaehlt, kein Fremdpreis."""
    kaufbox = ('<div id="corePrice_feature_div"><span class="a-price">'
               '<span class="a-offscreen">899,99 €</span></span></div>')
    bestand = '<div id="availability"><span>Auf Lager</span></div>'
    seite = ('<html><body><span class="a-offscreen">1.488,00 €</span>'
             '<span id="productTitle">Playstation 5 Pro 2 TB</span>'
             + kaufbox + bestand + '</body></html>')
    st = core.extract_structured(seite)
    check("Amazon ohne JSON-LD", st.get("preis"), None)
    check("Amazon Kaufbox-Preis", core.extract_amazon(seite)["preis"], 899.99)
    check("Amazon Kaufbox Bestand", core.extract_amazon(seite)["verfuegbar"], True)
    check("Amazon Zustand", core.extract_amazon(seite)["state"], "in_stock")

    # Ganzzahl und Nachkommateil getrennt, ohne a-offscreen.
    geteilt = ('<div id="apex_desktop"><span class="a-price-whole">1.469'
               '<span class="a-price-decimal">,</span></span>'
               '<span class="a-price-fraction">98</span></div>')
    check("Amazon geteilter Preis", core.extract_amazon(geteilt)["preis"], 1469.98)

    aus = (kaufbox + '<div id="availability">Derzeit nicht verfügbar</div>')
    check("Amazon ausverkauft", core.extract_amazon(aus)["verfuegbar"], False)
    check("Amazon ausverkauft Zustand", core.extract_amazon(aus)["state"], "sold_out")

    # Ohne Kaufbox bleibt der Preis offen - lieber kein Treffer als ein
    # geratener Preis aus Werbung oder Zubehoer.
    ohne = '<html><body><span class="a-offscreen">1.488,00 €</span></body></html>'
    check("Amazon ohne Kaufbox kein Preis", core.extract_amazon(ohne)["preis"], None)

    check("Amazon Host erkannt", core.ist_amazon("https://www.amazon.de/dp/B0FRYBZR91"), True)
    check("Amazon AT Host erkannt", core.ist_amazon("https://www.amazon.at/dp/B0FRYBZR91"), True)
    check("Amazon Fremdhost", core.ist_amazon("https://amazon.de.evil.example/x"), False)

    # Bot-Schutz im 4xx-Body: Otto (Kasada) und Cloudflare antworten nicht mit
    # einer Produktseite, sondern mit einem kurzen Schutz-Script.
    kasada = "<!DOCTYPE html><html><body><script>window.KPSDK={};KPSDK.now=1;</script></body></html>"
    check("Kasada erkannt", core.detect_challenge(kasada[:3000].lower()), True)
    wolke = ("<html><head><title>Just a moment...</title></head>"
             "<body>_cf_chl_opt</body></html>")
    check("Cloudflare erkannt", core.detect_challenge(wolke[:3000].lower()), True)
    check("Bot-Schutz ist Challenge-Klasse",
          core.fehler_klasse("Bot-Schutz (HTTP 400)"), "challenge")
    check("400 ohne Schutz bleibt Fehler", core.fehler_klasse("HTTP 400"), "error")


def fastpath_tests():
    """JSON-LD-Teilabruf: BuyAction, Lesegrenze, Fallback, PS-Direct-Ziel."""
    buy = ('<script type="application/ld+json">'
           '{"@type":"BuyAction","object":{"@type":"ProductGroup",'
           '"name":"SONY PlayStation\u00ae5 Pro - 2 TB Spielekonsole",'
           '"sku":"3018022","gtin13":"0711719024040",'
           '"offers":{"@type":"Offer","price":899.99,'
           '"priceCurrency":"EUR",'
           '"availability":"https://schema.org/OutOfStock"}}}'
           '</script>')
    st = core.extract_structured(buy)
    check("buyaction ist_konsole", st["ist_konsole"], True)
    check("buyaction preis", st["preis"], 899.99)
    check("buyaction verfuegbar", st["verfuegbar"], False)
    check("buyaction state", st["state"], "sold_out")
    check("buyaction gtin", st["gtin"], "0711719024040")
    check("buyaction sku", st["sku"], "3018022")

    class _R:
        def __init__(self, chunks):
            self.chunks = chunks
            self.closed = False

        def iter_content(self, n):
            yield from self.chunks

        def close(self):
            self.closed = True

    r = _R([b"a" * 10, b"b" * 10])
    roh, gekuerzt = core._read_bis(r, 15)
    check("read_bis limit", len(roh), 15)
    check("read_bis gekuerzt", gekuerzt, True)
    check("read_bis schliesst", r.closed, True)
    check("read_bis kurz", core._read_bis(_R([b"abc"]), 15), (b"abc", False))

    _alt_fetch = core.fetch_mit_cache
    _alt_beleg = core.beleg_speichern
    core.beleg_speichern = lambda *a, **k: True
    try:
        core.fetch_mit_cache = lambda *a, **k: (
            buy, "https://shop/x", None, {"bytes": len(buy)})
        schnell = core._scan_einen_json({"name": "MediaMarkt DE", "land": "DE",
                                         "urls": ["https://shop/x"]})
        check("fastpath preis", schnell["preis"], 899.99)
        check("fastpath klasse", schnell["klass"], "unavail")
        check("fastpath bytes", schnell["bytes"], len(buy))
        core.fetch_mit_cache = lambda *a, **k: (
            "<html>kein jsonld</html>", "https://shop/x", None, {"bytes": 20})
        check("fastpath fallback", core._scan_einen_json(
            {"name": "MediaMarkt DE", "land": "DE", "urls": ["https://shop/x"]}), None)

        def _gesperrt(*a, **k):
            raise RuntimeError("Bot-Schutz (HTTP 403)")
        core.fetch_mit_cache = _gesperrt
        sperre = core._scan_einen_json(
            {"name": "MediaMarkt DE", "land": "DE", "urls": ["https://shop/x"]})
        check("fastpath sperre", sperre["klass"], "challenge")
    finally:
        core.fetch_mit_cache = _alt_fetch
        core.beleg_speichern = _alt_beleg

    # Die echte PS-Direct-Fixture (Captured 20.11.2026) muss auch durch den
    # Teilabruf-Pfad gehen, nicht nur durch extract_structured. PS Direct
    # liest nur 64 KB; der JSON-LD-Block muss vollstaendig darin liegen.
    with open(os.path.join(ROOT, "tools", "fixtures", "shop-ps-direct-de.json"),
              encoding="utf-8") as f:
        ps = json.load(f)
    roh = ps["html"].encode("utf-8")
    check("fastpath ps direct grenze", core.fast_json_limit("PS Direct DE"),
          core.FAST_JSON_BYTES_PSDIRECT)
    check("fastpath ps direct at grenze", core.fast_json_limit("PS Direct AT"),
          core.FAST_JSON_BYTES_PSDIRECT)
    check("fastpath andere shops 192 kb", core.fast_json_limit("MediaMarkt DE"),
          core.FAST_JSON_BYTES)
    check("fastpath 64 kb ist kleiner",
          core.FAST_JSON_BYTES_PSDIRECT < core.FAST_JSON_BYTES, True)
    check("fastpath ps direct jsonld in 64 kb",
          roh.find(b"application/ld+json") < core.FAST_JSON_BYTES_PSDIRECT, True)
    teil = roh[:core.FAST_JSON_BYTES_PSDIRECT]
    check("fastpath ps direct outofstock in 64 kb", b"OutOfStock" in teil, True)
    _alt_fetch = core.fetch_mit_cache
    try:
        core.fetch_mit_cache = lambda *a, **k: (
            ps["html"], ps["url"], None, {"bytes": len(ps["html"])})
        pd = core._scan_einen_json({"name": "PS Direct DE", "land": "DE",
                                    "urls": [ps["url"]]})
        check("fastpath ps direct preis", pd["preis"], 899.99)
        check("fastpath ps direct zustand", pd["avail_state"], "sold_out")
        check("fastpath ps direct klasse", pd["klass"], "unavail")
        check("fastpath ps direct url", pd["url"], ps["url"])
        check("fastpath ps direct signal", pd["signal"], "jsonld")
        # Der Teilabruf muss fuer PS Direct wirklich 64 KB anfordern.
        anfrage = {}
        def _mit_grenze(urls, cancel=None, force=False, limit=None):
            anfrage["limit"] = limit
            return (teil.decode("utf-8", "ignore"), ps["url"], None,
                    {"bytes": len(teil)})
        core.fetch_mit_cache = _mit_grenze
        pd64 = core._scan_einen_json({"name": "PS Direct AT", "land": "AT",
                                      "urls": [ps["url"]]})
        check("fastpath ps direct anfrage 64 kb", anfrage.get("limit"),
              core.FAST_JSON_BYTES_PSDIRECT)
        check("fastpath ps direct 64 kb preis", pd64["preis"], 899.99)
        check("fastpath ps direct 64 kb zustand", pd64["avail_state"], "sold_out")
        check("fastpath ps direct 64 kb bytes", pd64["bytes"], len(teil))
    finally:
        core.fetch_mit_cache = _alt_fetch

    check("ps direct de ziel", core.HAENDLER_BASIS["PS Direct DE"][0],
          "https://www.playstation.com/de-de/ps5/ps5-pro/buy-now/")
    check("ps direct at ziel", core.HAENDLER_BASIS["PS Direct AT"][0],
          "https://www.playstation.com/de-at/ps5/ps5-pro/buy-now/")


def cloud_watcher_tests():
    """Cloud-Waechter: Konfiguration, Takt, Schattenfrist, Baseline, Zustand."""
    import cloud_watcher.watcher as cw

    k = cw.Konfig.aus_env({})
    check("cloud shops standard", list(k.shops),
          ["PS Direct DE", "PS Direct AT"])
    check("cloud fenstertakt standard", 30 <= k.window_takt <= 60, True)
    check("cloud takt aussen standard", k.aussen_takt >= 60, True)
    check("cloud schatten standard", k.shadow, True)
    check("cloud schattenstunden", k.shadow_hours, 48.0)

    k2 = cw.Konfig.aus_env({"WATCH_SHADOW": "0", "WATCH_WINDOW_TAKT": "5",
                            "WATCH_TAKT_AUSSEN": "10",
                            "WATCH_SHOPS": " PS Direct DE "})
    check("cloud fenstertakt geklemmt", k2.window_takt, 30)
    check("cloud takt aussen geklemmt", k2.aussen_takt, 60)
    check("cloud scharf", k2.shadow, False)
    check("cloud shop getrimmt", list(k2.shops), ["PS Direct DE"])
    unbekannt = False
    try:
        cw.Konfig.aus_env({"WATCH_SHOPS": "Nirgends DE"})
    except ValueError:
        unbekannt = True
    check("cloud unbekannter shop", unbekannt, True)

    z = cw.neuer_zustand(1000.0, 48)
    check("cloud schattenfrist", z["schatten_bis"], 1000.0 + 48 * 3600)
    check("cloud schatten aktiv",
          cw.schatten_aktiv(z, 1000.0 + 47 * 3600, False), True)
    check("cloud schatten vorbei",
          cw.schatten_aktiv(z, 1000.0 + 49 * 3600, False), False)
    check("cloud schatten erzwungen",
          cw.schatten_aktiv(z, 1000.0 + 49 * 3600, True), True)

    dt_fenster = core._als_datetime(
        time.mktime((2026, 11, 16, 10, 0, 0, 0, 0, -1)))
    dt_aussen = core._als_datetime(
        time.mktime((2026, 11, 16, 19, 0, 0, 0, 0, -1)))
    ruhig = {"status": "unavail", "fail_streak": 0}
    check("cloud takt im fenster",
          30 <= cw.takt_sekunden("PS Direct DE", ruhig, dt_fenster, k) <= 60,
          True)
    check("cloud takt ausserhalb",
          cw.takt_sekunden("PS Direct DE", ruhig, dt_aussen, k) >= 150, True)
    check("cloud takt sperre",
          cw.takt_sekunden("PS Direct DE",
                           {"status": "challenge", "fail_streak": 1},
                           dt_fenster, k), cw.CHALLENGE_TAKT)
    check("cloud takt fehler",
          cw.takt_sekunden("PS Direct DE",
                           {"status": "parser", "fail_streak": 2},
                           dt_fenster, k), cw.FEHLER_TAKT)

    tmp = tempfile.mkdtemp(prefix="ps5pro-cloud-")
    alt_dir = core.data_dir()
    alt_scan = core.scan_einen
    alt_verify = core.verify_treffer
    try:
        pfad = os.path.join(tmp, cw.STATE_FILE)
        neu = cw.zustand_laden(pfad, 1000.0, 48)
        check("cloud zustand neu", neu["schatten_bis"], 1000.0 + 48 * 3600)
        cw.zustand_speichern(pfad, neu)
        wieder = cw.zustand_laden(pfad, 5000.0, 48)
        check("cloud zustand bleibt", wieder["schatten_bis"],
              neu["schatten_bis"])
        check("cloud zustand datei", os.path.isfile(pfad), True)
        check("cloud zustand atomar", os.path.exists(pfad + ".tmp"), False)

        eintrag = {}
        unavail = {"haendler": "PS Direct DE", "land": "DE",
                   "klass": "unavail", "preis": 899.99,
                   "verfuegbar": False, "dauer": 0.1}
        check("cloud baseline kein alarm", cw.ereignis(eintrag, unavail), None)
        cw.aktualisiere(eintrag, unavail, 1000.0, None)
        check("cloud baseline gesetzt", eintrag.get("initialisiert"), True)
        check("cloud baseline preis", eintrag.get("preis"), 899.99)
        hit = dict(unavail, klass="hit", verfuegbar=True,
                   verify="bestaetigt", sofort=True)
        check("cloud restock erkannt", cw.ereignis(eintrag, hit), "restock")
        cw.aktualisiere(eintrag, hit, 1060.0, None)
        check("cloud bestand", eintrag.get("verfuegbar"), True)
        check("cloud kein doppelalarm", cw.ereignis(eintrag, hit), None)
        check("cloud neuer preis",
              cw.ereignis(eintrag, dict(hit, preis=849.0)), "new")
        ohne_flag = dict(hit)
        ohne_flag.pop("verfuegbar")
        cw.aktualisiere(eintrag, ohne_flag, 1240.0, None)
        check("cloud treffer ohne flag", eintrag.get("verfuegbar"), True)

        # Unbestaetigt, Vorbestellung und Gebrauchtware duerfen den Bestand
        # nicht setzen; der spaetere bestaetigte Treffer muss Restock sein.
        bestaetigt = {"haendler": "PS Direct DE", "land": "DE",
                      "klass": "hit", "preis": 899.0, "sofort": True,
                      "verify": "bestaetigt", "condition": "neu",
                      "verfuegbar": True}
        unbestaetigt = dict(bestaetigt, verify="unbestaetigt")
        e_unb = {"initialisiert": True, "verfuegbar": False,
                 "preis": 899.99}
        check("cloud unbestaetigt kein alarm",
              cw.ereignis(e_unb, unbestaetigt), None)
        cw.aktualisiere(e_unb, unbestaetigt, 1300.0, None)
        check("cloud unbestaetigt nicht verfuegbar",
              e_unb.get("verfuegbar"), False)
        check("cloud unbestaetigt dann restock",
              cw.ereignis(e_unb, bestaetigt), "restock")
        cw.aktualisiere(e_unb, bestaetigt, 1360.0, None)
        check("cloud bestaetigt verfuegbar", e_unb.get("verfuegbar"), True)

        e_pre = {"initialisiert": True, "verfuegbar": False,
                 "preis": 899.99}
        vorbestellung = dict(bestaetigt, sofort=False)
        check("cloud vorbestellung kein alarm",
              cw.ereignis(e_pre, vorbestellung), None)
        cw.aktualisiere(e_pre, vorbestellung, 1300.0, None)
        check("cloud vorbestellung nicht verfuegbar",
              e_pre.get("verfuegbar"), False)
        check("cloud vorbestellung dann restock",
              cw.ereignis(e_pre, bestaetigt), "restock")
        cw.aktualisiere(e_pre, bestaetigt, 1360.0, None)
        check("cloud vorbestellung dann verfuegbar",
              e_pre.get("verfuegbar"), True)

        e_used = {"initialisiert": True, "verfuegbar": False,
                  "preis": 899.99}
        gebraucht = dict(bestaetigt, condition="used")
        check("cloud gebraucht kein alarm",
              cw.ereignis(e_used, gebraucht), None)
        cw.aktualisiere(e_used, gebraucht, 1300.0, None)
        check("cloud gebraucht nicht verfuegbar",
              e_used.get("verfuegbar"), False)
        check("cloud gebraucht dann restock",
              cw.ereignis(e_used, bestaetigt), "restock")

        challenge = dict(unavail, klass="challenge", verfuegbar=None,
                         fehler="HTTP 403")
        cw.aktualisiere(eintrag, challenge, 1120.0, None)
        check("cloud fehlerserie", eintrag.get("fail_streak"), 1)
        check("cloud sperre bis", eintrag.get("challenge_bis"), 2020.0)
        cw.aktualisiere(eintrag, hit, 1180.0, None)
        check("cloud fehlerserie zurueck", eintrag.get("fail_streak"), 0)

        core.set_data_dir(tmp)
        core.reset_health()
        shop = {"name": "PS Direct DE", "land": "DE",
                "urls": ["https://example.invalid/ps5"]}
        deckel = core.preis_deckel_aus({"max_preis": 900})
        core.scan_einen = lambda h, cancel=None, force=False: {
            "haendler": h["name"], "land": h["land"], "preis": 1500.0,
            "klass": "hit", "verfuegbar": True, "dauer": 0.01,
            "url": "https://example.invalid/ps5", "condition": "neu"}
        r = cw.pruefe_shop(shop, deckel, None)
        check("cloud preisdeckel", r.get("klass"), "expensive")
        check("cloud preisdeckel nicht verfuegbar",
              r.get("verfuegbar"), False)

        core.scan_einen = lambda h, cancel=None, force=False: {
            "haendler": h["name"], "land": h["land"], "preis": 899.0,
            "klass": "unavail", "verfuegbar": False, "dauer": 0.01,
            "url": "https://example.invalid/ps5"}
        r = cw.pruefe_shop(shop, deckel, None)
        check("cloud unavail nicht verfuegbar", r.get("verfuegbar"), False)

        gesehen = []
        core.scan_einen = lambda h, cancel=None, force=False: {
            "haendler": h["name"], "land": h["land"], "preis": 899.0,
            "klass": "hit", "verfuegbar": True, "sofort": True,
            "dauer": 0.01, "url": "https://example.invalid/ps5",
            "condition": "neu"}
        def _bestaetigen(h, r, cancel=None):
            gesehen.append(1)
            r["verify"] = "bestaetigt"
            return r
        core.verify_treffer = _bestaetigen
        r = cw.pruefe_shop(shop, deckel, None)
        check("cloud treffer geprueft", len(gesehen), 1)
        check("cloud treffer bleibt", r.get("klass"), "hit")
        check("cloud treffer verfuegbar", r.get("verfuegbar"), True)
    finally:
        core.scan_einen = alt_scan
        core.verify_treffer = alt_verify
        core.set_data_dir(alt_dir)
        core.reset_health()
        shutil.rmtree(tmp, ignore_errors=True)

    # Der Schattenalarm darf niemals den Webhook aufrufen und nie die
    # Webhook-URL ins Log schreiben. Live ruft er ihn genau einmal.
    k3 = cw.Konfig.aus_env({
        "WATCH_WEBHOOK_URL": "https://ntfy.sh/secret-topic"})
    assert k3.webhook_preset == "ntfy"
    zustand = {"alarme_schatten": 0, "alarme_gesendet": 0}
    alarm = {"haendler": "PS Direct DE", "klass": "hit", "preis": 899.0,
             "verfuegbar": True, "verify": "bestaetigt",
             "url": "https://example.invalid/ps5"}
    logs = []
    aufrufe = []
    alt_log = cw.log
    alt_send = core.sende_webhook_alarm
    alt_dedupe = core.webhook_dedupe
    tmp_outbox = tempfile.mkdtemp(prefix="ps5pro-outbox-")
    pfad_outbox = os.path.join(tmp_outbox, cw.STATE_FILE)
    try:
        cw.log = lambda d: logs.append(d)
        core.webhook_dedupe = lambda *a, **k: True
        core.sende_webhook_alarm = lambda *a, **k: (
            aufrufe.append(1) or (True, "HTTP 200"))
        cw.melde(alarm, "restock", k3, zustand, True,
                 cw.settings_aus(k3), None)
        check("cloud schatten kein versand", aufrufe, [])
        check("cloud schatten aktion", logs[-1].get("aktion"),
              "wuerde_senden")
        check("cloud schatten gezaehlt",
              zustand.get("alarme_schatten"), 1)
        check("cloud schatten ohne webhook-url",
              "secret-topic" not in json.dumps(logs, ensure_ascii=False), True)
        cw.melde(alarm, "restock", k3, zustand, False,
                 cw.settings_aus(k3), None, pfad_outbox)
        check("cloud live vorgemerkt", logs[-1].get("aktion"), "eingereiht")
        cw.outbox_drain(zustand, k3, cw.settings_aus(k3), None,
                        jetzt=time.time(), pfad=pfad_outbox)
        check("cloud live versand", len(aufrufe), 1)
        check("cloud live gezaehlt", zustand.get("alarme_gesendet"), 1)
        check("cloud live aktion", logs[-1].get("aktion"), "gesendet")
    finally:
        cw.log = alt_log
        core.sende_webhook_alarm = alt_send
        core.webhook_dedupe = alt_dedupe
        shutil.rmtree(tmp_outbox, ignore_errors=True)

    for datei in ("Dockerfile.watcher", "fly.toml",
                  "cloud_watcher/docker-compose.yml",
                  "cloud_watcher/README.md",
                  "cloud_watcher/.env.example"):
        check("cloud datei " + datei,
              os.path.isfile(os.path.join(ROOT, datei)), True)
    with open(os.path.join(ROOT, "fly.toml"), encoding="utf-8") as f:
        fly = f.read()
    check("cloud fly zwei shops", "PS Direct DE,PS Direct AT" in fly, True)
    check("cloud fly schatten", 'WATCH_SHADOW = "1"' in fly, True)
    check("cloud fly neustart", 'policy = "always"' in fly, True)
    with open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8") as f:
        ignore = f.read()
    check("cloud docker ohne env", "cloud_watcher/.env" in ignore, True)


def watcher_p0_tests():
    """Cloud-Waechter P0: Preflight, Tageszeile, Preistoleranz, Budget, Challenges."""
    import cloud_watcher.watcher as cw

    tmp = tempfile.mkdtemp(prefix="ps5pro-watcher-p0-")
    pfad = os.path.join(tmp, cw.STATE_FILE)
    try:
        # 1. Preflight: Schatten ohne Kanal ist in Ordnung, live nicht.
        k_schatten = cw.Konfig.aus_env({"WATCH_DATA_DIR": tmp})
        ok, checks = cw.preflight(k_schatten, pfad)
        check("p0 preflight schatten ok", ok, True)
        check("p0 preflight schatten webhook",
              [c["ok"] for c in checks if c["name"] == "webhook"], [True])
        k_live = cw.Konfig.aus_env({"WATCH_SHADOW": "0",
                                    "WATCH_DATA_DIR": tmp})
        ok, _ = cw.preflight(k_live, pfad)
        check("p0 preflight live ohne kanal", ok, False)
        k_http = cw.Konfig.aus_env({"WATCH_SHADOW": "0",
                                    "WATCH_WEBHOOK_URL": "http://ntfy.sh/x",
                                    "WATCH_DATA_DIR": tmp})
        ok, _ = cw.preflight(k_http, pfad)
        check("p0 preflight live http", ok, False)
        k_https = cw.Konfig.aus_env({
            "WATCH_SHADOW": "0",
            "WATCH_WEBHOOK_URL": "https://ntfy.sh/secret-p0",
            "WATCH_DATA_DIR": tmp})
        ok, checks = cw.preflight(k_https, pfad)
        check("p0 preflight live https", ok, True)
        check("p0 preflight ohne url-leak",
              "secret-p0" not in json.dumps(checks, ensure_ascii=False), True)
        k_ops_http = cw.Konfig.aus_env({
            "WATCH_SHADOW": "0",
            "WATCH_WEBHOOK_URL": "https://ntfy.sh/secret-p0",
            "WATCH_OPS_WEBHOOK_URL": "http://ntfy.sh/ops",
            "WATCH_DATA_DIR": tmp})
        ok, checks = cw.preflight(k_ops_http, pfad)
        check("p0 preflight ops warnung", ok, True)
        check("p0 preflight ops nicht ok",
              [c["ok"] for c in checks if c["name"] == "ops"], [False])

        # 2. Minutenbudget: gleitendes Fenster, harte Obergrenze, Vorrang.
        jetzt = 5000.0
        verlauf = []
        check("p0 budget leer", cw.budget_rest(verlauf, jetzt, 12), 12)
        verlauf = [jetzt - 1] * 12
        check("p0 budget voll", cw.budget_rest(verlauf, jetzt, 12), 0)
        verlauf = [jetzt - 61] * 3 + [jetzt - 10] * 2
        check("p0 budget alt verworfen", cw.budget_rest(verlauf, jetzt, 12), 10)
        check("p0 budget alt entfernt", len(verlauf), 2)
        check("p0 budget minimum", cw.budget_rest([], jetzt, 0), 1)
        check("p0 shop vorrang", (cw.shop_vorrang("PS Direct AT"),
                                  cw.shop_vorrang("Amazon DE")), (0, 1))

        # 3. Preistoleranz: kleine Ausschlaege schweigen, grosse melden.
        check("p0 preis toleranz klein",
              cw.preis_signifikant(798.5, 799.0, 1.0), False)
        check("p0 preis toleranz gross",
              cw.preis_signifikant(797.5, 799.0, 1.0), True)
        check("p0 preis toleranz null",
              cw.preis_signifikant(798.98, 799.0, 0.0), True)
        check("p0 preis toleranz cent",
              cw.preis_signifikant(798.995, 799.0, 0.0), False)
        check("p0 preis erster",
              cw.preis_signifikant(799.0, None, 1.0), True)
        treffer = {"haendler": "PS Direct DE", "klass": "hit", "preis": 798.5,
                   "verfuegbar": True, "sofort": True,
                   "verify": "bestaetigt", "condition": "neu"}
        eintrag = {"initialisiert": True, "verfuegbar": True, "preis": 799.0}
        check("p0 ereignis toleranz unterdrueckt",
              cw.ereignis(eintrag, treffer, 1.0), None)
        check("p0 ereignis toleranz meldet",
              cw.ereignis(eintrag, dict(treffer, preis=797.0), 1.0), "new")
        e_unavail = {"initialisiert": True, "verfuegbar": False,
                     "preis": 900.0}
        check("p0 ereignis restock trotz toleranz",
              cw.ereignis(e_unavail, dict(treffer, preis=900.0), 5.0),
              "restock")

        # 4. Drei Challenges in Folge: 60 Minuten statt 15.
        eintrag = {"initialisiert": True, "preis": 799.0, "verfuegbar": False}
        heraus = {"haendler": "Amazon DE", "klass": "challenge",
                  "preis": None, "verfuegbar": None, "fehler": "HTTP 403"}
        now = 10000.0
        for i in range(1, 4):
            cw.aktualisiere(eintrag, heraus, now + i * 10, None)
            check("p0 challenge serie %d" % i,
                  eintrag.get("challenge_serie"), i)
        check("p0 challenge kurz", cw.CHALLENGE_TAKT, 900)
        check("p0 challenge lang", cw.challenge_takt(eintrag),
              cw.CHALLENGE_LANG)
        check("p0 challenge lang 60 min",
              eintrag.get("challenge_bis"), now + 30 + cw.CHALLENGE_LANG)
        check("p0 challenge takt lang",
              cw.takt_sekunden("Amazon DE", eintrag,
                               core._als_datetime(now + 100),
                               cw.Konfig.aus_env({})), cw.CHALLENGE_LANG)
        cw.aktualisiere(eintrag, dict(heraus, klass="unavail", preis=799.0,
                                      verfuegbar=False), now + 5000, None)
        check("p0 challenge serie zurueck",
              eintrag.get("challenge_serie"), 0)

        # 5. Tageszeile: Kennzahlen, Perzentile, Outbox-Stand, Reset.
        z = cw.neuer_zustand(1000.0, 48)
        check("p0 tag neu", cw.tag_sicherstellen(z).get("checks"), 0)
        r_hit = {"klass": "hit", "dauer": 0.2, "bytes": 1200,
                 "verify": "bestaetigt"}
        cw.tag_buchen(z, r_hit, 1000.0, None)
        cw.tag_buchen(z, {"klass": "challenge", "dauer": 0.4, "bytes": 800},
                      1001.0, None)
        cw.tag_buchen(z, {"klass": "parser", "dauer": 0.6, "bytes": 400},
                      1002.0, None)
        tag = z["tag"]
        check("p0 tag checks", tag.get("checks"), 3)
        check("p0 tag treffer", tag.get("treffer"), 1)
        check("p0 tag challenge", tag.get("challenge"), 1)
        check("p0 tag fehler", tag.get("fehler"), 1)
        check("p0 tag parser", tag.get("parser"), 1)
        check("p0 tag requests", tag.get("requests"), 4)
        check("p0 tag bytes", tag.get("bytes"), 2400)
        cw.tag_sicherstellen(z)["alarme"] = 2
        cw.tag_sicherstellen(z)["schatten"] = 1
        box = cw.outbox_sicherstellen(z)
        box["items"] = [
            {"id": "a", "status": "pending"},
            {"id": "b", "status": "failed"},
            {"id": "c", "status": "sent"},
        ]
        zusammen = cw.tag_zusammenfassung(tag, box)
        check("p0 tag quote", zusammen.get("quote"), 33.3)
        check("p0 tag p50", zusammen.get("ms_p50"), 400)
        check("p0 tag p95", zusammen.get("ms_p95"), 600)
        check("p0 tag alarme", zusammen.get("alarme"), 2)
        check("p0 tag outbox offen", zusammen.get("outbox_offen"), 1)
        check("p0 tag outbox failed", zusammen.get("outbox_failed"), 1)

        tz = cw.Konfig.aus_env({}).zeitzone()
        from datetime import datetime as _dt
        spaet = _dt(2026, 11, 21, 23, 30, tzinfo=tz).timestamp()
        frueh = _dt(2026, 11, 22, 0, 30, tzinfo=tz).timestamp()
        z = cw.neuer_zustand(spaet, 0)
        z["schatten_bis"] = 0.0
        cw.tag_sicherstellen(z)["datum"] = cw._tag_datum(spaet, tz)
        cw.tag_buchen(z, r_hit, spaet, tz)
        check("p0 tagwechsel vorher", cw.tageswechsel(z, spaet, tz), None)
        zeile = cw.tageswechsel(z, frueh, tz)
        check("p0 tagwechsel zeile", (zeile or {}).get("datum"), "2026-11-21")
        check("p0 tagwechsel checks", (zeile or {}).get("checks"), 1)
        check("p0 tagwechsel reset", z["tag"].get("checks"), 0)
        check("p0 tagwechsel neu", z["tag"].get("datum"), "2026-11-22")
        check("p0 tagwechsel einmal", cw.tageswechsel(z, frueh, tz), None)
        cw.zustand_speichern(pfad, z)
        geladen = cw.zustand_laden(pfad, frueh, 48)
        check("p0 tag persistiert", geladen["tag"].get("datum"), "2026-11-22")

        # 6. Lokaler Status: Wachzeit, Runden, Outbox, Budget und Heartbeat.
        z = cw.neuer_zustand(3000.0, 48)
        z["runden"] = 7
        z["letzte_runde"] = 2990.0
        box = cw.outbox_sicherstellen(z)
        box["items"] = [
            {"id": "a", "status": "pending"},
            {"id": "b", "status": "sending"},
            {"id": "c", "status": "failed"},
            {"id": "d", "status": "sent"},
        ]
        box["gesamt"] = 4
        k_status = cw.Konfig.aus_env({"WATCH_MAX_REQ_MIN": "9"})
        status = cw.status_daten(z, k_status, 3000.0, None, 3)
        check("p0 status wach", status.get("wach_ts"), 3000.0)
        check("p0 status runden", status.get("runden"), 7)
        check("p0 status outbox", status.get("outbox"),
              {"offen": 2, "failed": 1, "gesamt": 4})
        check("p0 status budget", status.get("budget"),
              {"max": 9, "verbraucht": 3})
        status_pfad = os.path.join(tmp, cw.STATUS_FILE)
        check("p0 status schreiben",
              cw.status_schreiben(status, status_pfad), True)
        with open(status_pfad, encoding="utf-8") as f:
            gespeichert = json.load(f)
        check("p0 status datei wach", gespeichert.get("wach_ts"), 3000.0)
        check("p0 status atomar", os.path.exists(status_pfad + ".tmp"), False)
        check("p0 heartbeat faellig", cw.heartbeat_faellig(0.0, 60.0), True)
        check("p0 heartbeat nicht faellig",
              cw.heartbeat_faellig(10.0, 69.0), False)
        pings = []
        alt_send = core.webhook_senden
        alt_log = cw.log
        core.webhook_senden = lambda url, preset, titel, text, timeout=5: (
            pings.append((url, text)) or (True, "HTTP 200"))
        cw.log = lambda d: None
        try:
            k_hb = cw.Konfig.aus_env({
                "WATCH_HEARTBEAT_URL": "https://hc-ping.com/secret-hb"})
            cw.heartbeat(k_hb, status)
        finally:
            core.webhook_senden = alt_send
            cw.log = alt_log
        check("p0 heartbeat text", "runden=7" in pings[0][1], True)
        check("p0 heartbeat outbox", "offen=2" in pings[0][1], True)
        check("p0 heartbeat budget", "budget=3/9" in pings[0][1], True)
        check("p0 heartbeat url nicht im text",
              "secret-hb" not in pings[0][1], True)

        # 7. Der Container-Healthcheck prueft die Statusdatei.
        with open(os.path.join(ROOT, "Dockerfile.watcher"), encoding="utf-8") as f:
            dockerfile = f.read()
        check("p0 healthcheck vorhanden", "HEALTHCHECK" in dockerfile, True)
        check("p0 healthcheck statusdatei",
              "watcher_status.json" in dockerfile, True)
        check("p0 healthcheck wachzeit", "wach_ts" in dockerfile, True)

        # 8. Alte Zustaende bleiben ohne Datenverlust migrierbar.
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump({"schema": 2, "angelegt": 1.0, "schatten_bis": 1.0,
                       "shops": {},
                       "runden": 0, "alarme_schatten": 0,
                       "alarme_gesendet": 0, "letzte_runde": 0.0,
                       "outbox": {"items": [], "gesamt": 0,
                                  "letzte_id": ""}}, f)
        geladen = cw.zustand_laden(pfad, 2000.0, 48)
        check("p0 migration schema", geladen.get("schema"), 3)
        check("p0 migration tag", isinstance(geladen.get("tag"), dict), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def outbox_tests():
    """Alarm-Outbox: Persist-first, Backoff, Cap, Systemalarm, Ops-Kanal, Migration."""
    import cloud_watcher.watcher as cw

    tmp = tempfile.mkdtemp(prefix="ps5pro-outbox-tests-")
    pfad = os.path.join(tmp, cw.STATE_FILE)
    alt_log = cw.log
    alt_send = core.sende_webhook_alarm
    alt_dir = core.data_dir()
    logs = []
    calls = []
    seen_status = []
    antwort = {"ok": True, "info": "HTTP 200"}
    k = cw.Konfig.aus_env({"WATCH_WEBHOOK_URL": "https://ntfy.sh/secret-outbox"})
    settings = cw.settings_aus(k)
    r = {"haendler": "Amazon DE", "preis": 899.99, "url": "https://example.invalid/p",
         "condition": "neu", "sofort": True}

    def _fake_send(_r, _settings, titel, text, dedupe=True, **kwargs):
        url = str((_settings or {}).get("webhook_url") or "")
        calls.append({"titel": titel, "dedupe": dedupe, "url": url})
        try:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            items = daten.get("outbox", {}).get("items", [])
            if items:
                seen_status.append(items[-1].get("status"))
        except Exception:
            seen_status.append("nicht_lesbar")
        # Der Ops-Kanal ist erreichbar; der Produkt-Webhook folgt der
        # jeweiligen Testantwort.
        if str(titel).startswith("Waechter:") and "secret-ops" in url:
            return True, "HTTP 200"
        return antwort["ok"], antwort["info"]

    def _neu(zeit=1000.0):
        z = cw.neuer_zustand(zeit, 0)
        z["schatten_bis"] = 0.0
        cw.zustand_speichern(pfad, z)
        calls.clear()
        seen_status.clear()
        return z

    try:
        core.set_data_dir(tmp)
        cw.log = lambda d: logs.append(d)
        core.sende_webhook_alarm = _fake_send

        # 1. Ereignis wird vor dem Versand persistiert; der Versand sieht
        #    bereits den Status "sending" in der Datei.
        t0 = time.time()
        z = _neu(t0)
        cw.melde(r, "restock", k, z, False, settings, None, pfad)
        with open(pfad, encoding="utf-8") as f:
            gespeichert = json.load(f)
        check("outbox vormerken",
              gespeichert["outbox"]["items"][0]["status"], "pending")
        check("outbox alarm eingereiht",
              logs[-1].get("aktion"), "eingereiht")
        cw.outbox_drain(z, k, settings, None, jetzt=time.time(), pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox sending vor send", seen_status, ["sending"])
        check("outbox gesendet", item.get("status"), "sent")
        check("outbox zaehler", z.get("alarme_gesendet"), 1)
        check("outbox dedupe aus", calls[0].get("dedupe"), False)
        with open(pfad, encoding="utf-8") as f:
            gespeichert = json.load(f)
        check("outbox sent persistiert",
              gespeichert["outbox"]["items"][0]["status"], "sent")

        # 2. Retry-Backoff 30 s, 2 min, 10 min, 30 min, 2 h; nach sechs
        #    Versuchen failed plus einmaliger Systemalarm.
        z = _neu(2000.0)
        cw.outbox_enqueue(r, "restock", z, 2000.0, "Titel", "Text")
        cw.zustand_speichern(pfad, z)
        antwort.update(ok=False, info="HTTP 500")
        erwartet = [(2000.0, 1, 2030.0), (2030.0, 2, 2150.0),
                    (2150.0, 3, 2750.0), (2750.0, 4, 4550.0),
                    (4550.0, 5, 11750.0)]
        for zeit, versuch, naechste in erwartet:
            cw.outbox_drain(z, k, settings, None, jetzt=zeit, pfad=pfad)
            item = z["outbox"]["items"][0]
            check("outbox versuch %d" % versuch, item.get("attempts"), versuch)
            check("outbox backoff %d" % versuch, item.get("next_ts"), naechste)
            check("outbox pending %d" % versuch, item.get("status"), "pending")
        cw.outbox_drain(z, k, settings, None, jetzt=11750.0, pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox cap versuche", item.get("attempts"), 6)
        check("outbox cap status", item.get("status"), "failed")
        check("outbox cap grund", item.get("failed_grund"), "max_attempts")
        check("outbox systemalarm gesetzt", item.get("system_alarm_ts") is not None, True)
        check("outbox systemalarm einmal",
              sum(1 for c in calls if str(c["titel"]).startswith("Waechter:")), 1)
        check("outbox kein erfolgszaehler", z.get("alarme_gesendet"), 0)

        # 3. 4xx ist endgueltig: kein sechsfacher Backoff.
        z = _neu(3000.0)
        cw.outbox_enqueue(r, "new", z, 3000.0, "Titel", "Text")
        cw.zustand_speichern(pfad, z)
        antwort.update(ok=False, info="HTTP 401")
        cw.outbox_drain(z, k, settings, None, jetzt=3000.0, pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox 4xx terminal", item.get("status"), "failed")
        check("outbox 4xx ein versuch", item.get("attempts"), 1)
        check("outbox 4xx grund", item.get("failed_grund"), "http_4xx")
        # Der Produktalarm bleibt endgueltig; nur der Systemalarm darf
        # spaeter erneut versucht werden.
        def _produktalarme():
            return [c for c in calls
                    if not str(c["titel"]).startswith("Waechter:")]
        vorher = len(_produktalarme())
        cw.outbox_drain(z, k, settings, None, jetzt=5000.0, pfad=pfad)
        check("outbox 4xx kein retry", len(_produktalarme()), vorher)

        # 4. Ein haengender "sending"-Eintrag wird nach Karenz erneut versucht.
        z = _neu(4000.0)
        item = cw.outbox_enqueue(r, "restock", z, 4000.0, "Titel", "Text")
        item["status"] = "sending"
        item["attempts"] = 1
        item["last_attempt_ts"] = 4000.0
        item["next_ts"] = 4000.0
        cw.zustand_speichern(pfad, z)
        antwort.update(ok=True, info="HTTP 200")
        cw.outbox_drain(z, k, settings, None, jetzt=4301.0, pfad=pfad)
        check("outbox sending recovery",
              z["outbox"]["items"][0].get("status"), "sent")

        # 5. Shadow legt nichts in die Outbox.
        z = _neu(6000.0)
        cw.melde(r, "restock", k, z, True, settings, None, pfad)
        check("outbox shadow leer", len(z["outbox"]["items"]), 0)
        check("outbox shadow kein versand", len(calls), 0)

        # 6. Migration eines alten Zustands.
        alt = {"schema": 1, "angelegt": 1.0, "schatten_bis": 0.0,
               "shops": {}, "runden": 0, "alarme_schatten": 0,
               "alarme_gesendet": 0, "letzte_runde": 0.0}
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(alt, f)
        geladen = cw.zustand_laden(pfad, 7000.0, 48)
        check("outbox migration schema", geladen.get("schema"), 3)
        check("outbox migration leer", geladen.get("outbox", {}).get("items"), [])

        # 7. Outbox-Obergrenze active=20.
        z = _neu(8000.0)
        box = cw.outbox_sicherstellen(z)
        for i in range(cw.OUTBOX_MAX_ACTIVE):
            box["items"].append({"id": "x%d" % i, "status": "pending",
                                 "attempts": 0, "created": 8000.0})
        calls.clear()
        check("outbox voll",
              cw.outbox_enqueue(r, "restock", z, 8000.0, "T", "X"), None)
        cw.melde(r, "restock", k, z, False, settings, None, pfad)
        check("outbox overflow systemalarm",
              any(str(c["titel"]).startswith("Waechter:") for c in calls), True)

        # 8. Systemalarm wird nach einem Neustart genau einmal nachgeholt.
        z = _neu(9000.0)
        item = cw.outbox_enqueue(r, "restock", z, 9000.0, "T", "X")
        item["status"] = "failed"
        item["failed_ts"] = 9000.0
        item["failed_grund"] = "max_attempts"
        item["last_error"] = "HTTP 500"
        item["attempts"] = 6
        item["system_alarm_ts"] = None
        cw.zustand_speichern(pfad, z)
        calls.clear()
        cw.outbox_drain(z, k, settings, None, jetzt=9500.0, pfad=pfad)
        check("outbox systemalarm nachholen", len(calls), 1)
        # outbox_drain liest die Box neu ein; der Eintrag ist eine Kopie.
        item = z["outbox"]["items"][0]
        check("outbox systemalarm produktkanal", calls[0].get("url"),
              settings.get("webhook_url"))
        check("outbox systemalarm kanal",
              item.get("system_alarm_kanal"), "produkt")
        cw.outbox_drain(z, k, settings, None, jetzt=9600.0, pfad=pfad)
        check("outbox systemalarm nicht doppelt", len(calls), 1)

        # 8a. Ungueltige Ops-URL: Der Systemalarm faellt auf den Produkt-
        #     Webhook zurueck, statt ins Leere zu senden.
        k_ops_http = cw.Konfig.aus_env({
            "WATCH_WEBHOOK_URL": "https://ntfy.sh/secret-outbox",
            "WATCH_OPS_WEBHOOK_URL": "http://ntfy.sh/secret-ops"})
        settings_ops_http = cw.settings_aus(k_ops_http)
        check("outbox ops ungueltig fallback",
              cw._ops_ziel(settings_ops_http)[1], "produkt")
        z = _neu(9650.0)
        cw.outbox_enqueue(r, "restock", z, 9650.0, "T", "X")
        cw.zustand_speichern(pfad, z)
        calls.clear()
        antwort.update(ok=False, info="HTTP 401")
        cw.outbox_drain(z, k_ops_http, settings_ops_http, None,
                        jetzt=9650.0, pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox ops ungueltig produktalarm",
              calls[0].get("url"), settings_ops_http.get("webhook_url"))
        check("outbox ops ungueltig systemalarm",
              calls[-1].get("url"), settings_ops_http.get("webhook_url"))
        check("outbox ops ungueltig kanal",
              item.get("system_alarm_kanal"), "produkt")

        # 8b. Optionaler Ops-Kanal: Der Produkt-Webhook scheitert endgueltig,
        #     der Systemalarm geht trotzdem an die unabhaengige Ops-URL.
        k_ops = cw.Konfig.aus_env({
            "WATCH_WEBHOOK_URL": "https://ntfy.sh/secret-outbox",
            "WATCH_OPS_WEBHOOK_URL": "https://ntfy.sh/secret-ops"})
        settings_ops = cw.settings_aus(k_ops)
        check("outbox ops preset", k_ops.ops_preset, "ntfy")
        ziel, kanal = cw._ops_ziel(settings_ops)
        check("outbox ops ziel",
              (kanal, ziel.get("webhook_preset")), ("ops", "ntfy"))
        ziel, kanal = cw._ops_ziel({"ops_url": "https://ntfy.sh/x",
                                    "ops_preset": "unsinn"})
        check("outbox ops preset neu",
              (kanal, ziel.get("webhook_preset")), ("ops", "ntfy"))
        check("outbox ops produkt-fallback",
              cw._ops_ziel(settings)[1], "produkt")
        z = _neu(9700.0)
        cw.outbox_enqueue(r, "restock", z, 9700.0, "T", "X")
        cw.zustand_speichern(pfad, z)
        calls.clear()
        # Der Produkt-Webhook antwortet endgueltig mit 401, der Ops-Kanal
        # bleibt erreichbar. Beide Wege muessen getrennt bleiben.
        antwort.update(ok=False, info="HTTP 401")
        cw.outbox_drain(z, k_ops, settings_ops, None, jetzt=9750.0, pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox ops produktalarm", [c["url"] for c in calls],
              ["https://ntfy.sh/secret-outbox", "https://ntfy.sh/secret-ops"])
        check("outbox ops produktalarm titel",
              str(calls[0]["titel"]).startswith("Waechter:"), False)
        check("outbox ops systemalarm titel",
              str(calls[1]["titel"]).startswith("Waechter:"), True)
        check("outbox ops alarm failed", item.get("status"), "failed")
        check("outbox ops systemalarm ok", item.get("system_alarm_ok"), True)
        check("outbox ops kanal", item.get("system_alarm_kanal"), "ops")
        check("outbox ops log kanal",
              any(d.get("typ") == "systemalarm" and d.get("kanal") == "ops"
                  for d in logs), True)
        # Ein Fehlertext mit beiden URLs darf weder Zustand noch Log erreichen.
        gesaeubert = cw._outbox_safe_info(
            "HTTP 401 https://ntfy.sh/secret-ops / https://ntfy.sh/secret-outbox",
            settings_ops)
        check("outbox ops redaktion",
              "secret-ops" not in gesaeubert
              and "secret-outbox" not in gesaeubert, True)
        check("outbox ops url nie geloggt",
              "secret-ops" not in json.dumps(logs, ensure_ascii=False), True)

        # 8c. Ein fehlgeschlagener Systemalarm wird nach Backoff erneut
        #     versucht und erst nach Erfolg oder Cap beendet.
        z = _neu(9800.0)
        cw.outbox_enqueue(r, "restock", z, 9800.0, "T", "X")
        cw.zustand_speichern(pfad, z)
        calls.clear()
        antwort.update(ok=False, info="HTTP 401")
        cw.outbox_drain(z, k, settings, None, jetzt=9800.0, pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox systemalarm retry versuch",
              item.get("system_alarm_attempts"), 1)
        check("outbox systemalarm retry offen",
              item.get("system_alarm_ok"), False)
        check("outbox systemalarm retry wartet",
              item.get("system_alarm_next_ts"),
              9800.0 + cw.OUTBOX_SYSTEM_ALARM_BACKOFF_S[0])
        calls_vorher = len(calls)
        cw.outbox_drain(
            z, k, settings, None,
            jetzt=9800.0 + cw.OUTBOX_SYSTEM_ALARM_BACKOFF_S[0] - 1,
            pfad=pfad)
        check("outbox systemalarm retry nicht zu frueh",
              len(calls), calls_vorher)
        antwort.update(ok=True, info="HTTP 200")
        cw.outbox_drain(
            z, k, settings, None,
            jetzt=9800.0 + cw.OUTBOX_SYSTEM_ALARM_BACKOFF_S[0], pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox systemalarm retry erfolg",
              item.get("system_alarm_ok"), True)
        check("outbox systemalarm retry versuche",
              item.get("system_alarm_attempts"), 2)
        check("outbox systemalarm retry ende",
              item.get("system_alarm_next_ts"), None)
        calls_ende = len(calls)
        cw.outbox_drain(z, k, settings, None, jetzt=13000.0, pfad=pfad)
        check("outbox systemalarm kein dauerretry", len(calls), calls_ende)

        # 8d. Nach drei Fehlversuchen ist Schluss; kein Endlos-Retry.
        z = _neu(10400.0)
        cw.outbox_enqueue(r, "restock", z, 10400.0, "T", "X")
        cw.zustand_speichern(pfad, z)
        calls.clear()
        antwort.update(ok=False, info="HTTP 401")
        cw.outbox_drain(z, k, settings, None, jetzt=10400.0, pfad=pfad)
        versuche = [10400.0]
        versuche.append(versuche[-1] + cw.OUTBOX_SYSTEM_ALARM_BACKOFF_S[0])
        versuche.append(versuche[-1] + cw.OUTBOX_SYSTEM_ALARM_BACKOFF_S[1])
        for zeit in versuche[1:]:
            cw.outbox_drain(z, k, settings, None, jetzt=zeit, pfad=pfad)
        item = z["outbox"]["items"][0]
        check("outbox systemalarm cap versuche",
              item.get("system_alarm_attempts"), cw.OUTBOX_SYSTEM_ALARM_MAX)
        check("outbox systemalarm cap offen",
              item.get("system_alarm_ok"), False)
        check("outbox systemalarm cap ende",
              item.get("system_alarm_next_ts"), None)
        check("outbox systemalarm cap calls",
              sum(1 for c in calls
                  if str(c["titel"]).startswith("Waechter:")), 3)
        cw.outbox_drain(z, k, settings, None, jetzt=20000.0, pfad=pfad)
        check("outbox systemalarm cap kein weiter",
              sum(1 for c in calls
                  if str(c["titel"]).startswith("Waechter:")), 3)

        # 9. Fehlertexte duerfen die Webhook-URL nicht in Zustand oder Log
        #    weitertragen, auch wenn der Transport sie enthaelt.
        z = _neu(10000.0)
        cw.outbox_enqueue(r, "restock", z, 10000.0, "T", "X")
        cw.zustand_speichern(pfad, z)
        antwort.update(ok=False,
                       info="HTTP 401 " + settings.get("webhook_url", ""))
        cw.outbox_drain(z, k, settings, None, jetzt=10000.0, pfad=pfad)
        check("outbox fehler-url redigiert",
              "secret-outbox" not in json.dumps(z, ensure_ascii=False), True)

        # 10. Wenn das Persistieren scheitert, wird der Alarm nicht gesendet.
        z = _neu(11000.0)
        alt_save = cw.zustand_speichern
        def _save_fehler(*args, **kwargs):
            raise OSError("voll")
        cw.zustand_speichern = _save_fehler
        try:
            cw.melde(r, "restock", k, z, False, settings, None, pfad)
        finally:
            cw.zustand_speichern = alt_save
        check("outbox save-fehler kein versand", len(calls), 0)
        check("outbox save-fehler bleibt pending",
              z["outbox"]["items"][0].get("status"), "pending")

        check("outbox keine webhook-url im log",
              "secret-outbox" not in json.dumps(logs, ensure_ascii=False), True)
    finally:
        cw.log = alt_log
        core.sende_webhook_alarm = alt_send
        core.set_data_dir(alt_dir)
        shutil.rmtree(tmp, ignore_errors=True)


def watcher_log_tests():
    """NDJSON-Logs: Tagesrotation, Deckel und Aufbewahrung."""
    import cloud_watcher.watcher as cw
    from datetime import datetime

    tmp = tempfile.mkdtemp(prefix="ps5pro-watcher-log-")
    tz = cw.Konfig.aus_env({}).zeitzone()
    tag1 = datetime(2026, 11, 21, 23, 0, tzinfo=tz).timestamp()
    tag2 = datetime(2026, 11, 22, 1, 0, tzinfo=tz).timestamp()
    alt_max, alt_parts = cw.LOG_MAX_BYTES, cw.LOG_MAX_PARTS
    try:
        cw.log_datei_oeffnen(tmp, tag1, tz)
        cw.log({"typ": "check", "ts": tag1,
                "iso": "2026-11-21T23:00:00+01:00", "ms": 100,
                "bytes": 1000, "frisch": True, "not_modified": False,
                "klass": "unavail"}, jetzt=tag1)
        cw.log({"typ": "check", "ts": tag1,
                "iso": "2026-11-21T23:10:00+01:00", "ms": 300,
                "bytes": 0, "frisch": False, "not_modified": True,
                "klass": "unavail"}, jetzt=tag1)
        cw.log({"typ": "alarm", "ts": tag1,
                "iso": "2026-11-21T23:20:00+01:00", "aktion": "wuerde_senden",
                "event": "restock"}, jetzt=tag1)
        cw.log({"typ": "check", "ts": tag2,
                "iso": "2026-11-22T01:00:00+01:00", "ms": 500,
                "bytes": 500, "frisch": True, "not_modified": True,
                "klass": "hit"}, jetzt=tag2)
        cw.log_datei_schliessen()

        dateien = cw.log_dateien(tmp)
        check("log tagesrotation", len(dateien), 2)
        zeilen = []
        for datei in dateien:
            with open(datei, "r", encoding="utf-8") as f:
                zeilen.extend(json.loads(z) for z in f if z.strip())
        check("log zeilen", len(zeilen), 4)
        check("log json", all(isinstance(z, dict) for z in zeilen), True)

        # Nach dem Schliessen darf kein weiterer Satz in die Dateien gehen.
        cw.log({"typ": "danach"})
        check("log nach close keine datei", len(cw.log_dateien(tmp)), 2)

        # Groessendeckel: hoechstens zwei Teile, danach wird verworfen.
        tmp_cap = os.path.join(tmp, "cap")
        cw.LOG_MAX_BYTES = 150
        cw.LOG_MAX_PARTS = 2
        cw.log_datei_oeffnen(tmp_cap, tag1, tz)
        for i in range(12):
            cw.log({"typ": "test", "i": i, "text": "x" * 40}, jetzt=tag1)
        cw.log_datei_schliessen()
        cw.LOG_MAX_BYTES, cw.LOG_MAX_PARTS = alt_max, alt_parts
        cap_dateien = cw.log_dateien(tmp_cap)
        check("log deckel teile", len(cap_dateien), 2)
        cap_zeilen = 0
        for datei in cap_dateien:
            with open(datei, "r", encoding="utf-8") as f:
                cap_zeilen += len([z for z in f if z.strip()])
        check("log deckel greift", cap_zeilen < 12, True)

        # Aufbewahrung: aelter als 14 Tage fliegt raus, der Vortag bleibt.
        tmp_keep = os.path.join(tmp, "keep")
        os.makedirs(tmp_keep)
        alt_pfad = os.path.join(tmp_keep, cw.LOG_PREFIX + "2026-01-01" + cw.LOG_SUFFIX)
        neu_pfad = os.path.join(tmp_keep, cw.LOG_PREFIX + "2026-11-20" + cw.LOG_SUFFIX)
        for datei in (alt_pfad, neu_pfad):
            with open(datei, "w", encoding="utf-8") as f:
                f.write("{}\n")
        check("log aufraeumen zaehlt", cw.log_aufraeumen(tmp_keep, tag1, tz), 1)
        check("log alter tag weg", os.path.exists(alt_pfad), False)
        check("log neuer tag bleibt", os.path.exists(neu_pfad), True)
    finally:
        cw.log_datei_schliessen()
        cw.LOG_MAX_BYTES, cw.LOG_MAX_PARTS = alt_max, alt_parts
        shutil.rmtree(tmp, ignore_errors=True)


def watcher_report_tests():
    """Report-Tool: Kennzahlen aus NDJSON-Zeilen."""
    if os.path.join(ROOT, "tools") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
    import watcher_report as wr

    zeilen = [
        {"typ": "check", "ts": 1000.0, "ms": 100, "bytes": 1000,
         "frisch": True, "not_modified": False, "klass": "unavail"},
        {"typ": "check", "ts": 1100.0, "ms": 300, "bytes": 0,
         "frisch": False, "not_modified": True, "klass": "unavail"},
        {"typ": "alarm", "ts": 1200.0, "aktion": "wuerde_senden",
         "event": "restock"},
        {"typ": "check", "ts": 2000.0, "ms": 500, "bytes": 500,
         "frisch": True, "not_modified": True, "klass": "hit"},
    ]
    bericht = wr.bericht(zeilen, 4.40)
    check("report checks", bericht["checks"], 3)
    check("report 304 quote", bericht["rate_304"], 66.7)
    check("report 304 flag", bericht["not_modified"], 2)
    check("report traffic", bericht["bytes"], 1500)
    check("report p95", bericht["ms"]["p95"], 500)
    check("report alarme", bericht["alarme"], 1)
    check("report kosten pro alarm",
          isinstance(bericht["kosten"]["pro_alarm"], float), True)
    text = wr._text(bericht)
    check("report text p95", "p95 500 ms" in text, True)
    check("report text 304", "304-Quote: 66.7 %" in text, True)
    check("report perzentil", wr.perzentil([10, 20, 30, 40], 0.95), 40)


if __name__ == "__main__":
    try:
        main_tests()
        retry_tests()
        scan_status_tests()
        radar_tests()
        progress_tests()
        service_tests()
        feature_tests()
        adaptive_boot_tests()
        fixture_tests()
        amazon_tests()
        capture_helper_tests()
        v13_tests()
        webhook_tests()
        deckel_tests()
        kauf_tests()
        v14_tests()
        live_tests()
        fastpath_tests()
        spec_tests()
        play_rebrand_tests()
        cloud_watcher_tests()
        watcher_p0_tests()
        outbox_tests()
        watcher_log_tests()
        watcher_report_tests()
    finally:
        # main.py legt beim Import einen fonts/-Ordner an; im Test nicht noetig.
        try:
            os.rmdir(os.path.join(ROOT, "fonts"))
        except OSError:
            pass
    print()
    print(f"{COUNT - len(FAILS)}/{COUNT} Tests bestanden")
    if FAILS:
        print("FEHLER:", ", ".join(FAILS))
        sys.exit(1)
