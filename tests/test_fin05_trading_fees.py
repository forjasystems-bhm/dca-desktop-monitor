"""FIN-05: tax is explicit brokerage in USDT, not the Taxa_BRL FX field."""
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from backend.backend import DataManager, AnalysisEngine
from backend.finance_analytics import calcular_analise_por_periodo
from backend.historical_valuation import patrimonio_historico_na_data


def mov(data, moeda, tipo, valor, preco, qtd, fx="5.20", fee=None):
    return [data, moeda, tipo, str(valor), str(preco), str(qtd), str(fx)] + (
        [] if fee is None else [str(fee)]
    )


class FinancialFeesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.legacy = self.root / "nao-existe.csv"
        self.dm = DataManager(legacy_csv=self.legacy, data_dir=self.root / "storage")
        self.d1 = "2026-09-01 09:00:00"
        self.d2 = "2026-09-02 09:00:00"
        self.d3 = "2026-09-03 09:00:00"

    def deposito(self, value="200"):
        return self.dm.salvar_operacao(mov(self.d1, "USDT", "compra", value, "5.2", value))

    def compra(self, fee=None):
        return self.dm.salvar_operacao(
            mov(self.d2, "BTC", "compra", "100", "100", "1", fee=fee)
        )

    def venda(self, value="130", fee=None, qty="1"):
        return self.dm.salvar_operacao(
            mov(self.d3, "BTC", "venda", value, str(Decimal(value)/Decimal(qty)), qty, fee=fee)
        )

    def test_fee_does_not_disappear_in_sqlite_reopen(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra("1.23"))
        precise = self.dm.carregar_operacoes_precisas()
        self.assertIsNone(precise[0]["Taxa_Corretagem_USDT"])
        self.assertEqual(precise[1]["Taxa_Corretagem_USDT"], "1.23")
        other = DataManager(legacy_csv=self.legacy, data_dir=self.root / "storage")
        self.assertEqual(other.carregar_operacoes_precisas(), precise)

    def test_buy_fee_raises_cost_and_deducts_cash(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra("1"))
        p = AnalysisEngine.calcular_portfolio(self.dm.carregar_operacoes(), {"BTC": 110})
        self.assertEqual(p["totais"]["caixa_usdt"], 99)
        self.assertEqual(p["BTC"]["custo_posicao_final"], 101)
        self.assertEqual(p["BTC"]["lucro_nao_realizado"], 9)

    def test_sale_fee_reduces_proceeds_and_realized_profit(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra("1"))
        self.assertTrue(self.venda(fee="2"))
        x = calcular_analise_por_periodo(self.dm.carregar_operacoes_precisas())
        self.assertEqual(x["ativos"]["BTC"]["realizado_historico"], Decimal("27"))
        self.assertEqual(x["taxas_registradas_usdt"], Decimal("3"))
        self.assertEqual(x["operacoes_sem_taxa_documentada"], 0)
        self.assertEqual(AnalysisEngine.calcular_saldo_usdt(
            self.dm.carregar_operacoes())["saldo_atual"], 227)
        p = AnalysisEngine.calcular_portfolio(self.dm.carregar_operacoes(), {})
        self.assertEqual(p["BTC"]["lucro_realizado"], 27)

    def test_partial_sale_average_basis_correct(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra("1"))
        self.assertTrue(self.venda(value="60", fee="1", qty="0.5"))
        x = calcular_analise_por_periodo(self.dm.carregar_operacoes_precisas())
        self.assertEqual(x["ativos"]["BTC"]["quantidade"], Decimal("0.5"))
        self.assertEqual(x["ativos"]["BTC"]["custo_aberto"], Decimal("50.5"))
        self.assertEqual(x["ativos"]["BTC"]["realizado_historico"], Decimal("8.5"))
        self.assertEqual(AnalysisEngine.calcular_saldo_usdt(
            self.dm.carregar_operacoes())["saldo_atual"], 158)

    def test_fee_can_make_purchase_insufficient_and_roll_back(self):
        self.assertTrue(self.deposito("100"))
        before = self.dm.carregar_operacoes_precisas()
        self.assertFalse(self.compra("0.01"))
        self.assertIn("saldo USDT negativo", self.dm.ultimo_erro)
        self.assertEqual(before, self.dm.carregar_operacoes_precisas())

    def test_fee_invalid_negative_nan_or_exceeding_sale_rejected(self):
        self.assertTrue(self.deposito())
        for fee in ["-1", "NaN", "Infinity", "erro"]:
            with self.subTest(fee=fee):
                self.assertFalse(self.compra(fee))
                self.assertEqual(len(self.dm.carregar_operacoes()), 1)
        self.assertTrue(self.compra("0"))
        self.assertFalse(self.venda(fee="150"))
        self.assertIn("superar", self.dm.ultimo_erro)

    def test_fee_absent_is_unknown_not_confirmed_zero(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        x = calcular_analise_por_periodo(self.dm.carregar_operacoes_precisas())
        self.assertEqual(x["operacoes_sem_taxa_documentada"], 1)
        self.assertEqual(x["taxas_registradas_usdt"], Decimal("0"))
        row = self.dm.carregar_operacoes_precisas()[1]
        row["Taxa_Corretagem_USDT"] = "0"
        self.assertTrue(self.dm.atualizar_operacao(1, row, motivo="Justificativa sintética do teste"))
        x = calcular_analise_por_periodo(self.dm.carregar_operacoes_precisas())
        self.assertEqual(x["operacoes_sem_taxa_documentada"], 0)

    def test_edit_fee_revalidates_later_balance_and_rolls_back(self):
        self.assertTrue(self.deposito("100"))
        self.assertTrue(self.compra("0"))
        initial = self.dm.carregar_operacoes_precisas()
        changed = dict(initial[1], Taxa_Corretagem_USDT="1")
        self.assertFalse(self.dm.atualizar_operacao(1, changed, motivo="Justificativa sintética do teste"))
        self.assertEqual(initial, self.dm.carregar_operacoes_precisas())

    def test_transfer_fx_not_brokerage_and_stable_fee_prohibited(self):
        self.assertTrue(self.deposito())
        self.assertEqual(AnalysisEngine.calcular_saldo_usdt(
            self.dm.carregar_operacoes())["saldo_atual"], 200)
        self.assertFalse(self.dm.salvar_operacao(
            mov(self.d2, "USDC", "compra", "10", "5.20", "10", fee="0.1")
        ))
        self.assertIn("corretagem", self.dm.ultimo_erro.lower())

    def test_export_import_preserves_explicit_and_missing_fees(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra("0.25"))
        output = self.root / "exportado.csv"
        self.dm.exportar_csv(output)
        with output.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertIn("Taxa_Corretagem_USDT", rows[0])
        self.assertEqual(rows[0]["Taxa_Corretagem_USDT"], "")
        self.assertEqual(rows[1]["Taxa_Corretagem_USDT"], "0.25")
        imported = DataManager(legacy_csv=output, data_dir=self.root / "imported")
        self.assertEqual(
            imported.carregar_operacoes_precisas()[1]["Taxa_Corretagem_USDT"], "0.25"
        )
        self.assertEqual(imported.carregar_operacoes_precisas()[0]["Taxa_Corretagem_USDT"], None)

    def test_historical_cash_and_market_value_include_known_fee(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra("1"))
        t = date(2026, 9, 30)
        self.dm._store.salvar_cotacoes_historicas([{
            "data_utc": t.isoformat(), "ativo": "BTC", "moeda_cotacao": "USDT",
            "preco": "110", "fonte": "Binance/CCXT:OHLCV:1d:close",
            "abertura_utc_ms": int(datetime(2026,9,30,tzinfo=timezone.utc).timestamp()*1000),
            "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
        }], hoje_utc=date(2026,10,18))
        r = patrimonio_historico_na_data(
            self.dm._store, t, hoje_utc=date(2026,10,18)
        )
        self.assertEqual(r["caixa_usdt"], Decimal("99"))
        self.assertEqual(r["patrimonio_total"], Decimal("209"))
        self.assertEqual(r["lucro_nao_realizado"], Decimal("9"))
        self.assertEqual(r["operacoes_sem_taxa_documentada"], 0)


if __name__ == "__main__":
    unittest.main()
