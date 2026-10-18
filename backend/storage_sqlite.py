"""Camada SQLite transacional e importação conservadora do CSV legado."""
from __future__ import annotations

import csv
import hashlib
import json
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from contextlib import closing
from decimal import Decimal, InvalidOperation

COLUNAS = ("Data", "Moeda", "Operacao", "Valor_USDT", "Preco", "Quantidade", "Taxa_BRL")
CAMPO_FEE = "Taxa_Corretagem_USDT"
COLUNAS_EXPORTACAO = COLUNAS + (CAMPO_FEE,)


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
    fee = item.get(CAMPO_FEE)
    d[CAMPO_FEE] = None if fee is None or str(fee).strip() == "" else str(fee).strip()
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
        if set(headers) - set(COLUNAS_EXPORTACAO):
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
    def __init__(self, diretorio: Path, arquivo_legado: Path | None, *,
                 auto_importar_legado: bool = True):
        self.diretorio = Path(diretorio).expanduser().resolve()
        self.diretorio.mkdir(parents=True, exist_ok=True)
        self.arquivo_legado = Path(arquivo_legado).expanduser().resolve() if arquivo_legado else None
        self.arquivo_db = self.diretorio / "portfolio.sqlite3"
        self._inicializar()
        if (auto_importar_legado and self.arquivo_legado is not None
                and self.arquivo_legado.is_file()):
            self.importar_csv(self.arquivo_legado)

    def _conectar(self):
        conn = sqlite3.connect(str(self.arquivo_db), timeout=20, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=20000")
            conn.execute("PRAGMA synchronous=FULL")
            return conn
        except Exception:
            # Windows holds SQLite files while a handle is open. Corrupt
            # database pragmas must not leak a connection or lock the file.
            conn.close()
            raise

    def _inicializar(self):
        # Schema migrations require a verifiable snapshot BEFORE any ALTER.
        if self.arquivo_db.is_file() and self.arquivo_db.stat().st_size:
            with closing(sqlite3.connect(self.arquivo_db.as_uri() + "?mode=ro", uri=True)) as verify:
                version = verify.execute("PRAGMA user_version").fetchone()[0]
            if version < 6:
                from backend.backup_sqlite import criar_backup_sqlite
                criar_backup_sqlite(
                    self.arquivo_db, self.diretorio / "backups" / "sqlite",
                    motivo=f"antes_schema_v{version}_para_v6",
                )
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
            cols = {r[1] for r in conn.execute("PRAGMA table_info(operacoes)")}
            if "taxa_corretagem_usdt" not in cols:
                conn.execute("ALTER TABLE operacoes ADD COLUMN taxa_corretagem_usdt TEXT")
            conn.execute("""CREATE TABLE IF NOT EXISTS posicoes_iniciais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_posicao TEXT NOT NULL,
                moeda TEXT NOT NULL,
                quantidade TEXT NOT NULL,
                custodia TEXT NOT NULL,
                custo_total_usdt TEXT,
                observacao TEXT NOT NULL DEFAULT '',
                criado_em_utc TEXT NOT NULL,
                UNIQUE(moeda, custodia)
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS posicoes_externas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_posicao TEXT NOT NULL,
                moeda TEXT NOT NULL,
                quantidade TEXT NOT NULL,
                custodia TEXT NOT NULL,
                custo_total_usdt TEXT,
                observacao TEXT NOT NULL DEFAULT '',
                confirmacao_independente TEXT NOT NULL,
                criado_em_utc TEXT NOT NULL,
                UNIQUE(moeda, custodia)
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS ajustes_posicoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tabela_origem TEXT NOT NULL,
                id_posicao INTEGER NOT NULL,
                antes_json TEXT NOT NULL,
                depois_json TEXT NOT NULL,
                motivo TEXT NOT NULL,
                alterado_em_utc TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS movimentacoes_custodia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_utc TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('transferencia','venda')),
                moeda TEXT NOT NULL,
                origem TEXT NOT NULL,
                destino TEXT NOT NULL,
                quantidade TEXT NOT NULL,
                taxa_ativo TEXT NOT NULL,
                receita_usdt TEXT NOT NULL,
                taxa_usdt TEXT NOT NULL,
                observacao TEXT NOT NULL,
                criado_em_utc TEXT NOT NULL
            )""")
            conn.execute("PRAGMA user_version=6")
        finally:
            conn.close()

    def _conferir_origem(self):
        """Verifica o CSV EFETIVAMENTE importado, não um nome padrão do pacote."""
        con = self._conectar()
        try:
            registro = con.execute(
                "SELECT sha256, caminho_origem, caminho_backup "
                "FROM importacoes_legadas LIMIT 1"
            ).fetchone()
        finally:
            con.close()
        if registro is None:
            return
        sha, origem, backup = registro
        original = Path(origem)
        if original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest() != sha:
            raise ErroMigracao(
                "CSV legado modificado após a migração. Preserve os dois arquivos "
                "e faça conciliação antes de continuar."
            )
        copia = Path(backup)
        if not copia.is_file() or hashlib.sha256(copia.read_bytes()).hexdigest() != sha:
            raise ErroMigracao(
                "Backup legado original ausente ou modificado; não substituir "
                "nem regenerar o arquivo silenciosamente."
            )

    @staticmethod
    def _inserir(con, row: dict[str, str]):
        con.execute(
            "INSERT INTO operacoes (data, moeda, operacao, valor_usdt, preco, "
            "quantidade, taxa_brl, taxa_corretagem_usdt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(row[campo] for campo in COLUNAS) + (row.get(CAMPO_FEE),))

    def importar_csv(self, origem: Path, *, sha256_esperado: str | None = None) -> int:
        origem = Path(origem).expanduser().resolve()
        if not origem.is_file():
            raise ErroMigracao(f"CSV não encontrado: {origem}")
        dados = origem.read_bytes()
        sha = hashlib.sha256(dados).hexdigest()
        if sha256_esperado is not None and sha != sha256_esperado:
            raise ErroMigracao("CSV mudou após prévia; migração cancelada.")
        rows = _ler_csv_bytes(dados)
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            anterior = con.execute(
                "SELECT sha256, caminho_origem, caminho_backup "
                "FROM importacoes_legadas LIMIT 1"
            ).fetchone()
            if anterior is not None:
                if anterior[:2] == (sha, str(origem)):
                    # After successful migration, a missing/corrupt backup is
                    # evidence to report, not permission to silently recreate it.
                    backup_original = Path(anterior[2])
                    if (not backup_original.is_file()
                        or hashlib.sha256(backup_original.read_bytes()).hexdigest() != sha):
                        raise ErroMigracao(
                            "Backup original ausente ou alterado. "
                            "Verifique e restaure a cópia; não recriar automaticamente."
                        )
                    con.execute("COMMIT")
                    return 0
                raise ErroMigracao("CSV legado diferente do registrado (alterado ou origem distinta); não misturar dados.")
            if (con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0]
                or con.execute("SELECT COUNT(*) FROM posicoes_iniciais").fetchone()[0]
                or con.execute("SELECT COUNT(*) FROM posicoes_externas").fetchone()[0]):
                raise ErroMigracao(
                    "Banco contém operações ou saldos iniciais; "
                    "não misturar migração CSV com outro ponto de partida."
                )
            backup = _backup(dados, self.diretorio / "backups", sha)
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

    def prever_importacao_csv(self, origem: Path) -> dict:
        """Prévia somente leitura: confere linhas, símbolos, hash e banco alvo."""
        origem = Path(origem).expanduser().resolve()
        if not origem.is_file():
            raise ErroMigracao(f"CSV não encontrado: {origem}")
        dados = origem.read_bytes()
        linhas = _ler_csv_bytes(dados)  # Falha antes de qualquer mutação.
        con = self._conectar()
        try:
            usadas = con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0]
            abertas = con.execute(
                "SELECT (SELECT COUNT(*) FROM posicoes_iniciais) + "
                "(SELECT COUNT(*) FROM posicoes_externas)"
            ).fetchone()[0]
            migrado = con.execute(
                "SELECT sha256 FROM importacoes_legadas LIMIT 1"
            ).fetchone()
        finally:
            con.close()
        sha = hashlib.sha256(dados).hexdigest()
        if migrado or usadas or abertas:
            raise ErroMigracao(
                "Este banco já está em uso: não importar sobre registros existentes."
            )
        return {
            "arquivo": str(origem), "sha256": sha, "quantidade": len(linhas),
            "moedas": sorted({r["Moeda"].upper() for r in linhas}),
            "primeira_data": min((r["Data"] for r in linhas), default=None),
            "ultima_data": max((r["Data"] for r in linhas), default=None),
            "destino_vazio": True,
            "duplicatas_identicas": len(linhas) - len({
                tuple(r.get(c) for c in COLUNAS_EXPORTACAO) for r in linhas
            }),
        }

    def importar_csv_conferido(self, origem: Path, sha256_confirmado: str) -> dict:
        """Não aceita troca silenciosa de CSV entre prévia e confirmação."""
        preview = self.prever_importacao_csv(origem)
        if preview["sha256"] != sha256_confirmado:
            raise ErroMigracao("CSV mudou depois da prévia; verifique novamente.")
        linhas = self.importar_csv(origem, sha256_esperado=sha256_confirmado)
        if linhas != preview["quantidade"]:
            raise ErroMigracao("Contagem final divergente. Verifique o banco.")
        diagnostico = self.diagnostico_integridade()
        if diagnostico["status"] != "OK" or not diagnostico["backup_valido"]:
            raise ErroMigracao("Migração concluída sem backup íntegro — acesso bloqueado.")
        try:
            from backend.backup_sqlite import criar_backup_sqlite
            snapshot = criar_backup_sqlite(
                self.arquivo_db, self.diretorio / "backups" / "sqlite",
                motivo="depois_importacao_csv",
            )
            snapshot_path, aviso = snapshot["manifesto"], None
        except Exception as exc:
            # Importação já foi COMMITADA e o CSV original tem backup por hash.
            # NUNCA mentir que a migração foi revertida só porque backup falhou.
            snapshot_path, aviso = None, (
                "Importação gravada, mas backup SQLite falhou: " + str(exc)
            )
        return {**preview, "importadas": linhas, "backup_valido": True,
                "backup_sqlite": snapshot_path, "aviso_backup_sqlite": aviso,
                "banco": str(self.arquivo_db)}

    def informar_custo_inicial(self, moeda: str, custodia: str,
                              custo_total_usdt: str) -> dict:
        try:
            custo = Decimal(str(custo_total_usdt))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ErroArmazenamento("Custo total inválido.") from exc
        if not custo.is_finite() or custo <= 0:
            raise ErroArmazenamento("Informe custo total positivo e documentado em USDT.")
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT id FROM posicoes_iniciais WHERE moeda=? AND custodia=?",
                (moeda.strip().upper(), custodia.strip()),
            ).fetchone()
            if row is None:
                raise ErroArmazenamento("Saldo inicial não encontrado.")
            con.execute(
                "UPDATE posicoes_iniciais SET custo_total_usdt=? WHERE id=?",
                (str(custo), row[0]),
            )
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

        try:
            from backend.backup_sqlite import criar_backup_sqlite
            snapshot = criar_backup_sqlite(
                self.arquivo_db, self.diretorio / "backups" / "sqlite",
                motivo="depois_custo_inicial",
            )
            return {"gravado": True, "backup_sqlite": snapshot["manifesto"],
                    "aviso_backup_sqlite": None}
        except Exception as exc:
            return {"gravado": True, "backup_sqlite": None,
                    "aviso_backup_sqlite": "Custo registrado, mas backup falhou: " + str(exc)}

    @staticmethod
    def _validar_lote(moeda, quantidade, custodia, data_posicao, custo_total_usdt):
        ativo = str(moeda).strip().upper()
        local = str(custodia).strip()
        if not (2 <= len(ativo) <= 12 and ativo.isascii() and ativo.isalnum()):
            raise ErroArmazenamento("Código de ativo inválido.")
        if not local or len(local) > 80:
            raise ErroArmazenamento("Custódia precisa ter entre 1 e 80 caracteres.")
        try:
            data = datetime.strptime(str(data_posicao), "%Y-%m-%d").date()
            if data > datetime.now(timezone.utc).date():
                raise ValueError("future")
            qtd = Decimal(str(quantidade))
            custo = (None if custo_total_usdt is None
                     or str(custo_total_usdt).strip() == ""
                     else Decimal(str(custo_total_usdt)))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ErroArmazenamento("Data, quantidade ou custo inválido.") from exc
        if not qtd.is_finite() or qtd <= 0:
            raise ErroArmazenamento("Quantidade deve ser finita e positiva.")
        if custo is not None and (not custo.is_finite() or custo <= 0):
            raise ErroArmazenamento("Custo deve ser positivo ou não informado.")
        return ativo, str(qtd), local, data.isoformat(), (
            str(custo) if custo is not None else None
        )

    def listar_posicoes_externas(self) -> list[dict]:
        """Saldos comprovadamente FORA do CSV; nunca participam de vendas do livro."""
        self._conferir_origem()
        con = self._conectar()
        try:
            rows = con.execute(
                "SELECT id,data_posicao,moeda,quantidade,custodia,"
                "custo_total_usdt,observacao,confirmacao_independente "
                "FROM posicoes_externas ORDER BY id"
            ).fetchall()
        finally:
            con.close()
        return [dict(zip(
            ("ID","Data","Moeda","Quantidade","Custodia","Custo_Total_USDT",
             "Observacao","Declaracao_Independente"), row,
        )) for row in rows]

    def registrar_posicao_externa(
        self, *, moeda: str, quantidade: str, custodia: str,
        data_posicao: str, custo_total_usdt: str | None = None,
        confirmacao_independente: bool = False, observacao: str = "",
    ) -> dict:
        """Apenas saldo adicional e declarado NÃO incluído no histórico."""
        if confirmacao_independente is not True:
            raise ErroArmazenamento(
                "Confirme que esta posição NÃO está incluída no CSV nem "
                "em outro saldo cadastrado. Não consolidar automaticamente."
            )
        ativo,qtd,local,data,custo = self._validar_lote(
            moeda, quantidade, custodia, data_posicao, custo_total_usdt
        )
        if len(observacao) > 500:
            raise ErroArmazenamento("Observação excede 500 caracteres.")
        self._conferir_origem()
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            ultima = con.execute(
                "SELECT MAX(substr(data,1,10)) FROM operacoes"
            ).fetchone()[0]
            if ultima is not None and data < ultima:
                raise ErroArmazenamento(
                    "Data do saldo externo antecede operações do CSV. "
                    "Use uma data de conferência posterior ao histórico."
                )
            if con.execute(
                "SELECT COUNT(*) FROM posicoes_iniciais "
                "WHERE moeda=? AND custodia=?", (ativo,local)
            ).fetchone()[0]:
                raise ErroArmazenamento("Mesmo ativo e custódia já têm saldo inicial.")
            con.execute(
                "INSERT INTO posicoes_externas "
                "(data_posicao,moeda,quantidade,custodia,custo_total_usdt,"
                "observacao,confirmacao_independente,criado_em_utc) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (data,ativo,qtd,local,custo,observacao,
                 "DECLARADO_FORA_DO_CSV",datetime.now(timezone.utc).isoformat())
            )
            con.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise ErroArmazenamento(
                "Posição externa já cadastrada nesta custódia. "
                "Corrija o registro existente, não duplique."
            ) from exc
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        from backend.backup_sqlite import criar_backup_sqlite
        try:
            snap = criar_backup_sqlite(
                self.arquivo_db,self.diretorio/"backups"/"sqlite",
                motivo="depois_conciliacao_externa",
            )
            aviso, manifest = None, snap["manifesto"]
        except Exception as exc:
            aviso, manifest = "Saldo salvo; backup SQLite falhou: "+str(exc), None
        return {"moeda":ativo,"quantidade":qtd,"custodia":local,
                "custo_total_usdt":custo,"backup_sqlite":manifest,
                "aviso_backup_sqlite":aviso}

    @staticmethod
    def _movimentos_transacionais(conn) -> list[dict]:
        rows = conn.execute(
            "SELECT id,data_utc,tipo,moeda,origem,destino,quantidade,"
            "taxa_ativo,receita_usdt,taxa_usdt,observacao "
            "FROM movimentacoes_custodia ORDER BY id"
        ).fetchall()
        campos=("ID","Data","Tipo","Moeda","Origem","Destino",
                "Quantidade","Taxa_Ativo","Receita_USDT","Taxa_USDT","Observacao")
        return [dict(zip(campos,row)) for row in rows]

    @staticmethod
    def _externos_transacionais(conn) -> list[dict]:
        rows=conn.execute(
            "SELECT data_posicao,moeda,quantidade,custodia,custo_total_usdt "
            "FROM posicoes_externas ORDER BY id"
        ).fetchall()
        return [dict(zip(
            ("Data","Moeda","Quantidade","Custodia","Custo_Total_USDT"),row
        )) for row in rows]

    def listar_movimentos_custodia(self) -> list[dict]:
        self._conferir_origem()
        conn=self._conectar()
        try:
            return self._movimentos_transacionais(conn)
        finally:
            conn.close()

    def registrar_movimento_custodia(
        self, *, tipo:str, moeda:str, origem:str, destino:str, quantidade:str,
        data_utc:str, taxa_ativo:str, receita_usdt:str, taxa_usdt:str,
        observacao:str,
    ) -> dict:
        """Append immutable transfer/disposal, validate complete replay under lock."""
        from backend.custody_ledger import numero, apurar_custodia, ErroMovimentacaoCustodia
        tipo=tipo.strip().lower()
        ativo=moeda.strip().upper()
        origem=origem.strip()
        destino=destino.strip()
        if tipo not in ("transferencia","venda"):
            raise ErroArmazenamento("Tipo deve ser transferência ou venda externa.")
        if not (ativo.isascii() and ativo.isalnum() and 2<=len(ativo)<=12):
            raise ErroArmazenamento("Ativo inválido.")
        if not origem or not destino or len(origem)>80 or len(destino)>80:
            raise ErroArmazenamento("Informe origem e destino de custódia.")
        if not (8<=len(observacao.strip())<=500):
            raise ErroArmazenamento("Justificativa documental (8 a 500 caracteres) obrigatória.")
        try:
            dia=datetime.strptime(data_utc,"%Y-%m-%d").date()
            if dia > datetime.now(timezone.utc).date():
                raise ValueError("futuro")
            quant=numero(quantidade,"Quantidade")
            fee_coin=numero(taxa_ativo,"Taxa no ativo",allow_zero=True)
            fee_dollar=numero(taxa_usdt,"Taxa USDT",allow_zero=True)
            revenue=numero(receita_usdt,"Receita USDT",allow_zero=(tipo=="transferencia"))
        except (ValueError, TypeError) as exc:
            raise ErroArmazenamento("Data ou valores inválidos: "+str(exc)) from exc
        if tipo=="transferencia" and (revenue!=0 or fee_dollar!=0 or origem==destino):
            raise ErroArmazenamento("Transferência sem receita/corretagem USDT e entre locais distintos.")
        if tipo=="venda" and (ativo=="USDT" or revenue<=fee_dollar):
            raise ErroArmazenamento("Venda requer receita líquida positiva em USDT.")
        row={
            "Data":dia.isoformat(),"Tipo":tipo,"Moeda":ativo,
            "Origem":origem,"Destino":destino,"Quantidade":str(quant),
            "Taxa_Ativo":str(fee_coin),"Receita_USDT":str(revenue),
            "Taxa_USDT":str(fee_dollar),"Observacao":observacao.strip(),
        }
        self._conferir_origem()
        con=self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            opens=self._externos_transacionais(con)
            if not opens:
                raise ErroArmazenamento("Não existem saldos externos para movimentar.")
            # The opening snapshot is not a historical purchase: no backdating.
            datas=[str(p["Data"])[:10] for p in opens if p["Moeda"]==ativo]
            if not datas or dia.isoformat()<max(datas):
                raise ErroArmazenamento(
                    "Movimentação anterior à posição externa declarada."
                )
            earlier=self._movimentos_transacionais(con)
            latest=max((m["Data"][:10] for m in earlier if m["Moeda"]==ativo),
                       default=None)
            if latest and dia.isoformat()<latest:
                raise ErroArmazenamento(
                    "Movimentação anterior a um registro já confirmado; "
                    "não reordenar histórico financeiro."
                )
            from backend.custody_ledger import apurar_custodia
            apurar_custodia(opens,earlier+[row])
            con.execute(
                "INSERT INTO movimentacoes_custodia "
                "(data_utc,tipo,moeda,origem,destino,quantidade,taxa_ativo,"
                "receita_usdt,taxa_usdt,observacao,criado_em_utc) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (row["Data"]+"T12:00:00Z",tipo,ativo,origem,destino,
                 row["Quantidade"],row["Taxa_Ativo"],row["Receita_USDT"],
                 row["Taxa_USDT"],row["Observacao"],
                 datetime.now(timezone.utc).isoformat())
            )
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        try:
            from backend.backup_sqlite import criar_backup_sqlite
            snapshot=criar_backup_sqlite(
                self.arquivo_db,self.diretorio/"backups"/"sqlite",
                motivo="depois_movimento_custodia",
            )
            aviso,manifest=None,snapshot["manifesto"]
        except Exception as exc:
            aviso,manifest="Movimentação salva, backup posterior falhou: "+str(exc),None
        return {**row,"backup_sqlite":manifest,"aviso_backup_sqlite":aviso}

    def corrigir_posicao(
        self, *, origem: str, moeda: str, custodia: str,
        quantidade: str, custo_total_usdt: str | None,
        motivo: str,
    ) -> dict:
        """Mutação auditada com motivo e estado antes/depois na MESMA transação."""
        tabela = {"inicial":"posicoes_iniciais",
                  "externa":"posicoes_externas"}.get(origem)
        if tabela is None:
            raise ErroArmazenamento("Tipo de saldo inválido.")
        justificativa = motivo.strip()
        if len(justificativa) < 8 or len(justificativa) > 500:
            raise ErroArmazenamento("Descreva a correção (8 a 500 caracteres).")
        ativo,qtd,local,_,custo = self._validar_lote(
            moeda, quantidade, custodia,
            datetime.now(timezone.utc).date().isoformat(),
            custo_total_usdt,
        )
        from backend.backup_sqlite import criar_backup_sqlite
        # Before ANY edit, snapshot immutable and verified; no silent recovery.
        anterior = criar_backup_sqlite(
            self.arquivo_db, self.diretorio/"backups"/"sqlite",
            motivo="antes_corrigir_posicao",
        )
        self._conferir_origem()
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                f"SELECT id,data_posicao,moeda,quantidade,custodia,"
                f"custo_total_usdt,observacao FROM {tabela} "
                "WHERE moeda=? AND custodia=?", (ativo,local),
            ).fetchone()
            if row is None:
                raise ErroArmazenamento("Saldo não encontrado para corrigir.")
            keys=("id","Data","Moeda","Quantidade","Custodia","Custo_Total_USDT","Observacao")
            antes=dict(zip(keys,row))
            depois=dict(antes,Quantidade=qtd,Custo_Total_USDT=custo)
            if antes == depois:
                raise ErroArmazenamento("Valores iguais: nenhuma correção necessária.")
            con.execute(
                f"UPDATE {tabela} SET quantidade=?,custo_total_usdt=? WHERE id=?",
                (qtd,custo,row[0]),
            )
            if origem=="inicial":
                from backend.operation_integrity import validar_livro
                validar_livro(
                    self._livro_transacional(con), self._saldos_transacionais(con)
                )
            con.execute(
                "INSERT INTO ajustes_posicoes "
                "(tabela_origem,id_posicao,antes_json,depois_json,motivo,alterado_em_utc) "
                "VALUES (?,?,?,?,?,?)",
                (origem,row[0],json.dumps(antes,ensure_ascii=False),
                 json.dumps(depois,ensure_ascii=False),
                 justificativa,datetime.now(timezone.utc).isoformat())
            )
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        try:
            snap = criar_backup_sqlite(
                self.arquivo_db,self.diretorio/"backups"/"sqlite",
                motivo="depois_corrigir_posicao",
            )
            aviso,manifest=None,snap["manifesto"]
        except Exception as exc:
            aviso,manifest="Correção gravada, backup posterior falhou: "+str(exc),None
        return {"antes":antes,"depois":depois,"motivo":justificativa,
                "backup_antes":anterior["manifesto"],
                "backup_depois":manifest,"aviso_backup_sqlite":aviso}

    def listar_auditoria_posicoes(self) -> list[dict]:
        con = self._conectar()
        try:
            rows = con.execute(
                "SELECT tabela_origem,id_posicao,antes_json,depois_json,"
                "motivo,alterado_em_utc FROM ajustes_posicoes ORDER BY id"
            ).fetchall()
        finally:
            con.close()
        return [{"origem":r[0],"id_posicao":r[1],
                 "antes":json.loads(r[2]),"depois":json.loads(r[3]),
                 "motivo":r[4],"timestamp":r[5]} for r in rows]

    def listar_posicoes_iniciais(self) -> list[dict]:
        self._conferir_origem()
        con = self._conectar()
        try:
            rows = con.execute(
                "SELECT data_posicao, moeda, quantidade, custodia, "
                "custo_total_usdt, observacao FROM posicoes_iniciais ORDER BY id"
            ).fetchall()
        finally:
            con.close()
        return [dict(zip(
            ("Data", "Moeda", "Quantidade", "Custodia", "Custo_Total_USDT", "Observacao"), r
        )) for r in rows]

    def registrar_posicao_inicial(
        self, *, moeda: str, quantidade: str, custodia: str,
        data_posicao: str, custo_total_usdt: str | None = None,
        observacao: str = "",
    ) -> dict:
        """Não cria operação fictícia de compra ou aporte em USDT."""
        ativo = moeda.strip().upper()
        local = custodia.strip()
        if (not 2 <= len(ativo) <= 12 or not ativo.isascii()
                or not ativo.isalnum()):
            raise ErroArmazenamento("Código do ativo inválido.")
        if not local or len(local) > 80:
            raise ErroArmazenamento("Informe corretora ou carteira (até 80 caracteres).")
        if len(observacao) > 500:
            raise ErroArmazenamento("Observação excede 500 caracteres.")
        try:
            data = datetime.strptime(data_posicao, "%Y-%m-%d").date()
            if data > datetime.now(timezone.utc).date():
                raise ValueError("data futura")
        except ValueError as exc:
            raise ErroArmazenamento("Informe uma data de posição válida, não futura.") from exc
        try:
            qtd = Decimal(str(quantidade))
            custo = (
                None if custo_total_usdt is None or str(custo_total_usdt).strip() == ""
                else Decimal(str(custo_total_usdt))
            )
        except (ValueError, InvalidOperation, TypeError) as exc:
            raise ErroArmazenamento("Quantidade ou custo inválido.") from exc
        if not qtd.is_finite() or qtd <= 0:
            raise ErroArmazenamento("Quantidade inicial deve ser positiva.")
        if custo is not None and (not custo.is_finite() or custo <= 0):
            raise ErroArmazenamento("Custo total deve ser positivo ou ficar em branco.")
        self._conferir_origem()
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0]:
                raise ErroArmazenamento(
                    "Saldo inicial somente antes do primeiro lançamento. "
                    "Não inventar compras para conciliar operações antigas."
                )
            if con.execute("SELECT COUNT(*) FROM posicoes_externas").fetchone()[0]:
                raise ErroArmazenamento(
                    "Já há posição externa: cadastro inicial separado requer "
                    "conciliação antes de alterar a origem."
                )
            if con.execute("SELECT COUNT(*) FROM importacoes_legadas").fetchone()[0]:
                raise ErroArmazenamento(
                    "Histórico CSV já migrado: não somar saldos iniciais "
                    "que podem duplicar posições. Exige conciliação específica."
                )
            con.execute(
                "INSERT INTO posicoes_iniciais "
                "(data_posicao,moeda,quantidade,custodia,custo_total_usdt,"
                "observacao,criado_em_utc) VALUES (?,?,?,?,?,?,?)",
                (data.isoformat(), ativo, str(qtd), local,
                 str(custo) if custo is not None else None,
                 observacao, datetime.now(timezone.utc).isoformat()),
            )
            con.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise ErroArmazenamento(
                "Ativo já registrado nesse local. Não duplicar saldo; "
                "conferir e corrigir o cadastro antes de prosseguir."
            ) from exc
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        try:
            from backend.backup_sqlite import criar_backup_sqlite
            snapshot = criar_backup_sqlite(
                self.arquivo_db, self.diretorio / "backups" / "sqlite",
                motivo="depois_saldo_inicial",
            )
            aviso_backup = None
        except Exception as exc:
            snapshot = None
            aviso_backup = (
                "Posição gravada, mas não foi possível verificar o backup SQLite: "
                + str(exc)
            )
        return {"moeda": ativo, "quantidade": str(qtd), "custodia": local,
                "custo_total_usdt": str(custo) if custo is not None else None,
                "backup_sqlite": snapshot["manifesto"] if snapshot else None,
                "aviso_backup_sqlite": aviso_backup}

    def listar_preciso(self) -> list[dict]:
        """Mantém valores decimais como texto original para análise histórica."""
        self._conferir_origem()
        con = self._conectar()
        try:
            rows = con.execute(
                "SELECT data, moeda, operacao, valor_usdt, preco, quantidade, "
                "taxa_brl, taxa_corretagem_usdt FROM operacoes ORDER BY id"
            ).fetchall()
        finally:
            con.close()
        return [dict(zip(COLUNAS_EXPORTACAO, row)) for row in rows]

    def listar(self) -> list[dict]:
        self._conferir_origem()
        con = self._conectar()
        try:
            rows = con.execute(
                "SELECT data, moeda, operacao, valor_usdt, preco, quantidade, "
                "taxa_brl, taxa_corretagem_usdt FROM operacoes ORDER BY id").fetchall()
        finally:
            con.close()
        return [{
            "Data": row[0], "Moeda": row[1], "Operacao": row[2],
            "Valor_USDT": float(row[3]), "Preco": row[4],
            "Quantidade": float(row[5]), "Taxa_BRL": float(row[6]),
            CAMPO_FEE: row[7],
        } for row in rows]

    @staticmethod
    def _id_por_indice(con, indice: int):
        if not isinstance(indice, int) or indice < 0:
            return None
        row = con.execute("SELECT id FROM operacoes ORDER BY id LIMIT 1 OFFSET ?", (indice,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _saldos_transacionais(con) -> list[dict]:
        rows = con.execute(
            "SELECT data_posicao,moeda,quantidade,custodia,custo_total_usdt,observacao "
            "FROM posicoes_iniciais ORDER BY id"
        ).fetchall()
        return [dict(zip(
            ("Data", "Moeda", "Quantidade", "Custodia", "Custo_Total_USDT", "Observacao"), row
        )) for row in rows]

    @staticmethod
    def _livro_transacional(con) -> list[dict]:
        """Estado completo lido sob o lock de gravação da MESMA transação."""
        linhas = con.execute(
            "SELECT data, moeda, operacao, valor_usdt, preco, quantidade, "
            "taxa_brl, taxa_corretagem_usdt FROM operacoes ORDER BY id"
        ).fetchall()
        return [dict(zip(COLUNAS_EXPORTACAO, linha)) for linha in linhas]

    def diagnostico_livro_legado(self) -> dict:
        """Relatório apenas consultivo: importação CSV NÃO reescreve nem rejeita legado."""
        from backend.operation_integrity import validar_livro, ErroIntegridadeFinanceira
        historico = self.listar_preciso()
        try:
            validar_livro(historico, self.listar_posicoes_iniciais())
        except ErroIntegridadeFinanceira as exc:
            return {"consistente": False, "erro": str(exc), "registros": len(historico)}
        return {"consistente": True, "erro": None, "registros": len(historico)}

    def inserir(self, valores: list) -> bool:
        if len(valores) not in (len(COLUNAS), len(COLUNAS_EXPORTACAO)):
            raise ErroArmazenamento("Quantidade incorreta de campos.")
        row = _validar(dict(zip(COLUNAS_EXPORTACAO, valores)), 0)
        self._conferir_origem()
        from backend.operation_integrity import validar_livro
        con = self._conectar()
        try:
            con.execute("BEGIN IMMEDIATE")
            livro = self._livro_transacional(con)
            validar_livro(livro + [row], self._saldos_transacionais(con))
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
            validar_livro(livro, self._saldos_transacionais(con))
            con.execute(
                "UPDATE operacoes SET data=?, moeda=?, operacao=?, valor_usdt=?, "
                "preco=?, quantidade=?, taxa_brl=?, taxa_corretagem_usdt=? WHERE id=?",
                tuple(row[campo] for campo in COLUNAS) + (row.get(CAMPO_FEE), id_operacao,))
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
            validar_livro(livro, self._saldos_transacionais(con))
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

        saldos_abertura = con = None
        con2 = self._conectar()
        try:
            saldos_abertura = con2.execute(
                "SELECT COUNT(*) FROM posicoes_iniciais"
            ).fetchone()[0]
        finally:
            con2.close()
        resultado = {
            "saldos_iniciais": saldos_abertura,
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
        con = self._conectar()
        try:
            registrado = con.execute(
                "SELECT caminho_origem, caminho_backup "
                "FROM importacoes_legadas LIMIT 1"
            ).fetchone()
        finally:
            con.close()
        protegidos = {
            p.resolve() for p in [self.arquivo_legado] if p is not None
        }
        if registrado:
            protegidos.update(Path(x).resolve() for x in registrado)
        if destino in protegidos:
            raise ErroArmazenamento(
                "Proibido sobrescrever CSV original ou backup da migração."
            )
        rows = self.listar_preciso()
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("x", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUNAS_EXPORTACAO)
            writer.writeheader()
            writer.writerows(rows)
