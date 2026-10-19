from datetime import date
from decimal import Decimal
import unittest
from backend.backend import AnalysisEngine
from backend.finance_analytics import calcular_analise_por_periodo

OPEN = [{'Data':'2026-01-01','Moeda':'BTC','Custodia':'A',
         'Quantidade':'1','Custo_Total_USDT':'100'}]
def event(**changes):
    row=dict(ID=1, Data='2026-01-02', Tipo='transferencia', Moeda='BTC',
             Origem='A', Destino='B', Quantidade='0.1', Taxa_Ativo='0.01',
             Receita_USDT='0', Taxa_USDT='0')
    row.update(changes)
    return row

class TransferFeeTests(unittest.TestCase):
    def test_f05_current_and_historical_result_include_network_fee(self):
        movements=[event()]
        p=AnalysisEngine.calcular_portfolio([],{'BTC':100},saldos_externos=OPEN,
                                            movimentos_custodia=movements)
        h=calcular_analise_por_periodo([],fim='2026-01-03',
                    saldos_externos=OPEN,movimentos_custodia=movements)
        self.assertEqual(Decimal(str(p['totais']['realizado'])), h['lucro_custodia_usdt'])
        self.assertEqual(p['totais']['realizado'], -1)

class UnknownRealizedTests(unittest.TestCase):
    def test_f06_unknown_sale_basis_is_unavailable_not_zero(self):
        opening=[dict(OPEN[0],Custo_Total_USDT=None)]
        p=AnalysisEngine.calcular_portfolio([],{'BTC':100},saldos_externos=opening,
             movimentos_custodia=[event(Tipo='venda',Taxa_Ativo='0',Receita_USDT='20')])
        self.assertIsNone(p['totais']['realizado'])
        self.assertEqual(p['totais']['realizado_csv'],0)

class PeriodCustodyTests(unittest.TestCase):
    def test_f07_sale_in_january_not_in_february_and_asset_totals_reconcile(self):
        sale=event(Tipo='venda',Quantidade='0.2',Taxa_Ativo='0',Receita_USDT='50')
        jan=calcular_analise_por_periodo([],inicio='2026-01-01',fim='2026-01-31',
                          saldos_externos=OPEN,movimentos_custodia=[sale])
        feb=calcular_analise_por_periodo([],inicio='2026-02-01',fim='2026-02-28',
                          saldos_externos=OPEN,movimentos_custodia=[sale])
        self.assertEqual(jan['ativos']['BTC']['realizado_periodo'],Decimal('30'))
        self.assertEqual(feb['ativos']['BTC']['realizado_periodo'],0)
        self.assertEqual(feb['totais']['realizado_historico'],Decimal('30'))
        self.assertEqual(feb['totais']['realizado_csv_historico'],0)
        p=AnalysisEngine.calcular_portfolio([],{'BTC':100},saldos_externos=OPEN,movimentos_custodia=[sale])
        self.assertEqual(p['BTC']['lucro_realizado'],30)
        self.assertEqual(p['totais']['realizado'],30)

    def test_f07_closed_unknown_asset_result_is_never_zero_in_period(self):
        opening=[dict(OPEN[0],Custo_Total_USDT=None)]
        sale=event(Tipo='venda',Quantidade='1',Taxa_Ativo='0',Receita_USDT='50')
        jan=calcular_analise_por_periodo([],fim='2026-01-31',saldos_externos=opening,movimentos_custodia=[sale])
        self.assertIsNone(jan['ativos']['BTC']['realizado_historico'])
        self.assertIsNone(jan['totais']['realizado_historico'])
