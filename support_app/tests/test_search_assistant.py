"""Tests für den Suchassistenten. Ohne Kivy, ohne Netz."""
import os
import sys
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
SUPPORT = os.path.dirname(HIER)
REPO = os.path.dirname(SUPPORT)
sys.path.insert(0, SUPPORT)
sys.path.insert(0, REPO)

import search_assistant  # noqa: E402
from shops import SHOPS, SHOP_COUNT  # noqa: E402

try:  # Nur im Repository vorhanden, nicht im APK.
    import scan_core
    ECHTE_SHOPS = {h["name"] for h in scan_core.HAENDLER}
except Exception:  # pragma: no cover
    ECHTE_SHOPS = None


class ShopListeTest(unittest.TestCase):
    def test_anzahl_und_eindeutigkeit(self):
        self.assertEqual(SHOP_COUNT, 42)
        self.assertEqual(len(SHOPS), len(set(SHOPS)))

    @unittest.skipUnless(ECHTE_SHOPS, "scan_core nicht im Suchpfad")
    def test_shops_passen_zu_scan_core(self):
        self.assertEqual(set(SHOPS), ECHTE_SHOPS)


class PreisTest(unittest.TestCase):
    def test_unter_mit_shop(self):
        f = search_assistant.parse_query("unter 700, nur amazon")
        self.assertEqual(f["preis"], 700.0)
        self.assertEqual(f["shops"], ["Amazon DE"])

    def test_euro_zeichen(self):
        self.assertEqual(search_assistant.parse_query("800 €")["preis"], 800.0)

    def test_tausenderpunkt(self):
        self.assertEqual(
            search_assistant.parse_query("unter 1.000 €")["preis"], 1000.0)

    def test_grenzen_sind_gueltig(self):
        self.assertEqual(search_assistant.parse_query("unter 400")["preis"], 400.0)
        self.assertEqual(search_assistant.parse_query("bis 1.500")["preis"], 1500.0)

    def test_ausserhalb_bereich(self):
        for text in ("unter 350", "unter 1.600"):
            f = search_assistant.parse_query(text)
            self.assertIsNone(f["preis"], text)
            self.assertTrue(f["warnungen"], text)

    def test_shops_sind_kein_preis(self):
        self.assertIsNone(search_assistant.parse_query("alle 42 shops")["preis"])


class ShopTest(unittest.TestCase):
    def test_ohne_land_ist_deutschland_standard(self):
        self.assertEqual(search_assistant.parse_query("amazon")["shops"],
                         ["Amazon DE"])

    def test_oesterreich(self):
        self.assertEqual(
            search_assistant.parse_query("mediamarkt in oesterreich")["shops"],
            ["MediaMarkt AT"])

    def test_domain_form(self):
        self.assertEqual(search_assistant.parse_query("amazon.at")["shops"],
                         ["Amazon AT"])

    def test_reihenfolge_der_nennung(self):
        self.assertEqual(
            search_assistant.parse_query("nur saturn und cyberport")["shops"],
            ["Saturn DE", "Cyberport DE"])

    def test_langes_alias_gewinnt(self):
        self.assertEqual(search_assistant.parse_query("computerexpert")["shops"],
                         ["Computerexpert AT"])

    def test_unbekannter_shop(self):
        self.assertEqual(search_assistant.parse_query("nur kleinanzeigen")["shops"], [])


class FilterTest(unittest.TestCase):
    def test_nur_bestaetigte(self):
        self.assertTrue(
            search_assistant.parse_query("nur bestätigte")["nur_bestaetigt"])

    def test_verfuegbar(self):
        self.assertEqual(search_assistant.parse_query("nur verfügbar")["filter"],
                         "verfuegbar")

    def test_alle_shops(self):
        self.assertEqual(search_assistant.parse_query("alle shops")["filter"], "alle")

    def test_alle_minuten_ist_kein_filter(self):
        f = search_assistant.parse_query("alle 15 minuten")
        self.assertIsNone(f["filter"])
        self.assertEqual(f["intervall"], 900)

    def test_preis_loest_keine_sortierung_aus(self):
        # Regression: "preis bis 700" setzte früher zusätzlich sort=Preis.
        f = search_assistant.parse_query("preis bis 700")
        self.assertEqual(f["preis"], 700.0)
        self.assertIsNone(f["sort"])

    def test_sortieren_nach_zeit(self):
        self.assertEqual(search_assistant.parse_query("sortiere nach zeit")["sort"],
                         "Zeit")

    def test_guenstigste_sortiert_nach_preis(self):
        self.assertEqual(search_assistant.parse_query("die günstigste")["sort"],
                         "Preis")

    def test_schnellmodus(self):
        self.assertTrue(search_assistant.parse_query("schnellmodus")["schnellscan"])


class ZustandTest(unittest.TestCase):
    def test_nur_neu_ist_hinweis_nicht_einstellung(self):
        plan = search_assistant.build_plan("nur neu")
        namen = " ".join(n for n, _ in plan["einstellungen"])
        self.assertNotIn("zustand", namen.lower())
        self.assertTrue(any("Zustand" in h or "neu" in h
                            for h in plan["hinweise"]))


class PlanTest(unittest.TestCase):
    def test_plan_hat_schritte_und_einstellungen(self):
        plan = search_assistant.build_plan("unter 700, nur amazon, nur neu")
        self.assertEqual(plan["kind"], "plan")
        self.assertIn("700", plan["zusammenfassung"])
        self.assertTrue(plan["schritte"])
        namen = [n for n, _ in plan["einstellungen"]]
        self.assertTrue(any("max_preis" in n for n in namen))
        self.assertTrue(any("active_haendler" in n for n in namen))

    def test_ps_direct_als_manuelle_quelle(self):
        plan = search_assistant.build_plan("nur ps direct")
        self.assertTrue(any("manuelle Quelle" in h for h in plan["hinweise"]))

    def test_unklar(self):
        plan = search_assistant.build_plan("hallo")
        self.assertEqual(plan["kind"], "unklar")
        self.assertIn("Suchauftrag", plan["text"])

    def test_format(self):
        text = search_assistant.format_plan(
            search_assistant.build_plan("unter 700, nur amazon"))
        self.assertIn("SUCHAUFTRAG", text)
        self.assertIn("EINSTELLUNGEN IM RADAR", text)
        self.assertIn("Amazon DE", text)

    def test_ohne_shop_gilt_der_standard(self):
        plan = search_assistant.build_plan("unter 900")
        self.assertIn("alle 42", plan["einstellungen"][0][1])


if __name__ == "__main__":
    unittest.main()
