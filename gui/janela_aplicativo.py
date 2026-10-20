from backend.ui_dispatch import UiDispatcher
"""Desktop settings: update checks, explicit shortcut, tray opt-in and backup recovery."""
from pathlib import Path
from tkinter import filedialog, messagebox
import sys
import threading
import customtkinter as ctk

from backend.app_lifecycle import (
    APP_VERSION, carregar_preferencias, salvar_preferencias,
    verificar_release_estavel, baixar_atualizacao_verificada,
    preparar_atualizacao_manual,
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
                 ao_alterar_preferencia=None, ao_instalar=None):
        super().__init__(parent)
        self.transient(parent)
        self._tasks = UiDispatcher(self)
        self.title("DCA Monitor · Aplicativo e manutenção")
        self.geometry("960x720+70+45")
        self.minsize(780,560)
        self._db=data_manager
        self._on_restore=ao_restaurar
        self._on_pref=ao_alterar_preferencia
        self._on_install=ao_instalar
        self._manifesto_escolhido=None
        self._atualizacao_encontrada=None
        self._download_verificado=None
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
            updates,text=f"Versão instalada: {APP_VERSION}",
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
            updates,text="Baixar atualização",
            state="disabled",fg_color=BG_INPUT,
            command=self._baixar_atualizacao,
        )
        self._btn_instalar.pack(anchor="w",padx=12,pady=(4,12))
        self._btn_backup_atualizacao=ctk.CTkButton(updates,text='Preparar atualização (backup recuperável)',
            state='disabled',fg_color=BG_INPUT,command=self._preparar_atualizacao)
        self._btn_backup_atualizacao.pack(anchor='w',padx=12,pady=4)
        self._btn_aplicar=ctk.CTkButton(updates,text='Instalar atualização e reabrir',
                      state='disabled',fg_color=BTC_ORANGE,text_color=BG_SURFACE,
                      command=self._instalar_atualizacao)
        self._btn_aplicar.pack(anchor='w',padx=12,pady=4)
        self._texto(updates,'No Windows, a instalação cria uma pasta para a nova versão, '
                    'testa um backup e reabre o aplicativo com seus dados. '
                    'O atalho só muda após a confirmação de abertura. '
                    'No Linux, a troca da pasta continua manual.')

        shortcuts=self._box(wrap,"Atalho da Área de Trabalho")
        self.status_atalho=self._texto(
            shortcuts,
            "O Windows cria o atalho na primeira abertura. "
            "Use este botão para recriá-lo nesta instalação.",
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
        if sys.platform != 'win32':
            self._switch.configure(state='disabled')
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
        ctk.CTkButton(recovery,text="Exportar pacote portátil de recuperação",
            fg_color=BG_INPUT,command=self._exportar_pacote).pack(anchor="w",padx=12,pady=6)
        ctk.CTkButton(recovery,text="Escolher destino independente de backup",
            fg_color=BG_INPUT,command=self._escolher_backup_externo).pack(anchor="w",padx=12,pady=6)
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
        self._atualizacao_encontrada = None
        self._download_verificado = None
        self._btn_backup_atualizacao.configure(state='disabled')
        self._btn_aplicar.configure(state='disabled')
        self._btn_instalar.configure(state="disabled")
        self.status_atualizacao.configure(text="Verificando releases oficiais...")
        def tarefa():
            result = verificar_release_estavel()
            def complete():
                if not self.winfo_exists():
                    return
                self._atualizacao_encontrada = (
                    result if result.get("download_disponivel") else None
                )
                self._btn_instalar.configure(
                    state="normal" if self._atualizacao_encontrada else "disabled")
                self.status_atualizacao.configure(text=result["mensagem"])
            self._tasks.post(complete)
        self._tasks.run(tarefa)

    def _baixar_atualizacao(self):
        info = self._atualizacao_encontrada
        if info is None:
            return
        pacote = info["pacote"]
        if not messagebox.askyesno(
            "Baixar atualização verificada",
            f"Baixar {pacote['nome']} do GitHub oficial?\n\n"
            "Após verificar SHA-256, você decidirá quando instalar. "
            "O aplicativo e seu banco de dados não serão substituídos agora.",
            parent=self,
        ):
            return
        target = filedialog.asksaveasfilename(
            parent=self, title="Salvar atualização verificada",
            initialfile=pacote["nome"],
            defaultextension=".zip" if sys.platform=="win32" else ".gz",
            filetypes=[("Atualização do DCA", "*.zip *.gz"), ("Todos", "*.*")],
        )
        if not target:
            return
        self._btn_instalar.configure(state="disabled")
        self.status_atualizacao.configure(text="Baixando e verificando SHA-256...")
        def task():
            try:
                result = baixar_atualizacao_verificada(info, Path(target))
                error = None
            except Exception as exc:
                result, error = None, str(exc)
            def completed():
                if not self.winfo_exists():
                    return
                self._btn_instalar.configure(state="normal")
                if error:
                    self.status_atualizacao.configure(
                        text="Download não concluído: " + error)
                else:
                    self._download_verificado=(info,result['arquivo'])
                    self._btn_backup_atualizacao.configure(state='normal')
                    if sys.platform == 'win32' and getattr(sys,'frozen',False) and self._on_install:
                        self._btn_aplicar.configure(state='normal')
                    self.status_atualizacao.configure(
                        text="Download e SHA-256 verificados em "
                        + result["arquivo"] +
                        ". Agora você pode instalar e reabrir no Windows, "
                        "ou preparar um backup para troca manual. Seus dados continuam intactos.")
            self._tasks.post(completed)
        self._tasks.run(task)

    def _preparar_atualizacao(self):
        if not self._download_verificado:
            return
        if not messagebox.askyesno('Preparar atualização',
            'Criar e testar um backup portátil antes da instalação manual? '
            'Nenhum executável será substituído.',parent=self):
            return
        target=filedialog.asksaveasfilename(parent=self,title='Salvar backup portátil recuperável',
            defaultextension='.zip',initialfile='DCA-antes-atualizacao.zip',filetypes=[('Backup DCA','*.zip')])
        if not target:
            return
        info,path=self._download_verificado
        self._btn_backup_atualizacao.configure(state='disabled')
        def worker():
            try:
                result=preparar_atualizacao_manual(info,path,self._db.arquivo_db,Path(target))
                text=result['mensagem']+' Backup: '+result['backup']['pacote']
            except Exception as exc:
                text='Preparação recusada. Preserve a instalação atual: '+str(exc)
            def done():
                self.status_atualizacao.configure(text=text)
                self._btn_backup_atualizacao.configure(state='normal')
            self._tasks.post(done)
        self._tasks.run(worker)

    def _instalar_atualizacao(self):
        if not self._download_verificado or not self._on_install:
            return
        if not messagebox.askyesno('Instalar atualização',
                'Fechar o DCA, criar e testar um backup da carteira e abrir a nova versão? '
                'Se a preparação falhar, os arquivos serão preservados. '
                'Não há restauração automática do banco.', parent=self):
            return
        info, archive = self._download_verificado
        self._btn_aplicar.configure(state='disabled')
        self._btn_instalar.configure(state='disabled')
        self.status_atualizacao.configure(text='Verificando e preparando a nova versão...')
        def worker():
            try:
                from backend.update_install import preparar_instalacao
                result = preparar_instalacao(info, archive, self._db.arquivo_db)
                error = None
            except Exception as exc:
                result, error = None, str(exc)
            def done():
                if not self.winfo_exists():
                    return
                if error:
                    self.status_atualizacao.configure(text='Instalação recusada: ' + error)
                    self._btn_aplicar.configure(state='normal')
                    return
                try:
                    from backend.update_install import iniciar_instalacao
                    iniciar_instalacao(result['acao'])
                except Exception as exc:
                    self.status_atualizacao.configure(text='Auxiliar não iniciou: ' + str(exc))
                    self._btn_aplicar.configure(state='normal')
                    return
                self._on_install()
            self._tasks.post(done)
        self._tasks.run(worker)

    def _criar_atalho(self):
        if not messagebox.askyesno(
            "Criar atalho", "Criar um atalho para a instalação atual na Área de Trabalho?",
            parent=self,
        ):
            return
        try:
            from config.install import install_windows
            resultado=install_windows()
            self.status_atalho.configure(
                text=f"{resultado['status']} Local: {resultado['atalho']}",
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

    def _escolher_backup_externo(self):
        target=filedialog.askdirectory(parent=self,title="Destino independente para cópias de segurança")
        if not target:return
        try:
            from backend.backup_policy import configurar_destino_independente,proteger_gravacao
            configurar_destino_independente(Path(self._db.arquivo_db).parent,target)
            proteger_gravacao(self._db.arquivo_db)
            self.status_backup.configure(text="Backup independente verificado em "+target+". Retenção: todas as cópias.",text_color=CYAN)
        except Exception as exc:messagebox.showerror("Backup independente pendente",str(exc),parent=self)

    def _exportar_pacote(self):
        destino=filedialog.asksaveasfilename(parent=self,title="Salvar pacote de recuperação",
            defaultextension=".zip",initialfile="DCA-Recuperacao.zip",filetypes=[("Pacote DCA","*.zip")])
        if not destino:return
        try:
            from backend.recovery_bundle import exportar_pacote
            result=exportar_pacote(self._db.arquivo_db,destino)
            self.status_backup.configure(text="Pacote portátil verificado: "+result["pacote"],text_color=CYAN)
        except Exception as exc:
            messagebox.showerror("Pacote não exportado",str(exc),parent=self)

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
