# Play-Store-Launchplan

**Stand:** November 2026 · gilt für v1.3 und die geplante v2.0.
**Ziel:** Die App als eigenständiges, policy-konformes Produkt im Google Play Store
veröffentlichen — ohne die bestehende Sideload-Version zu beschädigen.

> **Kurzfassung:** Technisch ist der Weg frei (AAB ist eine Zeile). Der größte Blocker
> ist die Marke: Titel und Icon nutzen PlayStation-Trade-Dress. Ohne Rebrand gibt es
> kein Play-Release. Danach braucht es 12 Tester für 14 Tage (persönliches Konto)
> und eine saubere Foreground-Service-Deklaration.

---

## 1. Realitätscheck

| Bereich | Ampel | Was fehlt |
|---|---|---|
| AAB & Signatur | 🟡 | `android.release_artifact = aab`, Signieren mit Upload-Key, Test mit bundletool |
| Marke/IP | 🔴 | Neutraler Name, neues Icon ohne PlayStation-Symbole, neuer Package-Name |
| Foreground-Service | 🟡 | Play-Declaration mit Beschreibung, Nutzerauswirkung und Demo-Video |
| Datenschutz | 🟢 | Seite ist vorbereitet (`docs/privacy.html`), URL veröffentlichen |
| Store-Assets | 🟡 | Icon 512, Feature-Grafik 1024×500, 4–8 Screenshots 1080×1920 |
| Testphase | 🟡 | 12 Tester, 14 Tage durchgehend (persönliches Konto) |
| Rechtliches | 🟡 | Keine Sony-Verbindung suggerieren, keine Kaufzusage, faire Last |

**Geschätzte Dauer:** 6–8 Wochen ab Entscheidung, davon 3 Wochen Google-Testphase
und Review. Ohne Rebrand: nicht launchbar.

---

## 2. Die drei echten Blocker

### 2.1 Marke und IP — der wichtigste Punkt

Google Play verbietet die Nutzung fremder Marken, wenn Verwechslung möglich ist
([IP-Policy](https://support.google.com/googleplay/android-developer/answer/9888072)).
Die aktuelle App heißt „PS5 Pro Search Agent" und nutzt die PlayStation-Symbole
(Dreieck, Kreis, Kreuz, Quadrat) als Gestaltung. Das ist Trade Dress von Sony.

**Risiko:** Ablehnung wegen Trademark/Impersonation, im schlechtesten Fall
Sperrung des Entwicklerkontos. Ein Disclaimer im Text heilt das nicht.

**Empfehlung: Rebrand vor dem ersten Upload.**

| Element | Sideload (bleibt) | Play (neu) |
|---|---|---|
| Titel | PS5 Pro Search Agent | **Konsolen-Radar – Preisalarm** |
| Icon | PS-Symbole | Radar/Suchmarke, keine PlayStation-Formen |
| Package | `de.ps5pro.ps5prosearchagent` | `de.konsolenradar.app` (neu, vor dem ersten Upload) |
| Beschreibung | — | „für die PlayStation 5 Pro 2 TB" als beschreibende Nennung, mit Disclaimer |

Der Produktname „PlayStation", „PS5" und „PS5 Pro" darf **beschreibend** genannt
werden („kompatibel mit …"), nicht als Absender oder im Titel. Zusätzlich in die
Beschreibung: „Nicht mit Sony Interactive Entertainment verbunden. Alle Marken
gehören ihren jeweiligen Inhabern." Vorher eine kurze Markenrecherche (DPMA/EUIPO)
für „Konsolen-Radar" machen.

**Package-Name:** Da die App noch nicht im Play Store ist, ist der Wechsel jetzt
kostenlos. Später geht er nicht mehr. Wenn der Package-Name `ps5pro` bleibt, ist er
zwar nicht sichtbar, aber in der Store-URL und im APK — ein zusätzliches Angriffsziel
für Beschwerden. Empfehlung: neuer Package-Name für die Play-Linie; die Sideload-Linie
behält ihren Namen, bis v2.0 beide zusammenführt.

### 2.2 AAB und Signatur

Play akzeptiert seit August 2021 für neue Apps nur noch Android App Bundles.
python-for-android und Buildozer können AAB; im Repo ist es bewusst abgeschaltet:

```ini
# buildozer.spec
android.release_artifact = apk
```

Für den Play-Build:

```bash
# 1. AAB statt APK bauen (in einer Kopie der Spec, damit der APK-Release intakt bleibt)
cp buildozer.spec buildozer.spec.bak
sed -i 's/^android.release_artifact = apk/android.release_artifact = aab/' buildozer.spec
.venv/bin/buildozer -v android release
mv buildozer.spec.bak buildozer.spec

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
zusammen mit dem AAB und `aab.sha256`. Der Lauf vom 13.11.2026 ergab ein
21-MB-AAB (SHA-256 `187b88c1…9d2660`), Manifest: `versionCode 10300`,
`versionName 1.3`, `FOREGROUND_SERVICE_SPECIAL_USE`, `specialUse`-Subtyp und
BootReceiver. Der Build nutzt noch den aktuellen Package-Namen; vor dem ersten
Play-Upload muss der Rebrand erfolgen.

Wichtig:

* **Play App Signing** aktivieren. Google signiert die ausgelieferten APKs neu.
  Der lokale Schlüssel wird zum **Upload-Key**, nicht zum Distributionsschlüssel.
* **Kanal-Trennung:** Sideload-APK (GitHub) und Play-APK haben danach
  unterschiedliche Signaturen. Ein Wechsel zwischen den Kanälen erfordert
  Deinstallation. Das muss in Release-Notes und Store-Beschreibung stehen.
* **versionCode** muss bei jedem Upload steigen (`10300`, `10301`, …).
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

- [ ] Neuer Package-Name und neue App-ID für die Play-Linie
- [ ] `android.release_artifact = aab` im Play-Build, APK-Release unverändert
- [ ] AAB signiert (`jarsigner -verify`), mit bundletool validiert und als Universal-APK gebaut/getestet (macht der Workflow automatisch)
- [ ] Play App Signing aktiviert, Upload-Key sicher verwahrt
- [ ] `versionCode` monoton, `versionName` = Tag
- [ ] targetSdk 36, minSdk 24, arm64-v8a
- [ ] Manifest: keine unnötigen Permissions; `FOREGROUND_SERVICE_SPECIAL_USE` mit Subtyp
- [ ] Datenschutz-URL öffentlich (GitHub Pages aus `docs/`)
- [ ] Store-Assets vollständig (siehe Abschnitt 4)
- [ ] FGS-Demo-Video gedreht und verlinkt
- [ ] Interne Testspur mit echtem Gerät (Android 14 und 15)
- [ ] Pre-Launch-Report aktiviert und geprüft

---

## 4. Store-Assets

| Asset | Vorgabe | Inhalt |
|---|---|---|
| App-Icon | 512×512, 32-bit PNG mit Alpha, ≤ 1 MB | Radar-/Suchmotiv, **keine** PlayStation-Formen |
| Feature-Grafik | 1024×500, JPEG/24-bit PNG ohne Alpha | Radar + Trefferliste, dunkler PS1-Look, kein Text im Randbereich |
| Telefon-Screenshots | 4–8, 1080×1920 (9:16), JPEG/PNG ohne Alpha | Radar, Treffer mit `BESTÄTIGT`, Detail mit Preisverlauf, Webhook-Setup (Token maskiert!), Schnellscan |
| Tablet-Screenshots | optional 4, 9:16 oder 16:9, 1080–7680 px | Querformat mit Radar links, Liste rechts |
| Preview-Video | optional, YouTube | 30 s: Scan → Treffer → Detail → Alarm |

Regeln: echte App-Screens, keine erfundenen Funktionen, keine Ranglisten-/Preis-Badges,
keine Wörter wie „beste", „Nr. 1", „garantiert". Screenshots ohne personenbezogene
Daten und ohne sichtbare Webhook-URL.

Die vorhandenen README-Bilder sind 510×1020 (1:2) und damit für Play zu klein und im
falschen Verhältnis. Für den Store neu bei 1080×1920 aufnehmen; `tools/screenshots.py`
kann die Szenen liefern, das Seitenverhältnis muss beim Aufnehmen gepolstert werden.

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
| IP/Trademark-Ablehnung | hoch ohne Rebrand | neutraler Titel/Icon, Disclaimer, keine Sony-Formen |
| FGS-`specialUse` abgelehnt | mittel | Erklärung + Video; Fallback WorkManager |
| „Scraping"-Beschwerde eines Shops | niedrig–mittel | faire Last, keine Umgehung, keine Datenweitergabe, keine Werbung mit Shop-Inhalten |
| Data-Safety-Widerspruch | niedrig | konservative Angabe, Privacy-Seite konsistent |
| „Minimum functionality"/Spam | niedrig | echte Funktion, 42 Shops, Historie, Verifikation |
| Impersonation | hoch ohne Rebrand | siehe oben; kein „offiziell", keine Sony-Logos |

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
| 1 | Icon/Feature-Grafik/Screenshots, AAB-Pipeline, interner Test |
| 2 | Privacy-URL, Formulare, FGS-Video, Closed-Track vorbereiten |
| 3 | Closed Test startet (12 Tester) |
| 4–5 | Feedback, Fixes, 14-Tage-Fenster halten |
| 6 | Produktionszugang beantragen, Review abwarten |
| 7 | Staged Rollout, Monitoring |

Kosten: 25 USD Konto, 0 EUR Hosting (GitHub Pages), optional Grafiker für Icon/Grafik.
Der zeitliche Aufwand liegt realistisch bei 30–50 Stunden Arbeit plus 3 Wochen Wartezeit.

---

## 11. Checkliste vor dem Upload

- [ ] Titel/Icon/Beschreibung ohne Sony-Marke, Disclaimer vorhanden
- [ ] Package-Name final, `versionCode` neu
- [ ] AAB signiert und mit bundletool getestet
- [ ] Privacy-URL erreichbar (HTTP 200), Data-Safety-Antworten konsistent
- [ ] FGS-Declaration-Text + Video hinterlegt
- [ ] 4+ Screenshots 1080×1920, Icon 512, Feature-Grafik 1024×500
- [ ] Interne Tests auf Android 14/15, Akku-Optimierung, Boot-Start
- [ ] Keine Tokens/URLs in Screenshots oder Store-Texten
- [ ] 12 Tester organisiert, 14-Tage-Fenster eingeplant
