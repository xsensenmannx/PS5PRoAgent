"""Erzeugt die fünf Store-Screenshots der Hilfe-App als echte App-Aufnahmen.

Läuft mit Kivy im Fenster (1080x1920, Dichte 2.25) und speichert pro Reiter
einen Screenshot unter docs/store/hilfe/screenshots/. Die Inhalte entstehen
über die normalen UI-Aktionen (senden, planen, prüfen), nicht aus Mockups.

    python tools/hilfe_screenshots.py
"""
import glob
import os
import sys

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_METRICS_DENSITY", "2.25")

from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", "1080")
Config.set("graphics", "height", "1920")
Config.set("graphics", "resizable", "0")

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
BASIS = os.path.dirname(HIER)
APP = os.path.join(BASIS, "support_app")
ZIEL = os.path.join(BASIS, "store", "hilfe", "assets", "phone")
sys.path.insert(0, APP)

import main  # noqa: E402

# Reihenfolge = Reihenfolge im Store.
AUFNAHMEN = (
    ("chat", "01-fragen"),
    ("suche", "02-suche"),
    ("diag", "03-diagnose"),
    ("themen", "04-themen"),
    ("ki", "05-ki"),
)


def inhalte_fuellen(app):
    app.chat.eingabe.text = "Kein Alarm trotz Treffer"
    app.chat.senden()
    app.suche.eingabe.text = "unter 700, nur Amazon, nur neu, nur bestätigte"
    app.suche.planen()
    app.diag.eingabe.text = main.support_core.BEISPIEL_BERICHT
    app.diag.pruefen()
    app.ki.eingabe.text = "Warum findet der Scan bei MediaMarkt nichts?"


class Aufnahme(main.HilfeApp):
    def on_start(self):
        super().on_start()
        inhalte_fuellen(self)
        Clock.schedule_once(lambda *_: self.oben_ausrichten(), 0.6)
        Clock.schedule_once(lambda *_: self.schritt(0), 1.2)

    def oben_ausrichten(self):
        """Inhalt oben statt am unteren Rand zeigen (sonst leere Fläche)."""
        for screen, _ in AUFNAHMEN:
            bereich = getattr(self, screen, None)
            liste = getattr(bereich, "liste", None)
            sv = getattr(bereich, "sv", None)
            if liste is None or sv is None:
                continue
            liste.unbind(minimum_height=liste.setter("height"))
            liste.height = max(liste.minimum_height, sv.height)
            sv.scroll_y = 1

    def schritt(self, nummer):
        if nummer >= len(AUFNAHMEN):
            self.stop()
            return
        screen, datei = AUFNAHMEN[nummer]
        self.gehe(screen)
        Clock.schedule_once(lambda *_: self.sichern(datei, nummer), 0.9)

    def sichern(self, datei, nummer):
        pfad = Window.screenshot(name=os.path.join(ZIEL, datei + ".png"))
        ziel = os.path.join(ZIEL, datei + ".png")
        os.replace(pfad, ziel)
        print("gespeichert:", ziel, Window.size)
        Clock.schedule_once(lambda *_: self.schritt(nummer + 1), 0.3)


if __name__ == "__main__":
    os.makedirs(ZIEL, exist_ok=True)
    for alt in glob.glob(os.path.join(ZIEL, "*.png")):
        os.remove(alt)
    Aufnahme().run()
