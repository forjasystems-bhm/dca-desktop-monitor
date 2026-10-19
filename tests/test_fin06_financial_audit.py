"""FIN-06: no turnover-based ROI; externally funded portfolio return needs reconciliation."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from backend.backend import DataManager, AnalysisEngine
from backend.financial_audit import auditar_carteira_atual


def movimento(day, moeda, tipo, valor, preco, quantidade, fee=None):
    return [
        f"{day} 12:00:00", moeda, tipo,
        str(valor), str(preco), str(quantidade), "5.20",
        fee,
    ]


class AuditoriaRetornoTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = DataManager(
            legacy_csv=self.root / "nao-existe.csv",
            data_dir=self.root / "dados",
        )

    def entrada(self, day="2026-01-01", valor="1000"):
        self.assertTrue(self.db.salvar_operacao(
            movimento(day, "USDT", "compra", valor, 5.20, valor)
        ), self.db.ultimo_erro)

    def compra(self, day="2026-01-02", valor="500", preco="500", qtd="1", taxa="0"):
        self.assertTrue(self.db.salvar_operacao(
            movimento(day, "BTC", "compra", valor, preco, qtd, taxa)
        ), self.db.ultimo_erro)

    def calcula(self, precos=None, day=date(2026, 3, 1), carteira=None):
        operacoes = self.db.carregar_operacoes_precisas()
        p = carteira if carteira is not None else AnalysisEngine.calcular_portfolio(
            self.db.carregar_operacoes(), precos or {"BTC": 600}
        )
        return auditar_carteira_atual(operacoes, p, data_referencia=day)

    def test_full_liquidation_and_cash_reconcile_without_market_quotes(self):
        self.entrada()
        self.compra()
        self.assertTrue(self.db.salvar_operacao(movimento(
            "2026-02-01", "BTC", "venda", "600", "600", "1", "0"
        )))
        r = self.calcula(precos={})
        self.assertTrue(r["conciliado"], r)
        self.assertEqual(r["patrimonio_usdt"], Decimal("1100"))
        self.assertEqual(r["resultado_contabil_usdt"], Decimal("100"))
        self.assertEqual(r["resultado_patrimonial_usdt"], Decimal("100"))
        self.assertEqual(r["retorno_dietz_percentual"], Decimal("10"))

    def test_late_deposit_changes_denominator_but_not_trade_volume(self):
        self.entrada()
        self.compra()
        self.entrada("2026-02-01", "1000")
        r = self.calcula()
        self.assertTrue(r["conciliado"], r)
        self.assertEqual(r["patrimonio_usdt"], Decimal("2100"))
        self.assertEqual(r["aportes_externos_usdt"], Decimal("2000"))
        self.assertEqual(r["resultado_patrimonial_usdt"], Decimal("100"))
        self.assertGreater(r["retorno_dietz_percentual"], Decimal("6"))
        self.assertLess(r["retorno_dietz_percentual"], Decimal("7"))
        self.assertNotEqual(r["retorno_dietz_percentual"], Decimal("20"))

    def test_withdrawal_is_external_flow_not_a_trade(self):
        self.entrada()
        self.compra()
        self.assertTrue(self.db.salvar_operacao(movimento(
            "2026-02-01", "USDT", "venda", "300", "5.20", "300"
        )))
        r = self.calcula()
        self.assertTrue(r["conciliado"])
        self.assertEqual(r["retiradas_externas_usdt"], Decimal("300"))
        self.assertEqual(r["capital_externo_liquido_usdt"], Decimal("700"))
        self.assertEqual(r["patrimonio_usdt"], Decimal("800"))
        self.assertEqual(r["resultado_patrimonial_usdt"], Decimal("100"))
        self.assertGreater(r["retorno_dietz_percentual"], Decimal("10"))

    def test_known_transaction_fees_reconcile_cost_and_cash(self):
        self.entrada()
        self.assertTrue(self.db.salvar_operacao(movimento(
            "2026-01-02", "BTC", "compra", "500", "500", "1", "5"
        )))
        self.assertTrue(self.db.salvar_operacao(movimento(
            "2026-02-01", "BTC", "venda", "600", "600", "1", "3"
        )))
        r = self.calcula(precos={})
        self.assertEqual(r["resultado_patrimonial_usdt"], Decimal("92"))
        self.assertEqual(r["resultado_contabil_usdt"], Decimal("92"))
        self.assertEqual(r["retorno_dietz_percentual"], Decimal("9.2"))

    def test_undocumented_fee_disables_net_return_not_realized_result(self):
        self.entrada()
        self.compra(taxa=None)
        r = self.calcula()
        self.assertTrue(r["conciliado"])
        self.assertEqual(r["resultado_contabil_usdt"], Decimal("100"))
        self.assertEqual(r["operacoes_sem_taxa"], 1)
        self.assertIsNone(r["retorno_dietz_percentual"])
        self.assertTrue(any("sem corretagem" in x for x in r["motivos"]))

    def test_missing_quote_blocks_return_but_not_independent_cash(self):
        self.entrada()
        self.compra()
        r = self.calcula(precos={"ETH": 100})
        self.assertIsNone(r["retorno_dietz_percentual"])
        self.assertFalse(r["conciliado"])
        self.assertTrue(any("Cotações" in x for x in r["motivos"]))

    def test_external_usdc_blocks_consolidated_return_without_fx_basis(self):
        self.entrada()
        self.assertTrue(self.db.salvar_operacao(movimento(
            "2026-01-02", "USDC", "compra", "100", "5.10", "100"
        )))
        r = self.calcula(precos={"USDC": .98})
        self.assertIsNone(r["retorno_dietz_percentual"])
        self.assertTrue(any("USDC" in x for x in r["motivos"]))

    def test_missing_original_funding_blocks_false_wealth(self):
        csv_path = self.root / "inconsistente.csv"
        csv_path.write_text(
            "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
            "2026-01-02 12:00:00,BTC,compra,500,500,1,5\n", encoding="utf-8",
        )
        other = DataManager(legacy_csv=csv_path, data_dir=self.root / "legado")
        p = AnalysisEngine.calcular_portfolio(other.carregar_operacoes(), {"BTC": 600})
        r = auditar_carteira_atual(
            other.carregar_operacoes_precisas(), p, data_referencia=date(2026,3,1)
        )
        self.assertFalse(r["conciliado"])
        self.assertIsNone(r["retorno_dietz_percentual"])
        self.assertTrue(any("Livro" in x for x in r["motivos"]))

    def test_inconsistent_market_summary_is_blocked(self):
        self.entrada()
        self.compra()
        carteira = AnalysisEngine.calcular_portfolio(
            self.db.carregar_operacoes(), {"BTC": 600}
        )
        carteira["totais"]["valor_atual"] += 100
        r = self.calcula(carteira=carteira)
        self.assertFalse(r["conciliado"])
        self.assertIsNone(r["retorno_dietz_percentual"])
        self.assertEqual(r["desvio_conciliacao_usdt"], Decimal("100"))

    def test_deposit_same_day_does_not_produce_artificial_percent(self):
        self.entrada("2026-03-01", "1000")
        r = self.calcula(day=date(2026,3,1))
        self.assertTrue(r["conciliado"])
        self.assertIsNone(r["retorno_dietz_percentual"])
        self.assertTrue(any("Menos de um dia" in x for x in r["motivos"]))

    def test_zero_profit_returns_zero_instead_of_missing(self):
        self.entrada()
        self.compra()
        r = self.calcula(precos={"BTC": 500})
        self.assertEqual(r["resultado_patrimonial_usdt"], Decimal("0"))
        self.assertEqual(r["retorno_dietz_percentual"], Decimal("0"))

    def test_brl_historic_profit_is_not_converted_at_todays_fx(self):
        self.entrada()
        self.compra()
        self.assertIsNone(AnalysisEngine.calcular_pl_usdt_brl(
            self.db.carregar_operacoes(), 5.55
        ))

    def test_no_operations_is_never_reported_as_return(self):
        result = auditar_carteira_atual(
            [], {}, data_referencia=date(2026,3,1)
        )
        self.assertIsNone(result["retorno_dietz_percentual"])
        self.assertFalse(result["conciliado"])


if __name__ == "__main__":
    unittest.main()
