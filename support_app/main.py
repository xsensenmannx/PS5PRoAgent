"""PS5 Pro Search Agent – Hilfe: Offline-Support als eigenständige App.

Kein Netzwerk, kein Konto, keine Telemetrie. Die Inhalte stecken in
``knowledge.py``, die Logik in ``support_core.py``; diese Datei ist nur die
Oberfläche.
"""
import os
import sys

# Kivy parst sonst die Kommandozeile, bevor unser Code sie sieht, und beendet
# sich bei --selftest/--smoke mit einer Usage-Meldung (Exitcode 2).
os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import search_assistant
import support_core
from knowledge import ENTRIES

BG = (0.043, 0.071, 0.125, 1)
PANEL = (0.075, 0.110, 0.180, 1)
MINE = (0.100, 0.220, 0.400, 1)
ACCENT = (0.184, 0.486, 0.965, 1)
TEXT = (0.900, 0.930, 0.980, 1)
MUTED = (0.600, 0.660, 0.760, 1)
WARN = (0.360, 0.130, 0.150, 1)
NOTE = (0.330, 0.240, 0.080, 1)

STUFE_FARBE = {"hoch": WARN, "mittel": NOTE, "info": PANEL}


class Bubble(Label):
    """Textblase mit Hintergrund; Höhe folgt dem umbrochenen Text."""

    def __init__(self, text="", mine=False, bg=None, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        super().__init__(text=text, **kwargs)
        self.halign = "left"
        self.valign = "top"
        self.padding = (dp(12), dp(10), dp(12), dp(10))
        self.color = TEXT
        with self.canvas.before:
            Color(*(bg or (MINE if mine else PANEL)))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size,
                                          radius=[dp(10)])
        self.bind(pos=self._sync, size=self._sync)
        self.bind(width=self._wrap, texture_size=self._grow)
        self._wrap()

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _wrap(self, *_):
        breite = max(self.width - dp(24), dp(60))
        if self.text_size[0] != breite:
            self.text_size = (breite, None)

    def _grow(self, *_):
        self.height = max(self.texture_size[1] + dp(20), dp(40))


class BlasenListe(BoxLayout):
    """Scrollbarer Stapel aus Blasen."""

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None,
                         spacing=dp(8), padding=(dp(4), dp(4)), **kwargs)
        self.bind(minimum_height=self.setter("height"))


def _scrollbereich(inhalt):
    sv = ScrollView(do_scroll_x=False, bar_width=dp(3))
    sv.add_widget(inhalt)
    return sv


class ChatScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        root.add_widget(Label(
            text="FRAG MICH · OFFLINE", size_hint_y=None, height=dp(22),
            color=MUTED, font_size=dp(12), bold=True,
        ))
        self.liste = BlasenListe()
        self.sv = _scrollbereich(self.liste)
        root.add_widget(self.sv)

        zeile = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.eingabe = TextInput(
            hint_text="z. B. Kein Alarm trotz Treffer",
            multiline=False, size_hint_x=0.72,
            background_color=(0.10, 0.13, 0.20, 1), foreground_color=TEXT,
            cursor_color=ACCENT, padding=(dp(10), dp(12)),
        )
        self.eingabe.bind(on_text_validate=self.senden)
        knopf = Button(text="SENDEN", size_hint_x=0.28, bold=True,
                       background_normal="", background_color=ACCENT)
        knopf.bind(on_release=self.senden)
        zeile.add_widget(self.eingabe)
        zeile.add_widget(knopf)
        root.add_widget(zeile)
        self.add_widget(root)
        self.schreibe(
            "Hallo. Ich baue aus einem Suchwunsch einen konkreten Plan für den "
            "Radar, prüfe Alarm- und Webhook-Einstellungen und lese einen "
            "Diagnosebericht. Ich arbeite ohne Internet und ohne Konto."
        )

    def schreibe(self, text, mine=False, bg=None):
        blase = Bubble(text=text, mine=mine, bg=bg)
        self.liste.add_widget(blase)
        Clock.schedule_once(lambda *_: setattr(self.sv, "scroll_y", 0), 0.05)
        return blase

    def senden(self, *_):
        frage = self.eingabe.text.strip()
        if not frage:
            return
        self.eingabe.text = ""
        self.schreibe(frage, mine=True)
        self.schreibe(support_core.format_answer(support_core.answer(frage)))


class DiagnoseScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        root.add_widget(Label(
            text="BERICHT PRÜFEN", size_hint_y=None, height=dp(22),
            color=MUTED, font_size=dp(12), bold=True,
        ))
        self.eingabe = TextInput(
            hint_text=("Diagnose-Text aus dem Radar hier einfügen …\n\n"
                       "Paket, Shops, letzter Scan, Treffer, Konfidenz, "
                       "Webhook, 403/429."),
            multiline=True, size_hint_y=0.42,
            background_color=(0.10, 0.13, 0.20, 1), foreground_color=TEXT,
            cursor_color=ACCENT, padding=(dp(10), dp(10)),
        )
        root.add_widget(self.eingabe)

        knoepfe = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        pruefen = Button(text="PRÜFEN", bold=True, background_normal="",
                         background_color=ACCENT)
        pruefen.bind(on_release=self.pruefen)
        beispiel = Button(text="BEISPIEL", background_normal="",
                          background_color=PANEL)
        beispiel.bind(on_release=self.beispiel)
        knoepfe.add_widget(pruefen)
        knoepfe.add_widget(beispiel)
        root.add_widget(knoepfe)

        self.liste = BlasenListe()
        self.sv = _scrollbereich(self.liste)
        root.add_widget(self.sv)
        self.add_widget(root)
        self.schreibe(
            "Füge den Diagnose-Block aus dem Radar ein. Ich suche Shops, "
            "letzten Scan, Treffer, Konfidenz, Webhook-Fehler und 403/429."
        )

    def schreibe(self, text, bg=None):
        self.liste.add_widget(Bubble(text=text, bg=bg))
        Clock.schedule_once(lambda *_: setattr(self.sv, "scroll_y", 0), 0.05)

    def beispiel(self, *_):
        self.eingabe.text = support_core.BEISPIEL_BERICHT

    def pruefen(self, *_):
        text = self.eingabe.text.strip()
        self.liste.clear_widgets()
        if len(text) < 5:
            self.schreibe("Der Bericht ist leer. Kopiere den Diagnose-Block "
                          "aus dem Radar oder tippe auf „BEISPIEL“.")
            return
        bericht = support_core.parse_report(text)
        befunde = support_core.diagnose(bericht)
        self.schreibe(support_core.summarize(bericht))
        if not befunde:
            self.schreibe("Keine Auffälligkeit erkannt. Shops, Treffer und "
                          "Konfidenz sehen plausibel aus.")
            return
        for befund in befunde:
            self.schreibe(
                "%s · %s\n\n%s" % (befund["stufe"].upper(), befund["titel"],
                                   befund["text"]),
                bg=STUFE_FARBE.get(befund["stufe"], PANEL),
            )


class SuchScreen(Screen):
    """Wunsch in Einstellungen und Schritte übersetzen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        root.add_widget(Label(
            text="SUCHAUFTRAG BAUEN", size_hint_y=None, height=dp(22),
            color=MUTED, font_size=dp(12), bold=True,
        ))
        self.eingabe = TextInput(
            hint_text="z. B. unter 700, nur Amazon, nur neu",
            multiline=False, size_hint_y=None, height=dp(52),
            background_color=(0.10, 0.13, 0.20, 1), foreground_color=TEXT,
            cursor_color=ACCENT, padding=(dp(10), dp(14)),
        )
        self.eingabe.bind(on_text_validate=self.planen)
        root.add_widget(self.eingabe)

        knoepfe = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        planen = Button(text="PLAN", bold=True, background_normal="",
                        background_color=ACCENT)
        planen.bind(on_release=self.planen)
        beispiel = Button(text="BEISPIEL", background_normal="",
                          background_color=PANEL)
        beispiel.bind(on_release=self.beispiel)
        knoepfe.add_widget(planen)
        knoepfe.add_widget(beispiel)
        root.add_widget(knoepfe)

        self.liste = BlasenListe()
        self.sv = _scrollbereich(self.liste)
        root.add_widget(self.sv)
        self.add_widget(root)
        self.schreibe(
            "Beschreibe, was du suchst — ich übersetze es in Einstellungen "
            "und Schritte für den Radar. Abgerufen wird nichts; die Shops "
            "sieht weiterhin nur der Radar."
        )

    def schreibe(self, text, bg=None):
        self.liste.add_widget(Bubble(text=text, bg=bg))
        Clock.schedule_once(lambda *_: setattr(self.sv, "scroll_y", 0), 0.05)

    def beispiel(self, *_):
        self.eingabe.text = "unter 700, nur Amazon, nur neu, nur bestätigte"

    def planen(self, *_):
        wunsch = self.eingabe.text.strip()
        if not wunsch:
            self.liste.clear_widgets()
            self.schreibe("Schreib zuerst einen Suchwunsch, zum Beispiel "
                          "„unter 700, nur Amazon“. Oder tippe auf „BEISPIEL“.")
            return
        self.liste.clear_widgets()
        self.schreibe(search_assistant.format_plan(
            search_assistant.build_plan(wunsch)))


class ThemenScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        root.add_widget(Label(
            text="ALLE THEMEN", size_hint_y=None, height=dp(22),
            color=MUTED, font_size=dp(12), bold=True,
        ))
        inhalt = GridLayout(cols=1, size_hint_y=None, spacing=dp(6),
                            padding=(dp(2), dp(2)))
        inhalt.bind(minimum_height=inhalt.setter("height"))
        for entry in ENTRIES:
            knopf = Button(
                text=entry["title"], size_hint_y=None, height=dp(48),
                halign="left", valign="middle", background_normal="",
                background_color=PANEL, color=TEXT, font_size=dp(14),
                padding=(dp(12), 0),
            )
            knopf.bind(size=lambda inst, *_: setattr(
                inst, "text_size", (inst.width - dp(24), None)))
            knopf.bind(on_release=lambda inst, e=entry: App.get_running_app()
                       .show_topic(e))
            inhalt.add_widget(knopf)
        root.add_widget(_scrollbereich(inhalt))
        self.add_widget(root)


class HilfeApp(App):
    title = "PS5 Pro Search Agent - Hilfe"

    def build(self):
        Window.clearcolor = BG
        try:
            Window.softinput_mode = "below_target"
        except Exception:
            pass

        self._nav = {}
        root = BoxLayout(orientation="vertical")
        leiste = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4),
                           padding=(dp(6), dp(6)))
        for beschriftung, name in (("FRAGEN", "chat"), ("SUCHE", "suche"),
                                   ("DIAGNOSE", "diag"), ("THEMEN", "themen")):
            knopf = Button(text=beschriftung, bold=True, font_size=dp(11.5),
                           background_normal="", background_color=PANEL,
                           color=MUTED)
            knopf.bind(on_release=lambda inst, n=name: self.gehe(n))
            leiste.add_widget(knopf)
            self._nav[name] = knopf
        root.add_widget(leiste)

        self.sm = ScreenManager()
        self.chat = ChatScreen(name="chat")
        self.suche = SuchScreen(name="suche")
        self.diag = DiagnoseScreen(name="diag")
        self.themen = ThemenScreen(name="themen")
        for screen in (self.chat, self.suche, self.diag, self.themen):
            self.sm.add_widget(screen)
        root.add_widget(self.sm)
        self.gehe("chat")
        return root

    def gehe(self, name):
        self.sm.current = name
        for schluessel, knopf in self._nav.items():
            aktiv = schluessel == name
            knopf.background_color = ACCENT if aktiv else PANEL
            knopf.color = TEXT if aktiv else MUTED

    def show_topic(self, entry):
        self.chat.schreibe(support_core.format_entry(entry))
        self.gehe("chat")

    def on_start(self):
        Window.bind(on_keyboard=self._zurueck)

    def _zurueck(self, _window, key, *_args):
        if key == 27 and self.sm.current != "chat":
            self.gehe("chat")
            return True
        return False


if __name__ == "__main__":
    # --selftest prueft den Kern, --smoke baut die Oberflaeche einmal auf.
    # Beide beenden sich sofort; Exitcode 0 = ok.
    if "--selftest" in sys.argv:
        ergebnis = support_core.answer("webhook fehler 401")
        raise SystemExit(0 if ergebnis.get("kind") == "antwort" else 1)
    if "--smoke" in sys.argv:
        app = HilfeApp()
        root = app.build()
        okay = root is not None and len(app.sm.screen_names) == 4
        raise SystemExit(0 if okay else 1)
    HilfeApp().run()
