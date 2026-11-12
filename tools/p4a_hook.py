"""p4a-Hook: specialUse-Subtyp fuer den Hintergrund-Service ins Manifest.

Android 14 verlangt fuer jeden Foreground-Service einen Typ. Fuer einen
dauerhaft laufenden Preis-Beobachter passt `dataSync` nicht: Android 15 beendet
dataSync-Services nach 6 Stunden pro 24 h (und wirft eine Exception, wenn der
Service nicht selbst stoppt). `specialUse` hat dieses Limit nicht; Google Play
verlangt dafuer den Subtyp als <property> im <service>-Element.

Der Hook laeuft nach dem Rendern des Manifests und vor Gradle
(after_apk_build im p4a-Toolchain).
"""
import os
import xml.etree.ElementTree as ET

PACKAGE = "de.ps5pro.ps5prosearchagent"
SERVICE = PACKAGE + ".ServicePs5proscan"
SUBTYPE = ("Periodic price and availability checks for a product the user "
           "is watching; started explicitly via the AUTO switch")


def after_apk_build(toolchain):
    path = "src/main/AndroidManifest.xml"
    if not os.path.exists(path):
        print("[hook] Manifest nicht gefunden:", path)
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if "PROPERTY_SPECIAL_USE_FGS_SUBTYPE" in text:
        return

    needle = 'android:name="%s"' % SERVICE
    start = text.find(needle)
    if start < 0:
        print("[hook] Service %s nicht im Manifest" % SERVICE)
        return
    end = text.find("/>", start)
    if end < 0:
        print("[hook] Service-Element ist nicht selbstschliessend")
        return

    prop = ('>\n            <property '
            'android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"\n'
            '                      android:value="%s" />\n'
            '        </service>' % SUBTYPE)
    neu = text[:end] + prop + text[end + 2:]
    try:
        ET.fromstring(neu)
    except ET.ParseError as e:
        print("[hook] Manifest bliebe ungueltig, nichts geaendert:", e)
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(neu)
    print("[hook] specialUse-Subtyp eingetragen")
