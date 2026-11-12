"""Hintergrund-Scan als Android-Foreground-Service.

Laeuft in einem eigenen Prozess (python-for-android Service) und importiert
bewusst kein Kivy: dort gibt es keine Activity und keinen Fenster-Provider.
Gescannt wird mit derselben Logik wie in der App (scan_core), damit ein
Hintergrund-Treffer exakt derselbe ist wie ein Vordergrund-Treffer.

Start/Stop erfolgen aus main.py ueber ServicePs5proscan.start()/stop().
"""
import os, json, time, traceback
from datetime import datetime

import scan_core as core

# Im Hintergrund hoechstens alle 15 Minuten - kuerzere Intervalle aus der App
# (5/10 min) wuerden im Akkubetrieb nur Datenvolumen und Bot-Sperren kosten.
MIN_INTERVALL = 900
STATUS_DATEI = "ps5pro_bg.json"


def _argument():
    """Vom Startaufruf uebergebenes JSON (Intervall + Datenverzeichnis)."""
    try:
        arg = json.loads(os.environ.get("PYTHON_SERVICE_ARGUMENT") or "{}")
        return arg if isinstance(arg, dict) else {}
    except Exception:
        return {}


def _status_schreiben(ergebnisse, neu, fehler=None):
    daten = {
        "ts": time.time(),
        "zeit": datetime.now().strftime("%H:%M"),
        "geprueft": len(ergebnisse),
        "treffer": len(core.treffer_aus(ergebnisse)),
        "neu": len(neu),
        "results": ergebnisse,
    }
    if fehler:
        daten["fehler"] = str(fehler)[:200]
    pfad = os.path.join(core.data_dir(), STATUS_DATEI)
    try:
        tmp = pfad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False)
        os.replace(tmp, pfad)
    except Exception as e:
        print("[BG] Status:", e)


def _benachrichtige(titel, text):
    """Treffer-Meldung im Service-Prozess (dort gibt es keine Activity)."""
    try:
        from jnius import autoclass

        service = autoclass("org.kivy.android.PythonService").mService
        if service is None:
            return False
        Context = autoclass("android.content.Context")
        nm = service.getSystemService(Context.NOTIFICATION_SERVICE)
        Builder = autoclass("android.app.Notification$Builder")
        if autoclass("android.os.Build$VERSION").SDK_INT >= 26:
            NM = autoclass("android.app.NotificationManager")
            kanal = autoclass("android.app.NotificationChannel")(
                "ps5pro_hits", "PS5 Pro Treffer", NM.IMPORTANCE_HIGH)
            kanal.setDescription("Verfuegbarkeit der PS5 Pro 2 TB")
            nm.createNotificationChannel(kanal)
            b = Builder(service, "ps5pro_hits")
        else:
            b = Builder(service)
            b.setPriority(autoclass("android.app.Notification").PRIORITY_HIGH)
        b.setContentTitle(titel)
        b.setContentText(text)
        # System-Drawable: das App-Icon ist seit API 26 ein adaptives Icon und
        # als Small-Icon ungueltig (Meldung wuerde verworfen).
        b.setSmallIcon(autoclass("android.R$drawable").stat_notify_chat)
        b.setAutoCancel(True)
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        Activity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(service, Activity)
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        b.setContentIntent(PendingIntent.getActivity(
            service, 0, intent,
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
        if not nm.areNotificationsEnabled():
            return False
        nm.notify(int(time.time()) % 100000, b.build())
        return True
    except Exception as e:
        print("[BG] notify:", e)
        return False


def _warten(sekunden):
    """In 30-s-Schritten schlafen, damit ein Abschalten schnell greift."""
    ende = time.time() + sekunden
    while time.time() < ende:
        time.sleep(min(30, max(1, ende - time.time())))
        try:
            if not core.Settings().get("auto_scan", False):
                return
        except Exception:
            pass


def main():
    arg = _argument()
    if arg.get("data_dir"):
        core.set_data_dir(arg["data_dir"])
    try:
        intervall = core.bg_intervall(arg.get("interval"), MIN_INTERVALL)
    except Exception:
        intervall = MIN_INTERVALL
    print("[BG] Start, Intervall %ss, Daten %s" % (intervall, core.data_dir()))

    while True:
        settings = core.Settings()
        if not settings.get("auto_scan", False):
            print("[BG] AUTO ist aus - Service beendet")
            return
        intervall = core.bg_intervall(settings.get("auto_interval"), MIN_INTERVALL)
        namen = set(settings.get("active_haendler") or [])
        haendler = [h for h in core.HAENDLER if not namen or h["name"] in namen]
        max_preis = settings.get("max_preis", core.MAX_PREIS)
        try:
            ergebnisse = core.scan_alle(haendler, max_preis)
        except Exception as e:
            print("[BG] Scan:", e)
            _status_schreiben([], [], fehler=e)
            ergebnisse = []

        if ergebnisse:
            hist = core.History()
            neu = []
            for r in core.treffer_aus(ergebnisse):
                # Flags mitgeben: die App zeigt daraus "NEU" und den Preisunterschied.
                letzter = hist.get_last(r["haendler"])
                r["_prev"] = letzter
                r["_is_new"] = core.ist_neuer_treffer(r["preis"], letzter)
                if r["_is_new"]:
                    neu.append(r)
            hist.update(ergebnisse)
            _status_schreiben(ergebnisse, neu)
            if settings.get("notify", True):
                # Bei einem Ausverkauf koennen viele Shops gleichzeitig melden -
                # fuenf Meldungen reichen, der Rest steht in der App.
                for r in neu[:5]:
                    _benachrichtige(
                        "PS5 Pro 2 TB: " + core.format_preis(r["preis"]),
                        r["haendler"] + " - jetzt verfuegbar")
            print("[BG] %s geprueft, %s Treffer, %s neu"
                  % (len(ergebnisse), len(core.treffer_aus(ergebnisse)), len(neu)))
        else:
            _status_schreiben([], [], fehler="keine Ergebnisse")
        _warten(intervall)


# p4a fuehrt die Datei als Service-Entrypoint aus (dann ist ANDROID_PRIVATE
# gesetzt). Beim Import in Tests/Desktop darf nichts laufen.
if __name__ == "__main__" or os.environ.get("ANDROID_PRIVATE"):
    try:
        main()
    except Exception:
        print(traceback.format_exc())
