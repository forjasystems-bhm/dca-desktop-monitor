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


def ativar_restauracao_offline(manifesto, banco_ativo, *, confirmacao, aplicativo_encerrado=False):
    from backend.single_instance import TravaInstancia
    # Same application lock for the ENTIRE maintenance transaction, including
    # staging, replacement, verification and rollback; not merely a timed probe.
    with TravaInstancia(Path(banco_ativo).resolve().parent):
        return _ativar_restauracao_offline(manifesto,banco_ativo,
            confirmacao=confirmacao,aplicativo_encerrado=aplicativo_encerrado)


def _ativar_restauracao_offline(
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
    from backend.database_identity import validar_banco_dca
    import json
    marker=db.parent/"data-identity.json"
    expected=json.loads(marker.read_text(encoding="utf-8")).get("uuid") if marker.is_file() else None
    validar_banco_dca(origem, carteira_esperada=expected)
    if db == origem or db.suffix.lower() not in (".sqlite3",".db"):
        raise ErroBackupSQLite("Banco ativo inexistente, idêntico ao backup ou formato inválido.")
    # External process could still hold a WAL connection: do not move those files.
    if any(Path(str(db)+suffix).exists() for suffix in ("-wal","-shm","-journal")):
        raise ErroBackupSQLite(
            "Há arquivos WAL/SHM/journal. Encerre todos os processos e "
            "faça checkpoint offline; não substituir o banco enquanto existirem."
        )
    # Healthy databases receive a verified pre-backup. A corrupt original is
    # preserved byte-for-byte as rollback evidence, never forced through SQL.
    from backend.backup_sqlite import _hash_sha256
    original_hash = _hash_sha256(db) if db.is_file() else None
    original_copy = None
    if db.is_file():
        try:
            verificar_backup_sqlite(db)
        except ErroBackupSQLite:
            pass  # offline lock held; preserve unreadable original without changing it
        else:
            try:
                with closing(sqlite3.connect(str(db),timeout=0,isolation_level=None)) as cx:
                    cx.execute("BEGIN EXCLUSIVE")
                    cx.execute("ROLLBACK")
            except sqlite3.Error as exc:
                raise ErroBackupSQLite("Banco em uso ou bloqueado.") from exc
            original_copy = criar_backup_sqlite(
                db,db.parent/"backups"/"sqlite",motivo="antes_ativar_restauracao")
    stage = db.with_name("."+db.name+"-restauracao-"+secrets.token_hex(6)+".sqlite3")
    rollback = db.with_name(db.name+".rollback-"+secrets.token_hex(6)+".sqlite3")
    swapped=False
    try:
        preparar_restauracao_sqlite(Path(manifesto),stage)
        verificar_backup_sqlite(stage,verified["sha256"])
        # Atomic moves on the SAME filesystem; never overwrite user's
        # prior rollback copy. No source backup is touched.
        if db.exists():
            os.rename(db,rollback)
        swapped=True
        try:
            os.rename(stage,db)
            verificar_backup_sqlite(db,verified["sha256"])
        except Exception:
            if db.exists():
                db.unlink()
            if rollback.exists():
                os.rename(rollback,db)
            swapped=False
            if original_hash is not None and _hash_sha256(db) != original_hash:
                raise ErroBackupSQLite("Rollback diverge dos bytes originais.")
            raise
        return {
            "ativado":True,"banco":str(db),"sha256":verified["sha256"],
            "rollback_original":str(rollback) if rollback.exists() else None,
            "backup_previo":original_copy["manifesto"] if original_copy else None,
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
