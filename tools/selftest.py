"""Logiktests fuer main.py - laufen ohne Kivy und ohne Android.

Prueft die Teile, die ueber richtig/falsch entscheiden: Preis-Parsing, JSON-LD,
Verfuegbarkeit, Bot-Schutz, Klassifizierung, Haendlerdaten.

    python3 tools/selftest.py

Exit-Code 0 = alles gruen. Wird in .github/workflows/build-apk.yml als Gate
vor dem APK-Build ausgefuehrt, damit ein kaputtes Parsing nie in die APK geht.
"""
import configparser
import json
import os
import re
import shutil
import sys
import tempfile
import threading
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

    # Kuerzel
    check("initials PS Direct", main.initials_for("PS Direct DE"), "PS")
    check("initials MediaMarkt", main.initials_for("MediaMarkt AT"), "MM")
    check("initials Amazon", main.initials_for("Amazon DE"), "AM")
    check("initials Notebooksbilliger", main.initials_for("Notebooksbilliger"), "NB")

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
    ausnahmen = ("direct.playstation.com", "www.computeruniverse.net")
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
    check("spec release aab", c.get("app", "android.release_artifact"), "aab")
    check("spec version", c.get("app", "version"), "3.2")
    check("spec versionCode", c.get("app", "android.numeric_version"), "11")
    check("spec cutout", c.get("app", "android.display_cutout"), "shortEdges")
    # Hintergrund-Scan: ohne foregroundServiceType startet Android 14 den
    # Dienst nicht, ohne die Rechte schon gar nicht.
    check("spec hintergrund-service", c.get("app", "services"),
          "ps5proscan:service.py:foreground:sticky:foregroundServiceType=specialUse")
    perms = c.get("app", "android.permissions")
    check("spec foreground-recht", "FOREGROUND_SERVICE" in perms, True)
    check("spec specialUse-recht", "FOREGROUND_SERVICE_SPECIAL_USE" in perms, True)
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

        # Health: ein Fehler erhoeht den Zaehler, ein Erfolg setzt ihn zurueck.
        core.reset_health()
        hh = core.health()
        hh.record({"haendler": "Shop A", "klass": "challenge", "fehler": "Bot"})
        hh.record({"haendler": "Shop A", "klass": "error", "fehler": "Timeout"})
        check("Health Fehlerzaehler", hh.all()["Shop A"]["fail_streak"], 2)
        hh.record({"haendler": "Shop A", "klass": "hit", "preis": 799.0})
        check("Health Erfolg setzt zurueck", hh.all()["Shop A"]["fail_streak"], 0)
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
                core.fetch_mit_cache = lambda urls, cancel=None: (html_rules, urls[0], None, {})
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
                core.fetch_mit_cache = lambda urls, cancel=None: (
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
        check("Alarm Ruhezeit", core.alarm_erlaubt(
            neu, None, {"quiet_hours": True}, __import__("datetime").datetime(2026, 1, 1, 23, 30)), False)

        service_q = open(os.path.join(ROOT, "service.py"), encoding="utf-8").read()
        check("Heartbeat next_ts", '"next_ts"' in service_q, True)
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
            gesehen.append(fx.get("shop"))
        if exp.get("challenge"):
            check("fixture %s challenge" % name, core.detect_challenge(html.lower()), True)
            continue
        st = core.extract_structured(html)
        check("fixture %s ist konsole" % name, core.pruefe_nur_konsole(html, st), True)
        for feld in ("preis", "condition", "seller", "verfuegbar", "sofort"):
            if feld not in exp: continue
            if feld == "verfuegbar":
                wert = core.pruefe_verfuegbar(html, st)
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

    g = main.layout_geometrie(1280, 800)
    check("Layout Tablet quer", g["wide"], True)
    check("Layout Tablet zwei Spalten", g["panel_x"] + g["panel_w"], 1280)
    check("Layout Tablet Panel gedeckelt", g["panel_w"] <= 460, True)
    check("Layout Tablet Trefferflaeche", g["results_h"] >= 240, True)

    check("Layout Foldable quer", main.layout_geometrie(884, 700)["wide"], True)
    check("Layout Handy quer bleibt kompakt",
          main.layout_geometrie(800, 360)["wide"], False)
    check("Layout Tablet hoch bleibt einspaltig",
          main.layout_geometrie(800, 1280)["wide"], False)

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


if __name__ == "__main__":
    try:
        main_tests()
        retry_tests()
        radar_tests()
        progress_tests()
        service_tests()
        feature_tests()
        adaptive_boot_tests()
        fixture_tests()
        capture_helper_tests()
        spec_tests()
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
