from backend.ui_dispatch import UiDispatcher
import threading
import json
import logging
from tkinter import messagebox, colorchooser
# pyrefly: ignore [missing-import]
import customtkinter as ctk
from pathlib import Path

from config.tema_cripto import (
    BG_DEEP, BG_CARD, BG_INPUT,
    BTC_ORANGE, NEON_GREEN, CYAN,
    TEXT_SECONDARY,
)
from config.carregar_json import _get_config_path
from config.fontes import (
    F_TITULO     as _F_TITULO,
    F_STATUS     as _F_STATUS,
    F_BADGE      as _F_BADGE,
    F_SECAO      as _F_SECAO,
    F_CARD_TITLE as _F_CARD_TITLE,
    F_CARD_SUB   as _F_CARD_SUB,
    F_CARD_VAL   as _F_CARD_VAL,
    F_TREE       as _F_TREE,
    F_TREE_HEAD  as _F_TREE_HEAD,
    _f,
)

logger = logging.getLogger(__name__)

TEXT_PRIMARY  = "#e8eaf6"
RED_ALERT     = "#ff4d4d"
YELLOW_WARN   = "#e3b341"
BORDER_SUBTLE = "#2a2d3e"


class JanelaMoedas(ctk.CTkFrame):

    def __init__(self, parent, on_moedas_alteradas=None, price_manager=None):
        super().__init__(parent, fg_color=BG_DEEP)
        self._tasks = UiDispatcher(self)
        self._on_moedas_alteradas = on_moedas_alteradas
        self._price_manager       = price_manager
        self._moedas: list[str]   = []
        self._cores:  dict[str, str] = {}
        self._cor_nova            = "#ffffff"
        self._alterado            = False

        self._construir_interface()
        self._carregar_moedas()

    def _construir_interface(self):
        header = ctk.CTkFrame(self, fg_color=BG_DEEP)
        header.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(
            header,
            text="⚙  Gerenciar Moedas",
            font=_f(_F_TITULO),
            text_color=BTC_ORANGE,
            fg_color=BG_DEEP,
        ).pack(side="left")

        ctk.CTkFrame(self, fg_color=BTC_ORANGE, height=1).pack(fill="x", padx=24, pady=(8, 0))

        self._lbl_status = ctk.CTkLabel(
            self,
            text="",
            font=_f(_F_STATUS),
            text_color=NEON_GREEN,
            fg_color=BG_DEEP,
            anchor="center",
            justify="center",
        )
        self._lbl_status.pack(fill="x", pady=(4, 8))

        corpo = ctk.CTkFrame(self, fg_color=BG_DEEP)
        corpo.pack(fill="both", expand=True, padx=24, pady=0)
        corpo.columnconfigure(0, weight=3)
        corpo.columnconfigure(1, weight=2)
        corpo.rowconfigure(0, weight=1)

        self._construir_painel_lista(corpo)
        self._construir_painel_add(corpo)
        self._construir_rodape()

    def _construir_painel_lista(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, border_color=BORDER_SUBTLE, border_width=1)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="Moedas Ativas",
            font=_f(_F_SECAO),
            text_color=TEXT_PRIMARY,
            fg_color=BG_CARD,
        ).grid(row=0, column=0, sticky="ew", pady=10)

        ctk.CTkFrame(card, fg_color=BORDER_SUBTLE, height=1).grid(
            row=0, column=0, sticky="ew", pady=(36, 0)
        )

        lista_frame = ctk.CTkFrame(card, fg_color=BG_CARD)
        lista_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(10, 4))
        lista_frame.rowconfigure(0, weight=1)
        lista_frame.columnconfigure(0, weight=1)

        self._listbox = ctk.CTkTextbox(
            lista_frame,
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            font=_f(_F_CARD_VAL),
            activate_scrollbars=True,
            state="disabled",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        self._listbox._textbox.configure(cursor="hand2")
        self._listbox.bind("<Button-1>", self._on_listbox_click)

        btn_frame = ctk.CTkFrame(card, fg_color=BG_CARD)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))

        botoes = [
            ("▲ Subir",   self._mover_cima,    CYAN),
            ("▼ Descer",  self._mover_baixo,   CYAN),
            ("⤒ Topo",    self._mover_topo,    CYAN),
            ("⤓ Fim",     self._mover_fim,     CYAN),
            ("✕ Remover", self._remover_moeda, RED_ALERT),
        ]

        for txt, cmd, cor in botoes:
            ctk.CTkButton(
                btn_frame,
                text=txt,
                font=_f(_F_TREE_HEAD),
                fg_color=BG_INPUT,
                text_color=cor,
                hover_color=cor,
                border_width=0,
                cursor="hand2",
                height=30,
                command=cmd,
            ).pack(side="left", padx=3, pady=4)

        self._lbl_total = ctk.CTkLabel(
            card,
            text="",
            font=_f(_F_TREE),
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD,
        )
        self._lbl_total.grid(row=3, column=0, sticky="ew", pady=(0, 6))

        self._selected_idx: int | None = None

    def _on_listbox_click(self, event):
        widget = event.widget
        index  = widget.index(f"@{event.x},{event.y}")
        line   = int(index.split(".")[0]) - 1
        if 0 <= line < len(self._moedas):
            self._selected_idx = line
            self._highlight_selected()

    def _highlight_selected(self):
        self._listbox.configure(state="normal")
        self._listbox.tag_delete("selected")
        if self._selected_idx is not None:
            line_start = f"{self._selected_idx + 1}.0"
            line_end   = f"{self._selected_idx + 1}.end"
            self._listbox.tag_add("selected", line_start, line_end)
            self._listbox.tag_config("selected", background=BTC_ORANGE, foreground="#000")
        self._listbox.configure(state="disabled")

    def _construir_painel_add(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, border_color=BORDER_SUBTLE, border_width=1)
        card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ctk.CTkLabel(
            card,
            text="Adicionar Moeda",
            font=_f(_F_SECAO),
            text_color=TEXT_PRIMARY,
            fg_color=BG_CARD,
        ).pack(fill="x", pady=10)

        ctk.CTkFrame(card, fg_color=BORDER_SUBTLE, height=1).pack(fill="x")

        inner = ctk.CTkFrame(card, fg_color=BG_CARD)
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            inner,
            text="Símbolo da moeda:",
            font=_f(_F_CARD_SUB),
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self._entry_nova = ctk.CTkEntry(
            inner,
            font=_f(_F_CARD_VAL),
            fg_color=BG_INPUT,
            text_color=BTC_ORANGE,
            border_color=BTC_ORANGE,
            border_width=1,
            justify="center",
        )
        self._entry_nova.pack(fill="x")
        self._entry_nova.bind("<Return>", lambda _: self._adicionar_moeda())

        ctk.CTkLabel(
            inner,
            text='Ex: "BTC", "ETH", "SOL"',
            font=_f(_F_TREE),
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD,
        ).pack(pady=(4, 0))

        ctk.CTkLabel(
            inner,
            text="Cor no gráfico:",
            font=_f(_F_CARD_SUB),
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD,
            anchor="w",
        ).pack(fill="x", pady=(12, 4))

        picker_frame = ctk.CTkFrame(inner, fg_color=BG_CARD)
        picker_frame.pack(fill="x", pady=(0, 16))

        self._btn_cor_preview = ctk.CTkButton(
            picker_frame,
            text="",
            width=32,
            height=32,
            fg_color=self._cor_nova,
            hover_color=self._cor_nova,
            border_width=1,
            border_color=BORDER_SUBTLE,
            cursor="hand2",
            corner_radius=4,
            command=self._abrir_picker,
        )
        self._btn_cor_preview.pack(side="left", padx=(0, 8))

        self._lbl_cor_hex = ctk.CTkLabel(
            picker_frame,
            text=self._cor_nova,
            font=_f(_F_TREE),
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD,
        )
        self._lbl_cor_hex.pack(side="left")

        ctk.CTkLabel(
            inner,
            text="Inserir na posição:",
            font=_f(_F_CARD_SUB),
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self._var_posicao = ctk.StringVar(value="Final da lista")
        self._combo_posicao = ctk.CTkComboBox(
            inner,
            variable=self._var_posicao,
            state="readonly",
            font=_f(_F_CARD_SUB),
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
            button_color=BTC_ORANGE,
            dropdown_fg_color=BG_CARD,
            text_color=TEXT_PRIMARY,
            values=["Final da lista"],
        )
        self._combo_posicao.pack(fill="x", pady=(0, 20))

        ctk.CTkButton(
            inner,
            text="＋  Adicionar",
            font=_f(_F_CARD_TITLE),
            fg_color=NEON_GREEN,
            text_color="#000",
            hover_color=BTC_ORANGE,
            border_width=0,
            cursor="hand2",
            height=40,
            command=self._adicionar_moeda,
        ).pack(fill="x")

        ctk.CTkFrame(inner, fg_color=BG_CARD).pack(expand=True, fill="both")

        ctk.CTkLabel(
            inner,
            text="💡 Apenas moedas disponíveis na exchange configurada.\n\n⚠️ Atenção: Toda e qualquer alteração (adicionar, remover\nou reordenar moedas) só terá efeito no sistema após você\nclicar no botão 'Salvar e Aplicar' no rodapé da página.",
            font=_f(_F_TREE),
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD,
            justify="left",
        ).pack(anchor="w", pady=(16, 0))

    def _construir_rodape(self):
        rodape = ctk.CTkFrame(self, fg_color=BG_DEEP)
        rodape.pack(fill="x", padx=24, pady=16)

        container_botoes = ctk.CTkFrame(rodape, fg_color=BG_DEEP)
        container_botoes.pack(expand=True)

        ctk.CTkButton(
            container_botoes,
            text="↺  Descartar alterações",
            font=_f(_F_CARD_SUB),
            fg_color=BG_CARD,
            text_color=TEXT_SECONDARY,
            hover_color=YELLOW_WARN,
            border_width=0,
            cursor="hand2",
            width=180,
            height=40,
            command=self._descartar,
        ).pack(side="left", padx=10)

        self._btn_salvar = ctk.CTkButton(
            container_botoes,
            text="💾  Salvar e Aplicar",
            font=_f(_F_SECAO),
            fg_color=BTC_ORANGE,
            text_color="#000",
            hover_color=NEON_GREEN,
            border_width=0,
            cursor="hand2",
            width=220,
            height=40,
            state="disabled",
            command=self._salvar_e_aplicar,
        )
        self._btn_salvar.pack(side="left", padx=10)

    def _carregar_moedas(self):
        try:
            with _get_config_path().open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._moedas = list(data.get("moedas", []))
            self._cores  = dict(data.get("cores_moedas", {}))
        except Exception as e:
            logger.warning(f"Erro ao carregar moedas: {e}")
            self._moedas = []
            self._cores  = {}

        self._selected_idx = None
        self._sync_listbox()
        self._sync_combo_posicao()
        self._marcar_alterado(False)
        self._set_status("Configuração carregada.", CYAN, autoapagar=True)

    def _salvar_e_aplicar(self):
        if not self._moedas:
            messagebox.showwarning("Atenção", "A lista de moedas não pode ficar vazia!")
            return

        try:
            path = _get_config_path()
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            data["moedas"]       = self._moedas
            data["cores_moedas"] = self._cores

            from config.carregar_json import salvar_config
            salvar_config(data)

            self._marcar_alterado(False)
            self._set_status(f"✓ Salvo! {len(self._moedas)} moedas ativas.", NEON_GREEN)

            if callable(self._on_moedas_alteradas):
                self._on_moedas_alteradas(list(self._moedas))

        except Exception as e:
            logger.error(f"Erro ao salvar config: {e}")
            messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}")

    def _descartar(self):
        if self._alterado:
            if not messagebox.askyesno("Descartar", "Descartar todas as alterações não salvas?"):
                return
        self._carregar_moedas()

    def _abrir_picker(self):
        resultado = colorchooser.askcolor(color=self._cor_nova, title="Escolher cor")
        if resultado and resultado[1]:
            self._cor_nova = resultado[1].lower()
            self._btn_cor_preview.configure(
                fg_color=self._cor_nova,
                hover_color=self._cor_nova,
            )
            self._lbl_cor_hex.configure(text=self._cor_nova)

    def _adicionar_moeda(self):
        simbolo = self._entry_nova.get().strip().upper()
        if not simbolo:
            self._set_status("Digite o símbolo da moeda.", YELLOW_WARN, autoapagar=True)
            return
        if simbolo in self._moedas:
            self._set_status(f"{simbolo} já está na lista.", YELLOW_WARN, autoapagar=True)
            return

        self._set_status(f"🔍 Verificando {simbolo} na Binance...", CYAN)
        self._entry_nova.configure(state="disabled")

        def worker():
            valido = True
            if self._price_manager:
                valido = self._price_manager.validar_moeda(simbolo)
            self._tasks.post(lambda: self._finalizar_adicao(simbolo, valido))

        self._tasks.run(worker)

    def _finalizar_adicao(self, simbolo: str, valido: bool):
        self._entry_nova.configure(state="normal")
        self._entry_nova.focus()

        if not valido:
            self._set_status(
                f"✕ A moeda '{simbolo}' não existe na Binance (Par {simbolo}/USDT).",
                RED_ALERT, autoapagar=True,
            )
            return

        pos_txt = self._var_posicao.get()
        if pos_txt in ("Final da lista", ""):
            self._moedas.append(simbolo)
            idx = len(self._moedas) - 1
        elif pos_txt == "Início da lista":
            self._moedas.insert(0, simbolo)
            idx = 0
        else:
            try:
                ref = pos_txt.split(" ", 1)[1]
                idx = self._moedas.index(ref) + 1
            except (ValueError, IndexError):
                idx = len(self._moedas)
            self._moedas.insert(idx, simbolo)

        self._cores[simbolo] = self._cor_nova

        self._cor_nova = "#ffffff"
        self._btn_cor_preview.configure(fg_color="#ffffff", hover_color="#ffffff")
        self._lbl_cor_hex.configure(text="#ffffff")

        self._entry_nova.delete(0, "end")
        self._selected_idx = idx
        self._sync_listbox()
        self._sync_combo_posicao()
        self._highlight_selected()
        self._marcar_alterado(True)
        self._set_status(f"✓ {simbolo} adicionado com sucesso.", NEON_GREEN, autoapagar=True)

    def _remover_moeda(self):
        if self._selected_idx is None:
            self._set_status("Selecione uma moeda para remover.", YELLOW_WARN, autoapagar=True)
            return
        idx   = self._selected_idx
        moeda = self._moedas[idx]
        if not messagebox.askyesno("Remover", f"Remover {moeda} da lista?"):
            return
        self._moedas.pop(idx)
        self._cores.pop(moeda, None)
        self._selected_idx = min(idx, len(self._moedas) - 1) if self._moedas else None
        self._sync_listbox()
        self._sync_combo_posicao()
        self._highlight_selected()
        self._marcar_alterado(True)
        self._set_status(f"✕ {moeda} removida.", RED_ALERT, autoapagar=True)

    def _mover_cima(self):
        self._mover(-1)

    def _mover_baixo(self):
        self._mover(1)

    def _mover(self, delta: int):
        if self._selected_idx is None:
            self._set_status("Selecione uma moeda para mover.", YELLOW_WARN, autoapagar=True)
            return
        idx  = self._selected_idx
        novo = idx + delta
        if novo < 0 or novo >= len(self._moedas):
            return
        self._moedas[idx], self._moedas[novo] = self._moedas[novo], self._moedas[idx]
        self._selected_idx = novo
        self._sync_listbox()
        self._highlight_selected()
        self._marcar_alterado(True)

    def _mover_topo(self):
        if self._selected_idx is None:
            self._set_status("Selecione uma moeda para mover.", YELLOW_WARN, autoapagar=True)
            return
        if self._selected_idx == 0:
            return
        idx = self._selected_idx
        self._moedas.insert(0, self._moedas.pop(idx))
        self._selected_idx = 0
        self._sync_listbox()
        self._highlight_selected()
        self._marcar_alterado(True)

    def _mover_fim(self):
        if self._selected_idx is None:
            self._set_status("Selecione uma moeda para mover.", YELLOW_WARN, autoapagar=True)
            return
        if self._selected_idx == len(self._moedas) - 1:
            return
        idx = self._selected_idx
        self._moedas.append(self._moedas.pop(idx))
        self._selected_idx = len(self._moedas) - 1
        self._sync_listbox()
        self._highlight_selected()
        self._marcar_alterado(True)

    def _sync_listbox(self):
        self._listbox.configure(state="normal")
        self._listbox.delete("1.0", "end")
        for i, m in enumerate(self._moedas, 1):
            self._listbox.insert("end", f"  {i:>2}.  {m}\n")
        self._listbox.configure(state="disabled")
        self._lbl_total.configure(text=f"{len(self._moedas)} moeda(s) ativa(s)")

    def _sync_combo_posicao(self):
        opcoes = ["Início da lista"] + [f"Após {m}" for m in self._moedas] + ["Final da lista"]
        self._combo_posicao.configure(values=opcoes)
        self._var_posicao.set("Final da lista")

    def _marcar_alterado(self, estado: bool):
        self._alterado = estado
        self._btn_salvar.configure(state="normal" if estado else "disabled")

    def _set_status(self, msg: str, cor: str = TEXT_SECONDARY, autoapagar: bool = False):
        self._lbl_status.configure(text=msg, text_color=cor)
        if autoapagar:
            self.after(3000, lambda: self._lbl_status.configure(text=""))