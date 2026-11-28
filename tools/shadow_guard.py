"""Betriebswache fuer den lokalen Schattenlauf.

Die Wache haelt den Cloud-Waechter am Leben, verhindert den Systemstandby
waehrend der Messung und startet nach einer Benutzeranmeldung von selbst.
Der Schattenmodus ist fest verdrahtet: Die Wache setzt immer
``WATCH_SHADOW=1`` und leert alle Webhook-Variablen, damit aus diesem Prozess
heraus keine Produktionsalarme entstehen koennen.

Aktionen:

* ``--supervise`` (Standard): Endlosschleife, startet den Waechter bei Bedarf.
* ``--once``: ein einzelner Durchlauf, z. B. fuer einen manuellen Test.
* ``--status``: Fortschritt als lesbarer Text.
* ``--stop``: Waechter und Wache beenden.
* ``--install-startup`` / ``--remove-startup``: Autostart-Eintrag pflegen.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(ROOT, "_verify", "cloud_shadow_20261127_1215")
STARTUP_NAME = "PS5ProShadowWatcher.cmd"

STATE_FILE = "cloud_watch_state.json"
WATCHER_STATUS = "watcher_status.json"
GUARD_STATUS = "guard_status.json"
GUARD_PID = "guard.pid"
GUARD_LOG = "guard.log"

# Ein Status aelter als das gilt als haengend.
STATUS_VERALTET = 300
# Nach einem Absturz nicht sofort im Sekundentakt neu starten.
NEUSTART_SPERRE = 60
TAKT = 20

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
STILL_ACTIVE = 259
WAIT_TIMEOUT = 0x00000102
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


_KERNEL32 = None


def kernel32():
    """kernel32 mit sauberen Prototypen; ohne argtypes kuerzt ctypes Handles."""
    global _KERNEL32
    if _KERNEL32 is None:
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.OpenProcess.restype = ctypes.c_void_p
        dll.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        dll.CloseHandle.argtypes = [ctypes.c_void_p]
        dll.CloseHandle.restype = ctypes.c_int
        dll.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        dll.WaitForSingleObject.restype = ctypes.c_uint32
        dll.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        dll.GetExitCodeProcess.restype = ctypes.c_int
        dll.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        dll.TerminateProcess.restype = ctypes.c_int
        dll.IsProcessInJob.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        dll.IsProcessInJob.restype = ctypes.c_int
        dll.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
        dll.SetThreadExecutionState.restype = ctypes.c_uint32
        _KERNEL32 = dll
    return _KERNEL32


def jetzt_iso(ts=None):
    return datetime.fromtimestamp(float(ts or time.time())).strftime("%Y-%m-%d %H:%M:%S")


def log(ordner, text):
    """Eine Zeile in guard.log anhaengen; Fehler duerfen die Wache nicht stoppen."""
    try:
        with open(os.path.join(ordner, GUARD_LOG), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (jetzt_iso(), text))
    except OSError:
        pass


def json_lesen(pfad):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else {}
    except Exception:
        return {}


def json_schreiben(pfad, daten):
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, pfad)


def prozess_lebt(pid):
    if not pid or sys.platform != "win32":
        return False
    k32 = kernel32()
    handle = k32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, int(pid)
    )
    if not handle:
        return False
    try:
        if k32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT:
            return True
        code = ctypes.c_ulong(0)
        k32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def prozess_beenden(pid):
    if not pid or sys.platform != "win32":
        return True
    k32 = kernel32()
    handle = k32.OpenProcess(0x0001, False, int(pid))  # PROCESS_TERMINATE
    if not handle:
        return not prozess_lebt(pid)
    try:
        k32.TerminateProcess(handle, 1)
    finally:
        k32.CloseHandle(handle)
    for _ in range(20):
        if not prozess_lebt(pid):
            return True
        time.sleep(0.1)
    return not prozess_lebt(pid)


def in_auftragsgruppe(pid):
    """Pruefen, ob der Prozess an einer Auftragsgruppe haengt.

    Prozesse in der Gruppe eines beendeten Aufrufers werden mit beendet; nur
    ein abgekoppelter Prozess ueberlebt den Werkzeug-Lebenszyklus.
    """
    if not pid or sys.platform != "win32":
        return False
    k32 = kernel32()
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        wert = ctypes.c_int(0)
        if not k32.IsProcessInJob(handle, None, ctypes.byref(wert)):
            return False
        return bool(wert.value)
    finally:
        k32.CloseHandle(handle)


def schlafschutz(an):
    """Systemstandby verhindern, Bildschirm darf abschalten."""
    if sys.platform != "win32":
        return False
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if an else 0)
    return bool(kernel32().SetThreadExecutionState(flags))


def waechter_env(ordner):
    env = dict(os.environ)
    env.update(
        {
            "WATCH_DATA_DIR": ordner,
            # Fest im Schatten: keine Produktionsalarme aus diesem Lauf.
            "WATCH_SHADOW": "1",
            "WATCH_SHADOW_HOURS": "60",
            "WATCH_SHOPS": "PS Direct DE,PS Direct AT,Alternate DE",
            "WATCH_TAKT": "15",
            "WATCH_TAKT_NEBEN": "30",
            "WATCH_WEBHOOK_URL": "",
            "WATCH_OPS_WEBHOOK_URL": "",
            "WATCH_HEARTBEAT_URL": "",
            "WATCH_MAX_REQ_MIN": "12",
            "WATCH_TZ": "Europe/Berlin",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    return env


def waechter_starten(ordner, python):
    log_pfad = os.path.join(ordner, "run.log")
    os.makedirs(ordner, exist_ok=True)
    ziel = open(log_pfad, "ab", buffering=0)
    basis = [python, "-m", "cloud_watcher.watcher"]
    flaggen = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
    try:
        proc = subprocess.Popen(
            basis,
            cwd=ROOT,
            env=waechter_env(ordner),
            stdin=subprocess.DEVNULL,
            stdout=ziel,
            stderr=subprocess.STDOUT,
            creationflags=flaggen,
            close_fds=True,
        )
    except OSError:
        # Ohne Breakaway-Recht bleibt der Prozess in der Auftragsgruppe.
        proc = subprocess.Popen(
            basis,
            cwd=ROOT,
            env=waechter_env(ordner),
            stdin=subprocess.DEVNULL,
            stdout=ziel,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    ziel.close()
    return proc.pid


def wache_pid(ordner):
    try:
        with open(os.path.join(ordner, GUARD_PID), "r", encoding="utf-8") as f:
            return int((f.read() or "0").strip())
    except Exception:
        return 0


def waechter_pid(ordner):
    status = json_lesen(os.path.join(ordner, WATCHER_STATUS))
    try:
        return int(status.get("pid") or 0)
    except (TypeError, ValueError):
        return 0


def status_alter(ordner):
    status = json_lesen(os.path.join(ordner, WATCHER_STATUS))
    try:
        return time.time() - float(status.get("wach_ts") or 0)
    except (TypeError, ValueError):
        return float("inf")


def schatten_bis(ordner):
    try:
        return float(json_lesen(os.path.join(ordner, STATE_FILE)).get("schatten_bis") or 0)
    except (TypeError, ValueError):
        return 0.0


def einmal_pruefen(ordner, python, neu_starten=True):
    """Zustand pruefen und den Waechter bei Bedarf starten.

    Rueckgabe: (gestartet: bool, grund: str, pid: int)
    """
    pid = waechter_pid(ordner)
    lebt = prozess_lebt(pid)
    alter = status_alter(ordner)
    if lebt and alter <= STATUS_VERALTET:
        return False, "laeuft", pid
    if lebt and alter > STATUS_VERALTET:
        # Prozess haengt: kein Status seit mehr als STATUS_VERALTET.
        if not neu_starten:
            return False, "haengt", pid
        log(ordner, "Waechter PID %s haengt seit %.0f s, wird ersetzt" % (pid, alter))
        prozess_beenden(pid)
        time.sleep(1.0)
    elif pid and not lebt:
        log(ordner, "Waechter PID %s ist beendet, wird neu gestartet" % pid)

    if not neu_starten:
        return False, "gestoppt", pid

    neuer_pid = waechter_starten(ordner, python)
    log(ordner, "Waechter gestartet, PID %s" % neuer_pid)
    return True, "gestartet", neuer_pid


def wachen_status(ordner, pid, neustarts, schutz, laeuft):
    return {
        "ts": round(time.time(), 3),
        "iso": jetzt_iso(),
        "pid": pid,
        "laeuft": laeuft,
        "neustarts": neustarts,
        "schlafschutz": bool(schutz),
        "schatten_bis": schatten_bis(ordner),
        "waechter_pid": waechter_pid(ordner),
    }


def supervise(ordner, python):
    os.makedirs(ordner, exist_ok=True)
    fremd = wache_pid(ordner)
    if fremd and fremd != os.getpid() and prozess_lebt(fremd):
        print("Wache laeuft bereits (PID %s)" % fremd)
        return 0
    with open(os.path.join(ordner, GUARD_PID), "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    log(ordner, "Wache gestartet, PID %s" % os.getpid())

    neustarts = 0
    letzter_start = 0.0
    grenze = schatten_bis(ordner)
    schutz = schlafschutz(True)
    log(ordner, "Schlafschutz %s" % ("aktiv" if schutz else "nicht verfuegbar"))
    status_pfad = os.path.join(ordner, GUARD_STATUS)
    try:
        while True:
            jetzt = time.time()
            if not grenze:
                # Frisches Verzeichnis: der Zustand entsteht erst mit dem
                # ersten Waechterstart, die Frist wird dann nachgezogen.
                grenze = schatten_bis(ordner)
            if grenze and jetzt >= grenze:
                pid = waechter_pid(ordner)
                log(ordner, "Schattenfrist erreicht, Waechter PID %s wird beendet" % pid)
                prozess_beenden(pid)
                json_schreiben(
                    status_pfad, wachen_status(ordner, os.getpid(), neustarts, False, False)
                )
                schlafschutz(False)
                return 0
            if jetzt - letzter_start >= NEUSTART_SPERRE:
                gestartet, grund, _ = einmal_pruefen(ordner, python)
                if gestartet:
                    neustarts += 1
                    letzter_start = jetzt
                elif grund == "haengt":
                    letzter_start = jetzt
            schutz = schlafschutz(True) or schutz
            json_schreiben(
                status_pfad, wachen_status(ordner, os.getpid(), neustarts, schutz, True)
            )
            time.sleep(TAKT)
    finally:
        schlafschutz(False)
        try:
            os.remove(os.path.join(ordner, GUARD_PID))
        except OSError:
            pass


def abkoppeln(ordner, python):
    """Die Wache vom aufrufenden Prozess loesen und im Hintergrund starten."""
    args = [
        sys.executable,
        os.path.abspath(__file__),
        "--data-dir",
        ordner,
        "--python",
        python,
        "--supervise",
    ]
    gemeinsam = dict(
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    try:
        proc = subprocess.Popen(
            args,
            creationflags=DETACHED_PROCESS
            | CREATE_NEW_PROCESS_GROUP
            | CREATE_BREAKAWAY_FROM_JOB,
            **gemeinsam,
        )
    except OSError:
        proc = subprocess.Popen(
            args,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            **gemeinsam,
        )
    time.sleep(2.0)
    print("Wache gestartet, PID %s" % proc.pid)
    print(
        "Auftragsgruppe: %s"
        % ("ja (kann beim Aufraeumen enden)" if in_auftragsgruppe(proc.pid) else "nein (abgekoppelt)")
    )
    return 0 if prozess_lebt(proc.pid) else 1


def bericht(ordner, python):
    zustand = json_lesen(os.path.join(ordner, STATE_FILE))
    status = json_lesen(os.path.join(ordner, WATCHER_STATUS))
    wache = json_lesen(os.path.join(ordner, GUARD_STATUS))
    pid = waechter_pid(ordner)
    lebt = prozess_lebt(pid)
    alter = status_alter(ordner)
    bis = schatten_bis(ordner)
    rest = max(0.0, bis - time.time()) / 3600.0 if bis else 0.0
    wache_pid_wert = wache_pid(ordner)
    tag = zustand.get("tag") or {}
    print("Schattenlauf: %s" % ordner)
    print(
        "Waechter:     %s%s"
        % (
            "laeuft (PID %s)" % pid if lebt else "laeuft NICHT",
            ", letzter Status vor %.0f s" % alter if alter != float("inf") else "",
        )
    )
    print(
        "Runden:       %s, letzte Runde %s"
        % (zustand.get("runden", 0), jetzt_iso(zustand.get("letzte_runde") or 0))
    )
    print(
        "Schatten bis: %s (noch %.1f h)"
        % (jetzt_iso(bis) if bis else "unbekannt", rest)
    )
    print(
        "Heute:        %s Checks, %s Treffer, %s Challenges, %s Parserfehler, %s Alarme"
        % (
            tag.get("checks", 0),
            tag.get("treffer", 0),
            tag.get("challenge", 0),
            tag.get("parser", 0),
            tag.get("alarme", 0),
        )
    )
    print(
        "Alarme:       %s gesendet, %s im Schatten; Outbox %s offen, %s fehlerhaft"
        % (
            zustand.get("alarme_gesendet", 0),
            zustand.get("alarme_schatten", 0),
            (zustand.get("outbox") or {}).get("gesamt", 0),
            (status.get("outbox") or {}).get("failed", 0),
        )
    )
    print(
        "Wache:        %s, %s Neustarts, Schlafschutz %s"
        % (
            "laeuft (PID %s)" % wache_pid_wert
            if prozess_lebt(wache_pid_wert)
            else "laeuft NICHT",
            wache.get("neustarts", 0),
            "aktiv" if wache.get("schlafschutz") else "aus",
        )
    )
    if prozess_lebt(wache_pid_wert):
        print(
            "Abkopplung:   %s"
            % (
                "fehlt (Auftragsgruppe)"
                if in_auftragsgruppe(wache_pid_wert)
                else "ok"
            )
        )
    if not lebt:
        print("\nHinweis: Waechter laeuft nicht. Start mit: python tools/shadow_guard.py --supervise")
    return 0


def stoppen(ordner):
    pid = waechter_pid(ordner)
    ok_w = prozess_beenden(pid) if pid else True
    log(ordner, "Waechter PID %s beendet: %s" % (pid, ok_w))
    wpid = wache_pid(ordner)
    if wpid and wpid != os.getpid():
        prozess_beenden(wpid)
        print("Wache beendet (PID %s)" % wpid)
    json_schreiben(
        os.path.join(ordner, GUARD_STATUS),
        wachen_status(ordner, wpid, 0, False, False),
    )
    print("Waechter beendet (PID %s)" % pid)
    return 0


def startup_pfad():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(
        appdata,
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
        STARTUP_NAME,
    )


def startup_installieren(ordner, python):
    pythonw = python
    if pythonw.lower().endswith("python.exe"):
        kandidat = pythonw[:-10] + "pythonw.exe"
        if os.path.exists(kandidat):
            pythonw = kandidat
    inhalt = (
        "@echo off\r\n"
        'start "" "%s" "%s" --data-dir "%s" --supervise\r\n'
        % (pythonw, os.path.abspath(__file__), os.path.abspath(ordner))
    )
    pfad = startup_pfad()
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8", newline="") as f:
        f.write(inhalt)
    print("Autostart eingerichtet: %s" % pfad)
    print("Interpreter: %s" % pythonw)
    return 0


def startup_entfernen():
    pfad = startup_pfad()
    try:
        os.remove(pfad)
        print("Autostart entfernt: %s" % pfad)
    except FileNotFoundError:
        print("Kein Autostart-Eintrag vorhanden.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Betriebswache fuer den Schattenlauf")
    p.add_argument("--data-dir", default=DEFAULT_DIR, help="Datenverzeichnis des Laufs")
    p.add_argument("--python", default=sys.executable, help="Interpreter fuer den Waechter")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--supervise", action="store_true", help="Dauerbetrieb (Standard)")
    g.add_argument("--detach", action="store_true", help="Wache abgekoppelt im Hintergrund starten")
    g.add_argument("--once", action="store_true", help="einmal pruefen und starten")
    g.add_argument("--status", action="store_true", help="Fortschritt anzeigen")
    g.add_argument("--stop", action="store_true", help="Waechter und Wache beenden")
    g.add_argument("--install-startup", action="store_true", help="Autostart einrichten")
    g.add_argument("--remove-startup", action="store_true", help="Autostart entfernen")
    a = p.parse_args(argv)
    ordner = os.path.abspath(a.data_dir)

    if a.status:
        return bericht(ordner, a.python)
    if a.stop:
        return stoppen(ordner)
    if a.install_startup:
        return startup_installieren(ordner, a.python)
    if a.remove_startup:
        return startup_entfernen()
    if a.detach:
        return abkoppeln(ordner, a.python)
    if a.once:
        gestartet, grund, pid = einmal_pruefen(ordner, a.python)
        print("%s (PID %s)" % (grund, pid))
        return 0
    return supervise(ordner, a.python)


if __name__ == "__main__":
    sys.exit(main())
