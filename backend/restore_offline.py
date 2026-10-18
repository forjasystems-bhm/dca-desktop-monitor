"""OFFLINE-ONLY restore with preflight, reversible swap and independent evidence.

No GUI autorun. Requires explicit confirmation and a closed application.
A WAL/SHM sidecar causes refusal instead of risking stale transactions.
"""
from __future__ import annotations
from pathlib import Path
from contextlib import closing
import os
import secrets
import shutil
import sqlite3

from backend.backup_sqlite import (
    ErroBackupSQLite, criar_backup_sqlite, preparar_restauracao_sqlite,
    verificar_backup_sqlite, verificar_manifesto_sqlite,
)

CONFIRMACAO = "RESTAURAR BANCO SQLITE COM ROLLBACK"


def ativar_restauracao_offline(
    manifesto: Path, banco_ativo: Path, *, confirmacao: str,
    aplicativo_encerrado: bool = False,
) -> dict:
    """Maintenance only. No automatic recovery and no overwrite of backup."""
    if confirmacao != CONFIRMACAO or aplicativo_encerrado is not True:
        raise ErroBackupSQLite(
            "Restauração requer confirmação explícita e aplicativo encerrado."
        )
    db = Path(banco_ativo).expanduser().resolve()
    verified = verificar_manifesto_sqlite(manifesto)
    origem = Path(verified["verificacao"]["arquivo"])
    if not db.is_file() or db == origem or db.suffix.lower() not in (".sqlite3",".db"):
        raise ErroBackupSQLite("Banco ativo inexistente, idêntico ao backup ou formato inválido.")
    # External process could still hold a WAL connection: do not move those files.
    if any(Path(str(db)+suffix).exists() for suffix in ("-wal","-shm","-journal")):
        raise ErroBackupSQLite(
            "Há arquivos WAL/SHM/journal. Encerre todos os processos e "
            "faça checkpoint offline; não substituir o banco enquanto existirem."
        )
    # BEGIN EXCLUSIVE checks for active locks, but is not a magic proof that
    # all other processes will remain closed. Maintenance-only operation.
    try:
        with closing(sqlite3.connect(str(db),timeout=0, isolation_level=None)) as cx:
            cx.execute("PRAGMA locking_mode=EXCLUSIVE")
            cx.execute("BEGIN EXCLUSIVE")
            cx.execute("ROLLBACK")
    except sqlite3.Error as exc:
        raise ErroBackupSQLite("Banco em uso, bloqueado ou inválido.") from exc
    original_copy = criar_backup_sqlite(
        db, db.parent/"backups"/"sqlite", motivo="antes_ativar_restauracao"
    )
    stage = db.with_name("."+db.name+"-restauracao-"+secrets.token_hex(6)+".sqlite3")
    rollback = db.with_name(db.name+".rollback-"+secrets.token_hex(6)+".sqlite3")
    swapped=False
    try:
        preparar_restauracao_sqlite(Path(manifesto),stage)
        verificar_backup_sqlite(stage,verified["sha256"])
        # Atomic moves on the SAME filesystem; never overwrite user's
        # prior rollback copy. No source backup is touched.
        os.rename(db,rollback)
        swapped=True
        try:
            os.rename(stage,db)
            verificar_backup_sqlite(db,verified["sha256"])
        except Exception:
            if db.exists():
                db.unlink()
            os.rename(rollback,db)
            swapped=False
            verificar_backup_sqlite(db,original_copy["sha256"])
            raise
        return {
            "ativado":True,"banco":str(db),"sha256":verified["sha256"],
            "rollback_original":str(rollback),
            "backup_previo":original_copy["manifesto"],
            "manifesto_restaurado":str(Path(manifesto).resolve()),
        }
    except Exception as exc:
        if swapped and not db.exists() and rollback.exists():
            os.rename(rollback,db)
        if isinstance(exc, ErroBackupSQLite):
            raise
        raise ErroBackupSQLite("Ativação cancelada e banco anterior preservado: "+str(exc)) from exc
    finally:
        stage.unlink(missing_ok=True)
