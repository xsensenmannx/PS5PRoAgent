"""Hintergrund-Scan als Android-Foreground-Service.

Laeuft in einem eigenen Prozess (python-for-android Service) und importiert
bewusst kein Kivy: dort gibt es keine Activity und keinen Fenster-Provider.
Gescannt wird mit derselben Logik wie in der App (scan_core), damit ein
Hintergrund-Treffer exakt derselbe ist wie ein Vordergrund-Treffer.

Start/Stop erfolgen aus main.py ueber ServicePs5proscan.start()/stop().
"""
import os, json, time, traceback
from datetime import datetime

import branding
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


def _labels():
    """Der Service erbt die Marke ueber das Startargument der App."""
    arg = _argument()
    play = arg.get("brand") == "play" if arg.get("brand") else None
    return branding.labels(play)


def _ist_wlan():
    """Aktives Netz ist WLAN; ohne pruefbare API bleibt der Dienst an."""
    try:
        from jnius import autoclass
        service = autoclass("org.kivy.android.PythonService").mService
        if service is None:
            return True
        C = autoclass("android.content.Context")
        cm = service.getSystemService(C.CONNECTIVITY_SERVICE)
        net = cm.getActiveNetwork()
        if net is None:
            return False
        caps = cm.getNetworkCapabilities(net)
        if caps is None:
            return False
        NC = autoclass("android.net.NetworkCapabilities")
        return bool(caps.hasTransport(NC.TRANSPORT_WIFI))
    except Exception:
        return True


def _ist_laden():
    """Geraet haengt am Ladegeraet; ohne pruefbare API bleibt der Dienst an."""
    try:
        from jnius import autoclass
        service = autoclass("org.kivy.android.PythonService").mService
        if service is None:
            return True
        C = autoclass("android.content.Context")
        bm = service.getSystemService(C.BATTERY_SERVICE)
        if bm is not None and autoclass("android.os.Build$VERSION").SDK_INT >= 23:
            return bool(bm.isCharging())
        Intent = autoclass("android.content.Intent")
        IntentFilter = autoclass("android.content.IntentFilter")
        BatteryManager = autoclass("android.os.BatteryManager")
        status = service.registerReceiver(
            None, IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        ).getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        return status in (BatteryManager.BATTERY_STATUS_CHARGING,
                          BatteryManager.BATTERY_STATUS_FULL)
    except Exception:
        return True


def _pausiert(settings):
    """Grund, warum der Hintergrund gerade nicht scannen soll - oder ''."""
    try:
        if bool(settings.get("bg_wlan_only", False)) and not _ist_wlan():
            return "KEIN WLAN"
        if bool(settings.get("bg_laden_only", False)) and not _ist_laden():
            return "NICHT AM LADEN"
    except Exception:
        pass
    return ""


def _status_lesen():
    """Letzten Status lesen; ein kaputter Stand darf den Dienst nicht stoppen."""
    try:
        with open(os.path.join(core.data_dir(), STATUS_DATEI), "r",
                  encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _status_schreiben(ergebnisse, neu, fehler=None, intervall=None, hot=False,
                      pausiert=None):
    """Status fortschreiben - volle Runde und Hot-Runde teilen sich die Datei.

    ``ts`` bleibt der letzte volle Lauf, eine Hot-Runde schreibt ``hot_ts``.
    ``wach_ts`` ist der Wachhund-Stempel und wird auch beim Pausieren gesetzt,
    damit die App eine bewusste Pause von einem toten Dienst unterscheiden kann.
    """
    jetzt = time.time()
    daten = _status_lesen()
    daten["wach_ts"] = jetzt
    daten["wach_status"] = "pausiert" if pausiert else ("fehler" if fehler else "ok")
    if pausiert:
        daten["pausiert"] = str(pausiert)[:60]
    else:
        daten.pop("pausiert", None)
    if intervall:
        # Heartbeat: die App erkennt daran, ob der Dienst noch planmaessig laeuft.
        daten["intervall"] = int(intervall)
    if hot:
        daten["hot_ts"] = jetzt
        daten["hot_zeit"] = datetime.now().strftime("%H:%M")
        daten["hot_geprueft"] = len(ergebnisse)
        daten["hot_treffer"] = len(core.treffer_aus(ergebnisse))
        daten["hot_neu"] = len(neu)
        daten["hot_results"] = ergebnisse
        daten["hot_intervall"] = int(core.BG_HOT_TAKT)
        if fehler: daten["hot_fehler"] = str(fehler)[:200]
        else: daten.pop("hot_fehler", None)
    elif not pausiert:
        daten["ts"] = jetzt
        daten["zeit"] = datetime.now().strftime("%H:%M")
        daten["geprueft"] = len(ergebnisse)
        daten["treffer"] = len(core.treffer_aus(ergebnisse))
        daten["neu"] = len(neu)
        daten["results"] = ergebnisse
        if intervall: daten["next_ts"] = jetzt + int(intervall)
        if fehler: daten["fehler"] = str(fehler)[:200]
        else: daten.pop("fehler", None)
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
            L = _labels()
            kanal = autoclass("android.app.NotificationChannel")(
                L["channel_id"], L["channel_name"], NM.IMPORTANCE_HIGH)
            kanal.setDescription(L["channel_desc"])
            nm.createNotificationChannel(kanal)
            b = Builder(service, L["channel_id"])
        else:
            b = Builder(service)
            b.setPriority(autoclass("android.app.Notification").PRIORITY_HIGH)
        b.setContentTitle(titel)
        b.setContentText(text)
        b.setGroup(_labels()["group"])
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
            L = _labels()
            kanal = autoclass("android.app.NotificationChannel")(
                L["channel_id"], L["channel_name"], NM.IMPORTANCE_HIGH)
            kanal.setDescription(L["channel_desc"])
            nm.createNotificationChannel(kanal)
            b = Builder(service, L["channel_id"])
        else:
            b = Builder(service)
            b.setPriority(autoclass("android.app.Notification").PRIORITY_HIGH)
        titel = "%s: %d Treffer" % (_labels()["summary_title"], len(neu))
        b.setContentTitle(titel)
        b.setContentText("Tippen fuer Details")
        b.setSmallIcon(autoclass("android.R$drawable").stat_notify_chat)
        b.setAutoCancel(True)
        b.setGroup(_labels()["group"])
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


def _warten(bis, max_schritt=60):
    """Bis zu einem Zeitstempel warten; AUTO aus oder Pause greift schnell."""
    while True:
        rest = bis - time.time()
        if rest <= 0:
            return
        time.sleep(max(1, min(rest, max_schritt)))
        try:
            settings = core.Settings()
            if not settings.get("auto_scan", False):
                return
            if _pausiert(settings):
                return
        except Exception:
            pass


def _runde(haendler, settings):
    """Eine Scanrunde: pruefen, verifizieren, Verlauf und Meldungen.

    Rueckgabe (ergebnisse, neu, fehler). Der Aufrufer schreibt den Status,
    damit volle Runde und Hot-Runde getrennte Zeitstempel bekommen.
    """
    # Deckel je Land: AT darf einen eigenen Wert haben, sonst erbt es DE.
    try:
        ergebnisse = core.scan_alle(haendler, core.preis_deckel_aus(settings))
    except Exception as e:
        print("[BG] Scan:", e)
        return [], [], e
    if not ergebnisse:
        return [], [], None
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
    return ergebnisse, neu, None


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
    print("[BG] Start, Intervall %ss, Hot %ss, Daten %s"
          % (intervall, core.BG_HOT_TAKT, core.data_dir()))

    naechste_voll = 0.0
    naechste_hot = 0.0
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
        jetzt = time.time()
        intervall = core.bg_intervall(settings.get("auto_interval"), MIN_INTERVALL)
        pausiert = _pausiert(settings)
        if pausiert:
            # Wachhund-Stempel trotzdem schreiben: die App soll "pausiert"
            # von "Dienst tot" unterscheiden koennen. Nicht jede Minute auf
            # die Karte schreiben - alle fuenf Minuten reicht fuer den Wachhund.
            alt = _status_lesen()
            try: wach_alt = float(alt.get("wach_ts") or 0)
            except (TypeError, ValueError): wach_alt = 0.0
            if alt.get("pausiert") != pausiert or jetzt - wach_alt >= 300:
                _status_schreiben([], [], intervall=intervall, pausiert=pausiert)
                print("[BG] pausiert:", pausiert)
            _warten(jetzt + 60)
            continue
        namen = set(settings.get("active_haendler") or [])
        haendler = [h for h in core.HAENDLER if not namen or h["name"] in namen]
        if jetzt >= naechste_voll:
            ergebnisse, neu, fehler = _runde(haendler, settings)
            if not ergebnisse and not fehler:
                fehler = "keine Ergebnisse"
            _status_schreiben(ergebnisse, neu, fehler=fehler, intervall=intervall)
            # Der Dienst hat keinen Zugriff auf die Waechter-Logs. Er lernt
            # dieselben Fenster aus seinem eigenen Health-Verlauf; ohne
            # genug Treffer bleibt der Default 09-18 aktiv.
            try:
                _gelernt = core.lerne_drop_fenster_aus_lokal(
                    health_daten=core.health().all(),
                    event_liste=core.events().all())
                if _gelernt.get("shops"):
                    core.setze_drop_fenster(_gelernt["shops"])
            except Exception:
                pass
            naechste_voll = jetzt + intervall
            # Ausserhalb des Fensters nicht alle 45 s aufwachen: die volle
            # Runde hat PS Direct gerade mitgeprueft, der naechste Hot-Lauf
            # ist erst zum naechsten Fensterbeginn faellig.
            naechste_hot = (jetzt + core.BG_HOT_TAKT
                            if any(core.im_drop_fenster(h.get("name"), jetzt)
                                   for h in haendler)
                            else core.naechste_fenster_ts(jetzt))
        elif jetzt >= naechste_hot:
            hot = core.bg_hot_shops(haendler, namen, core.health().all(), jetzt)
            if hot:
                ergebnisse, neu, fehler = _runde(hot, settings)
                _status_schreiben(ergebnisse, neu, fehler=fehler, hot=True,
                                  intervall=intervall)
                naechste_hot = jetzt + core.BG_HOT_TAKT
            elif any(core.im_drop_fenster(h.get("name"), jetzt) for h in haendler):
                # Fenster offen, aber beide Shops gesperrt: kein Anklopfen.
                # Die volle Runde prueft sie weiter im 15-Minuten-Takt.
                naechste_hot = jetzt + core.BG_HOT_TAKT
            else:
                naechste_hot = core.naechste_fenster_ts(jetzt)
        _warten(min(naechste_voll, naechste_hot))


# p4a fuehrt die Datei als Service-Entrypoint aus (dann ist ANDROID_PRIVATE
# gesetzt). Beim Import in Tests/Desktop darf nichts laufen.
if __name__ == "__main__" or os.environ.get("ANDROID_PRIVATE"):
    try:
        main()
    except Exception:
        print(traceback.format_exc())
