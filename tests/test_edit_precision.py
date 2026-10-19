from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend.backend import DataManager
class EditPrecisionTests(unittest.TestCase):
    def test_f17_edit_source_keeps_all_decimal_places(self):
        with TemporaryDirectory() as temp:
            dm=DataManager(data_dir=Path(temp),auto_import_legacy=False)
            row=['2026-01-01 12:00:00','USDT','compra','100.123456789123456789','5.2345678912345','100.123456789123456789','5.2345678912345']
            self.assertTrue(dm.salvar_operacao(row))
            precise=dm.carregar_operacao_para_edicao(0)
            self.assertEqual(precise['Quantidade'],row[5]);self.assertEqual(precise['Taxa_BRL'],row[6])
            self.assertTrue(dm.atualizar_operacao(0,precise, motivo="Justificativa sintética do teste"))
            self.assertEqual(dm.carregar_operacao_para_edicao(0),precise)
