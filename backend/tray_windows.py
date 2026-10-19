"""Optional Windows tray icon. Never starts without explicit user preference."""
from pathlib import Path
import sys


class ErroBandeja(RuntimeError):
    pass


class BandejaWindows:
    def __init__(self, *, ao_abrir, ao_atualizar, ao_sair, icone=None):
        self._abrir = ao_abrir
        self._atualizar = ao_atualizar
        self._sair = ao_sair
        self._icone_caminho = Path(icone) if icone else None
        self._icon = None

    @property
    def ativa(self):
        return self._icon is not None

    def iniciar(self):
        if self._icon is not None:
            return
        if sys.platform != "win32":
            raise ErroBandeja("Bandeja disponível somente no Windows.")
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise ErroBandeja(
                "Dependências opcionais da bandeja indisponíveis."
            ) from exc

        if self._icone_caminho and self._icone_caminho.is_file():
            img = Image.open(self._icone_caminho).convert("RGBA")
        else:
            img = Image.new("RGBA", (64, 64), (13, 17, 23, 255))
            draw = ImageDraw.Draw(img)
            draw.ellipse((10, 10, 54, 54), fill=(247, 147, 26, 255))
            draw.ellipse((22, 22, 42, 42), fill=(13, 17, 23, 255))
        ic = pystray.Icon(
            "dca-monitor", img, "DCA Monitor",
            menu=pystray.Menu(
                pystray.MenuItem("Abrir", lambda *_: self._abrir(), default=True),
                pystray.MenuItem(
                    "Atualizar cotações", lambda *_: self._atualizar()
                ),
                pystray.MenuItem(
                    "Sair completamente", lambda *_: self._sair()
                ),
            ),
        )
        try:
            ic.run_detached()
            self._icon = ic
        except Exception as exc:
            try:
                ic.stop()
            except Exception:
                pass
            raise ErroBandeja(f"Não foi possível abrir a bandeja: {exc}") from exc

    def parar(self):
        ic, self._icon = self._icon, None
        if ic is not None:
            ic.stop()
