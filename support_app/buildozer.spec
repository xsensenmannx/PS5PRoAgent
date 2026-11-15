[app]

# Offline-Hilfe fuer den PS5 Pro Search Agent. Eigenes Paket, damit sie
# parallel zur Radar-App installiert werden kann und deren Releases unberuehrt
# bleiben. ASCII-Titel: aapt und Buildozer lesen die Spec je nach Locale.
title = PS5 Pro Search Agent - Hilfe
package.name = support
package.domain = de.konsolenradar

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,ttf
source.exclude_dirs = bin, .buildozer, __pycache__, tests

version = 1.1.0
# versionCode; tools/set_version_from_tag.sh leitet ihn bei Tag-Builds neu ab.
android.numeric_version = 10100

# Gleiche Pins wie die Radar-App: p4a master baut sonst CPython 3.14, das mit
# Kivy 2.3 und dem festen Cython 0.29 im Recipe nicht kompiliert. python3 und
# hostpython3 muessen identisch sein, sonst bricht p4a den Build ab.
requirements = python3==3.11.9, hostpython3==3.11.9, kivy==2.3.1

# Legacy-Icon 512 plus adaptives Icon (432er Ebenen, vom Launcher maskiert).
# Beide Ebenen sind Pflicht, sobald eine gesetzt ist.
icon.filename = %(source.dir)s/icon.png
icon.adaptive_foreground.filename = %(source.dir)s/icon_fg.png
icon.adaptive_background.filename = %(source.dir)s/icon_bg.png

orientation = portrait
fullscreen = 0

# Nur Internet, und nur fuer die optionale Online-KI mit eigenem Key. Ohne Key
# bleibt die App offline; keine Benachrichtigungen, kein Hintergrunddienst.
android.permissions = INTERNET

# Keine Cloud-Sicherung der lokalen Hilfe-Daten.
android.allow_backup = False

android.api = 36
android.minapi = 24
android.ndk = 28c
android.ndk_api = 24
android.accept_sdk_license = True

# 64- und 32-Bit: deckt aktuelle Geraete und aeltere ARM-Geraete ab (Android 7+).
# x86_64 (Emulator/Chromebooks) laesst sich bei Bedarf ergaenzen.
# Signiert wird ueber die Umgebung (p4a): P4A_RELEASE_KEYSTORE,
# P4A_RELEASE_KEYSTORE_PASSWD, P4A_RELEASE_KEYALIAS und
# P4A_RELEASE_KEYALIAS_PASSWD. Der Workflow setzt sie aus den Secrets und baut
# ausschliesslich `android release`; ohne Keystore entsteht kein APK.
android.archs = arm64-v8a, armeabi-v7a
android.release_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
