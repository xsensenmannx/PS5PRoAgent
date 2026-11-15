"""Tests für den lokalen Meldespeicher. Kein Kivy, kein Netz."""
from datetime import datetime, timezone
import os
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meldungen  # noqa: E402


JETZT = datetime(2026, 11, 15, 12, 30, tzinfo=timezone.utc)


def _meldung(kategorie="hass", nummer="1"):
    return meldungen.erstelle(
        kategorie,
        notiz="Bitte prüfen",
        frage="Warum?",
        antwort="Das ist die Antwort.",
        anbieter="freebuff",
        modell="deepseek-v4-flash",
        version="1.2.0",
        now=JETZT,
    ) | {"id": "M-20261115-123000-%s" % nummer}


class ErstellenTest(unittest.TestCase):
    def test_id_ist_lesbar_und_eindeutig(self):
        probe = meldungen.neue_id(JETZT)
        self.assertRegex(probe, r"^M-20261115-123000-[0-9A-F]{6}$")
        self.assertNotEqual(probe, meldungen.neue_id(JETZT))

    def test_felder_und_kein_key(self):
        eintrag = meldungen.erstelle(
            "gewalt", notiz="  Drohung  ", frage=" Frage ",
            antwort=" Antwort ", anbieter="groq", modell="m",
            version="1.2.0", now=JETZT)
        self.assertEqual(eintrag["kategorie_label"], "Gewalt oder Drohung")
        self.assertEqual(eintrag["notiz"], "Drohung")
        self.assertEqual(eintrag["frage"], "Frage")
        self.assertEqual(eintrag["antwort"], "Antwort")
        self.assertEqual(eintrag["zeit"], "2026-11-15T12:30:00Z")
        self.assertEqual(eintrag["status"], "neu")
        self.assertNotIn("key", eintrag)
        self.assertNotIn("api", eintrag)

    def test_unbekannte_kategorie(self):
        with self.assertRaises(ValueError):
            meldungen.erstelle("unbekannt", now=JETZT)

    def test_lange_texte_werden_begrenzt(self):
        eintrag = meldungen.erstelle(
            "sonstiges", notiz="n" * 900, frage="f" * 5000,
            antwort="a" * 5000, now=JETZT)
        self.assertEqual(len(eintrag["notiz"]), meldungen.MAX_NOTIZ)
        self.assertEqual(len(eintrag["frage"]), meldungen.MAX_FRAGE)
        self.assertEqual(len(eintrag["antwort"]), meldungen.MAX_ANTWORT)

    def test_alle_kategorien(self):
        self.assertEqual(len(meldungen.KATEGORIEN), 6)
        for code, label in meldungen.KATEGORIEN:
            self.assertEqual(meldungen.erstelle(code, now=JETZT)["kategorie"], code)
            self.assertTrue(label)


class SpeicherTest(unittest.TestCase):
    def test_speichern_laden_und_entfernen(self):
        with tempfile.TemporaryDirectory() as ordner:
            datei = meldungen.pfad(ordner)
            a = _meldung("hass", "A")
            b = _meldung("sexuell", "B")
            meldungen.speichern(datei, a)
            meldungen.speichern(datei, b)
            geladen = meldungen.laden(datei)
            self.assertEqual([x["id"] for x in geladen], [a["id"], b["id"]])
            self.assertEqual(meldungen.entfernen(datei, a["id"]), 1)
            self.assertEqual([x["id"] for x in meldungen.laden(datei)], [b["id"]])

    def test_kaputte_datei_blockiert_nicht(self):
        with tempfile.TemporaryDirectory() as ordner:
            datei = meldungen.pfad(ordner)
            with open(datei, "w", encoding="utf-8") as f:
                f.write("{kein json")
            self.assertEqual(meldungen.laden(datei), [])
            meldungen.speichern(datei, _meldung())
            self.assertEqual(len(meldungen.laden(datei)), 1)

    def test_maximal_fuenfzig_meldungen(self):
        with tempfile.TemporaryDirectory() as ordner:
            datei = meldungen.pfad(ordner)
            for i in range(55):
                meldungen.speichern(datei, _meldung(nummer=str(i)))
            geladen = meldungen.laden(datei)
            self.assertEqual(len(geladen), meldungen.MAX_MELDUNGEN)
            self.assertEqual(geladen[-1]["id"], "M-20261115-123000-54")

    def test_leeren(self):
        with tempfile.TemporaryDirectory() as ordner:
            datei = meldungen.pfad(ordner)
            meldungen.speichern(datei, _meldung())
            self.assertEqual(meldungen.leeren(datei), 0)
            self.assertEqual(meldungen.laden(datei), [])


class TextTest(unittest.TestCase):
    def test_bericht_enthaelt_alles_wichtige(self):
        text = meldungen.als_text(_meldung())
        for teil in ("KI-Meldung M-", "Kategorie: Hass", "Frage:", "Antwort:",
                     "Notiz:", "Anbieter: freebuff"):
            self.assertIn(teil, text)
        self.assertNotIn("Authorization", text)

    def test_mailto_ist_kodiert_und_an_den_kontakt_adressiert(self):
        uri = meldungen.mailto_url(_meldung())
        self.assertTrue(uri.startswith("mailto:smiley.medical%40gmail.com?"))
        daten = parse_qs(urlparse(uri).query)
        self.assertIn("Hilfe-App", daten["subject"][0])
        self.assertIn("M-20261115", daten["body"][0])
        self.assertIn("Das ist die Antwort", daten["body"][0])


if __name__ == "__main__":
    unittest.main()
