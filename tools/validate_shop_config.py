#!/usr/bin/env python3
"""Prueft die echte shop_config.json vor einem APK-/AAB-Build.

Die App verwirft bei einem einzigen Fehler die komplette Remote-Konfiguration.
Genau diese Pruefung laeuft hier in der CI, damit ein kaputtes JSON, ein
unbekannter Shop, eine unsichere URL oder eine ungueltige Parser-Regel nicht
erst nach dem 40-Minuten-Build auffaellt.

Aufruf:
    python tools/validate_shop_config.py [pfad]

Exit-Code 0 = gueltig (auch die leere Vorlage), 1 = ungueltig.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scan_core  # noqa: E402


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) > 1:
        print("Aufruf: python tools/validate_shop_config.py [pfad]", file=sys.stderr)
        return 2
    pfad = argv[0] if argv else os.path.join(ROOT, "shop_config.json")
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Shop-Config UNGUELTIG: {pfad}: {e}", file=sys.stderr)
        return 1
    try:
        geprueft = scan_core.validiere_shop_config(data)
    except Exception as e:
        print(f"Shop-Config UNGUELTIG: Validierung warf {type(e).__name__}: {e}",
              file=sys.stderr)
        return 1
    if geprueft is None:
        print(f"Shop-Config UNGUELTIG: Schema/URL/Parser-Regel in {pfad}",
              file=sys.stderr)
        return 1
    # Die Anzahl der Overrides ist fuer den CI-Log nuetzlich; Secrets stehen
    # in dieser Datei nicht.
    print(f"Shop-Config OK: {len(geprueft)} Shop-Override(s) in {pfad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
