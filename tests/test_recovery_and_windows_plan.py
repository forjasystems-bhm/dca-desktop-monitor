"""Recovery and Windows plan: adversarial tests without distribution or data loss."""
from pathlib import Path
from contextlib import closing
import hashlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.backup_sqlite import (
    ErroBackupSQLite, criar_backup_sqlite, verificar_backup_sqlite,
)
from backend.restore_offline import (
    ativar_restauracao_offline, CONFIRMACAO,
)
from backend.windows_lifecycle import (
    ErroCicloWindows, comparar_versoes, planejar_instalacao_sem_executar,
)


class RecuperacaoOfflineTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.db=self.root/"portfolio.sqlite3"
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("CREATE TABLE saldos(valor TEXT)")
            con.execute("INSERT INTO saldos VALUES ('ANTES')")
            con.commit()
        self.original=criar_backup_sqlite(
            self.db,self.root/"evidencias",motivo="versao_previa",
        )
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("INSERT INTO saldos VALUES ('DEPOIS')")
            con.commit()

    def count(self,path=None):
        with closing(sqlite3.connect(path or self.db)) as con:
            return con.execute("SELECT COUNT(*) FROM saldos").fetchone()[0]

    def test_restore_is_explicit_and_application_must_be_closed(self):
        with self.assertRaises(ErroBackupSQLite):
            ativar_restauracao_offline(
                self.original["manifesto"],self.db,confirmacao="",applicativo_encerrado=True,
            )
        with self.assertRaises(ErroBackupSQLite):
            ativar_restauracao_offline(
                self.original["manifesto"],self.db,confirmacao=CONFIRMACAO,
                aplicativo_encerrado=False,
            )
        self.assertEqual(self.count(),2)

    def test_real_offline_restore_preserves_a_rollback_copy(self):
        r=ativar_restauracao_offline(
            self.original["manifesto"],self.db,confirmacao=CONFIRMACAO,
            aplicativo_encerrado=True,
        )
        self.assertTrue(r["ativado"])
        self.assertEqual(self.count(),1)
        previous=Path(r["rollback_original"])
        self.assertEqual(self.count(previous),2)
        self.assertTrue(Path(r["backup_previo"]).exists())
        self.assertEqual(verificar_backup_sqlite(self.db)["integridade_sqlite"],"ok")

    def test_wal_sidecar_blocks_unchecked_swap(self):
        side=Path(str(self.db)+"-wal")
        side.write_bytes(b"untouched")
        with self.assertRaisesRegex(ErroBackupSQLite,"WAL"):
            ativar_restauracao_offline(
                self.original["manifesto"],self.db,confirmacao=CONFIRMACAO,
                aplicativo_encerrado=True,
            )
        self.assertEqual(self.count(),2)
        self.assertEqual(side.read_bytes(),b"untouched")

    def test_simulated_failure_during_second_rename_rolls_back(self):
        import backend.restore_offline as module
        real=module.os.rename
        calls=[0]
        def flaky(src,dst):
            calls[0]+=1
            if calls[0] == 2:
                raise PermissionError("Injected Windows rename failure")
            return real(src,dst)
        with patch.object(module.os,"rename",side_effect=flaky):
            with self.assertRaises(ErroBackupSQLite):
                ativar_restauracao_offline(
                    self.original["manifesto"],self.db,confirmacao=CONFIRMACAO,
                    aplicativo_encerrado=True,
                )
        self.assertEqual(self.count(),2)
        self.assertEqual(verificar_backup_sqlite(self.db)["integridade_sqlite"],"ok")


class WindowsUpdatePlanTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.pacote=self.root/"payload-simulacao.dat"
        self.pacote.write_bytes(b"NAO_E_EXECUTAVEL")
        self.hash=hashlib.sha256(self.pacote.read_bytes()).hexdigest()

    def test_semver_comparison(self):
        self.assertTrue(comparar_versoes("1.2.3","1.3.0")["elegivel"])
        self.assertTrue(comparar_versoes("2.0.0","1.9.9")["downgrade_bloqueado"])
        with self.assertRaises(ErroCicloWindows):
            comparar_versoes("dev","1.0.0")

    def test_update_plan_preserves_data_and_does_not_install(self):
        program=self.root/"app"
        data=self.root/"data"
        d=planejar_instalacao_sem_executar(
            program,data,self.pacote,self.hash,
            versao_atual="0.2.0",versao_nova="0.3.0",
        )
        self.assertFalse(d["instalacao_executada"])
        self.assertFalse(d["publicacao_autorizada"])
        self.assertFalse(d["atualizacao_automatica_ativa"])
        self.assertEqual(Path(d["diretorio_dados_persistente"]),data)
        self.assertEqual(list(self.root.iterdir()),[self.pacote])
        with self.assertRaisesRegex(ErroCicloWindows,"superior"):
            planejar_instalacao_sem_executar(
                program,data,self.pacote,self.hash,
                versao_atual="0.3.0",versao_nova="0.2.0",
            )

if __name__ == "__main__":
    unittest.main()
