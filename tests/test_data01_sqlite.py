"""Regressões de DATA-01 — migração segura e escrita transacional."""
import csv
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.backend import DataManager
from backend.storage_sqlite import ErroMigracao, ErroArmazenamento


CABECALHO = "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
COMPRA = "2026-01-01 10:00:00,BTC,compra,100,1000,0.1,5.25\n"
VENDA = "2026-01-02 10:00:00,BTC,venda,120,1200,0.1,5.30\n"


class Data01Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.data_dir = self.base / "dados"
        self.csv = self.base / "legado" / "db" / "meu_diario_operacoes.csv"
        self.csv.parent.mkdir(parents=True)
        self.csv.write_text(CABECALHO + COMPRA + VENDA, encoding="utf-8")

    def app(self, origem=None, pasta=None):
        return DataManager(data_dir=pasta or self.data_dir,
                           legacy_csv=origem if origem is not None else self.csv)

    def test_importacao_preserva_bytes_e_cria_backup_auditavel(self):
        conteudo = self.csv.read_bytes()
        d = self.app()
        ops = d.carregar_operacoes()
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]["Quantidade"], 0.1)
        self.assertEqual(ops[1]["Valor_USDT"], 120.0)
        self.assertEqual(self.csv.read_bytes(), conteudo)
        sha = hashlib.sha256(conteudo).hexdigest()
        backup = self.data_dir / "backups" / ("legado-" + sha + ".csv")
        self.assertEqual(backup.read_bytes(), conteudo)
        with closing(sqlite3.connect(d.arquivo_db)) as con:
            self.assertEqual(con.execute("SELECT sha256, quantidade_registros FROM importacoes_legadas").fetchone(), (sha, 2))
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_reabertura_idempotente_nao_duplica_historico(self):
        primeiro = self.app()
        segundo = self.app()
        self.assertEqual(primeiro.carregar_operacoes(), segundo.carregar_operacoes())
        self.assertEqual(len(segundo.carregar_operacoes()), 2)

    def test_banco_persiste_apos_csv_ser_movido(self):
        self.app()
        self.csv.rename(self.csv.with_suffix(".csv.bak"))
        self.assertEqual(len(self.app().carregar_operacoes()), 2)

    def test_modificacao_do_csv_antigo_bloqueia_leitura_e_nova_gravacao(self):
        d = self.app()
        self.csv.write_text(CABECALHO + COMPRA + VENDA + COMPRA, encoding="utf-8")
        with self.assertRaisesRegex(ErroMigracao, "modificado"):
            d.carregar_operacoes()
        self.assertFalse(d.salvar_operacao(["2026-01-03 10:00:00", "ETH", "compra", 50, 500, 0.1, 5.0]))
        with closing(sqlite3.connect(d.arquivo_db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0], 2)

    def test_csv_invalido_nao_produz_migracao_parcial(self):
        texto = CABECALHO + COMPRA + "2026-02-01 10:00:00,BTC,compra,INVALIDO,500,1,5\n"
        self.csv.write_text(texto, encoding="utf-8")
        with self.assertRaisesRegex(ErroMigracao, "Valor_USDT"):
            self.app()
        with closing(sqlite3.connect(self.data_dir / "portfolio.sqlite3")) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM importacoes_legadas").fetchone()[0], 0)
        self.assertEqual(self.csv.read_text(encoding="utf-8"), texto)

    def test_edicao_exclusao_e_inclusao_persistem_sem_alterar_csv(self):
        d = self.app()
        # Migração importa o legado fielmente, mesmo se seus aportes faltarem.
        # Um depósito retroativo concilia o livro sem tocar no CSV original.
        self.assertTrue(d.salvar_operacao([
            "2025-12-31 10:00:00", "USDT", "compra", 500, 5, 500, 5
        ]))
        nova = dict(d.carregar_operacoes()[0])
        nova["Valor_USDT"] = "120"
        nova["Preco"] = "1200"
        self.assertTrue(d.atualizar_operacao(0, nova, motivo="Justificativa sintética do teste"))
        self.assertEqual(d.carregar_operacoes()[0]["Valor_USDT"], 120)
        self.assertTrue(d.excluir_operacao(1, motivo="Justificativa sintética do teste"))
        self.assertFalse(d.excluir_operacao(99, motivo="Justificativa sintética do teste"))
        self.assertTrue(d.salvar_operacao([
            "2026-01-03 10:00:00", "ETH", "compra", 25, 250, 0.1, 5.3
        ]))
        self.assertEqual(
            [op["Moeda"] for op in d.carregar_operacoes()],
            ["BTC", "USDT", "ETH"]
        )
        self.assertIn(VENDA.strip(), self.csv.read_text(encoding="utf-8"))

    def test_edicao_invalida_nao_modifica_historico(self):
        d = self.app()
        original = d.carregar_operacoes()
        row = {**original[0], "Quantidade": "NaN"}
        self.assertFalse(d.atualizar_operacao(0, row, motivo="Justificativa sintética do teste"))
        self.assertEqual(d.carregar_operacoes(), original)

    def test_importacao_manual_aceita_so_banco_vazio(self):
        novo = self.base / "novo"
        d = self.app(origem=self.base / "inexistente.csv", pasta=novo)
        self.assertEqual(d.importar_csv_legado(str(self.csv)), 2)
        self.assertEqual(d.importar_csv_legado(str(self.csv)), 0)
        outro = self.base / "outro.csv"
        outro.write_text(CABECALHO + COMPRA, encoding="utf-8")
        with self.assertRaisesRegex(ErroMigracao, "diferente"):
            d.importar_csv_legado(str(outro))
        self.assertEqual(len(d.carregar_operacoes()), 2)

    def test_exportacao_cria_arquivo_novo_e_preserva_legado(self):
        d = self.app()
        with self.assertRaises(ErroArmazenamento):
            d.exportar_csv(str(self.csv))
        saida = self.base / "copia.csv"
        d.exportar_csv(str(saida))
        with saida.open(encoding="utf-8") as arquivo:
            self.assertEqual(len(list(csv.DictReader(arquivo))), 2)
        with self.assertRaises(FileExistsError):
            d.exportar_csv(str(saida))

    def test_saldo_legado_igual_apos_migracao(self):
        from backend.backend import AnalysisEngine
        d = self.app()
        portfolio = AnalysisEngine.calcular_portfolio(d.carregar_operacoes(), {"BTC": 1250})
        self.assertEqual(portfolio["BTC"]["lucro_realizado"], 20)
        self.assertEqual(portfolio["BTC"]["quantidade_final"], 0)


    def test_relatorio_visual_confere_sqlite_backup_e_operacoes(self):
        d = self.app()
        report = d._store.diagnostico_integridade()
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["integridade_sqlite"], "ok")
        self.assertEqual(report["operacoes_importadas"], 2)
        self.assertEqual(report["operacoes_atuais"], 2)
        self.assertTrue(report["backup_valido"])
        self.assertEqual(report["csv_original"], "preservado")
        self.assertTrue(d.salvar_operacao([
            "2025-12-31 10:00:00", "USDT", "compra", 500, 5.3, 500, 5.3
        ]))
        self.assertEqual(d._store.diagnostico_integridade()["operacoes_atuais"], 3)

    def test_relatorio_identifica_backup_adulterado(self):
        d = self.app()
        dados = d._store.diagnostico_integridade()
        backup = self.data_dir / "backups" / ("legado-" + dados["hash_legado"] + ".csv")
        backup.write_text("DADOS ADULTERADOS", encoding="utf-8")
        relatorio = d._store.diagnostico_integridade()
        self.assertEqual(relatorio["status"], "FALHA")
        self.assertFalse(relatorio["backup_valido"])
        self.assertEqual(self.csv.read_text(encoding="utf-8"), CABECALHO + COMPRA + VENDA)


if __name__ == "__main__":
    unittest.main()
