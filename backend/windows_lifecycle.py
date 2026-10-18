"""OPS-02 preflight for a future Windows release.

Pure validation only: no installer creation, remote download or app mutation.
"""
from pathlib import Path
import hashlib

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
