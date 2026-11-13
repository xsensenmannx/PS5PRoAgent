"""Marken-Schalter fuer die beiden Auslieferungslinien.

Die Sideload-App behaelt Package, Titel und PS-Optik. Die Play-App laeuft
unter ``de.konsolenradar.app`` und zeigt eine neutrale Marke. Die Entscheidung
faellt zur Laufzeit ueber den tatsaechlichen Package-Namen; fuer Screenshots
und Tests laesst sie sich mit ``KONSOLEN_RADAR_BRAND=play`` erzwingen.
"""
import os

PLAY_PACKAGE = "de.konsolenradar.app"
SIDELOAD_PACKAGE = "de.ps5pro.ps5prosearchagent"
PLAY_TITLE = "Konsolen-Radar – Preisalarm"
SIDELOAD_TITLE = "PS5 Pro Search Agent"


def _forced():
    value = os.environ.get("KONSOLEN_RADAR_BRAND", "").strip().lower()
    if value in ("play", "1", "true", "yes"):
        return True
    if value in ("sideload", "0", "false", "no"):
        return False
    return None


def package_name():
    """Aktueller Android-Package, ohne Kivy und ohne harte Annahme."""
    try:
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is not None:
            return str(activity.getPackageName())
    except Exception:
        pass
    try:
        from jnius import autoclass
        service = autoclass("org.kivy.android.PythonService").mService
        if service is not None:
            return str(service.getPackageName())
    except Exception:
        pass
    return ""


def is_play():
    forced = _forced()
    if forced is not None:
        return forced
    return package_name() == PLAY_PACKAGE


PLAY = is_play()
PACKAGE = PLAY_PACKAGE if PLAY else SIDELOAD_PACKAGE
TITLE = PLAY_TITLE if PLAY else SIDELOAD_TITLE
SHORT = "KONSOLEN-RADAR" if PLAY else "PS5 PRO"
SUBTITLE = "PREISALARM  ·  2 TB" if PLAY else "SEARCH AGENT  ·  2 TB"
CHANNEL_ID = "console_radar_hits" if PLAY else "ps5pro_hits"
CHANNEL_NAME = "Konsolen-Radar Treffer" if PLAY else "PS5 Pro Treffer"
CHANNEL_DESC = ("Verfuegbarkeit der PS5 Pro 2 TB"
                if not PLAY else "Preis- und Verfuegbarkeitsalarm")
GROUP = CHANNEL_ID
NOTIFY_HIT = "KONSOLEN-RADAR: TREFFER" if PLAY else "PS5 PRO 2TB VERFÜGBAR"
NOTIFY_RESTOCK = ("KONSOLEN-RADAR: WIEDER DA" if PLAY
                  else "PS5 PRO 2TB WIEDER VERFÜGBAR")
SERVICE_TITLE = "Konsolen-Radar" if PLAY else "PS5 Pro Scan"
SUMMARY_TITLE = "Konsolen-Radar" if PLAY else "PS5 Pro"
TEST_TITLE = "KONSOLEN-RADAR TESTALARM" if PLAY else "PS5 PRO TESTALARM"
SETUP_HEAD = ("KONSOLEN-RADAR  ·  PREISALARM" if PLAY
              else "PS5 PRO 2 TB  ·  LIMITED SEARCH AGENT")
SETUP_SUB = ("PREISALARM  ·  2 TB  ·  KEIN KONTO" if PLAY
             else "PS5 PRO 2 TB · FINAL EDITION")


def labels(play=None):
    """Labels fuer den Service, der den Package nicht immer selbst sieht."""
    if play is None:
        play = PLAY
    elif isinstance(play, str):
        play = play.strip().lower() == "play"
    else:
        play = bool(play)
    return {
        "play": play,
        "title": PLAY_TITLE if play else SIDELOAD_TITLE,
        "short": "KONSOLEN-RADAR" if play else "PS5 PRO",
        "subtitle": "PREISALARM  ·  2 TB" if play else "SEARCH AGENT  ·  2 TB",
        "channel_id": "console_radar_hits" if play else "ps5pro_hits",
        "channel_name": "Konsolen-Radar Treffer" if play else "PS5 Pro Treffer",
        "channel_desc": ("Preis- und Verfuegbarkeitsalarm" if play
                         else "Verfuegbarkeit der PS5 Pro 2 TB"),
        "group": "console_radar_hits" if play else "ps5pro_hits",
        "hit": "KONSOLEN-RADAR: TREFFER" if play else "PS5 PRO 2TB VERFÜGBAR",
        "restock": ("KONSOLEN-RADAR: WIEDER DA" if play
                    else "PS5 PRO 2TB WIEDER VERFÜGBAR"),
        "service_title": "Konsolen-Radar" if play else "PS5 Pro Scan",
        "summary_title": "Konsolen-Radar" if play else "PS5 Pro",
        "brand_arg": "play" if play else "sideload",
    }
