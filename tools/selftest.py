"""Logiktests fuer main.py - laufen ohne Kivy und ohne Android.

Prueft die Teile, die ueber richtig/falsch entscheiden: Preis-Parsing, JSON-LD,
Verfuegbarkeit, Bot-Schutz, Klassifizierung, Haendlerdaten.

    python3 tools/selftest.py

Exit-Code 0 = alles gruen. Wird in .github/workflows/build-apk.yml als Gate
vor dem APK-Build ausgefuehrt, damit ein kaputtes Parsing nie in die APK geht.
"""
import configparser
import os
import re
import sys
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
    _mod("kivy.uix.togglebutton", ToggleButton=_ToggleButton)
    _mod("kivy.uix.widget", Widget=_W)
    _mod("kivy.animation", Animation=_Animation)
    _mod("kivy.utils", get_color_from_hex=_get_color_from_hex, platform="linux")


_stub_kivy()
import main  # noqa: E402

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
    check("parse 1.299,00", main.parse_preis_str("1.299,00 €"), 1299.0)
    check("parse 799,99", main.parse_preis_str("799,99"), 799.99)
    check("parse EUR 1.199,00", main.parse_preis_str("EUR 1.199,00"), 1199.0)
    check("parse 1.299,5", main.parse_preis_str("1.299,5"), 1299.5)
    check("parse 1099,00 vierstellig", main.parse_preis_str("1099,00 €"), 1099.0)
    check("parse 1.099 Tausenderpunkt", main.parse_preis_str("1.099 €"), 1099.0)
    check("parse 2.099,90", main.parse_preis_str("2.099,90"), 2099.9)
    check("parse 1.5 bleibt dezimal", main.parse_preis_str("1.5"), 1.5)
    check("parse 799,- ohne Cent", main.parse_preis_str("799,-"), 799.0)
    check("parse 799,– Halbgeviertstrich", main.parse_preis_str("799,–"), 799.0)
    check("parse 1.299,-- ohne Cent", main.parse_preis_str("1.299,--"), 1299.0)
    check("parse 1.299,00 mit Sternchen", main.parse_preis_str("1.299,00 €*"), 1299.0)
    check("parse (799,00 €) in Klammern", main.parse_preis_str("(799,00 €)"), 799.0)
    check("parse ohne Zahl", main.parse_preis_str("n/a"), None)
    check("format 1299.5", main.format_preis(1299.5), "1.299,50 €")
    check("format 799", main.format_preis(799.0), "799,00 €")

    # Klassifizierung
    check("classify unavail", main.classify(False, 799, 900), "unavail")
    check("classify unknown", main.classify(True, None, 900), "unknown")
    check("classify hit", main.classify(True, 899, 900), "hit")
    check("classify expensive", main.classify(True, 901, 900), "expensive")
    check("classify max offen", main.classify(True, 5000, None), "hit")

    # JSON-LD
    st = main.extract_structured(HTML_OK)
    check("jsonld ist_konsole", st["ist_konsole"], True)
    check("jsonld preis", st["preis"], 799.99)
    check("jsonld verfuegbar", st["verfuegbar"], True)
    check("pruefe_nur_konsole", main.pruefe_nur_konsole(HTML_OK, st), True)
    check("pruefe_verfuegbar", main.pruefe_verfuegbar(HTML_OK, st), True)
    check("jsonld outofstock", main.extract_structured(
        HTML_OK.replace("InStock", "OutOfStock"))["verfuegbar"], False)
    check("jsonld ausschluss zubehoer", main.extract_structured(
        HTML_OK.replace("(E-Chassis)", "DualSense Edge Controller"))["ist_konsole"], False)
    check("nur_konsole ohne product", main.pruefe_nur_konsole(
        "<html><body>PlayStation 5 Pro 2 TB Uebersicht</body></html>", {}), True)
    check("nur_konsole fremdprodukt", main.pruefe_nur_konsole("<html>xbox</html>", {}), False)

    # Meta-Preis-Fallback
    check("meta preis", main.extract_meta_preis(
        '<meta property="product:price:amount" content="899,00">'), 899.0)
    check("meta preis im text", main.extract_meta_preis("<p>Preis: 1.049,00 €</p>"), 1049.0)
    check("meta preis unter minimum", main.extract_meta_preis("<p>Preis: 99,00 €</p>"), None)
    check("meta preis vierstellig", main.extract_meta_preis(
        "<p>Preis: 1099,00 €</p>"), 1099.0)

    # Bot-Schutz und Verfuegbarkeit
    check("challenge erkannt", main.detect_challenge("just a moment..."), True)
    check("kein challenge", main.detect_challenge("<html>shop</html>"), False)
    check("verfuegbar negativ", main.pruefe_verfuegbar(
        "nicht verfügbar ausverkauft", {"verfuegbar": None}), False)
    check("verfuegbar positiv", main.pruefe_verfuegbar(
        "in den warenkorb jetzt kaufen", {"verfuegbar": None}), True)

    # Kuerzel
    check("initials PS Direct", main.initials_for("PS Direct DE"), "PS")
    check("initials MediaMarkt", main.initials_for("MediaMarkt AT"), "MM")
    check("initials Amazon", main.initials_for("Amazon DE"), "AM")
    check("initials Notebooksbilliger", main.initials_for("Notebooksbilliger"), "NB")

    # Haendlerdaten
    names = [h["name"] for h in main.HAENDLER]
    check("haendler eindeutig", len(names), len(set(names)))
    check("haendler https", all(u.startswith("https://")
                                for h in main.HAENDLER for u in h["urls"]), True)
    check("haendler feld vollstaendig", all(
        h.get("name") and h.get("land") in ("DE", "AT") and h.get("urls")
        for h in main.HAENDLER), True)
    # Land und Domain muessen zusammenpassen. "Aetka AT" auf aetka.de war genau
    # so ein Datenfehler: der AT-Filter zeigte damit einen deutschen Shop.
    # Ausnahmen mit Grund: PS Direct fuehrt DE und AT unter derselben .com-Domain,
    # Computeruniverse ist ein deutscher Shop auf .net.
    ausnahmen = ("direct.playstation.com", "www.computeruniverse.net")
    falsch = []
    for h in main.HAENDLER:
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

    404/410 bringen bei jedem User-Agent dasselbe Ergebnis: drei Versuche mit
    0,4 s + 2 s + 5 s Pause werfen pro umgezogenem Haendler rund 7 s Scan-Zeit
    weg. 5xx/Timeout muessen dagegen weiter probiert werden.
    """
    echt = main._try_url
    echt_zeit = main.time
    # Nur sleep ersetzen, damit der Test nicht wirklich wartet.
    main.time = types.SimpleNamespace(sleep=lambda s: None)
    try:
        calls = []
        main._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 404"))[1]
        try:
            main.fetch_html_multi(["https://example.invalid"])
            fehler = None
        except RuntimeError as e:
            fehler = str(e)
        check("404 Fehlertext", fehler, "HTTP 404")
        check("404 nur ein Versuch", len(calls), 1)

        calls.clear()
        main._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 500"))[1]
        try:
            main.fetch_html_multi(["https://example.invalid"])
        except RuntimeError:
            pass
        check("500 dreimal probiert", len(calls), 3)

        calls.clear()
        main._try_url = lambda u, a, p=None: (calls.append(a), (None, "HTTP 403"))[1]
        try:
            main.fetch_html_multi(["https://example.invalid"])
        except RuntimeError:
            pass
        check("403 dreimal probiert", len(calls), 3)
    finally:
        main._try_url = echt
        main.time = echt_zeit


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


def spec_tests():
    """Der Build-Pin entscheidet ueber Erfolg oder Abbruch - deshalb geprueft.

    p4a baut ohne Pin CPython 3.14; Cython 0.29.36 (fest im p4a-Recipe) und
    Kivy 2.3.0 koennen nur bis 3.12. Ausserdem verlangt p4a, dass python3 und
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
    check("spec kivy 2.3.0", "kivy==2.3.0" in req, True)
    check("spec api 34", c.get("app", "android.api"), "34")


if __name__ == "__main__":
    try:
        main_tests()
        retry_tests()
        radar_tests()
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
