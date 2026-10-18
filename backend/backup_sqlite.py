"""Cópias verificáveis do SQLite (inclusive WAL), sem tocar no banco de origem.

Serviço isolado: ainda não agenda backups nem automatiza restaurações.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile


class ErroBackupSQLite(RuntimeError):
    """Um backup que não pôde ser validado não deve ser anunciado como concluído."""


def _hash_sha256(arquivo: Path) -> str:
    digest = hashlib.sha256()
    with arquivo.open("rb") as entrada:
        for bloco in iter(lambda: entrada.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _integridade(arquivo: Path) -> str:
    if not arquivo.is_file():
        raise ErroBackupSQLite(f"Arquivo de banco inexistente: {arquivo}")
    try:
        # mode=ro impede criar um SQLite vazio em caso de caminho incorreto.
        with closing(sqlite3.connect(arquivo.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            return con.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as exc:
        raise ErroBackupSQLite(f"Não foi possível validar SQLite: {exc}") from exc


def verificar_backup_sqlite(arquivo: Path, sha256_esperado: str | None = None) -> dict:
    """Confere a cópia real; não confia somente na existência do arquivo."""
    arquivo = Path(arquivo).expanduser().resolve()
    integridade = _integridade(arquivo)
    if integridade != "ok":
        raise ErroBackupSQLite(f"SQLite do backup inconsistente: {integridade}")
    sha = _hash_sha256(arquivo)
    if sha256_esperado is not None and sha.lower() != sha256_esperado.lower():
        raise ErroBackupSQLite("SHA-256 divergente: o backup foi alterado.")
    return {"arquivo": str(arquivo), "sha256": sha, "integridade_sqlite": integridade}


def criar_backup_sqlite(banco: Path, destino: Path, *, motivo: str = "manual") -> dict:
    """Cria snapshot online consistente usando sqlite3.Connection.backup.

    Nunca copia o .sqlite3 com shutil.copyfile: no modo WAL isso poderia
    deixar operações confirmadas somente no WAL fora da cópia.
    """
    banco = Path(banco).expanduser().resolve()
    destino = Path(destino).expanduser().resolve()
    if not banco.is_file():
        raise ErroBackupSQLite(f"Banco de origem inexistente: {banco}")
    if _integridade(banco) != "ok":
        raise ErroBackupSQLite("Banco de origem não passou no integrity_check.")
    destino.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(timezone.utc)
    identificador = f"portfolio-{agora:%Y%m%dT%H%M%S%fZ}-{secrets.token_hex(4)}"
    arquivo_final = destino / f"{identificador}.sqlite3"
    manifesto_final = destino / f"{identificador}.json"
    fd, temporario = tempfile.mkstemp(prefix=".dca-backup-", suffix=".sqlite3", dir=destino)
    os.close(fd)
    temporario = Path(temporario)
    manifesto_temp = None
    try:
        try:
            with closing(sqlite3.connect(banco.as_uri() + "?mode=ro", uri=True)) as origem:
                with closing(sqlite3.connect(str(temporario))) as copia:
                    origem.backup(copia, pages=128, sleep=0.1)
        except sqlite3.Error as exc:
            raise ErroBackupSQLite(f"Falha durante a cópia online: {exc}") from exc
        verificado = verificar_backup_sqlite(temporario)
        # A cópia precisa estar persistida antes de ser anunciada.
        with temporario.open("rb") as f:
            os.fsync(f.fileno())
        manifesto = {
            "formato": "DCA-SQLITE-BACKUP-1",
            "gerado_em_utc": agora.isoformat(),
            "motivo": motivo,
            "banco_origem": str(banco),
            "arquivo": arquivo_final.name,
            "sha256": verificado["sha256"],
            "integridade_sqlite": "ok",
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destino, prefix=".dca-manifest-",
            suffix=".json", delete=False
        ) as f:
            manifesto_temp = Path(f.name)
            json.dump(manifesto, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, arquivo_final)
        try:
            os.replace(manifesto_temp, manifesto_final)
        except OSError:
            # Jamais declarar sucesso com um snapshot sem trilha de auditoria.
            arquivo_final.unlink(missing_ok=True)
            raise
        return {"backup": str(arquivo_final), "manifesto": str(manifesto_final), **manifesto}
    finally:
        temporario.unlink(missing_ok=True)
        if manifesto_temp is not None:
            manifesto_temp.unlink(missing_ok=True)
