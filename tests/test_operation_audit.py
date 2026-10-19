from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from backend.backend import DataManager
class OperationAuditTests(unittest.TestCase):
    def test_f15_reason_before_after_and_atomic_rejection(self):
        with TemporaryDirectory() as temp:
            dm=DataManager(data_dir=Path(temp),auto_import_legacy=False)
            dm.salvar_operacao(['2026-01-01 12:00:00','USDT','compra','100','5','100','5'])
            row=dm.carregar_operacao_para_edicao(0)
            changed=dict(row,Quantidade='120',Valor_USDT='120')
            self.assertFalse(dm.atualizar_operacao(0,changed))
            self.assertTrue(dm.atualizar_operacao(0,changed,motivo='Conferência com comprovante'))
            records=dm._store.listar_auditoria_operacoes()
            self.assertEqual(records[-1]['antes']['Quantidade'],'100')
            self.assertEqual(records[-1]['depois']['Quantidade'],'120')
            self.assertTrue(dm.excluir_operacao(0,motivo='Cancelamento documentado'))
            self.assertIsNone(dm._store.listar_auditoria_operacoes()[-1]['depois'])
            with closing(sqlite3.connect(dm.arquivo_db)) as conn:
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute('DELETE FROM auditoria_operacoes')
