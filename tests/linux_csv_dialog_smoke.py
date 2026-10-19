"""Real Linux/Tk picker, nested refresh, cancellation and responsive preview.

Run with xvfb-run -a python tests/linux_csv_dialog_smoke.py. Synthetic data only.
"""
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
from backend.backend import DataManager, AnalysisEngine
from gui.janela_caixa import JanelaCaixa
from gui.janela_primeiro_uso import JanelaPrimeiroUso


def main():
    with tempfile.TemporaryDirectory(prefix='dca-csv-dialog-') as temp:
        folder = Path(temp)
        original = folder/'synthetic.csv'
        raw = (b'Data,Moeda,Operacao,Valor_USDT,Preco,Quantidade,Taxa_BRL\n'
               b'2026-01-01 12:00:00,USDT,compra,99.5,5,100,5\n')
        original.write_bytes(raw)
        dm = DataManager(data_dir=folder/'data', auto_import_legacy=False)
        root = ctk.CTk()
        errors = []
        root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
        caixa = JanelaCaixa(root, dm, object(), AnalysisEngine)
        owner = ctk.CTkToplevel(root)
        owner.transient(root)
        first = JanelaPrimeiroUso(owner, dm, lambda: None, lambda: None)
        first.pack(fill='both', expand=True)
        root.update()
        picker_seen = []

        def drive_picker(filename=None):
            try:
                window = '.__tk_filedialog'
                assert root.tk.call('winfo', 'exists', window)
                assert str(root.tk.call('wm', 'transient', window)) == str(owner)
                picker_seen.append(True)
                # This is precisely the callback that used to open a competing
                # modal while askopenfilename runs its nested Tcl event loop.
                caixa._mostrar_erro_saldo('Registro 207: USDT exige unidades iguais ao valor nominal.')
                if filename is None:
                    root.tk.call('::tk::dialog::file::CancelCmd', window)
                else:
                    root.tk.call('::tk::dialog::file::Done', window, str(filename))
            except Exception as exc:
                errors.append(str(exc))
                root.tk.call('set', '::tk::Priv(selectFilePath)', '')

        try:
            with patch('gui.janela_caixa.messagebox.showerror', side_effect=AssertionError('Unexpected modal')):
                root.after(350, drive_picker)
                first._escolher_csv()
                assert picker_seen and not first._csv_em_andamento
                assert first._previa is None
                assert 'Saldo não apurado' in caixa.lbl_saldo.cget('text')
                assert root.winfo_exists() and owner.winfo_exists()
                print('LINUX_REAL_PICKER_BACKGROUND_ERROR_CANCEL=PASS')

                release = threading.Event()
                heartbeat = []
                real_preview = dm.prever_csv
                def slow_preview(filename):
                    assert threading.current_thread() is not threading.main_thread()
                    if not release.wait(5):
                        raise RuntimeError('GUI did not release background preview')
                    return real_preview(filename)
                with patch.object(dm, 'prever_csv', side_effect=slow_preview):
                    root.after(350, lambda: drive_picker(original))
                    first._escolher_csv()
                    assert first._csv_em_andamento
                    root.after(50, lambda: (heartbeat.append(True), release.set()))
                    deadline = time.monotonic() + 8
                    while first._csv_em_andamento and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.005)
                assert heartbeat and first._previa
                assert str(first._btn_importar.cget('state')) == 'normal'
                assert dm.carregar_operacoes_precisas() == []
                print('LINUX_REAL_PICKER_RESPONSIVE_READ_ONLY_PREVIEW=PASS')

                with patch('gui.janela_primeiro_uso.messagebox.askyesno', return_value=True), \
                     patch('gui.janela_primeiro_uso.messagebox.showinfo'), \
                     patch('gui.janela_primeiro_uso.messagebox.showwarning'), \
                     patch('gui.janela_primeiro_uso.messagebox.showerror', side_effect=AssertionError('Import failed')):
                    first._importar_csv()
                caixa.atualizar()
                deadline = time.monotonic() + 5
                while caixa._tasks.running and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.005)
                assert not caixa._tasks.running
                assert 'Registro 1' in caixa.lbl_status.cget('text')
                assert 'Saldo não apurado' in caixa.lbl_saldo.cget('text')
                assert len(dm.carregar_operacoes_precisas()) == 1
                assert original.read_bytes() == raw
                assert not errors, errors
                print('LINUX_DIVERGENT_IMPORT_INLINE_BALANCE_CSV_PRESERVED=PASS')
        finally:
            root.destroy()


if __name__ == '__main__':
    main()
