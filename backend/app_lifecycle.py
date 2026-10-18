"""Desktop preferences and official-release checking; never install a release here."""
from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os
import re
import tempfile

from backend.storage_sqlite import diretorio_dados_padrao
from backend.windows_lifecycle import comparar_versoes

RELEASE_ENDPOINT = (
    "https://api.github.com/repos/tiolusystems/dca-desktop-monitor/releases/latest"
)
APP_VERSION = "0.0.0"  # development build until a signed release assigns its version
DEFAULTS = {"minimizar_para_bandeja": False}
VERSION_PATTERN = re.compile(r"^v?([0-9]+\.[0-9]+\.[0-9]+)$")


def arquivo_preferencias(data_dir=None):
    return Path(data_dir or diretorio_dados_padrao()) / "app-settings.json"


def carregar_preferencias(data_dir=None):
    file = arquivo_preferencias(data_dir)
    if not file.exists():
        return dict(DEFAULTS)
    try:
        parsed = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Configurações não são um objeto JSON.")
        return {"minimizar_para_bandeja": parsed.get("minimizar_para_bandeja") is True}
    except (OSError, ValueError) as exc:
        # Do not silently enable background mode if configuration is damaged.
        raise RuntimeError(f"Configurações locais inválidas em {file}: {exc}") from exc


def salvar_preferencias(prefs, data_dir=None):
    if not isinstance(prefs, dict):
        raise ValueError("Preferências inválidas.")
    allowed = {"minimizar_para_bandeja": prefs.get("minimizar_para_bandeja") is True}
    file = arquivo_preferencias(data_dir)
    file.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="app-settings-", suffix=".tmp", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(allowed, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, file)
    finally:
        Path(temp).unlink(missing_ok=True)
    return allowed


def verificar_release_estavel(*, versao_atual=APP_VERSION, fetch=None):
    """Only GitHub Releases/latest; PRs and branch heads are never updates.

    A published version is NOT an approved package. There is no updater,
    signature or downloader in this function.
    """
    def buscar():
        req = Request(
            RELEASE_ENDPOINT,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "DCA-Monitor-Desktop"},
        )
        with urlopen(req, timeout=8) as result:
            return json.loads(result.read(500_000).decode("utf-8"))

    try:
        raw = (fetch or buscar)()
    except HTTPError as exc:
        if exc.code == 404:
            return {"estado": "sem_release",
                    "mensagem": "Nenhuma versão estável publicada no canal oficial.",
                    "download_disponivel": False}
        return {"estado": "erro_rede", "mensagem": f"HTTP {exc.code}: verificação não concluída.",
                "download_disponivel": False}
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        return {"estado": "offline",
                "mensagem": f"Não foi possível verificar online: {exc}",
                "download_disponivel": False}
    if not isinstance(raw, dict) or raw.get("draft") or raw.get("prerelease"):
        return {"estado": "invalido", "mensagem": "Release ausente, não estável ou inválida.",
                "download_disponivel": False}
    match = VERSION_PATTERN.fullmatch(str(raw.get("tag_name", "")))
    if match is None:
        return {"estado": "invalido", "mensagem": "Versão publicada sem padrão X.Y.Z.",
                "download_disponivel": False}
    version = match.group(1)
    comparable = comparar_versoes(versao_atual, version)
    if comparable["elegivel"]:
        state, msg = "disponivel", f"Versão estável {version} encontrada."
    else:
        state, msg = "atual", f"Nenhuma versão mais nova que {versao_atual}."
    return {
        "estado": state, "versao_atual": versao_atual,
        "versao_publicada": version, "mensagem": msg,
        "pagina": str(raw.get("html_url", "")),
        "publicado_em": raw.get("published_at"),
        "download_disponivel": False,
        "aviso": "Nenhum pacote foi instalado; assinatura e autorização ainda são obrigatórias.",
    }
