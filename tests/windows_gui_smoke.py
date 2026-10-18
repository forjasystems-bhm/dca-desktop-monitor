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

        # FIN-03: a mesma instância usada pela GUI recusa a venda de
        # BTC já encerrado e mantém todos os registros do banco.
        anterior = dm.carregar_operacoes_precisas()
        assert not dm.salvar_operacao([
            "2026-10-01 09:00:00", "BTC", "venda", "200", "20000", "0.01", "5",
        ])
        assert "venda superior" in dm.ultimo_erro
        assert dm.carregar_operacoes_precisas() == anterior
        assert not dm.excluir_operacao(0), "Remover o aporte deve invalidar compras."
        assert "saldo USDT negativo" in dm.ultimo_erro
        assert dm.carregar_operacoes_precisas() == anterior
        print("GUI_FIN03_VALIDACAO_E_ROLLBACK=PASS")

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
            janela_detalhes = ui._detalhar_ativos_na_data()
            root.update_idletasks()
            root.update()
            linhas = [
                ui._detalhes_tabela.item(item)["values"]
                for item in ui._detalhes_tabela.get_children()
            ]
            assert len(linhas) == 4
            eth = next(row for row in linhas if row[0] == "ETH")
            btc = next(row for row in linhas if row[0] == "BTC")
            assert "500" in str(eth[4]), eth
            assert "300" in str(btc[5]), btc
            janela_detalhes.destroy()
            ui._data_cotacao.delete(0, "end")
            ui._data_cotacao.insert(0, "2026-09-29")
            historico_sem_dado = ui._apurar_valor_historico()
            assert historico_sem_dado["patrimonio_total"] is None
            assert "INDISPONÍVEL" in ui._historico_valores.cget("text")
            print("GUI_HISTORICA=PASS")
            print("PATRIMONIO_2026_09_30=2180 USDT")
            print("PATRIMONIO_SEM_COTACAO=INDISPONIVEL")
            # FIN-02: a interface não pode transformar ativo aberto sem cotação em zero.
            atual = {"BTC": 40000.0, "SOL": 130.0, "LINK": 12.0, "USDT": 1.0}
            portfolio_sem_eth = app.analysis_engine.calcular_portfolio(
                dm.carregar_operacoes(), atual
            )
            dist_sem_eth = app.analysis_engine.calcular_distribuicao_portfolio(
                dm.carregar_operacoes(), atual
            )
            app.aba_distribuicao._atualizar_ui(
                portfolio_sem_eth, None, dist_sem_eth, 5.1
            )
            root.update_idletasks()
            root.update()
            dash = app.aba_distribuicao
            assert dash._lbl_patrimonio.cget("text") == "Indisponível"
            assert dash._lbl_pl_nr.cget("text") == "Indisponível"
            assert dash._lbl_pl.cget("text") == "Indisponível"
            assert "280" in dash._lbl_pl_r.cget("text")
            assert "Indisponível" in dash._lbl_div.cget("text")
            eth_row = next(
                row for row in dash._det_rows
                if row._labels[0].cget("text") == "ETH"
            )
            assert eth_row._labels[1].cget("text").startswith("0.500")
            assert eth_row._labels[5].cget("text") == "Indisponível"
            assert eth_row._labels[6].cget("text") == "Indisponível"
            app.aba_distribuicao._atualizar_ui(
                app.analysis_engine.calcular_portfolio(
                    dm.carregar_operacoes(), FakePriceManager.precos_cache
                ),
                None,
                app.analysis_engine.calcular_distribuicao_portfolio(
                    dm.carregar_operacoes(), FakePriceManager.precos_cache
                ),
                5.1,
            )
            root.update_idletasks()
            root.update()
            assert "Indisponível" not in dash._lbl_patrimonio.cget("text")
            # FIN-04: USDC does not finance USDT, and is not a 1:1 asset.
            assert dm.salvar_operacao([
                "2026-10-02 09:00:00", "USDC", "compra",
                "200", "5.12", "200", "5.12",
            ])
            stable = app.analysis_engine.calcular_saldo_usdt(dm.carregar_operacoes())
            assert stable["saldo_atual"] == 1680, stable
            app.aba_caixa._atualizar_ui(
                stable,
                __import__("backend.stablecoin_ledger", fromlist=["saldos_stablecoins"])
                .saldos_stablecoins(dm.carregar_operacoes_precisas()),
            )
            assert "200.00" in app.aba_caixa.lbl_saldo_usdc.cget("text")
            assert "Não convertido" in app.aba_caixa.lbl_fluxo_usdc.cget("text")
            cotados = {**FakePriceManager.precos_cache, "USDC": 0.965}
            carteira = app.analysis_engine.calcular_portfolio(
                dm.carregar_operacoes(), cotados
            )
            distribuicao = app.analysis_engine.calcular_distribuicao_portfolio(
                dm.carregar_operacoes(), cotados
            )
            dash._atualizar_ui(carteira, None, distribuicao, 5.1)
            root.update_idletasks()
            root.update()
            assert carteira["totais"]["valor_atual"] == 2623
            assert "2,623" in dash._lbl_patrimonio.cget("text")
            assert dash._lbl_pl_nr.cget("text") == "Indisponível"
            usdc_rows = [
                row for row in dash._det_rows
                if row._labels[0].cget("text") == "USDC (Caixa)"
            ]
            assert len(usdc_rows) == 1
            assert "200" in usdc_rows[0]._labels[1].cget("text")
            assert "Não apurado" in usdc_rows[0]._labels[4].cget("text")
            assert "USDC" in distribuicao["distribuicao"]
            print("GUI_FIN04_SALDOS_SEPARADOS=PASS")
            print("GUI_FIN04_PATRIMONIO_USDC_0_965=2623 USDT")
            print("GUI_FIN02_SEM_COTACAO=PASS")
            print("GUI_FIN02_RECUPERACAO=PASS")
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
