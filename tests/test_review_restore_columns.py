"""Review P1 F10/F12: every operational schema column is required on restore."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from backend.backend import DataManager
from backend.backup_sqlite import criar_backup_sqlite
from backend.database_identity import validar_banco_dca
from backend.restore_offline import ativar_restauracao_offline, CONFIRMACAO


class RestoreMissingColumnReviewTests(unittest.TestCase):
    def test_missing_operational_column_rejected_before_activation(self):
        for table, column in (
            ("posicoes_externas","observacao"),
            ("movimentacoes_custodia","criado_em_utc"),
            ("cotacoes_historicas","capturado_em_utc"),
        ):
            with self.subTest(table=table,column=column),TemporaryDirectory() as tmp:
                root=Path(tmp)
                dm=DataManager(data_dir=root/"active",auto_import_legacy=False)
                dm.registrar_posicao_externa(
                    moeda="BTC",quantidade="1",custodia="A",
                    data_posicao="2026-01-01",custo_total_usdt="100",
                    confirmacao_independente=True,
                )
                backup_db=root/"damaged.sqlite3"
                with closing(sqlite3.connect(dm.arquivo_db.resolve().as_uri()+"?mode=ro",uri=True)) as source:
                    with closing(sqlite3.connect(backup_db)) as dest:
                        source.backup(dest)
                with closing(sqlite3.connect(backup_db)) as c:
                    c.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
                    c.commit()
                # Valid manifest/hash and SQLite integrity must NOT be sufficient.
                manifest=criar_backup_sqlite(backup_db,root/"snapshots")["manifesto"]
                original=dm.arquivo_db.read_bytes()
                with self.assertRaisesRegex(RuntimeError,"Estrutura|estrutura"):
                    validar_banco_dca(backup_db)
                with self.assertRaisesRegex(RuntimeError,"Estrutura|estrutura"):
                    ativar_restauracao_offline(Path(manifest),dm.arquivo_db,
                        confirmacao=CONFIRMACAO,aplicativo_encerrado=True)
                self.assertEqual(dm.arquivo_db.read_bytes(),original)
                self.assertEqual(dm.carregar_posicoes_externas()[0]["Quantidade"],"1")

    def test_current_database_required_set_matches_actual_operational_schema(self):
        from backend.database_identity import REQUIRED
        with TemporaryDirectory() as tmp:
            dm=DataManager(data_dir=Path(tmp),auto_import_legacy=False)
            with closing(sqlite3.connect(dm.arquivo_db)) as c:
                for table, cols in REQUIRED.items():
                    with self.subTest(table=table):
                        actual={r[1] for r in c.execute("PRAGMA table_info("+table+")")}
                        self.assertTrue(cols<=actual)
            self.assertEqual(validar_banco_dca(dm.arquivo_db)["schema"],10)

if __name__=="__main__":
    unittest.main()
