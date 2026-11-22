# Release 1.5.2 — Erfolge-Ansicht und Takt-Frische

**Stand:** veröffentlicht am 22.11.2026.
**Basis:** v1.5.1 (`versionCode 10501`).
**Release:** v1.5.2 (`versionCode 10502`), Commit `f25fc97`.

## Inhalt

- SETUP → ERFOLGE bündelt die Verfügbarkeitsfenster aus dem Verlauf: Shop,
  Preis, Dauer und Bestpreis.
- `OFFEN` gilt nur, solange der letzte `verfügbar`-Wechsel innerhalb des
  eingestellten Scan-Takts plus zwei Minuten liegt oder ein frischer,
  erfolgreicher Scan den Stand bestätigt. Ältere offene Fenster stehen als
  `LETZTER STAND`.
- Die Detailansicht zeigt bis zu drei `LETZTE ERFOLGE`. Das gemeinsame
  Listen-Popup folgt in der Höhe dem Inhalt (mindestens 220 dp, höchstens
  520 dp); tiefe Zeilen bleiben linksbündig.
- Takt-Frische: 5 min → 420 s, 10 min → 720 s, 60 min → 3600 s; bei fehlendem
  oder ungültigem Takt gilt 720 s.
- Keine zusätzlichen Abrufe: ERFOLGE nutzt denselben Event-Ticker wie VERLAUF.

## Gates

Alle Release-Gates bestanden:

- `PYTHONIOENCODING=utf-8 python tools/selftest.py` — 1375/1375.
- `python tools/kivy_smoke.py` — sechs Größen: 360×780, 420×820, 720×480,
  620×380, 620×380 @ 120 %, 884×700.
- `python tools/validate_shop_config.py`
- `python tools/check_hilfe_specs.py`
- APK: `versionName=1.5.2`, `versionCode=10502`, `targetSdkVersion=36`.
- Signatur mit `apksigner` gegen den festen Zertifikat-Fingerprint geprüft.

## Veröffentlichung

Release: https://github.com/xsensenmannx/PS5PRoAgent/releases/tag/v1.5.2

Asset: `ps5prosearchagent-1.5.2-arm64-v8a.apk`, 23.062.789 Bytes, nur
`arm64-v8a`.

SHA-256:

```
f5fa4ee6ca55068a10810f398d85052b40d4ab8227d23c74b1b2a3aa06c0ba99
```

## Rollback

v1.5.1 bleibt als Asset erhalten. Ein Downgrade über eine installierte 1.5.2
ist wegen des höheren `versionCode` nur nach Deinstallation möglich
(Datenverlust).
