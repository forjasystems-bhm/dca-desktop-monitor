"""FIN-02: nenhum ativo aberto sem cotação pode virar preço zero ou patrimônio parcial."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.backend import AnalysisEngine, PriceManager


def op(moeda, tipo, qtd, valor, dia="2026-09-01 10:00:00"):
    return {
        "Moeda": moeda, "Operacao": tipo, "Quantidade": qtd,
        "Valor_USDT": valor, "Data": dia,
        "Preco": float(valor) / float(qtd), "Taxa_BRL": 5,
    }


class BinanceFalsa:
    def __init__(self, faltam=()):
        self.faltam = set(faltam)
        self.chamadas = []

    def fetch_ticker(self, par):
        self.chamadas.append(par)
        if par in self.faltam:
            raise ConnectionError(f"falha simulada {par}")
        return {"last": {
            "BTC/USDT": 100,
            "ETH/USDT": 50,
            "USDT/BRL": 5.20,
        }.get(par)}


class IntegridadeCotacaoTests(unittest.TestCase):
    def setUp(self):
        self.ops = [
            op("USDT", "compra", 500, 500),
            op("BTC", "compra", 1, 100),
            op("ETH", "compra", 2, 120),
        ]

    def test_cotacao_faltante_preserva_posicao_custo_e_bloqueia_totais(self):
        p = AnalysisEngine.calcular_portfolio(self.ops, {"BTC": 110})
        self.assertEqual(p["ETH"]["quantidade_final"], 2)
        self.assertEqual(p["ETH"]["custo_posicao_final"], 120)
        self.assertIsNone(p["ETH"]["preco_de_mercado"])
        self.assertIsNone(p["ETH"]["valor_atual_posicao"])
        self.assertIsNone(p["ETH"]["lucro_nao_realizado"])
        self.assertIsNone(p["ETH"]["lucro_total"])
        self.assertFalse(p["totais"]["avaliacao_completa"])
        self.assertEqual(p["totais"]["cotacoes_pendentes"], ["ETH"])
        self.assertIsNone(p["totais"]["valor_atual"])
        self.assertIsNone(p["totais"]["nao_realizado"])
        self.assertEqual(p["totais"]["investido_liquido"], 220)
        self.assertEqual(p["totais"]["caixa_usdt"], 280)

    def test_distribuicao_parcial_e_proibida(self):
        d = AnalysisEngine.calcular_distribuicao_portfolio(self.ops, {"BTC": 110})
        self.assertFalse(d["avaliacao_completa"])
        self.assertIsNone(d["total_valor_portfolio"])
        self.assertIsNone(d["total_investido"])
        self.assertEqual(d["cotacoes_pendentes"], ["ETH"])
        self.assertEqual(d["distribuicao"], {})

    def test_dados_validos_recalculam_patrimonio_e_percentuais(self):
        p = AnalysisEngine.calcular_portfolio(self.ops, {"BTC": 110, "ETH": 60})
        self.assertTrue(p["totais"]["avaliacao_completa"])
        self.assertEqual(p["totais"]["valor_atual"], 510)
        self.assertEqual(p["totais"]["nao_realizado"], 10)
        d = AnalysisEngine.calcular_distribuicao_portfolio(self.ops, {"BTC": 110, "ETH": 60})
        self.assertEqual(d["total_valor_portfolio"], 510)
        self.assertAlmostEqual(sum(a["percentual"] for a in d["distribuicao"].values()), 100)

    def test_posicao_encerrada_nao_exige_preco_e_preserva_realizado(self):
        ops = [
            op("USDT", "compra", 200, 200),
            op("BTC", "compra", 1, 100),
            op("BTC", "venda", 1, 130, dia="2026-09-02 10:00:00"),
        ]
        p = AnalysisEngine.calcular_portfolio(ops, {})
        self.assertTrue(p["totais"]["avaliacao_completa"])
        self.assertEqual(p["BTC"]["valor_atual_posicao"], 0)
        self.assertEqual(p["BTC"]["lucro_nao_realizado"], 0)
        self.assertEqual(p["BTC"]["lucro_realizado"], 30)
        self.assertEqual(p["totais"]["valor_atual"], 230)
        self.assertEqual(p["totais"]["cotacoes_pendentes"], [])

    def test_preco_zero_nulo_negativo_nan_infinito_nao_sao_cotacoes(self):
        for preco in [None, 0, -10, "NaN", "Infinity", float("inf"), "x", "1e9999", "1e-9999"]:
            with self.subTest(preco=preco):
                p = AnalysisEngine.calcular_portfolio(self.ops, {"BTC": preco, "ETH": 50})
                self.assertFalse(p["totais"]["avaliacao_completa"])
                self.assertEqual(p["totais"]["cotacoes_pendentes"], ["BTC"])
                self.assertIsNone(p["BTC"]["valor_atual_posicao"])

    def test_ausencia_de_todas_as_cotacoes_mantem_realizado_e_custo(self):
        ops = self.ops + [op("BTC", "venda", 0.5, 70, dia="2026-09-02 10:00:00")]
        p = AnalysisEngine.calcular_portfolio(ops, {})
        self.assertIsNone(p["totais"]["valor_atual"])
        self.assertEqual(p["totais"]["realizado"], 20)
        self.assertEqual(p["BTC"]["quantidade_final"], 0.5)
        self.assertEqual(p["BTC"]["custo_posicao_final"], 50)
        self.assertEqual(p["totais"]["cotacoes_pendentes"], ["BTC", "ETH"])

    def test_nao_reutiliza_cache_que_falhou_mesmo_se_recentissimo(self):
        pm = PriceManager.__new__(PriceManager)
        pm.exchange = BinanceFalsa()
        pm.precos_cache = {}
        pm.cotacoes_atualizadas_em = {}
        pm.falhas_cotacao = set()
        pm.ultima_atualizacao = None
        pm.preco_brl = 0
        pm._brl_atualizado_em = None
        pm._brl_falhou = True
        self.assertTrue(pm.atualizar_precos(["BTC", "ETH"]))
        self.assertEqual(pm.precos_para_avaliacao()["BTC"], 100)
        self.assertEqual(pm.taxa_brl_para_avaliacao(), 5.2)
        pm.exchange = BinanceFalsa({"ETH/USDT", "USDT/BRL"})
        self.assertFalse(pm.atualizar_precos(["BTC", "ETH"]))
        self.assertEqual(pm.precos_cache["ETH"], 50)
        self.assertNotIn("ETH", pm.precos_para_avaliacao())
        self.assertIsNone(pm.get_preco("ETH"))
        self.assertEqual(pm.get_preco("BTC"), 100)
        self.assertIsNone(pm.taxa_brl_para_avaliacao())

    def test_expiracao_de_cache_em_dias_ou_minutos_rejeita_cotacao(self):
        pm = PriceManager.__new__(PriceManager)
        agora = datetime.now(timezone.utc)
        pm.precos_cache = {"BTC": 100, "ETH": 50}
        pm.cotacoes_atualizadas_em = {
            "BTC": agora - timedelta(days=1),
            "ETH": agora - timedelta(seconds=20),
        }
        pm.falhas_cotacao = set()
        pm._brl_falhou = False
        pm.preco_brl = 5.2
        pm._brl_atualizado_em = agora - timedelta(days=1)
        precos = pm.precos_para_avaliacao(agora=agora, max_age=120)
        self.assertNotIn("BTC", precos)
        self.assertEqual(precos["ETH"], 50)
        self.assertIsNone(pm.taxa_brl_para_avaliacao(agora=agora, max_age=120))

    def test_offline_nao_cria_cotacao_ficticia(self):
        pm = PriceManager.__new__(PriceManager)
        pm.exchange = None
        pm.precos_cache = {}
        pm.cotacoes_atualizadas_em = {}
        pm.falhas_cotacao = set()
        pm._brl_falhou = True
        self.assertFalse(pm.atualizar_precos(["BTC", "ETH"]))
        self.assertEqual(pm.precos_para_avaliacao(), {"USDT": 1.0})


if __name__ == "__main__":
    unittest.main()
