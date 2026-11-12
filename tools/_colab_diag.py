#@title Diagnose: Umgebung und letzter Fehler {display-mode: 'form'}
import glob, os, subprocess

def run(cmd, n=3):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        out = (p.stdout + p.stderr).strip().splitlines()
        return out[:n] if out else ['(keine Ausgabe)']
    except Exception as e:
        return ['Fehler: %s' % e]

print('=== System ===')
print('Python:', run('python3 --version'))
print('Java:', run('java -version 2>&1'))
print('Platz:', run('df -h /content | tail -1'))
print('RAM:', run('free -h | head -2', 2))

print()
print('=== venv /content/bzenv ===')
print('vorhanden:', os.path.isdir('/content/bzenv'))
print('buildozer:', run('/content/bzenv/bin/buildozer --version'))
print('pip-Pakete:')
for l in run('/content/bzenv/bin/python -m pip list 2>/dev/null | grep -iE "buildozer|cython|python-for-android|virtualenv"', 8):
    print('  ', l)

print()
print('=== Projekt ===')
print('PROJ vorhanden:', os.path.isdir('/content/ps5pro'))
for f in ('main.py', 'buildozer.spec', 'icon.png', 'assets/icon_fg.png'):
    print('  ', f, os.path.exists('/content/ps5pro/' + f))

print()
print('=== SDK / NDK ===')
print('NDK:', sorted(glob.glob('/root/.buildozer/android/platform/android-ndk-*')) or 'keiner')
print('SDK:', sorted(glob.glob('/root/.buildozer/android/platform/android-sdk*')) or 'keiner')

print()
print('=== Letzter Fehler im Log ===')
log = '/content/buildozer.log'
if not os.path.exists(log):
    print('kein buildozer.log vorhanden - Zelle 5 lief noch nicht')
else:
    lines = open(log, encoding='utf-8', errors='replace').read().splitlines()
    print('Logzeilen:', len(lines))
    idx = [i for i, l in enumerate(lines) if 'Command failed' in l]
    start = max(0, idx[-1] - 25) if idx else max(0, len(lines) - 40)
    for l in lines[start:start + 45]:
        print(l)