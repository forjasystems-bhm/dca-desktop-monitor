from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from backend.backend import DataManager

class SchemaSafetyTests(unittest.TestCase):
    def test_f12_future_version_is_refused_without_any_change(self):
        with TemporaryDirectory() as root:
            dm=DataManager(data_dir=Path(root),auto_import_legacy=False)
            with closing(sqlite3.connect(dm.arquivo_db)) as c:
                c.execute('PRAGMA user_version=99');c.commit()
            before=dm.arquivo_db.read_bytes()
            with self.assertRaisesRegex(RuntimeError,'versão|versao|futur'):
                DataManager(data_dir=Path(root),auto_import_legacy=False)
            self.assertEqual(dm.arquivo_db.read_bytes(),before)

class MissingDatabaseTests(unittest.TestCase):
    def test_f08_missing_used_database_does_not_create_empty_replacement(self):
        with TemporaryDirectory() as root:
            dm=DataManager(data_dir=Path(root),auto_import_legacy=False)
            dm.registrar_posicao_externa(moeda='BTC',quantidade='1',custodia='A',
                data_posicao='2026-01-01',confirmacao_independente=True)
            dm.arquivo_db.unlink()
            with self.assertRaisesRegex(RuntimeError,'ausente|recuper'):
                DataManager(data_dir=Path(root),auto_import_legacy=False)
            self.assertFalse(dm.arquivo_db.exists())

class BackupIdentityTests(unittest.TestCase):
    def test_f10_foreign_sqlite_is_not_a_dca_backup(self):
        from backend.backup_sqlite import criar_backup_sqlite
        from backend.restore_offline import ativar_restauracao_offline,CONFIRMACAO
        with TemporaryDirectory() as temp:
            root=Path(temp); dm=DataManager(data_dir=root/'data',auto_import_legacy=False)
            other=root/'foreign.sqlite3'
            with closing(sqlite3.connect(other)) as c:c.execute('CREATE TABLE foreign_data(value TEXT)')
            manifest=criar_backup_sqlite(other,root/'backup')['manifesto']
            before=dm.arquivo_db.read_bytes()
            with self.assertRaisesRegex(RuntimeError,'DCA|carteira|estrutura'):
                ativar_restauracao_offline(Path(manifest),dm.arquivo_db,
                    confirmacao=CONFIRMACAO,aplicativo_encerrado=True)
            self.assertEqual(dm.arquivo_db.read_bytes(),before)

    def test_f10_different_wallet_backup_is_refused(self):
        from backend.backup_sqlite import criar_backup_sqlite
        from backend.restore_offline import ativar_restauracao_offline,CONFIRMACAO
        with TemporaryDirectory() as temp:
            root=Path(temp)
            one=DataManager(data_dir=root/'one',auto_import_legacy=False)
            two=DataManager(data_dir=root/'two',auto_import_legacy=False)
            manifest=criar_backup_sqlite(two.arquivo_db,root/'backup')['manifesto']
            with self.assertRaisesRegex(RuntimeError,'outra carteira'):
                ativar_restauracao_offline(Path(manifest),one.arquivo_db,
                    confirmacao=CONFIRMACAO,aplicativo_encerrado=True)

class DisasterRecoveryTests(unittest.TestCase):
    def test_f09_lost_or_corrupt_database_can_be_recovered_offline(self):
        from backend.backup_sqlite import criar_backup_sqlite
        from backend.restore_offline import ativar_restauracao_offline,CONFIRMACAO
        for state in ('missing','corrupt'):
            with self.subTest(state=state),TemporaryDirectory() as temp:
                root=Path(temp);dm=DataManager(data_dir=root/'data',auto_import_legacy=False)
                dm.registrar_posicao_externa(moeda='BTC',quantidade='1',custodia='A',
                    data_posicao='2026-01-01',confirmacao_independente=True)
                manifest=criar_backup_sqlite(dm.arquivo_db,root/'backup')['manifesto']
                with closing(sqlite3.connect(dm.arquivo_db)) as c:c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                if state=='missing':dm.arquivo_db.unlink()
                else:dm.arquivo_db.write_bytes(b'CORRUPT ORIGINAL EVIDENCE')
                result=ativar_restauracao_offline(Path(manifest),dm.arquivo_db,
                    confirmacao=CONFIRMACAO,aplicativo_encerrado=True)
                self.assertTrue(result['ativado'])
                if state=='corrupt':
                    self.assertEqual(Path(result['rollback_original']).read_bytes(),b'CORRUPT ORIGINAL EVIDENCE')
                reopened=DataManager(data_dir=root/'data',auto_import_legacy=False)
                self.assertEqual(reopened.carregar_posicoes_externas()[0]['Quantidade'],'1')

class PortableRecoveryTests(unittest.TestCase):
    def test_f11_bundle_survives_loss_of_original_paths_and_config(self):
        from backend.recovery_bundle import exportar_pacote, recuperar_pacote
        with TemporaryDirectory() as temp:
            root=Path(temp);source=root/'old';csv=root/'original.csv'
            csv.write_bytes(b'Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n2026-01-01 12:00:00,USDT,compra,100,5,100,5\n')
            dm=DataManager(data_dir=source,auto_import_legacy=False)
            preview=dm.prever_csv(str(csv));dm.confirmar_csv(str(csv),preview['sha256'])
            (source/'app-settings.json').write_text('{"minimizar_para_bandeja":false}')
            bundle=root/'recovery.zip';exportar_pacote(dm.arquivo_db,bundle)
            import shutil
            shutil.rmtree(source);csv.unlink()
            target=root/'recovered';recuperar_pacote(bundle,target)
            recovered=DataManager(data_dir=target,auto_import_legacy=False)
            self.assertEqual(recovered.carregar_operacoes_precisas()[0]['Quantidade'],'100')
            self.assertTrue((target/'app-settings.json').exists())
            self.assertEqual(recovered._store.diagnostico_integridade()['status'],'OK')
            with self.assertRaises(RuntimeError):recuperar_pacote(bundle,target)

    def test_f11_archive_path_traversal_is_refused_before_creating_target(self):
        from backend.recovery_bundle import recuperar_pacote
        import zipfile
        with TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'bad.zip';target=root/'target'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','bad')
            with self.assertRaises(RuntimeError):recuperar_pacote(archive,target)
            self.assertFalse(target.exists());self.assertFalse((root/'escape').exists())

class BackupPolicyTests(unittest.TestCase):
    def test_f13_ordinary_commit_has_verified_post_write_backup(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);dm=DataManager(data_dir=root,auto_import_legacy=False)
            dm.salvar_operacao(['2026-01-01 12:00:00','USDT','compra','100','5','100','5'])
            manifests=list((root/'backups'/'sqlite').glob('*.json'))
            self.assertTrue(manifests)
            import json
            manifest=json.loads(manifests[-1].read_text())
            with closing(sqlite3.connect(manifests[-1].parent/manifest['arquivo'])) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM operacoes').fetchone()[0],1)
