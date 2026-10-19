"""F01: future custody declarations cannot fund earlier movements or costs."""
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.backend import DataManager
from backend.custody_ledger import apurar_custodia, ErroMovimentacaoCustodia


class TemporalCustodyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.csv = self.root / "synthetic-original.csv"
        self.csv.write_bytes(
            b"Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n"
            b"2025-12-31 12:00:00,USDT,compra,100,5,100,5\n"
        )
        self.original_bytes = self.csv.read_bytes()
        self.dm = DataManager(
            data_dir=self.root / "data", legacy_csv=self.csv,
            auto_import_legacy=False,
        )
        preview = self.dm.prever_csv(str(self.csv))
        self.dm.confirmar_csv(str(self.csv), preview["sha256"])
        self.dm.registrar_posicao_externa(
            moeda="BTC", quantidade="1", custodia="A",
            data_posicao="2026-01-01", custo_total_usdt="100",
            confirmacao_independente=True,
        )
        self.dm.registrar_posicao_externa(
            moeda="BTC", quantidade="10", custodia="B",
            data_posicao="2026-10-01", custo_total_usdt="10000",
            confirmacao_independente=True,
        )

    def move(self, **changes):
        args = dict(
            tipo="transferencia", moeda="BTC", origem="A", destino="B",
            quantidade="0.1", data_utc="2026-01-02", taxa_ativo="0",
            receita_usdt="0", taxa_usdt="0",
            observacao="Synthetic documented F01 movement",
        )
        args.update(changes)
        return self.dm.registrar_movimento_custodia(**args)

    def reject_future_funded_sale(self):
        with self.assertRaisesRegex(ErroMovimentacaoCustodia, "saldo insuficiente"):
            self.move(
                tipo="venda", origem="B", destino="B", quantidade="5",
                data_utc="2026-01-03", receita_usdt="600",
            )

    def test_t1_future_declaration_cannot_fund_earlier_sale(self):
        self.move()
        self.reject_future_funded_sale()
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 1)

    def test_t2_old_custody_transfer_survives_unrelated_future_declaration(self):
        self.move()
        result = apurar_custodia(
            self.dm.carregar_posicoes_externas(),
            self.dm.carregar_movimentos_custodia(), ate=date(2026, 1, 2),
        )
        lots = {p["Custodia"]: p for p in result["saldos"]}
        self.assertEqual(Decimal(lots["A"]["Quantidade"]), Decimal("0.9"))
        self.assertEqual(Decimal(lots["B"]["Quantidade"]), Decimal("0.1"))
        self.assertEqual(Decimal(lots["B"]["Custo_Total_USDT"]), Decimal("10"))

    def test_t3_future_snapshot_cannot_change_earlier_balances_or_costs(self):
        self.move()
        self.move(
            tipo="venda", origem="B", destino="B", quantidade="0.05",
            data_utc="2026-01-03", receita_usdt="20",
        )
        snapshots = self.dm.carregar_posicoes_externas()
        movements = self.dm.carregar_movimentos_custodia()
        original = [p for p in snapshots if p["Custodia"] == "A"]
        for cutoff in (date(2025, 12, 31), date(2026, 1, 1),
                       date(2026, 1, 2), date(2026, 1, 3), date(2026, 9, 30)):
            with self.subTest(cutoff=cutoff):
                self.assertEqual(
                    apurar_custodia(snapshots, movements, ate=cutoff),
                    apurar_custodia(original, movements, ate=cutoff),
                )
        # A later snapshot must not retroactively change the basis of the sale,
        # even when calculating the current/full ledger after October.
        current = apurar_custodia(snapshots, movements)
        self.assertEqual(current["lucro_vendas_externas_usdt"], Decimal("15"))
        b = next(p for p in current["saldos"] if p["Custodia"] == "B"
                 and p["Moeda"] == "BTC")
        self.assertEqual(Decimal(b["Quantidade"]), Decimal("10.05"))
        self.assertEqual(Decimal(b["Custo_Total_USDT"]), Decimal("10005"))

    def test_t4_rejection_preserves_database_journal_and_original_csv(self):
        self.move()
        with closing(sqlite3.connect(self.dm.arquivo_db)) as con:
            before = list(con.iterdump())
        movements = self.dm.carregar_movimentos_custodia()
        operations = self.dm.carregar_operacoes_precisas()
        self.reject_future_funded_sale()
        with closing(sqlite3.connect(self.dm.arquivo_db)) as con:
            self.assertEqual(list(con.iterdump()), before)
        self.assertEqual(self.dm.carregar_movimentos_custodia(), movements)
        self.assertEqual(self.dm.carregar_operacoes_precisas(), operations)
        self.assertEqual(self.csv.read_bytes(), self.original_bytes)

    def test_replay_itself_rejects_earlier_sale_using_future_units(self):
        self.move()
        movements = self.dm.carregar_movimentos_custodia() + [{
            "ID": 2, "Data": "2026-01-03T12:00:00Z", "Tipo": "venda",
            "Moeda": "BTC", "Origem": "B", "Destino": "B",
            "Quantidade": "5", "Taxa_Ativo": "0",
            "Receita_USDT": "600", "Taxa_USDT": "0",
        }]
        for cutoff in (None, date(2026, 1, 3), date(2026, 10, 1)):
            with self.subTest(cutoff=cutoff):
                with self.assertRaisesRegex(ErroMovimentacaoCustodia, "saldo insuficiente"):
                    apurar_custodia(
                        self.dm.carregar_posicoes_externas(), movements, ate=cutoff,
                    )

    def test_f03_same_day_ordering_remains_outside_this_fix(self):
        # Use a destination without a future declaration so this only
        # characterizes the pre-existing same-day ordering issue, not F01.
        self.move(destino="C")
        with self.assertRaisesRegex(ErroMovimentacaoCustodia, "saldo insuficiente"):
            self.move(origem="C", destino="D")
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 1)


if __name__ == "__main__":
    unittest.main()
