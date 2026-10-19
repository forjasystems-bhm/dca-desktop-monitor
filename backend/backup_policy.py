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
        ultimo = None
        for item in sorted(alvo.glob("portfolio-*.json")):
            # Não confiar apenas em nomes: manifestos e snapshots são verificados.
            info = verificar_manifesto_sqlite(item)
            if str(info.get("gerado_em_utc", "")).startswith(dia) and (
                    Path(str(info.get("banco_origem", ""))).resolve() == banco):
                if ultimo is None or info["gerado_em_utc"] > ultimo[1]["gerado_em_utc"]:
                    ultimo = (item, info)
        if ultimo is not None:
            item, info = ultimo
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


def configurar_destino_independente(diretorio, destino):
    """Explicit opt-in; retain ALL backups. No destructive pruning policy."""
    import os,tempfile
    folder=Path(diretorio).resolve();external=Path(destino).resolve()
    if external==folder or folder in external.parents:
        raise ErroBackupSQLite('Escolha um destino fora da pasta de dados operacional.')
    external.mkdir(parents=True,exist_ok=True)
    config={'destino_externo':str(external),'retencao':'todos'}
    fd,temp=tempfile.mkstemp(dir=folder,prefix='.backup-policy-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(config,out);out.flush();os.fsync(out.fileno())
        os.replace(temp,folder/'backup-policy.json')
    finally:Path(temp).unlink(missing_ok=True)
    return config


def proteger_gravacao(banco):
    """Separate confirmed SQL commit from backup health; never claim rollback."""
    from uuid import uuid4
    db=Path(banco).resolve()
    snapshot=criar_backup_sqlite(db,db.parent/'backups'/'sqlite',motivo='apos_gravacao')
    return snapshot


def espelhar_banco(banco):
    from uuid import uuid4
    db=Path(banco).resolve()
    policy=db.parent/'backup-policy.json'
    if policy.is_file():
        config=json.loads(policy.read_text(encoding='utf-8'))
        if config.get('destino_externo'):
            from backend.recovery_bundle import exportar_pacote
            target=Path(config['destino_externo'])/('DCA-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex+'.zip')
            exportar_pacote(db,target)
