#!/usr/bin/env python3
"""Messt den JSON-LD-Teilabruf gegen den vollstaendigen HTML-Pfad.

Der Test laeuft gegen einen lokalen Server. Nur so ist der Zeitpunkt des
Verfuegbarkeitswechsels bekannt; echte Shops lassen sich nicht terminieren.
Gemessen werden:

  * gelesene Bytes pro Pruefung
  * Dauer pro Pruefung (p50/p95)
  * Erkennungsluecke bei einem Zustandswechsel (p50/p95)
  * Requests pro Pruefung und pro Runde

Es werden keine Shops kontaktiert und keine Schutzmechanismen umgangen.

    python tools/measure_fastpath.py
    python tools/measure_fastpath.py --runs 7 --interval 0.5 --shops 6
"""
import argparse
import os
import statistics
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scan_core as core  # noqa: E402

PAGE_BYTES = 1_000_000
BLOCK = 16 * 1024
FAST_NAME = "MediaMarkt DE"
HTML_NAME = "Amazon DE"


def _page(available):
    """Eine Seite mit Produkt-JSON-LD am Anfang und viel Fuellstoff danach."""
    avail = "InStock" if available else "OutOfStock"
    ld = ('<script type="application/ld+json">'
          '{"@type":"Product","name":"Sony PlayStation 5 Pro 2 TB",'
          '"sku":"3018022","gtin13":"0711719024040",'
          '"offers":{"@type":"Offer","price":"899.99",'
          '"priceCurrency":"EUR","availability":"%s"}}'
          '</script>') % avail
    kopf = ('<!doctype html><html><head><title>PS5 Pro 2 TB</title>%s'
            '</head><body>' % ld)
    rest = "x" * max(0, PAGE_BYTES - len(kopf) - 7)
    return (kopf + rest + "</body></html>").encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = self.server.body
        with self.server.lock:
            self.server.requests += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            for i in range(0, len(body), BLOCK):
                stueck = body[i:i + BLOCK]
                self.wfile.write(stueck)
                with self.server.lock:
                    self.server.sent += len(stueck)
                # 16 KB/ms ~ 16 MB/s: genug, um den Unterschied zwischen
                # 192 KB und 1 MB sichtbar zu machen, ohne den Test zu ziehen.
                time.sleep(0.001)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler):
        super().__init__(addr, handler)
        self.body = _page(False)
        self.requests = 0
        self.sent = 0
        self.lock = threading.Lock()

    def set_available(self, wert):
        self.body = _page(bool(wert))


def _scan(name, url):
    h = {"name": name, "land": "DE", "urls": [url]}
    t0 = time.perf_counter()
    r = core.scan_einen(h)
    return r, time.perf_counter() - t0


def _p95(xs):
    xs = sorted(xs)
    if not xs:
        return 0.0
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]


def _bytes_text(n):
    return f"{int(n):,}".replace(",", ".")


def _sekunden(xs):
    p50 = statistics.median(xs) if xs else 0.0
    return p50, _p95(xs)


def _fixed(name, url, runs):
    """Bytes und Dauer ohne Zustandswechsel."""
    bytes_, zeiten = [], []
    for _ in range(runs):
        r, dt = _scan(name, url)
        if r is None:
            raise RuntimeError("Scan lieferte None")
        bytes_.append(int(r.get("bytes") or 0))
        zeiten.append(dt)
    return bytes_, zeiten


def _gap(server, name, url, interval, runs):
    """Erkennungsluecke: Wechsel -> erster Treffer.

    Der Wechsel wird in verschiedenen Phasen des Taktfensters gesetzt
    (0 ... 0,8 * Intervall), damit nicht immer sofort gepollt wird.
    """
    gaps = []
    for i in range(runs):
        server.set_available(False)
        # Grundzustand sicherstellen, damit der Wechsel wirklich ein Wechsel ist.
        for _ in range(20):
            r, _ = _scan(name, url)
            if r is not None and r.get("klass") == "unavail":
                break
            time.sleep(0.01)
        phase = interval * (i / max(1, runs))
        server.set_available(True)
        t0 = time.perf_counter()
        if phase:
            time.sleep(phase)
        ende = t0 + interval * 3 + 2.0
        while time.perf_counter() < ende:
            r, _ = _scan(name, url)
            if r is not None and r.get("klass") == "hit":
                gaps.append(time.perf_counter() - t0)
                break
            time.sleep(interval)
        server.set_available(False)
    return gaps


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=5,
                    help="Laeufe fuer Bytes/Dauer und Erkennungsluecke (Standard 5)")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="Polling-Intervall in Sekunden (Standard 1,0)")
    ap.add_argument("--shops", type=int, default=6,
                    help="Shops pro Runde fuer die Request-Rechnung (Standard 6)")
    args = ap.parse_args(argv)

    # Kein Proxy fuer 127.0.0.1; keine Schreibzugriffe ins Home-Verzeichnis.
    os.environ.pop("PS5_PROXY", None)
    core.set_data_dir(tempfile.mkdtemp(prefix="fastpath-"))

    server = _Server(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/produkt"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # Ein Warmlauf pro Pfad (Import, Verbindungsaufbau, Parser-Caches).
        _scan(FAST_NAME, url)
        _scan(HTML_NAME, url)

        fast_bytes, fast_zeiten = _fixed(FAST_NAME, url, args.runs)
        html_bytes, html_zeiten = _fixed(HTML_NAME, url, args.runs)

        fast_gaps = _gap(server, FAST_NAME, url, args.interval, args.runs)
        html_gaps = _gap(server, HTML_NAME, url, args.interval, args.runs)

        with server.lock:
            server.requests = 0
            server.sent = 0
        for _ in range(max(1, args.shops)):
            _scan(FAST_NAME, url)
        req_runde = server.requests
        sent_runde = server.sent

        b_fast = int(statistics.median(fast_bytes))
        b_html = int(statistics.median(html_bytes))
        d_fast, d_fast95 = _sekunden(fast_zeiten)
        d_html, d_html95 = _sekunden(html_zeiten)
        g_fast, g_fast95 = _sekunden(fast_gaps)
        g_html, g_html95 = _sekunden(html_gaps)
        sparbar = 100.0 * (1.0 - b_fast / b_html) if b_html else 0.0
        takt = 30.0
        req_min = args.shops * (60.0 / takt)

        print()
        print("JSON-LD-Teilabruf gegen vollstaendige HTML-Seite")
        print("=" * 62)
        print(f"Testseite: {_bytes_text(PAGE_BYTES)} Bytes, JSON-LD bei ~0,4 KB")
        print()
        print(f"{'Pfad':<12}{'Bytes/Pruefung':>16}{'Dauer p50':>12}{'Dauer p95':>12}")
        print(f"{'JSON-LD':<12}{_bytes_text(b_fast):>16}{d_fast:>11.3f}s{d_fast95:>11.3f}s")
        print(f"{'HTML':<12}{_bytes_text(b_html):>16}{d_html:>11.3f}s{d_html95:>11.3f}s")
        print(f"{'Ersparnis':<12}{sparbar:>15.1f}%")
        print()
        print(f"Erkennungsluecke (Intervall {args.interval:.2f} s, {args.runs} Laeufe)")
        print(f"{'JSON-LD':<12}p50 {g_fast:.3f} s   p95 {g_fast95:.3f} s")
        print(f"{'HTML':<12}p50 {g_html:.3f} s   p95 {g_html95:.3f} s")
        print()
        print("Requests")
        print(f"pro Pruefung: 1 (JSON-LD) / 1 (HTML)")
        print(f"pro Runde mit {args.shops} Shops: {req_runde} Requests, "
              f"{_bytes_text(sent_runde)} Bytes serverseitig geschrieben")
        print(f"bei {takt:.0f}-s-Runden: {req_min:.0f} Requests/Minute")
        print()
        print("PS Direct: alt 2 Requests (301 + 200), neu 1 (direktes Ziel).")
        print("Der Teilabruf senkt Bytes und Parserzeit, nicht die Request-Zahl.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
