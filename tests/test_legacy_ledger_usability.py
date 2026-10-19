import csv
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.backend import DataManager
from backend.finance_analytics import calcular_analise_por_periodo
from backend.finance_brl import apurar_brl_historico
from backend.operation_integrity import ErroIntegridadeFinanceira, validar_livro


def trade(coin, kind, qty, price, gross, when='2026-01-02 12:00:00', fx='5', fee=None):
    return dict(Data=when, Moeda=coin, Operacao=kind, Quantidade=qty,
                Preco=price, Valor_USDT=gross, Taxa_BRL=fx, Taxa_Corretagem_USDT=fee)


def legacy_rows():
    return [trade('USDT', 'compra', '1000', '5', '1000', when='2026-01-01 10:00:00'),
            trade('BTC', 'compra', '1', '100', '99.50'),
            trade('BTC', 'venda', '0.5', '120', '60', when='2026-02-01 12:00:00')]


class LegacyLedgerUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        original = root / 'legacy.csv'
        rows = legacy_rows()
        with original.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.dm = DataManager(data_dir=root / 'data', legacy_csv=original)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_operation_is_accepted_despite_unchanged_legacy_divergence(self):
        self.assertTrue(self.dm.salvar_operacao(
            ['2026-03-01 10:00:00', 'ETH', 'compra', '100', '2000', '0.05', '5']))

    def test_new_operation_with_its_own_divergence_is_rejected(self):
        self.assertFalse(self.dm.salvar_operacao(
            ['2026-03-01 10:00:00', 'ETH', 'compra', '100', '2000', '0.06', '5']))
        self.assertIn('ETH', self.dm.ultimo_erro)

    def test_editing_other_fields_of_divergent_operation_is_allowed(self):
        op = dict(self.dm.carregar_operacao_para_edicao(1), Data='2026-01-03 12:00:00')
        self.assertTrue(self.dm.atualizar_operacao(1, op, motivo='Data conferida no extrato'))
        audit = self.dm._store.listar_auditoria_operacoes()
        self.assertEqual(audit[-1]['depois']['Data'], '2026-01-03 12:00:00')

    def test_changing_value_without_fixing_divergence_is_rejected(self):
        op = dict(self.dm.carregar_operacao_para_edicao(1), Valor_USDT='99.00')
        self.assertFalse(self.dm.atualizar_operacao(1, op, motivo='Valor alterado sem conferir'))

    def test_deleting_operation_is_allowed_with_legacy_divergence(self):
        self.assertTrue(self.dm.excluir_operacao(2, motivo='Lançamento duplicado conferido'))

    def test_same_day_entry_order_does_not_block_cash(self):
        self.assertTrue(self.dm.salvar_operacao(
            ['2026-03-01 10:00:30', 'USDT', 'compra', '1500', '5', '1500', '5']))
        self.assertTrue(self.dm.salvar_operacao(
            ['2026-03-01 10:00:00', 'ETH', 'compra', '2000', '2000', '1', '5']))

    def test_negative_cash_at_end_of_day_is_rejected(self):
        self.assertFalse(self.dm.salvar_operacao(
            ['2026-03-01 10:00:00', 'ETH', 'compra', '2000', '2000', '1', '5']))
        self.assertIn('fim do dia', self.dm.ultimo_erro)


class SellAllToleranceTests(unittest.TestCase):
    def rows(self, sold):
        return [trade('USDT', 'compra', '1000', '5', '1000', when='2026-01-01 10:00:00'),
                trade('SUI', 'compra', '100', '1', '100', fee='0'),
                trade('SUI', 'venda', sold, '2', str(Decimal(sold) * 2),
                      when='2026-02-01 12:00:00', fee='0')]

    def test_rounding_residue_on_sell_all_is_accepted(self):
        rows = self.rows('100.0002')
        validar_livro(rows)
        result = calcular_analise_por_periodo(rows)
        self.assertEqual(result['ativos']['SUI']['custo_aberto'], Decimal('0'))
        self.assertEqual(result['ativos']['SUI']['realizado_historico'], Decimal('100.0004'))
        brl = apurar_brl_historico(rows)
        self.assertEqual(brl['ativos']['SUI']['realizado_historico'], Decimal('500.0020'))
        self.assertFalse(brl['avisos'])

    def test_real_oversell_is_still_rejected(self):
        rows = self.rows('101')
        with self.assertRaises(ErroIntegridadeFinanceira):
            validar_livro(rows)
        with self.assertRaises(ValueError):
            calcular_analise_por_periodo(rows)
        self.assertIsNone(apurar_brl_historico(rows)['ativos']['SUI']['custo_aberto'])

    def test_residue_is_carried_so_later_buys_do_not_create_phantom_balance(self):
        rows = self.rows('100.0002') + [trade('SUI', 'compra', '10', '1', '10',
                                              when='2026-03-01 12:00:00', fee='0')]
        result = calcular_analise_por_periodo(rows)
        self.assertEqual(result['ativos']['SUI']['quantidade'], Decimal('9.9998'))


class HistoricalBrlEstimateTests(unittest.TestCase):
    def rows(self, gross='100'):
        return [trade('BTC', 'compra', '1', '100', gross, when='2026-01-01 10:00:00', fx='5'),
                trade('BTC', 'venda', '1', '150', '150', when='2026-02-01 10:00:00', fx='6')]

    def test_strict_mode_is_unchanged(self):
        result = apurar_brl_historico(self.rows())
        self.assertIsNone(result['totais']['realizado_historico'])
        self.assertFalse(result['estimado'])

    def test_missing_fee_is_estimated_with_period_fx(self):
        result = apurar_brl_historico(self.rows(), estimar=True)
        self.assertEqual(result['totais']['realizado_historico'], Decimal('400'))
        self.assertTrue(result['ativos']['BTC']['estimado'])
        self.assertTrue(result['estimado'])

    def test_small_divergence_uses_recorded_value(self):
        result = apurar_brl_historico(self.rows('99.50'), estimar=True)
        self.assertEqual(result['totais']['realizado_historico'], Decimal('402.50'))

    def test_large_divergence_stays_unavailable(self):
        result = apurar_brl_historico(self.rows('50'), estimar=True)
        self.assertIsNone(result['totais']['realizado_historico'])


if __name__ == '__main__':
    unittest.main()
