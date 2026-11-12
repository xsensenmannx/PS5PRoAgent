# Drittanbieter-Hinweise (Third-Party Notices)

Diese Datei dokumentiert die Open-Source-Bibliotheken, die in der Android-APK
dieses Projekts enthalten sind. Sie ergänzt die [MIT-Lizenz](LICENSE), die nur
den eigenen Projektcode (`main.py`, Build-Skripte, Doku, Icons) betrifft.

Stand: November 2026. Maßgeblich ist `buildozer.spec`: **Kivy 2.3.1** und
**CPython 3.11.9** sind gepinnt, die übrigen Python-Pakete löst
python-for-android beim Build in der jeweils aktuellen Fassung auf. Die
kompletten Lizenztexte liegen den Quellen der Bibliotheken bei und sind über die
verlinkten Repositories abrufbar.

## Python-Pakete in der APK

| Bibliothek | Rolle in der App | Lizenz (SPDX) | Copyright |
| --- | --- | --- | --- |
| [Kivy](https://github.com/kivy/kivy) 2.3.1 | UI-Framework (Widgets, Canvas, Clock) | MIT | Kivy Team and contributors |
| [python-for-android](https://github.com/kivy/python-for-android) | Build-Toolchain, Android-Bootstrap, `android`-Modul für Rechte/Vibration | MIT | Kivy Team and contributors |
| [requests](https://github.com/psf/requests) | HTTP-Scan der Händler (mit `urllib3`) | Apache-2.0 | Kenneth Reitz and contributors |
| [urllib3](https://github.com/urllib3/urllib3) | Transport, Connection-Pooling, TLS | MIT | Andrey Petrov and contributors |
| [certifi](https://github.com/certifi/python-certifi) | CA-Zertifikatsbundle für HTTPS | MPL-2.0 | Kenneth Reitz and contributors |
| [charset-normalizer](https://github.com/Ousret/charset_normalizer) | Zeichensatz-Erkennung für HTTP-Antworten | MIT | TAHRI Ahmed R. and contributors |
| [idna](https://github.com/kjd/idna) | IDNA-Kodierung für internationale Domains | BSD-3-Clause | Kim Davies and contributors |
| [plyer](https://github.com/kivy/plyer) | Benachrichtigungen (Desktop-Fallback) | MIT | Kivy Team and contributors |
| [pyjnius](https://github.com/kivy/pyjnius) | Java-/Android-Brücke (Intent, Vibrator, Notification) | MIT | Kivy Team and contributors |
| [CPython](https://github.com/python/cpython) 3.11.9 | Python-Laufzeit (`libpython3.11.so`) | PSF-2.0 | Python Software Foundation |

## Vom SDL2-Bootstrap mitgelieferte native Bibliotheken

Welche dieser Bibliotheken tatsächlich in der APK landen, hängt vom Stand von
python-for-android ab; die Liste folgt dem SDL2-Bootstrap.

| Bibliothek | Lizenz (SPDX) |
| --- | --- |
| OpenSSL | Apache-2.0 |
| SDL2, SDL2_image, SDL2_mixer, SDL2_ttf | Zlib |
| libffi | MIT |
| FreeType | FTL (FreeType License) |
| libpng | libpng-2.0 |
| bzip2 | bzip2-1.0.6 |
| xz / liblzma | Public Domain |
| SQLite | Public Domain |

## Hinweise zur Weitergabe

* **MIT, BSD-3-Clause, Zlib, FTL, libpng, bzip2, PSF-2.0** verlangen, dass
  Copyright- und Lizenzhinweis bei der Weitergabe erhalten bleiben. Diese Datei
  erfüllt das für die oben genannten Bibliotheken; der vollständige MIT-Text
  steht in [LICENSE](LICENSE) und gilt wortgleich für die MIT-lizenzierten
  Pakete.
* **Apache-2.0** (requests, OpenSSL) verlangt zusätzlich die Lizenzbeilage; der
  Text ist unter <https://www.apache.org/licenses/LICENSE-2.0> abrufbar. Es
  wurden keine Änderungen an diesen Bibliotheken vorgenommen.
* **MPL-2.0** (certifi) betrifft nur die Dateien von certifi selbst. Sie sind
  unverändert; es besteht keine Pflicht, eigenen Code offenzulegen.
* **Schriften:** Kivy liefert Roboto mit (Apache-2.0). Das Projekt selbst legt
  keine eigenen Schriftdateien bei; `main.py` nutzt nur optional einen lokal
  vorhandenen Font und fällt sonst auf Roboto zurück.
* Wer die APK **ohne dieses Repository** weitergibt, sollte diese Datei und
  [LICENSE](LICENSE) beilegen.

## Liste aktualisieren

Die Paketliste folgt `requirements` in `buildozer.spec`:

```
python3==3.11.9, hostpython3==3.11.9, kivy==2.3.1, plyer, pyjnius, requests,
urllib3, certifi, charset-normalizer, idna, android
```

Kommt ein Paket hinzu, hier eine Zeile mit Lizenz und Copyright ergänzen. Die
Kennung steht in der `METADATA` des Pakets (`License-Expression` bzw.
`Classifier: License`) oder in dessen Repository.
