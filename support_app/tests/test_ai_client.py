"""Tests für den KI-Client. Kein Kivy, kein echtes Netz: der Aufruf wird ersetzt."""
import io
import json
import os
import ssl
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_client  # noqa: E402


class EinstellungenTest(unittest.TestCase):
    def test_speichern_und_lesen(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = ai_client.settings_pfad(ordner)
            ai_client.save_settings(pfad, "  sk-test-123456789  ", "modell-a")
            daten = ai_client.load_settings(pfad)
            self.assertEqual(daten, {"key": "sk-test-123456789",
                                     "model": "modell-a"})

    def test_kaputte_datei_ergibt_leere_einstellungen(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = ai_client.settings_pfad(ordner)
            with open(pfad, "w", encoding="utf-8") as datei:
                datei.write("{kein json")
            self.assertEqual(ai_client.load_settings(pfad),
                             {"key": "", "model": ai_client.DEFAULT_MODEL})

    def test_mask_verraet_nichts(self):
        self.assertEqual(ai_client.mask(""), "")
        self.assertEqual(ai_client.mask("kurz"), "…")
        self.assertEqual(ai_client.mask("sk-1234567890abcdef"), "sk-1…cdef")


class PayloadTest(unittest.TestCase):
    def test_system_und_frage(self):
        payload = ai_client.build_payload("m1", "  Kein Alarm  ")
        self.assertEqual(payload["model"], "m1")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("PS5", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][-1],
                         {"role": "user", "content": "Kein Alarm"})

    def test_leere_frage(self):
        with self.assertRaises(ai_client.KiFehler):
            ai_client.build_payload("m1", "   ")

    def test_ohne_modell(self):
        with self.assertRaises(ai_client.KiFehler):
            ai_client.build_payload("", "Hallo")

    def test_kontext_wird_mitgeschickt(self):
        payload = ai_client.build_payload("m1", "Frage", kontext="KARTE A")
        self.assertEqual([m["role"] for m in payload["messages"]],
                         ["system", "system", "user"])
        self.assertIn("KARTE A", payload["messages"][1]["content"])

    def test_ohne_kontext_nur_zwei_nachrichten(self):
        payload = ai_client.build_payload("m1", "Frage")
        self.assertEqual(len(payload["messages"]), 2)

    def test_antwortlaenge_ist_begrenzt(self):
        payload = ai_client.build_payload("m1", "Frage")
        self.assertEqual(payload["max_tokens"], ai_client.MAX_TOKENS)
        self.assertLessEqual(ai_client.MAX_TOKENS, 500)


class AntwortTest(unittest.TestCase):
    def test_lesbar(self):
        daten = {"choices": [{"message": {"content": "  Antwort  "}}]}
        self.assertEqual(ai_client.parse_antwort(daten), "Antwort")

    def test_unerwartet(self):
        with self.assertRaises(ai_client.KiFehler):
            ai_client.parse_antwort({"foo": 1})

    def test_leer(self):
        daten = {"choices": [{"message": {"content": "   "}}]}
        with self.assertRaises(ai_client.KiFehler):
            ai_client.parse_antwort(daten)

    def test_zu_lange_antwort_wird_gekuerzt(self):
        daten = {"choices": [{"message": {
            "content": "x" * (ai_client.MAX_TEXT + 200)}}]}
        text = ai_client.parse_antwort(daten)
        self.assertLessEqual(len(text), ai_client.MAX_TEXT + 2)
        self.assertTrue(text.endswith("…"))


class FehlertextTest(unittest.TestCase):
    def test_status(self):
        self.assertIn("Key abgelehnt", ai_client.fehlertext(401))
        self.assertIn("429", ai_client.fehlertext(429))
        self.assertIn("nicht erreichbar", ai_client.fehlertext(503))
        self.assertIn("HTTP 418", ai_client.fehlertext(418))


def _antwort(daten):
    """Fake für urlopen: liefert JSON als BytesIO."""
    roh = json.dumps(daten).encode("utf-8")

    def oeffnen(_anfrage, timeout=None, context=None):
        return io.BytesIO(roh)

    return oeffnen


class ChatTest(unittest.TestCase):
    def test_antwort_wird_gelesen(self):
        opener = _antwort({"choices": [{"message": {"content": "Hallo"}}]})
        text = ai_client.chat({"key": "k", "model": "m"}, "Frage", opener=opener)
        self.assertEqual(text, "Hallo")

    def test_key_abgelehnt(self):
        def oeffnen(anfrage, timeout=None, context=None):
            raise urllib.error.HTTPError(anfrage.full_url, 401, "Nein", {}, None)

        with self.assertRaises(ai_client.KiFehler) as Kontext:
            ai_client.chat({"key": "k", "model": "m"}, "Frage", opener=oeffnen)
        self.assertIn("Key abgelehnt", str(Kontext.exception))

    def test_ohne_key(self):
        with self.assertRaises(ai_client.KeinKey):
            ai_client.chat({"key": "", "model": "m"}, "Frage")

    def test_keine_verbindung(self):
        def oeffnen(anfrage, timeout=None, context=None):
            raise urllib.error.URLError("offline")

        with self.assertRaises(ai_client.KiFehler) as Kontext:
            ai_client.chat({"key": "k", "model": "m"}, "Frage", opener=oeffnen)
        self.assertIn("Keine Verbindung", str(Kontext.exception))


class SSLTest(unittest.TestCase):
    def test_kontext_verlangt_zertifikate(self):
        self.assertEqual(ai_client.SSL_CONTEXT.verify_mode, ssl.CERT_REQUIRED)

    def test_https_bekommt_kontext(self):
        gesehen = {}

        def oeffnen(anfrage, timeout=None, context=None):
            gesehen["context"] = context
            return io.BytesIO(b'{"choices": [{"message": {"content": "ok"}}]}')

        ai_client.chat({"key": "k", "model": "m"}, "Frage", opener=oeffnen)
        self.assertIs(gesehen["context"], ai_client.SSL_CONTEXT)

    def test_404_nennt_modellwahl(self):
        self.assertIn("MODELL", ai_client.fehlertext(404))


class KontextTestChat(unittest.TestCase):
    def test_chat_schickt_kontext(self):
        gesehen = {}

        def oeffnen(anfrage, timeout=None, context=None):
            gesehen["body"] = json.loads(anfrage.data.decode("utf-8"))
            return io.BytesIO(
                b'{"choices": [{"message": {"content": "ok"}}]}')

        ai_client.chat({"key": "k", "model": "m"}, "Frage",
                       kontext="KARTE A", opener=oeffnen)
        self.assertIn("KARTE A", json.dumps(gesehen["body"]))


class EmpfehlungTest(unittest.TestCase):
    def test_bevorzugt_in_reihenfolge(self):
        alle = ["z", "gpt-5-mini", "deepseek-v4-flash", "a"]
        self.assertEqual(
            ai_client.empfohlene_modelle(alle),
            ["deepseek-v4-flash", "gpt-5-mini"])

    def test_sonst_die_ersten_20(self):
        alle = ["m%d" % i for i in range(30)]
        self.assertEqual(ai_client.empfohlene_modelle(alle), alle[:20])

    def test_leer(self):
        self.assertEqual(ai_client.empfohlene_modelle([]), [])


class ModelleTest(unittest.TestCase):
    def test_liste(self):
        opener = _antwort({"data": [{"id": "b"}, {"id": "a"}, {"id": ""}]})
        modelle = ai_client.liste_modelle({"key": "k"}, opener=opener)
        self.assertEqual(modelle, ["a", "b"])

    def test_ohne_key(self):
        opener = _antwort({"data": [{"id": "a"}]})
        self.assertEqual(ai_client.liste_modelle({"key": ""}, opener=opener),
                         ["a"])

    def test_leere_liste(self):
        opener = _antwort({"data": []})
        with self.assertRaises(ai_client.KiFehler):
            ai_client.liste_modelle({"key": "k"}, opener=opener)


if __name__ == "__main__":
    unittest.main()
