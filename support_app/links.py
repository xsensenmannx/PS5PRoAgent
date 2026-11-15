"""Externe Links und Mail-Entwürfe öffnen — nur auf ausdrücklichen Klick.

Die App selbst ruft nichts ab: ``oeffne`` startet den Systembrowser,
``oeffne_mailto`` das Mailprogramm (Android über Intents, Desktop über
``webbrowser``). Ohne Klick passiert nichts, und es gibt keine Telemetrie über
den Aufruf.
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


def oeffne_mailto(uri):
    """Öffnet einen vorbereiteten E-Mail-Entwurf; True bei Erfolg.

    Der Nutzer sendet die Nachricht selbst im Mailprogramm. Es gibt keinen
    automatischen Versand und keine Serververbindung aus der App.
    """
    uri = str(uri or "")
    kopf = uri[:200].lower()
    if not uri.startswith("mailto:") or ("@" not in kopf and "%40" not in kopf):
        return False
    if sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ:
        return _android_mailto(uri)
    try:
        return bool(webbrowser.open(uri))
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


def _android_mailto(uri):
    """ACTION_SENDTO mit mailto:; ohne Mail-App bleibt der Aufruf erfolglos."""
    try:
        from jnius import autoclass

        intent_klasse = autoclass("android.content.Intent")
        uri_klasse = autoclass("android.net.Uri")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = intent_klasse(intent_klasse.ACTION_SENDTO,
                               uri_klasse.parse(uri))
        activity.startActivity(intent)
        return True
    except Exception:
        return False
