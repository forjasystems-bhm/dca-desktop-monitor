"""Review P1 F06/F07: depletion ends unknown basis, never unknown history."""
from datetime import date
from decimal import Decimal
import unittest
from backend.custody_ledger import apurar_custodia
from backend.finance_analytics import calcular_analise_por_periodo

D = Decimal
OPEN = [
    {"Data":"2026-01-01","Moeda":"BTC","Custodia":"A",
     "Quantidade":"1","Custo_Total_USDT":None},
    {"Data":"2026-01-01","Moeda":"BTC","Custodia":"C",
     "Quantidade":"1","Custo_Total_USDT":"100"},
]
def movement(id, date, kind, origin, dest, amount, proceeds="0"):
    return {"ID":id,"Data":date,"Tipo":kind,"Moeda":"BTC",
            "Origem":origin,"Destino":dest,"Quantidade":amount,
            "Taxa_Ativo":"0","Taxa_USDT":"0","Receita_USDT":proceeds}
MOVES = [
    movement(1,"2026-01-02","transferencia","A","B","1"),
    movement(2,"2026-01-03","venda","B","B","1","25"),
    movement(3,"2026-02-01","transferencia","C","B","1"),
    movement(4,"2026-02-02","venda","B","B","1","150"),
]

class CostEpochReviewTests(unittest.TestCase):
    def test_older_unknown_result_is_not_restated_but_february_is_50(self):
        result = apurar_custodia(OPEN,MOVES,
            inicio=date(2026,2,1),ate=date(2026,2,28))
        btc = result["resultados_por_ativo"]["BTC"]
        self.assertIsNone(btc["realizado_historico"])
        self.assertEqual(btc["realizado_periodo"],D("50"))
        self.assertIsNone(result["lucro_vendas_externas_usdt"])
        self.assertFalse(result["resultado_completo"])
        self.assertNotIn("BTC",result["ativos_sem_custo"])

    def test_period_report_uses_documented_reentry_cost(self):
        feb=calcular_analise_por_periodo([],inicio="2026-02-01",
            fim="2026-02-28",saldos_externos=OPEN,movimentos_custodia=MOVES)
        self.assertEqual(feb["ativos"]["BTC"]["realizado_periodo"],D("50"))
        self.assertEqual(feb["totais"]["realizado_periodo"],D("50"))
        self.assertIsNone(feb["ativos"]["BTC"]["realizado_historico"])
        self.assertIsNone(feb["totais"]["realizado_historico"])
        jan=calcular_analise_por_periodo([],inicio="2026-01-01",
            fim="2026-01-31",saldos_externos=OPEN,movimentos_custodia=MOVES)
        self.assertIsNone(jan["ativos"]["BTC"]["realizado_periodo"])

    def test_open_unknown_and_known_lots_must_stay_unknown(self):
        partial=MOVES[:1]+[
            movement(2,"2026-01-03","transferencia","C","B","1"),
            movement(3,"2026-02-02","venda","B","B","1","150"),
        ]
        r=apurar_custodia(OPEN,partial,inicio=date(2026,2,1))
        self.assertIsNone(r["resultados_por_ativo"]["BTC"]["realizado_periodo"])
        self.assertIn("BTC",r["ativos_sem_custo"])

    def test_known_cost_transfer_after_depleted_unknown_recovers_basis(self):
        before=apurar_custodia(OPEN,MOVES[:3])
        b=next(x for x in before["saldos"] if x["Custodia"]=="B"
               and x["Moeda"]=="BTC")
        self.assertEqual(D(b["Quantidade"]),D("1"))
        self.assertEqual(D(b["Custo_Total_USDT"]),D("100"))
        self.assertIsNone(before["resultados_por_ativo"]["BTC"]["realizado_historico"])

if __name__=="__main__":
    unittest.main()
