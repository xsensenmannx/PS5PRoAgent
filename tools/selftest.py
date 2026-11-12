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
    check("insets ohne android", main.android_insets(), (0.0, 0.0))

    # Meta-Preis-Fallback
    check("meta preis", core.extract_meta_preis(
        '<meta property="product:price:amount" content="899,00">'), 899.0)
    check("meta preis im text", core.extract_meta_preis("<p>Preis: 1.049,00 €</p>"), 1049.0)
    check("meta preis unter minimum", core.extract_meta_preis("<p>Preis: 99,00 €</p>"), None)
    check("meta preis vierstellig", core.extract_meta_preis(
        "<p>Preis: 1099,00 €</p>"), 1099.0)

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

    404/410 bringen bei jedem User-Agent dasselbe Ergebnis: drei Versuche mit
    0,4 s + 2 s + 5 s Pause werfen pro umgezogenem Haendler rund 7 s Scan-Zeit
    weg. 5xx/Timeout muessen dagegen weiter probiert werden.
    """
    echt = core._try_url
    echt_zeit = core.time
    # Nur sleep ersetzen, damit der Test nicht wirklich wartet.
    core.time = types.SimpleNamespace(sleep=lambda s: None)
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
        except RuntimeError:
            pass
        check("403 dreimal probiert", len(calls), 3)
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
    def fake(h):
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
    check("spec version", c.get("app", "version"), "1.1")
    check("spec versionCode", c.get("app", "android.numeric_version"), "2")
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
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        main_tests()
        retry_tests()
        radar_tests()
        service_tests()
        feature_tests()
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
