"""
Instala o Portfolio DCA Monitor como atalho clicavel no sistema.

Windows : cria atalho na Area de Trabalho com icone — pode fixar na barra de tarefas
Linux   : cria entrada no menu de aplicativos — pode fixar no dock/painel

Uso (a partir da raiz do projeto ou da pasta config/):
    python config/install.py
"""
import sys
import subprocess
from pathlib import Path

# install.py fica em config/, entao a raiz do projeto eh o parent
BASE_DIR  = Path(__file__).parent.parent.resolve()
MAIN_PYW  = BASE_DIR / "main.pyw"
ICON_FILE = BASE_DIR / "img" / "favicon.ico"

APP_NAME = "Portfolio DCA Monitor"


def preparar_atalho_windows(
    destino: Path, *, executavel: Path | None = None, script: Path | None = None,
    icone: Path | None = None,
) -> str:
    """Somente prepara o comando; não cria atalho nem instala nada."""
    executable = Path(executavel) if executavel else (
        Path(sys.executable) if getattr(sys, "frozen", False)
        else (Path(sys.executable).parent / "pythonw.exe")
    )
    if not executable.is_file():
        raise FileNotFoundError(f"Executável não encontrado: {executable}")
    src = Path(script) if script else MAIN_PYW
    icon = Path(icone) if icone else ICON_FILE
    destination = Path(destino)
    if destination.suffix.lower() != ".lnk":
        raise ValueError("Atalho Windows deve terminar com .lnk")
    def ps(text):
        return "'" + str(text).replace("'", "''") + "'"

    code = [
        "$sh = New-Object -ComObject WScript.Shell",
        f"$lnk = $sh.CreateShortcut({ps(destination)})",
        f"$lnk.TargetPath = {ps(executable)}",
        f"$lnk.WorkingDirectory = {ps(executable.parent if getattr(sys, 'frozen', False) else BASE_DIR)}",
        f"$lnk.IconLocation = {ps(icon)}",
        "$lnk.Description = 'DCA Monitor - carteira local'",
    ]
    if not getattr(sys, "frozen", False):
        if not src.is_file():
            raise FileNotFoundError(f"Script Python não encontrado: {src}")
        code.append(f"$lnk.Arguments = {ps('"' + str(src) + '"')}")
    code.append("$lnk.Save()")
    return "\n".join(code)


def install_windows() -> None:
    """Somente quando o usuário pedir; não faz parte do primeiro boot."""
    desktop = Path.home() / "Desktop"
    shortcut = desktop / f"{APP_NAME}.lnk"
    if shortcut.exists():
        print(f"O atalho já existe: {shortcut}")
        return
    if not desktop.is_dir():
        raise FileNotFoundError(
            "Pasta Desktop não encontrada. Se estiver no OneDrive, "
            "selecione o destino ao criar o atalho."
        )
    script = preparar_atalho_windows(shortcut)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 or not shortcut.is_file():
        raise RuntimeError(
            "Falha ao criar o atalho: " + (result.stderr or "sem confirmação")
        )
    print(f"Atalho criado em: {shortcut}")


def install_linux() -> None:
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)

    python       = sys.executable
    desktop_file = apps_dir / "dca-portfolio-monitor.desktop"

    desktop_file.write_text(
        f"[Desktop Entry]\n"
        f"Name={APP_NAME}\n"
        f"Comment=Monitor de Portfolio DCA de Criptomoedas\n"
        f"Exec={python} \"{MAIN_PYW}\"\n"
        f"Icon={ICON_FILE}\n"
        f"Terminal=false\n"
        f"Type=Application\n"
        f"Categories=Finance;Utility;\n"
        f"StartupWMClass=main\n",
        encoding="utf-8",
    )
    desktop_file.chmod(0o755)
    subprocess.run(["update-desktop-database", str(apps_dir)], capture_output=True)

    print(f"Entrada criada em: {desktop_file}")
    print()
    print("Para fixar no dock/painel:")
    print("  Procure 'Portfolio DCA Monitor' no menu de aplicativos e arraste para o dock")
    print("  Ou clique direito -> Adicionar aos favoritos (GNOME/KDE)")


def main() -> None:
    if not MAIN_PYW.exists():
        print(f"Erro: nao encontrei {MAIN_PYW}")
        print("Execute este script a partir da raiz do projeto ou da pasta config/")
        sys.exit(1)

    if sys.platform == "win32":
        install_windows()
    elif sys.platform.startswith("linux"):
        install_linux()
    else:
        print(f"Sistema nao suportado: {sys.platform}")
        print("Plataformas suportadas: Windows e Linux")


if __name__ == "__main__":
    main()
