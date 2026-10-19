"""Testes cruzados: análise histórica lê decimais e posições do SQLite."""
import tempfile
from pathlib import Path
import unittest
from decimal import Decimal

from backend.backend import DataManager
from backend.finance_analytics import calcular_analise_por_periodo


HEADER = "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\\n"


class IntegracaoDataFinanceira(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.folder = Path(t.name)
        self.csv = self.folder / "original.csv"
        self.csv.write_text(
            "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
            "2025-12-01 10:00:00,USDT,compra,2000,5,2000,5\n"
            "2025-12-02 10:00:00,BTC,compra,1000,10000,0.1,5\n"
            "2026-01-04 10:00:00,BTC,venda,1300,13000,0.1,5\n"
            "2026-01-06 10:00:00,ETH,compra,0.3000000000000000001,1,0.3000000000000000001,5\n",
            encoding="utf-8",
        )
        self.dm = DataManager(legacy_csv=self.csv, data_dir=self.folder / "storage")

    def test_tela_periodos_consulta_sqlite_sem_precos_atuais(self):
        registros = self.dm.carregar_operacoes_precisas()
        self.assertEqual(registros[-1]["Quantidade"], "0.3000000000000000001")
        resultado = calcular_analise_por_periodo(registros, "2026-01-01", "2026-01-31")
        self.assertEqual(resultado["ativos"]["BTC"]["realizado_periodo"], Decimal("300"))
        self.assertEqual(resultado["ativos"]["BTC"]["quantidade"], Decimal("0"))
        self.assertEqual(resultado["ativos"]["ETH"]["quantidade"], Decimal("0.3000000000000000001"))
        self.assertEqual(resultado["totais"]["compras_periodo"], Decimal("0.3000000000000000001"))
        self.assertEqual(resultado["totais"]["realizado_periodo"], Decimal("300"))
        self.assertEqual(self.dm._store.diagnostico_integridade()["operacoes_importadas"], 4)

    def test_alteracoes_no_sqlite_atualizam_analise_historica_sem_csv(self):
        self.assertTrue(self.dm.salvar_operacao(
            ["2026-01-10 10:00:00", "SOL", "compra", "50", "50", "1", "5"]
        ))
        resultado = calcular_analise_por_periodo(self.dm.carregar_operacoes_precisas(), "2026-01-01", "2026-01-31")
        self.assertEqual(resultado["ativos"]["SOL"]["custo_aberto"], Decimal("50"))
        self.assertEqual(len(self.dm.carregar_operacoes_precisas()), 5)
        self.assertEqual(len(self.csv.read_text().splitlines()), 5)

if __name__ == "__main__":
    unittest.main()
