[app]

# Play-/AAB-Variante der Offline-Hilfe. Paketname und Titel bleiben identisch
# zur Sideload-APK, damit beide dieselbe App sind. Der einzige Unterschied ist
# das Artefakt: Google Play verlangt ein Android App Bundle.
#
# Der Workflow .github/workflows/support-aab.yml kopiert diese Datei vor dem
# Build nach buildozer.spec; das Original bleibt fuer APK-Builds unberuehrt.
title = PS5 Pro Search Agent - Hilfe
package.name = support
package.domain = de.konsolenradar

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,ttf
source.exclude_dirs = bin, .buildozer, __pycache__, tests

version = 1.2.0
# Wird bei einem Tag-Build aus dem Tag abgeleitet; im AAB-Workflow gilt der
# Wert aus dieser Spec. Er muss mit buildozer.spec uebereinstimmen.
android.numeric_version = 10200

# Gleiche Pins wie die Radar-App: p4a master baut sonst CPython 3.14, das mit
# Kivy 2.3 und dem festen Cython 0.29 im Recipe nicht kompiliert. python3 und
# hostpython3 muessen identisch sein. certifi bringt die CA-Zertifikate fuer
# die optionale Online-KI mit.
requirements = python3==3.11.9, hostpython3==3.11.9, kivy==2.3.1, certifi

# Icon und adaptive Ebenen wie in der APK-Variante.
icon.filename = %(source.dir)s/icon.png
icon.adaptive_foreground.filename = %(source.dir)s/icon_fg.png
icon.adaptive_background.filename = %(source.dir)s/icon_bg.png
android.add_resources = android_res/mipmap-mdpi/icon.png:mipmap-mdpi/icon.png, android_res/mipmap-hdpi/icon.png:mipmap-hdpi/icon.png, android_res/mipmap-xhdpi/icon.png:mipmap-xhdpi/icon.png, android_res/mipmap-xxhdpi/icon.png:mipmap-xxhdpi/icon.png, android_res/mipmap-xxxhdpi/icon.png:mipmap-xxxhdpi/icon.png

orientation = portrait
fullscreen = 0

# Nur Internet, und nur fuer die optionale Online-KI mit eigenem Key.
android.permissions = INTERNET

# Keine Cloud-Sicherung der lokalen Hilfe-Daten.
android.allow_backup = False

android.api = 36
android.minapi = 24
android.ndk = 28c
android.ndk_api = 24
android.accept_sdk_license = True

# Beide ARM-ABIs wie in der APK. Play liefert daraus pro Geraet nur die
# passende Fassung; die Universal-APK aus bundletool enthaelt beide.
android.archs = arm64-v8a, armeabi-v7a
android.release_artifact = aab

[buildozer]
log_level = 2
warn_on_root = 1
