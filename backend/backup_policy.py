"""Política simples: backup SQLite verificável a cada dia e antes de atualizar.

A base operacional NUNCA é restaurada automaticamente quando um arquivo some.
Não apagar cópias anteriores nesta etapa; a política de retenção precisa
ser validada antes de remover backups de um usuário real.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

from backend.backup_sqlite import (
    ErroBackupSQLite, criar_backup_sqlite, verificar_manifesto_sqlite,
)


def garantir_backup_diario(banco: Path, destino: Path | None = None, *,
                           hoje_utc: str | None = None) -> dict:
    banco = Path(banco).expanduser().resolve()
    alvo = (Path(destino) if destino is not None
            else banco.parent / "backups" / "sqlite").expanduser().resolve()
    dia = hoje_utc or datetime.now(timezone.utc).date().isoformat()
    if not banco.is_file():
        raise ErroBackupSQLite("SQLite operacional ausente; não criar banco de substituição.")
    if alvo.exists():
        for item in sorted(alvo.glob("portfolio-*.json")):
            # Mesmo backups anteriores devem permanecer verificáveis.
            info = verificar_manifesto_sqlite(item)
            if str(info.get("gerado_em_utc", "")).startswith(dia) and (
                    Path(str(info.get("banco_origem", ""))).resolve() == banco):
                return {"realizado": False, "backup": str(item.parent / info["arquivo"]),
                        "manifesto": str(item), "sha256": info["sha256"]}
    gerado = criar_backup_sqlite(banco, alvo, motivo="abertura_diaria")
    verificar_manifesto_sqlite(Path(gerado["manifesto"]))
    return {**gerado, "realizado": True}


def backup_antes_atualizacao(banco: Path) -> dict:
    origem = Path(banco).expanduser().resolve()
    result = criar_backup_sqlite(
        origem, origem.parent / "backups" / "sqlite",
        motivo="antes_atualizacao",
    )
    verificar_manifesto_sqlite(Path(result["manifesto"]))
    return result
