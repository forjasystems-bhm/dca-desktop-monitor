"""Update transaction tests with real isolated SQLite and recovery ZIPs."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
import hashlib
import json
import sys
import unittest
import zipfile

from backend.backend import DataManager
from backend.update_install import (
    preparar_instalacao, executar_instalacao, extrair_windows, conferir_pasta,
    sha256,
)


def package(root, version='1.1.0', extra=None):
    files={'DCA-Monitor.exe': b'INERT SYNTHETIC EXE', '_internal/resource.txt': b'data'}
    if extra:
        files.update(extra)
    manifest=dict(format='DCA-DISTRIBUTION-1',version=version,commit='a'*40,
                  files={name:hashlib.sha256(body).hexdigest() for name,body in files.items()})
    archive=root/f'DCA-Monitor-v{version}-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w') as out:
        for name,body in files.items():out.writestr('DCA-Monitor/'+name,body)
        out.writestr('DCA-Monitor/distribution-manifest.json',json.dumps(manifest))
    return archive,dict(download_disponivel=True,versao_publicada=version,pacote=dict(
        nome=archive.name,url=f'https://github.com/tiolusystems/dca-desktop-monitor/releases/download/v{version}/{archive.name}',
        sha256=sha256(archive),tamanho=archive.stat().st_size))


class DesktopUpdateTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.dm=DataManager(data_dir=self.root/'wallet',auto_import_legacy=False)
        self.dm.salvar_operacao(['2026-01-01 12:00:00','USDT','compra','10','5','10','5'])
        self.db_before=self.dm.arquivo_db.read_bytes()
        self.base=self.root/'versions'
        self.archive,self.info=package(self.root)

    def prepare(self):
        return preparar_instalacao(self.info,self.archive,self.dm.arquivo_db,raiz=self.base,origem=Path(sys.executable).resolve())

    def test_stage_is_complete_and_does_not_change_wallet_or_old_executable(self):
        result=self.prepare();record=json.loads(Path(result['acao']).read_text())
        self.assertEqual(record['state'],'prepared')
        conferir_pasta(result['destino'],version='1.1.0',commit='a'*40)
        self.assertEqual(self.dm.arquivo_db.read_bytes(),self.db_before)
        self.assertFalse(list(self.dm.arquivo_db.parent.glob('updates/*-backup.zip')))

    def test_changed_bytes_fail_before_staging_or_backup(self):
        self.archive.write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.base.exists())
        self.assertEqual(self.dm.arquivo_db.read_bytes(),self.db_before)

    def test_wrong_origin_downgrade_or_linux_cannot_install(self):
        import copy
        for mode in ('origin','downgrade','linux'):
            with self.subTest(mode=mode):
                info=copy.deepcopy(self.info)
                if mode=='origin':info['pacote']['url']='https://evil.example/p.zip'
                if mode=='downgrade':info['versao_publicada']='0.9.0'
                if mode=='linux':info['pacote']['nome']='DCA-Monitor-v1.1.0-Linux-x64.tar.gz'
                with self.assertRaises(ValueError):
                    preparar_instalacao(info,self.archive,self.dm.arquivo_db,raiz=self.base,origem=Path(sys.executable).resolve())
        self.assertFalse(self.base.exists())

    def test_traversal_personal_data_reserved_names_and_duplicate_case_rejected(self):
        for name in ('../escape','portfolio.sqlite3','CON.txt','_internal/resource.txt:evil',
                     '_internal/RESOURCE.txt','trailing. '):
            with self.subTest(name=name):
                archive,info=package(self.root,extra={name:b'bad'})
                target=self.base/'candidate'
                with self.assertRaises(ValueError):
                    extrair_windows(archive,target,version='1.1.0',digest=info['pacote']['sha256'])
                self.assertFalse(target.exists())
        self.assertFalse((self.root/'escape').exists())

    def test_extra_file_after_staging_blocks_launch_without_backup(self):
        result=self.prepare();(Path(result['destino'])/'unexpected.exe').write_bytes(b'bad')
        with patch('backend.update_install.raiz_instalacoes',return_value=self.base), \
             patch('backend.update_install.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'inesperados'):
                executar_instalacao(result['acao'])
            spawn.assert_not_called()
        self.assertEqual(self.dm.arquivo_db.read_bytes(),self.db_before)
        self.assertEqual(json.loads(Path(result['acao']).read_text())['state'],'failed')

    def test_backup_failure_never_starts_candidate_or_changes_shortcut(self):
        result=self.prepare()
        with patch('backend.update_install.raiz_instalacoes',return_value=self.base), \
             patch('backend.recovery_bundle.exportar_pacote',side_effect=OSError('disco cheio')), \
             patch('backend.update_install.subprocess.Popen') as spawn, \
             patch('config.install.install_windows') as shortcut:
            with self.assertRaisesRegex(OSError,'disco cheio'):
                executar_instalacao(result['acao'])
            spawn.assert_not_called();shortcut.assert_not_called()
        self.assertEqual(self.dm.arquivo_db.read_bytes(),self.db_before)

    def test_waits_for_old_instance_instead_of_forcing_close(self):
        from backend.single_instance import TravaInstancia
        result=self.prepare()
        with TravaInstancia(self.dm.arquivo_db.parent), \
             patch('backend.update_install.raiz_instalacoes',return_value=self.base), \
             patch('backend.update_install.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'continua aberto'):
                executar_instalacao(result['acao'],timeout=0)
            spawn.assert_not_called()
        self.assertEqual(self.dm.arquivo_db.read_bytes(),self.db_before)

    def test_real_recoverable_backup_then_acknowledged_activation(self):
        result=self.prepare();action=Path(result['acao']);target=Path(result['destino'])
        child=Mock(pid=1234);child.poll.return_value=None
        def launch(args,**kwargs):
            record=json.loads(action.read_text())
            self.assertEqual(record['state'],'starting')
            self.assertEqual(kwargs['env']['DCA_MONITOR_DATA_DIR'],str(self.dm.arquivo_db.parent))
            self.assertTrue(Path(record['backup']['pacote']).is_file())
            action.with_suffix('.ready.json').write_text(json.dumps(dict(
                token=record['token'],version='1.1.0',executable=str(target/'DCA-Monitor.exe'),pid=1234)))
            return child
        with patch('backend.update_install.raiz_instalacoes',return_value=self.base), \
             patch('backend.update_install.subprocess.Popen',side_effect=launch), \
             patch('config.install.install_windows',return_value={'criado':True,'proprio':True}) as shortcut:
            record=executar_instalacao(action)
        self.assertEqual(record['state'],'installed');shortcut.assert_called_once()
        self.assertEqual(self.dm.arquivo_db.read_bytes(),self.db_before)
        with self.assertRaisesRegex(ValueError,'já utilizada'):executar_instalacao(action)

    def test_failed_candidate_does_not_reopen_old_code_or_restore_over_newer_data(self):
        result=self.prepare();child=Mock();child.poll.return_value=1
        with patch('backend.update_install.raiz_instalacoes',return_value=self.base), \
             patch('backend.update_install.subprocess.Popen',return_value=child) as spawn, \
             patch('config.install.install_windows') as shortcut:
            with self.assertRaisesRegex(RuntimeError,'não conseguiu abrir'):
                executar_instalacao(result['acao'])
            self.assertEqual(spawn.call_count,1);shortcut.assert_not_called()
        self.assertTrue(Path(result['destino']).exists())
        self.assertEqual(self.dm.arquivo_db.read_bytes(),self.db_before)
        record=json.loads(Path(result['acao']).read_text())
        self.assertEqual(record['state'],'failed');self.assertTrue(Path(record['backup']['pacote']).is_file())

    def test_junction_or_symlink_install_root_is_rejected(self):
        real=self.root/'real';real.mkdir();link=self.root/'link'
        try:link.symlink_to(real,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink creation unavailable')
        with self.assertRaisesRegex(ValueError,'vínculo'):
            preparar_instalacao(self.info,self.archive,self.dm.arquivo_db,raiz=link)


if __name__=='__main__':unittest.main()
