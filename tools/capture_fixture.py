#!/usr/bin/env python3
"""Minimale Shop-Fixtures aus einer echten Seite erzeugen.

Der Helfer nutzt denselben Parser wie die App, damit eine Fixture genau den
Vertrag festhaelt, den scan_einen spaeter auswertet. Er speichert nur Titel,
relevante Meta-Tags, JSON-LD und Text-/Attribut-Ausschnitte, nicht die komplette
Shop-Seite.

Beispiele:

    python3 tools/capture_fixture.py --shop "Amazon DE"
    python3 tools/capture_fixture.py --shop "Amazon DE" --input page.html
    python3 tools/capture_fixture.py --all --force
    python3 tools/capture_fixture.py --check

Ohne --input wird die eingebaute Shop-URL ueber denselben Netzwerkpfad wie die
App geladen. Der Helfer ist ein bewusst manueller Schritt: Die CI testet die
Fixtures offline und braucht keinen Shop-Zugriff.
"""
import argparse
import datetime
import html as html_lib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scan_core  # noqa: E402  (Pfad wird oben fuer den direkten Aufruf gesetzt)

FIXTURE_DIR = os.path.join(ROOT, "tools", "fixtures")
MAX_FIXTURE_BYTES = 32 * 1024
MAX_FULL_BYTES = 64 * 1024
MAX_INPUT_BYTES = scan_core.MAX_HTML_BYTES
MAX_JSONLD_BYTES = 12 * 1024
MAX_TEXT_BYTES = 6000
MAX_TAGS = 24
MAX_META = 20

JSONLD_RE = re.compile(
    r'<script[^>]*\btype\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S)
META_RE = re.compile(r"<meta\b[^>]*>", re.I)
TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
RELEVANT_META_RE = re.compile(
    r"(?:price|preis|product|availability|og:title|og:type|twitter:title)", re.I)
RELEVANT_TAG_RE = re.compile(
    r"<[^>]*(?:price|preis|availability|verfüg|verfueg|stock|lager|"
    r"warenkorb|kaufen|liefer)[^>]*>", re.I)
STRIP_BLOCK_RE = re.compile(
    r"<(?:script|style|noscript|svg)\b[^>]*>.*?</(?:script|style|noscript|svg)\s*>",
    re.I | re.S)
TEXT_KEYS = (
    "playstation", "ps5", "2 tb", "2tb", "€", "eur", "preis",
    "lager", "verfüg", "verfueg", "ausverkauft", "vorbestell",
    "warenkorb", "kaufen", "liefer", "sofort",
)


class CaptureError(RuntimeError):
    """Die Seite liess sich nicht in eine brauchbare Fixture ueberfuehren."""


def slug(name):
    """Stabiler ASCII-Dateiname, auch fuer 'shöpping.at' und Umlaute."""
    s = unicodedata.normalize("NFKD", str(name))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "shop"


def fixture_dateiname(shop):
    return "shop-%s.json" % slug(shop["name"])


def shop_finden(name):
    for shop in scan_core.HAENDLER:
        if shop["name"] == name:
            return shop
    raise CaptureError("Unbekannter Shop: %s" % name)


def url_erlaubt(url):
    """Nur die bereits eingebauten Shop-Hosts, nur HTTPS, kein Fremdziel."""
    try:
        return scan_core._validiere_url(url, scan_core._erlaubte_hosts())
    except Exception:
        return False


def _text_ausschnitte(html, max_bytes=MAX_TEXT_BYTES):
    """Nur Textfenster mit Produkt-/Preis-/Lieferbegriffen behalten."""
    text = STRIP_BLOCK_RE.sub(" ", html)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    low = text.lower()
    spans = []
    for key in TEXT_KEYS:
        start = 0
        while len(spans) < 32:
            i = low.find(key, start)
            if i < 0:
                break
            spans.append((max(0, i - 80), min(len(text), i + 180)))
            start = i + len(key)
    if not spans:
        return text[:max_bytes]
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out = " ".join(text[a:b] for a, b in merged)[:max_bytes]
    return out


def minimiere_html(html, full=False):
    """Entfernt alles, was der Parser nicht fuer Preis/Produkt/Status braucht.

    Bei `full=True` wird die Seite nur auf MAX_FULL_BYTES gekuerzt. Das ist der
    Notausgang, wenn eine echte Seite mit den Ausschnitten nicht mehr identisch
    geparst wird.
    """
    if not isinstance(html, str) or not html:
        raise CaptureError("Leere HTML-Seite")
    if full:
        return html[:MAX_FULL_BYTES]

    parts = []
    m = TITLE_RE.search(html)
    if m:
        titel = re.sub(r"\s+", " ", html_lib.unescape(m.group(1))).strip()
        if titel:
            parts.append("<title>%s</title>" % html_lib.escape(titel))

    meta_count = 0
    for m in META_RE.finditer(html):
        tag = m.group(0)
        if RELEVANT_META_RE.search(tag):
            parts.append(tag)
            meta_count += 1
            if meta_count >= MAX_META:
                break

    for m in JSONLD_RE.finditer(html):
        raw = m.group(1).strip()
        if not raw:
            continue
        if len(raw) > MAX_JSONLD_BYTES:
            # Kompakt serialisieren, statt ein wichtiges JSON-LD abzuschneiden.
            try:
                raw = json.dumps(json.loads(raw), ensure_ascii=False,
                                 separators=(",", ":"))
            except Exception:
                continue
        if len(raw) <= MAX_JSONLD_BYTES:
            parts.append('<script type="application/ld+json">%s</script>' % raw)

    tag_count = 0
    for m in RELEVANT_TAG_RE.finditer(STRIP_BLOCK_RE.sub(" ", html)):
        tag = m.group(0)
        if tag.lower().startswith(("<script", "</")):
            continue
        parts.append(tag)
        tag_count += 1
        if tag_count >= MAX_TAGS:
            break

    text = _text_ausschnitte(html)
    if text:
        parts.append("<body>%s</body>" % html_lib.escape(text))

    out = "\n".join(parts)
    if not out:
        raise CaptureError("Keine verwertbaren Parser-Ausschnitte gefunden")
    if len(out.encode("utf-8")) > MAX_FIXTURE_BYTES:
        raise CaptureError(
            "Minimierte Fixture ist zu gross; mit --full oder einer kleineren "
            "Seite erneut versuchen")
    return out


def erwartung(html):
    """Leitet die erwarteten Parserwerte aus derselben HTML ab."""
    if scan_core.detect_challenge(html[:3000].lower()):
        raise CaptureError("Bot-Challenge statt Produktseite")
    st = scan_core.extract_structured(html)
    if not scan_core.pruefe_nur_konsole(html, st):
        raise CaptureError("Seite wird nicht als PS5 Pro 2 TB erkannt")
    preis = st.get("preis")
    if preis is None:
        preis = scan_core.extract_meta_preis(html)
    if preis is None:
        raise CaptureError("Kein Preis erkannt")
    verfuegbar = scan_core.pruefe_verfuegbar(html, st)
    sofort = st.get("sofort")
    if sofort is None and verfuegbar:
        sofort = scan_core.ist_sofort_verfuegbar(html)
    exp = {"ist_konsole": True, "preis": float(preis),
           "verfuegbar": bool(verfuegbar)}
    if st.get("condition"):
        exp["condition"] = st["condition"]
    if st.get("seller"):
        exp["seller"] = st["seller"]
    if sofort is not None:
        exp["sofort"] = bool(sofort)
    return exp


def baue_fixture(shop, html, url, captured=None, full=False):
    """Erzeugt und validiert das JSON-Objekt einer Fixture."""
    if not url_erlaubt(url):
        raise CaptureError("URL nicht auf einem bekannten Shop-Host: %s" % url)
    roh_erwartung = erwartung(html)
    mini = minimiere_html(html, full=full)
    mini_erwartung = erwartung(mini)
    if mini_erwartung != roh_erwartung:
        raise CaptureError(
            "Minimierung veraendert das Parser-Ergebnis; mit --full erneut "
            "versuchen")
    name = "shop-%s" % slug(shop["name"])
    return {
        "schema": 1,
        "name": name,
        "shop": shop["name"],
        "url": url,
        "captured": captured or datetime.date.today().isoformat(),
        "html": mini,
        "expect": roh_erwartung,
    }


def _html_aus_datei(pfad):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            html = f.read(MAX_INPUT_BYTES + 1)
    except OSError as e:
        raise CaptureError("HTML-Datei nicht lesbar: %s" % e)
    if len(html) > MAX_INPUT_BYTES:
        raise CaptureError("HTML-Datei ist groesser als das Parser-Limit")
    return html


def hole_html(url):
    """Laedt eine Seite ohne dauerhafte HTTP-Cache-Datei des Nutzers."""
    if not url_erlaubt(url):
        raise CaptureError("URL nicht auf einem bekannten Shop-Host: %s" % url)
    alt_dir = scan_core._data_dir()
    tmp = tempfile.mkdtemp(prefix="ps5pro-capture-")
    scan_core.set_data_dir(tmp)
    scan_core.reset_http_cache()
    try:
        html, _final, _cached, _meta = scan_core.fetch_mit_cache([url])
        if not html:
            raise CaptureError("Shop lieferte keinen HTML-Inhalt")
        if scan_core.detect_challenge(html[:3000].lower()):
            raise CaptureError("Bot-Challenge statt Produktseite")
        return html
    finally:
        scan_core.set_data_dir(alt_dir)
        scan_core.reset_http_cache()
        shutil.rmtree(tmp, ignore_errors=True)


def schreibe_fixture(shop, html, url, out_dir, force=False, dry_run=False,
                     full=False):
    ziel = os.path.join(out_dir, fixture_dateiname(shop))
    if os.path.exists(ziel) and not force:
        raise CaptureError("Fixture existiert bereits (--force): %s" % ziel)
    fixture = baue_fixture(shop, html, url, full=full)
    if dry_run:
        print("[dry-run] %s (%s Bytes)" % (ziel, len(fixture["html"])))
        return ziel
    os.makedirs(out_dir, exist_ok=True)
    tmp = ziel + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, ziel)
    print("[fixture] %s -> %s (%s Bytes)"
          % (shop["name"], ziel, len(fixture["html"])))
    return ziel


def pruefe_fixtures(out_dir=FIXTURE_DIR):
    """Prueft offline, dass fuer jeden Shop eine Fixture vorhanden ist."""
    fehlend = []
    for shop in scan_core.HAENDLER:
        pfad = os.path.join(out_dir, fixture_dateiname(shop))
        if not os.path.exists(pfad):
            fehlend.append(shop["name"])
            continue
        try:
            with open(pfad, encoding="utf-8") as f:
                fx = json.load(f)
            if fx.get("shop") != shop["name"]:
                fehlend.append(shop["name"])
        except Exception:
            fehlend.append(shop["name"])
    if fehlend:
        print("Fehlende/kaputte Fixtures (%s):" % len(fehlend))
        for name in fehlend:
            print("  -", name)
        return 1
    print("Fixtures vollstaendig: %s Shops" % len(scan_core.HAENDLER))
    return 0


def _argumente(argv=None):
    ap = argparse.ArgumentParser(
        description="Minimale Parser-Fixture aus einer Shop-Seite erzeugen")
    ap.add_argument("--shop", help="Exakter Name aus scan_core.HAENDLER")
    ap.add_argument("--all", action="store_true", help="alle 42 Shops aufnehmen")
    ap.add_argument("--input", help="bereits gespeicherte HTML-Datei statt Netz")
    ap.add_argument("--url", help="nur fuer einen Shop: alternative bekannte URL")
    ap.add_argument("--out-dir", default=FIXTURE_DIR)
    ap.add_argument("--force", action="store_true", help="vorhandene Fixture ersetzen")
    ap.add_argument("--dry-run", action="store_true", help="nur Ziel/Groesse zeigen")
    ap.add_argument("--full", action="store_true",
                    help="HTML nur kuerzen, wenn die Minimierung das Ergebnis aendert")
    ap.add_argument("--check", action="store_true",
                    help="nur pruefen, ob alle 42 Fixtures vorhanden sind")
    return ap.parse_args(argv)


def main(argv=None):
    args = _argumente(argv)
    if args.check:
        return pruefe_fixtures(args.out_dir)
    if args.all and args.shop:
        raise CaptureError("--all und --shop nicht kombinieren")
    if args.all and args.input:
        raise CaptureError("--input gehoert zu genau einem --shop")
    if args.all and args.url:
        raise CaptureError("--url gehoert zu genau einem --shop")
    if not args.all and not args.shop:
        raise CaptureError("--shop oder --all angeben")

    shops = scan_core.HAENDLER if args.all else [shop_finden(args.shop)]
    fehler = 0
    for shop in shops:
        try:
            url = args.url or shop["urls"][0]
            if not url_erlaubt(url):
                raise CaptureError("URL nicht erlaubt: %s" % url)
            html = (_html_aus_datei(args.input) if args.input
                    else hole_html(url))
            schreibe_fixture(shop, html, url, args.out_dir,
                             force=args.force, dry_run=args.dry_run,
                             full=args.full)
        except CaptureError as e:
            print("[fehler] %s: %s" % (shop["name"], e), file=sys.stderr)
            fehler += 1
        except Exception as e:
            print("[fehler] %s: %s" % (shop["name"], e), file=sys.stderr)
            fehler += 1
    return 1 if fehler else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CaptureError as e:
        print("[fehler] %s" % e, file=sys.stderr)
        sys.exit(2)
