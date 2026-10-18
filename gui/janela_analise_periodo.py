"""Consulta histórica por ativo e consolidada (somente dados demonstráveis)."""
from datetime import date, datetime, timedelta, timezone
import threading
from decimal import Decimal
import tkinter as tk
from tkinter import ttk, messagebox

import customtkinter as ctk

from backend.finance_analytics import (
    ErroAnaliseFinanceira, calcular_analise_por_periodo
)
from backend.historical_valuation import patrimonio_historico_na_data
from backend.historical_prices import buscar_e_persistir_fechamentos, validar_data_encerrada
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
        self._busca_historica_ativa = False
        self._ultimo_historico = None
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
                 " · Fechamentos passados apenas quando registrados no banco",
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
        self._montar_avaliacao_historica()

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

    def _montar_avaliacao_historica(self):
        """Área histórica independente dos valores de mercado atuais."""
        frame = ctk.CTkFrame(self, fg_color=BG_CARD, border_color=BORDER,
                             border_width=1, corner_radius=8)
        frame.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(
            frame, text="PATRIMÔNIO NA DATA (FECHAMENTO UTC · USDT)",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(9, 4))
        self._data_cotacao = ctk.CTkEntry(
            frame, placeholder_text="AAAA-MM-DD", width=125
        )
        self._data_cotacao.grid(row=1, column=0, padx=(14, 8), pady=6, sticky="w")
        self._data_cotacao.insert(
            0, (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        )
        ctk.CTkButton(
            frame, text="Avaliar (somente banco)", width=190,
            command=self._apurar_valor_historico
        ).grid(row=1, column=1, padx=5, pady=6, sticky="w")
        self._btn_buscar_cotacoes = ctk.CTkButton(
            frame, text="Buscar fechamentos na Binance", width=220,
            fg_color="#2f4c69", command=self._buscar_cotacoes_historicas
        )
        self._btn_buscar_cotacoes.grid(
            row=1, column=2, padx=6, pady=6, sticky="w"
        )
        self._btn_detalhar_historico = ctk.CTkButton(
            frame, text="Detalhar por ativo", width=150,
            state="disabled", command=self._detalhar_ativos_na_data
        )
        self._btn_detalhar_historico.grid(
            row=1, column=3, padx=(6, 12), pady=6, sticky="w"
        )
        self._historico_valores = ctk.CTkLabel(
            frame, text="Selecione uma data encerrada para consultar o SQLite.",
            font=ctk.CTkFont("Segoe UI", 12), text_color=TEXT_SECONDARY,
            justify="left", anchor="w",
        )
        self._historico_valores.grid(
            row=2, column=0, columnspan=3, sticky="ew",
            padx=14, pady=(3, 10)
        )
        frame.grid_columnconfigure(2, weight=1)

    def _dia_selecionado(self):
        from backend.historical_prices import ErroCotacaoHistorica
        valor = self._data_cotacao.get().strip()
        try:
            dia = date.fromisoformat(valor)
        except ValueError as exc:
            raise ErroCotacaoHistorica(
                "Informe data no formato AAAA-MM-DD."
            ) from exc
        validar_data_encerrada(dia)
        return dia

    def _apurar_valor_historico(self):
        try:
            dia = self._dia_selecionado()
            resultado = patrimonio_historico_na_data(
                self._dados._store, dia
            )
            self._ultimo_historico = resultado
            self._btn_detalhar_historico.configure(state="normal")
            if resultado["completo"]:
                valor = f"{self._valor(resultado['patrimonio_total'])} USDT"
                total = f"{self._valor(resultado['resultado_total'])} USDT"
                texto = (
                    f"Patrimônio em {dia}: {valor}  |  "
                    f"P/L realizado acumulado: "
                    f"{self._valor(resultado['lucro_realizado'])} USDT  |  "
                    f"P/L não realizado: "
                    f"{self._valor(resultado['lucro_nao_realizado'])} USDT  |  "
                    f"P/L total: {total}  |  Caixa: "
                    f"{self._valor(resultado['caixa_usdt'])} USDT"
                )
                cor = NEON_GREEN
            else:
                texto = (
                    f"Patrimônio em {dia}: INDISPONÍVEL — "
                    + "; ".join(resultado["alertas"])
                    + f" | P/L realizado (operações): "
                    f"{self._valor(resultado['lucro_realizado'])} USDT."
                )
                cor = NEON_RED
            self._historico_valores.configure(text=texto, text_color=cor)
            return resultado
        except Exception as exc:
            self._ultimo_historico = None
            self._btn_detalhar_historico.configure(state="disabled")
            self._historico_valores.configure(
                text=f"Não é possível apurar: {exc}", text_color=NEON_RED
            )
            return None

    def _detalhar_ativos_na_data(self):
        """Exibe valores históricos INDIVIDUAIS, sem recorrer ao preço atual."""
        resultado = self._ultimo_historico
        if resultado is None:
            return
        janela = ctk.CTkToplevel(self)
        janela.title(f"DCA — Ativos em {resultado['data_utc']} (USDT)")
        janela.geometry("1160x420")
        janela.minsize(850, 300)
        ctk.CTkLabel(
            janela,
            text=f"PATRIMÔNIO HISTÓRICO POR ATIVO · {resultado['data_utc']} · USDT",
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", padx=20, pady=(17, 6))
        ctk.CTkLabel(
            janela,
            text="Cotação = fechamento UTC do dia gravado no SQLite. "
                 "Sem cotação, posição aberta fica INDISPONÍVEL; "
                 "posição encerrada preserva o resultado realizado.",
            font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_SECONDARY
        ).pack(anchor="w", padx=20, pady=(0, 10))
        cols = ("ativo", "qtd", "custo", "cotacao", "mercado", "realizado", "nao_realizado")
        frm = tk.Frame(janela, bg=BG_CARD)
        frm.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        table = ttk.Treeview(frm, columns=cols, show="headings",
                             style="DCAAsset.Treeview")
        titles = ("Ativo", "Quantidade", "Custo aberto",
                  "Preço UTC/USDT", "Valor histórico", "P/L realizado", "P/L aberto")
        for idx, (key, title) in enumerate(zip(cols, titles)):
            table.heading(key, text=title)
            table.column(key, width=160 if idx != 0 else 100,
                         anchor="w" if idx == 0 else "e", minwidth=90)
        for ativo, p in resultado["ativos"].items():
            cot = p["cotacao"]
            preco = (
                self._valor(cot["preco"], 6) if cot else
                ("—" if p["quantidade"] == 0 else "INDISPONÍVEL")
            )
            def fmt(valor, casas=2):
                return self._valor(valor, casas) if valor is not None else "INDISPONÍVEL"
            table.insert("", "end", values=(
                ativo, fmt(p["quantidade"], 8), fmt(p["custo_aberto"]),
                preco, fmt(p["valor_mercado"]), fmt(p["lucro_realizado"]),
                fmt(p["nao_realizado"])
            ))
        sx = ttk.Scrollbar(frm, orient="horizontal", command=table.xview)
        sy = ttk.Scrollbar(frm, orient="vertical", command=table.yview)
        table.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        frm.grid_rowconfigure(0, weight=1)
        frm.grid_columnconfigure(0, weight=1)
        table.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self._detalhes_janela = janela
        self._detalhes_tabela = table
        return janela

    def _buscar_cotacoes_historicas(self):
        if self._busca_historica_ativa:
            return
        try:
            dia = self._dia_selecionado()
            model = calcular_analise_por_periodo(
                self._dados.carregar_operacoes_precisas(), fim=dia
            )
            ativos_abertos = [
                nome for nome, valores in model["ativos"].items()
                if valores["quantidade"] > 0
            ]
            if not ativos_abertos:
                self._apurar_valor_historico()
                return
        except Exception as exc:
            self._historico_valores.configure(
                text=f"Não é possível consultar: {exc}", text_color=NEON_RED
            )
            return

        self._busca_historica_ativa = True
        self._btn_buscar_cotacoes.configure(state="disabled")
        self._historico_valores.configure(
            text="Consultando apenas candles diários históricos. "
                 "Nenhum preço atual será utilizado.",
            text_color=CYAN,
        )

        def worker():
            try:
                import ccxt
                exchange = ccxt.binance({
                    "enableRateLimit": True, "timeout": 12000
                })
                count = buscar_e_persistir_fechamentos(
                    self._dados._store, exchange, dia, ativos_abertos
                )
                erro = None
            except Exception as exc:
                count, erro = 0, str(exc)

            def concluir():
                self._busca_historica_ativa = False
                if not self.winfo_exists():
                    return
                self._btn_buscar_cotacoes.configure(state="normal")
                if erro:
                    self._historico_valores.configure(
                        text=f"Cotações não importadas: {erro}",
                        text_color=NEON_RED
                    )
                else:
                    self._apurar_valor_historico()
            try:
                self.after(0, concluir)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

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
                (self._dados.carregar_operacoes_precisas()
                 if hasattr(self._dados, "carregar_operacoes_precisas")
                 else self._dados.carregar_operacoes()), inicio, fim
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
               "Avalie o patrimônio histórico separadamente pelas cotações fechadas registradas no SQLite. "
               "Valores em USDT; não são lucro fiscal em BRL.")
        if selecionado == "Todos os ativos":
            msg += (
                f" Aportes externos no período: "
                f"{self._valor(self._analise['aportes_periodo_usdt'])} USDT; "
                f"retiradas: {self._valor(self._analise['saques_periodo_usdt'])} USDT."
            )
        self._status.configure(text=msg, text_color=TEXT_SECONDARY)
