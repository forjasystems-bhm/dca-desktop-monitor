"""FIN-03: operações auditáveis, regras globais e rollback atômico."""
import csv
from decimal import Decimal
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import threading
import unittest

from backend.backend import DataManager
from backend.finance_analytics import calcular_analise_por_periodo


def novo(dia, moeda, tipo, valor, preco, quantidade, taxa="5"):
    return [dia, moeda, tipo, str(valor), str(preco), str(quantidade), str(taxa)]


class Fin03Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = DataManager(
            legacy_csv=self.root / "arquivo-inexistente.csv",
            data_dir=self.root / "dados",
        )

    def deposito(self, valor="1000", dia="2026-01-01 09:00:00"):
        return self.db.salvar_operacao(
            novo(dia, "USDT", "compra", valor, "5.2", valor)
        )

    def compra(self, dia="2026-01-02 09:00:00", ativo="BTC",
               valor="500", preco="50000", qtd="0.01"):
        return self.db.salvar_operacao(novo(dia, ativo, "compra", valor, preco, qtd))

    def venda(self, dia="2026-01-03 09:00:00", ativo="BTC",
              valor="600", preco="60000", qtd="0.01"):
        return self.db.salvar_operacao(novo(dia, ativo, "venda", valor, preco, qtd))

    def test_fluxo_valido_deposito_compra_venda_parcial_e_saldo(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        self.assertTrue(self.venda(valor="300", preco="60000", qtd="0.005"))
        estado = calcular_analise_por_periodo(self.db.carregar_operacoes_precisas())
        self.assertEqual(estado["ativos"]["BTC"]["quantidade"], Decimal("0.005"))
        self.assertEqual(estado["ativos"]["BTC"]["custo_aberto"], Decimal("250"))
        self.assertEqual(estado["ativos"]["BTC"]["realizado_historico"], Decimal("50"))
        self.assertEqual(self.db.ultimo_erro, None)

    def test_compra_sem_saldo_rejeitada_sem_gravacao_parcial(self):
        self.assertFalse(self.compra())
        self.assertIn("saldo USDT negativo", self.db.ultimo_erro)
        self.assertEqual(self.db.carregar_operacoes(), [])
        with closing(sqlite3.connect(self.db.arquivo_db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0], 0)

    def test_venda_superior_ao_saldo_rejeitada(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        anterior = self.db.carregar_operacoes()
        self.assertFalse(self.venda(valor="1200", preco="60000", qtd="0.02"))
        self.assertIn("venda superior", self.db.ultimo_erro)
        self.assertEqual(self.db.carregar_operacoes(), anterior)

    def test_preco_quantidade_valor_divergentes_rejeitados(self):
        self.assertTrue(self.deposito())
        self.assertFalse(self.compra(valor="400"))
        self.assertIn("Valor_USDT divergente", self.db.ultimo_erro)
        self.assertEqual(len(self.db.carregar_operacoes()), 1)

    def test_deposito_usdt_nao_multiplica_valor_pela_taxa_brl(self):
        self.assertFalse(self.db.salvar_operacao(novo(
            "2026-01-01 09:00:00", "USDT", "compra", "1000", "5", "950"
        )))
        self.assertIn("Quantidade igual a Valor_USDT", self.db.ultimo_erro)
        self.assertTrue(self.deposito(valor="1000"))
        self.assertEqual(self.db.carregar_operacoes_precisas()[0]["Quantidade"], "1000")

    def test_entrada_decimal_arredondada_oito_casas_permitida(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra(valor="5.0000", preco="50000", qtd="0.00010000"))
        self.assertTrue(self.db.salvar_operacao(novo(
            "2026-01-04 09:00:00", "ETH", "compra",
            "0.3333", "1000", "0.00033330"
        )))
        self.assertEqual(len(self.db.carregar_operacoes()), 3)

    def test_valor_malformado_nan_infinito_negativo_rejeitados(self):
        self.assertTrue(self.deposito())
        for texto in ("NaN", "Infinity", "-1", "0", "abcd"):
            with self.subTest(texto=texto):
                self.assertFalse(self.compra(valor=texto))
        self.assertEqual(len(self.db.carregar_operacoes()), 1)

    def test_excluir_compra_que_sustenta_venda_e_proibido(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        self.assertTrue(self.venda())
        original = self.db.carregar_operacoes()
        self.assertFalse(self.db.excluir_operacao(1))
        self.assertIn("venda superior", self.db.ultimo_erro)
        self.assertEqual(self.db.carregar_operacoes(), original)

    def test_excluir_aporte_que_sustenta_compras_e_proibido(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        original = self.db.carregar_operacoes()
        self.assertFalse(self.db.excluir_operacao(0))
        self.assertIn("saldo USDT negativo", self.db.ultimo_erro)
        self.assertEqual(self.db.carregar_operacoes(), original)

    def test_edicao_compra_passada_que_invalida_venda_futura_rejeitada(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        self.assertTrue(self.venda())
        original = self.db.carregar_operacoes_precisas()
        row = dict(original[1])
        row["Quantidade"] = "0.005"
        row["Valor_USDT"] = "250"
        self.assertFalse(self.db.atualizar_operacao(1, row))
        self.assertIn("venda superior", self.db.ultimo_erro)
        self.assertEqual(self.db.carregar_operacoes_precisas(), original)

    def test_edicao_de_data_pode_tornar_saldo_insuficiente_e_rejeita(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        original = self.db.carregar_operacoes_precisas()
        row = dict(original[0])
        row["Data"] = "2026-01-04 09:00:00"
        self.assertFalse(self.db.atualizar_operacao(0, row))
        self.assertIn("saldo USDT negativo", self.db.ultimo_erro)
        self.assertEqual(self.db.carregar_operacoes_precisas(), original)

    def test_edicao_moeda_proibida_e_sem_atualizacao_parcial(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        row = dict(self.db.carregar_operacoes_precisas()[1])
        row["Moeda"] = "ETH"
        self.assertFalse(self.db.atualizar_operacao(1, row))
        self.assertIn("moeda", self.db.ultimo_erro.lower())
        self.assertEqual(self.db.carregar_operacoes_precisas()[1]["Moeda"], "BTC")

    def test_edicao_valida_muda_custo_medio_e_lucro(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        self.assertTrue(self.venda())
        row = dict(self.db.carregar_operacoes_precisas()[1])
        row.update({"Preco": "45000", "Valor_USDT": "450"})
        self.assertTrue(self.db.atualizar_operacao(1, row))
        result = calcular_analise_por_periodo(self.db.carregar_operacoes_precisas())
        self.assertEqual(result["ativos"]["BTC"]["realizado_historico"], Decimal("150"))

    def test_exclusao_valida_altera_estado_financeiro_e_reabre(self):
        self.assertTrue(self.deposito())
        self.assertTrue(self.compra())
        self.assertTrue(self.venda())
        self.assertTrue(self.db.excluir_operacao(2))
        outra = DataManager(legacy_csv=self.root / "arquivo-inexistente.csv",
                           data_dir=self.root / "dados")
        result = calcular_analise_por_periodo(outra.carregar_operacoes_precisas())
        self.assertEqual(result["ativos"]["BTC"]["quantidade"], Decimal("0.01"))
        self.assertEqual(result["ativos"]["BTC"]["realizado_historico"], Decimal("0"))

    def test_importacao_de_legado_inconsistente_e_preservada_sem_omissao(self):
        csv_path = self.root / "legado.csv"
        texto = (
            "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
            "2026-01-01 10:00:00,BTC,compra,100,1000,0.1,5\n"
            "2026-01-02 10:00:00,BTC,venda,120,1200,0.1,5\n"
        )
        csv_path.write_text(texto, encoding="utf-8")
        outra = DataManager(legacy_csv=csv_path, data_dir=self.root / "outro")
        self.assertEqual(len(outra.carregar_operacoes()), 2)
        relatorio = outra._store.diagnostico_livro_legado()
        self.assertFalse(relatorio["consistente"])
        self.assertIn("saldo USDT negativo", relatorio["erro"])
        self.assertFalse(outra.salvar_operacao(novo(
            "2026-01-03 10:00:00", "ETH", "compra", 25, 250, 0.1
        )))
        self.assertEqual(csv_path.read_text(encoding="utf-8"), texto)
        self.assertEqual(len(outra.carregar_operacoes()), 2)
        # Aporte retroativo viabiliza conciliação sem editar ou apagar o CSV.
        self.assertTrue(outra.salvar_operacao(novo(
            "2025-12-31 10:00:00", "USDT", "compra", 500, 5, 500
        )))
        self.assertTrue(outra._store.diagnostico_livro_legado()["consistente"])

    def test_usdc_fica_preservado_no_legado_sem_regra_contabil_inventada(self):
        self.assertTrue(self.deposito())
        self.assertFalse(self.db.salvar_operacao(novo(
            "2026-01-02 09:00:00", "USDC", "compra", 10, 5, 10
        )))
        self.assertIn("FIN-04", self.db.ultimo_erro)

    def test_duas_compras_concorrentes_nao_gastam_mesmo_saldo_duas_vezes(self):
        self.assertTrue(self.deposito("100"))
        barrier = threading.Barrier(3)
        resultados = []
        def comprar(nome):
            barrier.wait()
            resultados.append(self.db._store.inserir(novo(
                "2026-01-02 09:00:00", nome, "compra", 75, 75, 1
            )))
        def seguro(nome):
            try:
                comprar(nome)
            except Exception as exc:
                resultados.append(str(exc))
        a = threading.Thread(target=seguro, args=("BTC",))
        b = threading.Thread(target=seguro, args=("ETH",))
        a.start()
        b.start()
        barrier.wait()
        a.join(timeout=15)
        b.join(timeout=15)
        self.assertEqual(sum(r is True for r in resultados), 1, resultados)
        self.assertEqual(len(self.db.carregar_operacoes()), 2)
        self.assertTrue(any("saldo USDT negativo" in str(r) for r in resultados), resultados)


if __name__ == "__main__":
    unittest.main()
