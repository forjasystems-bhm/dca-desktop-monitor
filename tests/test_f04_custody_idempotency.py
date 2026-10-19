"""F04: one command is posted once; identical independent events stay valid."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.backend import DataManager
from backend.custody_ledger import apurar_custodia
from backend.storage_sqlite import ErroArmazenamento


class CustodyIdempotencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.csv = self.root / 'synthetic-original.csv'
        self.csv.write_bytes(
            b'Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n'
            b'2025-12-31 12:00:00,USDT,compra,100,5,100,5\n'
        )
        self.original = self.csv.read_bytes()
        self.dm = DataManager(data_dir=self.root/'data', legacy_csv=self.csv,
                              auto_import_legacy=False)
        preview = self.dm.prever_csv(str(self.csv))
        self.dm.confirmar_csv(str(self.csv), preview['sha256'])
        self.dm.registrar_posicao_externa(
            moeda='BTC', quantidade='1', custodia='A', data_posicao='2026-01-01',
            custo_total_usdt='100', confirmacao_independente=True,
        )

    def move(self, **changes):
        args = dict(tipo='transferencia', moeda='BTC', origem='A', destino='B',
                    quantidade='0.1', data_utc='2026-01-02', taxa_ativo='0',
                    receita_usdt='0', taxa_usdt='0',
                    observacao='Synthetic documented external event')
        args.update(changes)
        return self.dm.registrar_movimento_custodia(**args)

    def state(self):
        with closing(sqlite3.connect(self.dm.arquivo_db)) as conn:
            return list(conn.iterdump())

    def test_retry_transfer_does_not_post_again_or_create_another_backup(self):
        first = self.move(comando_id='transfer:document-1')
        before = self.state()
        with patch('backend.backup_sqlite.criar_backup_sqlite') as backup:
            second = self.move(comando_id='transfer:document-1')
        backup.assert_not_called()
        self.assertEqual(second['ID'], first['ID'])
        self.assertFalse(second['registrado_agora'])
        self.assertTrue(first['registrado_agora'])
        self.assertEqual(self.state(), before)
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 1)
        self.assertEqual(self.csv.read_bytes(), self.original)

    def test_retry_sale_after_reopening_credits_proceeds_only_once(self):
        first = self.move(comando_id='sale:document-1', tipo='venda', quantidade='1',
                          receita_usdt='20', taxa_usdt='1')
        self.dm = DataManager(data_dir=self.root/'data', auto_import_legacy=False)
        retry = self.move(comando_id='sale:document-1', tipo='venda', quantidade='1',
                          receita_usdt='20', taxa_usdt='1')
        self.assertEqual(first['ID'], retry['ID'])
        result = apurar_custodia(self.dm.carregar_posicoes_externas(),
                                 self.dm.carregar_movimentos_custodia())
        cash = [p for p in result['saldos'] if p['Moeda']=='USDT']
        self.assertEqual(Decimal(cash[0]['Quantidade']), Decimal('19'))
        self.assertEqual(result['vendas'], 1)

    def test_independent_identical_operations_are_not_deduplicated_by_values(self):
        for tipo in ('transferencia', 'venda'):
            for number in (1, 2):
                self.move(comando_id=f'{tipo}:real-{number}', tipo=tipo,
                          receita_usdt='20' if tipo=='venda' else '0')
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 4)
        self.assertEqual(self.csv.read_bytes(), self.original)

    def test_conflicting_payload_for_same_command_is_rejected_without_changes(self):
        self.move(comando_id='document-1')
        before = self.state()
        for changes in ({'quantidade':'0.2'}, {'destino':'C'},
                        {'observacao':'Different document'},
                        {'tipo':'venda', 'receita_usdt':'20'}):
            with self.subTest(changes=changes), self.assertRaises(ErroArmazenamento):
                self.move(comando_id='document-1', **changes)
            self.assertEqual(self.state(), before)
        self.assertEqual(self.csv.read_bytes(), self.original)

    def test_equivalent_decimal_representation_is_the_same_command(self):
        first = self.move(comando_id='document-1')
        retry = self.move(comando_id='document-1', quantidade='0.100', taxa_ativo='0.00')
        self.assertEqual(first['ID'], retry['ID'])
        self.assertFalse(retry['registrado_agora'])

    def test_concurrent_retries_have_one_transactional_winner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.move(comando_id='race:1'), range(2)))
        self.assertEqual(sum(r['registrado_agora'] for r in results), 1)
        self.assertEqual(len({r['ID'] for r in results}), 1)
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 1)

    def test_failed_validation_does_not_reserve_the_command(self):
        before = self.state()
        with self.assertRaises(ValueError):
            self.move(comando_id='rejected:1', quantidade='5')
        self.assertEqual(self.state(), before)
        good = self.move(comando_id='rejected:1')
        self.assertTrue(good['registrado_agora'])

    def test_retry_of_older_command_after_later_event_is_still_idempotent(self):
        first = self.move(comando_id='old-event')
        self.move(comando_id='later-event', data_utc='2026-01-03')
        retry = self.move(comando_id='old-event')
        self.assertEqual(retry['ID'], first['ID'])
        self.assertFalse(retry['registrado_agora'])
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 2)

    def test_invalid_command_identity_does_not_mutate_the_database(self):
        before = self.state()
        for key in ('', 'with spaces', 'x'*129, 123):
            with self.subTest(key=key), self.assertRaises(ErroArmazenamento):
                self.move(comando_id=key)
            self.assertEqual(self.state(), before)

    def test_retry_after_post_commit_backup_warning_does_not_repeat_sale(self):
        with patch('backend.backup_sqlite.criar_backup_sqlite', side_effect=OSError('disk full')):
            first = self.move(comando_id='sale:backup-failed', tipo='venda', receita_usdt='20')
        self.assertIsNotNone(first['aviso_backup_sqlite'])
        retry = self.move(comando_id='sale:backup-failed', tipo='venda', receita_usdt='20')
        self.assertEqual(first['ID'], retry['ID'])
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 1)

    def test_schema_upgrade_preserves_existing_journal_without_inventing_identity(self):
        self.move()
        journal = self.dm.carregar_movimentos_custodia()
        # Remove only F04 metadata to simulate the v6 journal, preserving PK,
        # constraints and all original financial values.
        with closing(sqlite3.connect(self.dm.arquivo_db)) as conn:
            conn.execute('DROP INDEX ux_custodia_comando')
            conn.execute('ALTER TABLE movimentacoes_custodia DROP COLUMN comando_id')
            conn.execute('PRAGMA user_version=6')
            conn.commit()
        self.dm = DataManager(data_dir=self.root/'data', auto_import_legacy=False)
        after = self.dm.carregar_movimentos_custodia()
        self.assertEqual([{k:v for k,v in m.items() if k!='Comando_ID'} for m in after],
                         [{k:v for k,v in m.items() if k!='Comando_ID'} for m in journal])
        self.assertIsNone(after[0]['Comando_ID'])
        self.move(comando_id='post-upgrade')
        self.assertEqual(len(self.dm.carregar_movimentos_custodia()), 2)
        self.assertEqual(self.csv.read_bytes(), self.original)


if __name__=='__main__':
    unittest.main()
