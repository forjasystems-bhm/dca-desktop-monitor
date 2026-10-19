"""F03: same-day custody chronology must use confirmed journal sequence."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from backend.backend import DataManager
from backend.custody_ledger import apurar_custodia


class SameDayCustodySequenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "data"
        self.dm = DataManager(data_dir=self.path, auto_import_legacy=False)
        self.dm.registrar_posicao_externa(
            moeda="BTC", quantidade="1", custodia="A",
            data_posicao="2026-01-01", custo_total_usdt="100",
            confirmacao_independente=True,
        )

    def move(self, **updates):
        options = dict(
            tipo="transferencia", moeda="BTC", origem="A", destino="B",
            quantidade="0.4", data_utc="2026-01-02",
            taxa_ativo="0", receita_usdt="0", taxa_usdt="0",
            observacao="Movimento documental F03 sem horario conhecido",
        )
        options.update(updates)
        return self.dm.registrar_movimento_custodia(**options)

    def replay(self, *, ate=None):
        return apurar_custodia(
            self.dm.carregar_posicoes_externas(),
            self.dm.carregar_movimentos_custodia(),
            ate=ate,
        )

    @staticmethod
    def lots(replay):
        return {(row["Moeda"], row["Custodia"]): row
                for row in replay["saldos"]}

    def test_a_to_b_to_c_on_same_day_uses_documented_id_sequence(self):
        self.move()
        self.move(origem="B", destino="C", quantidade="0.3")
        movements = self.dm.carregar_movimentos_custodia()
        self.assertEqual([m["ID"] for m in movements], [1, 2])
        self.assertEqual([m["Data"] for m in movements],
                         ["2026-01-02", "2026-01-02"])
        r = self.replay(ate=date(2026, 1, 2))
        lots = self.lots(r)
        self.assertEqual(Decimal(lots["BTC", "A"]["Quantidade"]), Decimal("0.6"))
        self.assertEqual(Decimal(lots["BTC", "B"]["Quantidade"]), Decimal("0.1"))
        self.assertEqual(Decimal(lots["BTC", "C"]["Quantidade"]), Decimal("0.3"))
        self.assertEqual(Decimal(lots["BTC", "C"]["Custo_Total_USDT"]), Decimal("30"))
        self.assertEqual(r, self.replay())

    def test_a_to_b_sale_then_usdt_transfer_same_day(self):
        self.move()
        self.move(tipo="venda", origem="B", destino="B",
                  quantidade="0.3", receita_usdt="60", taxa_usdt="1")
        self.move(moeda="USDT", origem="B", destino="C",
                  quantidade="30")
        persisted = self.dm.carregar_movimentos_custodia()
        self.assertEqual([m["ID"] for m in persisted], [1, 2, 3])
        r = self.replay(ate=date(2026, 1, 2))
        lots = self.lots(r)
        self.assertEqual(Decimal(lots["BTC", "B"]["Quantidade"]), Decimal("0.1"))
        self.assertEqual(Decimal(lots["USDT", "B"]["Quantidade"]), Decimal("29"))
        self.assertEqual(Decimal(lots["USDT", "C"]["Quantidade"]), Decimal("30"))
        self.assertEqual(r["lucro_vendas_externas_usdt"], Decimal("29"))
        self.assertEqual(r["vendas"], 1)
        self.assertEqual(self.dm.carregar_operacoes_precisas(), [])

    def test_reverse_chain_rejected_atomically_and_no_fictitious_trade(self):
        before = self.dm.carregar_movimentos_custodia()
        with self.assertRaises(Exception):
            self.move(origem="B", destino="C", quantidade="0.1")
        self.assertEqual(self.dm.carregar_movimentos_custodia(), before)
        self.assertEqual(self.dm.carregar_operacoes_precisas(), [])
        self.move()
        after_first = self.dm.carregar_movimentos_custodia()
        with self.assertRaises(Exception):
            self.move(origem="A", destino="D", quantidade="0.7")
        self.assertEqual(self.dm.carregar_movimentos_custodia(), after_first)

    def test_legacy_synthetic_timestamps_do_not_override_id_order(self):
        older = {"ID": 1, "Data": "2026-01-02T23:59:59Z",
                 "Tipo": "transferencia", "Moeda": "BTC",
                 "Origem": "A", "Destino": "B", "Quantidade": "0.4",
                 "Taxa_Ativo": "0", "Taxa_USDT": "0", "Receita_USDT": "0"}
        newer = {"ID": 2, "Data": "2026-01-02T00:00:00Z",
                 "Tipo": "transferencia", "Moeda": "BTC",
                 "Origem": "B", "Destino": "C", "Quantidade": "0.3",
                 "Taxa_Ativo": "0", "Taxa_USDT": "0", "Receita_USDT": "0"}
        result = apurar_custodia(
            self.dm.carregar_posicoes_externas(), [newer, older],
            ate=date(2026, 1, 2),
        )
        lots = self.lots(result)
        self.assertEqual(Decimal(lots["BTC", "C"]["Quantidade"]), Decimal("0.3"))

    def test_reopening_preserves_same_day_sequence_and_f01_temporal_cutoff(self):
        self.move()
        self.move(origem="B", destino="C", quantidade="0.1")
        self.dm.registrar_posicao_externa(
            moeda="ETH", quantidade="2", custodia="Cold",
            data_posicao="2026-10-01", custo_total_usdt="400",
            confirmacao_independente=True,
        )
        reopened = DataManager(data_dir=self.path, auto_import_legacy=False)
        history = apurar_custodia(
            reopened.carregar_posicoes_externas(),
            reopened.carregar_movimentos_custodia(),
            ate=date(2026, 1, 2),
        )
        self.assertEqual([p["Moeda"] for p in history["saldos"]], ["BTC", "BTC", "BTC"])
        self.assertEqual(Decimal(self.lots(history)["BTC", "C"]["Quantidade"]),
                         Decimal("0.1"))
        self.assertEqual(len(reopened.carregar_movimentos_custodia()), 2)


if __name__ == "__main__":
    unittest.main()
