"""Desktop settings behavior; no live network, installer or downloaded release."""
from pathlib import Path
from urllib.error import HTTPError, URLError
import json
import tempfile
import unittest

from backend.app_lifecycle import (
    APP_VERSION, arquivo_preferencias, carregar_preferencias,
    salvar_preferencias, verificar_release_estavel,
)


class ConfiguracoesDesktopTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base=Path(t.name)

    def test_background_mode_is_opt_in_and_persistent(self):
        self.assertFalse(carregar_preferencias(self.base)["minimizar_para_bandeja"])
        result=salvar_preferencias({"minimizar_para_bandeja":True},self.base)
        self.assertTrue(result["minimizar_para_bandeja"])
        self.assertTrue(carregar_preferencias(self.base)["minimizar_para_bandeja"])
        saved=json.loads(arquivo_preferencias(self.base).read_text("utf-8"))
        self.assertEqual(saved,{"minimizar_para_bandeja":True})
        salvar_preferencias({"minimizar_para_bandeja":False},self.base)
        self.assertFalse(carregar_preferencias(self.base)["minimizar_para_bandeja"])

    def test_malformed_preferences_fail_safe_without_tray(self):
        arquivo_preferencias(self.base).write_text("{nao_e_json",encoding="utf-8")
        with self.assertRaises(RuntimeError):
            carregar_preferencias(self.base)

    def test_release_available_does_not_unlock_installation(self):
        r=verificar_release_estavel(
            versao_atual="0.8.0",
            fetch=lambda: {"tag_name":"v0.9.0","draft":False,
                           "prerelease":False,"html_url":"https://github.com/example/release",
                           "published_at":"2026-10-18T00:00:00Z"},
        )
        self.assertEqual(r["estado"],"disponivel")
        self.assertFalse(r["download_disponivel"])
        self.assertEqual(r["versao_publicada"],"0.9.0")

    def test_stale_or_prerelease_is_not_offered_as_new(self):
        outdated=verificar_release_estavel(
            versao_atual="1.0.0",
            fetch=lambda: {"tag_name":"v0.9.0","draft":False,"prerelease":False},
        )
        self.assertEqual(outdated["estado"],"atual")
        new_pre=verificar_release_estavel(
            versao_atual="1.0.0",
            fetch=lambda: {"tag_name":"v2.0.0","draft":False,"prerelease":True},
        )
        self.assertEqual(new_pre["estado"],"invalido")

    def test_404_is_no_release_and_network_failure_is_not_up_to_date(self):
        def unavailable():
            raise HTTPError("https://example.org",404,"Not Found",{},None)
        empty=verificar_release_estavel(fetch=unavailable)
        self.assertEqual(empty["estado"],"sem_release")
        def offline():
            raise URLError("sem rede")
        disconnected=verificar_release_estavel(fetch=offline)
        self.assertEqual(disconnected["estado"],"offline")
        self.assertNotEqual(disconnected["estado"],"atual")
        self.assertFalse(disconnected["download_disponivel"])

    def test_invalid_release_tag_cannot_become_update(self):
        r=verificar_release_estavel(
            versao_atual="0.1.0",
            fetch=lambda: {"tag_name":"../../../evil.exe","draft":False,"prerelease":False},
        )
        self.assertEqual(r["estado"],"invalido")
        self.assertFalse(r["download_disponivel"])

if __name__=="__main__":
    unittest.main()
