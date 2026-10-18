import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

# pyrefly: ignore [missing-import]
import customtkinter as ctk

from widgets.brl_toggle import BRLToggle
from config.fontes import (
    F_STATUS       as _F_STATUS,
    F_BADGE        as _F_BADGE,
    F_SECAO        as _F_SECAO,
    F_CARD_TITLE   as _F_CARD_TITLE,
    F_CARD_SUB     as _F_CARD_SUB,
    F_CARD_VAL     as _F_CARD_VAL,
    F_CARD_DISPLAY as _F_CARD_DISPLAY,
    F_TREE         as _F_TREE,
    F_TREE_HEAD    as _F_TREE_HEAD,
)

BG_DEEP        = "#0a0e1a"
BG_SURFACE     = "#0d1117"
BG_CARD        = "#161b22"
BG_INPUT       = "#1c2128"
BORDER         = "#30363d"
BORDER_ACC     = "#f7931a"
BTC_ORANGE     = "#f7931a"
NEON_GREEN     = "#00ff88"
NEON_RED       = "#ff4d4d"
CYAN           = "#58a6ff"
YELLOW         = "#e3b341"
TEXT_PRIMARY   = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED     = "#484f58"

_CARD_DEFS = [
    ("depositos", "↓  Depósitos USDT", NEON_GREEN),
    ("saques",    "↑  Saques USDT",    NEON_RED),
    ("compras",   "🛒  Compras Cripto", BTC_ORANGE),
    ("vendas",    "💱  Vendas Cripto",  CYAN),
]

_TIPO_MAP = {
    "deposito_usdt": ("Depósito USDT", "deposito", "deposito_alt"),
    "saque_usdt":    ("Saque USDT",    "saque",    "saque_alt"),
    "compra_crypto": ("Compra Cripto", "compra",   "compra_alt"),
    "venda_crypto":  ("Venda Cripto",  "venda",    "venda_alt"),
}

_TREE_COLS = ("Data", "Tipo", "Descrição", "Saldo Atualizado")

_TREE_TAGS = {
    "deposito":     (NEON_GREEN,     BG_CARD),
    "deposito_alt": (NEON_GREEN,     BG_INPUT),
    "saque":        (NEON_RED,       BG_CARD),
    "saque_alt":    (NEON_RED,       BG_INPUT),
    "compra":       (BTC_ORANGE,     BG_CARD),
    "compra_alt":   (BTC_ORANGE,     BG_INPUT),
    "venda":        (CYAN,           BG_CARD),
    "venda_alt":    (CYAN,           BG_INPUT),
    "vazio":        (TEXT_SECONDARY, BG_CARD),
}


class JanelaCaixa(ctk.CTkFrame):
    def __init__(self, parent, data_manager, price_manager, analysis_engine):
        super().__init__(parent, fg_color=BG_DEEP, corner_radius=0)
        self._data_manager  = data_manager
        self._price_manager = price_manager
        self._engine        = analysis_engine
        self.display_currency = "USD"
        self._cards           = {}
        self._build_ui()
        self._bind_tab_select(parent)

    def _bind_tab_select(self, notebook):
        try:
            notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        except Exception:
            pass

    def _on_tab_changed(self, event):
        try:
            selected = event.widget.select()
            if event.widget.nametowidget(selected) is self:
                self.atualizar()
        except Exception:
            pass

    def _build_ui(self):
        self.pack(fill="both", expand=True)
        self._build_hero()
        self._build_accent_divider(self)
        self._build_cards()
        self._build_table()
        self._build_footer()

    def _build_hero(self):
        hero = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=0)
        hero.pack(fill="x")

        self._accent_bar(hero)

        inner = ctk.CTkFrame(hero, fg_color=BG_SURFACE, corner_radius=0)
        inner.pack(fill="x", padx=30, pady=(18, 16))

        self._build_hero_left(inner)
        self._build_hero_right(inner)

    def _build_hero_left(self, parent):
        left = ctk.CTkFrame(parent, fg_color=BG_SURFACE, corner_radius=0)
        left.pack(side=tk.LEFT, fill="both", expand=True)

        ctk.CTkLabel(
            left,
            text="CAIXA  ·  USDT",
            font=_F_BADGE,
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w")

        self.lbl_saldo = ctk.CTkLabel(
            left,
            text="Carregando...",
            font=_F_CARD_DISPLAY,
            text_color=NEON_GREEN,
            anchor="w",
        )
        self.lbl_saldo.pack(anchor="w", pady=(4, 0))
        self.lbl_saldo_usdc = ctk.CTkLabel(
            left, text="USDC: carregando...", font=_F_CARD_VAL,
            text_color=CYAN, anchor="w",
        )
        self.lbl_saldo_usdc.pack(anchor="w", pady=(5, 0))
        self.lbl_fluxo_usdc = ctk.CTkLabel(
            left, text="USDC independente: sem conversão 1:1",
            font=_F_STATUS, text_color=TEXT_SECONDARY, anchor="w"
        )
        self.lbl_fluxo_usdc.pack(anchor="w", pady=(2, 0))

    def _build_hero_right(self, parent):
        right = ctk.CTkFrame(parent, fg_color=BG_SURFACE, corner_radius=0)
        right.pack(side=tk.RIGHT, anchor="center")

        self._brl_toggle = BRLToggle(
            right,
            price_manager=self._price_manager,
            on_change=self._on_currency_change,
        )
        self._brl_toggle.pack(anchor="e")

        self.lbl_status = ctk.CTkLabel(
            right,
            text="",
            font=_F_STATUS,
            text_color=TEXT_SECONDARY,
            anchor="e",
        )
        self.lbl_status.pack(anchor="e", pady=(8, 0))

    def _on_currency_change(self, currency: str):
        self.display_currency = currency
        self.atualizar()

    def _build_cards(self):
        frame = ctk.CTkFrame(self, fg_color=BG_DEEP, corner_radius=0)
        frame.pack(fill="x", padx=30, pady=(20, 6))

        for key, label, cor in _CARD_DEFS:
            card = self._make_card(frame, label, "--", cor)
            card.pack(side=tk.LEFT, padx=(0, 12), fill="x", expand=True)
            self._cards[key] = card

    def _make_card(self, parent, titulo, valor, cor):
        frame = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            corner_radius=8,
            border_width=1,
            border_color=cor,
        )
        ctk.CTkLabel(
            frame,
            text=titulo,
            font=_F_CARD_TITLE,
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w", padx=18, pady=(14, 2))

        lbl = ctk.CTkLabel(
            frame,
            text=valor,
            font=_F_CARD_VAL,
            text_color=cor,
            anchor="w",
        )
        lbl.pack(anchor="w", padx=18, pady=(0, 14))
        frame._value_label = lbl
        return frame

    def _set_card(self, key, valor):
        try:
            self._cards[key]._value_label.configure(text=valor)
        except Exception:
            pass

    def _build_table(self):
        outer = ctk.CTkFrame(self, fg_color=BG_DEEP, corner_radius=0)
        outer.pack(fill="both", expand=True, padx=30, pady=(4, 10))

        self._build_section_header(outer)
        self._build_treeview(outer)

    def _build_section_header(self, parent):
        header = ctk.CTkFrame(parent, fg_color=BG_DEEP, corner_radius=0)
        header.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            header,
            text="EXTRATO DE MOVIMENTAÇÕES",
            font=_F_SECAO,
            text_color=TEXT_SECONDARY,
        ).pack(side=tk.LEFT)

        ctk.CTkFrame(header, fg_color=BORDER, height=1, corner_radius=0).pack(
            side=tk.LEFT, fill="x", expand=True, padx=(14, 0)
        )

    def _build_treeview(self, parent):
        border_frame = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        border_frame.pack(fill="both", expand=True)

        container = tk.Frame(border_frame, bg=BG_CARD)
        container.pack(fill="both", expand=True)

        self._configure_tree_style()

        self.tree = ttk.Treeview(
            container,
            columns=_TREE_COLS,
            show="headings",
            selectmode="none",
            style="Caixa.Treeview",
        )
        self._configure_tree_columns()
        self._configure_tree_tags()

        sb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill="y")
        self.tree.pack(fill="both", expand=True)

    def _configure_tree_style(self):
        style = ttk.Style()
        style.configure(
            "Caixa.Treeview",
            background=BG_CARD,
            fieldbackground=BG_CARD,
            foreground=TEXT_PRIMARY,
            rowheight=36,
            borderwidth=0,
            relief="flat",
            font=_F_TREE,
        )
        style.configure(
            "Caixa.Treeview.Heading",
            background=BG_INPUT,
            foreground=TEXT_SECONDARY,
            font=_F_TREE_HEAD,
            relief="flat",
            borderwidth=0,
        )
        style.map("Caixa.Treeview", background=[("selected", BTC_ORANGE)])
        style.layout("Caixa.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    def _configure_tree_columns(self):
        headings = {
            "Data":             ("DATA",             "center", 165, False),
            "Tipo":             ("TIPO",             "center", 155, False),
            "Descrição":        ("DESCRIÇÃO",        "w",      400, True),
            "Saldo Atualizado": ("SALDO ATUALIZADO", "center", 185, False),
        }
        for col, (text, anchor, width, stretch) in headings.items():
            self.tree.heading(col, text=text, anchor=anchor if anchor != "w" else "w")
            self.tree.column(col, width=width, anchor=anchor, stretch=stretch)

    def _configure_tree_tags(self):
        for tag, (fg, bg) in _TREE_TAGS.items():
            self.tree.tag_configure(tag, foreground=fg, background=bg)

    def _build_footer(self):
        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0)
        sep.pack(fill="x", side=tk.BOTTOM)
        sep.pack_propagate(False)

        ctk.CTkLabel(
            self,
            text="Atualização automática ao acessar a aba",
            font=_F_STATUS,
            text_color=TEXT_MUTED,
        ).pack(side=tk.BOTTOM, pady=6)

    def _accent_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=BTC_ORANGE, height=2, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

    def _build_accent_divider(self, parent):
        self._accent_bar(parent)

    def _fmt_val(self, val):
        if self.display_currency == "BRL":
            taxa = (self._price_manager.taxa_brl_para_avaliacao()
                    if hasattr(self._price_manager, "taxa_brl_para_avaliacao")
                    else self._price_manager.preco_brl)
            if not taxa or taxa <= 0:
                return "BRL indisponível"
            return f"R$ {val * taxa:,.2f}"
        return f"{val:,.2f} USDT"

    def atualizar(self):
        self.lbl_status.configure(text="⟳  calculando...", text_color=CYAN)
        for row in self.tree.get_children():
            self.tree.delete(row)
        threading.Thread(target=self._worker_atualizar, daemon=True).start()

    def _worker_atualizar(self):
        try:
            ops  = self._data_manager.carregar_operacoes()
            info = self._engine.calcular_saldo_usdt(ops)
            from backend.stablecoin_ledger import saldos_stablecoins
            stable = saldos_stablecoins(ops)
            stable["origem_usdc_legada"] = (
                self._data_manager._store.quantidade_usdc_de_origem_legada()
                if hasattr(self._data_manager, "_store") else 0
            )
            self.after(0, lambda: self._atualizar_ui(info, stable))
        except Exception as e:
            self.after(0, lambda: self.lbl_status.configure(text="✕ erro", text_color=NEON_RED))
            self.after(0, lambda: messagebox.showerror("Erro", f"Erro ao carregar saldo:\n{e}"))

    def _atualizar_ui(self, info, stable=None):
        if stable is not None:
            usdc = stable["saldos"]["USDC"]
            entrou = stable["entradas"]["USDC"]
            saiu = stable["saidas"]["USDC"]
            self.lbl_saldo_usdc.configure(
                text=f"USDC: {usdc:,.2f} unidades — saldo independente",
                text_color=NEON_GREEN if usdc >= 0 else NEON_RED,
            )
            legado = stable.get("origem_usdc_legada", 0)
            aviso = (
                f"  |  ⚠ {legado} operações USDC antigas: "
                "confirmar origem (transferência ou troca)"
                if legado else ""
            )
            self.lbl_fluxo_usdc.configure(
                text=f"USDC recebido: {entrou:,.2f}  |  enviado: {saiu:,.2f}  "
                     "· Não convertido em USDT" + aviso,
                text_color=YELLOW if legado else TEXT_SECONDARY,
            )
        s_atual = info["saldo_atual"]
        hist    = info["historico"]
        agora   = datetime.now().strftime("%d/%m  %H:%M:%S")

        cor_saldo = NEON_GREEN if s_atual >= 0 else NEON_RED
        self.lbl_saldo.configure(text=self._fmt_val(s_atual), text_color=cor_saldo)
        self.lbl_status.configure(text=f"✓ atualizado  {agora}", text_color=TEXT_SECONDARY)

        totais = {
            "deposito_usdt": 0,
            "saque_usdt":    0,
            "compra_crypto": 0,
            "venda_crypto":  0,
        }
        if hist:
            for m in hist:
                tipo = m.get("tipo")
                if tipo in totais:
                    totais[tipo] += m["valor"]

        self._set_card("depositos", self._fmt_val(totais["deposito_usdt"]))
        self._set_card("saques",    self._fmt_val(totais["saque_usdt"]))
        self._set_card("compras",   self._fmt_val(totais["compra_crypto"]))
        self._set_card("vendas",    self._fmt_val(totais["venda_crypto"]))

        if not hist:
            self.tree.insert("", "end",
                             values=("—", "—", "Nenhuma movimentação registrada.", "—"),
                             tags=("vazio",))
            return

        for idx, mov in enumerate(reversed(hist)):
            d                        = datetime.strptime(mov["data"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y  %H:%M")
            tipo                     = mov.get("tipo", "")
            label, tag_par, tag_imp  = _TIPO_MAP.get(tipo, (tipo, "deposito", "deposito_alt"))
            tag                      = tag_par if idx % 2 == 0 else tag_imp
            self.tree.insert(
                "", "end",
                values=(d, label, mov["descricao"], self._fmt_val(mov["saldo_apos"])),
                tags=(tag,),
            )