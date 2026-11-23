# Release 1.5.3 — Sofortiger Erfolgs-Feed und Journal

**Stand:** 23.11.2026.
**Basis:** v1.5.2 (`versionCode 10502`).
**Release:** v1.5.3 (`versionCode 10503`), Commit `0839abf`.

## Inhalt

- **Sofortiger Erfolgs-Feed:** Ein bestätigter Zustandswechsel wird mit der
  Zeit des Abrufs direkt journalisiert, nicht erst am Ende einer Runde. Die
  App zeigt den Treffer damit früh, ohne die Verifikation zu überspringen.
- **Ereignis-Journal:** `ps5pro_events.jsonl` ist append-only, mit
  Prozess-Lock, Dedupe und Rotation (5000 Ereignisse in fünf Segmenten). Die
  alte `ps5pro_events.json` wird beim ersten Start einmalig migriert.
- **ERFOLGE/VERLAUF:** Filter `AKTIVE`/`ALLE`, Tagesgruppen, antippbare
  Zeilen, `OFFEN SEIT`, Preis-/Deckel-Badges sowie Abdeckungslabels
  (`GESEHEN`/`LÜCKE`/`OHNE DATEN`, `SCAN`/`EREIGNIS`).
- **Direkt bestellen:** Bei einem offenen Fenster führt
  `BESTELLBAR · SHOP OEFFNEN` direkt zum Shop.
- **Keine falschen Vorschauen:** Erst verifizierte Treffer landen im Journal;
  Vorschauen werden am Rundenende ausgeschlossen.

## Gates

- `PYTHONIOENCODING=utf-8 python tools/selftest.py` — 1453/1453.
- Kivy-Smoke in sechs CI-Größen: 360×780, 420×820, 720×480, 620×380,
  620×380 @ 120 %, 884×700; zusätzlich 320×640 @ 120 % lokal.
- `python tools/validate_shop_config.py`
- `python tools/play_readiness.py --spec buildozer.play.spec --strict`
- APK: `versionName=1.5.3`, `versionCode=10503`, `targetSdkVersion=36`,
  Signatur mit festem Release-Schlüssel.

## Veröffentlichung

Release: https://github.com/xsensenmannx/PS5PRoAgent/releases/tag/v1.5.3

Asset: `ps5prosearchagent-1.5.3-arm64-v8a.apk`, 23.087.365 Bytes, nur
`arm64-v8a`.

SHA-256:

```
3805fa8ef2abc0798cb468fc37c89ebb1d97c87ce9154cc3d7c70d861c4600ce
```

## Rollback

v1.5.2 bleibt als Asset erhalten. Ein Downgrade über eine installierte 1.5.3
ist wegen des höheren `versionCode` nur nach Deinstallation möglich
(Datenverlust).
