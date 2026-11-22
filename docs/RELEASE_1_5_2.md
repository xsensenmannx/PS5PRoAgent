# Release 1.5.2 — Erfolge-Ansicht und Takt-Frische

**Stand:** lokal vorbereitet, nicht veröffentlicht.
**Basis:** v1.5.1 (`versionCode 10501`).
**Ziel:** v1.5.2 (`versionCode 10502`).

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

- `PYTHONIOENCODING=utf-8 python tools/selftest.py` — 1375/1375.
- `python tools/kivy_smoke.py` — sechs Größen: 360×780, 420×820, 720×480,
  620×380, 620×380 @ 120 %, 884×700.
- `python tools/validate_shop_config.py`
- `python tools/check_hilfe_specs.py`

## Veröffentlichung

1. Commit auf `main`.
2. `main` pushen, Tag `v1.5.2` setzen und pushen.
3. Die CI baut die signierte APK; Asset
   `ps5prosearchagent-1.5.2-arm64-v8a.apk`.
4. Prüfen: `versionName 1.5.2`, `versionCode 10502`, kein
   `application-debuggable`, Signatur und SHA-256.

Bis dahin bleibt v1.5.1 das veröffentlichte Release.

## Rollback

v1.5.1 bleibt als Asset erhalten. Ein Downgrade über eine installierte 1.5.2
ist wegen des höheren `versionCode` nur nach Deinstallation möglich
(Datenverlust).
