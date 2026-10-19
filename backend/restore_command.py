"""Separate graphical maintenance process; never restores during normal startup."""
from pathlib import Path
from tkinter import Tk, messagebox
import time

from backend.restore_offline import (
    CONFIRMACAO, ativar_restauracao_offline,
)


def executar_manutencao_restauracao(manifesto: Path, banco: Path) -> bool:
    """User approves again after the normal application has terminated."""
    window=Tk()
    window.withdraw()
    try:
        time.sleep(1.5)
        manifest=Path(manifesto).expanduser().resolve()
        db=Path(banco).expanduser().resolve()
        if not messagebox.askyesno(
            "DCA Monitor — recuperar banco offline",
            "O aplicativo principal deve estar fechado.\n\n"
            f"Backup: {manifest.name}\n"
            f"Banco a recuperar: {db}\n\n"
            "ATENÇÃO: esta ação trocará o banco ativo por uma cópia verificada. "
            "O banco anterior será preservado para rollback.\n\n"
            "Confirma a ativação agora?",
            parent=window,
        ):
            return False
        try:
            result=ativar_restauracao_offline(
                manifest,db,confirmacao=CONFIRMACAO,
                aplicativo_encerrado=True,
            )
        except Exception as exc:
            messagebox.showerror(
                "Recuperação recusada",
                f"Não foi possível ativar o backup. Nenhuma substituição "
                f"silenciosa é permitida.\n\n{exc}",
                parent=window,
            )
            return False
        messagebox.showinfo(
            "Recuperação concluída",
            f"Banco recuperado: {result['banco']}\n"
            f"Cópia de rollback: {result['rollback_original']}\n\n"
            "Feche esta janela e abra o DCA Monitor normalmente.",
            parent=window,
        )
        return True
    finally:
        window.destroy()


def executar_assistente_recuperacao():
    """Entry point independent of the operational DB and normal GUI boot."""
    from tkinter import filedialog
    from backend.storage_sqlite import diretorio_dados_padrao
    chooser=Tk();chooser.withdraw()
    try:
        manifest=filedialog.askopenfilename(parent=chooser,title='Escolher manifesto do backup DCA',
                                           filetypes=[('Manifesto DCA','*.json')])
        if not manifest:return False
        return executar_manutencao_restauracao(Path(manifest),diretorio_dados_padrao()/'portfolio.sqlite3')
    finally:
        chooser.destroy()
