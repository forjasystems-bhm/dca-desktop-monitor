"""Regression: real-world historic CSV uses unpadded month/day, not bad time.

All fixtures are fabricated. Do not load the user's CSV in CI.
"""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import sqlite3
import unittest

from backend.backend import DataManager
from backend.storage_sqlite import ErroMigracao

HEADER = b"Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\r\n"
RECORDS = (
    b"2026-01-31 22:01:51,BTC,compra,100,1000,0.1,5.25\r\n"
    b"2026-01-31 22:03:11,ETH,compra,200,2000,0.1,5.25\r\n"
    b"2026-01-31 22:03:55,LINK,compra,100,100,1,5.25\r\n"
    b"2026-1-31 22:04:09,NEAR,compra,50,50,1,5.25\r\n"
)

class HistoricCsvDateCompatibilityTests(unittest.TestCase):
    def test_line_five_unpadded_month_is_canonicalized_not_rejected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=root/"source.csv"
            content=HEADER+RECORDS
            original.write_bytes(content)
            manager=DataManager(data_dir=root/"wallet",legacy_csv=original,auto_import_legacy=False)
            preview=manager.prever_csv(str(original))
            self.assertEqual(preview["quantidade"],4)
            manager.confirmar_csv(str(original),preview["sha256"])
            stored=manager.carregar_operacoes_precisas()
            self.assertEqual(stored[3]["Data"],"2026-01-31 22:04:09")
            self.assertEqual(original.read_bytes(),content)
            digest=hashlib.sha256(content).hexdigest()
            self.assertEqual(preview["sha256"],digest)
            verified=root/"wallet"/"backups"/("legado-"+digest+".csv")
            self.assertEqual(verified.read_bytes(),content)
            with closing(sqlite3.connect(manager.arquivo_db)) as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM operacoes"
                ).fetchone()[0],4)

    def test_unpadded_day_is_normalized_too(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/"source.csv"
            original.write_bytes(
                HEADER+b"2026-1-3 09:05:07,BTC,compra,100,1000,0.1,5.25\r\n"
            )
            manager=DataManager(data_dir=root/"wallet",legacy_csv=original,auto_import_legacy=False)
            preview=manager.prever_csv(str(original))
            manager.confirmar_csv(str(original),preview["sha256"])
            self.assertEqual(manager.carregar_operacoes_precisas()[0]["Data"],
                             "2026-01-03 09:05:07")

    def test_invalid_calendar_date_still_fails_without_partial_import(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/"source.csv"
            content=HEADER+RECORDS+b"2026-2-30 09:05:07,BTC,compra,50,100,0.5,5.25\r\n"
            original.write_bytes(content)
            manager=DataManager(data_dir=root/"wallet",legacy_csv=original,auto_import_legacy=False)
            with self.assertRaisesRegex(ErroMigracao,r"Linha 6: data inválida"):
                manager.prever_csv(str(original))
            with closing(sqlite3.connect(manager.arquivo_db)) as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM operacoes"
                ).fetchone()[0],0)
            self.assertEqual(original.read_bytes(),content)

    def test_reject_trailing_timezone_and_non_numeric_date(self):
        from backend.storage_sqlite import _validar
        row={"Data":"2026-01-31T22:04:09Z","Moeda":"BTC",
             "Operacao":"compra","Valor_USDT":"100","Preco":"1000",
             "Quantidade":"0.1","Taxa_BRL":"5.25"}
        with self.assertRaisesRegex(ErroMigracao,"data inválida"):
            _validar(row,2)
        row["Data"]="2026-01-3A 22:04:09"
        with self.assertRaisesRegex(ErroMigracao,"data inválida"):
            _validar(row,2)

if __name__=="__main__":
    unittest.main()
