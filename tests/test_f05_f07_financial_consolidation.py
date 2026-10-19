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
