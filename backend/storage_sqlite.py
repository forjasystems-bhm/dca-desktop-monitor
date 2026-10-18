"""Camada SQLite transacional e importação conservadora do CSV legado."""
from __future__ import annotations

import csv
import hashlib
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

COLUNAS = ("Data", "Moeda", "Operacao", "Valor_USDT", "Preco", "Quantidade", "Taxa_BRL")


class ErroArmazenamento(RuntimeError):
    """O sistema não deve encobrir falhas de integridade dos dados."""


class ErroMigracao(ErroArmazenamento):
    """Origem legada requer revisão antes de importar/continuar."""


def diretorio_dados_padrao() -> Path:
    custom = os.environ.get("DCA_MONITOR_DATA_DIR")
    if custom:
        return Path(custom).expanduser().resolve()
    if getattr(sys, "frozen", False):
        pasta = Path(sys.executable).resolve().parent
        if (pasta / "DCA-PREVIEW-MODE").is_file():
            return pasta / "preview-data"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "DCA Desktop Monitor"
    root = os.environ.get("XDG_DATA_HOME")
    return (Path(root) if root else Path.home() / ".local" / "share") / "dca-desktop-monitor"


def _validar(item: dict, indice: int) -> dict[str, str]:
    if not isinstance(item, dict) or None in item:
        raise ErroMigracao(f"Linha {indice}: registro ou número de colunas inválido.")
    d = {k: str(item.get(k, "") if item.get(k) is not None else "").strip() for k in COLUNAS}
    for key in COLUNAS[:6]:
        if not d[key]:
            raise ErroMigracao(f"Linha {indice}: falta {key}.")
    try:
        if len(d["Data"]) != 19:
            raise ValueError("data incompleta")
        datetime.strptime(d["Data"], "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ErroMigracao(f"Linha {indice}: data inválida.") from exc
    d["Operacao"] = d["Operacao"].lower()
    if d["Operacao"] not in ("compra", "venda"):
        raise ErroMigracao(f"Linha {indice}: operação inválida.")
    for key in ("Valor_USDT", "Preco", "Quantidade", "Taxa_BRL"):
        val = d[key] or "0"
        try:
            numero = Decimal(val)
        except (InvalidOperation, ValueError) as exc:
            raise ErroMigracao(f"Linha {indice}: {key} não numérico.") from exc
        if not numero.is_finite() or (numero < 0 if key == "Taxa_BRL" else numero <= 0):
            raise ErroMigracao(f"Linha {indice}: {key} inválido.")
        d[key] = val
    return d


def _ler_csv_bytes(conteudo: bytes) -> list[dict[str, str]]:
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ErroMigracao("CSV sem codificação UTF-8 válida.") from exc
    try:
        reader = csv.DictReader(io.StringIO(texto, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers:
            raise ErroMigracao("CSV sem cabeçalho.")
        if len(headers) != len(set(headers)):
            raise ErroMigracao("CSV tem cabeçalhos repetidos.")
        if set(headers) - set(COLUNAS):
            raise ErroMigracao("CSV tem colunas desconhecidas.")
        if set(COLUNAS[:6]) - set(headers):
            raise ErroMigracao("CSV tem colunas obrigatórias ausentes.")
        return [_validar(op, indice) for indice, op in enumerate(reader, 2)]
    except csv.Error as exc:
        raise ErroMigracao("CSV malformado; importação cancelada.") from exc


def _backup(conteudo: bytes, pasta: Path, sha: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"legado-{sha}.csv"
    if arquivo.exists():
        if hashlib.sha256(arquivo.read_bytes()).hexdigest() != sha:
            raise ErroMigracao("Backup existente não confere com o hash.")
        return arquivo
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=pasta, prefix=".backup-", delete=False) as f:
            temporario = f.name
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, arquivo)
        if hashlib.sha256(arquivo.read_bytes()).hexdigest() != sha:
            raise ErroMigracao("Backup divergente após gravação.")
    finally:
        if temporario and os.path.exists(temporario):
            os.unlink(temporario)
    return arquivo


class ArmazemSQLite:
    def __init__(self, diretorio: Path, arquivo_legado: Path | None):
        self.diretorio = Path(diretorio).expanduser().resolve()
        self.diretorio.mkdir(parents=True, exist_ok=True)
        self.arquivo_legado = Path(arquivo_legado).expanduser().resolve() if arquivo_legado else None
        self.arquivo_db = self.diretorio / "portfolio.sqlite3"
        self._inicializar()
        if self.arquivo_legado is not None and self.arquivo_legado.is_file():
            self.importar_csv(self.arquivo_legado)

    def _conectar(self):
        conn = sqlite3.connect(str(self.arquivo_db), timeout=20, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=20000")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _inicializar(self):
        conn = self._conectar()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS operacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL, moeda TEXT NOT NULL, operacao TEXT NOT NULL,
                valor_usdt TEXT NOT NULL, preco TEXT NOT NULL,
                quantidade TEXT NOT NULL, taxa_brl TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS importacoes_legadas (
                sha256 TEXT PRIMARY KEY, caminho_origem TEXT NOT NULL,
                caminho_backup TEXT NOT NULL, quantidade_registros INTEGER NOT NULL,
                importado_em TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS cotacoes_historicas (
                data_utc TEXT NOT NULL,
                ativo TEXT NOT NULL,
                moeda_cotacao TEXT NOT NULL,
                preco TEXT NOT NULL,
                fonte TEXT NOT NULL,
                abertura_utc_ms INTEGER NOT NULL,
                capturado_em_utc TEXT NOT NULL,
                PRIMARY KEY (data_utc, ativo, moeda_cotacao)
            )""")
            conn.execute("PRAGMA user_version=2")
        finally:
            conn.close()

    def _conferir_origem(self):
        conn = self._conectar()
        try:
            registro = conn.execute(
                "SELECT sha256, caminho_origem FROM importacoes_legadas LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if registro and self.arquivo_legado and self.arquivo_legado.is_file():
            if str(self.arquivo_legado) != registro[1]:
                raise ErroMigracao("Há um CSV legado distinto; conciliação manual necessária.")
            if hashlib.sha256(self.arquivo_legado.read_bytes()).hexdigest() != registro[0]:
                raise ErroMigracao(
                    "CSV legado modificado após a migração. Não ignorar novas operações; "
                    "preserve os arquivos e concilie antes de continuar.")

    @staticmethod
    def _inserir(con, row: dict[str, str]):
        con.execute(
            "INSERT INTO operacoes (data, moeda, operacao, valor_usdt, preco, quantidade, taxa_brl) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuple(row[campo] for campo in COLUNAS))

    def importar_csv(self, origem: Path) -> int:
        origem = Path(origem).expanduser().resolve()
        if not origem.is_file():
            raise ErroMigracao(f"CSV não encontrado: {origem}")
        dados = origem.read_bytes()
        sha = hashlib.sha256(dados).hexdigest()
        rows = _ler_csv_bytes(dados)
        backup = _backup(dados, self.diretorio / "backups", sha)
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            anterior = con.execute(
                "SELECT sha256, caminho_origem FROM importacoes_legadas LIMIT 1"
            ).fetchone()
            if anterior is not None:
                if anterior == (sha, str(origem)):
                    con.execute("COMMIT")
                    return 0
                raise ErroMigracao("Já existe importação diferente; não misturar dados.")
            if con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0]:
                raise ErroMigracao("Banco contém operações; importação automática proibida.")
            for row in rows:
                self._inserir(con, row)
            con.execute(
                "INSERT INTO importacoes_legadas VALUES (?, ?, ?, ?, ?)",
                (sha, str(origem), str(backup), len(rows), datetime.now().isoformat(timespec="seconds")))
            if con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0] != len(rows):
                raise ErroMigracao("Contagem de linhas diverge; migração cancelada.")
            con.execute("COMMIT")
            return len(rows)
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def listar_preciso(self) -> list[dict]:
        """Mantém valores decimais como texto original para análise histórica."""
        self._conferir_origem()
        con = self._conectar()
        try:
            rows = con.execute(
                "SELECT data, moeda, operacao, valor_usdt, preco, quantidade, taxa_brl "
                "FROM operacoes ORDER BY id"
            ).fetchall()
        finally:
            con.close()
        return [dict(zip(COLUNAS, row)) for row in rows]

    def listar(self) -> list[dict]:
        self._conferir_origem()
        con = self._conectar()
        try:
            rows = con.execute(
                "SELECT data, moeda, operacao, valor_usdt, preco, quantidade, taxa_brl "
                "FROM operacoes ORDER BY id").fetchall()
        finally:
            con.close()
        return [{
            "Data": row[0], "Moeda": row[1], "Operacao": row[2],
            "Valor_USDT": float(row[3]), "Preco": row[4],
            "Quantidade": float(row[5]), "Taxa_BRL": float(row[6])
        } for row in rows]

    @staticmethod
    def _id_por_indice(con, indice: int):
        if not isinstance(indice, int) or indice < 0:
            return None
        row = con.execute("SELECT id FROM operacoes ORDER BY id LIMIT 1 OFFSET ?", (indice,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _livro_transacional(con) -> list[dict]:
        """Estado completo lido sob o lock de gravação da MESMA transação."""
        linhas = con.execute(
            "SELECT data, moeda, operacao, valor_usdt, preco, quantidade, taxa_brl "
            "FROM operacoes ORDER BY id"
        ).fetchall()
        return [dict(zip(COLUNAS, linha)) for linha in linhas]

    def diagnostico_livro_legado(self) -> dict:
        """Relatório apenas consultivo: importação CSV NÃO reescreve nem rejeita legado."""
        from backend.operation_integrity import validar_livro, ErroIntegridadeFinanceira
        historico = self.listar_preciso()
        try:
            validar_livro(historico)
        except ErroIntegridadeFinanceira as exc:
            return {"consistente": False, "erro": str(exc), "registros": len(historico)}
        return {"consistente": True, "erro": None, "registros": len(historico)}

    def inserir(self, valores: list) -> bool:
        if len(valores) != len(COLUNAS):
            raise ErroArmazenamento("Quantidade incorreta de campos.")
        row = _validar(dict(zip(COLUNAS, valores)), 0)
        self._conferir_origem()
        from backend.operation_integrity import validar_livro
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            livro = self._livro_transacional(con)
            validar_livro(livro + [row])
            self._inserir(con, row)
            con.execute("COMMIT")
            return True
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def substituir(self, indice: int, valores: dict) -> bool:
        row = _validar(valores, indice + 2)
        self._conferir_origem()
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            id_operacao = self._id_por_indice(con, indice)
            if id_operacao is None:
                con.execute("ROLLBACK")
                return False
            from backend.operation_integrity import validar_livro
            livro = self._livro_transacional(con)
            if livro[indice]["Moeda"].upper() != row["Moeda"].upper():
                from backend.operation_integrity import ErroIntegridadeFinanceira
                raise ErroIntegridadeFinanceira(
                    "A moeda de uma operação existente não pode ser alterada. "
                    "Exclua e registre novamente após verificar os saldos."
                )
            livro[indice] = row
            validar_livro(livro)
            con.execute(
                "UPDATE operacoes SET data=?, moeda=?, operacao=?, valor_usdt=?, "
                "preco=?, quantidade=?, taxa_brl=? WHERE id=?",
                tuple(row[campo] for campo in COLUNAS) + (id_operacao,))
            con.execute("COMMIT")
            return True
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def excluir(self, indice: int) -> bool:
        self._conferir_origem()
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            id_operacao = self._id_por_indice(con, indice)
            if id_operacao is None:
                con.execute("ROLLBACK")
                return False
            from backend.operation_integrity import validar_livro
            livro = self._livro_transacional(con)
            del livro[indice]
            validar_livro(livro)
            con.execute("DELETE FROM operacoes WHERE id=?", (id_operacao,))
            con.execute("COMMIT")
            return True
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def salvar_cotacoes_historicas(self, registros: list[dict], *, hoje_utc=None) -> int:
        """Lote ACID, registros imutáveis. Duplicata idêntica é idempotente."""
        from backend.historical_prices import validar_data_encerrada, ErroCotacaoHistorica
        from datetime import date as Date

        checados = []
        for r in registros:
            try:
                dia = Date.fromisoformat(r["data_utc"])
                validar_data_encerrada(dia, hoje_utc)
                ativo = str(r["ativo"]).strip().upper()
                if not ativo.isascii() or not ativo.isalnum() or ativo == "USDT":
                    raise ValueError("ativo inválido")
                if r["moeda_cotacao"] != "USDT":
                    raise ValueError("par de cotação diferente de USDT")
                if r["fonte"] != "Binance/CCXT:OHLCV:1d:close":
                    raise ValueError("fonte não identificada/permitida")
                preco = Decimal(str(r["preco"]))
                if not preco.is_finite() or preco <= 0:
                    raise ValueError("preço não positivo/finito")
                esperado_ms = int(datetime.combine(
                    dia, datetime.min.time(), timezone.utc
                ).timestamp() * 1000)
                if r["abertura_utc_ms"] != esperado_ms:
                    raise ValueError("instante do candle não corresponde à data")
                origem = datetime.fromisoformat(r["capturado_em_utc"])
                if origem.tzinfo is None or origem.utcoffset() != timedelta(0):
                    raise ValueError("captura sem fuso horário")
            except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError) as exc:
                raise ErroCotacaoHistorica(f"Registro histórico inválido: {exc}") from exc
            checados.append((
                dia.isoformat(), ativo, "USDT", str(preco),
                r["fonte"], esperado_ms, r["capturado_em_utc"]
            ))
        if not checados:
            return 0
        self._conferir_origem()
        con = self._conectar()
        inseridos = 0
        try:
            con.execute("BEGIN IMMEDIATE")
            for row in checados:
                antigo = con.execute(
                    "SELECT preco, fonte, abertura_utc_ms FROM cotacoes_historicas "
                    "WHERE data_utc=? AND ativo=? AND moeda_cotacao=?",
                    row[:3],
                ).fetchone()
                if antigo:
                    if (Decimal(antigo[0]) != Decimal(row[3])
                        or antigo[1] != row[4] or antigo[2] != row[5]):
                        raise ErroCotacaoHistorica(
                            f"Cotação {row[1]} em {row[0]} já registrada com valor/origem diferente."
                        )
                    continue
                con.execute(
                    "INSERT INTO cotacoes_historicas (data_utc, ativo, moeda_cotacao, "
                    "preco, fonte, abertura_utc_ms, capturado_em_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)", row,
                )
                inseridos += 1
            con.execute("COMMIT")
            return inseridos
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def ler_cotacoes_historicas(self, data_utc) -> dict:
        """SOMENTE banco local; não consulta nem reutiliza o cache da Binance."""
        from datetime import date as Date
        dia = data_utc if isinstance(data_utc, Date) else Date.fromisoformat(data_utc)
        if isinstance(dia, datetime):
            raise ValueError("É necessária uma data, não um timestamp.")
        self._conferir_origem()
        con = self._conectar()
        try:
            linhas = con.execute(
                "SELECT ativo, preco, fonte, abertura_utc_ms, capturado_em_utc "
                "FROM cotacoes_historicas WHERE data_utc=? AND moeda_cotacao='USDT'",
                (dia.isoformat(),)
            ).fetchall()
        finally:
            con.close()
        return {
            a: {
                "preco": Decimal(p), "fonte": f, "abertura_utc_ms": o,
                "capturado_em_utc": c, "data_utc": dia.isoformat(),
            }
            for a, p, f, o, c in linhas
        }

    def quantidade_usdc_de_origem_legada(self) -> int:
        """Identifica USDC importado sem classificação explícita de contraparte.

        Operações originais mantêm seu id do lote inicial; novas operações
        possuem ids posteriores e não são confundidas com o histórico legado.
        """
        self._conferir_origem()
        con = self._conectar()
        try:
            row = con.execute(
                "SELECT quantidade_registros FROM importacoes_legadas LIMIT 1"
            ).fetchone()
            if row is None:
                return 0
            return con.execute(
                "SELECT COUNT(*) FROM operacoes "
                "WHERE id <= ? AND UPPER(moeda) = 'USDC'",
                (row[0],)
            ).fetchone()[0]
        finally:
            con.close()

    def diagnostico_integridade(self) -> dict:
        """Lê o estado do SQLite e confere proveniência do backup, sem alterar dados."""
        con = self._conectar()
        try:
            integridade = con.execute("PRAGMA quick_check").fetchone()[0]
            total_atual = con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0]
            importacao = con.execute(
                "SELECT sha256, caminho_origem, caminho_backup, quantidade_registros "
                "FROM importacoes_legadas LIMIT 1"
            ).fetchone()
        finally:
            con.close()

        resultado = {
            "banco": str(self.arquivo_db),
            "integridade_sqlite": integridade,
            "operacoes_atuais": total_atual,
            "importacao": bool(importacao),
            "operacoes_importadas": 0,
            "backup_valido": None,
            "csv_original": "não importado",
            "status": "OK" if integridade == "ok" else "FALHA",
        }
        if not importacao:
            return resultado

        sha, origem, backup, quantidade = importacao
        arquivo_backup = Path(backup)
        backup_valido = (
            arquivo_backup.is_file()
            and hashlib.sha256(arquivo_backup.read_bytes()).hexdigest() == sha
        )
        arquivo_origem = Path(origem)
        if arquivo_origem.is_file():
            sha_atual = hashlib.sha256(arquivo_origem.read_bytes()).hexdigest()
            status_csv = "preservado" if sha_atual == sha else "ALTERADO"
        else:
            status_csv = "movido/ausente"

        resultado.update(
            operacoes_importadas=quantidade,
            backup_valido=backup_valido,
            csv_original=status_csv,
            hash_legado=sha,
        )
        if not backup_valido or status_csv == "ALTERADO":
            resultado["status"] = "FALHA"
        return resultado

    def exportar_csv(self, destino: Path):
        destino = Path(destino).expanduser().resolve()
        if self.arquivo_legado and destino == self.arquivo_legado:
            raise ErroArmazenamento("Proibido sobrescrever o CSV legado.")
        rows = self.listar()
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("x", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUNAS)
            writer.writeheader()
            writer.writerows(rows)
