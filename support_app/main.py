"""PS5 Pro Search Agent – Hilfe: Support-App mit optionaler Online-KI.

Standard ist offline: kein Konto, keine Telemetrie, Antworten aus
``knowledge.py``. Wer online fragen will, trägt unter „KI“ seinen eigenen
API-Key ein; er bleibt lokal. Anstößige KI-Antworten lassen sich im Reiter
„KI“ lokal melden und per E-Mail oder Zwischenablage an den Entwickler geben.
Die Logik steckt in ``support_core.py``, ``ai_client.py`` und ``meldungen.py``;
diese Datei ist nur die Oberfläche.
"""
import os
import sys
import threading

# Kivy parst sonst die Kommandozeile, bevor unser Code sie sieht, und beendet
# sich bei --selftest/--smoke mit einer Usage-Meldung (Exitcode 2).
os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform as kivy_platform
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

import ai_client
import links
import meldungen
import search_assistant
import support_core
import version
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

        self.plan_knopf = Button(
            text="PLAN KOPIEREN", size_hint_y=None, height=dp(40),
            bold=True, font_size=dp(11), background_normal="",
            background_color=PANEL, color=TEXT, disabled_color=MUTED,
        )
        self.plan_knopf.bind(on_release=self.plan_kopieren)
        self.plan_knopf.disabled = True
        root.add_widget(self.plan_knopf)
        self._plan = ""

        self.liste = BlasenListe()
        self.sv = _scrollbereich(self.liste)
        root.add_widget(self.sv)
        self.add_widget(root)
        self.schreibe(
            "Füge den Diagnose-Block aus dem Radar ein. Ich suche Shops, "
            "letzten Scan, Treffer, Konfidenz, Webhook-Fehler und 403/429. "
            "Nach der Prüfung kannst du den priorisierten Lösungsplan kopieren."
        )

    def schreibe(self, text, bg=None):
        self.liste.add_widget(Bubble(text=text, bg=bg))
        Clock.schedule_once(lambda *_: setattr(self.sv, "scroll_y", 0), 0.05)

    def beispiel(self, *_):
        self.eingabe.text = support_core.BEISPIEL_BERICHT
        self._plan = ""
        self.plan_knopf.disabled = True

    def plan_kopieren(self, *_):
        """Kopiert den priorisierten Plan in die Zwischenablage."""
        if not self._plan:
            return
        try:
            Clipboard.copy(self._plan)
        except Exception:
            self.schreibe("Der Lösungsplan konnte nicht kopiert werden.")
            return
        self.schreibe(
            "Lösungsplan kopiert. Arbeite die Schritte von oben nach unten "
            "ab; die Einstellungen stehen jeweils in der Aktion."
        )

    def pruefen(self, *_):
        text = self.eingabe.text.strip()
        self._plan = ""
        self.plan_knopf.disabled = True
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
        self._plan = support_core.loesungsplan(bericht, befunde)
        self.plan_knopf.disabled = not bool(self._plan)
        if self._plan:
            self.schreibe(
                "Lösungsplan bereit: %d Schritte, nach Dringlichkeit "
                "sortiert. Mit „PLAN KOPIEREN“ in die Zwischenablage legen."
                % len(befunde)
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

        # Versionsanzeige und Update-Weg fuer Sideload-Nutzer. Der Link wird
        # nur auf Klick geoeffnet; die App selbst fragt nichts ab.
        fuss = BoxLayout(orientation="vertical", size_hint_y=None,
                         height=dp(64), spacing=dp(2))
        self.version_label = Label(
            text="Version %s" % version.VERSION, size_hint_y=None,
            height=dp(18), color=MUTED, font_size=dp(11),
        )
        releases = Button(
            text="RELEASES AUF GITHUB", size_hint_y=None, height=dp(40),
            bold=True, font_size=dp(11), background_normal="",
            background_color=PANEL, color=TEXT,
        )
        releases.bind(on_release=self._releases)
        fuss.add_widget(self.version_label)
        fuss.add_widget(releases)
        root.add_widget(fuss)
        self.add_widget(root)

    def _releases(self, *_):
        """Oeffnet die Release-Seite im Browser; ohne Klick passiert nichts."""
        if not links.oeffne(version.RELEASES):
            self.version_label.text = ("Version %s · Link konnte nicht "
                                       "geoeffnet werden." % version.VERSION)


class KiScreen(Screen):
    """Online-KI mit eigenem Key. Ohne Key bleibt die App offline."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        kopf = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(6))
        self.kopf_label = Label(
            text="KI · OFFLINE", color=MUTED, font_size=dp(11), bold=True,
            halign="left", valign="middle",
        )
        kopf.add_widget(self.kopf_label)
        self.melden_knopf = Button(
            text="MELDEN", size_hint_x=None, width=dp(66), bold=True,
            font_size=dp(10), background_normal="", background_color=PANEL,
            color=MUTED, disabled_color=MUTED,
        )
        self.melden_knopf.bind(on_release=lambda *_: self.melden())
        self.melden_knopf.disabled = True
        kopf.add_widget(self.melden_knopf)
        self.key_knopf = Button(
            text="KEY", size_hint_x=None, width=dp(64), bold=True,
            font_size=dp(11), background_normal="", background_color=PANEL,
            color=TEXT,
        )
        self.key_knopf.bind(on_release=lambda *_: self.einstellungen())
        kopf.add_widget(self.key_knopf)
        root.add_widget(kopf)

        self.liste = BlasenListe()
        self.sv = _scrollbereich(self.liste)
        root.add_widget(self.sv)

        zeile = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.eingabe = TextInput(
            hint_text="z. B. Warum findet der Scan bei MediaMarkt nichts?",
            multiline=False, size_hint_x=0.72,
            background_color=(0.10, 0.13, 0.20, 1), foreground_color=TEXT,
            cursor_color=ACCENT, padding=(dp(10), dp(12)),
        )
        self.eingabe.bind(on_text_validate=self.senden)
        self.knopf = Button(text="SENDEN", size_hint_x=0.28, bold=True,
                            background_normal="", background_color=ACCENT)
        self.knopf.bind(on_release=self.senden)
        zeile.add_widget(self.eingabe)
        zeile.add_widget(self.knopf)
        root.add_widget(zeile)
        self.add_widget(root)
        self._letzte = None
        lokal = ("" if kivy_platform in ("android", "ios")
                 else " oder dein lokales Ollama")
        self.schreibe(
            "Die KI antwortet über den Anbieter, den du unter „KEY“ wählst: "
            "Freebuff, OpenRouter, Groq, Google AI Studio, Mistral%s. Jeder "
            "Key bleibt auf diesem Gerät; OpenRouter hat einen kostenlosen "
            "Free-Router. "
            "Ohne Key bleibt alles offline." % lokal
        )
        Clock.schedule_once(lambda *_: self._aktualisiere_kopf(), 0)

    def schreibe(self, text, mine=False, bg=None):
        blase = Bubble(text=text, mine=mine, bg=bg)
        self.liste.add_widget(blase)
        Clock.schedule_once(lambda *_: setattr(self.sv, "scroll_y", 0), 0.05)
        return blase

    def _pfad(self):
        ordner = App.get_running_app().user_data_dir
        os.makedirs(ordner, exist_ok=True)
        return ai_client.settings_pfad(ordner)

    def _zustand(self):
        return ai_client.load_state(self._pfad())

    def _aktualisiere_kopf(self):
        zustand = self._zustand()
        info = ai_client.anbieter_info(zustand["anbieter"])
        modell = ai_client.modell_fuer(zustand, zustand["anbieter"])
        text = "KI · %s" % info["name"].upper()
        if modell:
            text += " · " + modell
        self.kopf_label.text = text[:36]

    def _anbieter_namen(self):
        """Ollama nur dort anbieten, wo localhost der eigene Rechner ist."""
        namen = list(ai_client.ANBIETER)
        if kivy_platform in ("android", "ios"):
            namen = [name for name in namen if name != "ollama"]
        return namen

    def einstellungen(self):
        zustand = self._zustand()
        namen = self._anbieter_namen()
        if zustand["anbieter"] not in namen:
            zustand["anbieter"] = ai_client.STANDARD_ANBIETER
        anzeige = {ai_client.ANBIETER[name]["name"]: name for name in namen}
        gewaehlt = {"name": zustand["anbieter"]}

        inhalt = BoxLayout(orientation="vertical", padding=dp(10),
                           spacing=dp(6))
        inhalt.add_widget(Label(
            text="Anbieter (OpenAI-kompatibel)", size_hint_y=None,
            height=dp(20), color=MUTED, font_size=dp(12),
        ))
        anbieter = Spinner(
            text=ai_client.anbieter_info(zustand["anbieter"])["name"],
            values=[ai_client.ANBIETER[name]["name"] for name in namen],
            size_hint_y=None, height=dp(42), background_normal="",
            background_color=PANEL, color=TEXT,
        )
        inhalt.add_widget(anbieter)

        key_label = Label(text="API-Key (nur lokal)", size_hint_y=None,
                          height=dp(20), color=MUTED, font_size=dp(12))
        inhalt.add_widget(key_label)
        key_feld = TextInput(
            text=ai_client.key_fuer(zustand), password=True, multiline=False,
            size_hint_y=None, height=dp(42),
            background_color=(0.10, 0.13, 0.20, 1), foreground_color=TEXT,
            cursor_color=ACCENT, padding=(dp(10), dp(10)),
        )
        inhalt.add_widget(key_feld)

        kosten = Label(
            text=ai_client.anbieter_info(zustand["anbieter"])["kosten"],
            size_hint_y=None, height=dp(20), color=MUTED, font_size=dp(11),
        )
        inhalt.add_widget(kosten)

        inhalt.add_widget(Label(
            text="Modell", size_hint_y=None, height=dp(20), color=MUTED,
            font_size=dp(12),
        ))
        modell = Spinner(
            text=ai_client.modell_fuer(zustand, zustand["anbieter"]),
            values=[], size_hint_y=None, height=dp(42), background_normal="",
            background_color=PANEL, color=TEXT,
        )
        inhalt.add_widget(modell)

        hinweis = Label(text="", size_hint_y=None, height=dp(18), color=MUTED,
                        font_size=dp(11))
        inhalt.add_widget(hinweis)

        knoepfe = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        holen = Button(text="KEY HOLEN", size_hint_x=0.9, font_size=dp(11),
                       background_normal="", background_color=PANEL)
        laden = Button(text="MODELLE", font_size=dp(11), background_normal="",
                       background_color=PANEL)
        speichern = Button(text="SPEICHERN", bold=True, font_size=dp(11),
                           background_normal="", background_color=ACCENT)
        knoepfe.add_widget(holen)
        knoepfe.add_widget(laden)
        knoepfe.add_widget(speichern)
        inhalt.add_widget(knoepfe)

        popup = Popup(title="KI-Zugang", content=inhalt,
                      size_hint=(0.94, None), height=dp(470),
                      separator_color=ACCENT)

        def felder_fuellen(*_):
            name = anzeige.get(anbieter.text, ai_client.STANDARD_ANBIETER)
            gewaehlt["name"] = name
            info = ai_client.anbieter_info(name)
            key_feld.text = zustand["keys"].get(name, "")
            key_feld.disabled = not info["key_pflicht"]
            key_label.text = ("API-Key (nur lokal)" if info["key_pflicht"]
                              else "Kein Key nötig (lokal)")
            kosten.text = info["kosten"]
            vorhanden = ai_client.modell_fuer(zustand, name)
            modell.values = [vorhanden] if vorhanden else []
            modell.text = vorhanden
            hinweis.text = ""

        def modelle_laden(*_):
            name = gewaehlt["name"]
            probe = dict(zustand)
            probe["keys"] = dict(zustand["keys"])
            probe["keys"][name] = key_feld.text.strip()
            hinweis.text = "Lade Modelle …"
            laden.disabled = True

            def arbeit():
                try:
                    modelle = ai_client.liste_modelle(probe, anbieter=name)
                    fehler = ""
                except ai_client.KiFehler as problem:
                    modelle, fehler = [], str(problem)

                def fertig(*_args):
                    laden.disabled = False
                    if modelle:
                        auswahl = ai_client.empfohlene_modelle(modelle, name)
                        modell.values = auswahl
                        if modell.text not in auswahl:
                            modell.text = auswahl[0]
                        hinweis.text = "%d Modelle verfügbar." % len(modelle)
                    else:
                        hinweis.text = fehler or "Keine Modelle gemeldet."

                Clock.schedule_once(fertig)

            threading.Thread(target=arbeit, daemon=True).start()

        def speichern_(*_):
            name = gewaehlt["name"]
            info = ai_client.anbieter_info(name)
            key = key_feld.text.strip()
            wahl = modell.text.strip()
            if info["key_pflicht"] and not key:
                hinweis.text = "Key fehlt."
                return
            if not wahl:
                hinweis.text = "Erst „MODELLE“ laden und eins wählen."
                return
            zustand["anbieter"] = name
            zustand["keys"][name] = key
            zustand["modelle"][name] = wahl
            ai_client.save_state(self._pfad(), zustand)
            popup.dismiss()
            self._aktualisiere_kopf()
            self.schreibe("Gespeichert: %s · %s · %s"
                          % (info["name"], ai_client.mask(key) or "ohne Key",
                             wahl))

        def key_holen(*_):
            """Oeffnet die Key-Seite des Anbieters; ohne Klick passiert nichts."""
            links.oeffne(ai_client.anbieter_info(gewaehlt["name"])["key_url"])

        anbieter.bind(text=lambda *_: felder_fuellen())
        holen.bind(on_release=key_holen)
        laden.bind(on_release=modelle_laden)
        speichern.bind(on_release=speichern_)
        popup.open()
        felder_fuellen()

    def senden(self, *_):
        frage = self.eingabe.text.strip()
        if not frage:
            return
        zustand = self._zustand()
        name = zustand["anbieter"]
        info = ai_client.anbieter_info(name)
        self.eingabe.text = ""
        self.schreibe(frage, mine=True)
        if info["key_pflicht"] and not ai_client.key_fuer(zustand, name):
            self.schreibe(
                "Dafür fehlt der Key für %s. Tippe oben auf „KEY“ und trage "
                "deinen eigenen API-Key ein.\n\n" % info["name"]
                + support_core.format_answer(support_core.answer(frage)))
            self.einstellungen()
            return
        if not ai_client.modell_fuer(zustand, name):
            self.schreibe(
                "Für %s ist noch kein Modell gewählt. Öffne „KEY“, lade die "
                "Modelle und speichere.\n\n" % info["name"]
                + support_core.format_answer(support_core.answer(frage)))
            self.einstellungen()
            return
        modell = ai_client.modell_fuer(zustand, name)
        blase = self.schreibe("Denkt nach …")
        self.knopf.disabled = True

        def arbeit():
            text, fehler = "", ""
            try:
                text = ai_client.chat(
                    zustand, frage, kontext=support_core.kontext_text(frage))
            except ai_client.KiFehler as problem:
                fehler = str(problem)
            except Exception as problem:  # pragma: no cover - Notfall
                fehler = "Unerwarteter Fehler: %s" % problem
            Clock.schedule_once(
                lambda *_: self._fertig(blase, frage, text, fehler, name,
                                        modell))

        threading.Thread(target=arbeit, daemon=True).start()

    def _fertig(self, blase, frage, text, fehler, anbieter, modell):
        self.knopf.disabled = False
        if text:
            blase.text = text
            self._letzte = {
                "frage": frage,
                "antwort": text,
                "anbieter": anbieter,
                "modell": modell,
            }
            self.melden_knopf.disabled = False
            return
        blase.text = "Keine KI-Antwort: %s\n\nOffline-Antwort:" % fehler
        self.schreibe(support_core.format_answer(support_core.answer(frage)))

    def _meldungen_pfad(self):
        return meldungen.pfad(App.get_running_app().user_data_dir)

    def _kopiere(self, text):
        try:
            Clipboard.copy(text)
            return True
        except Exception:
            return False

    def melden(self):
        """Öffnet den Meldedialog für die zuletzt erhaltene KI-Antwort."""
        if not self._letzte:
            self.schreibe(
                "Noch keine KI-Antwort zum Melden. Stelle zuerst eine Frage; "
                "ohne Key bleibt die Offline-Hilfe sichtbar."
            )
            return
        letzte = dict(self._letzte)
        inhalt = BoxLayout(orientation="vertical", padding=dp(10),
                           spacing=dp(6))
        inhalt.add_widget(Label(
            text="Antwort melden", size_hint_y=None, height=dp(20),
            color=TEXT, bold=True, font_size=dp(14),
        ))
        inhalt.add_widget(Label(
            text="Die Meldung wird lokal gespeichert. E-Mail öffnet dein "
                 "Mailprogramm; gesendet wird sie erst dort.",
            size_hint_y=None, height=dp(38), color=MUTED, font_size=dp(10),
        ))
        inhalt.add_widget(Label(
            text="Was ist anstößig?", size_hint_y=None, height=dp(18),
            color=MUTED, font_size=dp(11),
        ))
        kategorie = Spinner(
            text="Bitte wählen",
            values=[label for _, label in meldungen.KATEGORIEN],
            size_hint_y=None, height=dp(40), background_normal="",
            background_color=PANEL, color=TEXT,
        )
        inhalt.add_widget(kategorie)
        inhalt.add_widget(Label(
            text="Notiz (optional)", size_hint_y=None, height=dp(18),
            color=MUTED, font_size=dp(11),
        ))
        notiz = TextInput(
            hint_text="Was war problematisch?", multiline=True,
            size_hint_y=None, height=dp(72),
            background_color=(0.10, 0.13, 0.20, 1), foreground_color=TEXT,
            cursor_color=ACCENT, padding=(dp(8), dp(8)),
        )
        inhalt.add_widget(notiz)
        inhalt.add_widget(Label(
            text="Kontakt: %s" % meldungen.KONTAKT,
            size_hint_y=None, height=dp(18), color=MUTED, font_size=dp(10),
        ))
        hinweis = Label(text="", size_hint_y=None, height=dp(26), color=MUTED,
                        font_size=dp(10))
        inhalt.add_widget(hinweis)
        knoepfe = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        abbrechen = Button(
            text="ABBRECHEN", size_hint_x=0.30, font_size=dp(10),
            background_normal="", background_color=PANEL,
        )
        kopieren = Button(
            text="KOPIEREN", size_hint_x=0.33, font_size=dp(10),
            background_normal="", background_color=PANEL,
        )
        email = Button(
            text="E-MAIL", size_hint_x=0.37, bold=True, font_size=dp(10),
            background_normal="", background_color=ACCENT,
        )
        knoepfe.add_widget(abbrechen)
        knoepfe.add_widget(kopieren)
        knoepfe.add_widget(email)
        inhalt.add_widget(knoepfe)
        popup = Popup(title="KI-Antwort melden", content=inhalt,
                      size_hint=(0.94, None), height=dp(500),
                      separator_color=ACCENT)

        def eintrag_bauen():
            code = next((code for code, label in meldungen.KATEGORIEN
                         if label == kategorie.text), "")
            if not code:
                hinweis.text = "Bitte eine Kategorie wählen."
                return None
            try:
                eintrag = meldungen.erstelle(
                    code, notiz=notiz.text, frage=letzte["frage"],
                    antwort=letzte["antwort"], anbieter=letzte["anbieter"],
                    modell=letzte["modell"], version=version.VERSION)
                meldungen.speichern(self._meldungen_pfad(), eintrag)
            except (OSError, ValueError) as problem:
                hinweis.text = "Speichern fehlgeschlagen: %s" % problem
                return None
            return eintrag

        def kopieren_(*_):
            eintrag = eintrag_bauen()
            if not eintrag:
                return
            popup.dismiss()
            if self._kopiere(meldungen.als_text(eintrag)):
                self.schreibe(
                    "Meldung %s gespeichert und kopiert. Sende sie an %s."
                    % (eintrag["id"], meldungen.KONTAKT)
                )
            else:
                self.schreibe(
                    "Meldung %s lokal gespeichert. Kopieren war nicht "
                    "möglich; öffne die Meldung erneut und nutze E-MAIL."
                    % eintrag["id"]
                )

        def email_(*_):
            eintrag = eintrag_bauen()
            if not eintrag:
                return
            popup.dismiss()
            if links.oeffne_mailto(meldungen.mailto_url(eintrag)):
                self.schreibe(
                    "Meldung %s lokal gespeichert. Das Mailprogramm wurde "
                    "geöffnet; sende die Nachricht dort ab." % eintrag["id"]
                )
            elif self._kopiere(meldungen.als_text(eintrag)):
                self.schreibe(
                    "Meldung %s lokal gespeichert. Kein Mailprogramm "
                    "gefunden; der Bericht liegt in der Zwischenablage. "
                    "Sende ihn an %s." % (eintrag["id"], meldungen.KONTAKT)
                )
            else:
                self.schreibe(
                    "Meldung %s lokal gespeichert, aber weder Mailprogramm "
                    "noch Zwischenablage verfügbar. Kontakt: %s."
                    % (eintrag["id"], meldungen.KONTAKT)
                )

        abbrechen.bind(on_release=lambda *_: popup.dismiss())
        kopieren.bind(on_release=kopieren_)
        email.bind(on_release=email_)
        popup.open()


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
                                   ("DIAGNOSE", "diag"), ("KI", "ki"),
                                   ("THEMEN", "themen")):
            knopf = Button(text=beschriftung, bold=True, font_size=dp(10.5),
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
        self.ki = KiScreen(name="ki")
        for screen in (self.chat, self.suche, self.diag, self.ki, self.themen):
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
        ki_ok = ai_client.build_payload("m", "test")["messages"][-1][
            "content"] == "test"
        raise SystemExit(
            0 if ergebnis.get("kind") == "antwort" and ki_ok else 1)
    if "--smoke" in sys.argv:
        app = HilfeApp()
        root = app.build()
        okay = root is not None and len(app.sm.screen_names) == 5
        raise SystemExit(0 if okay else 1)
    HilfeApp().run()
