from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
import unittest
from backend.storage_sqlite import ArmazemSQLite
from backend.historical_valuation import patrimonio_historico_na_data
class VersionTests(unittest.TestCase):
    def test_issued_result_survives_later_correction_and_identical_replay(self):
        with TemporaryDirectory() as folder:
            db=ArmazemSQLite(Path(folder),None)
            first=patrimonio_historico_na_data(db,date(2025,1,1))
            again=patrimonio_historico_na_data(db,date(2025,1,1))
            self.assertEqual(first['versao_resultado'],again['versao_resultado'])
            db.inserir(['2025-01-01 12:00:00','USDT','compra','10','5','10','5'])
            second=patrimonio_historico_na_data(db,date(2025,1,1))
            self.assertNotEqual(first['versao_resultado'],second['versao_resultado'])
            versions=db.listar_versoes_resultados()
            self.assertEqual(len(versions),2)
            self.assertEqual(versions[0]['resultado']['patrimonio_total'],'0')
            self.assertEqual(versions[1]['resultado']['patrimonio_total'],'10')
