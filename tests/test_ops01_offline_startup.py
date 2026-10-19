"""OPS-01: offline boot must never require network or lose financial records."""
from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing

from backend.backend import DataManager, PriceManager, AnalysisEngine
from backend.local_startup import abrir_carteira_local, FalhaInicializacaoLocal
from backend.storage_sqlite import ErroMigracao


class PriceManagerRedeProibida:
    def __init__(self):
        self.precos_cache = {}
        self.falhas_cotacao = set()

    def atualizar_precos(self, *_args):
        raise AssertionError("Startup must never request Binance")


class InicializacaoOffline(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.csv = self.root / "historico.csv"
        self.data_dir = self.root / "db"
        self.csv.write_text(
            "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
            "2026-01-01 12:00:00,USDT,compra,1000,5.2,1000,5.2\n"
            "2026-01-02 12:00:00,BTC,compra,500,500,1,5.2\n",
            encoding="utf-8",
        )

    def novo(self):
        return DataManager(legacy_csv=self.csv, data_dir=self.data_dir)

    def abrir(self, price_factory=PriceManagerRedeProibida):
        return abrir_carteira_local(data_factory=self.novo, price_factory=price_factory)

    def test_boot_local_does_not_call_network_and_preserves_portfolio(self):
        before = self.csv.read_bytes()
        dm, pm = self.abrir()
        self.assertIsInstance(pm, PriceManagerRedeProibida)
        self.assertEqual(len(dm.carregar_operacoes()), 2)
        self.assertEqual(self.csv.read_bytes(), before)
        self.assertTrue(dm._store.diagnostico_integridade()["status"] == "OK")
        p = AnalysisEngine.calcular_portfolio(dm.carregar_operacoes(), {})
        self.assertIsNone(p["totais"]["valor_atual"])
        self.assertEqual(p["totais"]["caixa_usdt"], 500)
        self.assertEqual(p["BTC"]["custo_posicao_final"], 500)

    def test_price_manager_with_no_ccxt_is_valid_for_offline_boot(self):
        def sem_rede():
            pm = PriceManager.__new__(PriceManager)
            pm.exchange = None
            pm.precos_cache = {}
            pm.cotacoes_atualizadas_em = {}
            pm.falhas_cotacao = set()
            pm.preco_brl = 0.0
            pm._brl_falhou = True
            pm._brl_atualizado_em = None
            return pm
        dm, pm = self.abrir(price_factory=sem_rede)
        self.assertFalse(pm.atualizar_precos(["BTC"]))
        p = AnalysisEngine.calcular_portfolio(
            dm.carregar_operacoes(), pm.precos_para_avaliacao()
        )
        self.assertEqual(p["totais"]["cotacoes_pendentes"], ["BTC"])
        self.assertIsNone(pm.taxa_brl_para_avaliacao())

    def test_offline_db_reopen_is_identical_and_no_duplicate_import(self):
        first, _ = self.abrir()
        initial = first.carregar_operacoes_precisas()
        second, _ = self.abrir()
        self.assertEqual(second.carregar_operacoes_precisas(), initial)
        self.assertEqual(second._store.diagnostico_integridade()["operacoes_importadas"], 2)

    def test_legacy_csv_changed_or_missing_backup_blocks_startup_without_reset(self):
        dm, _ = self.abrir()
        before = dm.carregar_operacoes_precisas()
        raw = self.csv.read_bytes()
        self.csv.write_bytes(raw + b"\n")
        with self.assertRaisesRegex(Exception, "CSV legado"):
            self.abrir()
        self.csv.write_bytes(raw)
        self.assertEqual(self.novo().carregar_operacoes_precisas(), before)
        backup = next((self.data_dir / "backups").glob("legado-*.csv"))
        backup.unlink()
        with self.assertRaises((FalhaInicializacaoLocal, ErroMigracao)):
            self.abrir()
        # Source CSV and SQLite records remain byte-preserved. No backup
        # silently regenerated; only an explicit restoration may unblock.
        self.assertFalse(backup.exists())
        self.assertEqual(self.csv.read_bytes(), raw)
        with closing(sqlite3.connect(dm.arquivo_db)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0], 2
            )

    def test_sqlite_corruption_never_displays_empty_portfolio_as_success(self):
        dm, _ = self.abrir()
        db_path = Path(dm.arquivo_db)
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db_path.write_bytes(b"not-a-sqlite-database")
        with self.assertRaises((sqlite3.DatabaseError, FalhaInicializacaoLocal)):
            self.abrir()
        self.assertEqual(db_path.read_bytes(), b"not-a-sqlite-database")

    def test_network_failure_does_not_reuse_recent_cached_quotes(self):
        from datetime import datetime, timezone
        pm = PriceManager.__new__(PriceManager)
        pm.exchange = None
        pm.precos_cache = {"BTC": 100.0, "USDC": 0.98}
        now = datetime.now(timezone.utc)
        pm.cotacoes_atualizadas_em = {"BTC": now, "USDC": now}
        pm.falhas_cotacao = set()
        pm._brl_falhou = False
        pm._brl_atualizado_em = now
        pm.preco_brl = 5.25
        self.assertEqual(pm.precos_para_avaliacao()["BTC"], 100.0)
        pm.invalidar_cotacoes(["BTC", "USDC"])
        self.assertEqual(pm.precos_para_avaliacao(), {"USDT": 1.0})
        self.assertIsNone(pm.taxa_brl_para_avaliacao())
        self.assertEqual(pm.precos_cache["BTC"], 100.0)

    def test_offline_changes_still_obey_financial_validators(self):
        dm, _ = self.abrir()
        self.assertFalse(dm.salvar_operacao([
            "2026-01-03 12:00:00", "ETH", "compra", "800", "800", "1", "5.2",
        ]))
        self.assertIn("saldo USDT negativo", dm.ultimo_erro)
        self.assertEqual(len(self.novo().carregar_operacoes()), 2)


if __name__ == "__main__":
    unittest.main()
