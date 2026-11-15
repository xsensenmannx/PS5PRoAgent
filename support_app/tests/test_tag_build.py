"""Regressionstest für den Tag-Build: Version, versionCode und version.py
müssen in APK-Spec, Play-Spec und Anzeige gemeinsam gesetzt werden."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HIER = Path(__file__).resolve().parent
APP = HIER.parent
ROOT = APP.parent
SKRIPT = ROOT / "tools" / "set_version_from_tag.sh"


class TagBuildTest(unittest.TestCase):
    def _wert(self, pfad, schluessel):
        text = pfad.read_text(encoding="utf-8")
        treffer = re.search(
            r"^" + re.escape(schluessel) + r"\s*=\s*(.*)$", text, re.M)
        self.assertIsNotNone(treffer, f"{schluessel} fehlt in {pfad.name}")
        return treffer.group(1).strip()

    def test_tag_build_synchronisiert_specs_und_version_py(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash fehlt; der Tag-Build wird unter Linux geprüft")

        with tempfile.TemporaryDirectory() as temporaer:
            ziel = Path(temporaer)
            for name in ("buildozer.spec", "buildozer.play.spec", "version.py"):
                shutil.copy2(APP / name, ziel / name)

            lauf = subprocess.run(
                [bash, str(SKRIPT), "v9.8.7", str(ziel / "buildozer.spec")],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                check=False,
            )
            self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)

            for name in ("buildozer.spec", "buildozer.play.spec"):
                self.assertEqual(self._wert(ziel / name, "version"), "9.8.7")
                self.assertEqual(
                    self._wert(ziel / name, "android.numeric_version"), "90807")

            anzeige = (ziel / "version.py").read_text(encoding="utf-8")
            treffer = re.search(r'^VERSION\s*=\s*"([^"]+)"', anzeige, re.M)
            self.assertIsNotNone(treffer, "VERSION fehlt in version.py")
            self.assertEqual(treffer.group(1), "9.8.7")


if __name__ == "__main__":
    unittest.main()
