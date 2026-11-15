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


def _zustand(key="k", modell="m", anbieter="freebuff"):
    zustand = ai_client.default_state()
    zustand["anbieter"] = anbieter
    zustand["keys"][anbieter] = key
    zustand["modelle"][anbieter] = modell
    return zustand


class EinstellungenTest(unittest.TestCase):
    def test_speichern_und_lesen(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = ai_client.settings_pfad(ordner)
            zustand = _zustand("  sk-test-123456789  ", "modell-a", "groq")
            zustand["keys"]["openrouter"] = "or-key"
            ai_client.save_state(pfad, zustand)
            daten = ai_client.load_state(pfad)
            self.assertEqual(daten["anbieter"], "groq")
            self.assertEqual(daten["keys"]["groq"], "sk-test-123456789")
            self.assertEqual(daten["keys"]["openrouter"], "or-key")
            self.assertEqual(daten["modelle"]["groq"], "modell-a")

    def test_alte_datei_wird_freebuff(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = ai_client.settings_pfad(ordner)
            with open(pfad, "w", encoding="utf-8") as datei:
                json.dump({"key": "alt", "model": "alt-modell"}, datei)
            daten = ai_client.load_state(pfad)
            self.assertEqual(daten["anbieter"], "freebuff")
            self.assertEqual(daten["keys"]["freebuff"], "alt")
            self.assertEqual(daten["modelle"]["freebuff"], "alt-modell")

    def test_kaputte_datei_ergibt_leeren_zustand(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = ai_client.settings_pfad(ordner)
            with open(pfad, "w", encoding="utf-8") as datei:
                datei.write("{kein json")
            self.assertEqual(ai_client.load_state(pfad),
                             ai_client.default_state())

    def test_mask_verraet_nichts(self):
        self.assertEqual(ai_client.mask(""), "")
        self.assertEqual(ai_client.mask("kurz"), "…")
        self.assertEqual(ai_client.mask("sk-1234567890abcdef"), "sk-1…cdef")


class AnbieterTest(unittest.TestCase):
    def test_bekannte_anbieter(self):
        for name in ("freebuff", "openrouter", "groq", "google", "mistral",
                     "ollama"):
            self.assertIn(name, ai_client.ANBIETER)
            self.assertTrue(ai_client.ANBIETER[name]["base"].startswith("http"))

    def test_unbekannter_anbieter_faellt_zurueck(self):
        self.assertEqual(ai_client.anbieter_info("gibt-es-nicht")["name"],
                         ai_client.ANBIETER["freebuff"]["name"])

    def test_ollama_braucht_keinen_key(self):
        self.assertFalse(ai_client.ANBIETER["ollama"]["key_pflicht"])

    def test_key_seiten_sind_https(self):
        for name, info in ai_client.ANBIETER.items():
            self.assertTrue(info["key_url"].startswith("https://"), name)


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

    def test_404_nennt_modellwahl(self):
        self.assertIn("MODELL", ai_client.fehlertext(404))


def _antwort(daten):
    """Fake für urlopen: liefert JSON als BytesIO."""
    roh = json.dumps(daten).encode("utf-8")

    def oeffnen(_anfrage, timeout=None, context=None):
        return io.BytesIO(roh)

    return oeffnen


class ChatTest(unittest.TestCase):
    def test_antwort_wird_gelesen(self):
        opener = _antwort({"choices": [{"message": {"content": "Hallo"}}]})
        text = ai_client.chat(_zustand(), "Frage", opener=opener)
        self.assertEqual(text, "Hallo")

    def test_key_abgelehnt(self):
        def oeffnen(anfrage, timeout=None, context=None):
            raise urllib.error.HTTPError(anfrage.full_url, 401, "Nein", {}, None)

        with self.assertRaises(ai_client.KiFehler) as Kontext:
            ai_client.chat(_zustand(), "Frage", opener=oeffnen)
        self.assertIn("Key abgelehnt", str(Kontext.exception))

    def test_ohne_key(self):
        with self.assertRaises(ai_client.KeinKey):
            ai_client.chat(_zustand(key=""), "Frage")

    def test_ohne_key_nennt_anbieter(self):
        with self.assertRaises(ai_client.KeinKey) as Kontext:
            ai_client.chat(_zustand(key="", anbieter="groq"), "Frage")
        self.assertIn("Groq", str(Kontext.exception))

    def test_keine_verbindung(self):
        def oeffnen(anfrage, timeout=None, context=None):
            raise urllib.error.URLError("offline")

        with self.assertRaises(ai_client.KiFehler) as Kontext:
            ai_client.chat(_zustand(), "Frage", opener=oeffnen)
        self.assertIn("Keine Verbindung", str(Kontext.exception))

    def test_openrouter_nutzt_eigene_adresse(self):
        gesehen = {}

        def oeffnen(anfrage, timeout=None, context=None):
            gesehen["url"] = anfrage.full_url
            gesehen["auth"] = anfrage.get_header("Authorization")
            return io.BytesIO(
                b'{"choices": [{"message": {"content": "ok"}}]}')

        ai_client.chat(_zustand(anbieter="openrouter"), "Frage",
                       opener=oeffnen)
        self.assertEqual(gesehen["url"],
                         "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(gesehen["auth"], "Bearer k")

    def test_ollama_laeuft_ohne_key_und_ohne_tls(self):
        gesehen = {}

        def oeffnen(anfrage, timeout=None, context=None):
            gesehen["url"] = anfrage.full_url
            gesehen["auth"] = anfrage.get_header("Authorization")
            gesehen["context"] = context
            return io.BytesIO(
                b'{"choices": [{"message": {"content": "lokal"}}]}')

        text = ai_client.chat(
            _zustand(key="", modell="llama3.2", anbieter="ollama"),
            "Frage", opener=oeffnen)
        self.assertEqual(text, "lokal")
        self.assertEqual(gesehen["url"],
                         "http://localhost:11434/v1/chat/completions")
        self.assertIsNone(gesehen["auth"])
        self.assertIsNone(gesehen["context"])

    def test_ohne_modell(self):
        with self.assertRaises(ai_client.KiFehler):
            ai_client.chat(_zustand(anbieter="ollama", modell=""), "Frage")


class SSLTest(unittest.TestCase):
    def test_kontext_verlangt_zertifikate(self):
        self.assertEqual(ai_client.SSL_CONTEXT.verify_mode, ssl.CERT_REQUIRED)

    def test_https_bekommt_kontext(self):
        gesehen = {}

        def oeffnen(anfrage, timeout=None, context=None):
            gesehen["context"] = context
            return io.BytesIO(
                b'{"choices": [{"message": {"content": "ok"}}]}')

        ai_client.chat(_zustand(), "Frage", opener=oeffnen)
        self.assertIs(gesehen["context"], ai_client.SSL_CONTEXT)


class KontextTestChat(unittest.TestCase):
    def test_chat_schickt_kontext(self):
        gesehen = {}

        def oeffnen(anfrage, timeout=None, context=None):
            gesehen["body"] = json.loads(anfrage.data.decode("utf-8"))
            return io.BytesIO(
                b'{"choices": [{"message": {"content": "ok"}}]}')

        ai_client.chat(_zustand(), "Frage", kontext="KARTE A", opener=oeffnen)
        self.assertIn("KARTE A", json.dumps(gesehen["body"]))


class EmpfehlungTest(unittest.TestCase):
    def test_freebuff_bevorzugt_in_reihenfolge(self):
        alle = ["z", "gpt-5-mini", "deepseek-v4-flash", "a"]
        self.assertEqual(
            ai_client.empfohlene_modelle(alle, "freebuff"),
            ["deepseek-v4-flash", "gpt-5-mini"])

    def test_openrouter_nur_free_modelle(self):
        alle = ["openai/gpt-4o", "meta/llama:free", "z-ai/glm:free"]
        self.assertEqual(
            ai_client.empfohlene_modelle(alle, "openrouter"),
            ["meta/llama:free", "z-ai/glm:free"])

    def test_openrouter_free_router_bleibt_in_auswahl(self):
        alle = ["openrouter/free", "openai/gpt-4o", "z-ai/glm:free"]
        self.assertEqual(
            ai_client.empfohlene_modelle(alle, "openrouter"),
            ["openrouter/free", "z-ai/glm:free"])

    def test_openrouter_ohne_free_faellt_zurueck(self):
        alle = ["m%d" % i for i in range(25)]
        self.assertEqual(ai_client.empfohlene_modelle(alle, "openrouter"),
                         alle[:20])

    def test_sonst_die_ersten_20(self):
        alle = ["m%d" % i for i in range(30)]
        self.assertEqual(ai_client.empfohlene_modelle(alle, "groq"), alle[:20])

    def test_leer(self):
        self.assertEqual(ai_client.empfohlene_modelle([], "freebuff"), [])


class ModelleTest(unittest.TestCase):
    def test_liste(self):
        opener = _antwort({"data": [{"id": "b"}, {"id": "a"}, {"id": ""}]})
        modelle = ai_client.liste_modelle(_zustand(), opener=opener)
        self.assertEqual(modelle, ["a", "b"])

    def test_ohne_key_abrufbar(self):
        opener = _antwort({"data": [{"id": "a"}]})
        self.assertEqual(ai_client.liste_modelle(_zustand(key=""), opener=opener),
                         ["a"])

    def test_openrouter_liste_ohne_key(self):
        opener = _antwort({"data": [{"id": "openrouter/free"}]})
        modelle = ai_client.liste_modelle(
            _zustand(key="", anbieter="openrouter"), opener=opener)
        self.assertEqual(modelle, ["openrouter/free"])

    def test_key_pflicht_ohne_key(self):
        with self.assertRaises(ai_client.KeinKey):
            ai_client.liste_modelle(_zustand(key="", anbieter="groq"))

    def test_leere_liste(self):
        opener = _antwort({"data": []})
        with self.assertRaises(ai_client.KiFehler):
            ai_client.liste_modelle(_zustand(), opener=opener)

    def test_ollama_modelle_lokal(self):
        gesehen = {}

        def oeffnen(anfrage, timeout=None, context=None):
            gesehen["url"] = anfrage.full_url
            return io.BytesIO(b'{"data": [{"id": "llama3.2"}]}')

        modelle = ai_client.liste_modelle(
            _zustand(key="", anbieter="ollama"), opener=oeffnen)
        self.assertEqual(modelle, ["llama3.2"])
        self.assertEqual(gesehen["url"],
                         "http://localhost:11434/v1/models")


if __name__ == "__main__":
    unittest.main()
