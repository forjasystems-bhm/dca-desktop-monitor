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
            # Falha parcial da Binance deve recalcular a tela — jamais
            # reter um valor anterior como atual ou interromper o callback.
            from unittest.mock import patch
            chamadas_refresh = []
            original_refresh = app._atualizar_abas_seguro
            original_preco = app.price_manager.atualizar_precos
            app._atualizar_abas_seguro = (
                lambda precos_completos=True: chamadas_refresh.append(precos_completos)
            )
            app.price_manager.atualizar_precos = lambda moedas: False

            class ThreadDireta:
                def __init__(self, target, daemon=False):
                    self.target = target
                def start(self):
                    self.target()

            with patch.object(entry["threading"], "Thread", ThreadDireta):
                app.atualizar_todas_as_analises()
            root.update_idletasks()
            root.update()
            assert False in chamadas_refresh, chamadas_refresh
            app._atualizar_abas_seguro = original_refresh
            app.price_manager.atualizar_precos = original_preco
            print("GUI_FIN04_FALHA_COTACAO_RECALCULA=PASS")
            print("GUI_FIN02_SEM_COTACAO=PASS")
            print("GUI_FIN02_RECUPERACAO=PASS")
            # FIN-05: the real form has a single, optional fee field.
            assert hasattr(app.aba_registro, "_entry_taxa_corretagem")
            assert app.aba_registro.get_taxa_corretagem_str() == ""
            assert hasattr(app.aba_edicao, "_campo_corretagem")
            assert dm.salvar_operacao([
                "2026-10-04 12:00:00", "BTC", "compra",
                "100", "100", "1", "5.20", "1",
            ])
            d = app.analysis_engine.calcular_portfolio(
                dm.carregar_operacoes(), {"BTC": 110, "ETH": 1500, "USDC": 0.965}
            )
            assert d["BTC"]["custo_posicao_final"] == 101, d["BTC"]
            assert d["totais"]["caixa_usdt"] == 1579, d["totais"]
            assert d["BTC"]["lucro_nao_realizado"] == 9
            print("GUI_FIN05_CAMPO_E_CALCULO=PASS")
            # FIN-06: UI must not mistake trade volume for portfolio return,
            # nor translate historic USD P/L using today's BRL exchange rate.
            from backend.financial_audit import auditar_carteira_atual
            from backend.backend import AnalysisEngine
            def fatia(dia, moeda, tipo, valor, preco, quantidade):
                return {
                    "Data": f"{dia} 12:00:00", "Moeda": moeda,
                    "Operacao": tipo, "Valor_USDT": str(valor),
                    "Preco": str(preco), "Quantidade": str(quantidade),
                    "Taxa_BRL": "5.20", "Taxa_Corretagem_USDT": (
                        None if moeda == "USDT" else "0"
                    ),
                }
            auditoria_op = [
                fatia("2026-01-01", "USDT", "compra", 1000, 5.2, 1000),
                fatia("2026-01-02", "BTC", "compra", 500, 500, 1),
                fatia("2026-02-01", "BTC", "venda", 600, 600, 1),
            ]
            portfolio_audit = AnalysisEngine.calcular_portfolio(auditoria_op, {})
            dist_audit = AnalysisEngine.calcular_distribuicao_portfolio(auditoria_op, {})
            audit = auditar_carteira_atual(
                auditoria_op, portfolio_audit,
                data_referencia=date(2026, 3, 1),
            )
            assert audit["conciliado"] and audit["retorno_dietz_percentual"] == Decimal("10"), audit
            dash.display_currency = "BRL"
            dash._atualizar_ui(portfolio_audit, None, dist_audit, 5.10, audit)
            root.update_idletasks()
            root.update()
            assert dash._lbl_retorno.cget("text") == "+10.00%"
            assert "100.00 USDT" in dash._lbl_pl_r.cget("text")
            assert "100.00 USDT" in dash._lbl_pl.cget("text")
            assert "BRL" not in dash._lbl_pl_r.cget("text")
            assert "BRL" not in dash._lbl_custo.cget("text")
            print("GUI_FIN06_RETORNO_DIETZ=PASS")
            print("GUI_FIN06_PNL_HISTORICO_SOMENTE_USDT=PASS")
            dash.display_currency = "USD"
            # UI-01: even at a compact desktop viewport, none of the
            # ten financial columns may be compressed into an unreadable grid.
            root.state("normal")
            root.geometry("980x700+5+5")
            root.update_idletasks()
            root.update()
            dash = app.aba_distribuicao
            canvas = dash._det_canvas
            assert canvas.winfo_width() >= 250, canvas.winfo_width()
            assert canvas.xview()[1] < 0.99, (
                "A grade não tem colunas laterais navegáveis.", canvas.xview()
            )
            assert len(dash._det_rows[0]._labels) == 10
            assert dash._det_rows[0]._labels[9].winfo_width() >= 90
            canvas.xview_moveto(1.0)
            root.update()
            assert canvas.xview()[0] > 0.10, canvas.xview()
            assert canvas.winfo_width() < dash._det_rows[0].winfo_width()
            print("GUI_UI01_DASHBOARD_HORIZONTAL=PASS")
            canvas.xview_moveto(0.0)

            analise = app.aba_analise
            assert analise._conteudo_rolavel.winfo_exists()
            analise._data_cotacao.delete(0, "end")
            analise._data_cotacao.insert(0, "2026-09-30")
            assert analise._apurar_valor_historico()["patrimonio_total"] == Decimal("2180")
            assert "2,180.00" in analise._historico_cards["patrimonio_total"].cget("text")
            assert "1,680.00" in analise._historico_cards["caixa_usdt"].cget("text")
            assert analise._historico_valores.cget("wraplength") <= 900
            scroll = analise._conteudo_rolavel._parent_canvas
            root.update()
            assert scroll.yview()[1] < 1.0, scroll.yview()
            scroll.yview_moveto(1.0)
            root.update()
            assert scroll.yview()[0] > 0.0, scroll.yview()
            assert analise._arvore.winfo_exists()
            print("GUI_UI01_ANALYSIS_SCROLL_AND_CARDS=PASS")
            assert analise._arvore.column("compras_periodo")["minwidth"] >= 160
            assert analise._arvore.column("realizado_historico")["minwidth"] >= 170
            print("GUI_UI01_TITULOS_EXTRATO_LEGIVEIS=PASS")
            dash.set_status(
                "Retorno não apurado: histórico USDC sem custo de aquisição comprovado",
                "#95a5b2",
            )
            assert dash._badge._lbl.cget("text") == "Verificar dados"
            assert "USDC" in dash._status_detalhe.cget("text")
            assert dash._status_detalhe.cget("wraplength") <= 950
            print("GUI_UI01_AVISOS_FINANCEIROS_SEM_CORTE=PASS")

            app.tabview.set("✏️  Registrar Operação")
            root.update_idletasks()
            root.update()
            form_scroller = app.aba_registro._scroll_registro._parent_canvas
            assert app.aba_registro._btn_salvar.winfo_exists()
            form_scroller.yview_moveto(1.0)
            root.update()
            assert form_scroller.yview()[0] > 0.0, form_scroller.yview()
            print("GUI_UI01_OPERACAO_CONFIRMACAO_ACESSIVEL=PASS")

            app.tabview.set("💰  Caixa (USD/BRL)")
            root.update_idletasks()
            root.update()
            extrato = app.aba_caixa.tree
            assert app.aba_caixa._extrato_scroll_horizontal.winfo_exists()
            for coluna in ("Data", "Tipo", "Descrição", "Saldo Atualizado"):
                assert extrato.column(coluna)["minwidth"] >= 150
            print("GUI_UI01_CAIXA_COLUNAS_PRESERVADAS=PASS")

            # OPS-01: startup does not perform a Binance request. Use
            # the actual splash boot procedure without creating a second UI.
            from backend.local_startup import abrir_carteira_local
            from gui.janela_splash import JanelaSplash
            from unittest.mock import patch
            offline_manager = FakePriceManager()
            offline_manager.atualizar_precos = lambda *_: (
                (_ for _ in ()).throw(AssertionError("Network used during startup"))
            )
            local_db, price_no_net = abrir_carteira_local(
                data_factory=lambda: dm,
                price_factory=lambda: offline_manager,
            )
            assert local_db is dm and price_no_net is offline_manager
            splash = object.__new__(JanelaSplash)
            splash.sucesso = False
            splash._erro = None
            with patch("backend.local_startup.abrir_carteira_local", return_value=(dm, offline_manager)):
                splash._carregar_dados()
            assert splash.sucesso
            assert splash._erro is None
            print("GUI_OPS01_STARTUP_OFFLINE=PASS")

            # OPS-01: repeated refresh requests must not start parallel
            # workers or commit background results after window destruction.
            # A atualização inicial pode já estar ativa neste ponto,
            # conforme o escalonamento da thread Windows. Ambas as situações
            # devem rejeitar a segunda atualização.
            acquired = app._refresh_lock.acquire(blocking=False)
            try:
                assert app.atualizar_todas_as_analises() is False
            finally:
                if acquired:
                    app._refresh_lock.release()
            assert app._closing is False
            app._on_closing()
            assert app._closing and not app._countdown_ativo
            assert app._after_id is None and app._initial_refresh_id is None
            assert app.atualizar_todas_as_analises() is False
            assert app._agendar_ui(lambda: 1 / 0) is False
            print("GUI_OPS01_SEM_CONCORRENCIA_E_FECHAMENTO=PASS")
            print("GUI_INTEGRADA=PASS")
            print("MODULOS=SQLite+AnalysisEngine+AssetPeriodAnalytics+CustomTkinter")
            print("REGISTROS_MIGRADOS=" + str(dm._store.diagnostico_integridade()["operacoes_importadas"]))
            print("ATIVOS=" + ",".join(sorted(nomes)))
            print("P_L_REALIZADO_TOTAL=280 USDT")
            print("COMPRA_HISTORICA_TOTAL=1750 USDT")
        finally:
            # OPS-01 also tests WM_DELETE_WINDOW; double-destroy is unnecessary.
            try:
                if root.winfo_exists():
                    root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    main()
