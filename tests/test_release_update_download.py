"""Official release discovery and download: mocked, no network or real data."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from backend.app_lifecycle import (
    verificar_release_estavel, baixar_atualizacao_verificada,
)
VERSION="1.1.0"
NAME=f"DCA-Monitor-v{VERSION}-Windows-x64.zip"
URL=f"https://github.com/tiolusystems/dca-desktop-monitor/releases/download/v{VERSION}/{NAME}"
DATA=b"X"*4096
DIGEST=hashlib.sha256(DATA).hexdigest()

def fake_release(url=URL,digest=DIGEST):
    return {"tag_name":"v"+VERSION,"draft":False,"prerelease":False,
            "html_url":"https://github.com/tiolusystems/dca-desktop-monitor/releases/tag/v1.1.0",
            "assets":[{"name":NAME,"browser_download_url":url,
                       "size":len(DATA),"digest":"sha256:"+digest}]}

class ReleaseUpdateTests(unittest.TestCase):
    def test_only_official_release_asset_with_digest_can_enable_download(self):
        with patch("backend.app_lifecycle.platform.system",return_value="Windows"):
            available=verificar_release_estavel(fetch=lambda:fake_release())
            self.assertTrue(available["download_disponivel"])
            self.assertEqual(available["pacote"]["sha256"],DIGEST)
            malicious=verificar_release_estavel(fetch=lambda:fake_release(
                url="https://evil.example/file.zip"))
            self.assertFalse(malicious["download_disponivel"])
            unsigned=verificar_release_estavel(fetch=lambda:fake_release(digest="bad"))
            self.assertFalse(unsigned["download_disponivel"])

    def test_tampered_download_is_rejected_without_partial_target(self):
        with TemporaryDirectory() as tmp:
            with patch("backend.app_lifecycle.platform.system",return_value="Windows"):
                info=verificar_release_estavel(fetch=lambda:fake_release())
            class Response:
                def __enter__(self): return self
                def __exit__(self,*args): return False
                def geturl(self): return URL
                def read(self,n): return b"tampered" if not getattr(self,"seen",False) and setattr(self,"seen",True) is None else b""
            target=Path(tmp)/NAME
            with patch("backend.app_lifecycle.urlopen",return_value=Response()):
                with self.assertRaisesRegex(ValueError,"SHA-256"):
                    baixar_atualizacao_verificada(info,target)
            self.assertFalse(target.exists())

    def test_unsigned_release_and_downgrade_are_not_downloadable(self):
        with patch("backend.app_lifecycle.platform.system",return_value="Windows"):
            stale=verificar_release_estavel(versao_atual="2.0.0",fetch=lambda:fake_release())
            self.assertFalse(stale["download_disponivel"])
            draft=fake_release();draft["draft"]=True
            self.assertFalse(verificar_release_estavel(fetch=lambda:draft)["download_disponivel"])

if __name__ == "__main__":
    unittest.main()
