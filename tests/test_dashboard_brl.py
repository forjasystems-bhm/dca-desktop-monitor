from decimal import Decimal
import unittest

from backend.backend import AnalysisEngine
from backend.finance_brl import apurar_brl_historico
from gui.janela_distribuicao import JanelaDistribuicao


def trade(coin, kind, qty, price, gross, when, fx):
    return dict(Data=when, Moeda=coin, Operacao=kind, Quantidade=qty, Preco=price,
                Valor_USDT=gross, Taxa_BRL=fx, Taxa_Corretagem_USDT=None)


class DashboardBrlTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            trade('USDT', 'compra', '1000', '5', '1000', '2026-01-01 09:00:00', '5'),
            trade('BTC', 'compra', '2', '100', '200', '2026-01-02 10:00:00', '5'),
            trade('BTC', 'venda', '1', '150', '150', '2026-02-01 10:00:00', '6'),
        ]
        self.portfolio = AnalysisEngine.calcular_portfolio(self.rows, {'BTC': 200})
        self.tela = JanelaDistribuicao.__new__(JanelaDistribuicao)
        self.tela._brl = apurar_brl_historico(self.rows, estimar=True)
        self.tela._taxa_brl_valida = 7.0

    def test_brl_uses_historical_fx_for_cost_and_current_fx_for_value(self):
        self.tela.display_currency = 'BRL'
        m = self.tela._metricas('BTC', self.portfolio['BTC'])
        self.assertAlmostEqual(m['custo'], 500.0)
        self.assertAlmostEqual(m['pmc'], 500.0)
        self.assertAlmostEqual(m['pl_r'], 400.0)
        self.assertAlmostEqual(m['pl_nr'], 200 * 7.0 - 500.0)
        self.assertAlmostEqual(m['pl_tot'], 1300.0)
        self.assertTrue(m['est'])

    def test_current_fx_change_does_not_move_realized_or_cost(self):
        self.tela.display_currency = 'BRL'
        antes = self.tela._metricas('BTC', self.portfolio['BTC'])
        self.tela._taxa_brl_valida = 6.0
        depois = self.tela._metricas('BTC', self.portfolio['BTC'])
        self.assertEqual(antes['custo'], depois['custo'])
        self.assertEqual(antes['pl_r'], depois['pl_r'])
        self.assertNotEqual(antes['pl_nr'], depois['pl_nr'])

    def test_usdt_view_is_unchanged(self):
        self.tela.display_currency = 'USD'
        m = self.tela._metricas('BTC', self.portfolio['BTC'])
        self.assertAlmostEqual(m['custo'], 100.0)
        self.assertAlmostEqual(m['pl_r'], 50.0)

    def test_brl_totals_sum_assets_and_formatting(self):
        self.tela.display_currency = 'BRL'
        moedas = {k: v for k, v in self.portfolio.items() if k != 'totais'}
        custo, pl_nr, pl_r, comprado, est = self.tela._totais_exibicao(self.portfolio['totais'], moedas)
        self.assertAlmostEqual(custo, 500.0)
        self.assertAlmostEqual(pl_r, 400.0)
        self.assertAlmostEqual(comprado, float(Decimal('1000')))
        self.assertTrue(est)
        self.assertEqual(self.tela._fmt_hist(-241.47), '-R$241.47')

    def test_missing_historical_book_is_unavailable_not_zero(self):
        self.tela.display_currency = 'BRL'
        self.tela._brl = None
        m = self.tela._metricas('BTC', self.portfolio['BTC'])
        self.assertIsNone(m['custo'])
        self.assertIsNone(m['pl_tot'])


if __name__ == '__main__':
    unittest.main()
