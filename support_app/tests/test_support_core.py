"""Tests für den Offline-Kern. Nur Standardbibliothek, kein Kivy, kein Netz."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import support_core  # noqa: E402
from knowledge import ENTRIES  # noqa: E402


class NormalisierungTest(unittest.TestCase):
    def test_umlaute_und_zeichen(self):
        self.assertEqual(support_core.normalize("Konfidenz: 92 % – Hä?"),
                         "konfidenz 92 hae")

    def test_stoppwoerter_fallen_weg(self):
        self.assertEqual(support_core.tokenize("Wie ist der Alarm bei mir?"),
                         ["alarm"])


class AntwortTest(unittest.TestCase):
    def test_webhook_frage(self):
        treffer = support_core.search("webhook fehler 401")
        self.assertTrue(treffer)
        self.assertEqual(treffer[0]["entry"]["id"], "webhook")

    def test_kein_alarm(self):
        treffer = support_core.search("kein alarm")
        self.assertTrue(treffer)
        self.assertEqual(treffer[0]["entry"]["id"], "alarm-kommt-nicht")

    def test_akku(self):
        treffer = support_core.search("akku hintergrund")
        self.assertEqual(treffer[0]["entry"]["id"], "akku-hintergrund")

    def test_lotterie(self):
        treffer = support_core.search("lotterie verlosung")
        self.assertEqual(treffer[0]["entry"]["id"], "chance")

    def test_ps_direct(self):
        treffer = support_core.search("warum kein ps direct")
        self.assertEqual(treffer[0]["entry"]["id"], "ps-direct")

    def test_fallback(self):
        ergebnis = support_core.answer("quantenphysik")
        self.assertEqual(ergebnis["kind"], "fallback")
        self.assertEqual(len(ergebnis["suggestions"]), 3)

    def test_leere_frage(self):
        self.assertEqual(support_core.search(""), [])
        self.assertEqual(support_core.answer("  ")["kind"], "fallback")

    def test_format_enthaelt_schritte(self):
        entry = next(e for e in ENTRIES if e["id"] == "erste-schritte")
        text = support_core.format_entry(entry)
        self.assertIn(entry["title"].upper(), text)
        self.assertIn("1.", text)

    def test_alle_eintraege_vollstaendig(self):
        ids = [e["id"] for e in ENTRIES]
        self.assertEqual(len(ids), len(set(ids)), "IDs müssen eindeutig sein")
        for entry in ENTRIES:
            self.assertTrue(entry["title"].strip())
            self.assertTrue(entry["answer"].strip())
            self.assertTrue(entry["keywords"])


class BerichtTest(unittest.TestCase):
    def test_beispiel_parsen(self):
        bericht = support_core.parse_report(support_core.BEISPIEL_BERICHT)
        self.assertFalse(bericht["leer"])
        self.assertEqual(bericht["shops"], 42)
        self.assertEqual(bericht["treffer"], 0)
        self.assertEqual(bericht["konfidenz"], 62)
        self.assertEqual(bericht["letzter_scan"], "12:04")
        self.assertEqual(bericht["paket"], "de.konsolenradar.app")
        self.assertIn("401", bericht["webhook_fehler"])
        # Ein Code-Token kann mehrere Shops meinen; gezählt wird der Code.
        self.assertEqual(bericht["anzahl_403"], 1)
        self.assertEqual(bericht["anzahl_429"], 1)

    def test_leerer_bericht(self):
        bericht = support_core.parse_report("")
        self.assertTrue(bericht["leer"])
        befunde = support_core.diagnose(bericht)
        self.assertEqual(len(befunde), 1)
        self.assertEqual(befunde[0]["titel"], "Bericht unvollständig")

    def test_diagnose_hoch_zuerst(self):
        befunde = support_core.diagnose(
            support_core.parse_report(support_core.BEISPIEL_BERICHT))
        self.assertTrue(befunde)
        self.assertEqual(befunde[0]["stufe"], "hoch")
        titel = [b["titel"] for b in befunde]
        self.assertIn("Shops blockieren den Scan", titel)
        self.assertIn("Webhook wird abgelehnt", titel)
        stufen = [b["stufe"] for b in befunde]
        self.assertEqual(stufen, sorted(stufen, key=lambda s: {"hoch": 0, "mittel": 1, "info": 2}[s]))

    def test_unvollstaendiger_scan(self):
        befunde = support_core.diagnose(support_core.parse_report("Shops: 12"))
        self.assertTrue(any(b["titel"] == "Scan war unvollständig"
                            for b in befunde))

    def test_sideload_wird_erkannt(self):
        befunde = support_core.diagnose(support_core.parse_report(
            "Paket: de.ps5pro.ps5prosearchagent\nShops: 42\nTreffer: 1"))
        self.assertTrue(any("Sideload" in b["titel"] for b in befunde))

    def test_konfidenz_hinweis(self):
        befunde = support_core.diagnose(support_core.parse_report(
            "Konfidenz: 55\nShops: 42"))
        self.assertTrue(any("Konfidenz" in b["titel"] for b in befunde))

    def test_zusammenfassung(self):
        text = support_core.summarize(
            support_core.parse_report(support_core.BEISPIEL_BERICHT))
        self.assertIn("42 Shops", text)
        self.assertIn("12:04", text)


if __name__ == "__main__":
    unittest.main()
