"""Review P2 F13/F14: issued historical version is present in last recovery."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from contextlib import closing
import sqlite3
import unittest

from backend.storage_sqlite import ArmazemSQLite
from backend.backup_policy import configurar_destino_independente
from backend.historical_valuation import patrimonio_historico_na_data
from backend.recovery_bundle import recuperar_pacote

class IssuedVersionProtectionReviewTests(unittest.TestCase):
    def test_version_is_in_new_independent_package_and_restores(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=root/"source"
            external=root/"offsite"
            db=ArmazemSQLite(data,None,auto_importar_legado=False)
            configurar_destino_independente(data,external)
            previous=len(list(external.glob("DCA-*.zip")))
            result=patrimonio_historico_na_data(db,date(2025,1,1))
            bundles=sorted(external.glob("DCA-*.zip"))
            self.assertEqual(len(bundles),previous+1)
            self.assertIsNone(db.ultimo_aviso_backup)
            recovered=root/"recovered"
            recuperar_pacote(bundles[-1],recovered)
            with closing(sqlite3.connect(recovered/"portfolio.sqlite3")) as c:
                count=c.execute("SELECT count(*) FROM versoes_resultados").fetchone()[0]
                restored=c.execute("SELECT identidade FROM versoes_resultados").fetchone()[0]
            self.assertEqual(count,1)
            self.assertEqual(restored,result["versao_resultado"])

            # Idempotent emission: same proof must not generate an extra bundle.
            same=patrimonio_historico_na_data(db,date(2025,1,1))
            self.assertEqual(same["versao_resultado"],restored)
            self.assertEqual(len(list(external.glob("DCA-*.zip"))),len(bundles))

    def test_after_commit_failed_backup_is_surfaced_not_called_rollback(self):
        with TemporaryDirectory() as tmp:
            db=ArmazemSQLite(Path(tmp),None,auto_importar_legado=False)
            with patch("backend.backup_policy.proteger_gravacao",side_effect=OSError("disco cheio")):
                result=patrimonio_historico_na_data(db,date(2025,1,1))
            self.assertEqual(db.listar_versoes_resultados()[0]["identidade"],
                             result["versao_resultado"])
            self.assertIn("disco cheio",db.ultimo_aviso_backup)

if __name__=="__main__":
    unittest.main()
