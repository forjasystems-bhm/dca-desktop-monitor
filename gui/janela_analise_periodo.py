"""Consulta histórica por ativo e consolidada (somente dados demonstráveis)."""
from datetime import date, timedelta
from decimal import Decimal
import tkinter as tk
from tkinter import ttk, messagebox

import customtkinter as ctk

from backend.finance_analytics import (
    ErroAnaliseFinanceira, calcular_analise_por_periodo
)
from config.tema_cripto import (
    BG_CARD, BG_DEEP, BG_SURFACE, CYAN, NEON_GREEN, NEON_RED,
    TEXT_PRIMARY, TEXT_SECONDARY, BORDER,
)

PERIODOS = [
    "Todo o histórico",
    "Últimos 30 dias",
    "Este mês",
    "Este ano",
    "Personalizado",
]
COLUNAS = (
    ("ativo", "ATIVO", 85),
    ("compras_historicas", "COMPRADO HIST.", 143),
    ("compras_periodo", "COMPRADO PERÍODO", 160),
    ("vendas_periodo", "VENDIDO PERÍODO", 160),
    ("realizado_periodo", "P/L REALIZ. PERÍODO", 169),
    ("realizado_historico", "P/L REALIZ. TOTAL", 170),
    ("custo_aberto", "CUSTO ABERTO", 139),
    ("quantidade", "QTD. FINAL", 125),
)


class JanelaAnalisePeriodo(ctk.CTkFrame):
    """Não estima valorização histórica sem preços naquela data."""

    def __init__(self, parent, data_manager):
        super().__init__(parent, fg_color="transparent")
        self._dados = data_manager
        self._filtro_periodo = ctk.StringVar(value="Todo o histórico")
        self._filtro_ativo = ctk.StringVar(value="Todos os ativos")
        self._indicadores = {}
        self._construir()
        self.after(150, self.atualizar)

    @staticmethod
    def _valor(x: Decimal, casas=2):
        return f"{x:,.{casas}f}"

    @staticmethod
    def _positivo(x: Decimal):
        return NEON_GREEN if x >= 0 else NEON_RED

    def _construir(self):
        titulo = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=9)
        titulo.pack(fill="x", padx=12, pady=(12, 6))
        ctk.CTkLabel(
            titulo, text="ANÁLISE FINANCEIRA POR ATIVO E PERÍODO",
            font=ctk.CTkFont("Segoe UI", 19, "bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", padx=18, pady=(11, 2))
        ctk.CTkLabel(
            titulo,
            text="Compras, vendas, custo em aberto e resultado realizado · USDT"
                 " · Sem estimativas de cotações passadas",
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont("Segoe UI", 12)
        ).pack(anchor="w", padx=18, pady=(0, 12))

        filtros = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=9)
        filtros.pack(fill="x", padx=12, pady=6)
        for i in range(6):
            filtros.grid_columnconfigure(i, weight=1 if i in (0, 1) else 0)
        ctk.CTkLabel(filtros, text="Período", text_color=TEXT_SECONDARY).grid(
            row=0, column=0, padx=9, pady=(10, 0), sticky="w")
        ctk.CTkLabel(filtros, text="Ativo", text_color=TEXT_SECONDARY).grid(
            row=0, column=1, padx=9, pady=(10, 0), sticky="w")
        self._periodos = ctk.CTkComboBox(
            filtros, values=PERIODOS, variable=self._filtro_periodo,
            width=190, command=self._on_periodo)
        self._periodos.grid(row=1, column=0, padx=9, pady=(2, 10), sticky="ew")
        self._ativos = ctk.CTkComboBox(
            filtros, values=["Todos os ativos"], variable=self._filtro_ativo,
            width=170, command=lambda _: self._renderizar())
        self._ativos.grid(row=1, column=1, padx=9, pady=(2, 10), sticky="ew")
        self._inicio = ctk.CTkEntry(filtros, width=122, placeholder_text="AAAA-MM-DD")
        self._inicio.grid(row=1, column=2, padx=6, pady=(2, 10), sticky="ew")
        self._fim = ctk.CTkEntry(filtros, width=122, placeholder_text="AAAA-MM-DD")
        self._fim.grid(row=1, column=3, padx=6, pady=(2, 10), sticky="ew")
        ctk.CTkButton(
            filtros, text="Aplicar", width=90, command=self.atualizar
        ).grid(row=1, column=4, padx=(5, 12), pady=(2, 10))
        self._on_periodo("Todo o histórico", recarregar=False)

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x", padx=12, pady=6)
        metadados = [
            ("compras_periodo", "COMPRADO NO PERÍODO"),
            ("vendas_periodo", "VENDIDO NO PERÍODO"),
            ("realizado_periodo", "RESULTADO REALIZADO NO PERÍODO"),
            ("compras_historicas", "COMPRADO HISTORICAMENTE"),
            ("realizado_historico", "RESULTADO REALIZADO ACUMULADO"),
            ("custo_aberto", "CUSTO DA POSIÇÃO NO FIM"),
        ]
        for idx, (key, titulo_card) in enumerate(metadados):
            card = ctk.CTkFrame(cards, fg_color=BG_CARD, border_color=BORDER,
                                border_width=1, corner_radius=7)
            card.grid(row=idx // 3, column=idx % 3,
                      sticky="nsew", padx=4, pady=4)
            cards.grid_columnconfigure(idx % 3, weight=1)
            ctk.CTkLabel(
                card, text=titulo_card,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=TEXT_SECONDARY
            ).pack(anchor="w", padx=14, pady=(10, 2))
            valor = ctk.CTkLabel(
                card, text="—",
                font=ctk.CTkFont("Segoe UI", 19, "bold"),
                text_color=CYAN
            )
            valor.pack(anchor="w", padx=14, pady=(0, 12))
            self._indicadores[key] = valor

        frame_tabela = ctk.CTkFrame(
            self, fg_color=BG_CARD, border_color=BORDER,
            border_width=1, corner_radius=9)
        frame_tabela.pack(fill="both", expand=True, padx=12, pady=6)
        ctk.CTkLabel(
            frame_tabela, text="EXTRATO CONSOLIDADO POR ATIVO",
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont("Segoe UI", 14, "bold")
        ).pack(anchor="w", padx=14, pady=(12, 8))
        tabela_area = tk.Frame(frame_tabela, bg=BG_CARD)
        tabela_area.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        estilo = ttk.Style()
        estilo.configure(
            "DCAAsset.Treeview",
            background=BG_DEEP, fieldbackground=BG_DEEP,
            foreground=TEXT_PRIMARY, rowheight=32,
            font=("Segoe UI", 10), borderwidth=0,
        )
        estilo.configure(
            "DCAAsset.Treeview.Heading",
            background=BG_SURFACE, foreground=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
        )
        estilo.map("DCAAsset.Treeview", background=[("selected", "#214465")])
        nomes = [c[0] for c in COLUNAS]
        self._arvore = ttk.Treeview(
            tabela_area, columns=nomes, show="headings",
            style="DCAAsset.Treeview")
        for key, title, width in COLUNAS:
            self._arvore.heading(key, text=title)
            self._arvore.column(key, width=width,
                                minwidth=90, stretch=True, anchor="e" if key != "ativo" else "w")
        y = ttk.Scrollbar(tabela_area, orient="vertical", command=self._arvore.yview)
        x = ttk.Scrollbar(tabela_area, orient="horizontal", command=self._arvore.xview)
        self._arvore.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tabela_area.rowconfigure(0, weight=1)
        tabela_area.columnconfigure(0, weight=1)
        self._arvore.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        self._arvore.tag_configure("negativo", foreground=NEON_RED)
        self._arvore.tag_configure("positivo", foreground=NEON_GREEN)

        self._status = ctk.CTkLabel(
            self, text="", text_color=TEXT_SECONDARY,
            anchor="w", font=ctk.CTkFont("Segoe UI", 11),
            wraplength=1200
        )
        self._status.pack(fill="x", padx=22, pady=(2, 10))

    def _on_periodo(self, selecionado, recarregar=True):
        estado = "normal" if selecionado == "Personalizado" else "disabled"
        self._inicio.configure(state=estado)
        self._fim.configure(state=estado)
        if recarregar and estado == "disabled":
            self.atualizar()

    def _datas(self):
        hoje = date.today()
        modo = self._filtro_periodo.get()
        if modo == "Todo o histórico":
            return None, None
        if modo == "Últimos 30 dias":
            return hoje - timedelta(days=29), hoje
        if modo == "Este mês":
            return hoje.replace(day=1), hoje
        if modo == "Este ano":
            return hoje.replace(month=1, day=1), hoje
        if modo == "Personalizado":
            return self._inicio.get().strip() or None, self._fim.get().strip() or None
        raise ErroAnaliseFinanceira(f"Filtro desconhecido: {modo}")

    def atualizar(self):
        try:
            inicio, fim = self._datas()
            self._analise = calcular_analise_por_periodo(
                self._dados.carregar_operacoes(), inicio, fim
            )
            itens = ["Todos os ativos", *self._analise["ativos"].keys()]
            self._ativos.configure(values=itens)
            if self._filtro_ativo.get() not in itens:
                self._filtro_ativo.set("Todos os ativos")
            self._renderizar()
        except Exception as exc:
            for lbl in self._indicadores.values():
                lbl.configure(text="—")
            for item in self._arvore.get_children():
                self._arvore.delete(item)
            self._status.configure(
                text=f"Não é possível apurar o histórico: {exc}",
                text_color=NEON_RED,
            )

    def _renderizar(self):
        if not hasattr(self, "_analise"):
            return
        selecionado = self._filtro_ativo.get()
        todos = self._analise["ativos"]
        exibidos = {selecionado: todos[selecionado]} if selecionado in todos else (
            todos if selecionado == "Todos os ativos" else {}
        )
        registro = (
            self._analise["totais"] if selecionado == "Todos os ativos"
            else exibidos.get(selecionado)
        )
        if registro is None:
            return
        for key, lbl in self._indicadores.items():
            valor = registro[key]
            lbl.configure(
                text=f"{self._valor(valor)} USDT",
                text_color=self._positivo(valor) if key.startswith("realizado_") else CYAN,
            )
        for item in self._arvore.get_children():
            self._arvore.delete(item)
        for nome, s in exibidos.items():
            valores = [
                nome, self._valor(s["compras_historicas"]),
                self._valor(s["compras_periodo"]),
                self._valor(s["vendas_periodo"]),
                self._valor(s["realizado_periodo"]),
                self._valor(s["realizado_historico"]),
                self._valor(s["custo_aberto"]),
                self._valor(s["quantidade"], 8),
            ]
            self._arvore.insert(
                "", "end", values=valores,
                tags=("negativo" if s["realizado_periodo"] < 0 else "positivo",),
            )
        fim = self._analise["fim"]
        data_texto = fim.strftime("%d/%m/%Y") if fim else "última operação"
        msg = (f"Custo da posição apurado até {data_texto}. "
               "Resultados realizados calculados pelo custo médio de todas as compras anteriores. "
               "Sem preços históricos, não há P/L não realizado nem patrimônio retroativo nesta aba. "
               "Valores em USDT; não são lucro fiscal em BRL.")
        if selecionado == "Todos os ativos":
            msg += (
                f" Aportes externos no período: "
                f"{self._valor(self._analise['aportes_periodo_usdt'])} USDT; "
                f"retiradas: {self._valor(self._analise['saques_periodo_usdt'])} USDT."
            )
        self._status.configure(text=msg, text_color=TEXT_SECONDARY)
