"""HIST-01: avaliação retrospectiva sem preços correntes ou estimativas."""
import tempfile
import unittest
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from backend.backend import DataManager
from backend.historical_prices import (
    ErroCotacaoHistorica, buscar_e_persistir_fechamentos,
    candle_binance_diario, validar_data_encerrada,
)
from backend.historical_valuation import patrimonio_historico_na_data


HOJE = date(2026, 10, 18)
DIA = date(2026, 9, 30)
CAB = "Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
DADOS = (
    "2026-09-01 09:00:00,USDT,compra,2000,5,2000,5\n"
    "2026-09-05 10:00:00,BTC,compra,1000,10000,0.1,5\n"
    "2026-09-12 11:00:00,BTC,venda,1300,13000,0.1,5\n"
    "2026-09-15 10:00:00,ETH,compra,600,1200,0.5,5\n"
    "2026-09-17 10:00:00,SOL,compra,100,100,1,5\n"
    "2026-09-19 10:00:00,SOL,venda,80,80,1,5\n"
    "2026-09-20 10:00:00,LINK,compra,50,10,5,5\n"
    "2026-09-22 10:00:00,LINK,venda,50,10,5,5\n"
)


class BinanceFake:
    def __init__(self, fecha="1000", timestamp_delta=0, missing=False):
        self.fecha = fecha
        self.timestamp_delta = timestamp_delta
        self.missing = missing
        self.chamadas = []

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.chamadas.append((symbol, timeframe, since, limit))
        if self.missing:
            return []
        return [[since + self.timestamp_delta, 900, 1001, 850, self.fecha, 100]]


class Hist01Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.csv = self.root / "legado.csv"
        self.csv.write_text(CAB + DADOS, encoding="utf-8")
        self.dm = DataManager(legacy_csv=self.csv, data_dir=self.root / "dados")
        self.store = self.dm._store

    def registrar_eth(self, preco="1000"):
        fake = BinanceFake(preco)
        count = buscar_e_persistir_fechamentos(
            self.store, fake, DIA, ["ETH"], hoje_utc=HOJE
        )
        return count, fake

    def test_sem_cotacao_total_inexistente_mas_lucro_realizado_preservado(self):
        result = patrimonio_historico_na_data(self.store, DIA, hoje_utc=HOJE)
        self.assertFalse(result["completo"])
        self.assertIsNone(result["patrimonio_total"])
        self.assertIsNone(result["lucro_nao_realizado"])
        self.assertIsNone(result["resultado_total"])
        self.assertEqual(result["faltam_cotacoes"], ["ETH"])
        self.assertEqual(result["lucro_realizado"], Decimal("280"))
        self.assertEqual(result["caixa_usdt"], Decimal("1680"))
        self.assertEqual(result["ativos"]["BTC"]["valor_mercado"], Decimal("0"))

    def test_cotacao_registrada_fecha_patrimonio_historico_exato(self):
        self.registrar_eth()
        r = patrimonio_historico_na_data(self.store, DIA, hoje_utc=HOJE)
        self.assertTrue(r["completo"])
        self.assertEqual(r["patrimonio_total"], Decimal("2180"))
        self.assertEqual(r["lucro_nao_realizado"], Decimal("-100"))
        self.assertEqual(r["lucro_realizado"], Decimal("280"))
        self.assertEqual(r["resultado_total"], Decimal("180"))
        self.assertEqual(r["ativos"]["ETH"]["valor_mercado"], Decimal("500"))
        self.assertEqual(r["ativos"]["ETH"]["cotacao"]["fonte"], "Binance/CCXT:OHLCV:1d:close")

    def test_reconsulta_usando_apenas_sqlite_nao_chama_exchange(self):
        count, fake = self.registrar_eth()
        self.assertEqual(count, 1)
        self.assertEqual(fake.chamadas[0][0], "ETH/USDT")
        self.assertEqual(fake.chamadas[0][1], "1d")
        self.assertEqual(fake.chamadas[0][3], 1)
        self.assertEqual(fake.chamadas[0][2],
            int(datetime.combine(DIA, time.min, timezone.utc).timestamp() * 1000))
        fake_second = BinanceFake("99999999")
        self.assertEqual(buscar_e_persistir_fechamentos(
            self.store, fake_second, DIA, ["ETH", "ETH"], hoje_utc=HOJE
        ), 0)
        self.assertEqual(fake_second.chamadas, [])
        self.assertEqual(
            patrimonio_historico_na_data(self.store, DIA, hoje_utc=HOJE)["patrimonio_total"],
            Decimal("2180")
        )

    def test_cotacao_de_outra_data_nao_passa_pela_validacao(self):
        fake = BinanceFake(timestamp_delta=86400000)
        with self.assertRaisesRegex(ErroCotacaoHistorica, "outra data"):
            buscar_e_persistir_fechamentos(
                self.store, fake, DIA, ["ETH"], hoje_utc=HOJE
            )
        self.assertEqual(self.store.ler_cotacoes_historicas(DIA), {})

    def test_data_atual_ou_futura_nao_admite_candle_incompleto(self):
        for data in [HOJE, date(2026, 10, 19)]:
            with self.subTest(data=data), self.assertRaisesRegex(
                ErroCotacaoHistorica, "encerradas"
            ):
                validar_data_encerrada(data, HOJE)
            with self.assertRaises(ErroCotacaoHistorica):
                patrimonio_historico_na_data(self.store, data, hoje_utc=HOJE)

    def test_preco_zero_nan_negativo_ausente_bloqueado(self):
        for preco in ["0", "-1", "NaN", "Infinity"]:
            with self.subTest(preco=preco):
                with self.assertRaises(ErroCotacaoHistorica):
                    buscar_e_persistir_fechamentos(
                        self.store, BinanceFake(preco), DIA, ["ETH"],
                        hoje_utc=HOJE
                    )
        with self.assertRaisesRegex(ErroCotacaoHistorica, "Sem candle"):
            buscar_e_persistir_fechamentos(
                self.store, BinanceFake(missing=True), DIA, ["ETH"],
                hoje_utc=HOJE
            )
        self.assertEqual(self.store.ler_cotacoes_historicas(DIA), {})

    def test_registro_nao_pode_ser_sobrescrito_por_preco_diferente(self):
        count, _ = self.registrar_eth()
        self.assertEqual(count, 1)
        alt = dict(self.store.ler_cotacoes_historicas(DIA)["ETH"])
        alt.update({
            "data_utc": DIA.isoformat(), "ativo": "ETH", "moeda_cotacao": "USDT",
            "preco": "2222"
        })
        with self.assertRaisesRegex(ErroCotacaoHistorica, "diferente"):
            self.store.salvar_cotacoes_historicas([alt], hoje_utc=HOJE)
        self.assertEqual(
            self.store.ler_cotacoes_historicas(DIA)["ETH"]["preco"], Decimal("1000")
        )

    def test_lote_de_candles_e_atomico_se_um_ativo_falhar(self):
        class Parcial:
            def fetch_ohlcv(self, symbol, timeframe, since, limit):
                return [[since, 1, 2, 0.5, 1000, 100]] if symbol == "ETH/USDT" else []
        with self.assertRaises(ErroCotacaoHistorica):
            buscar_e_persistir_fechamentos(
                self.store, Parcial(), DIA, ["ETH", "BTC"], hoje_utc=HOJE
            )
        self.assertEqual(self.store.ler_cotacoes_historicas(DIA), {})

    def test_valor_historico_nao_inclui_operacoes_posteriores(self):
        self.registrar_eth()
        antes = patrimonio_historico_na_data(self.store, DIA, hoje_utc=HOJE)
        self.assertTrue(self.dm.salvar_operacao([
            "2026-10-10 12:00:00", "ETH", "compra", "900", "1500", "0.6", "5"
        ]))
        depois = patrimonio_historico_na_data(self.store, DIA, hoje_utc=HOJE)
        self.assertEqual(depois["patrimonio_total"], antes["patrimonio_total"])
        self.assertEqual(depois["lucro_nao_realizado"], antes["lucro_nao_realizado"])

    def test_falta_cotacao_adicional_nao_gera_total_parcial(self):
        self.registrar_eth()
        self.assertTrue(self.dm.salvar_operacao([
            "2026-09-25 15:00:00", "ADA", "compra", "100", "1", "100", "5"
        ]))
        r = patrimonio_historico_na_data(self.store, DIA, hoje_utc=HOJE)
        self.assertFalse(r["completo"])
        self.assertIn("ADA", r["faltam_cotacoes"])
        self.assertIsNone(r["patrimonio_total"])
        self.assertEqual(r["ativos"]["ETH"]["valor_mercado"], Decimal("500"))

    def test_sem_cotacao_de_outro_dia_nao_substitui_a_data_pedida(self):
        self.registrar_eth()
        outro = date(2026, 9, 29)
        r = patrimonio_historico_na_data(self.store, outro, hoje_utc=HOJE)
        self.assertIsNone(r["patrimonio_total"])
        self.assertEqual(r["faltam_cotacoes"], ["ETH"])

    def test_reabertura_preserva_cotacoes_e_integridade_csv(self):
        self.registrar_eth("1234.56789")
        outro = DataManager(legacy_csv=self.csv, data_dir=self.root / "dados")
        r = patrimonio_historico_na_data(outro._store, DIA, hoje_utc=HOJE)
        self.assertEqual(r["ativos"]["ETH"]["valor_mercado"], Decimal("617.283945"))
        self.assertEqual(r["patrimonio_total"], Decimal("2297.283945"))
        self.assertEqual(outro._store.diagnostico_integridade()["csv_original"], "preservado")
        self.assertEqual(outro._store.diagnostico_integridade()["operacoes_importadas"], 8)


if __name__ == "__main__":
    unittest.main()
