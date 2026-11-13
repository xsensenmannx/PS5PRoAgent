"""p4a-Hook: specialUse-Subtyp und Boot-Receiver ins Manifest.

Android 14 verlangt fuer jeden Foreground-Service einen Typ. Fuer einen
dauerhaft laufenden Preis-Beobachter passt `dataSync` nicht: Android 15 beendet
dataSync-Services nach 6 Stunden pro 24 h (und wirft eine Exception, wenn der
Service nicht selbst stoppt). `specialUse` hat dieses Limit nicht; Google Play
verlangt dafuer den Subtyp als <property> im <service>-Element.

Zusaetzlich traegt der Hook den BootReceiver ein. Der Receiver ist eine kleine
Java-Klasse (Sideload: android_src/.../BootReceiver.java, Play:
android_src_play/.../BootReceiver.java), weil ein manifest-deklarierter
BroadcastReceiver eine Java-Klasse sein muss. Er startet den Service nur, wenn
der Nutzer AUTO aktiviert hat; die Pruefung passiert im Receiver.

Der Hook laeuft nach dem Rendern des Manifests und vor Gradle
(after_apk_build im p4a-Toolchain).
"""
import os
import re
import xml.etree.ElementTree as ET

SUBTYPE = ("Periodic price and availability checks for a product the user "
           "is watching; started explicitly via the AUTO switch")


def erweitere_manifest(text):
    """Ergaenzt Service-Property und BootReceiver; bei Fehlern unveraendert.

    Package und Service-Klasse werden aus dem gerenderten Manifest gelesen.
    Dadurch funktioniert derselbe Hook fuer Sideload (de.ps5pro...) und Play
    (de.konsolenradar.app), ohne dass eine Marke hartcodiert bleibt.
    Die Funktion ist absichtlich ohne Toolchain testbar. Sie gibt immer ein
    vollstaendiges, XML-parsebares Manifest zurueck (oder das Original).
    """
    original = text
    if not isinstance(text, str):
        return original

    m = re.search(r'android:name="([^"]+)\.ServicePs5proscan"', text)
    if not m:
        return original
    service = m.group(1) + ".ServicePs5proscan"
    receiver = m.group(1) + ".BootReceiver"
    receiver_xml = """        <receiver
            android:name="%s"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
            </intent-filter>
        </receiver>
""" % receiver

    needle = 'android:name="%s"' % service
    start = text.find(needle)
    if start < 0:
        return original
    end = text.find("/>", start)
    if end < 0:
        return original

    if "PROPERTY_SPECIAL_USE_FGS_SUBTYPE" not in text:
        prop = ('>\n            <property '
                'android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"\n'
                '                      android:value="%s" />\n'
                '        </service>' % SUBTYPE)
        text = text[:end] + prop + text[end + 2:]

    if receiver not in text:
        close = text.rfind("</application>")
        if close < 0:
            return original
        text = text[:close] + receiver_xml + text[close:]

    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        print("[hook] Manifest bliebe ungueltig, nichts geaendert:", e)
        return original
    return text


def after_apk_build(toolchain):
    path = "src/main/AndroidManifest.xml"
    if not os.path.exists(path):
        print("[hook] Manifest nicht gefunden:", path)
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    neu = erweitere_manifest(text)
    if neu == text:
        print("[hook] Manifest unveraendert (Service/Property/Receiver bereits vorhanden)")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(neu)
    print("[hook] specialUse-Subtyp und BootReceiver eingetragen")
