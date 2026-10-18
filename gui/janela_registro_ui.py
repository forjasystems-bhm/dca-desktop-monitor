# pyrefly: ignore [missing-import]
import customtkinter as ctk
from typing import Any, Callable, List, Optional

from config.tema_cripto import (
    BG_DEEP, BG_SURFACE, BG_CARD, BG_INPUT,
    BORDER, BORDER_ACC,
    BTC_ORANGE, NEON_GREEN, NEON_RED, CYAN, YELLOW,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)
from config.fontes import (
    F_BADGE      as _F_BADGE,
    F_SECAO      as _F_SECAO,
    F_CARD_TITLE as _F_CARD_TITLE,
    F_CARD_SUB   as _F_CARD_SUB,
    F_CARD_VAL   as _F_CARD_VAL,
    F_TREE       as _F_TREE,
    F_BADGE      as _FONT,
    F_TREE_HEAD  as _FONT_HEAD,
)
from widgets.combo_custom import ComboCustom

ctk.set_appearance_mode("dark")
_SEL_BG       = "#1A3A5C"
_SEL_GLOW     = "#4A9EFF"
_HOVER_BG     = "#1E2D3D"


class _SectionBar(ctk.CTkFrame):
    def __init__(self, parent, text: str, **kw):
        super().__init__(parent, fg_color=BG_INPUT, corner_radius=4,
                         border_width=0, height=32, **kw)
        self.pack_propagate(False)
        ctk.CTkFrame(self, fg_color=BTC_ORANGE, width=3,
                     corner_radius=0).pack(side="left", fill="y")
        ctk.CTkLabel(self, text=f"  {text}", font=_F_SECAO,
                     text_color=BTC_ORANGE, anchor="w").pack(
            side="left", fill="both", expand=True, padx=8)


class JanelaRegistroUI(ctk.CTkFrame):

    def __init__(
        self,
        parent: Any,
        moedas_suportadas: List[str],
        on_moeda_changed: Callable,
        on_tipo_changed: Callable,
        on_calcular: Callable,
        on_salvar: Callable,
    ):
        super().__init__(parent, fg_color=BG_SURFACE, corner_radius=0)
        self._moedas           = moedas_suportadas
        self._on_moeda_changed = on_moeda_changed
        self._on_tipo_changed  = on_tipo_changed
        self._on_calcular      = on_calcular
        self._on_salvar        = on_salvar

        self.pack(fill="both", expand=True)
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=0, column=0)

        self._build_card(center)
        self._build_footer(center)

    def _build_card(self, parent: ctk.CTkFrame):
        outer = ctk.CTkFrame(parent, fg_color=BG_CARD,
                             border_color=BORDER, border_width=1,
                             corner_radius=8)
        outer.pack(pady=30, padx=40)

        title_strip = ctk.CTkFrame(outer, fg_color=BG_INPUT,
                                   corner_radius=0, height=46,
                                   border_color=BTC_ORANGE, border_width=2)
        title_strip.pack(fill="x")
        title_strip.pack_propagate(False)

        ctk.CTkFrame(title_strip, fg_color=BTC_ORANGE, width=5,
                     corner_radius=0).pack(side="left", fill="y")
        ctk.CTkLabel(title_strip, text="  REGISTRAR OPERACAO",
                     font=_F_CARD_VAL, text_color=BTC_ORANGE,
                     anchor="w").pack(side="left", padx=10,
                                      fill="both", expand=True)

        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(padx=36, pady=24)

        self._build_form(inner)

    def _build_form(self, p: ctk.CTkFrame):
        p.columnconfigure(0, minsize=130)
        p.columnconfigure(1, minsize=225)
        p.columnconfigure(2, minsize=185)

        def sep(row):
            ctk.CTkFrame(p, fg_color=BORDER, height=1, corner_radius=0).grid(
                row=row, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        def section(row, text):
            _SectionBar(p, text).grid(
                row=row, column=0, columnspan=3, sticky="ew", pady=(4, 6))

        def label(row, text):
            lbl = ctk.CTkLabel(p, text=text, font=_F_BADGE,
                               text_color=TEXT_SECONDARY,
                               anchor="e", width=128)
            lbl.grid(row=row, column=0, sticky="e", pady=7, padx=(0, 14))
            return lbl

        def entry(row):
            e = ctk.CTkEntry(p, font=_F_TREE, height=36, width=223,
                             fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
                             border_color=BORDER, border_width=1,
                             corner_radius=5,
                             placeholder_text_color=TEXT_MUTED)
            e.grid(row=row, column=1, sticky="w", pady=7)
            return e

        def combo(row):
            c = ComboCustom(
                p,
                width=223,
                height=36,
                fg_color=BG_INPUT,
                text_color=TEXT_PRIMARY,
                border_color=BORDER,
                button_color=BTC_ORANGE,
                button_hover_color="#e8820f",
                dropdown_fg_color=BG_CARD,
                dropdown_hover_color=_HOVER_BG,
            )
            c.grid(row=row, column=1, sticky="w", pady=7)
            return c

        def badge(row, color=TEXT_SECONDARY):
            lbl = ctk.CTkLabel(p, text="", font=_F_BADGE,
                               text_color=color, anchor="w", width=175)
            lbl.grid(row=row, column=2, sticky="w", padx=(14, 0), pady=7)
            return lbl

        section(0, "ATIVO")
        label(1, "MOEDA")
        self._combo_moeda = combo(1)
        self._combo_moeda.configure(values=self._moedas,
                                    command=self._on_moeda_changed)
        self._lbl_preco_atual = badge(1, CYAN)

        sep(2)
        section(3, "OPERACAO")
        label(4, "TIPO")
        self._combo_tipo = combo(4)
        self._combo_tipo.configure(state="disabled",
                                   command=self._on_tipo_changed)
        self._lbl_saldo = badge(4, NEON_GREEN)

        sep(5)
        section(6, "VALORES")

        self._lbl_preco_titulo = label(7, "PRECO UNIT.")
        self._entry_preco = entry(7)
        self._entry_preco.configure(state="disabled")
        self._entry_preco.bind("<KeyRelease>", self._on_calcular)

        self._lbl_valor_titulo = label(8, "VALOR (USDT)")
        self._entry_valor = entry(8)
        self._entry_valor.configure(state="disabled")
        self._entry_valor.bind("<KeyRelease>", self._on_calcular)
        self._lbl_quantidade = badge(8, TEXT_SECONDARY)

        label(9, "TAXA CORRET. USDT")
        self._entry_taxa_corretagem = entry(9)
        self._entry_taxa_corretagem.configure(state="disabled")
        self._lbl_taxa_info = badge(9, TEXT_SECONDARY)
        self._lbl_taxa_info.configure(text="Opcional · deixe vazio se desconhecida")

        self._lbl_ajuda = ctk.CTkLabel(p, text="", font=_F_CARD_SUB,
                                       text_color=CYAN, anchor="w",
                                       width=360, justify="left")
        self._lbl_ajuda.grid(row=10, column=1, columnspan=2,
                             sticky="w", pady=(4, 0))

        self._lbl_erro_saldo = ctk.CTkLabel(p, text="", font=_F_CARD_SUB,
                                            text_color=NEON_RED, anchor="w",
                                            width=360, justify="left")
        self._lbl_erro_saldo.grid(row=11, column=1, columnspan=2,
                                  sticky="w", pady=(2, 4))

    def _build_footer(self, parent: ctk.CTkFrame):
        ctk.CTkFrame(parent, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", padx=40, pady=(0, 20))

        footer = ctk.CTkFrame(parent, fg_color="transparent")
        footer.pack(pady=(0, 30))

        self._btn_salvar = ctk.CTkButton(
            footer,
            text="CONFIRMAR OPERACAO",
            font=_FONT,
            height=46,
            width=290,
            fg_color=BTC_ORANGE,
            hover_color="#e8820f",
            text_color=BG_DEEP,
            corner_radius=6,
            state="disabled",
            cursor="hand2",
            command=self._on_salvar,
        )
        self._btn_salvar.pack()

        self._lbl_status_btn = ctk.CTkLabel(
            footer,
            text="preencha todos os campos",
            font=_F_CARD_SUB,
            text_color=TEXT_MUTED,
        )
        self._lbl_status_btn.pack(pady=(8, 0))

    def get_moeda(self) -> str:
        return self._combo_moeda.get()

    def get_tipo_label(self) -> str:
        return self._combo_tipo.get()

    def get_valor_str(self) -> str:
        return self._entry_valor.get()

    def get_taxa_corretagem_str(self) -> str:
        return self._entry_taxa_corretagem.get().strip()

    def set_taxa_corretagem_state(self, state: str) -> None:
        self._entry_taxa_corretagem.configure(state=state)

    def get_preco_str(self) -> str:
        return self._entry_preco.get()

    def set_combo_tipo_values(self, values: list, state: str = "readonly") -> None:
        self._combo_tipo.configure(values=values, state=state)

    def set_combo_tipo_state(self, state: str) -> None:
        self._combo_tipo.configure(state=state)

    def set_combo_tipo_value(self, value: str) -> None:
        self._combo_tipo.set(value)

    def set_combo_moedas(self, moedas: list) -> None:
        self._moedas = moedas
        self._combo_moeda.configure(values=moedas)

    def set_combo_moeda_value(self, value: str) -> None:
        self._combo_moeda.set(value)

    def set_entry_preco(self, value: str, state_before: str = "normal",
                        state_after: Optional[str] = None) -> None:
        self._entry_preco.configure(state="normal")
        self._entry_preco.delete(0, "end")
        if value:
            self._entry_preco.insert(0, value)
        if state_after:
            self._entry_preco.configure(state=state_after)

    def set_entry_valor(self, value: str) -> None:
        self._entry_valor.configure(state="normal")
        self._entry_valor.delete(0, "end")
        if value:
            self._entry_valor.insert(0, value)

    def set_entry_preco_state(self, state: str) -> None:
        self._entry_preco.configure(state=state)

    def set_entry_valor_state(self, state: str) -> None:
        self._entry_valor.configure(state=state)

    def set_label_preco_atual(self, text: str) -> None:
        self._lbl_preco_atual.configure(text=text)

    def set_label_preco_titulo(self, text: str) -> None:
        self._lbl_preco_titulo.configure(text=text)

    def set_label_valor_titulo(self, text: str) -> None:
        self._lbl_valor_titulo.configure(text=text)

    def set_label_saldo(self, text: str, style: str = "Saldo.TLabel") -> None:
        cor = NEON_GREEN if "Saldo" in style else TEXT_SECONDARY
        self._lbl_saldo.configure(text=text, text_color=cor)

    def set_label_quantidade(self, text: str, style: str = "Info.TLabel") -> None:
        cor_map = {
            "Info.TLabel":     TEXT_SECONDARY,
            "Travado.TLabel":  YELLOW,
            "Erro.TLabel":     NEON_RED,
            "Saldo.TLabel":    NEON_GREEN,
            "Destaque.TLabel": CYAN,
        }
        self._lbl_quantidade.configure(
            text=text, text_color=cor_map.get(style, TEXT_SECONDARY))

    def set_label_ajuda(self, text: str) -> None:
        self._lbl_ajuda.configure(text=text)

    def set_label_erro_saldo(self, text: str) -> None:
        self._lbl_erro_saldo.configure(text=text)

    def set_btn_salvar_state(self, state: str) -> None:
        self._btn_salvar.configure(state=state)
        if state == "normal":
            self._lbl_status_btn.configure(
                text="pronto para registrar  ✓", text_color=NEON_GREEN)
        else:
            self._lbl_status_btn.configure(
                text="preencha todos os campos", text_color=TEXT_MUTED)

    def limpar_campos(self) -> None:
        self._combo_moeda.set("")
        self._combo_tipo.set("")
        self._combo_tipo.configure(state="disabled")

        self._entry_preco.configure(state="normal")
        self._entry_preco.delete(0, "end")
        self._entry_preco.configure(state="disabled")

        self._entry_valor.configure(state="normal")
        self._entry_valor.delete(0, "end")
        self._entry_valor.configure(state="disabled")

        self._entry_taxa_corretagem.configure(state="normal")
        self._entry_taxa_corretagem.delete(0, "end")
        self._entry_taxa_corretagem.configure(state="disabled")
        self._lbl_quantidade.configure(text="", text_color=TEXT_SECONDARY)
        self._lbl_preco_atual.configure(text="")
        self._lbl_saldo.configure(text="", text_color=NEON_GREEN)
        self._lbl_ajuda.configure(text="")
        self._lbl_erro_saldo.configure(text="")
        self._lbl_preco_titulo.configure(text="PRECO UNIT.")
        self._lbl_valor_titulo.configure(text="VALOR (USDT)")
        self._btn_salvar.configure(state="disabled")
        self._lbl_status_btn.configure(
            text="preencha todos os campos", text_color=TEXT_MUTED)

    def atualizar_lista_moedas(self, novas_moedas: list) -> str:
        moeda_atual = self._combo_moeda.get()
        self.set_combo_moedas(novas_moedas)
        return moeda_atual