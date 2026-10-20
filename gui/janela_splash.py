import os
import math
import time
import random
import logging
import platform
import threading
import tkinter as tk
# pyrefly: ignore [missing-import]
import customtkinter as ctk
from tkinter import messagebox

from backend.backend import DataManager, PriceManager
from config.tema_cripto import (
    BG_DEEP, BG_CARD, BG_INPUT,
    BTC_ORANGE, CYAN, TEXT_SECONDARY,
)
from config.carregar_json import _carregar_config
from config.fontes import (
    F_SPLASH_TITLE as _F_TITLE,
    F_SPLASH_SUB   as _F_SUB,
    F_SPLASH_MICRO as _F_MICRO,
    F_SPLASH_STAT  as _F_STAT,
    F_SPLASH_HASH  as _F_HASH,
    F_UI_BTC       as _F_BTC,
)

logger = logging.getLogger(__name__)

CONFIG            = _carregar_config()
MOEDAS_SUPORTADAS = CONFIG["moedas"]
TIMEOUT_SEGUNDOS  = CONFIG.get("splash_timeout", 60)

CANDLE_VERDE    = "#00c896"
CANDLE_VERMELHO = "#e84040"
WICK_VERDE      = "#009e75"
WICK_VERMELHO   = "#b02e2e"
GRID_COR        = "#0d1520"

_HEX = "0123456789abcdef"


def _rand_hash(n: int = 32) -> str:
    return "".join(random.choices(_HEX, k=n))


class _AnimacaoCandles:
    LARGURA   = 14
    ESPACO    = 5
    INTERVALO = 600

    def __init__(self, canvas: tk.Canvas):
        self.canvas      = canvas
        self.candles     = []
        self.preco_y     = 0
        self.largura     = 0
        self.altura      = 0
        self.max_candles = 0
        self._ativo      = True
        self._after_id   = None
        self._floats: list[dict] = []
        self.canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, evento):
        if evento.width < 50 or evento.height < 50:
            return
        primeira_vez    = not self.candles
        self.largura    = evento.width
        self.altura     = evento.height
        self.max_candles = self.largura // (self.LARGURA + self.ESPACO) + 2

        if primeira_vez:
            self.preco_y = self.altura / 2
            self.candles = [self._novo_candle() for _ in range(self.max_candles)]
            self._floats = [self._novo_float() for _ in range(20)]
        else:
            while len(self.candles) < self.max_candles:
                self.candles.append(self._novo_candle())
            while len(self.candles) > self.max_candles:
                self.candles.pop(0)

        self._desenhar_grid()
        self._desenhar()
        if primeira_vez and self._after_id is None:
            self._tick()

    def _novo_candle(self):
        direcao   = random.choice([-1, -1, 1, 1, 1, -1])
        corpo     = random.uniform(8, 32) * direcao
        margem    = 70
        novo_y    = max(margem, min(self.altura - margem, self.preco_y + corpo))
        open_y    = self.preco_y
        close_y   = novo_y
        pavio_sup = min(open_y, close_y) - random.uniform(4, 22)
        pavio_inf = max(open_y, close_y) + random.uniform(4, 22)
        self.preco_y = novo_y
        return (open_y, close_y, pavio_sup, pavio_inf)

    def _novo_float(self):
        return {
            "x":       random.uniform(0, max(1, self.largura)),
            "y":       random.uniform(0, max(1, self.altura)),
            "dx":      random.uniform(-0.35, 0.35),
            "dy":      random.uniform(-0.25, 0.25),
            "text":    _rand_hash(random.randint(8, 18)),
            "age":     0,
            "max_age": random.randint(80, 220),
        }

    def _desenhar_grid(self):
        self.canvas.delete("grid")
        for y in range(0, int(self.altura), 70):
            self.canvas.create_line(
                0, y, self.largura, y, fill=GRID_COR, tags="grid")
        for x in range(0, int(self.largura), 90):
            self.canvas.create_line(
                x, 0, x, self.altura, fill=GRID_COR, tags="grid")

    def _desenhar(self):
        self.canvas.delete("float_hash")
        self.canvas.delete("candle")
        self.canvas.delete("preco_linha")

        for f in self._floats:
            pct  = max(0.0, 1.0 - f["age"] / max(1, f["max_age"]))
            g_val = int(0x0e + pct * 0x2c)
            cor   = f"#0a{g_val:02x}12"
            self.canvas.create_text(
                f["x"], f["y"], text=f["text"],
                font=_F_MICRO, fill=cor,
                anchor="nw", tags="float_hash",
            )

        x = self.largura - len(self.candles) * (self.LARGURA + self.ESPACO)
        for open_y, close_y, pavio_sup, pavio_inf in self.candles:
            subiu     = close_y < open_y
            cor_corpo = CANDLE_VERDE    if subiu else CANDLE_VERMELHO
            cor_pavio = WICK_VERDE      if subiu else WICK_VERMELHO
            cx = x + self.LARGURA // 2
            self.canvas.create_line(
                cx, pavio_sup, cx, pavio_inf,
                fill=cor_pavio, width=1, tags="candle")
            top = min(open_y, close_y)
            bot = max(open_y, close_y)
            if bot - top < 2:
                bot = top + 2
            self.canvas.create_rectangle(
                x, top, x + self.LARGURA, bot,
                fill=cor_corpo, outline=cor_corpo, tags="candle")
            x += self.LARGURA + self.ESPACO

        if self.candles:
            ultimo_y = self.candles[-1][1]
            self.canvas.create_line(
                0, ultimo_y, self.largura, ultimo_y,
                fill=BTC_ORANGE, width=1, dash=(4, 4), tags="preco_linha")

    def _tick(self):
        if not self._ativo:
            return
        if self.candles:
            self.candles.pop(0)
            self.candles.append(self._novo_candle())
        for f in self._floats:
            f["x"]   += f["dx"]
            f["y"]   += f["dy"]
            f["age"] += 1
            if f["age"] >= f["max_age"] or not (0 <= f["x"] <= self.largura):
                f.update(self._novo_float())
        self._desenhar()
        self._after_id = self.canvas.after(self.INTERVALO, self._tick)

    def parar(self):
        self._ativo = False
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


class JanelaSplash:
    _BLOCK_BASE = 831_000

    def __init__(self, root_pai, criar_app_callback):
        self.root_pai           = root_pai
        self.criar_app_callback = criar_app_callback

        self.sucesso         = False
        self.data_manager    = None
        self.price_manager   = None
        self._erro           = None
        self._start_time     = time.time()
        self._status_msg     = "Inicializando node..."
        self._animacao       = None
        self._app_construida = False
        self._app_agendada = False
        self._block_height   = self._BLOCK_BASE + random.randint(0, 999)
        self._pulse_phase    = 0.0

        self._btc_canvas:   tk.Canvas | None          = None
        self.lbl_status:    ctk.CTkLabel | None       = None
        self.lbl_hash:      ctk.CTkLabel | None       = None
        self.lbl_block:     ctk.CTkLabel | None       = None
        self.lbl_net_val:   ctk.CTkLabel | None       = None
        self.progresso:     ctk.CTkProgressBar | None = None

        ctk.set_appearance_mode("dark")

        self.splash = ctk.CTkToplevel(root_pai)
        self.splash.title("Portfolio CRIPTO")
        self.splash.configure(fg_color=BG_DEEP)
        self.splash.attributes("-alpha", 1.0)

        self._maximizar()
        self._aplicar_icone()
        self._construir_interface()

        threading.Thread(target=self._carregar_dados, daemon=True).start()
        self.splash.after(100, self._checar_progresso)
        self.splash.after(150, self._animar_card)

    def _maximizar(self):
        self.splash.update_idletasks()
        try:
            self.splash.state("zoomed")
        except Exception:
            try:
                self.splash.attributes("-zoomed", True)
            except Exception:
                w = self.splash.winfo_screenwidth()
                h = self.splash.winfo_screenheight()
                self.splash.geometry(f"{w}x{h}+0+0")

    def _aplicar_icone(self):
        base_dir    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        caminho_ico = os.path.join(base_dir, "img", "dca-monitor.ico")
        caminho_png = os.path.join(base_dir, "img", "dca-monitor.png")
        try:
            if platform.system() == "Windows" and os.path.exists(caminho_ico):
                self.splash.iconbitmap(caminho_ico)
            if os.path.exists(caminho_png):
                img = tk.PhotoImage(file=caminho_png)
                self.splash.iconphoto(True, img)
        except Exception as e:
            logger.warning(f"Falha ao aplicar ícone: {e}")

    def _construir_interface(self):
        self.canvas = tk.Canvas(
            self.splash, bg=BG_DEEP, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._animacao = _AnimacaoCandles(self.canvas)

        self.card = ctk.CTkFrame(
            self.splash,
            fg_color=BG_CARD,
            border_color=BTC_ORANGE,
            border_width=2,
            corner_radius=20,
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        inner = ctk.CTkFrame(self.card, fg_color="transparent")
        inner.pack(padx=52, pady=40)

        self._btc_canvas = tk.Canvas(
            inner, width=90, height=90,
            bg=BG_CARD, highlightthickness=0, bd=0,
        )
        self._btc_canvas.pack(pady=(0, 8))
        self._desenhar_btc(1.0)

        ctk.CTkLabel(
            inner, text="PORTFOLIO  CRIPTO",
            font=_F_TITLE,
            text_color=BTC_ORANGE,
            fg_color="transparent",
        ).pack()

        ctk.CTkLabel(
            inner, text="< decentralized asset tracker />",
            font=_F_SUB,
            text_color=TEXT_SECONDARY,
            fg_color="transparent",
        ).pack(pady=(2, 14))

        ctk.CTkFrame(
            inner, fg_color="#2e1a00", height=1, corner_radius=0,
        ).pack(fill="x", pady=(0, 14))

        stats = ctk.CTkFrame(inner, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 14))
        for col in range(3):
            stats.columnconfigure(col, weight=1)

        def _stat(parent, col, title, value, color) -> ctk.CTkLabel:
            ctk.CTkLabel(
                parent, text=title,
                font=_F_MICRO, text_color=TEXT_SECONDARY,
                fg_color="transparent",
            ).grid(row=0, column=col, sticky="w", padx=8)
            lbl = ctk.CTkLabel(
                parent, text=value,
                font=_F_STAT,
                text_color=color,
                fg_color="transparent",
            )
            lbl.grid(row=1, column=col, sticky="w", padx=8)
            return lbl

        self.lbl_block   = _stat(stats, 0, "BLOCK HEIGHT",
                                 f"#{self._block_height:,}", CYAN)
        _                = _stat(stats, 1, "CHAIN",
                                 "mainnet", "#00c896")
        self.lbl_net_val = _stat(stats, 2, "STATUS",
                                 "syncing...", BTC_ORANGE)

        hash_box = ctk.CTkFrame(
            inner, fg_color="#060c12", corner_radius=8,
            border_color="#1a2a3a", border_width=1,
        )
        hash_box.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            hash_box, text="  TX HASH  >>>",
            font=_F_MICRO, text_color=TEXT_SECONDARY,
            fg_color="transparent",
        ).pack(anchor="w", padx=10, pady=(7, 2))

        self.lbl_hash = ctk.CTkLabel(
            hash_box,
            text=f"0x{_rand_hash(32)}",
            font=_F_HASH,
            text_color="#1c6e30",
            fg_color="transparent",
            wraplength=390,
        )
        self.lbl_hash.pack(anchor="w", padx=10, pady=(0, 8))

        self.lbl_status = ctk.CTkLabel(
            inner, text=self._status_msg,
            font=_F_STAT,
            text_color=CYAN,
            fg_color="transparent",
        )
        self.lbl_status.pack(pady=(0, 10))

        self.progresso = ctk.CTkProgressBar(
            inner, mode="indeterminate",
            width=400, height=6,
            progress_color=BTC_ORANGE,
            fg_color=BG_INPUT,
            corner_radius=3,
        )
        self.progresso.pack()
        self.progresso.start()

        ctk.CTkLabel(
            inner,
            text="Dados locais primeiro  ·  Cotações online opcionais",
            font=_F_MICRO,
            text_color=TEXT_SECONDARY,
            fg_color="transparent",
        ).pack(pady=(10, 0))

    def _desenhar_btc(self, glow: float):
        c = self._btc_canvas
        c.delete("all")
        cx, cy, r = 45, 45, 34

        for i, r_off in enumerate((14, 9, 4)):
            intensity = glow * (60 - i * 15)
            r_val = min(255, int(intensity * 4))
            g_val = min(255, int(intensity * 2))
            cor   = f"#{r_val:02x}{g_val:02x}00"
            c.create_oval(
                cx - r - r_off, cy - r - r_off,
                cx + r + r_off, cy + r + r_off,
                outline=cor, width=max(1, 3 - i),
            )

        c.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill="#180e00", outline=BTC_ORANGE, width=2,
        )

        c.create_text(
            cx, cy, text="₿",
            font=_F_BTC, fill=BTC_ORANGE,
        )

    def _animar_card(self):
        try:
            if not self.splash.winfo_exists():
                return
        except Exception:
            return

        self._pulse_phase = (self._pulse_phase + 0.07) % (2 * math.pi)
        glow = 0.5 + 0.5 * math.sin(self._pulse_phase)

        try:
            self._desenhar_btc(glow)
        except Exception:
            pass

        try:
            self.lbl_hash.configure(text=f"0x{_rand_hash(32)}")
        except Exception:
            pass

        if random.random() < 0.04:
            self._block_height += 1
            try:
                self.lbl_block.configure(text=f"#{self._block_height:,}")
            except Exception:
                pass

        self.splash.after(100, self._animar_card)

    def _carregar_dados(self):
        """Abre sem rede; falha somente se os dados locais não forem confiáveis."""
        try:
            self._status_msg = "Verificando banco local e backups..."
            from backend.local_startup import abrir_carteira_local
            data_mgr, price_mgr = abrir_carteira_local()
            self._status_msg = "Abrindo carteira local (sem depender da Binance)..."
            self.data_manager = data_mgr
            self.price_manager = price_mgr
            self.sucesso = True
        except Exception as exc:
            logger.exception("Falha ao abrir dados locais")
            self._erro = str(exc)

    def _checar_progresso(self):
        try:
            self.lbl_status.configure(text=self._status_msg)
        except Exception:
            pass

        if self.sucesso and not self._app_agendada:
            self._app_agendada = True
            try:
                self.lbl_net_val.configure(text="local", text_color="#00c896")
            except Exception:
                pass
            self.splash.after(300, self._construir_app)
            return
        if self._app_agendada:
            return

        if self._erro is not None:
            messagebox.showerror("Erro crítico", self._erro)
            self._encerrar(sucesso=False)
            return

        if time.time() - self._start_time > TIMEOUT_SEGUNDOS:
            messagebox.showerror(
                "Timeout",
                f"Tempo limite de {TIMEOUT_SEGUNDOS}s excedido ao carregar "
                "os dados locais. Nenhum registro foi apagado.",
            )
            self._encerrar(sucesso=False)
            return

        self.splash.after(80, self._checar_progresso)

    def _construir_app(self):
        try:
            self.criar_app_callback(self.data_manager, self.price_manager)
            self._app_construida = True
        except Exception as e:
            logger.exception("Falha ao construir aplicação")
            messagebox.showerror("Erro", f"Falha ao construir app:\n{e}")
            self._encerrar(sucesso=False)
            return
        self._fade_out()

    def _fade_out(self):
        try:
            alpha = float(self.splash.attributes("-alpha"))
        except Exception:
            alpha = 1.0
        if alpha > 0.05:
            self.splash.attributes("-alpha", max(0.0, alpha - 0.10))
            self.splash.after(22, self._fade_out)
        else:
            self._encerrar(sucesso=True)

    def _encerrar(self, sucesso: bool):
        try:
            if self._animacao is not None:
                self._animacao.parar()
        except Exception:
            pass
        try:
            self.progresso.stop()
        except Exception:
            pass
        try:
            self.splash.destroy()
        except Exception:
            pass
        if sucesso:
            self.root_pai.deiconify()
        else:
            self.root_pai.destroy()