"""Online-KI für die Hilfe-App: mehrere Anbieter, jeweils eigener Key.

Die App bleibt ohne Key vollständig offline. Wer online fragen will, trägt
seinen eigenen API-Key ein; er liegt nur im privaten App-Speicher und wird
nirgends protokolliert. Es gibt keinen eingebauten Key, kein Teilen fremder
Kontingente und keine Telemetrie.

Unterstützt werden OpenAI-kompatible Endpunkte: Freebuff, OpenRouter (dort
ausdrücklich die kostenlosen ``:free``-Modelle), Groq, Google AI Studio und
ein lokal laufendes Ollama ohne Key.
"""
import json
import os
import ssl
import urllib.error
import urllib.request

try:
    import certifi
except ImportError:  # Desktop-Python hat meist eigene CAs; Android nicht.
    certifi = None

ANBIETER = {
    "freebuff": {
        "name": "Freebuff",
        "base": "https://freebuff.com/api/v1/paid",
        "key_url": "https://freebuff.com/account/api",
        "key_pflicht": True,
        "liste_ohne_key": True,
        "kosten": "Guthaben deines Freebuff-Accounts",
        "modelle": ("deepseek-v4-flash", "deepseek-v4.1-flash",
                    "gpt-5-mini", "gpt-4o-mini", "claude-haiku-4-5",
                    "gemini-2.5-flash"),
        "standard": "deepseek-v4-flash",
        "nur_free": False,
    },
    "openrouter": {
        "name": "OpenRouter",
        "base": "https://openrouter.ai/api/v1",
        "key_url": "https://openrouter.ai/keys",
        "key_pflicht": True,
        "liste_ohne_key": True,
        "kosten": "kostenloser Free-Router, 50 Anfragen/Tag",
        "modelle": ("openrouter/free",),
        "standard": "openrouter/free",
        "nur_free": True,
    },
    "groq": {
        "name": "Groq",
        "base": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
        "key_pflicht": True,
        "liste_ohne_key": False,
        "kosten": "kostenloses Kontingent",
        "modelle": ("openai/gpt-oss-120b", "openai/gpt-oss-20b",
                    "qwen/qwen3.8-27b"),
        "standard": "openai/gpt-oss-120b",
        "nur_free": False,
    },
    "google": {
        "name": "Google AI Studio",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_url": "https://aistudio.google.com/apikey",
        "key_pflicht": True,
        "liste_ohne_key": False,
        "kosten": "kostenloses Kontingent",
        "modelle": ("gemini-3.8-flash", "gemini-3.6-flash",
                    "gemini-2.5-flash"),
        "standard": "gemini-3.8-flash",
        "nur_free": False,
    },
    "mistral": {
        "name": "Mistral",
        "base": "https://api.mistral.ai/v1",
        "key_url": "https://console.mistral.ai/api-keys",
        "key_pflicht": True,
        "liste_ohne_key": False,
        "kosten": "Free-Mode mit Monatslimit",
        "modelle": ("mistral-small-latest",),
        "standard": "mistral-small-latest",
        "nur_free": False,
    },
    "ollama": {
        "name": "Ollama (lokal)",
        "base": "http://localhost:11434/v1",
        "key_url": "https://ollama.com/download",
        "key_pflicht": False,
        "liste_ohne_key": True,
        "kosten": "lokal auf deinem PC, kostenlos",
        "modelle": (),
        "standard": "",
        "nur_free": False,
    },
}
STANDARD_ANBIETER = "freebuff"
DATEI = "ki.json"
DEFAULT_MODEL = ANBIETER[STANDARD_ANBIETER]["standard"]
# Kleine, guenstige Chat-Modelle zuerst; die volle Liste hat ~280 Eintraege
# und ist als Auswahlliste auf dem Telefon unbrauchbar.
BEVORZUGT = ANBIETER[STANDARD_ANBIETER]["modelle"]
# Die Modellliste ist gross: OpenRouter liefert ~850 kB, Tendenz steigend.
MAX_ANTWORT = 4_000_000
MAX_FRAGE = 4000
# Kurze Antworten: weniger Gelegenheit, Einstellungen zu erfinden.
MAX_TOKENS = 450
MAX_TEXT = 1400
MAX_KONTEXT = 4000

SYSTEM = (
    "Du bist die Hilfe-App zum 'PS5 Pro Search Agent' (Konsolen-Radar), einer "
    "Android-App, die 42 Shops nach PS5-Pro-Angeboten durchsucht und Alarme "
    "sowie Webhooks verschickt. Antworte auf Deutsch, kurz und in Du-Form. "
    "Themen: Einrichtung, Alarme, Webhooks, Konfidenz, Chance-Zustände, "
    "Diagnosebericht, 403/429, Akku, Shops. Dir werden Auszüge aus den "
    "Hilfe-Karten mitgeschickt. Nutze nur Einstellungen, Schalter und Zahlen, "
    "die dort stehen. Steht etwas nicht in den Auszügen, sage das offen und "
    "verweise auf den Diagnose-Reiter; erfinde nichts. Antworte in höchstens "
    "fünf Sätzen. Keine Links, keine Kaufberatung."
)


def _ssl_kontext():
    """Kontext mit mitgelieferten CA-Zertifikaten.

    Android hat keinen CA-Store fuer Pythons OpenSSL; ohne eigenes Bundle
    scheitert HTTPS dort mit CERTIFICATE_VERIFY_FAILED. certifi liegt dem
    Build bei (buildozer.spec).
    """
    try:
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
    except (OSError, ssl.SSLError):
        pass
    return ssl.create_default_context()


SSL_CONTEXT = _ssl_kontext()


class KiFehler(Exception):
    """Fehler mit einer Meldung, die direkt in der App angezeigt werden darf."""


class KeinKey(KiFehler):
    pass


def settings_pfad(ordner):
    return os.path.join(ordner, DATEI)


def default_state():
    """Leerer Zustand mit allen Anbietern; Modell faellt auf den Standard."""
    return {
        "anbieter": STANDARD_ANBIETER,
        "keys": {name: "" for name in ANBIETER},
        "modelle": {name: "" for name in ANBIETER},
    }


def _bereinige(text):
    return str(text or "").strip()


def load_state(pfad):
    """Liest Anbieter, Keys und Modelle; kaputte Dateien ergeben leeren Zustand.

    Das alte Format ``{"key": ..., "model": ...}`` wird als Freebuff gelesen,
    damit ein Update niemanden aussperrt.
    """
    zustand = default_state()
    try:
        with open(pfad, "r", encoding="utf-8") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return zustand
    if not isinstance(daten, dict):
        return zustand
    if "keys" in daten or "modelle" in daten:
        gewaehlt = _bereinige(daten.get("anbieter"))
        zustand["anbieter"] = (gewaehlt if gewaehlt in ANBIETER
                               else STANDARD_ANBIETER)
        keys = daten.get("keys") if isinstance(daten.get("keys"), dict) else {}
        modelle = daten.get("modelle") if isinstance(
            daten.get("modelle"), dict) else {}
        for name in ANBIETER:
            zustand["keys"][name] = _bereinige(keys.get(name))
            zustand["modelle"][name] = _bereinige(modelle.get(name))
        return zustand
    zustand["keys"][STANDARD_ANBIETER] = _bereinige(daten.get("key"))
    zustand["modelle"][STANDARD_ANBIETER] = _bereinige(daten.get("model"))
    return zustand


def save_state(pfad, zustand):
    """Schreibt den Zustand atomar und nur für den Nutzer lesbar."""
    ordner = os.path.dirname(pfad) or "."
    os.makedirs(ordner, exist_ok=True)
    daten = {
        "anbieter": (zustand.get("anbieter") or STANDARD_ANBIETER),
        "keys": {name: _bereinige((zustand.get("keys") or {}).get(name))
                 for name in ANBIETER},
        "modelle": {name: _bereinige((zustand.get("modelle") or {}).get(name))
                    for name in ANBIETER},
    }
    zwischen = pfad + ".tmp"
    with open(zwischen, "w", encoding="utf-8") as datei:
        json.dump(daten, datei, ensure_ascii=False, indent=2)
    try:
        os.chmod(zwischen, 0o600)
    except OSError:
        # Windows kennt keine POSIX-Rechte; der App-Ordner ist ohnehin privat.
        pass
    os.replace(zwischen, pfad)


def anbieter_info(name):
    """Konfiguration eines Anbieters; unbekannte Namen fallen auf Standard."""
    return ANBIETER.get(name) or ANBIETER[STANDARD_ANBIETER]


def key_fuer(zustand, name=None):
    name = name or (zustand.get("anbieter") or STANDARD_ANBIETER)
    return _bereinige((zustand.get("keys") or {}).get(name))


def modell_fuer(zustand, name=None):
    name = name or (zustand.get("anbieter") or STANDARD_ANBIETER)
    gewaehlt = _bereinige((zustand.get("modelle") or {}).get(name))
    return gewaehlt or anbieter_info(name)["standard"]


def mask(key):
    """Kurze Anzeige für Hinweise, ohne den Key zu verraten."""
    key = (key or "").strip()
    if len(key) < 12:
        return "…" if key else ""
    return key[:4] + "…" + key[-4:]


def build_payload(model, frage, verlauf=None, kontext=""):
    if not model:
        raise KiFehler("Kein Modell gewählt.")
    frage = (frage or "").strip()[:MAX_FRAGE]
    if not frage:
        raise KiFehler("Die Frage ist leer.")
    nachrichten = [{"role": "system", "content": SYSTEM}]
    kontext = (kontext or "").strip()[:MAX_KONTEXT]
    if kontext:
        nachrichten.append({
            "role": "system",
            "content": "Auszüge aus den Hilfe-Karten:\n\n" + kontext,
        })
    for eintrag in verlauf or []:
        rolle = eintrag.get("role")
        inhalt = str(eintrag.get("content") or "").strip()[:MAX_FRAGE]
        if rolle in ("user", "assistant") and inhalt:
            nachrichten.append({"role": rolle, "content": inhalt})
    nachrichten.append({"role": "user", "content": frage})
    return {"model": model, "messages": nachrichten,
            "max_tokens": MAX_TOKENS}


def fehlertext(status):
    if status in (401, 403):
        return ("Key abgelehnt (HTTP %d). Prüfe den Key unter „KEY“." % status)
    if status == 404:
        return ("Modell oder Adresse nicht gefunden (HTTP 404). Prüfe die "
                "Modellwahl unter „MODELL“.")
    if status == 429:
        return ("Limit erreicht (HTTP 429). Warte kurz oder prüfe dein "
                "Guthaben.")
    if 500 <= status < 600:
        return "Dienst nicht erreichbar (HTTP %d). Später nochmal." % status
    return "Anfrage fehlgeschlagen (HTTP %d)." % status


def parse_antwort(daten):
    try:
        text = daten["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise KiFehler("Unerwartete Antwort der KI.") from None
    text = str(text or "").strip()
    if not text:
        raise KiFehler("Die KI hat nichts geantwortet.")
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT].rstrip() + " …"
    return text


def _request(url, key, payload=None, timeout=45, opener=None, key_pflicht=True):
    if key_pflicht and not key:
        raise KeinKey("Kein Key gespeichert.")
    daten = None
    kopf = {
        "Accept": "application/json",
        "User-Agent": "PS5ProHilfe/1.2.0",
    }
    if key:
        kopf["Authorization"] = "Bearer " + key
    if payload is not None:
        daten = json.dumps(payload).encode("utf-8")
        kopf["Content-Type"] = "application/json"
    anfrage = urllib.request.Request(
        url, data=daten, headers=kopf, method="POST" if daten else "GET")
    oeffnen = opener or urllib.request.urlopen
    optionen = {"timeout": timeout}
    if url.startswith("https://"):
        optionen["context"] = SSL_CONTEXT
    try:
        with oeffnen(anfrage, **optionen) as antwort:
            roh = antwort.read(MAX_ANTWORT + 1)
    except urllib.error.HTTPError as fehler:
        raise KiFehler(fehlertext(fehler.code)) from None
    except urllib.error.URLError as fehler:
        grund = getattr(fehler, "reason", fehler)
        raise KiFehler("Keine Verbindung (%s). Prüfe Internet." % grund) from None
    except OSError as fehler:
        raise KiFehler("Keine Verbindung (%s). Prüfe Internet." % fehler) from None
    if len(roh) > MAX_ANTWORT:
        raise KiFehler("Die Antwort ist zu groß.")
    try:
        return json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise KiFehler("Die Antwort war kein gültiges JSON.") from None


def chat(zustand, frage, verlauf=None, kontext="", opener=None, timeout=45,
         anbieter=None):
    """Eine Frage an den gewählten Anbieter; gibt den Antworttext zurück."""
    name = anbieter or (zustand or {}).get("anbieter") or STANDARD_ANBIETER
    info = anbieter_info(name)
    key = key_fuer(zustand, name)
    model = modell_fuer(zustand, name)
    if info["key_pflicht"] and not key:
        raise KeinKey("%s braucht einen eigenen Key." % info["name"])
    if not model:
        raise KiFehler("Kein Modell gewählt. Lade unter „KEY“ die Modelle.")
    daten = _request(info["base"] + "/chat/completions", key,
                     build_payload(model, frage, verlauf, kontext),
                     timeout=timeout, opener=opener,
                     key_pflicht=info["key_pflicht"])
    return parse_antwort(daten)


def liste_modelle(zustand, anbieter=None, opener=None, timeout=20):
    """Verfügbare Modelle des Anbieters, alphabetisch sortiert."""
    name = anbieter or (zustand or {}).get("anbieter") or STANDARD_ANBIETER
    info = anbieter_info(name)
    key = key_fuer(zustand, name)
    if not info.get("liste_ohne_key") and not key:
        raise KeinKey("%s braucht zuerst einen Key." % info["name"])
    daten = _request(info["base"] + "/models", key,
                     timeout=timeout, opener=opener, key_pflicht=False)
    eintraege = daten.get("data") if isinstance(daten, dict) else None
    modelle = []
    for eintrag in eintraege or []:
        kennung = str((eintrag or {}).get("id") or "").strip()
        if kennung:
            modelle.append(kennung)
    if not modelle:
        raise KiFehler("Der Anbieter meldet keine Modelle.")
    return sorted(set(modelle))


def empfohlene_modelle(alle, anbieter=STANDARD_ANBIETER):
    """Kurze Auswahlliste passend zum Anbieter."""
    vorrat = list(alle or [])
    info = anbieter_info(anbieter)
    if info.get("nur_free"):
        frei = [name for name in vorrat
                if name.endswith(":free") or name == "openrouter/free"]
        if frei:
            return frei[:20]
    vorhanden = [name for name in info["modelle"] if name in vorrat]
    return vorhanden or vorrat[:20]
