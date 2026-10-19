import math
import tkinter as tk
# pyrefly: ignore [missing-import]
import customtkinter as ctk
from config.tema_cripto import (
    BG_CARD, BTC_ORANGE, NEON_GREEN, NEON_RED, CYAN,
    TEXT_SECONDARY, TEXT_MUTED, BORDER,
)
from config.fontes import (
    F_LATERAL_TITLE  as _F_TITLE,
    F_LATERAL_SUB    as _F_SUBTITLE,
    F_LATERAL_VAL    as _F_VALUE,
    F_LATERAL_VAL_SM as _F_VALUE_SM,
    F_LATERAL_BTC    as _F_BTC,
)

_ACCENT_W = 3
_SEP_H    = 1


def _lighten(hex_color: str, factor: float = 0.07) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


_BG_ROW     = _lighten(BG_CARD, 0.07)
_BG_ROW_HOV = _lighten(BG_CARD, 0.16)

_ITEMS_DEF = [
    ("patrimonio", "💼 Patrimônio Total",  "preço mercado × posição",  BTC_ORANGE),
    ("custo",      "📥 Custo Posição",     "capital das posições abertas", CYAN),
    ("compras_hist","📚 Compras Históricas","total comprado em ativos", CYAN),
    ("pl_nr",      "📈 P/L Não Realizado", "ganho em aberto",           NEON_GREEN),
    ("pl_r",       "💰 P/L Realizado",     "lucro já sacado/vendido",   NEON_GREEN),
    ("pl",         "🏁 P/L Total",         "realizado + não realizado", NEON_GREEN),
    ("pct",        "📊 Variação Aberta %",  "P/L aberto ÷ custo das posições", NEON_GREEN),
    ("retorno",    "📉 Retorno Dietz %",      "estimativa ajustada pelos fluxos externos", NEON_GREEN),
    ("div",        "🎯 Diversificação",    "ativos distintos",          TEXT_SECONDARY),
    ("melhor",     "🏆 Melhor Ativo",      "maior P/L total",           NEON_GREEN),
    ("pior",       "💀 Pior Ativo",        "menor P/L total",           NEON_RED),
]


def _sep(parent: tk.Widget) -> None:
    c = tk.Canvas(parent, height=_SEP_H, bg=BTC_ORANGE,
                  highlightthickness=0, bd=0)
    c.pack(fill="x")


class _BtcFooter:
    _INTERVAL = 100

    def __init__(self, parent: tk.Widget):
        self._phase = 0.0
        self._after_id = None
        self._ativo = True

        self.canvas = tk.Canvas(parent, height=90, bg=BG_CARD,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", pady=(4, 0))
        self.canvas.bind("<Configure>", lambda e: self._draw())
        self.canvas.after(50, self._tick)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width() or 260
        h = 90
        cx, cy = w // 2, h // 2

        glow = 0.5 + 0.5 * math.sin(self._phase)

        for i, r_off in enumerate((26, 18, 10)):
            intensity = glow * (55 - i * 14)
            r_val = min(255, int(intensity * 4))
            g_val = min(255, int(intensity * 2))
            cor   = f"#{r_val:02x}{g_val:02x}00"
            c.create_oval(
                cx - r_off, cy - r_off, cx + r_off, cy + r_off,
                outline=cor, width=max(1, 3 - i),
            )

        for i in range(1, 4):
            y = int(h * i / 4)
            c.create_line(0, y, w, y, fill=BORDER, width=1, dash=(2, 8))

        c.create_text(
            cx, cy,
            text="₿",
            font=_F_BTC,
            fill=_lighten(BG_CARD, 0.22),
            anchor="center",
        )

        c.create_line(0, h - 1, w, h - 1, fill=BTC_ORANGE, width=1)

    def _tick(self):
        if not self._ativo:
            return
        self._phase = (self._phase + 0.07) % (2 * math.pi)
        self._draw()
        self._after_id = self.canvas.after(self._INTERVAL, self._tick)

    def parar(self):
        self._ativo = False
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


class PainelCards(ctk.CTkScrollableFrame):

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=TEXT_MUTED,
            **kwargs,
        )
        self._labels: dict[str, ctk.CTkLabel] = {}
        self._footer_anim: _BtcFooter | None = None
        self._build()

    def _build(self) -> None:
        for idx, (key, titulo, subtitulo, cor_val) in enumerate(_ITEMS_DEF):
            self._labels[key] = self._criar_item(titulo, subtitulo, cor_val, key in ("melhor", "pior"))
            if idx < len(_ITEMS_DEF) - 1:
                _sep(self)
        self._footer_anim = _BtcFooter(self)

    def _criar_item(self, titulo: str, subtitulo: str, cor_val: str, small: bool) -> ctk.CTkLabel:
        outer = ctk.CTkFrame(self, fg_color=_BG_ROW, corner_radius=0, cursor="hand2")
        outer.pack(fill="x")

        outer.columnconfigure(0, minsize=_ACCENT_W, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.columnconfigure(2, weight=0)

        tk.Frame(outer, bg=BTC_ORANGE, width=_ACCENT_W).grid(
            row=0, column=0, rowspan=2, sticky="nsew",
        )

        ctk.CTkLabel(
            outer, text=titulo, font=_F_TITLE,
            text_color=TEXT_SECONDARY, fg_color="transparent", anchor="w", cursor="hand2",
        ).grid(row=0, column=1, sticky="w", padx=(10, 4), pady=(6, 0))

        lbl = ctk.CTkLabel(
            outer, text="--",
            font=_F_VALUE_SM if small else _F_VALUE,
            text_color=cor_val, fg_color="transparent", anchor="e", cursor="hand2",
        )
        lbl.grid(row=0, column=2, sticky="e", padx=(4, 10), pady=(6, 0))

        ctk.CTkLabel(
            outer, text=subtitulo, font=_F_SUBTITLE,
            text_color=TEXT_MUTED, fg_color="transparent", anchor="w", cursor="hand2",
        ).grid(row=1, column=1, columnspan=2, sticky="w", padx=(10, 10), pady=(0, 6))

        self._bind_hover(outer)
        self._bind_scroll_rec(outer)
        return lbl

    def _bind_hover(self, outer: ctk.CTkFrame) -> None:
        def _enter(e): outer.configure(fg_color=_BG_ROW_HOV)
        def _leave(e): outer.configure(fg_color=_BG_ROW)
        for w in (outer, *outer.winfo_children()):
            w.bind("<Enter>", _enter, add="+")
            w.bind("<Leave>", _leave, add="+")

    def _on_scroll(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            self._parent_canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self._parent_canvas.yview_scroll(1, "units")

    def _bind_scroll_rec(self, widget) -> None:
        widget.bind("<Button-4>",   self._on_scroll, add="+")
        widget.bind("<Button-5>",   self._on_scroll, add="+")
        widget.bind("<MouseWheel>", self._on_scroll, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_rec(child)

    @property
    def lbl_patrimonio(self) -> ctk.CTkLabel: return self._labels["patrimonio"]
    @property
    def lbl_custo(self)      -> ctk.CTkLabel: return self._labels["custo"]
    @property
    def lbl_compras_hist(self) -> ctk.CTkLabel: return self._labels["compras_hist"]
    @property
    def lbl_pl_nr(self)      -> ctk.CTkLabel: return self._labels["pl_nr"]
    @property
    def lbl_pl_r(self)       -> ctk.CTkLabel: return self._labels["pl_r"]
    @property
    def lbl_pl(self)         -> ctk.CTkLabel: return self._labels["pl"]
    @property
    def lbl_pct(self)        -> ctk.CTkLabel: return self._labels["pct"]
    @property
    def lbl_retorno(self)    -> ctk.CTkLabel: return self._labels["retorno"]
    @property
    def lbl_div(self)        -> ctk.CTkLabel: return self._labels["div"]
    @property
    def lbl_melhor(self)     -> ctk.CTkLabel: return self._labels["melhor"]
    @property
    def lbl_pior(self)       -> ctk.CTkLabel: return self._labels["pior"]