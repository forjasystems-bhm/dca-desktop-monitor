"""Integração real da GUI Windows — não requer Binance nem histórico pessoal."""
from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path
import runpy
import tempfile
import sys
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import customtkinter as ctk

from backend.backend import DataManager
from backend.finance_analytics import calcular_analise_por_periodo


class FakePriceManager:
    preco_brl = 5.1
    precos_cache = {"BTC": 40000.0, "ETH": 1500.0, "SOL": 130.0, "LINK": 12.0, "USDT": 1.0}
    ultima_atualizacao = None
    def get_preco(self, moeda): return self.precos_cache.get(moeda)
    def atualizar_precos(self, moedas): return True


def main():
    projeto = Path(__file__).resolve().parent.parent
    fixture = projeto / "tests" / "fixtures" / "preview_operacoes.csv"
    with tempfile.TemporaryDirectory(prefix="dca-integration-gui-") as pasta:
        dm = DataManager(legacy_csv=fixture, data_dir=Path(pasta) / "SQLite")
        model = calcular_analise_por_periodo(dm.carregar_operacoes_precisas())
        assert model["totais"]["compras_historicas"] == Decimal("1750"), model["totais"]
        assert model["ativos"]["BTC"]["realizado_historico"] == Decimal("300")
        assert model["ativos"]["SOL"]["realizado_historico"] == Decimal("-20")
        assert model["ativos"]["LINK"]["realizado_historico"] == Decimal("0")
        assert model["ativos"]["ETH"]["custo_aberto"] == Decimal("600")

        # Cotação histórica de ETH difere deliberadamente do preço atual do fake.
        ontem = date(2026, 9, 30)
        dm._store.salvar_cotacoes_historicas([{
            "data_utc": ontem.isoformat(),
            "ativo": "ETH",
            "moeda_cotacao": "USDT",
            "preco": "1000",
            "fonte": "Binance/CCXT:OHLCV:1d:close",
            "abertura_utc_ms": int(datetime(
                2026, 9, 30, tzinfo=timezone.utc
            ).timestamp() * 1000),
            "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
        }])

        entry = runpy.run_path(str(projeto / "main.pyw"), run_name="dca_gui_smoke")
        root = ctk.CTk()
        try:
            root.geometry("1550x900")
            app = entry["PortfolioDCA"](root, dm, FakePriceManager())
            root.update_idletasks()
            root.update()
            tab = app.tabview.tab("📊  Análise por Período")
            assert tab.winfo_exists(), "Aba de análise financeira não foi montada."
            app.aba_analise.atualizar()
            root.update_idletasks()
            root.update()
            cards = app.aba_analise._indicadores
            assert len(cards) == 6, f"Indicadores ausentes: {list(cards)}"
            assert "1,750" in cards["compras_historicas"].cget("text")
            assert "280" in cards["realizado_historico"].cget("text")
            rows = app.aba_analise._arvore.get_children()
            assert len(rows) == 4, f"Esperadas 4 criptomoedas, recebidas {len(rows)}"
            nomes = {
                app.aba_analise._arvore.item(row)["values"][0]
                for row in rows
            }
            assert nomes == {"BTC", "ETH", "SOL", "LINK"}, nomes
            # Renderização real: preço atual ETH=1500, histórico ETH=1000.
            ui = app.aba_analise
            ui._data_cotacao.delete(0, "end")
            ui._data_cotacao.insert(0, "2026-09-30")
            historico = ui._apurar_valor_historico()
            assert historico["completo"]
            assert historico["patrimonio_total"] == Decimal("2180")
            assert "2,180.00" in ui._historico_valores.cget("text")
            ui._data_cotacao.delete(0, "end")
            ui._data_cotacao.insert(0, "2026-09-29")
            historico_sem_dado = ui._apurar_valor_historico()
            assert historico_sem_dado["patrimonio_total"] is None
            assert "INDISPONÍVEL" in ui._historico_valores.cget("text")
            print("GUI_HISTORICA=PASS")
            print("PATRIMONIO_2026_09_30=2180 USDT")
            print("PATRIMONIO_SEM_COTACAO=INDISPONIVEL")
            print("GUI_INTEGRADA=PASS")
            print("MODULOS=SQLite+AnalysisEngine+AssetPeriodAnalytics+CustomTkinter")
            print("REGISTROS_MIGRADOS=" + str(dm._store.diagnostico_integridade()["operacoes_importadas"]))
            print("ATIVOS=" + ",".join(sorted(nomes)))
            print("P_L_REALIZADO_TOTAL=280 USDT")
            print("COMPRA_HISTORICA_TOTAL=1750 USDT")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
