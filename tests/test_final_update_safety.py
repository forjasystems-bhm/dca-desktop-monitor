"""Offline update acceptance; no release is published and no user install touched."""
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from backend.app_lifecycle import (verificar_release_estavel,baixar_atualizacao_verificada,
                                   preparar_atualizacao_manual)
from backend.backend import DataManager

BODY=b'SYNTHETIC DOWNLOAD CONTENT '*200
VERSION='1.1.0'


def release(system='Windows'):
    name='DCA-Monitor-v1.1.0-'+system+'-x64'+('.zip' if system=='Windows' else '.tar.gz')
    url='https://github.com/tiolusystems/dca-desktop-monitor/releases/download/v1.1.0/'+name
    raw=dict(tag_name='v1.1.0',draft=False,prerelease=False,assets=[dict(name=name,
        browser_download_url=url,size=len(BODY),digest='sha256:'+hashlib.sha256(BODY).hexdigest())])
    with patch('backend.app_lifecycle.platform.system',return_value=system), patch(
            'backend.app_lifecycle.platform.machine',return_value='x86_64'):
        return verificar_release_estavel(fetch=lambda:raw)


class Response(io.BytesIO):
    def geturl(self):
        return 'https://release-assets.githubusercontent.com/synthetic'


class FinalUpdateSafetyTests(unittest.TestCase):
    def test_successful_download_publishes_only_fully_verified_file(self):
        with TemporaryDirectory() as temp:
            info=release();target=Path(temp)/info['pacote']['nome']
            with patch('backend.app_lifecycle.urlopen',return_value=Response(BODY)):
                result=baixar_atualizacao_verificada(info,target)
            self.assertEqual(target.read_bytes(),BODY)
            self.assertFalse(result['instalado'])
            self.assertEqual(list(Path(temp).iterdir()),[target])

    def test_interrupted_download_removes_partial_file_without_touching_other_files(self):
        class Interrupted(Response):
            def read(self,n=-1):
                if self.tell(): raise OSError('synthetic connection lost')
                return super().read(100)
        with TemporaryDirectory() as temp:
            info=release();target=Path(temp)/info['pacote']['nome']
            unrelated=Path(temp)/'keep.txt';unrelated.write_bytes(b'preserve')
            with patch('backend.app_lifecycle.urlopen',return_value=Interrupted(BODY)):
                with self.assertRaisesRegex(OSError,'connection lost'):
                    baixar_atualizacao_verificada(info,target)
            self.assertEqual(list(Path(temp).iterdir()),[unrelated])
            self.assertEqual(unrelated.read_bytes(),b'preserve')

    def test_untrusted_redirect_is_refused_before_writing_final(self):
        class OtherHost(Response):
            def geturl(self):return 'https://example.invalid/archive'
        with TemporaryDirectory() as temp:
            info=release();target=Path(temp)/info['pacote']['nome']
            with patch('backend.app_lifecycle.urlopen',return_value=OtherHost(BODY)):
                with self.assertRaisesRegex(ValueError,'não confiável'):
                    baixar_atualizacao_verificada(info,target)
            self.assertFalse(target.exists())

    def test_existing_download_is_never_overwritten(self):
        with TemporaryDirectory() as temp:
            info=release();target=Path(temp)/info['pacote']['nome'];target.write_bytes(b'old file')
            with self.assertRaises(ValueError):baixar_atualizacao_verificada(info,target)
            self.assertEqual(target.read_bytes(),b'old file')

    def test_linux_package_and_unsupported_architecture(self):
        self.assertTrue(release('Linux')['pacote']['nome'].endswith('Linux-x64.tar.gz'))
        with patch('backend.app_lifecycle.platform.machine',return_value='aarch64'):
            # Don't nest release(), which intentionally sets the x64 fixture.
            self.assertFalse(verificar_release_estavel(fetch=lambda:dict(
                tag_name='v1.1.0',assets=[]))['download_disponivel'])

    def test_direct_download_cannot_bypass_version_guard(self):
        info=release();info['versao_publicada']='0.9.0'
        p=info['pacote'];p['nome']='DCA-Monitor-v0.9.0-Windows-x64.zip'
        p['url']='https://github.com/tiolusystems/dca-desktop-monitor/releases/download/v0.9.0/'+p['nome']
        with TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError,'superior'):
            baixar_atualizacao_verificada(info,Path(temp)/p['nome'])

    def test_manual_preparation_proves_portable_recovery_without_installing(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);dm=DataManager(data_dir=root/'wallet',auto_import_legacy=False)
            self.assertTrue(dm.salvar_operacao(['2026-01-01 12:00:00','USDT','compra','10','5','10','5']))
            original=dm.arquivo_db.read_bytes()
            info=release();download=root/info['pacote']['nome'];download.write_bytes(BODY)
            result=preparar_atualizacao_manual(info,download,dm.arquivo_db,root/'independent.zip')
            self.assertFalse(result['instalado'])
            self.assertTrue((root/'independent.zip').exists())
            self.assertEqual(dm.arquivo_db.read_bytes(),original)
            self.assertEqual(len(dm.carregar_operacoes_precisas()),1)

    def test_failed_preparation_leaves_sqlite_and_download_untouched(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);dm=DataManager(data_dir=root/'wallet',auto_import_legacy=False)
            original=dm.arquivo_db.read_bytes()
            info=release();download=root/info['pacote']['nome'];download.write_bytes(BODY)
            with patch('backend.recovery_bundle.exportar_pacote',side_effect=OSError('disco cheio')):
                with self.assertRaises(OSError):
                    preparar_atualizacao_manual(info,download,dm.arquivo_db,root/'backup.zip')
            self.assertEqual(dm.arquivo_db.read_bytes(),original)
            self.assertEqual(download.read_bytes(),BODY)

    def test_changed_download_is_refused_before_backup(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);info=release();download=root/info['pacote']['nome']
            download.write_bytes(b'X'*len(BODY))
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                preparar_atualizacao_manual(info,download,root/'absent.sqlite3',root/'backup.zip')
            self.assertFalse((root/'absent.sqlite3').exists())


if __name__=='__main__':unittest.main()
