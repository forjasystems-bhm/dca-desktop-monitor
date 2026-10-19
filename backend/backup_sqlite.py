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
        with temporario.open("rb+") as f:
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
        if (destino == banco.parent / "backups" / "sqlite"
                and not motivo.startswith("antes_schema")):
            from backend.backup_policy import espelhar_banco
            espelhar_banco(banco)
        return {"backup": str(arquivo_final), "manifesto": str(manifesto_final), **manifesto}
    finally:
        temporario.unlink(missing_ok=True)
        if manifesto_temp is not None:
            manifesto_temp.unlink(missing_ok=True)


def verificar_manifesto_sqlite(manifesto_path: Path) -> dict:
    """Verifica o manifesto E os bytes antes de oferecer restauração."""
    path = Path(manifesto_path).expanduser().resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        nome = manifest["arquivo"]
        expected = manifest["sha256"]
        if manifest["formato"] != "DCA-SQLITE-BACKUP-1":
            raise ErroBackupSQLite("Formato de manifesto desconhecido.")
        if Path(nome).name != nome or not nome.endswith(".sqlite3"):
            raise ErroBackupSQLite("Nome de snapshot inválido no manifesto.")
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected.lower()):
            raise ErroBackupSQLite("Hash inválido no manifesto.")
        comprovacao = verificar_backup_sqlite(path.parent / nome, expected)
        return {**manifest, "verificacao": comprovacao}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        if isinstance(exc, ErroBackupSQLite):
            raise
        raise ErroBackupSQLite(f"Manifesto do backup inválido: {exc}") from exc


def publicar_arquivo_exclusivo(origem: Path, destino: Path):
    """Publish without overwrite, including filesystems lacking hard links.

    On failure remove only an output this call actually created; a concurrent
    destination belongs to someone else and MUST remain byte-for-byte intact.
    """
    owned = False
    try:
        try:
            os.link(origem, destino)
            owned = True
        except OSError:
            with destino.open("xb") as output:
                owned = True
                with origem.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        if _hash_sha256(origem) != _hash_sha256(destino):
            raise ErroBackupSQLite("Publicação de arquivo divergente da origem.")
    except Exception:
        if owned:
            destino.unlink(missing_ok=True)
        raise


def preparar_restauracao_sqlite(manifesto: Path, destino: Path) -> dict:
    """RECUPERA em arquivo separado; nunca troca DB ativo ou sobrescreve um arquivo.

    O usuário pode inspecionar e comparar este arquivo; só uma manutenção
    offline explícita pode adotá-lo como banco ativo.
    """
    verificado = verificar_manifesto_sqlite(manifesto)
    origem = Path(verificado["verificacao"]["arquivo"])
    destino = Path(destino).expanduser().resolve()
    if destino.exists():
        raise ErroBackupSQLite("Destino de recuperação já existe; nenhuma substituição permitida.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name("." + destino.name + "-" + secrets.token_hex(4) + ".tmp")
    published = False
    try:
        with origem.open("rb") as fonte, temporario.open("xb") as copia:
            for bloco in iter(lambda: fonte.read(1024 * 1024), b""):
                copia.write(bloco)
            copia.flush()
            os.fsync(copia.fileno())
        verificar_backup_sqlite(temporario, verificado["sha256"])
        publicar_arquivo_exclusivo(temporario, destino)
        published = True
        verificar_backup_sqlite(destino, verificado["sha256"])
        return {"preparado": str(destino), "sha256": verificado["sha256"],
                "ativado": False, "origem": str(origem)}
    except Exception:
        # Se verificação final falhar, não deixar arquivo anunciado como pronto.
        if published:
            destino.unlink(missing_ok=True)
        raise
    finally:
        temporario.unlink(missing_ok=True)
