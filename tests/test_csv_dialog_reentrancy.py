"""Synthetic regressions: background balance errors must not steal modal focus."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import ast
import unittest
from unittest.mock import Mock, patch

from backend.ui_dispatch import UiDispatcher
from backend.custody_ledger import apurar_custodia
from backend.stablecoin_ledger import ErroStablecoin
from backend.backend import DataManager
from backend.stablecoin_ledger import saldos_stablecoins


def callbacks_without_display(filename, class_name, methods):
    """Run the production callbacks without constructing Tk or requiring CTk.

    The separate GUI acceptance runs the full widgets and real file picker.
    """
    path = Path(__file__).resolve().parents[1] / 'gui' / filename
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    namespace = dict(filedialog=SimpleNamespace(askopenfilename=Mock()),
        messagebox=SimpleNamespace(showerror=Mock()), CYAN='cyan', NEON_RED='red',
        _CARD_DEFS=[('depositos',), ('saques',), ('compras',), ('vendas',)],
        apurar_custodia=apurar_custodia)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in methods}), namespace


JanelaCaixa, caixa_globals = callbacks_without_display('janela_caixa.py', 'JanelaCaixa',
    ['_mostrar_erro_saldo', '_worker_atualizar'])
JanelaPrimeiroUso, csv_globals = callbacks_without_display('janela_primeiro_uso.py', 'JanelaPrimeiroUso',
    ['_escolher_csv', '_concluir_previa_csv'])


class CsvDialogRegressions(unittest.TestCase):
    def test_background_balance_error_is_inline_and_clears_stale_values(self):
        ui = SimpleNamespace(lbl_status=Mock(), lbl_saldo=Mock(),
            lbl_saldo_usdc=Mock(), lbl_fluxo_usdc=Mock(), tree=Mock(), _set_card=Mock())
        ui.tree.get_children.return_value = ['stale']
        with patch.object(caixa_globals['messagebox'], 'showerror') as modal:
            JanelaCaixa._mostrar_erro_saldo(ui, 'Registro 207: USDT divergente')
        modal.assert_not_called()
        self.assertIn('207', ui.lbl_status.configure.call_args.kwargs['text'])
        self.assertIn('Histórico e Edição', ui.lbl_status.configure.call_args.kwargs['text'])
        self.assertIn('não apurado', ui.lbl_saldo.configure.call_args.kwargs['text'])
        self.assertEqual(ui._set_card.call_count, 4)
        ui.tree.delete.assert_called_once_with('stale')

    def test_worker_posts_inline_error_instead_of_modal(self):
        callbacks = []
        ui = SimpleNamespace(_tasks=SimpleNamespace(post=callbacks.append),
            _data_manager=Mock(), _engine=Mock(), _mostrar_erro_saldo=Mock())
        ui._data_manager.carregar_operacoes.side_effect = ErroStablecoin('Registro 207')
        with patch.object(caixa_globals['messagebox'], 'showerror') as modal:
            JanelaCaixa._worker_atualizar(ui)
            for callback in callbacks:
                callback()
        modal.assert_not_called()
        ui._mostrar_erro_saldo.assert_called_once_with('Registro 207')

    def chooser(self):
        owner = object()
        ui = SimpleNamespace(_previa={'arquivo': 'old.csv'}, _csv_em_andamento=False,
            _btn_escolher_csv=Mock(), _btn_importar=Mock(), _resumo_csv=Mock(),
            _db=Mock(), _tasks=Mock(), winfo_toplevel=lambda: owner)
        return ui, owner

    def test_cancel_invalidates_old_preview_and_owns_dialog(self):
        ui, owner = self.chooser()
        with patch.object(csv_globals['filedialog'], 'askopenfilename', return_value='') as dialog:
            JanelaPrimeiroUso._escolher_csv(ui)
        self.assertIs(dialog.call_args.kwargs['parent'], owner)
        self.assertIsNone(ui._previa)
        ui._btn_importar.configure.assert_called_with(state='disabled')
        ui._db.prever_csv.assert_not_called()
        self.assertFalse(ui._csv_em_andamento)

    def test_dialog_failure_is_inline_and_allows_retry(self):
        ui, _ = self.chooser()
        with patch.object(csv_globals['filedialog'], 'askopenfilename', side_effect=RuntimeError('synthetic Tk failure')):
            JanelaPrimeiroUso._escolher_csv(ui)
        self.assertIn('synthetic Tk failure', ui._resumo_csv.configure.call_args.kwargs['text'])
        self.assertFalse(ui._csv_em_andamento)
        ui._btn_escolher_csv.configure.assert_called_with(state='normal')

    def test_reentrant_click_does_not_open_second_dialog(self):
        ui, _ = self.chooser()
        ui._csv_em_andamento = True
        with patch.object(csv_globals['filedialog'], 'askopenfilename') as dialog:
            JanelaPrimeiroUso._escolher_csv(ui)
        dialog.assert_not_called()

    def test_preview_is_scheduled_instead_of_running_in_click_callback(self):
        ui, _ = self.chooser()
        with patch.object(csv_globals['filedialog'], 'askopenfilename', return_value='synthetic.csv'):
            JanelaPrimeiroUso._escolher_csv(ui)
        ui._db.prever_csv.assert_not_called()
        ui._tasks.run.assert_called_once()

    def test_failed_async_preview_keeps_import_disabled_and_allows_retry(self):
        ui, _ = self.chooser()
        with patch.object(csv_globals['messagebox'], 'showerror') as modal:
            JanelaPrimeiroUso._concluir_previa_csv(ui, None, 'synthetic bad CSV')
        self.assertIsNone(ui._previa)
        self.assertFalse(ui._csv_em_andamento)
        ui._btn_importar.configure.assert_called_with(state='disabled')
        ui._btn_escolher_csv.configure.assert_called_with(state='normal')
        modal.assert_not_called()

    def test_successful_async_preview_enables_explicit_confirmation(self):
        ui, _ = self.chooser()
        preview = dict(arquivo='synthetic.csv', quantidade=1, moedas=['USDT'],
            primeira_data='2026-01-01', ultima_data='2026-01-01', sha256='synthetic',
            duplicatas_identicas=0)
        JanelaPrimeiroUso._concluir_previa_csv(ui, preview)
        self.assertEqual(ui._previa, preview)
        ui._btn_importar.configure.assert_called_with(state='normal')
        self.assertFalse(ui._csv_em_andamento)

    def test_stablecoin_discrepancy_can_be_audited_without_changing_original(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / 'synthetic.csv'
            raw = (b'Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n'
                   b'2026-01-01 12:00:00,USDT,compra,99.5,5,100,5\n')
            original.write_bytes(raw)
            dm = DataManager(data_dir=root/'data', legacy_csv=original)
            before = dm.carregar_operacoes_precisas()
            db_before = dm.arquivo_db.read_bytes()
            with self.assertRaises(ErroStablecoin):
                saldos_stablecoins(before)
            self.assertEqual(dm.arquivo_db.read_bytes(), db_before)
            self.assertEqual(original.read_bytes(), raw)
            invalid = dict(before[0], Valor_USDT='98')
            self.assertFalse(dm.conciliar_operacao(0, invalid, motivo='Rejeição sintética documentada'))
            self.assertEqual(dm.carregar_operacoes_precisas(), before)
            self.assertEqual(dm.arquivo_db.read_bytes(), db_before)
            corrected = dict(before[0], Valor_USDT='100')
            self.assertTrue(dm.conciliar_operacao(0, corrected, motivo='Comprovante sintético confirma 100 USDT'))
            self.assertEqual(saldos_stablecoins(dm.carregar_operacoes_precisas())['saldos']['USDT'], 100)
            audit = dm._store.listar_auditoria_operacoes()
            self.assertEqual(audit[-1]['antes']['Valor_USDT'], '99.5')
            self.assertEqual(audit[-1]['depois']['Valor_USDT'], '100')
            self.assertEqual(original.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
