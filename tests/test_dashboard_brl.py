import unittest

from backend.backend import AnalysisEngine
from backend.finance_brl import apurar_brl_historico
from backend.metricas_exibicao import metricas_ativo, totais_exibicao


def trade(coin, kind, qty, price, gross, when, fx):
    return dict(Data=when, Moeda=coin, Operacao=kind, Quantidade=qty, Preco=price,
                Valor_USDT=gross, Taxa_BRL=fx, Taxa_Corretagem_USDT=None)


class DashboardBrlTests(unittest.TestCase):
    def setUp(self):
        rows = [
            trade('USDT', 'compra', '1000', '5', '1000', '2026-01-01 09:00:00', '5'),
            trade('BTC', 'compra', '2', '100', '200', '2026-01-02 10:00:00', '5'),
            trade('BTC', 'venda', '1', '150', '150', '2026-02-01 10:00:00', '6'),
        ]
        self.portfolio = AnalysisEngine.calcular_portfolio(rows, {'BTC': 200})
        self.livro = apurar_brl_historico(rows, estimar=True)

    def btc(self, taxa=7.0, brl=True):
        return metricas_ativo(self.portfolio['BTC'], self.livro['ativos']['BTC'],
                              brl=brl, taxa_brl=taxa)

    def test_brl_uses_historical_fx_for_cost_and_current_fx_for_value(self):
        m = self.btc()
        self.assertAlmostEqual(m['custo'], 500.0)
        self.assertAlmostEqual(m['pmc'], 500.0)
        self.assertAlmostEqual(m['pl_r'], 400.0)
        self.assertAlmostEqual(m['pl_nr'], 200 * 7.0 - 500.0)
        self.assertAlmostEqual(m['pl_tot'], 1300.0)
        self.assertTrue(m['est'])

    def test_current_fx_change_does_not_move_realized_or_cost(self):
        antes, depois = self.btc(7.0), self.btc(6.0)
        self.assertEqual(antes['custo'], depois['custo'])
        self.assertEqual(antes['pl_r'], depois['pl_r'])
        self.assertNotEqual(antes['pl_nr'], depois['pl_nr'])

    def test_usdt_view_is_unchanged(self):
        m = self.btc(brl=False)
        self.assertAlmostEqual(m['custo'], 100.0)
        self.assertAlmostEqual(m['pl_r'], 50.0)

    def test_brl_totals_sum_assets(self):
        custo, pl_nr, pl_r, comprado, est = totais_exibicao(
            self.portfolio['totais'], [self.btc()], self.livro['totais'], brl=True)
        self.assertAlmostEqual(custo, 500.0)
        self.assertAlmostEqual(pl_nr, 900.0)
        self.assertAlmostEqual(pl_r, 400.0)
        self.assertAlmostEqual(comprado, 1000.0)
        self.assertTrue(est)

    def test_missing_quote_or_book_is_unavailable_not_zero(self):
        self.assertIsNone(self.btc(taxa=None)['pl_nr'])
        m = metricas_ativo(self.portfolio['BTC'], None, brl=True, taxa_brl=7.0)
        self.assertIsNone(m['custo'])
        self.assertIsNone(m['pl_tot'])


if __name__ == '__main__':
    unittest.main()
