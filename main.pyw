import threading
import logging
import os
import platform
import sys
from pathlib import Path

# pyrefly: ignore [missing-import]
import customtkinter as ctk

if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from backend.backend import AnalysisEngine, CCXT_AVAILABLE
from gui.janela_splash import JanelaSplash
from gui.janela_edicao import JanelaEdicao
from gui.janela_distribuicao import JanelaDistribuicao
from gui.janela_registro_logica import JanelaRegistro
from gui.janela_caixa import JanelaCaixa
from gui.janela_moedas import JanelaMoedas
from gui.janela_analise_periodo import JanelaAnalisePeriodo

from config.tema_cripto import (
    aplicar_tema,
    BG_CARD, BG_SURFACE,
    BTC_ORANGE, NEON_GREEN, CYAN,
    TEXT_SECONDARY,
)
from config.carregar_json import _carregar_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_FONT = "Courier New" if platform.system() == "Windows" else "Monospace"

CONFIG            = _carregar_config()
MOEDAS_SUPORTADAS = CONFIG["moedas"]

ABAS = [
    ("📈  Dashboard Geral",      "aba_distribuicao"),
    ("📊  Análise por Período",   "aba_analise"),
    ("💰  Caixa (USD/BRL)",         "aba_caixa"),
    ("✏️  Registrar Operação",   "aba_registro"),
    ("⚙️  Histórico e Edição",   "aba_edicao"),
    ("🪙  Gerenciar Moedas",     "aba_moedas"),
]


class PortfolioDCA:
    def __init__(self, janela: ctk.CTk, data_manager, price_manager):
        self.data_manager    = data_manager
        self.price_manager   = price_manager
        self.analysis_engine = AnalysisEngine()
        self._stop_updates   = False

        self.janela = janela
        self.janela.title("Portfolio CRIPTO — Dashboard Interativo")
        self.janela.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._preview_data01 = (
            getattr(sys, "frozen", False)
            and (Path(sys.executable).resolve().parent / "DCA-PREVIEW-MODE").is_file()
        )
        self._criar_interface()
        self._preencher_dados_iniciais()
        self._iniciar_atualizacoes_automaticas()

    def _aplicar_cursor_abas(self):
        try:
            _sb = self.tabview._segmented_button
            _sb.configure(
                text_color="#f0f4ff",
                text_color_disabled=TEXT_SECONDARY,
            )
            for _btn in _sb._buttons_dict.values():
                _btn.configure(cursor="hand2", text_color="#f0f4ff")
                for child in _btn.winfo_children():
                    try:
                        child.configure(cursor="hand2")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("cursor abas: %s", e)

    def _criar_interface(self) -> None:
        self.janela.minsize(950, 660)
        ctk.set_appearance_mode("dark")

        base_dir    = os.path.dirname(os.path.abspath(__file__))
        caminho_ico = os.path.join(base_dir, "img", "favicon.ico")
        caminho_png = os.path.join(base_dir, "img", "favicon.png")

        try:
            if platform.system() == "Windows" and os.path.exists(caminho_ico):
                self.janela.iconbitmap(caminho_ico)
            if os.path.exists(caminho_png):
                import tkinter as tk
                icone_img = tk.PhotoImage(file=caminho_png)
                self.janela.iconphoto(True, icone_img)
        except Exception:
            pass

        aplicar_tema(self.janela)

        ctk.CTkFrame(self.janela, fg_color=BTC_ORANGE, height=1, corner_radius=0).pack(
            side="bottom", fill="x"
        )
        status_bar = ctk.CTkFrame(self.janela, fg_color=BG_CARD, height=28, corner_radius=0)
        status_bar.pack(side="bottom", fill="x")
        ctk.CTkLabel(
            status_bar,
            text="Dev by Bruno Machado",
            font=ctk.CTkFont(_FONT, 9, "bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="right", padx=10)

        if self._preview_data01:
            self._montar_validacao_data01()

        self.tabview = ctk.CTkTabview(
            self.janela,
            fg_color=BG_SURFACE,
            segmented_button_fg_color=BG_CARD,
            segmented_button_selected_color=BTC_ORANGE,
            segmented_button_selected_hover_color=CYAN,
            segmented_button_unselected_color=BG_CARD,
            segmented_button_unselected_hover_color="#2a3550",
            text_color=TEXT_SECONDARY,
            text_color_disabled=TEXT_SECONDARY,
            border_color=BTC_ORANGE,
            border_width=1,
        )
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)

        for nome_aba, _ in ABAS:
            self.tabview.add(nome_aba)
            self.tabview.tab(nome_aba).grid_rowconfigure(0, weight=1)
            self.tabview.tab(nome_aba).grid_columnconfigure(0, weight=1)

        def _embutir(frame):
            frame.grid(row=0, column=0, sticky="nsew")

        self.aba_distribuicao = JanelaDistribuicao(
            self.tabview.tab("📈  Dashboard Geral"),
            self.data_manager, self.price_manager, self.analysis_engine,
        )
        _embutir(self.aba_distribuicao)

        self.aba_analise = JanelaAnalisePeriodo(
            self.tabview.tab("📊  Análise por Período"),
            self.data_manager,
        )
        _embutir(self.aba_analise)

        self.aba_caixa = JanelaCaixa(
            self.tabview.tab("💰  Caixa (USD/BRL)"),
            self.data_manager, self.price_manager, self.analysis_engine,
        )
        _embutir(self.aba_caixa)

        self.aba_registro = JanelaRegistro(
            self.tabview.tab("✏️  Registrar Operação"),
            self.data_manager, self.price_manager, self.analysis_engine,
            MOEDAS_SUPORTADAS, self.atualizar_todas_as_analises,
        )
        _embutir(self.aba_registro)

        self.aba_edicao = JanelaEdicao(
            self.tabview.tab("⚙️  Histórico e Edição"),
            self.data_manager, self.price_manager, self.analysis_engine,
            self.atualizar_todas_as_analises,
        )
        _embutir(self.aba_edicao)

        self.aba_moedas = JanelaMoedas(
            self.tabview.tab("🪙  Gerenciar Moedas"),
            on_moedas_alteradas=self._ao_alterar_moedas,
            price_manager=self.price_manager,
        )
        _embutir(self.aba_moedas)

        self.janela.after(0, self._aplicar_cursor_abas)

        try:
            self.janela.state("zoomed")
        except Exception:
            self.janela.attributes("-zoomed", True)

    def _montar_validacao_data01(self):
        faixa = ctk.CTkFrame(
            self.janela, fg_color=BG_CARD, border_color=BTC_ORANGE,
            border_width=1, corner_radius=7,
        )
        faixa.pack(side="top", fill="x", padx=15, pady=(8, 0))
        try:
            estado = self.data_manager._store.diagnostico_integridade()
            texto = (
                f"DEMONSTRAÇÃO DATA-01  •  SQLite {estado['status']}  •  "
                f"{estado['operacoes_importadas']} registros importados  •  "
                f"{estado['operacoes_atuais']} no banco  •  "
                f"Backup {'verificado' if estado['backup_valido'] else 'NÃO VERIFICADO'}"
            )
        except Exception as exc:
            texto = f"DEMONSTRAÇÃO DATA-01  •  Falha na verificação: {exc}"
        ctk.CTkLabel(
            faixa, text=texto, font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color="#f4f4f4", anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=14, pady=8)
        ctk.CTkButton(
            faixa, text="Verificar banco e backup", width=190,
            fg_color=BTC_ORANGE, text_color="#101010",
            command=self._verificar_data01,
        ).pack(side="right", padx=10, pady=6)

    def _verificar_data01(self):
        from tkinter import messagebox
        try:
            estado = self.data_manager._store.diagnostico_integridade()
            if estado["status"] != "OK":
                titulo = "DATA-01 — VERIFICAÇÃO COM FALHA"
                aviso = messagebox.showerror
            else:
                titulo = "DATA-01 — BANCO E BACKUP VERIFICADOS"
                aviso = messagebox.showinfo
            aviso(titulo, (
                "AMBIENTE DE DEMONSTRAÇÃO (DADOS FICTÍCIOS)\n\n"
                f"SQLite: {estado['integridade_sqlite']}\n"
                f"Registros importados do CSV: {estado['operacoes_importadas']}\n"
                f"Registros atuais no banco: {estado['operacoes_atuais']}\n"
                f"Backup do CSV íntegro: {'SIM' if estado['backup_valido'] else 'NÃO'}\n"
                f"Arquivo original: {estado['csv_original']}\n"
                f"Hash de origem: {estado.get('hash_legado', 'N/A')}\n\n"
                f"Banco local: {estado['banco']}\n\n"
                "O arquivo CSV original não foi substituído.\n"
                "A interface financeira ainda é a do software original."
            ))
        except Exception as exc:
            messagebox.showerror(
                "DATA-01 — NÃO FOI POSSÍVEL VERIFICAR",
                f"A integridade não pôde ser demonstrada:\n{exc}",
            )

    def _preencher_dados_iniciais(self):
        self.aba_caixa.atualizar()
        self.aba_distribuicao.atualizar()
        self.aba_analise.atualizar()
        self.aba_edicao.atualizar()

    def _iniciar_atualizacoes_automaticas(self) -> None:
        self._countdown_ativo = True
        self._countdown       = CONFIG["intervalo_atualizacao"]
        self._after_id        = None
        self._tick_countdown()

    def _tick_countdown(self):
        if not self._countdown_ativo:
            return
        if self._countdown > 0:
            self.aba_distribuicao.set_countdown(self._countdown)
            self._countdown -= 1
            self._after_id = self.janela.after(1000, self._tick_countdown)
        else:
            self.aba_distribuicao.set_countdown(0)
            self._after_id = None
            if CCXT_AVAILABLE:
                self.atualizar_todas_as_analises()

    def _reiniciar_countdown(self):
        if self._after_id is not None:
            self.janela.after_cancel(self._after_id)
            self._after_id = None
        self._countdown = CONFIG["intervalo_atualizacao"]
        self._tick_countdown()

    def atualizar_todas_as_analises(self) -> None:
        def worker():
            try:
                self._atualizar_status("⟳ Atualizando preços na Binance...", CYAN)
                # Mesmo que falhe UMA cotação, o Dashboard deve ser recalculado
                # para sinalizar posições indisponíveis, nunca manter número velho.
                moedas = list(dict.fromkeys(MOEDAS_SUPORTADAS))
                if "USDC" not in moedas:
                    operacoes = self.data_manager.carregar_operacoes_precisas()
                    if any(str(op["Moeda"]).upper() == "USDC" for op in operacoes):
                        moedas.append("USDC")
                sucesso = self.price_manager.atualizar_precos(moedas)
                self.janela.after(
                    0, lambda ok=sucesso: self._atualizar_abas_seguro(ok)
                )
            except Exception as exc:
                logger.exception("Falha no ciclo de atualização: %s", exc)
                self._atualizar_status(
                    "✕ Não foi possível atualizar; verificar dados e rede",
                    "#ff4d4d"
                )
                self.janela.after(0, self._reiniciar_countdown)

        threading.Thread(target=worker, daemon=True).start()

    def _atualizar_abas_seguro(self, precos_completos=True):
        try:
            self.aba_distribuicao.atualizar()
            self.aba_analise.atualizar()
            self.aba_caixa.atualizar()
            if precos_completos:
                self._atualizar_status("✓ Cotações atualizadas", NEON_GREEN)
            else:
                self._atualizar_status(
                    "⚠ Cotação indisponível: resultados parciais bloqueados",
                    "#e3b341",
                )
        except Exception:
            self._atualizar_status("⚠ Erro ao atualizar interface.", "#e3b341")
        finally:
            self._reiniciar_countdown()

    def _ao_alterar_moedas(self, novas_moedas: list) -> None:
        global MOEDAS_SUPORTADAS
        MOEDAS_SUPORTADAS = novas_moedas
        self.aba_registro.atualizar_lista_moedas(novas_moedas)
        self._atualizar_status("🪙 Novas moedas salvas! Buscando preços...", CYAN)
        self.atualizar_todas_as_analises()

    def _atualizar_status(self, mensagem: str, cor: str = TEXT_SECONDARY) -> None:
        def _update():
            self.aba_distribuicao.set_status(mensagem, cor)
        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            self.janela.after(0, _update)

    def _on_closing(self) -> None:
        self._countdown_ativo = False
        self._stop_updates    = True
        self.janela.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    root_principal = ctk.CTk()
    root_principal.withdraw()

    def criar_app(data_mgr, price_mgr):
        root_principal.app = PortfolioDCA(
            janela=root_principal,
            data_manager=data_mgr,
            price_manager=price_mgr,
        )

    JanelaSplash(root_principal, criar_app_callback=criar_app)
    root_principal.mainloop()