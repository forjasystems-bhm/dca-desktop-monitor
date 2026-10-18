import threading
import logging
import os
import platform
import sys
import subprocess
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
from gui.janela_primeiro_uso import JanelaPrimeiroUso
from gui.janela_aplicativo import JanelaAplicativo
from backend.app_lifecycle import carregar_preferencias
from backend.tray_windows import BandejaWindows, ErroBandeja

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
        self._closing = False
        self._refresh_lock = threading.Lock()
        self._initial_refresh_id = None
        self._primeiro_uso_janela = None
        self._janela_aplicativo = None
        self._tray_hidden = False
        try:
            self._preferences = carregar_preferencias(data_manager._store.diretorio)
        except Exception as exc:
            logger.warning("Preferências do Windows inválidas; modo bandeja DESLIGADO: %s", exc)
            self._preferences = {"minimizar_para_bandeja": False}
        self._tray = BandejaWindows(
            ao_abrir=lambda: self._agendar_ui(self._restaurar_da_bandeja),
            ao_atualizar=lambda: self._agendar_ui(self.atualizar_todas_as_analises),
            ao_sair=lambda: self._agendar_ui(lambda: self._on_closing(force=True)),
            icone=Path(__file__).resolve().parent/"img"/"favicon.png",
        )

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
        if (not self.data_manager.carregar_operacoes_precisas()
                and not self.data_manager.carregar_posicoes_iniciais()
                and not self.data_manager.carregar_posicoes_externas()):
            self.janela.after(500, self._abrir_primeiro_uso)
        # A GUI já pode consultar os dados locais neste ponto.
        # Binance nunca bloqueia a inicialização do aplicativo.
        self.aba_distribuicao.set_status(
            "Carteira local · aguardando cotações", TEXT_SECONDARY
        )
        if CCXT_AVAILABLE:
            self._initial_refresh_id = self.janela.after(
                1200, self._primeira_consulta_online
            )
        else:
            self.aba_distribuicao.set_status(
                "Offline · cotações indisponíveis", "#e3b341"
            )

    def _abrir_primeiro_uso(self):
        if self._closing:
            return
        if (self._primeiro_uso_janela is not None
                and self._primeiro_uso_janela.winfo_exists()):
            self._primeiro_uso_janela.lift()
            self._primeiro_uso_janela.focus_force()
            return
        janela = ctk.CTkToplevel(self.janela)
        self._primeiro_uso_janela = janela
        janela.title("DCA Monitor · Primeira utilização e dados anteriores")
        largura = max(940, min(1030, janela.winfo_screenwidth() - 70))
        altura = max(650, min(850, janela.winfo_screenheight() - 100))
        janela.geometry(f"{largura}x{altura}+35+35")
        janela.minsize(870, 610)
        JanelaPrimeiroUso(
            janela, self.data_manager,
            on_change=lambda: self._atualizar_abas_seguro(False),
            on_begin_empty=lambda: janela.destroy(),
        ).pack(fill="both", expand=True)
        janela.lift()

    def _abrir_configuracoes(self):
        if self._closing:
            return
        if (self._janela_aplicativo is not None
                and self._janela_aplicativo.winfo_exists()):
            self._janela_aplicativo.lift()
            return
        self._janela_aplicativo = JanelaAplicativo(
            self.janela, self.data_manager,
            ao_restaurar=self._restaurar_fora_app,
            ao_alterar_preferencia=self._alterar_preferencias,
        )
        self._janela_aplicativo.lift()

    def _alterar_preferencias(self, preferencias):
        self._preferences = dict(preferencias)

    def _restaurar_da_bandeja(self):
        if self._closing:
            return
        self.janela.deiconify()
        self.janela.lift()
        self._tray_hidden = False
        self._tray.parar()

    def _restaurar_fora_app(self, manifesto):
        if self._closing:
            return
        caminho=Path(self.data_manager.arquivo_db).resolve()
        if getattr(sys, "frozen", False):
            comando=[sys.executable,"--maintenance-restore",
                     str(manifesto),str(caminho)]
        else:
            comando=[sys.executable,str(Path(__file__).resolve()),
                     "--maintenance-restore",str(manifesto),str(caminho)]
        try:
            subprocess.Popen(
                comando,cwd=str(Path(__file__).resolve().parent),
                close_fds=True,
            )
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("Manutenção não iniciada",str(exc),parent=self.janela)
            return
        self._on_closing(force=True)

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
        ctk.CTkButton(
            status_bar, text="Aplicativo / Configurações",
            command=self._abrir_configuracoes, height=24, width=190,
            fg_color=BG_CARD, text_color=BTC_ORANGE, hover_color=BG_SURFACE,
        ).pack(side="left", padx=(4, 8))
        ctk.CTkButton(
            status_bar, text="Dados iniciais / Importar CSV",
            command=self._abrir_primeiro_uso, height=24, width=180,
            fg_color=BG_CARD, text_color=BTC_ORANGE, hover_color=BG_SURFACE,
        ).pack(side="left", padx=8)

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

    def _primeira_consulta_online(self):
        self._initial_refresh_id = None
        if not self._closing:
            self.atualizar_todas_as_analises()

    def _iniciar_atualizacoes_automaticas(self) -> None:
        self._countdown_ativo = True
        self._countdown       = CONFIG["intervalo_atualizacao"]
        self._after_id        = None
        self._tick_countdown()

    def _tick_countdown(self):
        if not self._countdown_ativo or self._closing:
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
            else:
                self._atualizar_status(
                    "Offline · histórico local disponível", "#e3b341"
                )
                self._reiniciar_countdown()

    def _reiniciar_countdown(self):
        if self._closing or not self._countdown_ativo:
            return
        if self._after_id is not None:
            self.janela.after_cancel(self._after_id)
            self._after_id = None
        self._countdown = CONFIG["intervalo_atualizacao"]
        self._tick_countdown()

    def _agendar_ui(self, acao):
        """Descarta resultados de tarefas encerradas, sem criar janelas ocultas."""
        if self._closing:
            return False
        try:
            self.janela.after(
                0, lambda: None if self._closing else acao()
            )
            return True
        except Exception:
            # Tk pode já ter sido destruído ao finalizar a aplicação.
            return False

    def atualizar_todas_as_analises(self) -> bool:
        """No more than one Binance sync at a time; offline is non-blocking."""
        if self._closing or not self._refresh_lock.acquire(blocking=False):
            return False

        def worker():
            try:
                if self._closing:
                    return
                self._atualizar_status("⟳ Consultando cotações...", CYAN)
                moedas = list(dict.fromkeys(
                    list(MOEDAS_SUPORTADAS)
                    + [str(x["Moeda"]) for x in self.data_manager.carregar_posicoes_iniciais()]
                    + [str(x["Moeda"]) for x in self.data_manager.carregar_posicoes_externas()]
                    + [str(x["Moeda"]) for x in self.data_manager.carregar_operacoes_precisas()]
                ))
                if "USDC" not in moedas:
                    operacoes = self.data_manager.carregar_operacoes_precisas()
                    if any(str(op["Moeda"]).upper() == "USDC" for op in operacoes):
                        moedas.append("USDC")
                sucesso = self.price_manager.atualizar_precos(moedas)
                if self._closing:
                    return
                self._agendar_ui(
                    lambda ok=sucesso: self._atualizar_abas_seguro(ok)
                )
            except Exception as exc:
                logger.exception("Falha não fatal no ciclo de atualização: %s", exc)
                # Uma falha sistêmica inesperada não pode deixar preços
                # antigos, ainda recentes, parecerem confirmados pela Binance.
                invalidar = getattr(self.price_manager, "invalidar_cotacoes", None)
                if callable(invalidar):
                    try:
                        invalidar(list(MOEDAS_SUPORTADAS) + ["USDC"])
                    except Exception:
                        logger.exception("Falha ao invalidar cotações")
                if not self._closing:
                    self._agendar_ui(
                        lambda: self._atualizar_abas_seguro(False)
                    )
            finally:
                self._refresh_lock.release()

        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self._refresh_lock.release()
            logger.exception("Não foi possível iniciar atualização de cotações")
            return False
        return True

    def _atualizar_abas_seguro(self, precos_completos=True):
        if self._closing:
            return
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
        if self._closing:
            return
        def _update():
            if not self._closing:
                self.aba_distribuicao.set_status(mensagem, cor)
        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            self._agendar_ui(_update)

    def _on_closing(self, *, force: bool = False) -> None:
        if self._closing:
            return
        if not force and self._preferences.get("minimizar_para_bandeja", False):
            try:
                self._tray.iniciar()
                self.janela.withdraw()
                self._tray_hidden = True
                return
            except ErroBandeja as exc:
                logger.warning("Bandeja indisponível, janela permanece aberta: %s", exc)
                from tkinter import messagebox
                messagebox.showwarning(
                    "Bandeja indisponível",
                    str(exc)+" Desative a opção ou utilize Sair completamente.",
                    parent=self.janela,
                )
                return
        self._closing = True
        self._tray.parar()
        if (self._janela_aplicativo is not None
                and self._janela_aplicativo.winfo_exists()):
            self._janela_aplicativo.destroy()
        if (self._primeiro_uso_janela is not None
                and self._primeiro_uso_janela.winfo_exists()):
            self._primeiro_uso_janela.destroy()
        self._countdown_ativo = False
        self._stop_updates = True
        for after_id in (self._after_id, self._initial_refresh_id):
            if after_id is not None:
                try:
                    self.janela.after_cancel(after_id)
                except Exception:
                    pass
        self._after_id = None
        self._initial_refresh_id = None
        try:
            self.aba_distribuicao.donut_chart.parar()
        except (AttributeError, RuntimeError):
            pass
        try:
            self.janela.destroy()
        except Exception:
            logger.exception("Falha ao fechar janela")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--maintenance-restore":
        from backend.restore_command import executar_manutencao_restauracao
        status = executar_manutencao_restauracao(
            Path(sys.argv[2]), Path(sys.argv[3])
        )
        sys.exit(0 if status else 1)
    from backend.single_instance import TravaInstancia, OutraInstanciaAberta
    from backend.storage_sqlite import diretorio_dados_padrao
    trava=TravaInstancia(diretorio_dados_padrao())
    try:
        trava.adquirir()
    except OutraInstanciaAberta as exc:
        from tkinter import Tk, messagebox
        aviso=Tk()
        aviso.withdraw()
        try:
            messagebox.showinfo("DCA Monitor já em execução",str(exc),parent=aviso)
        finally:
            aviso.destroy()
        sys.exit(0)

    try:
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
    finally:
        trava.liberar()