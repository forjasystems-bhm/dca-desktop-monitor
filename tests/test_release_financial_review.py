"""Synthetic diagnostics and documented BRL P/L, without real CSV."""
import unittest
from decimal import Decimal
from backend.ledger_diagnostics import diagnosticar_operacoes
from backend.finance_brl import apurar_brl_historico

def op(day, kind, qty, price, gross, rate, fee="0",coin="BTC"):
    return {"Data":day,"Moeda":coin,"Operacao":kind,
            "Quantidade":qty,"Preco":price,"Valor_USDT":gross,
            "Taxa_BRL":rate,"Taxa_Corretagem_USDT":fee}

class FinancialReviewReleaseTests(unittest.TestCase):
    def test_discrepancy_returns_actionable_issue_without_editing(self):
        rows=[op("2026-09-22 12:00:00","venda","173.8","10","1737.50","5.10",coin="UNI")]
        original=[dict(r) for r in rows]
        issues=diagnosticar_operacoes(rows)
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]["operacao"],1)
        self.assertEqual(issues[0]["diferenca_usdt"],Decimal("0.50"))
        self.assertIn("Confira extrato",issues[0]["orientacao"])
        self.assertEqual(rows,original)
        self.assertEqual(issues[0]["moeda"],"UNI")

    def test_brl_loss_possible_even_with_usdt_profit(self):
        rows=[op("2026-01-01 10:00:00","compra","1","100","100","6"),
              op("2026-02-01 10:00:00","venda","1","120","120","4")]
        r=apurar_brl_historico(rows,inicio="2026-02-01",fim="2026-02-28")
        self.assertEqual(r["ativos"]["BTC"]["realizado_periodo"],Decimal("-120"))
        self.assertEqual(r["totais"]["realizado_historico"],Decimal("-120"))
        self.assertEqual(r["ativos"]["BTC"]["custo_aberto"],Decimal("0"))

    def test_unknown_rate_or_fee_does_not_invent_brl_profit(self):
        rows=[op("2026-01-01 10:00:00","compra","1","100","100","0"),
              op("2026-02-01 10:00:00","venda","1","150","150","5")]
        r=apurar_brl_historico(rows)
        self.assertIsNone(r["totais"]["realizado_historico"])
        self.assertTrue(r["avisos"])
        rows[0]["Taxa_BRL"]="5"; rows[1]["Taxa_Corretagem_USDT"]=None
        self.assertIsNone(apurar_brl_historico(rows)["totais"]["realizado_historico"])

    def test_period_and_gross_mismatch_do_not_autocorrect(self):
        rows=[op("2026-01-01 10:00:00","compra","1","100","100","5"),
              op("2026-02-01 10:00:00","venda","1","150","149.50","5")]
        original=[dict(x) for x in rows]
        r=apurar_brl_historico(rows,inicio="2026-02-01",fim="2026-02-28")
        self.assertIsNone(r["totais"]["realizado_periodo"])
        self.assertEqual(rows,original)

    def test_disjoint_unknown_asset_makes_consolidated_brl_unknown(self):
        rows=[op("2026-01-01 10:00:00","compra","1","100","100","5"),
              op("2026-02-01 10:00:00","venda","1","150","150","5")]
        ext=[{"Data":"2026-01-10","Moeda":"ETH","Quantidade":"2","Custodia":"C","Custo_Total_USDT":"100"}]
        r=apurar_brl_historico(rows,saldos_externos=ext)
        self.assertIsNone(r["totais"]["realizado_historico"])
        self.assertEqual(r["ativos"]["BTC"]["realizado_historico"],Decimal("250"))
        self.assertIsNone(r["ativos"]["ETH"]["realizado_historico"])

if __name__=="__main__":
    unittest.main()
