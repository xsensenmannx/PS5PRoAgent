"""Kivy-Smoke-Test fuer die Popups aus v1.2.

Dieser Test laeuft mit echtem Kivy (nicht mit den Stubs aus selftest.py), weil
nur so Popup-Aufbau, ScrollView und Button-Callbacks wirklich ausgefuehrt
werden. Er benutzt ein temporaeres Datenverzeichnis und ersetzt alle Wege nach
aussen (Shop-Konfiguration, Benachrichtigungen, Browser, Share), damit kein
Test einen echten Shop kontaktiert.

    KIVY_NO_ARGS=1 python3 tools/kivy_smoke.py

Auf Linux ohne Display:

    xvfb-run -a python3 tools/kivy_smoke.py

Exit-Code 0 = alle Pruefungen bestanden. Fehlt Kivy oder ein Fenster-Provider,
endet der Test mit dem entsprechenden Kivy-Fehler; die CI installiert beides.
"""
import os
import shutil
import sys
import tempfile
import time
import traceback

# Vor dem Kivy-Import setzen: sonst versucht Kivy, argv zu parsen.
os.environ["KIVY_NO_ARGS"] = "1"

from kivy.config import Config  # noqa: E402

# Realistische Telefonmasse. Die Popups berechnen ihre Breite aus Window.width.
Config.set("graphics", "width", "420")
Config.set("graphics", "height", "820")
Config.set("graphics", "resizable", "0")

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main  # noqa: E402
import scan_core  # noqa: E402

FAILS = []


def check(name, got, want=True):
    if got == want:
        print(f"PASS {name}")
        return True
    print(f"FAIL {name}: {got!r} (erwartet {want!r})")
    FAILS.append(name)
    return False


class SmokeApp(App):
    def build(self):
        self.root_layout = main.RootLayout()
        return self.root_layout

    def on_start(self):
        self.ui = self.root_layout.main_ui
        Clock.schedule_once(self.run_checks, 0.2)

    def pump(self, frames=12):
        # Popup.dismiss() laeuft ueber eine kurze Kivy-Animation. Ohne echte
        # Clock-Ticks bliebe das Popup deshalb im Window und der naechste Test
        # wuerde den alten Inhalt pruefen. Die kurze Pause laesst die Animation
        # deterministisch fertig laufen.
        for _ in range(frames):
            Clock.tick()
            self.root_layout.do_layout()
            time.sleep(0.02)

    def popups(self):
        return [w for w in Window.children if isinstance(w, main.Popup)]

    def popup(self, name):
        self.pump()
        offen = self.popups()
        check(f"{name}: Popup geoeffnet", len(offen) == 1, True)
        if not offen:
            raise AssertionError(f"{name}: kein Popup gefunden")
        p = offen[-1]
        check(f"{name}: Breite passt ins Fenster", p.width <= Window.width + 1, True)
        check(f"{name}: Hoehe passt ins Fenster", p.height <= Window.height + 1, True)
        return p

    def texts(self, popup):
        return [str(getattr(w, "text", "")) for w in popup.content.walk()]

    def button(self, popup, text):
        for w in popup.content.walk():
            if isinstance(w, main.PS1Button) and str(w.text) == text:
                return w
        raise AssertionError("Button nicht gefunden: " + text)

    def textinput(self, popup):
        for w in popup.content.walk():
            if isinstance(w, main.TextInput):
                return w
        raise AssertionError("TextInput nicht gefunden")

    def close(self, popup, label):
        self.button(popup, label).dispatch("on_release")
        self.pump()
        check(f"{label}: Popup geschlossen", not self.popups(), True)

    def no_popup(self):
        self.pump()
        check("kein Popup bleibt offen", not self.popups(), True)

    def run_checks(self, _dt):
        try:
            self.alarm_rules()
            self.shop_health()
            self.detail()
            self.no_popup()
        except Exception:
            traceback.print_exc()
            check("Smoke-Test ohne Ausnahme", False, True)
        finally:
            Clock.schedule_once(lambda _dt: self.stop(), 0)

    # ── Alarm-Regeln ────────────────────────────────────────────────────
    def alarm_rules(self):
        settings = self.ui.settings
        settings.set("notify_sofort", True)
        settings.set("notify_low_only", False)
        settings.set("quiet_hours", False)
        settings.set("mute_haendler", ["Amazon DE"])
        self.ui.max_preis = 900.0

        self.ui._open_alarm_rules()
        p = self.popup("Alarm-Regeln")
        text = " ".join(self.texts(p))
        check("Alarm: Titel", "ALARM-REGELN" in text, True)
        check("Alarm: Sofort-Schalter", self.button(p, "NUR SOFORT: AN") is not None, True)
        check("Alarm: Preis-Schalter", self.button(p, "NUR TIEFSTPREIS: AUS") is not None, True)
        check("Alarm: Ruhezeit-Schalter", self.button(p, "RUHEZEIT 23-07: AUS") is not None, True)
        check("Alarm: Stumm-Liste", "STUMME SHOPS: 1" in text, True)

        # Jeder Toggle muss nicht nur den Text, sondern auch die Einstellung
        # umschalten. Der zweite Klick muss den Ausgangszustand wiederherstellen.
        self.button(p, "NUR SOFORT: AN").dispatch("on_release")
        check("Alarm: Sofort aus", settings.get("notify_sofort"), False)
        check("Alarm: Sofort-Text aus", self.button(p, "NUR SOFORT: AUS") is not None, True)
        self.button(p, "NUR SOFORT: AUS").dispatch("on_release")
        check("Alarm: Sofort wieder an", settings.get("notify_sofort"), True)

        # Ungueltige Grenze darf den bestehenden Wert nicht ueberschreiben.
        ti = self.textinput(p)
        ti.text = "399"
        self.button(p, "PREIS SETZEN").dispatch("on_release")
        check("Alarm: Preisgrenze validiert", self.ui.max_preis, 900.0)
        ti.text = "850"
        self.button(p, "PREIS SETZEN").dispatch("on_release")
        check("Alarm: Preisgrenze gesetzt", self.ui.max_preis, 850.0)
        check("Alarm: Preisgrenze gespeichert", settings.get("max_preis"), 850.0)

        # Der Testalarm darf im Smoke-Test keine echte Benachrichtigung senden;
        # notify wird vor dem App-Start ersetzt.
        self.button(p, "TESTALARM SENDEN").dispatch("on_release")
        check("Alarm: Testalarm aufgerufen", NOTIFY_CALLS, ["PS5 PRO TESTALARM"])

        self.button(p, "STUMME SHOPS: 1  ·  LISTE LEEREN").dispatch("on_release")
        check("Alarm: Stumm-Liste geleert", settings.get("mute_haendler"), [])
        self.close(p, "SCHLIESSEN")

    # ── Shop-Health ─────────────────────────────────────────────────────
    def shop_health(self):
        # Zwei kuenstliche Zustaende reichen: ein auffaelliger Shop fuer den
        # Retry-Pfad, alle anderen erfolgreich fuer die 42-Zeilen-Pruefung.
        jetzt = time.time()
        fehler_name = scan_core.HAENDLER[0]["name"]
        daten = scan_core.Health()
        daten.data = {}
        for h in scan_core.HAENDLER:
            name = h["name"]
            daten.data[name] = {
                "last_status": "error" if name == fehler_name else "hit",
                "last_ts": jetzt,
                "ok_ts": jetzt if name != fehler_name else None,
            }
        # _open_health() liest Health() neu von Platte, nicht den Singleton.
        daten.save()

        self.ui._open_health()
        p = self.popup("Shop-Health")
        text = " ".join(self.texts(p))
        check("Health: Titel", "SHOP-HEALTH" in text, True)
        check("Health: 42 Shops", f"{len(scan_core.HAENDLER)} SHOPS" in text, True)
        check("Health: auffaelliger Shop", "1 AUFFAELLIG" in text, True)
        labels = [w for w in p.content.walk()
                  if isinstance(w, main.Label) and str(w.text) in
                  {h["name"] for h in scan_core.HAENDLER}]
        check("Health: alle Shop-Zeilen", len(labels), len(scan_core.HAENDLER))
        check("Health: Fehlerzeile", fehler_name in text, True)

        # Der Retry darf keinen Scan starten (sonst waere der Smoke-Test online).
        calls = []
        echt_scan = self.ui._scan_start
        self.ui._scan_start = lambda nur=None: calls.append(nur)
        try:
            self.button(p, "FEHLER PRUEFEN").dispatch("on_release")
            self.pump()
            check("Health: Retry schliesst Popup", not self.popups(), True)
            check("Health: Retry nur Fehler-Shop", calls, [[fehler_name]])
        finally:
            self.ui._scan_start = echt_scan

        self.ui._open_health()
        p = self.popup("Shop-Health erneut")
        self.close(p, "ZU")

    # ── Detailansicht ───────────────────────────────────────────────────
    def detail(self):
        result = {
            "haendler": "Amazon DE",
            "preis": 799.0,
            "klass": "hit",
            "condition": "new",
            "seller": "Amazon",
            "sofort": True,
            "signal": "jsonld",
            "verfuegbarkeit": "InStock",
            "url": "https://example.invalid/ps5pro",
        }
        serie = [["2026-11-01T10:00:00", 849.0],
                 ["2026-11-02T10:00:00", 799.0]]
        self.ui.settings.set("mute_haendler", [])
        self.ui._open_detail(result, serie)
        p = self.popup("Detailansicht")
        text = " ".join(self.texts(p))
        check("Detail: Haendler", "Amazon DE" in text, True)
        check("Detail: Preis", "799,00" in text, True)
        check("Detail: Zustand", "NEU" in text, True)
        check("Detail: Lieferstatus", "SOFORT" in text, True)
        check("Detail: Verkaeufer", "Amazon" in text, True)
        check("Detail: Sparkline", any(isinstance(w, main.Sparkline)
                                        for w in p.content.walk()), True)

        # Stummschalten wirkt sofort auf die Einstellung und den Button.
        self.button(p, "HANDLER STUMM").dispatch("on_release")
        check("Detail: Handler stumm", self.ui.settings.get("mute_haendler"), ["Amazon DE"])
        check("Detail: Stumm-Button gedreht", self.button(p, "HANDLER LAUT") is not None, True)

        # SHOP OEFFNEN darf im Test keinen Browser starten.
        self.button(p, "SHOP OEFFNEN").dispatch("on_release")
        self.pump()
        check("Detail: Shop-URL geoeffnet", OPEN_URLS, ["https://example.invalid/ps5pro"])
        check("Detail: Shop oeffnen schliesst Popup", not self.popups(), True)

        # Eine fehlende bzw. leere Serie ist bei alten Daten moeglich und darf
        # nicht in len(serie) abstuerzen.
        self.ui._open_detail(result, None)
        p = self.popup("Detailansicht ohne Serie")
        check("Detail: leerer Verlauf", any("Noch zu wenig Preisverlauf" in str(getattr(w, "text", ""))
                                            for w in p.content.walk()), True)
        self.close(p, "SCHLIESSEN")


# Ausserhalb der App-Klasse, damit die ersetzten globalen Funktionen die
# Aufrufe einfach protokollieren koennen.
NOTIFY_CALLS = []
OPEN_URLS = []


def main_test():
    tmp = tempfile.mkdtemp(prefix="ps5pro-kivy-smoke-")
    scan_core.set_data_dir(tmp)
    scan_core.Settings().set("onboarded", True)
    # Keine Shop-Netzwerkzugriffe aus dem Hintergrund-Thread und aus Popups.
    main.aktualisiere_shop_config = lambda *a, **k: 0
    main.lade_shop_config = lambda *a, **k: None
    main.notify = lambda *a, **k: (NOTIFY_CALLS.append(a[0]), True)[1]
    main.open_url = lambda url: (OPEN_URLS.append(url), True)[1]
    main.share_text = lambda *a, **k: True
    main.MainUI._shop_config_bg = lambda self, force=False: 0

    app = SmokeApp()
    try:
        app.run()
    except Exception:
        traceback.print_exc()
        FAILS.append("App-Start")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAILS:
        print()
        print(f"{len(FAILS)} Smoke-Test(s) fehlgeschlagen: {', '.join(FAILS)}")
        return 1
    print()
    print("Kivy-Smoke-Test bestanden")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
