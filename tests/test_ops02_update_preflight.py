"""OPS-02 antes de release: nenhum instalador e nenhuma atualização aplicada."""
from pathlib import Path
import hashlib
import sqlite3
from contextlib import closing
import tempfile
import unittest

from backend.windows_lifecycle import (
    ErroCicloWindows, verificar_separacao_dados, conferir_pacote_local,
    planejar_atualizacao_sem_executar,
)
from backend.backup_sqlite import (
    criar_backup_sqlite, preparar_restauracao_sqlite, ErroBackupSQLite,
)


class PreparacaoWindowsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.app = self.root / "programa"
        self.app.mkdir()
        self.data = self.root / "dados"
        self.data.mkdir()
        self.db = self.data / "portfolio.sqlite3"
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("CREATE TABLE operacoes (id INTEGER PRIMARY KEY, valor TEXT)")
            con.execute("INSERT INTO operacoes(valor) VALUES ('x')")
            con.commit()
        self.package = self.root / "proximo-pacote-qa.bin"
        self.package.write_bytes(b"fixture-em-testes-nao-executavel")
        self.sha = hashlib.sha256(self.package.read_bytes()).hexdigest()

    def test_dados_devem_ficar_fora_da_pasta_do_programa(self):
        verificar_separacao_dados(self.app, self.db)
        with self.assertRaises(ErroCicloWindows):
            verificar_separacao_dados(self.app, self.app / "dados" / "portfolio.sqlite3")

    def test_pacote_qa_exige_hash_completo_sem_validar_falsa_assinatura(self):
        info = conferir_pacote_local(self.package, self.sha)
        self.assertFalse(info["instalacao_autorizada"])
        self.assertFalse(info["assinatura_verificada"])
        with self.assertRaisesRegex(ErroCicloWindows, "hash"):
            conferir_pacote_local(self.package, "a" * 64)
        with self.assertRaisesRegex(ErroCicloWindows, "inexistente"):
            conferir_pacote_local(self.root / "ausente.bin", self.sha)

    def test_pre_update_backup_while_never_installing_or_overwriting(self):
        before = self.db.read_bytes()
        plan = planejar_atualizacao_sem_executar(
            self.app, self.db, self.package, self.sha
        )
        self.assertFalse(plan["aplicada"])
        self.assertTrue(Path(plan["backup_sqlite"]).exists())
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.package.read_bytes(), b"fixture-em-testes-nao-executavel")
        self.assertEqual(list(self.app.iterdir()), [])

    def test_restore_tampered_manifest_refuses_any_file(self):
        snap = criar_backup_sqlite(self.db, self.data / "snapshots")
        manifest = Path(snap["manifesto"])
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text.replace(snap["sha256"], "0" * 64), encoding="utf-8")
        output = self.data / "separado.sqlite3"
        with self.assertRaises(ErroBackupSQLite):
            preparar_restauracao_sqlite(manifest, output)
        self.assertFalse(output.exists())
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0], 1
            )


if __name__ == "__main__":
    unittest.main()
