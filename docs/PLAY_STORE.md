# Play-Store-Launchplan

**Stand:** November 2026 · gilt für v1.4.0 und die geplante v2.0.
**Ziel:** Die App als eigenständiges, policy-konformes Produkt im Google Play Store
veröffentlichen — ohne die bestehende Sideload-Version zu beschädigen.

> **Kurzfassung:** Der Play-Rebrand ist umgesetzt: neutraler Titel
> „Konsolen-Radar – Preisalarm“, Package `de.konsolenradar.app`, ein eigenes
> Radar-Icon und fertige Store-Assets. `tools/play_readiness.py` meldet für
> `buildozer.play.spec` **0 Blocker**. Es fehlen nur noch der neue AAB-Build
> (Hinweis, kein Blocker), die FGS-Demo und die 12er-Testphase.

---

## 1. Realitätscheck

| Bereich | Ampel | Was fehlt |
|---|---|---|
| AAB & Signatur | 🟡 | Neuer Play-AAB aus `buildozer.play.spec`; Pipeline und Upload-Key sind vorbereitet. |
| Marke/IP | 🟢 | Erledigt: neutraler Titel, Package und Icon ohne PlayStation-Formen. |
| Foreground-Service | 🟡 | Play-Declaration mit Beschreibung, Nutzerauswirkung und Demo-Video |
| Datenschutz | 🟢 | Seite ist vorbereitet (`docs/privacy.html`), URL veröffentlichen |
| Store-Assets | 🟢 | Icon 512, Feature-Grafik 1024×500, zwei gültige Screenshots 1080×1920 |
| Testphase | 🟡 | 12 Tester, 14 Tage durchgehend (persönliches Konto) |
| Rechtliches | 🟡 | Keine Sony-Verbindung suggerieren, keine Kaufzusage, faire Last |

**Geschätzte Dauer:** 6–8 Wochen ab Entscheidung, davon 3 Wochen Google-Testphase
und Review. Der technische Rebrand ist abgeschlossen; der AAB-Build ist der nächste
Schritt.

---

## 2. Blocker-Status

### 2.1 Marke und IP — umgesetzt

Google Play verbietet die Nutzung fremder Marken, wenn Verwechslung möglich ist
([IP-Policy](https://support.google.com/googleplay/android-developer/answer/9888072)).
Die Sideload-App heißt weiterhin „PS5 Pro Search Agent“ und behält ihre Optik. Die
Play-Linie ist davon getrennt und nutzt keine PlayStation-Formen mehr.

| Element | Sideload (unverändert) | Play (neu) |
|---|---|---|
| Titel | PS5 Pro Search Agent | **Konsolen-Radar – Preisalarm** |
| Icon | PS-Symbole | Radar/Suchmarke, keine PlayStation-Formen |
| Package | `de.ps5pro.ps5prosearchagent` | `de.konsolenradar.app` |
| Build | `buildozer.spec`, APK | `buildozer.play.spec`, AAB |

Umgesetzt sind:

* `branding.py` schaltet Titel, Notification-Texte und UI-Motive anhand des
  tatsächlichen Package-Namens um; `KONSOLEN_RADAR_BRAND=play` erzwingt die
  Play-Optik für Screenshots und Tests.
* Neutrale Icons in `assets/play/`: 512er Store-Icon, adaptives Foreground/Background
  und Notification-Icon. Das Motiv ist ein Radar mit Preis-Pfeil, ohne Sony-Formen.
* `store/assets/icon-512.png` und `store/assets/feature-1024x500.png` sind fertig;
  die Telefon-Screenshots liegen als echte App-Aufnahmen in 1080×1920 vor.
* `tools/p4a_hook.py` liest Package und Service-Klasse dynamisch aus dem gerenderten
  Manifest. Der Play-BootReceiver liegt unter `android_src_play/`.

Der Produktname „PlayStation“, „PS5“ und „PS5 Pro“ darf **beschreibend** genannt
werden („kompatibel mit …“), nicht als Absender oder im Titel. Zusätzlich in die
Beschreibung: „Nicht mit Sony Interactive Entertainment verbunden. Alle Marken
gehören ihren jeweiligen Inhabern.“ Eine Markenrecherche (DPMA/EUIPO) für
„Konsolen-Radar“ bleibt empfehlenswert, ist aber kein technischer Blocker.

### 2.2 AAB und Signatur

Play akzeptiert seit August 2021 für neue Apps nur noch Android App Bundles.
python-for-android und Buildozer können AAB. Die Sideload-Spec bleibt bewusst bei APK;
Play nutzt eine eigene Spec:

```ini
# buildozer.play.spec
android.release_artifact = aab
```

Für den Play-Build wird die Play-Spec im CI-Lauf als `buildozer.spec` aktiviert
(`cp buildozer.play.spec buildozer.spec`). Danach läuft der bestehende Buildpfad:

```bash
# 1. AAB aus der Play-Spec bauen (Sideload-APK bleibt unberührt)
cp buildozer.play.spec buildozer.spec
ARTIFACT=aab bash tools/ci_build.sh

# 2. Mit dem Upload-Key signieren (PKCS#12, Alias ps5pro)
jarsigner -keystore release.p12 -storetype PKCS12 \
  -storepass:env KEYSTORE_PASSWORD -sigalg SHA256withRSA -digestalg SHA-256 \
  bin/*.aab ps5pro
jarsigner -verify -strict bin/*.aab

# 3. Vor dem Upload lokal prüfen: Universale APKs bauen und installieren
bundletool build-apks --bundle=bin/*.aab --output=/tmp/app.apks \
  --mode=universal --ks=release.p12 --ks-key-alias=ps5pro
```

**Im Repository verifiziert:** Der manuelle Workflow `Play AAB` baut mit
`ARTIFACT=aab` ein Bundle, signiert es mit dem Upload-Key, prüft die Signatur
mit `jarsigner` und validiert es zusätzlich mit **bundletool 1.18.3**. Aus dem
Bundle wird eine **Universal-APK** erzeugt, mit `apksigner` gegen den erwarteten
Upload-Key geprüft und per `aapt2` auf Package/Version kontrolliert. Beide
Artefakte (`ps5pro-universal.apk`, `.apks`) landen im Artifact `ps5pro-aab`,
zusammen mit dem AAB und `aab.sha256`. Letzter vollständiger Lauf:
`43518504491` (v1.4.0). Ergebnis: 21-MB-AAB (SHA-256 `37217381…f6b0`)
und 21-MB-Universal-APK (SHA-256 `f399f91c…4312`). Geprüft: `bundletool
validate` erfolgreich, Universal-APK mit Upload-Key signiert (Zertifikat
`63:E5:1D:…:70:DD`), Package `de.ps5pro.ps5prosearchagent`,
`versionCode 10400`, `versionName 1.4.0`, minSdk 24, targetSdk 36,
`FOREGROUND_SERVICE_SPECIAL_USE`, `specialUse`-Subtyp und BootReceiver. Dieser
Lauf dokumentiert den alten Package-Namen der v1.4.0. Für den Play-Upload muss
derselbe Workflow mit `buildozer.play.spec` laufen; erwartet werden Package
`de.konsolenradar.app` und Titel `Konsolen-Radar – Preisalarm`.

Wichtig:

* **Play App Signing** aktivieren. Google signiert die ausgelieferten APKs neu.
  Der lokale Schlüssel wird zum **Upload-Key**, nicht zum Distributionsschlüssel.
* **Kanal-Trennung:** Sideload-APK (GitHub) und Play-APK haben danach
  unterschiedliche Signaturen. Ein Wechsel zwischen den Kanälen erfordert
  Deinstallation. Das muss in Release-Notes und Store-Beschreibung stehen.
* **versionCode** muss bei jedem Upload steigen (`10400`, `10401`, …).
* **64-bit:** arm64-v8a ist vorhanden; das erfüllt die Play-Anforderung.
* **targetSdk 36** ist gesetzt (Play-Pflicht seit 31.08.2026).
* **Kein `debuggable`**, keine Testsignatur, keine überflüssigen Permissions.

### 2.3 Foreground-Service `specialUse`

Die App nutzt einen dauerhaften Foreground-Service für den Hintergrund-Scan.
Play verlangt für `specialUse` eine Erklärung im Play Console: Funktion, Auswirkung
auf den Nutzer, was passiert, wenn Android die Aufgabe verschiebt oder beendet, und
ein **Demo-Video** ([Play-Hilfe](https://support.google.com/googleplay/android-developer/answer/13392821)).

**Einzureichender Text (Vorschlag):**

> Die App prüft auf ausdrücklichen Wunsch des Nutzers (AUTO-Schalter) alle 15 Minuten
> die Verfügbarkeit eines Produkts bei Online-Händlern und meldet Treffer per
> Benachrichtigung. Der Dienst ist die Kernfunktion: Ohne ihn kann der Nutzer keinen
> Preisalarm erhalten, während die App geschlossen ist. Der Dienst zeigt eine
> dauerhafte Benachrichtigung mit dem letzten Prüfzeitpunkt; der Nutzer kann ihn
> jederzeit über AUTO beenden. Wird der Dienst vom System beendet, erscheint beim
> nächsten Öffnen ein Hinweis und die App verlinkt die Akku-Einstellungen. Es werden
> keine Standort-, Kamera- oder Mikrofondaten verwendet.

**Demo-Video (60–90 s, unlisted):** AUTO einschalten → dauerhafte Benachrichtigung
zeigen → Display aus → nach dem Intervall Treffer-Benachrichtigung → App öffnen →
AUTO ausschalten. Das Video ist Pflichtbestandteil der Declaration.

**Fallback, falls `specialUse` abgelehnt wird:** Play-Build auf `WorkManager`
(periodisch, Minimum 15 Minuten) umstellen, ohne dauerhaften Dienst. Das kostet
Zuverlässigkeit und die Sofort-Benachrichtigung bei geschlossener App, ist aber
policy-sicher. Aufwand: ca. 3–5 Tage plus Testmatrix. Diese Entscheidung erst nach
dem ersten Review treffen, nicht vorher.

---

## 3. Technische Checkliste

- [x] Neuer Package-Name und neue App-ID für die Play-Linie (`de.konsolenradar.app`)
- [x] `android.release_artifact = aab` im Play-Build, APK-Release unverändert
- [x] Play-AAB-Pfad auf `buildozer.play.spec` und `android_src_play` umgestellt
- [ ] Neuen Play-AAB bauen, signieren und mit bundletool testen
- [x] AAB-Pipeline signiert (`jarsigner -verify`), validiert mit bundletool und baut eine Universal-APK (macht der Workflow automatisch)
- [ ] Play App Signing aktiviert, Upload-Key sicher verwahrt
- [ ] `versionCode` monoton, `versionName` = Tag
- [ ] targetSdk 36, minSdk 24, arm64-v8a
- [ ] Manifest: keine unnötigen Permissions; `FOREGROUND_SERVICE_SPECIAL_USE` mit Subtyp
- [ ] Datenschutz-URL öffentlich (GitHub Pages aus `docs/`)
- [x] Store-Assets für die Mindestanforderung vollständig (Icon, Feature, 2 Screenshots)
- [ ] FGS-Demo-Video gedreht und verlinkt
- [ ] Interne Testspur mit echtem Gerät (Android 14 und 15)
- [ ] Pre-Launch-Report aktiviert und geprüft

---

## 4. Store-Assets

| Asset | Vorgabe | Inhalt |
|---|---|---|
| App-Icon | 512×512, 32-bit PNG mit Alpha, ≤ 1 MB | Radar-/Suchmotiv, **keine** PlayStation-Formen |
| Feature-Grafik | 1024×500, JPEG/24-bit PNG ohne Alpha | Radar + Trefferliste, dunkler PS1-Look, kein Text im Randbereich |
| Telefon-Screenshots | mind. 2, 1080×1920 (9:16), JPEG/PNG ohne Alpha | Radar und Trefferliste sowie Detail mit Preisverlauf; weitere Motive optional |
| Tablet-Screenshots | optional 4, 9:16 oder 16:9, 1080–7680 px | Querformat mit Radar links, Liste rechts |
| Preview-Video | optional, YouTube | 30 s: Scan → Treffer → Detail → Alarm |

Regeln: echte App-Screens, keine erfundenen Funktionen, keine Ranglisten-/Preis-Badges,
keine Wörter wie „beste", „Nr. 1", „garantiert". Screenshots ohne personenbezogene
Daten und ohne sichtbare Webhook-URL.

Die Store-Screenshots liegen als echte Aufnahmen in `store/assets/phone/`:
`01-radar.png` und `02-detail.png`, jeweils 1080×1920. `tools/screenshots.py` nimmt
das App-Fenster per GDI/PrintWindow auf und skaliert anschließend auf 1080×1920.
Weitere Motive (z. B. Webhook-Setup mit maskiertem Token) können ergänzt werden,
sind für die Mindestanforderung aber nicht nötig.

---

## 5. Store-Listing

Texte liegen fertig in `store/listing.de.md` und `store/listing.en.md`.
Eckdaten:

* **Titel:** max. 30 Zeichen, ohne Sony-Marke.
* **Kurzbeschreibung:** max. 80 Zeichen, Nutzen statt Superlative.
* **Vollbeschreibung:** max. 4000 Zeichen, Funktionen, Grenzen, Disclaimer.
* **Kategorie:** Tools (alternativ Shopping).
* **Preis:** kostenlos, keine In-App-Käufe, keine Werbung.
* **Sprache:** Deutsch (Standard), Englisch; Österreich über Deutsch abgedeckt.

---

## 6. App-Content-Formulare

### Datenschutz / Data Safety

| Frage | Antwort | Begründung |
|---|---|---|
| Werden Nutzerdaten erhoben oder geteilt? | **Nein** (Entwickler erhält nichts) | Einstellungen, Verlauf und Belege bleiben lokal |
| Standort, Kontakte, Fotos, Mikrofon | Nein | nicht angefragt, nicht genutzt |
| Werbung/Analytics | Nein | keine SDKs |
| Verschlüsselte Übertragung | Ja | ausschließlich HTTPS |
| Kontolöschung | entfällt | keine Konten |
| Webhooks | vom Nutzer konfiguriert | Shop-/Preisdaten gehen an das vom Nutzer gewählte Ziel, nicht an den Entwickler |

Wenn Google den Webhook als „Sharing" wertet, ist die konservative Antwort:
„App-Aktivität → App-Funktionalität → mit Dritten geteilt, optional, nicht
personenbezogen". Diese Variante in `store/DATA_SAFETY.md` ist vorbereitet.

### Inhaltsbewertung (IARC)

Keine Gewalt, keine Sexualität, keine Sprache, keine Drogen, kein Glücksspiel,
keine Käufe, kein nutzergenerierter Inhalt, keine Standortfreigabe → **Everyone**.
Zielgruppe: **18+** (Shopping-App, keine Familienfreigabe).

### Weitere Deklarationen

* App-Zugang: vollständig ohne Login nutzbar.
* Werbung: nein. In-App-Käufe: nein.
* Nachrichten-App: nein. Regierungs-App: nein. Finanz-/Gesundheits-App: nein.
* Foreground-Service: `specialUse` mit Text und Video (Abschnitt 2.3).

---

## 7. Test- und Release-Ablauf

Persönliche Entwicklerkonten, die **nach dem 13.11.2023** erstellt wurden, müssen
vor der Produktion eine geschlossene Testspur mit **mindestens 12 Testern** laufen
lassen, die **14 Tage durchgehend** opt-in bleiben
([Play-Hilfe](https://support.google.com/googleplay/android-developer/answer/14151465)).
Organisationskonten sind ausgenommen. Danach Produktionszugang beantragen
(Review üblicherweise ≤ 7 Tage).

1. Entwicklerkonto anlegen ($25 einmalig), Identität verifizieren.
2. App anlegen, Store-Eintrag und Formulare ausfüllen.
3. AAB in die **interne Testspur** laden, auf mindestens zwei Geräten testen.
4. **Geschlossene Spur** mit 12+ Testern starten; Testlink teilen; 14 Tage halten.
5. Produktionszugang beantragen; Fragen zu Design, Testprozess, Reife beantworten.
6. Nach Freigabe: **staged rollout** 5 % → 20 % → 50 % → 100 %, Absturzquote beobachten.
7. Pre-Launch-Report und erste Bewertungen auswerten, Hotfix-Spur bereithalten.

---

## 8. Review-Risiken und Antworten

| Risiko | Wahrscheinlichkeit | Antwort |
|---|---|---|
| IP/Trademark-Ablehnung | niedrig nach Rebrand | neutraler Titel/Icon, Disclaimer, keine Sony-Formen |
| FGS-`specialUse` abgelehnt | mittel | Erklärung + Video; Fallback WorkManager |
| „Scraping"-Beschwerde eines Shops | niedrig–mittel | faire Last, keine Umgehung, keine Datenweitergabe, keine Werbung mit Shop-Inhalten |
| Data-Safety-Widerspruch | niedrig | konservative Angabe, Privacy-Seite konsistent |
| „Minimum functionality"/Spam | niedrig | echte Funktion, 42 Shops, Historie, Verifikation |
| Impersonation | niedrig nach Rebrand | kein „offiziell“, keine Sony-Logos, neutraler Absender |

---

## 9. Nach dem Launch

* **Bewertungen:** In-App-Review erst nach einem bestätigten Treffer anbieten, nie beim Start.
* **Vitals:** Abstürze/ANRs im Play Console beobachten; der lokale Crash-Hook bleibt als Rückfallebene.
* **ASO:** Titel/Kurzbeschreibung in Play Console experimentell testen (Store-Listing-Experimente),
  Icon-A/B nur mit neutralen Motiven.
* **Update-Kadenz:** monatlich oder bei Shop-Brüchen; Remote-Config reduziert Notfall-Releases.
* **Kommunikation:** Änderungen an Filtern/Alarmen in den Release-Notes erklären,
  falsche Alarme offen adressieren.

---

## 10. Zeitplan und Kosten

| Woche | Aufgabe |
|---|---|
| 0 | Rebrand-Entscheidung, Package-Name, Markenrecherche |
| 1 | Icon/Feature-Grafik/Screenshots ✅, AAB-Pipeline ✅, interner Test |
| 2 | Privacy-URL, Formulare, FGS-Video, Closed-Track vorbereiten |
| 3 | Closed Test startet (12 Tester) |
| 4–5 | Feedback, Fixes, 14-Tage-Fenster halten |
| 6 | Produktionszugang beantragen, Review abwarten |
| 7 | Staged Rollout, Monitoring |

Kosten: 25 USD Konto, 0 EUR Hosting (GitHub Pages), optional Grafiker für Icon/Grafik.
Der zeitliche Aufwand liegt realistisch bei 30–50 Stunden Arbeit plus 3 Wochen Wartezeit.

---

## 11. Checkliste vor dem Upload

- [x] Titel/Icon/Beschreibung ohne Sony-Marke, Disclaimer vorhanden
- [x] Package-Name final (`de.konsolenradar.app`), `versionCode` 10400
- [ ] Play-AAB aus `buildozer.play.spec` bauen und `versionCode` für den Upload prüfen
- [ ] AAB signiert und mit bundletool getestet
- [ ] Privacy-URL erreichbar (HTTP 200), Data-Safety-Antworten konsistent
- [ ] FGS-Declaration-Text + Video hinterlegt
- [x] 2+ Screenshots 1080×1920, Icon 512, Feature-Grafik 1024×500
- [ ] Interne Tests auf Android 14/15, Akku-Optimierung, Boot-Start
- [ ] Keine Tokens/URLs in Screenshots oder Store-Texten
- [ ] 12 Tester organisiert, 14-Tage-Fenster eingeplant
