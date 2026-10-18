"""Regras financeiras da análise histórica por ativo e período."""
import unittest
from decimal import Decimal

from backend.finance_analytics import (
    ErroAnaliseFinanceira, calcular_analise_por_periodo
)


def op(d, moeda, tipo, qtd, valor):
    return {
        "Data": d, "Moeda": moeda, "Operacao": tipo,
        "Quantidade": qtd, "Valor_USDT": valor,
        "Preco": Decimal(str(valor)) / Decimal(str(qtd)),
        "Taxa_BRL": 0,
    }


class AnalisePorPeriodoTests(unittest.TestCase):
    def setUp(self):
        self.ops = [
            op("2026-01-01 10:00:00", "USDT", "compra", 2000, 2000),
            op("2026-01-05 10:00:00", "BTC", "compra", 0.1, 1000),
            op("2026-02-05 10:00:00", "BTC", "venda", 0.1, 1300),
            op("2026-02-06 10:00:00", "ETH", "compra", 0.5, 600),
            op("2026-03-01 10:00:00", "SOL", "compra", 1, 100),
            op("2026-03-02 10:00:00", "SOL", "venda", 1, 80),
            op("2026-03-04 10:00:00", "LINK", "compra", 5, 50),
            op("2026-03-05 10:00:00", "LINK", "venda", 5, 50),
        ]

    def test_acumulado_ativo_encerrado_continua_visivel(self):
        r = calcular_analise_por_periodo(self.ops)
        self.assertIn("BTC", r["ativos"])
        btc = r["ativos"]["BTC"]
        self.assertEqual(btc["compras_historicas"], Decimal("1000"))
        self.assertEqual(btc["vendas_historicas"], Decimal("1300"))
        self.assertEqual(btc["realizado_historico"], Decimal("300"))
        self.assertEqual(btc["quantidade"], Decimal("0"))
        self.assertEqual(btc["custo_aberto"], Decimal("0"))
        self.assertEqual(r["totais"]["compras_historicas"], Decimal("1750"))
        self.assertEqual(r["totais"]["realizado_historico"], Decimal("280"))
        self.assertEqual(r["aportes_periodo_usdt"], Decimal("2000"))

    def test_periodo_nao_confunde_compras_anteriores_com_periodo_atual(self):
        r = calcular_analise_por_periodo(self.ops, "2026-02-01", "2026-02-28")
        btc = r["ativos"]["BTC"]
        self.assertEqual(btc["compras_periodo"], Decimal("0"))
        self.assertEqual(btc["vendas_periodo"], Decimal("1300"))
        self.assertEqual(btc["realizado_periodo"], Decimal("300"))
        self.assertEqual(r["totais"]["compras_periodo"], Decimal("600"))
        self.assertEqual(r["totais"]["realizado_periodo"], Decimal("300"))

    def test_fechamento_em_janeiro_ignora_venda_futura(self):
        r = calcular_analise_por_periodo(self.ops, "2026-01-01", "2026-01-31")
        self.assertEqual(r["ativos"]["BTC"]["quantidade"], Decimal("0.1"))
        self.assertEqual(r["ativos"]["BTC"]["custo_aberto"], Decimal("1000"))
        self.assertEqual(r["ativos"]["BTC"]["realizado_periodo"], Decimal("0"))
        self.assertNotIn("ETH", r["ativos"])

    def test_fevereiro_usa_custo_medio_de_compras_anteriores(self):
        ops = [
            op("2025-12-01 10:00:00", "BTC", "compra", 2, 200),
            op("2026-02-01 10:00:00", "BTC", "venda", 1, 140),
        ]
        r = calcular_analise_por_periodo(ops, "2026-02-01", "2026-02-28")
        self.assertEqual(r["ativos"]["BTC"]["realizado_periodo"], Decimal("40"))
        self.assertEqual(r["ativos"]["BTC"]["custo_aberto"], Decimal("100"))
        self.assertEqual(r["ativos"]["BTC"]["quantidade"], Decimal("1"))

    def test_recompra_apos_posicao_encerrada_reinicia_custo(self):
        ops = [
            op("2026-01-01 10:00:00", "BTC", "compra", 1, 100),
            op("2026-01-02 10:00:00", "BTC", "venda", 1, 130),
            op("2026-01-03 10:00:00", "BTC", "compra", 2, 300),
        ]
        r = calcular_analise_por_periodo(ops, "2026-01-03", "2026-01-03")
        btc = r["ativos"]["BTC"]
        self.assertEqual(btc["custo_aberto"], Decimal("300"))
        self.assertEqual(btc["realizado_historico"], Decimal("30"))
        self.assertEqual(btc["compras_historicas"], Decimal("400"))
        self.assertEqual(btc["realizado_periodo"], Decimal("0"))

    def test_preserva_ativo_sem_lucro(self):
        r = calcular_analise_por_periodo(self.ops)
        self.assertIn("LINK", r["ativos"])
        self.assertEqual(r["ativos"]["LINK"]["realizado_historico"], Decimal("0"))

    def test_nao_soma_aporte_usdt_duas_vezes(self):
        r = calcular_analise_por_periodo(self.ops, "2026-01-01", "2026-12-31")
        self.assertEqual(r["totais"]["compras_historicas"], Decimal("1750"))
        self.assertEqual(r["aportes_periodo_usdt"], Decimal("2000"))

    def test_venda_maior_que_saldo_exibe_erro(self):
        with self.assertRaisesRegex(ErroAnaliseFinanceira, "excede"):
            calcular_analise_por_periodo([
                op("2026-01-01 10:00:00", "BTC", "compra", 1, 100),
                op("2026-02-01 10:00:00", "BTC", "venda", 2, 300),
            ])

    def test_datas_invertidas_nao_sao_aceitas(self):
        with self.assertRaises(ErroAnaliseFinanceira):
            calcular_analise_por_periodo(self.ops, "2026-02-01", "2026-01-01")

    def test_precisao_decimal_sem_arredondamentos_intermediarios(self):
        ops = [
            op("2026-01-01 10:00:00", "BTC", "compra", "0.3", "0.3"),
            op("2026-02-01 10:00:00", "BTC", "venda", "0.1", "0.2"),
        ]
        r = calcular_analise_por_periodo(ops)
        btc = r["ativos"]["BTC"]
        self.assertEqual(btc["quantidade"], Decimal("0.2"))
        self.assertEqual(btc["custo_aberto"], Decimal("0.2"))
        self.assertEqual(btc["realizado_historico"], Decimal("0.1"))


if __name__ == "__main__":
    unittest.main()
