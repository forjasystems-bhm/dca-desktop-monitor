"""Regressões financeiras: uma posição encerrada mantém todo o histórico."""
import unittest

from backend.backend import AnalysisEngine


def operacao(data, tipo, quantidade, valor, moeda="BTC"):
    return {
        "Data": data,
        "Moeda": moeda,
        "Operacao": tipo,
        "Quantidade": quantidade,
        "Valor_USDT": valor,
        "Preco": valor / quantidade,
        "Taxa_BRL": 0.0,
    }


class HistoricoPosicoesEncerradasTests(unittest.TestCase):
    def test_lucro_realizado_permanece_quando_posicao_zerada(self):
        ops = [
            operacao("2026-01-01 10:00:00", "compra", 2, 200),
            operacao("2026-02-01 10:00:00", "venda", 2, 250),
        ]
        carteira = AnalysisEngine.calcular_portfolio(ops, {"BTC": 0})
        btc = carteira["BTC"]
        self.assertEqual(btc["quantidade_final"], 0)
        self.assertEqual(btc["custo_posicao_final"], 0)
        self.assertEqual(btc["pmc_final"], 0)
        self.assertEqual(btc["lucro_realizado"], 50)
        self.assertEqual(btc["total_comprado_usdt"], 200)
        self.assertEqual(btc["total_vendido_usdt"], 250)
        self.assertEqual(carteira["totais"]["compras_historicas_usdt"], 200)
        self.assertEqual(carteira["totais"]["realizado"], 50)

    def test_posicao_encerrada_sem_lucro_nao_desaparece(self):
        ops = [
            operacao("2026-01-01 10:00:00", "compra", 1, 100),
            operacao("2026-01-02 10:00:00", "venda", 1, 100),
        ]
        carteira = AnalysisEngine.calcular_portfolio(ops, {"BTC": 0})
        self.assertIn("BTC", carteira)
        self.assertEqual(carteira["BTC"]["lucro_realizado"], 0)
        self.assertEqual(carteira["BTC"]["total_comprado_usdt"], 100)
        self.assertEqual(carteira["totais"]["compras_historicas_usdt"], 100)

    def test_prejuizo_realizado_permanece_apos_venda_total(self):
        ops = [
            operacao("2026-01-01 10:00:00", "compra", 1, 200),
            operacao("2026-01-02 10:00:00", "venda", 1, 150),
        ]
        carteira = AnalysisEngine.calcular_portfolio(ops, {"BTC": 0})
        self.assertEqual(carteira["BTC"]["lucro_realizado"], -50)
        self.assertEqual(carteira["totais"]["realizado"], -50)
        self.assertEqual(carteira["BTC"]["total_comprado_usdt"], 200)

    def test_recompra_separa_custo_aberto_de_compras_historicas(self):
        ops = [
            operacao("2026-01-01 10:00:00", "compra", 1, 100),
            operacao("2026-01-02 10:00:00", "venda", 1, 125),
            operacao("2026-01-03 10:00:00", "compra", 2, 200),
        ]
        carteira = AnalysisEngine.calcular_portfolio(ops, {"BTC": 110})
        btc = carteira["BTC"]
        self.assertEqual(btc["quantidade_final"], 2)
        self.assertEqual(btc["pmc_final"], 100)
        self.assertEqual(btc["custo_posicao_final"], 200)
        self.assertEqual(btc["total_comprado_usdt"], 300)
        self.assertEqual(btc["total_vendido_usdt"], 125)
        self.assertEqual(btc["lucro_realizado"], 25)
        self.assertEqual(btc["lucro_nao_realizado"], 20)

    def test_aporte_usdt_nao_e_compra_historica_de_ativo(self):
        ops = [
            operacao("2026-01-01 10:00:00", "compra", 500, 500, "USDT"),
            operacao("2026-01-02 10:00:00", "compra", 1, 100),
            operacao("2026-01-03 10:00:00", "venda", 1, 120),
        ]
        carteira = AnalysisEngine.calcular_portfolio(ops, {"BTC": 0})
        self.assertEqual(carteira["totais"]["compras_historicas_usdt"], 100)
        self.assertEqual(carteira["totais"]["vendas_historicas_usdt"], 120)
        self.assertEqual(carteira["totais"]["realizado"], 20)


if __name__ == "__main__":
    unittest.main()
