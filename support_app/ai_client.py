"""Online-KI für die Hilfe-App: eigener Key, direkter Aufruf der Freebuff-API.

Die App bleibt ohne Key vollständig offline. Wer online fragen will, trägt
seinen eigenen API-Key ein; er liegt nur im privaten App-Speicher und wird
nirgends protokolliert. Es gibt keinen eingebauten Key und keine Telemetrie.
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

BASE_URL = "https://freebuff.com/api/v1/paid"
CHAT_URL = BASE_URL + "/chat/completions"
MODELLE_URL = BASE_URL + "/models"
DATEI = "ki.json"
DEFAULT_MODEL = "deepseek-v4-flash"
# Kleine, guenstige Chat-Modelle zuerst; die volle Liste hat ~280 Eintraege
# und ist als Auswahlliste auf dem Telefon unbrauchbar.
BEVORZUGT = ("deepseek-v4-flash", "deepseek-v4.1-flash", "gpt-5-mini",
             "gpt-4o-mini", "claude-haiku-4-5", "gemini-2.5-flash")
# Die Modellliste der API ist gross (hunderte Eintraege, ~60 kB).
MAX_ANTWORT = 262144
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


def load_settings(pfad):
    """Liest Key und Modell; kaputte Dateien ergeben leere Einstellungen."""
    try:
        with open(pfad, "r", encoding="utf-8") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return {"key": "", "model": DEFAULT_MODEL}
    if not isinstance(daten, dict):
        return {"key": "", "model": DEFAULT_MODEL}
    return {
        "key": str(daten.get("key") or "").strip(),
        "model": str(daten.get("model") or DEFAULT_MODEL).strip(),
    }


def save_settings(pfad, key, model):
    """Schreibt die Einstellungen atomar und nur für den Nutzer lesbar."""
    ordner = os.path.dirname(pfad) or "."
    os.makedirs(ordner, exist_ok=True)
    zwischen = pfad + ".tmp"
    with open(zwischen, "w", encoding="utf-8") as datei:
        json.dump({"key": key.strip(), "model": model.strip()}, datei)
    try:
        os.chmod(zwischen, 0o600)
    except OSError:
        # Windows kennt keine POSIX-Rechte; der App-Ordner ist ohnehin privat.
        pass
    os.replace(zwischen, pfad)


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
        "User-Agent": "PS5ProHilfe/1.1.4",
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


def chat(settings, frage, verlauf=None, kontext="", opener=None, timeout=45):
    """Eine Frage an die KI; gibt den Antworttext zurück oder wirft KiFehler."""
    key = (settings or {}).get("key") or ""
    model = (settings or {}).get("model") or ""
    if not key:
        raise KeinKey("Kein Key gespeichert.")
    daten = _request(CHAT_URL, key,
                     build_payload(model, frage, verlauf, kontext),
                     timeout=timeout, opener=opener)
    return parse_antwort(daten)


def liste_modelle(settings, opener=None, timeout=20):
    """Verfügbare Modelle, alphabetisch sortiert (auch ohne Key abrufbar)."""
    key = (settings or {}).get("key") or ""
    daten = _request(MODELLE_URL, key, timeout=timeout, opener=opener,
                     key_pflicht=False)
    eintraege = daten.get("data") if isinstance(daten, dict) else None
    modelle = []
    for eintrag in eintraege or []:
        kennung = str((eintrag or {}).get("id") or "").strip()
        if kennung:
            modelle.append(kennung)
    if not modelle:
        raise KiFehler("Der Account meldet keine Modelle.")
    return sorted(set(modelle))


def empfohlene_modelle(alle):
    """Kurze Auswahlliste: bevorzugte Modelle, sonst die ersten 20."""
    vorrat = list(alle or [])
    vorhanden = [name for name in BEVORZUGT if name in vorrat]
    return vorhanden or vorrat[:20]
