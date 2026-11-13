"""Einmalige GitHub-Aufraeumung fuer PS5PRoAgent.

Behalten werden ausschliesslich die Releases/Tags v1.0, v3.3.2 und v5.0.
Geloescht werden alle anderen Releases, Tags, Workflow-Laeufe, Artefakte und
Caches. Der laufende Aufraeum-Workflow selbst bleibt erhalten.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ["REPO"]
CURRENT_RUN_ID = os.environ["CURRENT_RUN_ID"]
BASE = "https://api.github.com/repos/%s" % REPO
KEEP = {"v1.0", "v3.3.2", "v5.0"}
HEADERS = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "PS5PRoAgent-cleanup",
}
errors = []
summary_path = os.environ.get("GITHUB_STEP_SUMMARY")


def summary(line):
    print(line)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def request(method, path, payload=None):
    url = BASE + path
    data = None
    headers = dict(HEADERS)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        errors.append("%s %s -> HTTP %s: %s" % (method, path, exc.code, body[:300]))
        print("WARN %s %s -> HTTP %s" % (method, path, exc.code))
        return exc.code, None


def list_all(path, key=None):
    """Liste laden; GitHub liefert je nach Endpoint Liste oder Objekt."""
    status, data = request("GET", path + ("&" if "?" in path else "?") + "per_page=100")
    if status != 200:
        return []
    if isinstance(data, dict):
        data = data.get(key, [])
    return data if isinstance(data, list) else []


def delete(path):
    return request("DELETE", path)[0]


releases = list_all("/releases")
for release in releases:
    tag = release.get("tag_name")
    if tag in KEEP:
        print("BEHALTE Release", tag)
        continue
    print("LOESCHE Release", tag)
    delete("/releases/%s" % release["id"])

tags = list_all("/git/refs/tags")
for ref in tags:
    full = ref.get("ref", "")
    tag = full.removeprefix("refs/tags/")
    if tag in KEEP:
        print("BEHALTE Tag", tag)
        continue
    print("LOESCHE Tag", tag)
    delete("/git/refs/%s" % urllib.parse.quote(full, safe=""))

for run in list_all("/actions/runs", "workflow_runs"):
    if str(run.get("id")) == str(CURRENT_RUN_ID):
        print("BEHALTE aktuellen Aufraeum-Lauf", run.get("id"))
        continue
    print("LOESCHE Workflow-Lauf", run.get("id"), run.get("name"), run.get("conclusion"))
    delete("/actions/runs/%s" % run["id"])

for artifact in list_all("/actions/artifacts", "artifacts"):
    print("LOESCHE Artefakt", artifact.get("name"), artifact.get("id"))
    delete("/actions/artifacts/%s" % artifact["id"])

for cache in list_all("/actions/caches", "actions_caches"):
    print("LOESCHE Cache", cache.get("key"), cache.get("id"))
    delete("/actions/caches/%s" % cache["id"])

summary("## GitHub-Aufraeumung")
summary("")
summary("Verbleibende Fehler: %s" % len(errors))
for error in errors:
    summary("- FEHLER: `%s`" % error.replace("`", "'"))
# Ein einzelner nicht loeschbarer Lauf soll den Aufraeumlauf nicht rot machen;
# die Zusammenfassung zeigt trotzdem jeden Fehler.
sys.exit(0)
