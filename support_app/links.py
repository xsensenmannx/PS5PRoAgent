"""Externe Links öffnen — nur auf ausdrücklichen Klick.

Die App selbst ruft nichts ab: ``oeffne`` startet den Systembrowser (Android
über einen Intent, Desktop über ``webbrowser``). Ohne Klick passiert nichts,
und es gibt keine Telemetrie über den Aufruf.
"""
import os
import sys
import webbrowser


def oeffne(url):
    """Öffnet eine HTTPS-Adresse im Systembrowser; True bei Erfolg."""
    if not str(url or "").startswith("https://"):
        return False
    if sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ:
        return _android(url)
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def _android(url):
    """Intent auf ACTION_VIEW; p4a stellt die Java-Klassen über jnius bereit."""
    try:
        from jnius import autoclass

        intent_klasse = autoclass("android.content.Intent")
        uri_klasse = autoclass("android.net.Uri")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = intent_klasse(intent_klasse.ACTION_VIEW,
                               uri_klasse.parse(url))
        activity.startActivity(intent)
        return True
    except Exception:
        return False
