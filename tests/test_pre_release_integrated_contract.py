"""Final synthetic cross-module gate before using the user's real CSV.

No release, installer or real wallet credentials are required or allowed.
"""
from pathlib import Path
from decimal import Decimal
import hashlib
import tempfile
import unittest

from backend.backend import DataManager, AnalysisEngine
from backend.finance_analytics import calcular_analise_por_periodo
from backend.backup_policy import backup_antes_atualizacao
from backend.backup_sqlite import (
    verificar_manifesto_sqlite, preparar_restauracao_sqlite,
)
from backend.app_lifecycle import carregar_preferencias, verificar_release_estavel


class IntegracaoPreCSVTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.original=self.root/"user-old.csv"
        self.original.write_text(
            "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
            "2026-01-01 09:00:00,USDT,compra,1000,5.2,1000,5.2\n"
            "2026-01-02 09:00:00,ETH,compra,200,200,1,5.2\n"
            "2026-01-03 09:00:00,ETH,venda,120,240,0.5,5.2\n",
            encoding="utf-8",
        )
        self.bytes=self.original.read_bytes()
        self.sha=hashlib.sha256(self.bytes).hexdigest()
        self.dir=self.root/"data"

    def novo(self):
        return DataManager(
            data_dir=self.dir,legacy_csv=None,
            auto_import_legacy=False,
        )

    def test_import_external_transfer_sale_backup_restore_same_original(self):
        dm=self.novo()
        preview=dm.prever_csv(str(self.original))
        self.assertEqual(preview["sha256"],self.sha)
        self.assertEqual(dm.confirmar_csv(str(self.original),preview["sha256"])["importadas"],3)
        dm.registrar_posicao_externa(
            moeda="ETH",quantidade="2",custodia="Ledger",
            data_posicao="2026-09-30",custo_total_usdt="300",
            confirmacao_independente=True,
        )
        dm.registrar_movimento_custodia(
            tipo="transferencia",moeda="ETH",origem="Ledger",
            destino="Exchange A",quantidade="1",
            data_utc="2026-10-01",taxa_ativo="0.002",
            receita_usdt="0",taxa_usdt="0",
            observacao="Transferência com TXID verificado",
        )
        dm.registrar_movimento_custodia(
            tipo="venda",moeda="ETH",origem="Exchange A",
            destino="Exchange A",quantidade="0.4",
            data_utc="2026-10-02",taxa_ativo="0.001",
            receita_usdt="110",taxa_usdt="1",
            observacao="Venda externa com comprovante",
        )
        reopened=self.novo()
        self.assertEqual(reopened.carregar_operacoes_precisas(),
                         dm.carregar_operacoes_precisas())
        self.assertEqual(len(reopened.carregar_movimentos_custodia()),2)
        self.assertEqual(self.original.read_bytes(),self.bytes)
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(),self.sha)
        missing=AnalysisEngine.calcular_portfolio(
            reopened.carregar_operacoes_precisas(),{},
            saldos_externos=reopened.carregar_posicoes_externas(),
            movimentos_custodia=reopened.carregar_movimentos_custodia(),
        )
        self.assertFalse(missing["totais"]["avaliacao_completa"])
        self.assertIsNone(missing["totais"]["valor_atual"])
        assert "ETH" in missing["totais"]["cotacoes_pendentes"]
        shown=AnalysisEngine.calcular_portfolio(
            reopened.carregar_operacoes_precisas(),{"ETH":250},
            saldos_externos=reopened.carregar_posicoes_externas(),
            movimentos_custodia=reopened.carregar_movimentos_custodia(),
        )
        self.assertAlmostEqual(shown["ETH"]["quantidade_final"],2.097)
        self.assertEqual(shown["totais"]["compras_historicas_usdt"],200)
        self.assertEqual(len(reopened.carregar_operacoes_precisas()),3)
        old=calcular_analise_por_periodo(
            reopened.carregar_operacoes_precisas(),fim="2026-09-30",
            saldos_externos=reopened.carregar_posicoes_externas(),
            movimentos_custodia=reopened.carregar_movimentos_custodia(),
        )
        self.assertEqual(old["ativos"]["ETH"]["quantidade"],Decimal("2.5"))
        post=calcular_analise_por_periodo(
            reopened.carregar_operacoes_precisas(),fim="2026-10-02",
            saldos_externos=reopened.carregar_posicoes_externas(),
            movimentos_custodia=reopened.carregar_movimentos_custodia(),
        )
        self.assertEqual(post["ativos"]["ETH"]["quantidade"],Decimal("2.097"))
        self.assertEqual(post["ativos"]["ETH"]["realizado_historico"],Decimal("20"))
        assert post["lucro_custodia_usdt"] is not None
        backup=backup_antes_atualizacao(reopened.arquivo_db)
        assert verificar_manifesto_sqlite(Path(backup["manifesto"]))["sha256"]==backup["sha256"]
        restored=self.root/"restored"/"dca.sqlite3"
        recovery=preparar_restauracao_sqlite(Path(backup["manifesto"]),restored)
        self.assertFalse(recovery["ativado"])
        self.assertEqual(restored.read_bytes(),Path(backup["backup"]).read_bytes())
        self.assertEqual(self.original.read_bytes(),self.bytes)

    def test_release_and_preferences_cannot_trigger_install_or_hidden_tray(self):
        self.assertFalse(carregar_preferencias(self.dir)["minimizar_para_bandeja"])
        latest=verificar_release_estavel(
            versao_atual="0.1.0",
            fetch=lambda: {"tag_name":"v0.2.0","draft":False,"prerelease":False},
        )
        self.assertEqual(latest["estado"],"disponivel")
        self.assertFalse(latest["download_disponivel"])
        self.assertFalse((self.root/"dist").exists())


if __name__=="__main__":
    unittest.main()
