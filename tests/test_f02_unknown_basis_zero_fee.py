"""F02: transferências sem taxa não exigem custo de aquisição conhecido."""
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from backend.backend import DataManager
from backend.custody_ledger import apurar_custodia


class ZeroFeeUnknownBasisTests(unittest.TestCase):
    @staticmethod
    def declaration(cost=None):
        return {"Data": "2026-01-01", "Moeda": "BTC", "Custodia": "A",
                "Quantidade": "1", "Custo_Total_USDT": cost}

    @staticmethod
    def movement(fee="0"):
        return {"ID": 1, "Data": "2026-01-02T12:00:00Z",
                "Tipo": "transferencia", "Moeda": "BTC",
                "Origem": "A", "Destino": "B", "Quantidade": "0.25",
                "Taxa_Ativo": fee, "Taxa_USDT": "0", "Receita_USDT": "0"}

    def test_zero_fee_unknown_basis_preserves_units_and_unknown_cost(self):
        r = apurar_custodia([self.declaration()], [self.movement()])
        lots = {p["Custodia"]: p for p in r["saldos"]}
        self.assertEqual(Decimal(lots["A"]["Quantidade"]), Decimal("0.75"))
        self.assertEqual(Decimal(lots["B"]["Quantidade"]), Decimal("0.25"))
        self.assertIsNone(lots["A"]["Custo_Total_USDT"])
        self.assertIsNone(lots["B"]["Custo_Total_USDT"])
        self.assertIn("BTC", r["ativos_sem_custo"])
        self.assertEqual(r["custo_taxas_transferencias_usdt"], Decimal("0"))

    def test_positive_fee_unknown_basis_keeps_fee_cost_unavailable(self):
        r = apurar_custodia([self.declaration()], [self.movement("0.01")])
        lots = {p["Custodia"]: p for p in r["saldos"]}
        self.assertEqual(Decimal(lots["A"]["Quantidade"]), Decimal("0.74"))
        self.assertEqual(Decimal(lots["B"]["Quantidade"]), Decimal("0.25"))
        self.assertIsNone(lots["A"]["Custo_Total_USDT"])
        self.assertIsNone(lots["B"]["Custo_Total_USDT"])
        self.assertIsNone(r["custo_taxas_transferencias_usdt"])
        self.assertFalse(r["resultado_completo"])

    def test_known_cost_still_allocates_basis_without_fee(self):
        r = apurar_custodia([self.declaration("100")], [self.movement()])
        lots = {p["Custodia"]: p for p in r["saldos"]}
        self.assertEqual(Decimal(lots["A"]["Custo_Total_USDT"]), Decimal("75"))
        self.assertEqual(Decimal(lots["B"]["Custo_Total_USDT"]), Decimal("25"))
        self.assertEqual(r["custo_taxas_transferencias_usdt"], Decimal("0"))

    def test_sqlite_transfer_is_persisted_without_fictitious_csv_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            dm = DataManager(data_dir=root, auto_import_legacy=False)
            dm.registrar_posicao_externa(
                moeda="BTC", quantidade="1", custodia="A",
                data_posicao="2026-01-01", custo_total_usdt=None,
                confirmacao_independente=True,
            )
            dm.registrar_movimento_custodia(
                tipo="transferencia", moeda="BTC", origem="A",
                destino="B", quantidade="0.25", data_utc="2026-01-02",
                taxa_ativo="0", receita_usdt="0", taxa_usdt="0",
                observacao="Documento de transferência taxa zero F02",
            )
            self.assertEqual(len(dm.carregar_movimentos_custodia()), 1)
            self.assertEqual(dm.carregar_operacoes_precisas(), [])
            again = DataManager(data_dir=root, auto_import_legacy=False)
            r = apurar_custodia(
                again.carregar_posicoes_externas(),
                again.carregar_movimentos_custodia(),
            )
            lots = {p["Custodia"]: p for p in r["saldos"]}
            self.assertEqual(Decimal(lots["B"]["Quantidade"]), Decimal("0.25"))
            self.assertIsNone(lots["B"]["Custo_Total_USDT"])
            self.assertEqual(r["custo_taxas_transferencias_usdt"], Decimal("0"))


if __name__ == "__main__":
    unittest.main()
