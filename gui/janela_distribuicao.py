import tkinter as tk
from tkinter import messagebox
import threading

# pyrefly: ignore [missing-import]
import customtkinter as ctk

from config.donut_chart import DonutChart
from config.cards_lateral import PainelCards
from config.carregar_json import _carregar_cores_moedas
from config.conexao_badge import ConexaoBadge
from widgets.brl_toggle import BRLToggle
from config.tema_cripto import (
    BG_DEEP, BG_CARD, NEON_GREEN, NEON_RED, CYAN, YELLOW,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER,
)
from config.fontes import (
    F_SECAO    as _F_SECAO,
    F_TREE     as _F_TREE,
    F_BADGE    as _FONT,
    F_TREE_HEAD as _FONT_HEAD,
)

_SEL_BG   = "#1A3A5C"
_SEL_GLOW = "#4A9EFF"
_HOVER_BG = "#1E2D3D"

_CORES_ATIVOS   = ["#f7931a", "#58a6ff", "#00ff88", "#e3b341", "#a371f7",
                   "#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4", "#ff9ff3"]
_DIVERSIFICACAO = [(7, "🟢 Excelente", NEON_GREEN), (4, "🟡 Moderada", YELLOW),
                   (2, "🟠 Baixa", "#e3b341"),       (0, "🔴 Mínima",  NEON_RED)]

_DET_COLS = (
    "Ativo", "Posição", "Preço Médio", "Preço Mercado",
    "Custo Posição", "Valor Atual",
    "P/L N. Realizado", "P/L Realizado", "P/L Total", "Ganho %",
)
_N = len(_DET_COLS)

_ALINHAMENTOS = ["w", "w", "w", "w", "w", "w", "w", "w", "w", "w"]


class JanelaDistribuicao(ctk.CTkFrame):

    def __init__(self, parent, data_manager, price_manager, analysis_engine, on_change=None):
        super().__init__(parent, fg_color="transparent")

        self._data_manager  = data_manager
        self._price_manager = price_manager
        self._engine        = analysis_engine

        self._usdt_pl_brl     = {}
        self.display_currency = "USD"
        self.brl_toggle_var   = tk.BooleanVar(value=False)

        self._det_rows      = []
        self._det_sel       = None
        self._det_hover     = None
        self._det_scroll_fn = None

        self._build_ui()

    def set_estado(self, estado: str):
        self._badge.set_estado(estado)

    def set_status(self, mensagem: str, cor: str = TEXT_SECONDARY):
        self._badge.set_status(mensagem, cor)

    def set_countdown(self, segundos: int):
        self._badge.set_countdown(segundos)

    def _build_ui(self):
        self.pack(fill="both", expand=True, padx=10, pady=(3, 10))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(2, 2))

        self._badge = ConexaoBadge(toolbar)
        self._badge.pack(side=tk.LEFT, padx=(6, 5), pady=2)

        self._brl_toggle = BRLToggle(
            toolbar,
            price_manager=self._price_manager,
            on_change=self._on_currency_change,
        )
        self._brl_toggle.pack(side=tk.RIGHT, padx=(5, 6), pady=2)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=0, minsize=350)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        def _secao(parent, titulo: str, center: bool = False):
            outer = ctk.CTkFrame(
                parent, fg_color=BG_CARD, border_color=BORDER,
                border_width=1, corner_radius=8,
            )
            ctk.CTkLabel(
                outer, text=titulo, font=_F_SECAO,
                text_color=TEXT_SECONDARY, fg_color="transparent",
                anchor="center" if center else "w",
            ).pack(fill="x", padx=12, pady=(8, 2))
            inner = ctk.CTkFrame(outer, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            return outer, inner

        cards_outer, cards_inner = _secao(content, "📋 Resumo do Portfólio", center=True)
        cards_outer.grid(row=0, column=0, sticky="nsew", padx=(5, 6), pady=(4, 0))

        painel = PainelCards(cards_inner)
        painel.pack(fill="both", expand=True)

        self._lbl_patrimonio = painel.lbl_patrimonio
        self._lbl_custo      = painel.lbl_custo
        self._lbl_compras_hist = painel.lbl_compras_hist
        self._lbl_pl_nr      = painel.lbl_pl_nr
        self._lbl_pl_r       = painel.lbl_pl_r
        self._lbl_pl         = painel.lbl_pl
        self._lbl_pct        = painel.lbl_pct
        self._lbl_retorno    = painel.lbl_retorno
        self._lbl_div        = painel.lbl_div
        self._lbl_melhor     = painel.lbl_melhor
        self._lbl_pior       = painel.lbl_pior

        right = ctk.CTkFrame(content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 5), pady=(4, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=2)
        right.rowconfigure(1, weight=3)

        donut_outer, donut_inner = _secao(right, " Performance P/L por Ativo ")
        donut_outer.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        self.donut_chart = DonutChart(donut_inner)
        self.donut_chart.pack(fill="both", expand=True)

        detalhe_outer, detalhe_inner = _secao(right, " Análise Detalhada de P&L ")
        detalhe_outer.grid(row=1, column=0, sticky="nsew")

        header = ctk.CTkFrame(detalhe_inner, fg_color=BG_DEEP, corner_radius=6)
        header.pack(fill="x", padx=(4, 16), pady=(0, 2))
        for i in range(_N):
            header.columnconfigure(i, weight=1, uniform="tabela_col")
        for i, (txt, anchor) in enumerate(zip(_DET_COLS, _ALINHAMENTOS)):
            ctk.CTkLabel(
                header, text=txt, font=_FONT_HEAD,
                text_color=TEXT_SECONDARY, fg_color="transparent", anchor=anchor,
            ).grid(row=0, column=i, sticky="ew", padx=10, pady=6)

        self._det_scroll = ctk.CTkScrollableFrame(
            detalhe_inner, fg_color=BG_CARD,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=TEXT_MUTED,
            corner_radius=6,
        )
        self._det_scroll.pack(fill="both", expand=True)
        self._det_scroll.columnconfigure(0, weight=1)
        self._bind_det_scroll(self._det_scroll)

    def _bind_det_scroll(self, frame: ctk.CTkScrollableFrame):
        canvas = frame._parent_canvas

        def _scroll(event):
            if event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")

        for w in (frame, canvas):
            w.bind("<Button-4>",   _scroll, add="+")
            w.bind("<Button-5>",   _scroll, add="+")
            w.bind("<MouseWheel>", _scroll, add="+")
        self._det_scroll_fn = _scroll

    def _bind_det_scroll_row(self, widget):
        if self._det_scroll_fn is None:
            return
        widget.bind("<Button-4>",   self._det_scroll_fn, add="+")
        widget.bind("<Button-5>",   self._det_scroll_fn, add="+")
        widget.bind("<MouseWheel>", self._det_scroll_fn, add="+")
        for child in widget.winfo_children():
            self._bind_det_scroll_row(child)

    def _toggle_det_sel(self, row: ctk.CTkFrame):
        if getattr(row, '_eh_vazio', False):
            return
        self._det_sel = None if self._det_sel is row else row
        self._aplicar_det_sel()

    def _aplicar_det_sel(self):
        for r in self._det_rows:
            if getattr(r, '_eh_vazio', False):
                continue
            if r is self._det_sel:
                r.configure(fg_color=_SEL_BG, border_color=_SEL_GLOW, border_width=1)
            else:
                r.configure(fg_color=r._bg_normal, border_width=0)

    def _hover_det(self, row: ctk.CTkFrame, entering: bool):
        if getattr(row, '_eh_vazio', False) or row is self._det_sel:
            return
        row.configure(fg_color=_HOVER_BG if entering else row._bg_normal)

    def _fmt_val(self, val):
        if self.display_currency == "BRL":
            taxa = self._price_manager.preco_brl
            if taxa and taxa > 0:
                return f"R${val * taxa:,.2f}"
        return f"${val:,.2f}"

    def _fmt_prc(self, val):
        if self.display_currency == "BRL":
            taxa = self._price_manager.preco_brl
            if taxa and taxa > 0:
                return f"R${val * taxa:,.4f}"
        return f"${val:,.4f}"

    def _resetar_cards(self):
        for lbl in (
            self._lbl_patrimonio, self._lbl_custo, self._lbl_compras_hist, self._lbl_pl_nr,
            self._lbl_pl_r, self._lbl_pl, self._lbl_pct, self._lbl_retorno,
            self._lbl_div, self._lbl_melhor, self._lbl_pior,
        ):
            lbl.configure(text="--")

    def _on_currency_change(self, currency: str):
        self.display_currency = currency
        self.atualizar()

    def atualizar(self):
        self.set_status("🔄 Calculando P&L...", CYAN)
        threading.Thread(target=self._worker_atualizar, daemon=True).start()

    def _worker_atualizar(self):
        try:
            ops = self._data_manager.carregar_operacoes()
            if not ops:
                self.after(0, self._ui_vazia)
                return
            portfolio = self._engine.calcular_portfolio(ops, self._price_manager.precos_cache)
            usdt_pl   = self._engine.calcular_pl_usdt_brl(ops, self._price_manager.preco_brl)
            dist      = self._engine.calcular_distribuicao_portfolio(ops, self._price_manager.precos_cache)
            self.after(0, lambda: self._atualizar_ui(portfolio, usdt_pl, dist))
            self.after(0, lambda: self.set_estado("conectado"))  
        except Exception as e:
            self.after(0, lambda: self.set_status("❌ Falha no processamento", NEON_RED))
            self.after(0, lambda: messagebox.showerror("Exceção do Engine", str(e)))

    def _ui_vazia(self):
        self._limpar_det_rows()
        self.set_status("", TEXT_SECONDARY)
        self._resetar_cards()
        self._inserir_detalhe_vazio()
        self.donut_chart.limpar()

    def _limpar_det_rows(self):
        for r in self._det_rows:
            r.destroy()
        self._det_rows.clear()
        self._det_sel   = None
        self._det_hover = None

    def _inserir_detalhe_vazio(self):
        row = ctk.CTkFrame(self._det_scroll, fg_color=BG_CARD, corner_radius=0)
        row.pack(fill="x", pady=1)
        row.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            row, text="Nenhuma operação registrada.", font=_FONT,
            text_color=TEXT_MUTED, fg_color="transparent",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        row._eh_vazio = True
        self._det_rows.append(row)

    def _atualizar_ui(self, portfolio, usdt_pl, dist):
        if self._det_rows and getattr(self._det_rows[0], '_eh_vazio', False):
            self._limpar_det_rows()

        self._usdt_pl_brl = usdt_pl
        distribuicao = dist.get("distribuicao", {})

        if distribuicao:
            n_ativos         = len(distribuicao)
            lbl_txt, cor_txt = next((lb, c) for minv, lb, c in _DIVERSIFICACAO if n_ativos >= minv)
            self._lbl_div.configure(text=lbl_txt, text_color=cor_txt)

            ord_dist  = sorted(distribuicao.items(), key=lambda x: x[1]["percentual"], reverse=True)
            cores_cfg = _carregar_cores_moedas()

            fallback_idx = 0
            cor_map      = {}
            for m, _ in ord_dist:
                chave = m.upper().replace(" (CAIXA)", "").strip()
                if chave in cores_cfg:
                    cor_map[m] = cores_cfg[chave]
                else:
                    cor_map[m] = _CORES_ATIVOS[fallback_idx % len(_CORES_ATIVOS)]
                    fallback_idx += 1

            pl_map = {}
            for moeda_pl, dados_pl in portfolio.items():
                if moeda_pl in ("totais", "USDT (Caixa)"):
                    continue
                custo_pl = dados_pl.get("custo_posicao_final", 0)
                if custo_pl > 0.000001:
                    pl_map[moeda_pl] = dados_pl.get("lucro_nao_realizado", 0) / custo_pl * 100

            self.donut_chart.atualizar_dados(ord_dist, cor_map, pl_map=pl_map)
        else:
            self._lbl_div.configure(text="--", text_color=TEXT_SECONDARY)
            self.donut_chart.limpar()

        moedas_dados = {m: d for m, d in portfolio.items() if m != "totais"}
        ord_port     = sorted(moedas_dados.items(), key=lambda item: item[1].get("valor_atual_posicao", 0), reverse=True)

        tot_custo = tot_val = tot_pl_nr = tot_pl_r = 0
        for idx, (moeda, dados) in enumerate(ord_port):
            self._inserir_detalhe(moeda, dados, idx)
            tot_custo += dados.get("custo_posicao_final", 0)
            tot_val   += dados.get("valor_atual_posicao", 0)
            tot_pl_nr += dados.get("lucro_nao_realizado", 0)
            tot_pl_r  += dados.get("lucro_realizado", 0)

        while len(self._det_rows) > len(ord_port):
            linha_sobrando = self._det_rows.pop()
            linha_sobrando.destroy()
            if self._det_sel is linha_sobrando:
                self._det_sel = None

        tot_pl    = tot_pl_nr + tot_pl_r
        pct_nr    = (tot_pl_nr / tot_custo * 100) if tot_custo > 0.000001 else 0
        tot_comprado = portfolio.get("totais", {}).get("compras_historicas_usdt", 0)
        pct_total = (tot_pl / tot_comprado * 100) if tot_comprado > 0.000001 else 0

        cor_pl      = NEON_GREEN if tot_pl    >= 0 else NEON_RED
        cor_nr      = NEON_GREEN if tot_pl_nr >= 0 else NEON_RED
        cor_r       = NEON_GREEN if tot_pl_r  >= 0 else NEON_RED
        cor_retorno = NEON_GREEN if pct_total >= 0 else NEON_RED

        self._lbl_patrimonio.configure(text=self._fmt_val(tot_val))
        self._lbl_custo.configure(     text=self._fmt_val(tot_custo))
        # Compras históricas: sempre em USDT, sem converter pelo câmbio atual.
        self._lbl_compras_hist.configure(text=f"{tot_comprado:,.2f} USDT")
        self._lbl_pl_nr.configure(     text=self._fmt_val(tot_pl_nr),  text_color=cor_nr)
        self._lbl_pl_r.configure(      text=self._fmt_val(tot_pl_r),   text_color=cor_r)
        self._lbl_pl.configure(        text=self._fmt_val(tot_pl),     text_color=cor_pl)
        self._lbl_pct.configure(       text=f"{pct_nr:+.2f}%",         text_color=cor_nr)
        self._lbl_retorno.configure(   text=f"{pct_total:+.2f}%",      text_color=cor_retorno)

        moedas_validas = [(m, d) for m, d in ord_port if m != "USDT (Caixa)" and d.get("lucro_total") is not None]
        if moedas_validas:
            melhor = max(moedas_validas, key=lambda x: x[1].get("lucro_total", 0))
            pior   = min(moedas_validas, key=lambda x: x[1].get("lucro_total", 0))

            def _pct_ativo(d):
                c = d.get("custo_posicao_final", 0)
                return (d.get("lucro_nao_realizado", 0) / c * 100) if c > 0.000001 else 0

            self._lbl_melhor.configure(
                text=f"{melhor[0]}  {self._fmt_val(melhor[1].get('lucro_total', 0))}  ({_pct_ativo(melhor[1]):+.1f}%)"
            )
            self._lbl_pior.configure(
                text=f"{pior[0]}  {self._fmt_val(pior[1].get('lucro_total', 0))}  ({_pct_ativo(pior[1]):+.1f}%)"
            )
        else:
            self._lbl_melhor.configure(text="--")
            self._lbl_pior.configure(  text="--")

    def _inserir_detalhe(self, moeda: str, dados: dict, idx: int):
        qtd     = dados.get("quantidade_final", 0)
        pmc     = dados.get("pmc_final", 0)
        custo   = dados.get("custo_posicao_final", 0)
        p_mkt   = dados.get("preco_de_mercado", 0)
        v_atual = dados.get("valor_atual_posicao", 0)
        pl_nr   = dados.get("lucro_nao_realizado", 0)
        pl_r    = dados.get("lucro_realizado", 0)
        pl_tot  = dados.get("lucro_total", 0)
        comprado_hist = dados.get("total_comprado_usdt", 0)
        # Para posição encerrada, o percentual representa resultado realizado.
        base_pct = (pl_nr / custo) if custo > 0.000001 else (
            pl_r / comprado_hist if comprado_hist > 0.000001 else 0
        )
        str_pct = f"{base_pct * 100:+.2f}%"
        bg      = BG_CARD if idx % 2 == 0 else BG_DEEP

        if moeda == "USDT (Caixa)":
            taxa = self._price_manager.preco_brl or 1.0
            if self.display_currency == "BRL":
                pl = self._usdt_pl_brl
                if pl and pl.get("pmc_brl", 0) > 0:
                    valores = [
                        moeda,
                        f"{qtd:,.2f} USDT",
                        f"R${pl['pmc_brl']:,.4f}",
                        f"R${taxa:,.4f}",
                        f"R${pl['custo_posicao_brl']:,.2f}",
                        f"R${pl['valor_atual_brl']:,.2f}",
                        f"R${pl['lucro_nao_realizado_brl']:+,.2f}",
                        f"R${pl['lucro_realizado_brl']:+,.2f}",
                        f"R${pl['lucro_total_brl']:+,.2f}",
                        f"{(pl['lucro_nao_realizado_brl'] / pl['custo_posicao_brl'] * 100):+.2f}%"
                        if pl["custo_posicao_brl"] > 0 else "0.00%",
                    ]
                    pos = pl["lucro_total_brl"] >= 0
                else:
                    valores = [moeda, f"{qtd:,.2f} USDT", "N/A", f"R${taxa:,.4f}", "N/A",
                               f"R${qtd * taxa:,.2f}", "N/A", "N/A", "N/A", "0.00%"]
                    pos = True
            else:
                valores = [moeda, f"{qtd:,.2f} USDT", "N/A", self._fmt_prc(1.0),
                           "N/A", self._fmt_val(v_atual), "N/A", "N/A", "N/A", "0.00%"]
                pos = True
        else:
            valores = [
                moeda, f"{qtd:,.8f}", self._fmt_prc(pmc), self._fmt_prc(p_mkt),
                self._fmt_val(custo), self._fmt_val(v_atual), self._fmt_val(pl_nr),
                self._fmt_val(pl_r), self._fmt_val(pl_tot), str_pct,
            ]
            pos = pl_tot >= 0

        cor_pl     = NEON_GREEN if pos else NEON_RED
        _col_cores = [
            TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_MUTED,
            TEXT_SECONDARY, TEXT_PRIMARY, cor_pl, cor_pl, cor_pl, cor_pl,
        ]

        if idx < len(self._det_rows):
            row = self._det_rows[idx]
            row._bg_normal = bg
            if self._det_sel is row:
                row.configure(fg_color=_SEL_BG, border_color=_SEL_GLOW, border_width=1)
            else:
                row.configure(fg_color=bg, border_width=0)
            for lbl, txt, cor in zip(row._labels, valores, _col_cores):
                lbl.configure(text=txt, text_color=cor)
        else:
            row = ctk.CTkFrame(self._det_scroll, fg_color=bg, corner_radius=0, cursor="hand2")
            row.pack(fill="x", pady=0)
            row._bg_normal = bg

            for i in range(_N):
                row.columnconfigure(i, weight=1, uniform="tabela_col")

            row_labels = []
            for i, (txt, cor, anchor) in enumerate(zip(valores, _col_cores, _ALINHAMENTOS)):
                lbl = ctk.CTkLabel(
                    row, text=txt, font=_F_TREE,
                    text_color=cor, fg_color="transparent",
                    anchor=anchor, cursor="hand2",
                )
                lbl.grid(row=0, column=i, sticky="ew", padx=10, pady=3)
                lbl.bind("<Button-1>", lambda e, r=row: self._toggle_det_sel(r))
                lbl.bind("<Enter>",    lambda e, r=row: self._hover_det(r, True))
                lbl.bind("<Leave>",    lambda e, r=row: self._hover_det(r, False))
                row_labels.append(lbl)

            row._labels = row_labels
            row.bind("<Button-1>", lambda e, r=row: self._toggle_det_sel(r))
            row.bind("<Enter>",    lambda e, r=row: self._hover_det(r, True))
            row.bind("<Leave>",    lambda e, r=row: self._hover_det(r, False))
            self._bind_det_scroll_row(row)
            self._det_rows.append(row)