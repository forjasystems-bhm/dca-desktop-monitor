"""Pre-release custody reconciliation: CSV is immutable and external units never fake trades."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import hashlib
import tempfile
import unittest

from backend.backend import DataManager, AnalysisEngine
from backend.finance_analytics import calcular_analise_por_periodo
from backend.storage_sqlite import ErroArmazenamento, ErroMigracao
from backend.financial_audit import auditar_carteira_atual

HEADER = "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
ROWS = (
    "2026-01-01 12:00:00,USDT,compra,1000,5.2,1000,5.2\n"
    "2026-01-02 12:00:00,BTC,compra,500,500,1,5.2\n"
    "2026-01-03 12:00:00,BTC,venda,300,600,0.5,5.2\n"
)


class CustodiaForaCSVTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.csv = self.root/"operacoes-antigas.csv"
        self.csv.write_text(HEADER+ROWS, encoding="utf-8")
        self.original = self.csv.read_bytes()
        self.dm = DataManager(legacy_csv=self.csv, data_dir=self.root/"dados",
                              auto_import_legacy=False)
        before = self.dm.prever_csv(str(self.csv))
        self.dm.confirmar_csv(str(self.csv), before["sha256"])

    def externo(self, **extra):
        params = dict(moeda="BTC",quantidade="0.2",custodia="Cold wallet",
                      data_posicao="2026-09-30",custo_total_usdt=None,
                      confirmacao_independente=True)
        params.update(extra)
        return self.dm.registrar_posicao_externa(**params)

    def calcula(self, prices=None):
        return AnalysisEngine.calcular_portfolio(
            self.dm.carregar_operacoes_precisas(),
            {"BTC":600} if prices is None else prices,
            saldos_iniciais=self.dm.carregar_posicoes_iniciais(),
            saldos_externos=self.dm.carregar_posicoes_externas(),
        )

    def test_user_must_attest_external_origin(self):
        with self.assertRaisesRegex(ErroArmazenamento,"Confirme"):
            self.externo(confirmacao_independente=False)
        self.assertEqual(self.dm.carregar_posicoes_externas(),[])

    def test_csv_original_bytes_and_sha_remain_identical(self):
        self.externo()
        self.assertEqual(self.csv.read_bytes(),self.original)
        self.assertEqual(hashlib.sha256(self.csv.read_bytes()).hexdigest(),
                         hashlib.sha256(self.original).hexdigest())
        self.assertEqual(len(self.dm.carregar_operacoes_precisas()),3)

    def test_unknown_external_basis_adds_units_but_no_fictitious_profit(self):
        original=self.calcula()
        self.assertEqual(original["BTC"]["quantidade_final"],0.5)
        self.assertEqual(original["BTC"]["lucro_realizado"],50)
        self.externo()
        p=self.calcula()
        self.assertAlmostEqual(p["BTC"]["quantidade_final"],0.7)
        self.assertEqual(p["totais"]["valor_atual"],1220)
        self.assertEqual(p["BTC"]["lucro_realizado"],50)
        self.assertIsNone(p["BTC"]["lucro_nao_realizado"])
        self.assertIsNone(p["BTC"]["pmc_final"])
        self.assertIsNone(p["totais"]["nao_realizado"])
        self.assertEqual(p["BTC"]["total_comprado_usdt"],500)
        self.assertEqual(p["totais"]["compras_historicas_usdt"],500)
        self.assertEqual(p["totais"]["saldos_externos_declarados"],1)

    def test_documented_external_basis_does_not_modify_legacy_realized_pl(self):
        self.externo(custo_total_usdt="80")
        p=self.calcula()
        self.assertEqual(p["BTC"]["lucro_realizado"],50)
        self.assertAlmostEqual(p["BTC"]["custo_posicao_final"],330)
        self.assertAlmostEqual(p["BTC"]["lucro_nao_realizado"],90)
        self.assertEqual(p["totais"]["valor_atual"],1220)
        self.assertAlmostEqual(p["totais"]["nao_realizado"],90)
        period=calcular_analise_por_periodo(
            self.dm.carregar_operacoes_precisas(),
            saldos_externos=self.dm.carregar_posicoes_externas(),
        )
        self.assertEqual(period["ativos"]["BTC"]["realizado_historico"],Decimal("50"))
        self.assertEqual(period["ativos"]["BTC"]["compras_historicas"],Decimal("500"))
        self.assertEqual(period["ativos"]["BTC"]["quantidade"],Decimal("0.7"))
        audit=auditar_carteira_atual(
            self.dm.carregar_operacoes_precisas(),p,
            saldos_externos=self.dm.carregar_posicoes_externas(),
        )
        self.assertIsNone(audit["retorno_dietz_percentual"])

    def test_dates_before_external_snapshot_do_not_include_custody(self):
        self.externo()
        a=calcular_analise_por_periodo(
            self.dm.carregar_operacoes_precisas(),fim=date(2026,3,1),
            saldos_externos=self.dm.carregar_posicoes_externas(),
        )
        self.assertEqual(a["ativos"]["BTC"]["quantidade"],Decimal("0.5"))
        self.assertFalse(a["saldos_externos_declarados"])

    def test_duplicates_and_backdating_rejected(self):
        self.externo()
        with self.assertRaisesRegex(ErroArmazenamento,"já cadastrada"):
            self.externo()
        with self.assertRaisesRegex(ErroArmazenamento,"antecede"):
            self.externo(custodia="Corretora X",data_posicao="2025-12-31")
        self.assertEqual(len(self.dm.carregar_posicoes_externas()),1)

    def test_external_custody_does_not_authorize_sale_through_legacy_ledger(self):
        self.externo()
        self.assertFalse(self.dm.salvar_operacao([
            "2026-10-03 13:00:00","BTC","venda","420","600","0.7","5.2"
        ]))
        self.assertEqual(len(self.dm.carregar_operacoes_precisas()),3)

    def test_error_in_lot_correction_rolls_back_without_audit(self):
        self.externo()
        initial=self.dm.carregar_posicoes_externas()
        with self.assertRaisesRegex(ErroArmazenamento,"8 a 500"):
            self.dm.corrigir_posicao(
                origem="externa",moeda="BTC",custodia="Cold wallet",
                quantidade="1",custo_total_usdt="100",motivo="erro",
            )
        self.assertEqual(self.dm.carregar_posicoes_externas(),initial)
        self.assertEqual(self.dm.carregar_auditoria_posicoes(),[])

    def test_audited_correction_keeps_old_value_and_backup(self):
        self.externo()
        a=self.dm.corrigir_posicao(
            origem="externa",moeda="BTC",custodia="Cold wallet",
            quantidade="0.3",custo_total_usdt="90",
            motivo="Extrato de custódia revisado",
        )
        self.assertEqual(a["antes"]["Quantidade"],"0.2")
        self.assertEqual(a["depois"]["Quantidade"],"0.3")
        self.assertTrue(Path(a["backup_antes"]).exists())
        self.assertEqual(len(self.dm.carregar_auditoria_posicoes()),1)
        self.assertEqual(self.csv.read_bytes(),self.original)
        reopened=DataManager(data_dir=self.root/"dados",legacy_csv=None,
                             auto_import_legacy=False)
        self.assertEqual(reopened.carregar_posicoes_externas()[0]["Quantidade"],"0.3")
        self.assertEqual(len(reopened.carregar_auditoria_posicoes()),1)

    def test_cannot_import_a_second_csv_over_external_lots(self):
        self.externo()
        with self.assertRaises(ErroMigracao):
            self.dm.prever_csv(str(self.csv))
        self.assertEqual(self.csv.read_bytes(),self.original)

    def test_initial_balance_correction_cannot_invalidate_prior_sale(self):
        # A separate new user holds 1 BTC initially, then sells 0.6.
        fresh = DataManager(
            legacy_csv=self.root/"nenhum.csv",
            data_dir=self.root/"usuario_novo",
            auto_import_legacy=False,
        )
        fresh.registrar_posicao_inicial(
            moeda="BTC",quantidade="1",custodia="Ledger",
            data_posicao="2026-09-30",custo_total_usdt="100",
        )
        fresh.registrar_posicao_inicial(
            moeda="USDT",quantidade="0.01",custodia="Exchange",
            data_posicao="2026-09-30",
        )
        self.assertTrue(fresh.salvar_operacao([
            "2026-10-01 12:00:00","BTC","venda","90","150","0.6","5.2","0",
        ]), fresh.ultimo_erro)
        before=fresh.carregar_posicoes_iniciais()
        with self.assertRaises(Exception):
            fresh.corrigir_posicao(
                origem="inicial",moeda="BTC",custodia="Ledger",
                quantidade="0.4",custo_total_usdt="40",
                motivo="Conferência posterior da carteira",
            )
        self.assertEqual(fresh.carregar_posicoes_iniciais(),before)
        self.assertEqual(fresh.carregar_auditoria_posicoes(),[])

    def test_external_usdt_usdc_are_cash_not_buy_volume(self):
        self.dm.registrar_posicao_externa(
            moeda="USDT",quantidade="40",custodia="Cold storage",
            data_posicao="2026-09-30",confirmacao_independente=True,
        )
        self.dm.registrar_posicao_externa(
            moeda="USDC",quantidade="20",custodia="Exchange B",
            data_posicao="2026-09-30",confirmacao_independente=True,
        )
        p=AnalysisEngine.calcular_portfolio(
            self.dm.carregar_operacoes_precisas(),
            {"BTC":600,"USDC":0.965},
            saldos_externos=self.dm.carregar_posicoes_externas(),
        )
        self.assertEqual(p["totais"]["caixa_usdt"],840)
        self.assertEqual(p["totais"]["caixa_usdc"],20)
        self.assertAlmostEqual(p["totais"]["valor_atual"],1159.3)
        self.assertEqual(p["totais"]["compras_historicas_usdt"],500)
        self.assertIsNone(p["totais"]["nao_realizado"])

if __name__ == "__main__":
    unittest.main()
