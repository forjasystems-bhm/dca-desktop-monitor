"""Desktop settings: update checks, explicit shortcut, tray opt-in and backup recovery."""
from pathlib import Path
from tkinter import filedialog, messagebox
import sys
import threading
import customtkinter as ctk

from backend.app_lifecycle import (
    APP_VERSION, carregar_preferencias, salvar_preferencias,
    verificar_release_estavel,
)
from backend.backup_sqlite import (
    verificar_manifesto_sqlite, preparar_restauracao_sqlite,
)
from config.tema_cripto import (
    BG_SURFACE,BG_CARD,BG_INPUT,BORDER,BTC_ORANGE,
    CYAN,TEXT_PRIMARY,TEXT_SECONDARY,NEON_RED,
)


class JanelaAplicativo(ctk.CTkToplevel):
    def __init__(self, parent, data_manager, *, ao_restaurar=None,
                 ao_alterar_preferencia=None):
        super().__init__(parent)
        self.title("DCA Monitor · Aplicativo e manutenção")
        self.geometry("960x720+70+45")
        self.minsize(780,560)
        self._db=data_manager
        self._on_restore=ao_restaurar
        self._on_pref=ao_alterar_preferencia
        self._manifesto_escolhido=None
        self._pref=carregar_preferencias(self._db._store.diretorio)
        self.configure(fg_color=BG_SURFACE)
        wrap=ctk.CTkScrollableFrame(
            self,fg_color="transparent",scrollbar_button_color=BORDER,
        )
        wrap.pack(fill="both",expand=True,padx=12,pady=12)
        ctk.CTkLabel(
            wrap,text="APLICATIVO  ·  PREFERÊNCIAS E MANUTENÇÃO",
            font=ctk.CTkFont("Segoe UI",19,"bold"),text_color=BTC_ORANGE,
        ).pack(anchor="w",padx=8,pady=(6,12))

        updates=self._box(wrap,"Atualizações voluntárias")
        ctk.CTkLabel(
            updates,text=f"Versão instalada: {APP_VERSION} (desenvolvimento)",
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w",padx=12,pady=4)
        self.status_atualizacao=self._texto(
            updates,
            "Não verificado. Consultaremos apenas GitHub Releases estáveis, "
            "nunca branches ou PRs. Nenhuma atualização é baixada automaticamente.",
        )
        ctk.CTkButton(
            updates,text="Verificar atualizações",fg_color=BG_INPUT,
            command=self._verificar_atualizacoes,
        ).pack(anchor="w",padx=12,pady=(7,4))
        self._btn_instalar=ctk.CTkButton(
            updates,text="Atualizar agora — indisponível nesta versão",
            state="disabled",fg_color=BG_INPUT,
        )
        self._btn_instalar.pack(anchor="w",padx=12,pady=(4,12))

        shortcuts=self._box(wrap,"Atalho da Área de Trabalho")
        self.status_atalho=self._texto(
            shortcuts,
            "Cria um atalho .lnk apontando para o executável instalado. "
            "Nenhum atalho é criado automaticamente.",
        )
        frozen=getattr(sys,"frozen",False)
        preview=(Path(sys.executable).parent/"DCA-PREVIEW-MODE").is_file()
        enabled=sys.platform=="win32" and frozen and not preview
        self.btn_atalho=ctk.CTkButton(
            shortcuts,text="Criar atalho na Área de Trabalho",
            state="normal" if enabled else "disabled",
            fg_color=BTC_ORANGE,text_color=BG_SURFACE,
            command=self._criar_atalho,
        )
        self.btn_atalho.pack(anchor="w",padx=12,pady=(7,12))
        if not enabled:
            self.status_atalho.configure(
                text="Atalho operacional disponível apenas após instalar "
                "uma versão Windows homologada; este é um ambiente de desenvolvimento.",
            )

        second=self._box(wrap,"Segundo plano (Windows)")
        self.variavel_bandeja=ctk.BooleanVar(
            value=self._pref["minimizar_para_bandeja"],
        )
        self._switch=ctk.CTkSwitch(
            second,variable=self.variavel_bandeja,
            text="Ao fechar a janela, minimizar para a bandeja",
            command=self._alternar_bandeja,
            fg_color=BG_INPUT,progress_color=BTC_ORANGE,
            text_color=TEXT_PRIMARY,
        )
        self._switch.pack(anchor="w",padx=12,pady=(9,6))
        self._texto(
            second,
            "Desativado por padrão. Na bandeja: Abrir, Atualizar cotações, "
            "Sair completamente. Não inicia com o Windows nem negocia cripto.",
        ).pack_configure(pady=(0,12))

        recovery=self._box(wrap,"Backup e recuperação segura do SQLite")
        self.status_backup=self._texto(
            recovery,
            "Verifique backups e seus hashes. Restaurar exige encerrar o "
            "aplicativo e confirmar a manutenção em janela separada.",
        )
        row=ctk.CTkFrame(recovery,fg_color="transparent")
        row.pack(anchor="w",padx=12,pady=8)
        ctk.CTkButton(
            row,text="Conferir backups",fg_color=BG_INPUT,
            command=self._verificar_backups,
        ).pack(side="left",padx=(0,8))
        ctk.CTkButton(
            row,text="Preparar cópia de recuperação",
            fg_color=BG_INPUT,command=self._preparar_recuperacao,
        ).pack(side="left",padx=8)
        self._btn_restaurar=ctk.CTkButton(
            recovery,text="Fechar aplicativo e ativar recuperação",
            fg_color=BTC_ORANGE,text_color=BG_SURFACE,
            state="disabled",command=self._pedir_restauracao,
        )
        self._btn_restaurar.pack(anchor="w",padx=12,pady=(4,13))
        self._verificar_backups()

    def _box(self,parent,title):
        box=ctk.CTkFrame(
            parent,fg_color=BG_CARD,border_color=BORDER,border_width=1,
        )
        box.pack(fill="x",padx=8,pady=(0,12))
        ctk.CTkLabel(
            box,text=title,text_color=BTC_ORANGE,
            font=ctk.CTkFont("Segoe UI",13,"bold"),
        ).pack(anchor="w",padx=12,pady=(10,6))
        return box

    def _texto(self,parent,value):
        lbl=ctk.CTkLabel(
            parent,text=value,text_color=TEXT_SECONDARY,
            wraplength=820,justify="left",anchor="w",
        )
        lbl.pack(fill="x",padx=12,pady=4)
        return lbl

    def _verificar_atualizacoes(self):
        self.status_atualizacao.configure(text="Verificando canal oficial de releases...")
        def tarefa():
            result=verificar_release_estavel()
            try:
                self.after(0,lambda: self.status_atualizacao.configure(
                    text=result["mensagem"]+" Nenhum pacote é instalado nesta etapa.",
                ) if self.winfo_exists() else None)
            except Exception:
                pass
        threading.Thread(target=tarefa,daemon=True).start()

    def _criar_atalho(self):
        if not messagebox.askyesno(
            "Criar atalho", "Criar um atalho para a instalação atual na Área de Trabalho?",
            parent=self,
        ):
            return
        try:
            from config.install import install_windows
            install_windows()
            self.status_atalho.configure(
                text="Comando executado. Confira o atalho no Desktop do Windows.",
                text_color=CYAN,
            )
        except Exception as exc:
            messagebox.showerror("Atalho não criado",str(exc),parent=self)

    def _alternar_bandeja(self):
        new=bool(self.variavel_bandeja.get())
        try:
            saved=salvar_preferencias(
                {"minimizar_para_bandeja":new},
                self._db._store.diretorio,
            )
            self._pref=saved
            if self._on_pref:
                self._on_pref(saved)
        except Exception as exc:
            self.variavel_bandeja.set(not new)
            messagebox.showerror("Preferência não salva",str(exc),parent=self)

    def _verificar_backups(self):
        folder=Path(self._db.arquivo_db).parent/"backups"/"sqlite"
        checked=[]
        invalid=[]
        for file in sorted(folder.glob("portfolio-*.json")) if folder.exists() else []:
            try:
                value=verificar_manifesto_sqlite(file)
                checked.append((file,value))
            except Exception as exc:
                invalid.append(f"{file.name}: {exc}")
        last=checked[-1][0].name if checked else "nenhum"
        message=(
            f"Backups íntegros: {len(checked)} · Mais recente: {last}. "
            + (f"ERRO em {len(invalid)} cópia(s): "+", ".join(invalid[:3])
               if invalid else "Nenhuma falha identificada.")
            + " Uma cópia externa é recomendada."
        )
        self.status_backup.configure(
            text=message,text_color=NEON_RED if invalid else TEXT_SECONDARY,
        )
        return checked,invalid

    def _preparar_recuperacao(self):
        base=Path(self._db.arquivo_db).parent/"backups"/"sqlite"
        manifest=filedialog.askopenfilename(
            title="Selecione o manifesto JSON de um backup verificado",
            initialdir=str(base),filetypes=[("Manifesto SQLite","*.json")],
            parent=self,
        )
        if not manifest:
            return
        try:
            info=verificar_manifesto_sqlite(Path(manifest))
        except Exception as exc:
            messagebox.showerror("Backup inválido",str(exc),parent=self)
            return
        destino=filedialog.asksaveasfilename(
            title="Salvar cópia de recuperação em arquivo SEPARADO",
            defaultextension=".sqlite3",
            initialfile="dca-recuperado.sqlite3",
            filetypes=[("Banco SQLite","*.sqlite3")],
            parent=self,
        )
        if not destino:
            return
        try:
            db=Path(self._db.arquivo_db).resolve()
            if Path(destino).resolve()==db:
                raise ValueError("Não é permitido usar o banco ativo como destino.")
            stage=preparar_restauracao_sqlite(Path(manifest),Path(destino))
            self._manifesto_escolhido=Path(manifest)
            self._btn_restaurar.configure(state="normal")
            self.status_backup.configure(
                text=f"Cópia recuperada e verificada: {stage['preparado']}. "
                "O banco operacional não foi substituído. Para ativar "
                "essa cópia será necessário fechar o aplicativo.",
                text_color=CYAN,
            )
        except Exception as exc:
            messagebox.showerror("Recuperação não preparada",str(exc),parent=self)

    def _pedir_restauracao(self):
        if self._manifesto_escolhido is None or self._on_restore is None:
            return
        if not messagebox.askyesno(
            "Manutenção offline",
            "Fechar o programa, verificar novamente o manifesto e solicitar "
            "ativação do backup? O banco atual será preservado em rollback. "
            "Não há restauração automática sem sua confirmação.",
            parent=self,
        ):
            return
        self._on_restore(self._manifesto_escolhido)
