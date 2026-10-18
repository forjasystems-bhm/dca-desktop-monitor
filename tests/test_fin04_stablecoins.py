"""FIN-04: stablecoins are separate ledgers and USDC is NEVER implicitly 1:1."""
import tempfile
import unittest
from pathlib import Path
from datetime import date
from decimal import Decimal

from backend.backend import DataManager, AnalysisEngine
from backend.finance_analytics import calcular_analise_por_periodo
from backend.historical_prices import buscar_e_persistir_fechamentos
from backend.historical_valuation import patrimonio_historico_na_data
from backend.stablecoin_ledger import saldos_stablecoins


HEADER = "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
D1 = "2026-09-01 10:00:00"
D2 = "2026-09-02 10:00:00"
D3 = "2026-09-03 10:00:00"


def op(dia, moeda, tipo, valor, preco, qtd, taxa="5"):
    return [dia, moeda, tipo, str(valor), str(preco), str(qtd), str(taxa)]


class BinanceFake:
    def __init__(self, close):
        self.close = close
        self.calls = []

    def fetch_ohlcv(self, par, timeframe, since, limit):
        self.calls.append((par, timeframe, since, limit))
        return [[since, 1, 1, 1, self.close, 100]]


class StablecoinsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dm = DataManager(
            legacy_csv=self.root / "nao-existe.csv",
            data_dir=self.root / "dados",
        )

    def depositar(self, moeda, qtd, dia=D1):
        return self.dm.salvar_operacao(op(dia, moeda, "compra", qtd, "5.13", qtd))

    def sacar(self, moeda, qtd, dia=D2):
        return self.dm.salvar_operacao(op(dia, moeda, "venda", qtd, "5.08", qtd))

    def test_usdc_deposito_nao_cria_usdt_nem_lucro_realizado(self):
        self.assertTrue(self.depositar("USDC", "250.12345678"))
        operacoes = self.dm.carregar_operacoes_precisas()
        self.assertEqual(
            saldos_stablecoins(operacoes)["saldos"]["USDC"], Decimal("250.12345678")
        )
        self.assertEqual(AnalysisEngine.calcular_saldo_usdt(operacoes)["saldo_atual"], 0)
        p = AnalysisEngine.calcular_portfolio(operacoes, {})
        self.assertEqual(p["totais"]["caixa_usdt"], 0)
        self.assertAlmostEqual(p["totais"]["caixa_usdc"], 250.12345678)
        self.assertEqual(p["totais"]["realizado"], 0)
        self.assertEqual(p["totais"]["cotacoes_pendentes"], ["USDC"])
        self.assertIsNone(p["totais"]["valor_atual"])
        self.assertIsNone(p["USDC (Caixa)"]["lucro_total"])

    def test_saque_usdc_reduz_so_usdc_nao_usdt(self):
        self.assertTrue(self.depositar("USDC", "200"))
        self.assertTrue(self.depositar("USDT", "1000"))
        self.assertTrue(self.sacar("USDC", "75"))
        saldos = saldos_stablecoins(self.dm.carregar_operacoes_precisas())
        self.assertEqual(saldos["saldos"]["USDC"], Decimal("125"))
        self.assertEqual(saldos["saldos"]["USDT"], Decimal("1000"))
        self.assertEqual(saldos["entradas"]["USDC"], Decimal("200"))
        self.assertEqual(saldos["saidas"]["USDC"], Decimal("75"))
        self.assertEqual(AnalysisEngine.calcular_saldo_usdt(
            self.dm.carregar_operacoes())["saldo_atual"], 1000)

    def test_usdc_nao_financia_compra_btc(self):
        self.assertTrue(self.depositar("USDC", "1000"))
        self.assertFalse(self.dm.salvar_operacao(op(D2, "BTC", "compra", 500, 50000, "0.01")))
        self.assertIn("saldo USDT negativo", self.dm.ultimo_erro)
        self.assertEqual(len(self.dm.carregar_operacoes()), 1)

    def test_saque_usdc_acima_saldo_e_rollback(self):
        self.assertTrue(self.depositar("USDC", "10"))
        anterior = self.dm.carregar_operacoes_precisas()
        self.assertFalse(self.sacar("USDC", "11"))
        self.assertIn("saldo USDC negativo", self.dm.ultimo_erro)
        self.assertEqual(anterior, self.dm.carregar_operacoes_precisas())

    def test_excluir_entrada_usdc_que_sustenta_saque_e_bloqueado(self):
        self.assertTrue(self.depositar("USDC", "100"))
        self.assertTrue(self.sacar("USDC", "80"))
        self.assertFalse(self.dm.excluir_operacao(0))
        self.assertIn("USDC", self.dm.ultimo_erro)
        self.assertEqual(len(self.dm.carregar_operacoes()), 2)

    def test_valor_nominal_usdc_nao_e_cotacao_de_mercado(self):
        self.assertFalse(self.dm.salvar_operacao(
            op(D1, "USDC", "compra", "100", "5", "99")
        ))
        self.assertIn("Quantidade igual ao Valor_USDT", self.dm.ultimo_erro)
        self.assertTrue(self.depositar("USDC", "100"))
        p = AnalysisEngine.calcular_portfolio(self.dm.carregar_operacoes(), {"USDC": 0.97})
        self.assertAlmostEqual(p["totais"]["valor_atual"], 97)
        self.assertIsNone(p["totais"]["nao_realizado"])
        self.assertIsNone(p["USDC (Caixa)"]["custo_posicao_final"])
        d = AnalysisEngine.calcular_distribuicao_portfolio(
            self.dm.carregar_operacoes(), {"USDC": 0.97}
        )
        self.assertAlmostEqual(d["distribuicao"]["USDC"]["percentual"], 100)

    def test_preco_usdc_atual_ausente_nao_usa_1_para_consolidar(self):
        self.assertTrue(self.depositar("USDT", "500"))
        self.assertTrue(self.depositar("USDC", "200"))
        self.assertEqual(
            AnalysisEngine.calcular_portfolio(
                self.dm.carregar_operacoes(), {}
            )["totais"]["cotacoes_pendentes"], ["USDC"]
        )
        p = AnalysisEngine.calcular_portfolio(
            self.dm.carregar_operacoes(), {"USDC": 0.98}
        )
        self.assertAlmostEqual(p["totais"]["valor_atual"], 696)
        self.assertEqual(p["totais"]["realizado"], 0)
        self.assertIsNone(p["totais"]["nao_realizado"])

    def test_analise_por_periodo_nao_confunde_aporte_usdc_e_compra_cripto(self):
        self.assertTrue(self.depositar("USDT", "1000"))
        self.assertTrue(self.depositar("USDC", "200"))
        self.assertTrue(self.sacar("USDC", "50"))
        self.assertTrue(self.dm.salvar_operacao(
            op(D2, "BTC", "compra", "250", "25000", "0.01")
        ))
        x = calcular_analise_por_periodo(self.dm.carregar_operacoes_precisas())
        self.assertEqual(x["totais"]["compras_historicas"], Decimal("250"))
        self.assertNotIn("USDC", x["ativos"])
        self.assertEqual(x["aportes_periodo_usdt"], Decimal("1000"))
        self.assertEqual(x["entradas_periodo_usdc"], Decimal("200"))
        self.assertEqual(x["saidas_periodo_usdc"], Decimal("50"))
        self.assertEqual(x["saldo_usdc"], Decimal("150"))
        self.assertEqual(x["totais"]["realizado_historico"], Decimal("0"))

    def test_historico_real_exige_fechamento_usdc_da_data_em_sqlite(self):
        self.assertTrue(self.depositar("USDT", "500"))
        self.assertTrue(self.depositar("USDC", "200"))
        dia = date(2026, 9, 30)
        falta = patrimonio_historico_na_data(self.dm._store, dia, hoje_utc=date(2026, 10, 18))
        self.assertFalse(falta["completo"])
        self.assertIn("USDC", falta["faltam_cotacoes"])
        self.assertIsNone(falta["patrimonio_total"])
        fake = BinanceFake("0.965")
        self.assertEqual(buscar_e_persistir_fechamentos(
            self.dm._store, fake, dia, ["USDC"], hoje_utc=date(2026, 10, 18)
        ), 1)
        self.assertEqual(fake.calls[0][0], "USDC/USDT")
        historico = patrimonio_historico_na_data(
            self.dm._store, dia, hoje_utc=date(2026, 10, 18)
        )
        self.assertTrue(historico["completo"])
        self.assertEqual(historico["patrimonio_total"], Decimal("693.000"))
        self.assertEqual(historico["ativos"]["USDC"]["valor_mercado"], Decimal("193.000"))
        self.assertIsNone(historico["resultado_total"])
        self.assertTrue(historico["base_de_custo_incompleta"])

    def test_registro_historico_nao_usa_preco_atual_igual_1(self):
        self.assertTrue(self.depositar("USDC", "50"))
        dia = date(2026, 9, 30)
        r = patrimonio_historico_na_data(self.dm._store, dia, hoje_utc=date(2026, 10, 18))
        self.assertIsNone(r["patrimonio_total"])
        self.assertEqual(r["faltam_cotacoes"], ["USDC"])

    def test_registro_legado_usdc_preservado_e_reclassificado_com_rastreabilidade(self):
        arquivo = self.root / "importado.csv"
        original = (HEADER +
            "2026-09-01 10:00:00,USDC,compra,60,5.00,60,5.00\n"
            "2026-09-02 10:00:00,USDC,venda,20,5.00,20,5.00\n")
        arquivo.write_text(original, encoding="utf-8")
        legado = DataManager(legacy_csv=arquivo, data_dir=self.root / "legado")
        self.assertEqual(legado._store.diagnostico_integridade()["operacoes_importadas"], 2)
        self.assertEqual(arquivo.read_text(encoding="utf-8"), original)
        self.assertEqual(saldos_stablecoins(
            legado.carregar_operacoes_precisas())["saldos"]["USDC"], Decimal("40"))
        self.assertTrue(legado._store.diagnostico_livro_legado()["consistente"])

    def test_posicao_usdc_zerada_nao_exige_cotacao(self):
        self.assertTrue(self.depositar("USDC", "100"))
        self.assertTrue(self.sacar("USDC", "100"))
        portfolio = AnalysisEngine.calcular_portfolio(self.dm.carregar_operacoes(), {})
        self.assertTrue(portfolio["totais"]["avaliacao_completa"])
        self.assertEqual(portfolio["totais"]["valor_atual"], 0)
        self.assertEqual(portfolio["totais"]["realizado"], 0)
        self.assertIsNone(portfolio["totais"].get("cotacoes_pendentes") and None)

    def test_usdc_legacy_historico_sem_conversao_ficticia_a_usdt(self):
        self.assertTrue(self.depositar("USDC", "80"))
        self.assertEqual(AnalysisEngine.calcular_saldo_usdt(
            self.dm.carregar_operacoes())["historico"], [])


if __name__ == "__main__":
    unittest.main()
