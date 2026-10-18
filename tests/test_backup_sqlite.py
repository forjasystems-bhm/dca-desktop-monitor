"""Testes do backup SQLite, incluindo transações confirmadas em WAL."""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.backup_sqlite import (
    ErroBackupSQLite, criar_backup_sqlite, verificar_backup_sqlite,
)


class BackupSqliteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.banco = self.base / "portfolio.sqlite3"
        self.destino = self.base / "backups"
        with closing(sqlite3.connect(self.banco)) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE operacoes(id INTEGER PRIMARY KEY, valor TEXT)")
            con.execute("INSERT INTO operacoes(valor) VALUES ('100.123456789')")
            con.commit()

    def test_snapshot_preserva_transacoes_e_gera_manifesto_verificavel(self):
        origem_antes = self.banco.read_bytes()
        resultado = criar_backup_sqlite(self.banco, self.destino, motivo="antes_atualizacao")
        copia = Path(resultado["backup"])
        dados = json.loads(Path(resultado["manifesto"]).read_text(encoding="utf-8"))
        self.assertEqual(dados["motivo"], "antes_atualizacao")
        self.assertEqual(dados["sha256"], hashlib.sha256(copia.read_bytes()).hexdigest())
        self.assertEqual(verificar_backup_sqlite(copia, dados["sha256"])["integridade_sqlite"], "ok")
        with closing(sqlite3.connect(copia)) as con:
            self.assertEqual(con.execute("SELECT valor FROM operacoes").fetchone()[0], "100.123456789")
        self.assertEqual(self.banco.read_bytes(), origem_antes)

    def test_backup_inclui_registros_confirmados_em_wal(self):
        with closing(sqlite3.connect(self.banco)) as con:
            con.execute("PRAGMA wal_autocheckpoint=0")
            con.execute("INSERT INTO operacoes(valor) VALUES ('200')")
            con.commit()
            self.assertTrue(Path(str(self.banco) + "-wal").exists())
            copia = Path(criar_backup_sqlite(self.banco, self.destino)["backup"])
            with closing(sqlite3.connect(copia)) as backup_con:
                self.assertEqual(backup_con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0], 2)

    def test_repeticao_nao_substitui_backups_anteriores(self):
        primeiro = criar_backup_sqlite(self.banco, self.destino)
        segundo = criar_backup_sqlite(self.banco, self.destino)
        self.assertNotEqual(primeiro["backup"], segundo["backup"])
        self.assertTrue(Path(primeiro["backup"]).is_file())
        self.assertTrue(Path(segundo["backup"]).is_file())

    def test_adulteracao_do_snapshot_e_detectada_pelo_hash(self):
        resultado = criar_backup_sqlite(self.banco, self.destino)
        backup = Path(resultado["backup"])
        with backup.open("ab") as f:
            f.write(b"LIXO")
        with self.assertRaisesRegex(ErroBackupSQLite, "SHA-256"):
            verificar_backup_sqlite(backup, resultado["sha256"])

    def test_banco_inexistente_ou_corrompido_bloqueia_backup(self):
        with self.assertRaisesRegex(ErroBackupSQLite, "inexistente"):
            criar_backup_sqlite(self.base / "nao-existe.sqlite3", self.destino)
        with closing(sqlite3.connect(self.banco)) as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.banco.write_bytes(b"CORROMPIDO")
        with self.assertRaises(ErroBackupSQLite):
            criar_backup_sqlite(self.banco, self.destino)
        self.assertFalse(list(self.destino.glob("*.sqlite3")) if self.destino.exists() else [])


if __name__ == "__main__":
    unittest.main()
