"""Desktop preferences and official-release checking; never install a release here."""
from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
import hashlib
import platform
from urllib.parse import urlsplit
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
APP_VERSION = "1.0.0"  # versioned production candidate; GitHub release required
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
    os_type = platform.system()
    archive = {
        "Windows": f"DCA-Monitor-v{version}-Windows-x64.zip",
        "Linux": f"DCA-Monitor-v{version}-Linux-x64.tar.gz",
    }.get(os_type)
    asset = None
    if archive and isinstance(raw.get("assets"), list):
        for entry in raw["assets"]:
            if not isinstance(entry, dict) or entry.get("name") != archive:
                continue
            url = entry.get("browser_download_url", "")
            expected = (
                "https://github.com/tiolusystems/dca-desktop-monitor/"
                f"releases/download/v{version}/{archive}"
            )
            digest = entry.get("digest", "")
            size = entry.get("size", 0)
            if (url == expected and isinstance(digest, str) and
                    re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest) and
                    isinstance(size, int) and 1024 < size < 400_000_000):
                asset = {"url": url, "nome": archive,
                         "sha256": digest[7:].lower(), "tamanho": size}
                break
    eligible = state == "disponivel" and asset is not None
    if state == "disponivel" and not eligible:
        msg += " Pacote compatível ou SHA-256 não disponível: download bloqueado."
    return {
        "estado": state, "versao_atual": versao_atual,
        "versao_publicada": version, "mensagem": msg,
        "pagina": str(raw.get("html_url", "")),
        "publicado_em": raw.get("published_at"),
        "download_disponivel": eligible,
        "pacote": asset if eligible else None,
        "aviso": ("O pacote será baixado e verificado; instalação NÃO é automática. "
                  "SHA-256 não substitui assinatura do editor."),
    }


def baixar_atualizacao_verificada(info: dict, destino: Path) -> dict:
    """Download authenticated HTTPS GitHub release bytes, verify GitHub API digest.

    Do not overwrite files, install code, or modify the application's SQLite.
    A SHA does not by itself prove publisher identity or code signing.
    """
    if not isinstance(info, dict) or not info.get("download_disponivel"):
        raise ValueError("Não há atualização verificada para baixar.")
    pacote = info.get("pacote") or {}
    versao = info.get("versao_publicada")
    esperado = (
        "https://github.com/tiolusystems/dca-desktop-monitor/"
        f"releases/download/v{versao}/{pacote.get('nome', '')}"
    )
    if (not VERSION_PATTERN.fullmatch(str(versao))
            or pacote.get("url") != esperado
            or re.fullmatch(r"[a-f0-9]{64}", str(pacote.get("sha256", ""))) is None
            or pacote.get("nome") not in (
                f"DCA-Monitor-v{versao}-Windows-x64.zip",
                f"DCA-Monitor-v{versao}-Linux-x64.tar.gz",
            )):
        raise ValueError("Manifesto da atualização inválido.")
    target = Path(destino).expanduser().resolve()
    if target.name != pacote["nome"] or target.exists():
        raise ValueError("Destino incompatível ou arquivo já existente.")
    if not target.parent.is_dir():
        raise ValueError("Pasta de download inexistente.")
    fd, temporary = tempfile.mkstemp(prefix=".dca-download-", dir=target.parent)
    total = 0
    sha = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as local:
            with urlopen(Request(pacote["url"],
                                 headers={"User-Agent": "DCA-Monitor-Desktop"}),
                         timeout=30) as response:
                final = urlsplit(response.geturl())
                # GitHub downloads redirect to GitHub-controlled release CDN.
                if (final.scheme != "https" or final.hostname not in (
                    "github.com", "release-assets.githubusercontent.com",
                    "objects.githubusercontent.com")):
                    raise ValueError("Redirecionamento de download não confiável.")
                while True:
                    data = response.read(1024 * 1024)
                    if not data:
                        break
                    total += len(data)
                    if total > 400_000_000:
                        raise ValueError("Atualização supera tamanho máximo.")
                    sha.update(data)
                    local.write(data)
            local.flush()
            os.fsync(local.fileno())
        if total != pacote["tamanho"] or sha.hexdigest() != pacote["sha256"]:
            raise ValueError("Tamanho ou SHA-256 da atualização não confere.")
        # Exclusive final publication avoids overwriting existing user files.
        with target.open("xb") as out, open(temporary, "rb") as source:
            while True:
                data = source.read(1024 * 1024)
                if not data:
                    break
                out.write(data)
            out.flush()
            os.fsync(out.fileno())
        return {"arquivo": str(target), "sha256": sha.hexdigest(),
                "instalado": False}
    except Exception:
        target.unlink(missing_ok=True) if target.is_file() and (
            target.stat().st_size != total or sha.hexdigest() != pacote["sha256"]
        ) else None
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
