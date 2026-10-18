"""Integração real da GUI Windows — não requer Binance nem histórico pessoal."""
from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path
import runpy
import tempfile
import sys

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
