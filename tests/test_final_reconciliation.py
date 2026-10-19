"""Synthetic release acceptance, independent of the legacy regression fixtures."""
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.backend import AnalysisEngine, DataManager
from backend.finance_analytics import calcular_analise_por_periodo
from backend.finance_brl import apurar_brl_historico
from backend.historical_valuation import patrimonio_historico_na_data


def trade(coin,kind,qty,price,gross,day='2026-01-02',fx='5',fee='0'):
    return dict(Data=day+' 12:00:00',Moeda=coin,Operacao=kind,Quantidade=qty,
                Preco=price,Valor_USDT=gross,Taxa_BRL=fx,Taxa_Corretagem_USDT=fee)


class FinalReconciliationTests(unittest.TestCase):
    def rows(self):
        return [trade('USDT','compra','10000','5','10000',day='2026-01-01',fee=None),
                trade('UNI','compra','173.8','10','1737.50'),
                trade('UNI','venda','173.8','11','1911.8',day='2026-02-01'),
                trade('BTC','compra','1','100','100'),
                trade('BTC','venda','1','150','150',day='2026-02-01')]

    def test_small_pending_uni_is_estimated_and_does_not_hide_btc(self):
        result=calcular_analise_por_periodo(self.rows())
        self.assertEqual(result['ativos']['UNI']['realizado_historico'],Decimal('174.30'))
        self.assertTrue(result['ativos']['UNI']['estimado'])
        self.assertFalse(result['ativos']['UNI']['conciliado'])
        self.assertEqual(result['ativos']['BTC']['realizado_historico'],Decimal('50'))
        self.assertNotIn('estimado',result['ativos']['BTC'])
        self.assertTrue(result['pendencias_conciliacao'])
        self.assertTrue(result['pendencias_conciliacao'][0]['estimavel'])
        current=AnalysisEngine.calcular_portfolio(self.rows(),{'UNI':11,'BTC':150})
        self.assertAlmostEqual(current['UNI']['lucro_realizado'],174.30)
        self.assertTrue(current['UNI']['estimado'])
        self.assertEqual(current['BTC']['lucro_realizado'],50)
        self.assertNotIn('estimado',current['BTC'])
        self.assertTrue(current['totais']['estimado'])
        self.assertTrue(current['totais']['avaliacao_completa'])
        self.assertIsNotNone(current['totais']['valor_atual'])
        import csv
        with TemporaryDirectory() as temp:
            original=Path(temp)/'synthetic.csv'
            with original.open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(self.rows()[0]))
                writer.writeheader();writer.writerows(self.rows())
            dm=DataManager(data_dir=Path(temp)/'data',legacy_csv=original)
            self.assertIsNone(patrimonio_historico_na_data(dm._store,date(2026,3,1))['lucro_realizado'])

    def test_large_pending_uni_does_not_become_usdt_profit_or_hide_btc(self):
        rows=self.rows()
        rows[1]=trade('UNI','compra','173.8','10','1000')
        result=calcular_analise_por_periodo(rows)
        self.assertIsNone(result['ativos']['UNI']['realizado_historico'])
        self.assertIsNone(result['ativos']['UNI']['custo_aberto'])
        self.assertEqual(result['ativos']['BTC']['realizado_historico'],Decimal('50'))
        self.assertIsNone(result['totais']['realizado_historico'])
        self.assertFalse(result['pendencias_conciliacao'][0]['estimavel'])
        current=AnalysisEngine.calcular_portfolio(rows,{'UNI':11,'BTC':150})
        self.assertIsNone(current['UNI']['lucro_realizado'])
        self.assertEqual(current['BTC']['lucro_realizado'],50)
        self.assertIsNone(current['totais']['realizado'])
        self.assertIsNone(current['totais']['valor_atual'])
        self.assertFalse(current['totais']['estimado'])

    def test_future_pending_operation_does_not_invalidate_earlier_cut(self):
        early=calcular_analise_por_periodo(self.rows(),fim='2026-01-01')
        self.assertFalse(early['pendencias_conciliacao'])
        self.assertEqual(early['totais']['realizado_historico'],Decimal('0'))

    def test_brl_independent_positive_negative_and_undocumented_fx(self):
        rows=[trade('BTC','compra','2','100','200',fx='5',fee='2'),
              trade('BTC','venda','1','150','150',day='2026-02-01',fx='6',fee='1')]
        # Purchase basis (200+2)*5=1010; allocated 505. Sale (150-1)*6=894.
        self.assertEqual(apurar_brl_historico(rows)['totais']['realizado_historico'],Decimal('389'))
        rows[-1]['Taxa_BRL']='3'
        self.assertEqual(apurar_brl_historico(rows)['totais']['realizado_historico'],Decimal('-58'))
        rows[0]['Taxa_BRL']='0'
        self.assertIsNone(apurar_brl_historico(rows)['totais']['realizado_historico'])

    def test_individual_correction_can_reduce_two_legacy_issues_with_full_audit(self):
        import csv
        with TemporaryDirectory() as temp:
            root=Path(temp); original=root/'synthetic.csv'
            rows=self.rows()+[trade('ETH','compra','1','10','9.5')]
            with original.open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
                writer.writeheader();writer.writerows(rows)
            raw=original.read_bytes()
            dm=DataManager(data_dir=root/'data',legacy_csv=original)
            corrected=dict(dm.carregar_operacao_para_edicao(1),Valor_USDT='1738.00')
            self.assertTrue(dm.conciliar_operacao(1,corrected,motivo='Comprovante sintético confirma o valor bruto'))
            self.assertEqual(original.read_bytes(),raw)
            audit=dm._store.listar_auditoria_operacoes()
            self.assertEqual(audit[-1]['antes']['Valor_USDT'],'1737.50')
            self.assertEqual(audit[-1]['depois']['Valor_USDT'],'1738.00')
            self.assertEqual(audit[-1]['depois']['Taxa_Corretagem_USDT'],'0')
            # Remaining unrelated issue stays pending, never silently approved.
            r=calcular_analise_por_periodo(dm.carregar_operacoes_precisas())
            self.assertEqual(r['ativos']['UNI']['realizado_historico'],Decimal('173.80'))
            self.assertTrue(r['pendencias_conciliacao'])
            before=dm.arquivo_db.read_bytes()
            bad=dict(corrected,Quantidade='9999')
            self.assertFalse(dm.conciliar_operacao(1,bad,motivo='Teste sintético de rejeição segura'))
            self.assertEqual(dm.arquivo_db.read_bytes(),before)
            # Historical API propagates an unavailable aggregate without crashing.
            historical=patrimonio_historico_na_data(dm._store,date(2026,3,1))
            self.assertIsNone(historical['lucro_realizado'])


if __name__=='__main__':
    unittest.main()
