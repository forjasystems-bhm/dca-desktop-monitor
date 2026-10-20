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
ICON_FILE = BASE_DIR / "img" / "dca-monitor.ico"

APP_NAME = "Portfolio DCA Monitor"


def _powershell(arguments, *, timeout):
    """The windowed app must not flash a console while managing its shortcut."""
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    return subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                           '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); ' +
                           arguments], capture_output=True, text=True, encoding='utf-8',
                          timeout=timeout, **options)


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
    icon = Path(icone) if icone else (executable if getattr(sys, 'frozen', False) else ICON_FILE)
    destination = Path(destino)
    if destination.suffix.lower() != ".lnk":
        raise ValueError("Atalho Windows deve terminar com .lnk")
    def ps(text):
        return "'" + str(text).replace("'", "''") + "'"

    code = [
        "$ErrorActionPreference = 'Stop'",
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
        arguments = '"' + str(src) + '"'
        code.append(f"$lnk.Arguments = {ps(arguments)}")
    else:
        code.append("$lnk.Arguments = ''")
    code.append("$lnk.Save()")
    return "\n".join(code)


def install_windows(*, executavel=None, anterior=None, desktop=None) -> dict:
    """Create or retarget only our shortcut; preserve unrelated user shortcuts."""
    executable = Path(executavel or sys.executable).resolve()
    localizacao = _powershell("[Environment]::GetFolderPath('Desktop')", timeout=15)
    escritorio = localizacao.stdout.strip() if localizacao.returncode == 0 else ""
    desktop = Path(desktop) if desktop is not None else (Path(escritorio) if escritorio else None)
    if desktop is None:
        raise RuntimeError('O Windows não informou a pasta da Área de Trabalho.')
    shortcut = desktop / f"{APP_NAME}.lnk"
    if shortcut.exists():
        quoted = str(shortcut).replace("'", "''")
        inspected = _powershell(
             "$ErrorActionPreference='Stop'; $s=(New-Object -ComObject WScript.Shell).CreateShortcut('"+
             quoted+"'); @{target=$s.TargetPath;description=$s.Description;arguments=$s.Arguments} | ConvertTo-Json -Compress",
             timeout=15)
        import json
        existing = json.loads(inspected.stdout) if inspected.returncode == 0 else {}
        known = {str(executable).casefold()}
        if anterior:
            known.add(str(Path(anterior).resolve()).casefold())
        # A manually downloaded new version can refresh our older official
        # portable shortcut after verifying the old target's package identity.
        previous = Path(existing.get('target') or '__absent__')
        if (getattr(sys, 'frozen', False) and previous.name == 'DCA-Monitor.exe'
                and previous.is_file()):
            try:
                import hashlib
                from backend.app_lifecycle import APP_VERSION, comparar_versoes
                manifest = json.loads((previous.parent/'distribution-manifest.json').read_text('utf-8'))
                with previous.open('rb') as binary:
                    digest = hashlib.file_digest(binary, 'sha256').hexdigest()
                if (manifest.get('format') == 'DCA-DISTRIBUTION-1' and
                        not comparar_versoes(manifest['version'], APP_VERSION)['downgrade_bloqueado'] and
                        manifest['files']['DCA-Monitor.exe'] == digest):
                    known.add(str(previous).casefold())
            except (OSError, ValueError, KeyError):
                pass
        own = (existing.get('description') == 'DCA Monitor - carteira local' and
               str(existing.get('target', '')).casefold() in known and not existing.get('arguments'))
        if not own:
            return {'criado': False, 'proprio': False, 'atalho': str(shortcut),
                    'status': 'Atalho existente de outra instalação preservado. Remova-o ou renomeie-o para criar este.'}
    if not desktop.is_dir():
        raise FileNotFoundError(
            "Pasta Desktop não encontrada. Se estiver no OneDrive, "
            "selecione o destino ao criar o atalho."
        )
    script = preparar_atalho_windows(shortcut, executavel=executable)
    result = _powershell(script, timeout=30)
    if result.returncode != 0 or not shortcut.is_file():
        raise RuntimeError(
            "Falha ao criar o atalho: " + (result.stderr or "sem confirmação")
        )
    print(f"Atalho criado em: {shortcut}")
    return {"criado": True, "atalho": str(shortcut),
            "proprio": True,
            "status": "Atalho criado e verificado."}


def primeiro_atalho(data_dir):
    """One automatic attempt in a real Windows distribution, never in QA wallets."""
    import json
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return
    folder = Path(data_dir)
    if (folder / 'package-test-owner.json').exists():
        return
    marker = folder / 'desktop-setup.json'
    if marker.exists():
        return
    try:
        result = install_windows()
    except Exception as exc:
        result = {'criado': False, 'status': str(exc)}
    with marker.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False)


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
