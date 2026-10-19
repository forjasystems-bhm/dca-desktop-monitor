"""Fotos da interface CustomTkinter REAL, usando apenas operações fictícias.

Falha deliberadamente se o ambiente de captura retornar uma imagem plana/preta.
Nunca usa dados pessoais ou preços da Binance ao gerar as capturas.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import os
import runpy
import sys
import tempfile
import time

from PIL import ImageGrab, ImageStat
import customtkinter as ctk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.backend import DataManager, AnalysisEngine
from backend.stablecoin_ledger import saldos_stablecoins
from backend.tipo_operacao import TipoOperacao


class PrecosDeExemplo:
    """Somente valores fictícios para screenshot — sem API."""
    preco_brl = 5.10
    precos_cache = {
        "BTC": 110.0, "ETH": 1500.0, "SOL": 130.0,
        "LINK": 12.0, "USDC": 0.965, "USDT": 1.0,
    }
    ultima_atualizacao = None

    def get_preco(self, moeda):
        return self.precos_cache.get(moeda)

    def atualizar_precos(self, moedas):
        return True


def render(root):
    root.update_idletasks()
    root.update()
    deadline=time.monotonic()+0.55
    while time.monotonic()<deadline:
        root.update()
        time.sleep(0.01)
    root.update_idletasks()
    root.update()


def capture(widget, filename, target):
    render(widget.winfo_toplevel())
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    width, height = widget.winfo_width(), widget.winfo_height()
    if width < 650 or height < 290:
        raise RuntimeError(f"Janela pequena ou não montada {filename}: {width}x{height}")
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert("RGB")
    stats = ImageStat.Stat(image)
    # Dark app is valid but *uniform* or black capture is not.
    extremes = image.getextrema()
    if max(channel[1] - channel[0] for channel in extremes) < 35:
        raise RuntimeError(f"Captura sem pixels reais de interface: {filename}")
    output = target / filename
    image.save(output, optimize=True)
    print(f"FRONT_SCREENSHOT={filename} {width}x{height} bytes={output.stat().st_size}", flush=True)
    return output


def main():
    target = ROOT / "docs" / "front-screenshots"
    target.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "tests" / "fixtures" / "preview_operacoes.csv"
    with tempfile.TemporaryDirectory(prefix="fin05-visual-") as directory:
        dm = DataManager(legacy_csv=fixture, data_dir=Path(directory) / "ledger")
        # Supplement fixture with an external USDC transfer and one operation with fee.
        assert dm.salvar_operacao([
            "2026-10-02 09:00:00", "USDC", "compra",
            "200", "5.12", "200", "5.12",
        ])
        assert dm.salvar_operacao([
            "2026-10-04 09:00:00", "BTC", "compra",
            "100", "100", "1", "5.20", "1",
        ])
        on = date(2026, 9, 30)
        dm._store.salvar_cotacoes_historicas([{
            "data_utc": on.isoformat(),
            "ativo": "ETH",
            "moeda_cotacao": "USDT",
            "preco": "1000",
            "fonte": "Binance/CCXT:OHLCV:1d:close",
            "abertura_utc_ms": int(
                datetime(2026, 9, 30, tzinfo=timezone.utc).timestamp() * 1000
            ),
            "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
        }])
        entry = runpy.run_path(str(ROOT / "main.pyw"), run_name="fin05_visual")
        root = ctk.CTk()
        try:
            # Need actual visible Windows Tk widgets, not HTML or illustrative frames.
            app = entry["PortfolioDCA"](root, dm, PrecosDeExemplo())
            app._countdown_ativo = False
            if app._after_id is not None:
                root.after_cancel(app._after_id)
                app._after_id = None
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            window_w = max(950, min(1450, sw - 40))
            window_h = max(660, min(930, sh - 85))
            root.state("normal")
            root.geometry(f"{window_w}x{window_h}+10+10")
            root.lift()
            render(root)
            print(f"SCREEN={sw}x{sh} WINDOW={window_w}x{window_h}", flush=True)
            eng = AnalysisEngine()
            p = eng.calcular_portfolio(dm.carregar_operacoes(), PrecosDeExemplo.precos_cache)
            d = eng.calcular_distribuicao_portfolio(dm.carregar_operacoes(), PrecosDeExemplo.precos_cache)
            assert p["totais"]["valor_atual"] == 2632
            assert p["totais"]["nao_realizado"] is None
            app.aba_distribuicao._atualizar_ui(p, None, d, 5.1)
            app.tabview.set("📈  Dashboard Geral")
            capture(root, "01_dashboard.png", target)
            app.aba_distribuicao._det_canvas.xview_moveto(1.0)
            capture(root, "06_dashboard_colunas_finais.png", target)
            app.aba_distribuicao._det_canvas.xview_moveto(0.0)

            app.tabview.set("📊  Análise por Período")
            app.aba_analise.atualizar()
            render(root)
            assert "1,850" in app.aba_analise._indicadores["compras_historicas"].cget("text")
            capture(root, "02_analise_por_periodo.png", target)

            item = app.aba_analise
            item._data_cotacao.delete(0, "end")
            item._data_cotacao.insert(0, "2026-09-30")
            hist = item._apurar_valor_historico()
            assert hist["patrimonio_total"] == Decimal("2180")
            capture(root, "03_patrimonio_historico.png", target)
            app.aba_analise._conteudo_rolavel._parent_canvas.yview_moveto(1.0)
            capture(root, "07_extrato_financeiro_rolagem.png", target)
            app.aba_analise._conteudo_rolavel._parent_canvas.yview_moveto(0.0)

            app.tabview.set("💰  Caixa (USD/BRL)")
            hist_usdt = eng.calcular_saldo_usdt(dm.carregar_operacoes())
            stable = saldos_stablecoins(dm.carregar_operacoes_precisas())
            app.aba_caixa._atualizar_ui(hist_usdt, stable)
            capture(root, "04_caixa_usdt_usdc.png", target)
            app.aba_caixa.tree.xview_moveto(1.0)
            capture(root, "08_caixa_colunas_finais.png", target)
            app.aba_caixa.tree.xview_moveto(0.0)

            app.tabview.set("✏️  Registrar Operação")
            app.aba_registro.set_combo_moeda_value("BTC")
            app.aba_registro._ao_mudar_moeda()
            app.aba_registro.set_combo_tipo_value(TipoOperacao.COMPRA.label)
            app.aba_registro._ao_mudar_tipo()
            app.aba_registro.set_entry_valor("100")
            app.aba_registro._entry_taxa_corretagem.insert(0, "1.00")
            app.aba_registro._calcular_quantidade()
            assert app.aba_registro.get_taxa_corretagem_str() == "1.00"
            capture(root, "05_registrar_operacao_taxa.png", target)
            app.aba_registro._scroll_registro._parent_canvas.yview_moveto(1.0)
            capture(root, "09_registro_confirmacao.png", target)

            report = (
                "# Capturas reais da interface — UI-01\n\n"
                "Screenshots produzidos automaticamente pela aplicação **CustomTkinter real** "
                "na execução de testes Windows do GitHub Actions.\n\n"
                "**DADOS FICTÍCIOS**: operações artificiais e cotações simuladas; "
                "não há requisições à Binance nem dados pessoais.\n\n"
                "1. Dashboard: carteira com USDC e resultado indisponível sem custo histórico do USDC.\n"
                "2. Análises por ativo/período: BTC, ETH, SOL, LINK, inclusive posições encerradas.\n"
                "3. Patrimônio histórico: avaliação 30/09/2026 com fechamento ETH=1000 USDT de teste.\n"
                "4. Caixa: entradas e saldos USDT/USDC separados.\n"
                "5. Registrar operação: campo opcional de corretagem em USDT.\n"
                "6. Dashboard rolado horizontalmente: colunas finais preservadas.\n"
                "7. Análise rolada verticalmente: extrato financeiro acessível.\n"
                "8. Caixa: navegação até a última coluna do extrato.\n"
                "9. Registro: rolagem até o botão de confirmação.\n\n"
                "**Em desenvolvimento:** painel de configurações e bandeja opt-in "
                "implementados; atualização/instalador assinados ainda aguardam "
                "homologação e pacote oficial.\n"
            )
            (target / "README.md").write_text(report, encoding="utf-8")
            # Primeira utilização: captura do diálogo REAL sobre o programa,
            # usando uma base NOVA e vazia, sem importar a carteira de exemplo.
            from gui.janela_primeiro_uso import JanelaPrimeiroUso
            fresh = DataManager(
                legacy_csv=Path(directory) / "sem-csv-anterior.csv",
                data_dir=Path(directory) / "conta-nova",
                auto_import_legacy=False,
            )
            janela_inicio = ctk.CTkToplevel(root)
            janela_inicio.title("DCA Monitor · Primeiro acesso")
            janela_inicio.geometry("1020x760+20+20")
            assistente = JanelaPrimeiroUso(
                janela_inicio, fresh, on_change=lambda: None,
                on_begin_empty=lambda: janela_inicio.destroy(),
            )
            assistente.pack(fill="both", expand=True)
            render(root)
            render(janela_inicio)
            assert fresh.carregar_operacoes_precisas() == []
            assert assistente._btn_importar.cget("state") == "disabled"
            capture(janela_inicio, "10_primeiro_uso_selecao.png", target)
            assistente._externo_flag.set(True)
            assistente._motivo_correcao.insert(
                0, "Divergência documental de quantidade na custódia"
            )
            render(janela_inicio)
            assert assistente._externo_flag.get()
            capture(janela_inicio, "11_conciliacao_saldo_fora_csv.png", target)
            assistente._parent_canvas.yview_moveto(1.0)
            render(janela_inicio)
            capture(janela_inicio, "12_transferencias_vendas_externas.png", target)
            janela_inicio.destroy()
            app._abrir_configuracoes()
            render(root)
            render(app._janela_aplicativo)
            assert app._janela_aplicativo._btn_instalar.cget("state") == "disabled"
            capture(app._janela_aplicativo, "13_configuracoes_windows.png", target)
            app._janela_aplicativo.destroy()
            render(root)
            print("FRONT_CAPTURE=PASS", flush=True)
        finally:
            app._countdown_ativo = False
            root.destroy()


if __name__ == "__main__":
    from gui_error_guard import install, verify
    install()
    main()
    verify()
