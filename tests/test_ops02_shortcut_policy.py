"""Windows shortcut planning: code is tested, no .exe/installer is produced."""
from pathlib import Path
import sys
import tempfile
import unittest

from config.install import preparar_atalho_windows


class AtalhoWindowsTests(unittest.TestCase):
    def test_shortcut_points_to_existing_binary_and_source_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parent.parent
            dest = Path(tmp) / "Meu DCA Monitor.lnk"
            ps = preparar_atalho_windows(
                dest, executavel=Path(sys.executable), script=root / "main.pyw"
            )
            self.assertIn("CreateShortcut", ps)
            self.assertIn(str(Path(sys.executable)), ps)
            self.assertIn("main.pyw", ps)
            self.assertFalse(dest.exists())
            self.assertEqual(str(dest.suffix), ".lnk")

    def test_invalid_shortcut_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, ".lnk"):
                preparar_atalho_windows(
                    Path(tmp) / "nao-criar.exe", executavel=Path(sys.executable)
                )

    def test_absent_executable_cannot_create_shortcut(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                preparar_atalho_windows(
                    Path(tmp) / "faltante.lnk",
                    executavel=Path(tmp) / "arquivo-inexistente.exe",
                )

if __name__ == "__main__":
    unittest.main()
