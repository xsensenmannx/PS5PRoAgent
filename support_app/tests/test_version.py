"""Tests für Versionsanzeige und Release-Link. Kein Kivy, kein Netz."""
import os
import re
import sys
import unittest

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)

import links  # noqa: E402
import version  # noqa: E402


class VersionTest(unittest.TestCase):
    def test_format(self):
        self.assertRegex(version.VERSION, r"^\d+\.\d+\.\d+$")

    def test_spec_und_anzeige_stimmen_ueberein(self):
        with open(os.path.join(HIER, "buildozer.spec"), encoding="utf-8") as f:
            spec = f.read()
        treffer = re.search(r"^version\s*=\s*(\S+)", spec, re.M)
        self.assertIsNotNone(treffer)
        self.assertEqual(treffer.group(1), version.VERSION)

    def test_release_adresse(self):
        self.assertEqual(
            version.RELEASES,
            "https://github.com/xsensenmannx/PS5PRoAgent/releases")


class LinksTest(unittest.TestCase):
    def test_nur_https(self):
        # Kein Browserstart im Test: http und leer werden vorher abgelehnt.
        self.assertFalse(links.oeffne("http://example.org"))
        self.assertFalse(links.oeffne(""))
        self.assertFalse(links.oeffne(None))

    def test_kein_netzwerk_modul(self):
        quelle = open(links.__file__, encoding="utf-8").read()
        for verboten in ("urllib", "requests", "socket"):
            self.assertNotIn(verboten, quelle)


if __name__ == "__main__":
    unittest.main()
