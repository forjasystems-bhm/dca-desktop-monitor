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
