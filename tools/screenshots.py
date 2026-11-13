"""Erzeugt Screenshots und das Scan-GIF aus der echten Kivy-Oberflaeche.

Laeuft nur unter Windows: ``Window.screenshot()`` liefert auf diesem Rechner
schwarze Bilder, deshalb wird das Fenster ueber sein HWND gesucht und per
``ImageGrab`` aufgenommen.

Beispiele (Groessen in Pixeln; Kivy rechnet auf Windows mit Dichte 1.0, also
entspricht 620x380 auch 620x380 dp):

    python tools/screenshots.py --scene main   --size 510x1020 --out docs/screenshots/hochformat.png
    python tools/screenshots.py --scene main   --size 620x380  --out docs/screenshots/querformat-kompakt.png
    python tools/screenshots.py --scene detail --size 510x1020 --out docs/screenshots/detail.png
    python tools/screenshots.py --scene scan   --size 320x640  --out docs/screenshots/scan.gif

Die Szenen benutzen feste Trefferdaten und ersetzen alle Netzwerk- und
Systemaufrufe; ein Lauf braucht weder Internet noch echte Shop-Antworten.
"""
import argparse
import ctypes
from ctypes import wintypes
import os
import shutil
import sys
import tempfile
import time

P = argparse.ArgumentParser(description=__doc__)
P.add_argument("--scene", required=True, choices=["main", "detail", "scan"])
P.add_argument("--size", required=True, help="Breite x Hoehe in Pixeln, z. B. 620x380")
P.add_argument("--out", required=True, help="Ziel-Datei (.png oder .gif)")
P.add_argument("--frames", type=int, default=16, help="Frames fuer das Scan-GIF")
P.add_argument("--interval", type=float, default=0.14, help="Sekunden pro GIF-Frame")
P.add_argument("--gif-width", type=int, default=0,
               help="GIF auf diese Breite skalieren (0 = Aufnahmebreite)")
P.add_argument("--gif-colors", type=int, default=128,
               help="Farben pro GIF-Frame (256 = volle Palette)")
ARGS = P.parse_args()

W, H = (int(v) for v in ARGS.size.lower().split("x"))
TITLE = "PS5PRO_SHOT"
IS_GIF = ARGS.out.lower().endswith(".gif")

if not sys.platform.startswith("win"):
    raise SystemExit("tools/screenshots.py laeuft nur unter Windows (HWND-Aufnahme).")

os.environ["KIVY_NO_ARGS"] = "1"

from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", str(W))
Config.set("graphics", "height", str(H))
Config.set("graphics", "resizable", "0")
Config.set("graphics", "borderless", "1")

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main  # noqa: E402
import scan_core  # noqa: E402

USER32 = ctypes.windll.user32
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040

BASIS = {
    "land": "DE", "zeit": "12:04", "condition": "new", "sofort": True,
    "signal": "jsonld", "verfuegbarkeit": "InStock",
}


def ergebnis(name, preis, klass, **extra):
    r = {**BASIS, "haendler": name, "preis": preis, "klass": klass,
         "seller": name, "url": f"https://example.invalid/{name.lower()}",
         "_is_new": False, "_prev": None}
    r.update(extra)
    return r


def treffer():
    return {
        "Amazon DE": ergebnis("Amazon DE", 799.0, "hit", _is_new=True, _prev=849.0),
        "MediaMarkt": ergebnis("MediaMarkt", 819.0, "hit", _prev=829.0),
        "Otto": ergebnis("Otto", 849.0, "hit"),
        "Saturn": ergebnis("Saturn", 899.0, "hit"),
        "Cyberport": ergebnis("Cyberport", None, "unavail",
                              sofort=False, seller="Cyberport",
                              verfuegbarkeit="OutOfStock"),
    }


def client_box():
    hwnd = USER32.FindWindowW(None, TITLE)
    if not hwnd:
        raise RuntimeError("Fenster nicht gefunden: " + TITLE)
    USER32.SetForegroundWindow(hwnd)
    USER32.BringWindowToTop(hwnd)
    # Oben links parken, damit die Taskbar unten nichts verdeckt.
    USER32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_SHOWWINDOW)
    USER32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    time.sleep(0.12)
    rect = wintypes.RECT()
    USER32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = wintypes.POINT(0, 0)
    USER32.ClientToScreen(hwnd, ctypes.byref(pt))
    return hwnd, (pt.x, pt.y, pt.x + rect.right, pt.y + rect.bottom)


def grab(path):
    from PIL import ImageGrab
    hwnd, box = client_box()
    img = ImageGrab.grab(bbox=box)
    USER32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    print("SHOT", path, img.size)


def frames_to_gif(frames, out):
    from PIL import Image
    bilder = [Image.open(p).convert("RGB") for p in frames]
    if ARGS.gif_width and bilder[0].width != ARGS.gif_width:
        hoehe = round(bilder[0].height * ARGS.gif_width / bilder[0].width)
        bilder = [b.resize((ARGS.gif_width, hoehe), Image.LANCZOS) for b in bilder]
    if 2 <= ARGS.gif_colors < 256:
        # 128 Farben sind bei der kleinen Anzeige nicht zu unterscheiden und
        # sparen rund ein Fuenftel der Dateigroesse.
        bilder = [b.quantize(colors=ARGS.gif_colors, method=Image.MEDIANCUT)
                  for b in bilder]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bilder[0].save(out, save_all=True, append_images=bilder[1:],
                   duration=int(ARGS.interval * 1000), loop=0, optimize=True)
    print("GIF", out, f"{len(bilder)} Frames", f"{os.path.getsize(out) // 1024} KB")


class ShotApp(App):
    def build(self):
        return main.RootLayout()

    def on_start(self):
        self.ui = self.root.main_ui
        Window.set_title(TITLE)
        Clock.schedule_once(self.prepare, 0.5)

    def prepare(self, _dt):
        if ARGS.scene == "main":
            self.zeige_treffer()
            Clock.schedule_once(lambda _d: self.fertig(), 0.6)
        elif ARGS.scene == "detail":
            self.zeige_treffer()
            Clock.schedule_once(self.oeffne_detail, 0.4)
        else:
            self.start_scan()
            # Kurz Vorlauf: der erste Frame soll den bereits gezeichneten
            # Radar zeigen, nicht den leeren Zustand direkt nach dem Layout.
            Clock.schedule_once(
                lambda _d: Clock.schedule_interval(self.scan_frame, ARGS.interval),
                0.45)

    def zeige_treffer(self):
        ui = self.ui
        ui.auto_scan = False
        ui.max_preis = 900.0
        ui.max_preis_chip.text = ui._max_text()
        ui.scanned = treffer()
        ui._rerender()
        for name, r in ui.scanned.items():
            ui._update_blip(name, r["klass"])
        hits = [r for r in ui.scanned.values() if r["klass"] == "hit"]
        ui.results_status.text = f"{len(hits)} TREFFER · BEST 799 € · 12:04"
        ui.results_status.color = main.CARD_STATUS["hit"]
        ui.results_count.text = f"{len(hits)}/{len(ui.scanned)}"
        ui.results_count.color = main.CARD_STATUS["hit"]
        ui._update_radar_hud()
        self.root.do_layout()
        fl = main.radar_flaeche(ui.radar.width, ui.radar.height,
                                ui.radar.reserve_bottom, ui.radar.reserve_top)
        print("RADAR pos", ui.radar.pos, "size", ui.radar.size,
              "flaeche", fl, "panel", ui.results_panel.pos,
              ui.results_panel.size)
        if fl is None:
            raise RuntimeError("Radarflaeche ist leer - Layout pruefen")

    def oeffne_detail(self, _dt):
        serie = [["2026-11-01T10:00:00", 849.0],
                 ["2026-11-05T18:30:00", 829.0],
                 ["2026-11-09T09:15:00", 819.0],
                 ["2026-11-13T12:04:00", 799.0]]
        self.ui._open_detail(treffer()["Amazon DE"], serie)
        Clock.schedule_once(lambda _d: self.fertig(), 0.8)

    def start_scan(self):
        ui = self.ui
        ui.auto_scan = False
        ui.max_preis = 900.0
        ui.max_preis_chip.text = ui._max_text()
        ui.scanned = {}
        ui._clear_results()
        ui.radar.blips = []
        ui.scanning = True
        ui.radar.scanning = True
        ui.scan_btn.text = "STOP"
        ui._scan_done = 0
        ui._scan_total = len(scan_core.HAENDLER)
        ui._scan_t0 = time.time()
        self.frames = 0
        self.reihe = list(treffer().items())
        # Ersten Treffer sofort zeigen, damit der Startframe nicht den
        # Platzhalter "SYSTEM BEREIT" traegt.
        name, r = self.reihe[0]
        ui.scanned[name] = r
        ui._update_blip(name, r["klass"])
        self.index = 1
        ui._rerender()
        ui.results_status.text = main.scan_fortschritt(1, ui._scan_total, 1, 0)
        ui.results_count.text = f"1/{ui._scan_total}"

    def scan_frame(self, _dt):
        ui = self.ui
        self.frames += 1
        anteil = min(1.0, self.frames / float(ARGS.frames))
        ziel = int(round(anteil * len(self.reihe)))
        while self.index < ziel:
            name, r = self.reihe[self.index]
            ui.scanned[name] = r
            ui._update_blip(name, r["klass"])
            self.index += 1
        done = max(1, int(round(anteil * len(scan_core.HAENDLER))))
        hits = sum(1 for x in ui.scanned.values() if x["klass"] == "hit")
        ui._scan_done = done
        ui.results_status.text = main.scan_fortschritt(
            done, len(scan_core.HAENDLER), hits, time.time() - ui._scan_t0)
        ui.results_count.text = f"{done}/{len(scan_core.HAENDLER)}"
        ui._update_radar_hud()
        ui._rerender()
        self.root.do_layout()
        # Das Bild auf dem Schirm zeigt den Stand des vorherigen Ticks.
        if self.frames > 1:
            grab(os.path.join(self.frame_dir, f"frame{self.frames - 1:02d}.png"))
        if self.frames >= ARGS.frames:
            Clock.unschedule(self.scan_frame)
            Clock.schedule_once(self.scan_settle, 0.25)

    def scan_settle(self, _dt):
        grab(os.path.join(self.frame_dir, f"frame{ARGS.frames:02d}.png"))
        bilder = sorted(os.path.join(self.frame_dir, n)
                        for n in os.listdir(self.frame_dir) if n.endswith(".png"))
        frames_to_gif(bilder, ARGS.out)
        self.stop()

    def fertig(self):
        grab(ARGS.out)
        self.stop()


def run():
    tmp = tempfile.mkdtemp(prefix="ps5pro-shot-")
    scan_core.set_data_dir(tmp)
    scan_core.Settings().set("onboarded", True)
    main.aktualisiere_shop_config = lambda *a, **k: 0
    main.lade_shop_config = lambda *a, **k: None
    main.notify = lambda *a, **k: True
    main.open_url = lambda url: True
    main.share_text = lambda *a, **k: True
    main.MainUI._shop_config_bg = lambda self, force=False: 0
    App_ = ShotApp
    App_.frame_dir = tempfile.mkdtemp(prefix="ps5pro-frames-", dir=tmp)
    try:
        App_().run()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run()
