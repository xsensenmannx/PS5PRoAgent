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


def _status_schreiben(ergebnisse, neu, fehler=None, intervall=None):
    jetzt = time.time()
    daten = {
        "ts": jetzt,
        "zeit": datetime.now().strftime("%H:%M"),
        "geprueft": len(ergebnisse),
        "treffer": len(core.treffer_aus(ergebnisse)),
        "neu": len(neu),
        "results": ergebnisse,
    }
    if intervall:
        # Heartbeat: die App erkennt daran, ob der Dienst noch planmaessig laeuft.
        daten["intervall"] = int(intervall)
        daten["next_ts"] = jetzt + int(intervall)
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


_NOTIFY_ID = [4200]

def _naechste_id():
    _NOTIFY_ID[0] = (_NOTIFY_ID[0] + 1) % 100000
    return _NOTIFY_ID[0]


def _benachrichtige(titel, text, url=None):
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
        b.setGroup("ps5pro_hits")
        # System-Drawable: das App-Icon ist seit API 26 ein adaptives Icon und
        # als Small-Icon ungueltig (Meldung wuerde verworfen).
        b.setSmallIcon(autoclass("android.R$drawable").stat_notify_chat)
        b.setAutoCancel(True)
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        Activity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(service, Activity)
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if url:
            intent.putExtra("ps5pro_url", url)
        b.setContentIntent(PendingIntent.getActivity(
            service, _naechste_id(), intent,
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
        if not nm.areNotificationsEnabled():
            return False
        nm.notify(_naechste_id(), b.build())
        return True
    except Exception as e:
        print("[BG] notify:", e)
        return False


def _benachrichtige_summary(neu):
    """Eine sammelbare Meldung fuer alle Treffer eines Laufs."""
    if not neu:
        return False
    try:
        from jnius import autoclass

        service = autoclass("org.kivy.android.PythonService").mService
        if service is None:
            return False
        Context = autoclass("android.content.Context")
        nm = service.getSystemService(Context.NOTIFICATION_SERVICE)
        if not nm.areNotificationsEnabled():
            return False
        Builder = autoclass("android.app.Notification$Builder")
        if autoclass("android.os.Build$VERSION").SDK_INT >= 26:
            NM = autoclass("android.app.NotificationManager")
            kanal = autoclass("android.app.NotificationChannel")(
                "ps5pro_hits", "PS5 Pro Treffer", NM.IMPORTANCE_HIGH)
            nm.createNotificationChannel(kanal)
            b = Builder(service, "ps5pro_hits")
        else:
            b = Builder(service)
            b.setPriority(autoclass("android.app.Notification").PRIORITY_HIGH)
        titel = "PS5 Pro: %d Treffer" % len(neu)
        b.setContentTitle(titel)
        b.setContentText("Tippen fuer Details")
        b.setSmallIcon(autoclass("android.R$drawable").stat_notify_chat)
        b.setAutoCancel(True)
        b.setGroup("ps5pro_hits")
        b.setGroupSummary(True)
        try:
            style = autoclass("android.app.Notification$InboxStyle")()
            style.setBigContentTitle(titel)
            for r in neu[:5]:
                zusatz = " (wieder da)" if r.get("_restock") else ""
                style.addLine("%s - %s%s" % (r.get("haendler", "?"),
                                              core.format_preis(r.get("preis")), zusatz))
            b.setStyle(style)
        except Exception:
            pass
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        Activity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(service, Activity)
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
        b.setContentIntent(PendingIntent.getActivity(
            service, 4000, intent,
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
        nm.notify(4000, b.build())
        return True
    except Exception as e:
        print("[BG] summary:", e)
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
    core.install_crash_hook("service")
    arg = _argument()
    if arg.get("data_dir"):
        core.set_data_dir(arg["data_dir"])
    # Remote-URL-Liste einmal pro Dienststart; Fallback bleibt die eingebaute Liste.
    try:
        core.lade_shop_config()
        core.aktualisiere_shop_config()
    except Exception:
        pass
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
        # Auch im Dauerbetrieb einmal taeglich Remote-URLs/Regeln nachziehen;
        # der Cache verhindert dabei einen Abruf bei jedem Intervall.
        try:
            core.aktualisiere_shop_config()
        except Exception:
            pass
        intervall = core.bg_intervall(settings.get("auto_interval"), MIN_INTERVALL)
        namen = set(settings.get("active_haendler") or [])
        haendler = [h for h in core.HAENDLER if not namen or h["name"] in namen]
        max_preis = settings.get("max_preis", core.MAX_PREIS)
        try:
            ergebnisse = core.scan_alle(haendler, max_preis)
        except Exception as e:
            print("[BG] Scan:", e)
            _status_schreiben([], [], fehler=e, intervall=intervall)
            ergebnisse = []

        if ergebnisse:
            # Auch im Hintergrund wird ein Treffer gegengeprueft. Ohne diesen
            # zweiten Abruf waere "NUR BESTAETIGTE" dort wirkungslos.
            nach_name = {h["name"]: h for h in haendler}
            for r in list(ergebnisse):
                if r.get("klass") == "hit" and not core.ist_gebraucht(r.get("condition")):
                    try:
                        core.verify_treffer(nach_name.get(r.get("haendler")), r)
                    except Exception as e:
                        print("[BG] verify:", e)
            hist = core.History()
            neu = []
            for r in core.treffer_aus(ergebnisse):
                # Flags mitgeben: die App zeigt daraus "NEU" und den Preisunterschied.
                letzter = hist.get_last(r["haendler"])
                tief = hist.get_tief(r["haendler"])
                vorher_av = hist.get_verfuegbar(r["haendler"])
                ereignis = core.alarm_ereignis(r, letzter, vorher_av)
                r["_prev"] = letzter
                r["_is_new"] = ereignis == "new"
                r["_restock"] = ereignis == "restock"
                # Ein neuer Treffer ist nicht automatisch ein guter Alarm:
                # Quiet Hours, stummgeschaltete Shops, Vorbestellungen und
                # Gebrauchtware filtert die gemeinsame Regel.
                if ereignis and core.alarm_erlaubt(r, tief, settings):
                    neu.append(r)
            hist.update(ergebnisse)
            _status_schreiben(ergebnisse, neu, intervall=intervall)
            if settings.get("notify", True):
                # Bei einem Ausverkauf koennen viele Shops gleichzeitig melden -
                # fuenf Meldungen reichen, der Rest steht in der App.
                for r in neu[:5]:
                    titel = ("PS5 Pro 2 TB: wieder verfuegbar"
                             if r.get("_restock") else
                             "PS5 Pro 2 TB: " + core.format_preis(r["preis"]))
                    text = (r["haendler"] + " - wieder verfuegbar"
                            if r.get("_restock") else
                            r["haendler"] + " - jetzt verfuegbar")
                    _benachrichtige(titel, text, r.get("url"))
                    try:
                        core.sende_webhook_alarm(r, settings, titel, text)
                    except Exception as e:
                        print("[BG] webhook:", e)
                _benachrichtige_summary(neu[:5])
            print("[BG] %s geprueft, %s Treffer, %s neu"
                  % (len(ergebnisse), len(core.treffer_aus(ergebnisse)), len(neu)))
        else:
            _status_schreiben([], [], fehler="keine Ergebnisse", intervall=intervall)
        _warten(intervall)


# p4a fuehrt die Datei als Service-Entrypoint aus (dann ist ANDROID_PRIVATE
# gesetzt). Beim Import in Tests/Desktop darf nichts laufen.
if __name__ == "__main__" or os.environ.get("ANDROID_PRIVATE"):
    try:
        main()
    except Exception:
        print(traceback.format_exc())
