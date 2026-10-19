"""OPS-02 preflight for a future Windows release.

Pure validation only: no installer creation, remote download or app mutation.
"""
from pathlib import Path
import hashlib
import re

from backend.backup_policy import backup_antes_atualizacao
from backend.backup_sqlite import verificar_manifesto_sqlite


class ErroCicloWindows(RuntimeError):
    pass


def verificar_separacao_dados(pasta_app: Path, banco: Path) -> None:
    app = Path(pasta_app).expanduser().resolve()
    db = Path(banco).expanduser().resolve()
    if db == app or app in db.parents:
        raise ErroCicloWindows(
            "Banco dentro da pasta substituível do aplicativo; "
            "atualização bloqueada até separar os dados com backup."
        )


def conferir_pacote_local(pacote: Path, sha256_esperado: str) -> dict:
    """Only compare bytes and SHA. This does NOT authenticate a publisher."""
    pacote = Path(pacote).expanduser().resolve()
    if not pacote.is_file():
        raise ErroCicloWindows("Pacote de atualização inexistente.")
    if (len(sha256_esperado) != 64
            or any(x not in "0123456789abcdef" for x in sha256_esperado.lower())):
        raise ErroCicloWindows("Hash esperado inválido.")
    digest = hashlib.sha256()
    with pacote.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != sha256_esperado.lower():
        raise ErroCicloWindows("Pacote não corresponde ao hash de referência.")
    return {
        "arquivo": str(pacote), "sha256": digest.hexdigest(),
        "assinatura_verificada": False, "instalacao_autorizada": False,
    }


def planejar_atualizacao_sem_executar(pasta_app: Path, banco: Path,
                                      pacote: Path, hash_pacote: str) -> dict:
    """Safe plan and verified SQLite snapshot. No overwrite or application."""
    verificar_separacao_dados(pasta_app, banco)
    file_check = conferir_pacote_local(pacote, hash_pacote)
    backup = backup_antes_atualizacao(banco)
    verificar_manifesto_sqlite(Path(backup["manifesto"]))
    return {
        "pacote": file_check, "backup_sqlite": backup["manifesto"],
        "banco_intacto": str(Path(banco).resolve()),
        "aplicada": False,
        "pendente": "Assinatura do publicador, consentimento e homologação final",
    }

def comparar_versoes(versao_atual: str, versao_nova: str) -> dict:
    """Reject downgrades, nonnumeric tags and no-op update."""
    def parse(v):
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", str(v)):
            raise ErroCicloWindows("Versão deve ser no formato MAJOR.MINOR.PATCH.")
        return tuple(int(x) for x in v.split("."))
    atual,nova=parse(versao_atual),parse(versao_nova)
    return {"atual":versao_atual,"nova":versao_nova,
            "elegivel":nova>atual,"downgrade_bloqueado":nova<atual,
            "versao_inalterada":nova==atual}


def planejar_instalacao_sem_executar(
    pasta_app: Path, pasta_dados: Path, pacote: Path, hash_pacote: str,
    *, versao_atual: str, versao_nova: str,
) -> dict:
    """One versioned app path, one persistent data path. No install or release."""
    apps=Path(pasta_app).expanduser().resolve()
    dados=Path(pasta_dados).expanduser().resolve()
    verificar_separacao_dados(apps,dados/"portfolio.sqlite3")
    v=comparar_versoes(versao_atual,versao_nova)
    if not v["elegivel"]:
        raise ErroCicloWindows("Versão nova deve ser superior à instalada.")
    pacote_conf=conferir_pacote_local(pacote,hash_pacote)
    return {
        "versao":v,
        "destino_versao":str(apps/"versions"/versao_nova),
        "diretorio_dados_persistente":str(dados),
        "pacote":pacote_conf,
        "novo_atalho_precisa_ser_criado":False,
        "instalacao_executada":False,
        "atualizacao_automatica_ativa":False,
        "publicacao_autorizada":False,
        "pendencias":["Autenticidade/assinatura do publicador",
                      "Revisão manual de pacote", "Cópia SQLite pré-atualização",
                      "Homologação e consentimento do usuário"],
    }
