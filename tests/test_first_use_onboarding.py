"""PRIMEIRO USO: migração CSV integral e saldos declarados sem compras fictícias."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import hashlib
import sqlite3
from contextlib import closing
import tempfile
import unittest

from backend.backend import DataManager, AnalysisEngine
from backend.historical_valuation import patrimonio_historico_na_data
from backend.finance_analytics import calcular_analise_por_periodo
from backend.storage_sqlite import ErroMigracao, ErroArmazenamento
from backend.backup_policy import garantir_backup_diario, backup_antes_atualizacao
from backend.backup_sqlite import (
    ErroBackupSQLite, preparar_restauracao_sqlite, verificar_manifesto_sqlite,
)


HEADER = "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
ROWS = (
    "2026-01-01 10:00:00,USDT,compra,1000,5.2,1000,5.2\n"
    "2026-01-02 10:00:00,BTC,compra,500,500,1,5.2\n"
    "2026-01-03 10:00:00,BTC,venda,300,600,0.5,5.2\n"
)


class PrimeiroUsoTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data_dir = self.root / "conta"
        self.csv = self.root / "antigo" / "meu_diario_operacoes.csv"
        self.csv.parent.mkdir(parents=True)
        self.csv.write_text(HEADER + ROWS, encoding="utf-8")
        self.original = self.csv.read_bytes()
        self.db = DataManager(
            data_dir=self.data_dir, legacy_csv=self.csv,
            auto_import_legacy=False,
        )

    def test_csv_original_preview_then_full_import_and_reopen_without_duplicates(self):
        self.assertEqual(self.db.carregar_operacoes(), [])
        previous = self.db.prever_csv(str(self.csv))
        self.assertEqual(previous["quantidade"], 3)
        self.assertEqual(previous["sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(previous["moedas"], ["BTC", "USDT"])
        result = self.db.confirmar_csv(str(self.csv), previous["sha256"])
        self.assertEqual(result["importadas"], 3)
        self.assertTrue(result["backup_valido"])
        self.assertEqual(self.csv.read_bytes(), self.original)
        initial = self.db.carregar_operacoes_precisas()
        self.assertEqual(len(initial), 3)
        self.assertEqual(self.db._store.diagnostico_integridade()["operacoes_importadas"], 3)
        again = DataManager(data_dir=self.data_dir, legacy_csv=self.root / "outro.csv",
                            auto_import_legacy=False)
        self.assertEqual(again.carregar_operacoes_precisas(), initial)
        with self.assertRaises(ErroMigracao):
            again.prever_csv(str(self.csv))
        with closing(sqlite3.connect(again.arquivo_db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes_legadas").fetchone()[0], 1)

    def test_csv_changed_after_preview_fails_without_partial_rows(self):
        seen = self.db.prever_csv(str(self.csv))
        self.csv.write_bytes(self.original + b"\n")
        with self.assertRaisesRegex(ErroMigracao, "prévia|mudou"):
            self.db.confirmar_csv(str(self.csv), seen["sha256"])
        self.assertEqual(self.db.carregar_operacoes(), [])
        self.assertEqual(self.db._store.diagnostico_integridade()["importacao"], False)

    def test_csv_malformed_extra_column_fails_closed_without_partial_import(self):
        self.csv.write_text(HEADER + ROWS.replace(
            "BTC,compra", "BTC,compra,EXTRA", 1
        ), encoding="utf-8")
        with self.assertRaises(ErroMigracao):
            self.db.prever_csv(str(self.csv))
        self.assertFalse(self.db.carregar_operacoes())

    def test_csv_migrated_from_different_folder_original_cannot_be_overwritten(self):
        p = self.db.prever_csv(str(self.csv))
        self.db.confirmar_csv(str(self.csv), p["sha256"])
        with self.assertRaises(ErroArmazenamento):
            self.db.exportar_csv(str(self.csv))
        self.assertEqual(self.csv.read_bytes(), self.original)
        self.csv.unlink()
        self.assertEqual(len(self.db.carregar_operacoes_precisas()), 3)

    def test_holding_wallet_without_any_purchase_cost_stays_unknown(self):
        self.db.registrar_posicao_inicial(
            moeda="btc", quantidade="0.025", custodia="Cold wallet",
            data_posicao="2026-09-30",
        )
        self.assertEqual(len(self.db.carregar_operacoes()), 0)
        p = AnalysisEngine.calcular_portfolio(
            self.db.carregar_operacoes(), {"BTC": 60000},
            saldos_iniciais=self.db.carregar_posicoes_iniciais(),
        )
        self.assertAlmostEqual(p["BTC"]["quantidade_final"], .025)
        self.assertAlmostEqual(p["BTC"]["valor_atual_posicao"], 1500)
        self.assertIsNone(p["BTC"]["pmc_final"])
        self.assertIsNone(p["BTC"]["custo_posicao_final"])
        self.assertIsNone(p["BTC"]["lucro_nao_realizado"])
        self.assertEqual(p["totais"]["valor_atual"], 1500)
        self.assertIsNone(p["totais"]["nao_realizado"])
        self.assertTrue(p["totais"]["base_de_custo_incompleta"])

    def test_holding_without_quote_is_not_valued_by_nominal_cost_or_zero(self):
        self.db.registrar_posicao_inicial(
            moeda="ETH", quantidade="4", custodia="Corretora X",
            data_posicao="2026-09-30",
        )
        p = AnalysisEngine.calcular_portfolio(
            [], {}, saldos_iniciais=self.db.carregar_posicoes_iniciais(),
        )
        self.assertFalse(p["totais"]["avaliacao_completa"])
        self.assertEqual(p["totais"]["cotacoes_pendentes"], ["ETH"])
        self.assertIsNone(p["totais"]["valor_atual"])

    def test_known_opening_cost_is_not_fabricated_buy(self):
        self.db.registrar_posicao_inicial(
            moeda="ETH", quantidade="2", custodia="Cold wallet",
            custo_total_usdt="2500", data_posicao="2026-09-30",
        )
        p = AnalysisEngine.calcular_portfolio(
            [], {"ETH": 1500}, saldos_iniciais=self.db.carregar_posicoes_iniciais(),
        )
        self.assertEqual(p["ETH"]["custo_posicao_final"], 2500)
        self.assertEqual(p["ETH"]["lucro_nao_realizado"], 500)
        self.assertEqual(p["ETH"]["total_comprado_usdt"], 0)
        a = calcular_analise_por_periodo(
            [], saldos_iniciais=self.db.carregar_posicoes_iniciais()
        )
        self.assertEqual(a["ativos"]["ETH"]["quantidade"], Decimal("2"))
        self.assertEqual(a["ativos"]["ETH"]["compras_historicas"], Decimal("0"))

    def test_unknown_basis_blocks_sale_until_documented(self):
        self.db.registrar_posicao_inicial(
            moeda="BTC", quantidade="1", custodia="Ledger",
            data_posicao="2026-09-30",
        )
        sale = ["2026-10-01 11:00:00", "BTC", "venda", 100, 100, 1, 5]
        self.assertFalse(self.db.salvar_operacao(sale))
        self.assertIn("custo inicial", self.db.ultimo_erro)
        self.assertEqual(self.db.carregar_operacoes(), [])
        self.db._store.informar_custo_inicial("BTC", "Ledger", "70")
        self.assertTrue(self.db.salvar_operacao(sale), self.db.ultimo_erro)
        p = AnalysisEngine.calcular_portfolio(
            self.db.carregar_operacoes(), {},
            saldos_iniciais=self.db.carregar_posicoes_iniciais(),
        )
        self.assertEqual(p["BTC"]["lucro_realizado"], 30)

    def test_opening_usdt_funds_later_trade_without_fake_deposit(self):
        self.db.registrar_posicao_inicial(
            moeda="USDT", quantidade="500", custodia="Exchange A",
            data_posicao="2026-09-30",
        )
        self.assertTrue(self.db.salvar_operacao([
            "2026-10-01 11:00:00", "BTC", "compra", 200, 200, 1, 5,
        ]), self.db.ultimo_erro)
        p = AnalysisEngine.calcular_portfolio(
            self.db.carregar_operacoes(), {"BTC": 210},
            saldos_iniciais=self.db.carregar_posicoes_iniciais(),
        )
        self.assertEqual(p["totais"]["caixa_usdt"], 300)
        self.assertEqual(p["totais"]["valor_atual"], 510)
        self.assertEqual(len(self.db.carregar_operacoes()), 1)

    def test_cannot_mix_csv_with_onboarded_wallet_balances(self):
        self.db.registrar_posicao_inicial(
            moeda="BTC", quantidade=".5", custodia="Cold wallet",
            data_posicao="2026-09-30",
        )
        with self.assertRaises(ErroMigracao):
            self.db.prever_csv(str(self.csv))
        with self.assertRaises(ErroMigracao):
            self.db.importar_csv_legado(str(self.csv))
        self.assertEqual(self.csv.read_bytes(), self.original)

    def test_repeated_wallet_asset_custody_not_duplicated(self):
        kw = {"moeda": "ETH", "quantidade": "1", "custodia": "Exchange",
              "data_posicao": "2026-09-30"}
        self.db.registrar_posicao_inicial(**kw)
        with self.assertRaisesRegex(ErroArmazenamento, "duplicar"):
            self.db.registrar_posicao_inicial(**kw)
        self.assertEqual(len(self.db.carregar_posicoes_iniciais()), 1)

    def test_invalid_wallet_balance_never_inserted(self):
        for invalid in ("NaN", "Infinity", "-1", "0"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ErroArmazenamento):
                    self.db.registrar_posicao_inicial(
                        moeda="BTC", quantidade=invalid,
                        custodia="Cold wallet", data_posicao="2026-09-30"
                    )
        self.assertEqual(self.db.carregar_posicoes_iniciais(), [])

    def test_daily_backup_verified_restore_to_separate_file(self):
        self.db.registrar_posicao_inicial(
            moeda="BTC", quantidade="1.235", custodia="Corretora",
            data_posicao="2026-09-30",
        )
        first = garantir_backup_diario(self.db.arquivo_db, hoje_utc="2026-10-18")
        second = garantir_backup_diario(self.db.arquivo_db, hoje_utc="2026-10-18")
        self.assertTrue(first["realizado"])
        self.assertFalse(second["realizado"])
        manifest = verificar_manifesto_sqlite(Path(first["manifesto"]))
        self.assertEqual(manifest["sha256"], first["sha256"])
        separate = self.root / "restauracao" / "recuperado.sqlite3"
        staged = preparar_restauracao_sqlite(Path(first["manifesto"]), separate)
        self.assertFalse(staged["ativado"])
        with closing(sqlite3.connect(separate)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM posicoes_iniciais").fetchone()[0], 1)
        self.assertEqual(len(self.db.carregar_posicoes_iniciais()), 1)
        with self.assertRaises(ErroBackupSQLite):
            preparar_restauracao_sqlite(Path(first["manifesto"]), separate)

    def test_preupdate_backup_does_not_modify_db_or_csv(self):
        self.db.confirmar_csv(str(self.csv), self.db.prever_csv(str(self.csv))["sha256"])
        before = self.db.carregar_operacoes_precisas()
        snapshot = backup_antes_atualizacao(self.db.arquivo_db)
        self.assertEqual(verificar_manifesto_sqlite(
            Path(snapshot["manifesto"]))["sha256"], snapshot["sha256"])
        self.assertEqual(self.db.carregar_operacoes_precisas(), before)
        self.assertEqual(self.csv.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
