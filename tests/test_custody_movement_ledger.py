"""CUST-01: external custody transfers and disposals cannot invent old CSV trades."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from backend.backend import DataManager, AnalysisEngine
from backend.custody_ledger import apurar_custodia, ErroMovimentacaoCustodia
from backend.finance_analytics import calcular_analise_por_periodo


HEADER="Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
CSV=("2026-01-01 12:00:00,USDT,compra,1000,5.2,1000,5.2\n"
     "2026-01-02 12:00:00,BTC,compra,500,500,1,5.2\n"
     "2026-01-03 12:00:00,BTC,venda,300,600,0.5,5.2\n")


class MovimentacaoCustodiaTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir=Path(tmp.name)
        self.legacy=self.dir/"operacoes-originais.csv"
        self.legacy.write_text(HEADER+CSV,encoding="utf-8")
        self.old_bytes=self.legacy.read_bytes()
        self.dm=DataManager(
            data_dir=self.dir/"data",legacy_csv=self.legacy,
            auto_import_legacy=False,
        )
        preview=self.dm.prever_csv(str(self.legacy))
        self.dm.confirmar_csv(str(self.legacy),preview["sha256"])
        self.dm.registrar_posicao_externa(
            moeda="BTC",quantidade="0.30",custodia="Cold wallet",
            data_posicao="2026-09-30",custo_total_usdt="120",
            confirmacao_independente=True,
        )

    def mover(self, **kwargs):
        args=dict(tipo="transferencia",moeda="BTC",origem="Cold wallet",
                  destino="Corretora X",quantidade="0.1",
                  data_utc="2026-10-01",taxa_ativo="0",receita_usdt="0",
                  taxa_usdt="0",observacao="TXID ou documento conferido")
        args.update(kwargs)
        return self.dm.registrar_movimento_custodia(**args)

    def apurar(self):
        return apurar_custodia(
            self.dm.carregar_posicoes_externas(),
            self.dm.carregar_movimentos_custodia(),
        )

    def carteira(self):
        return AnalysisEngine.calcular_portfolio(
            self.dm.carregar_operacoes_precisas(),{"BTC":600},
            saldos_externos=self.dm.carregar_posicoes_externas(),
            movimentos_custodia=self.dm.carregar_movimentos_custodia(),
        )

    def test_transfer_between_custodies_without_legacy_trade(self):
        r=self.mover()
        self.assertTrue(Path(r["backup_sqlite"]).exists())
        d=self.apurar()
        positions={(x["Moeda"],x["Custodia"]): x for x in d["saldos"]}
        self.assertEqual(Decimal(positions["BTC","Cold wallet"]["Quantidade"]),Decimal("0.2"))
        self.assertEqual(Decimal(positions["BTC","Corretora X"]["Quantidade"]),Decimal("0.1"))
        self.assertEqual(d["vendas"],0)
        self.assertEqual(self.carteira()["BTC"]["quantidade_final"],0.8)
        self.assertEqual(self.legacy.read_bytes(),self.old_bytes)
        self.assertEqual(len(self.dm.carregar_operacoes_precisas()),3)

    def test_fee_paid_in_base_asset_reduces_inventory_and_cost(self):
        self.mover(taxa_ativo="0.001")
        d=self.apurar()
        positions={x["Custodia"]:x for x in d["saldos"] if x["Moeda"]=="BTC"}
        self.assertEqual(Decimal(positions["Cold wallet"]["Quantidade"]),Decimal("0.199"))
        self.assertEqual(Decimal(positions["Corretora X"]["Quantidade"]),Decimal("0.1"))
        self.assertEqual(d["custo_taxas_transferencias_usdt"],Decimal("0.4"))
        self.assertEqual(self.carteira()["BTC"]["quantidade_final"],0.799)

    def test_sale_credits_real_usdt_and_realized_cost_without_fake_deposit(self):
        self.mover(tipo="venda",destino="Corretora X",quantidade="0.1",
                   receita_usdt="75",taxa_usdt="2",taxa_ativo="0.005")
        d=self.apurar()
        self.assertEqual(d["lucro_vendas_externas_usdt"],Decimal("31"))
        cash=[x for x in d["saldos"] if x["Moeda"]=="USDT"]
        self.assertEqual(cash[0]["Quantidade"],"73")
        portfolio=self.carteira()
        self.assertEqual(portfolio["totais"]["caixa_usdt"],873)
        self.assertEqual(portfolio["totais"]["realizado"],81)
        self.assertEqual(portfolio["totais"]["compras_historicas_usdt"],500)
        self.assertEqual(portfolio["BTC"]["quantidade_final"],0.695)
        self.assertEqual(len(self.dm.carregar_operacoes_precisas()),3)

    def test_unknown_historical_cost_does_not_create_realized_profit(self):
        self.dm.registrar_posicao_externa(
            moeda="ETH",quantidade="1",custodia="Ledger",
            data_posicao="2026-09-30",confirmacao_independente=True,
        )
        self.mover(tipo="venda",moeda="ETH",origem="Ledger",destino="Corretora X",
                   quantidade="0.2",receita_usdt="220",taxa_usdt="1")
        d=self.apurar()
        self.assertIsNone(d["lucro_vendas_externas_usdt"])
        p=AnalysisEngine.calcular_portfolio(
            self.dm.carregar_operacoes_precisas(),{"BTC":600,"ETH":1200},
            saldos_externos=self.dm.carregar_posicoes_externas(),
            movimentos_custodia=self.dm.carregar_movimentos_custodia(),
        )
        self.assertTrue(p["totais"]["base_de_custo_incompleta"])
        self.assertIsNone(p["totais"]["nao_realizado"])

    def test_overspend_duplicate_or_backdated_movement_is_rolled_back(self):
        self.mover()
        cases=[
            {"quantidade":"1"},
            {"quantidade":"0.3","taxa_ativo":"0.001"},
            {"data_utc":"2026-09-01"},
            {"data_utc":"2026-09-31"},
            {"taxa_ativo":"-0.01"},
            {"tipo":"venda","receita_usdt":"10","taxa_usdt":"10"},
        ]
        for props in cases:
            with self.subTest(**props),self.assertRaises(Exception):
                self.mover(**props)
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()),1)

    def test_history_replays_only_events_before_cutoff(self):
        self.mover(tipo="venda",quantidade="0.1",receita_usdt="75",
                   taxa_usdt="2",data_utc="2026-10-01")
        before=calcular_analise_por_periodo(
            self.dm.carregar_operacoes_precisas(),fim="2026-09-30",
            saldos_externos=self.dm.carregar_posicoes_externas(),
            movimentos_custodia=self.dm.carregar_movimentos_custodia(),
        )
        after=calcular_analise_por_periodo(
            self.dm.carregar_operacoes_precisas(),fim="2026-10-01",
            saldos_externos=self.dm.carregar_posicoes_externas(),
            movimentos_custodia=self.dm.carregar_movimentos_custodia(),
        )
        self.assertEqual(before["ativos"]["BTC"]["quantidade"],Decimal("0.8"))
        self.assertEqual(after["ativos"]["BTC"]["quantidade"],Decimal("0.7"))
        self.assertEqual(before["saldo_usdt_inicial"],0)
        self.assertEqual(after["saldo_usdt_inicial"],Decimal("73"))
        self.assertEqual(after["lucro_custodia_usdt"],Decimal("33"))

    def test_reopen_preserves_appended_custody_journal_and_csv(self):
        self.mover()
        reopened=DataManager(data_dir=self.dir/"data",legacy_csv=None,
                             auto_import_legacy=False)
        self.assertEqual(reopened.carregar_movimentos_custodia(),
                         self.dm.carregar_movimentos_custodia())
        self.assertEqual(self.legacy.read_bytes(),self.old_bytes)
        self.assertEqual(len(reopened.carregar_operacoes_precisas()),3)

    def test_changing_opening_units_after_transfer_fails_atomically(self):
        self.mover(quantidade="0.2",taxa_ativo="0.01")
        before=self.dm.carregar_posicoes_externas()
        with self.assertRaises(ErroMovimentacaoCustodia):
            self.dm.corrigir_posicao(
                origem="externa",moeda="BTC",custodia="Cold wallet",
                quantidade="0.1",custo_total_usdt="40",
                motivo="Conferência posterior da carteira",
            )
        self.assertEqual(self.dm.carregar_posicoes_externas(),before)
        self.assertEqual(self.dm.carregar_auditoria_posicoes(),[])
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()),1)

    def test_old_wallet_can_move_before_unrelated_later_custody_snapshot(self):
        # A later second wallet must not invalidate valid earlier transfers
        # from an independently attested cold wallet.
        self.dm.registrar_posicao_externa(
            moeda="BTC",quantidade="0.05",custodia="Other Vault",
            data_posicao="2026-10-18",custo_total_usdt="20",
            confirmacao_independente=True,
        )
        self.mover(data_utc="2026-10-01")
        history=calcular_analise_por_periodo(
            self.dm.carregar_operacoes_precisas(),fim="2026-10-02",
            saldos_externos=self.dm.carregar_posicoes_externas(),
            movimentos_custodia=self.dm.carregar_movimentos_custodia(),
        )
        self.assertEqual(history["ativos"]["BTC"]["quantidade"],Decimal("0.8"))
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()),1)

    def test_ledger_fee_transfer_cannot_be_hidden_as_zero(self):
        with self.assertRaises(Exception):
            self.mover(taxa_ativo="")
        self.assertFalse(self.dm.carregar_movimentos_custodia())

if __name__=="__main__":
    unittest.main()
