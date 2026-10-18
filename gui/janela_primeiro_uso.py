"""Primeira utilização sem compras fictícias ou perda de histórico CSV."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk

from config.tema_cripto import (
    BG_SURFACE, BG_CARD, BG_INPUT, BORDER, BTC_ORANGE, CYAN,
    TEXT_PRIMARY, TEXT_SECONDARY, NEON_GREEN, NEON_RED,
)


class JanelaPrimeiroUso(ctk.CTkScrollableFrame):
    """Explicit choices: import old operations, declare holdings, or begin empty."""

    def __init__(self, parent, manager, on_change, on_begin_empty):
        super().__init__(
            parent, fg_color=BG_SURFACE, scrollbar_button_color=BORDER,
        )
        self._db = manager
        self._on_change = on_change
        self._on_begin_empty = on_begin_empty
        self._previa = None
        self._titulo = ctk.CTkLabel(
            self, text="PRIMEIRO ACESSO  ·  SEUS DADOS CONTINUAM SEUS",
            text_color=BTC_ORANGE, font=ctk.CTkFont("Segoe UI", 19, "bold"),
        )
        self._titulo.pack(anchor="w", padx=18, pady=(15, 6))
        ctk.CTkLabel(
            self, text=(
                "Escolha UM ponto de partida. Não conectamos à corretora, "
                "não solicitamos chaves privadas e não presumimos compras."
            ), text_color=TEXT_SECONDARY, wraplength=890, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))
        self._estado = ctk.CTkLabel(
            self, text="", text_color=CYAN, wraplength=900, justify="left",
        )
        self._estado.pack(anchor="w", padx=18, pady=(0, 8))

        csv = self._box("1 · JÁ USAVA A VERSÃO ANTIGA?  IMPORTE SEU CSV")
        ctk.CTkLabel(
            csv, text=(
                "Escolha o arquivo original, inclusive de outra pasta. "
                "Primeiro conferimos todas as linhas e o SHA-256. "
                "O CSV fica intacto e recebe cópia verificada."
            ), text_color=TEXT_SECONDARY, wraplength=875, justify="left",
        ).pack(anchor="w", padx=12)
        ctk.CTkButton(
            csv, text="Escolher CSV existente", fg_color=BTC_ORANGE,
            text_color=BG_SURFACE, command=self._escolher_csv,
        ).pack(anchor="w", padx=12, pady=(12, 6))
        self._resumo_csv = ctk.CTkLabel(
            csv, text="Nenhum arquivo escolhido.", text_color=TEXT_SECONDARY,
            wraplength=860, justify="left",
        )
        self._resumo_csv.pack(anchor="w", padx=12, pady=4)
        self._btn_importar = ctk.CTkButton(
            csv, text="Confirmar importação verificada",
            state="disabled", command=self._importar_csv,
        )
        self._btn_importar.pack(anchor="w", padx=12, pady=(8, 14))

        wallet = self._box("2 · JÁ POSSUI CRIPTO EM WALLET OU CORRETORA?")
        ctk.CTkLabel(
            wallet, text=(
                "Registre o saldo que já possui, não cada compra antiga. "
                "Custo total em USDT é opcional; sem ele, preço médio e lucro "
                "ficam não apurados. Nunca informe seed ou chave privada."
            ), text_color=TEXT_SECONDARY, wraplength=875, justify="left",
        ).pack(anchor="w", padx=12)
        fields = ctk.CTkFrame(wallet, fg_color="transparent")
        fields.pack(fill="x", padx=12, pady=(8, 0))
        spec = [
            ("Ativo", "BTC"), ("Quantidade", "0.025"),
            ("Custódia", "Minha cold wallet"), ("Data do saldo", "AAAA-MM-DD"),
            ("Custo total USDT (opcional)", "Deixe vazio se desconhecido"),
        ]
        self._campos = {}
        for i, (label, placeholder) in enumerate(spec):
            ctk.CTkLabel(
                fields, text=label, text_color=TEXT_SECONDARY,
            ).grid(row=i // 3 * 2, column=i % 3, sticky="w", padx=5)
            entry = ctk.CTkEntry(
                fields, width=215, placeholder_text=placeholder,
                fg_color=BG_INPUT, border_color=BORDER,
                text_color=TEXT_PRIMARY,
            )
            entry.grid(row=i // 3 * 2 + 1, column=i % 3, sticky="w",
                       padx=5, pady=(0, 9))
            self._campos[label] = entry
        self._campos["Data do saldo"].insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._externo_flag = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            wallet, variable=self._externo_flag, text=(
                "Este saldo é EXTERNO e NÃO consta no CSV ou em outros "
                "saldos cadastrados (confirmo a independência)"
            ), text_color=TEXT_PRIMARY, fg_color=BTC_ORANGE,
        ).pack(anchor="w", padx=15, pady=(4, 7))
        self._motivo_correcao = ctk.CTkEntry(
            wallet, width=630, fg_color=BG_INPUT,
            placeholder_text="Motivo de uma correção auditada (mínimo 8 caracteres)",
        )
        self._motivo_correcao.pack(anchor="w", padx=12, pady=(0, 6))
        actions = ctk.CTkFrame(wallet, fg_color="transparent")
        actions.pack(anchor="w", padx=12, pady=(4, 12))
        ctk.CTkButton(
            actions, text="Adicionar saldo existente", fg_color=BTC_ORANGE,
            text_color=BG_SURFACE, command=self._salvar_saldo,
        ).pack(side="left", padx=(0, 9))
        ctk.CTkButton(
            actions, text="Informar custo posteriormente",
            fg_color=BG_INPUT, command=self._informar_custo,
        ).pack(side="left")
        ctk.CTkButton(
            actions, text="Corrigir saldo registrado",
            fg_color=BG_INPUT, command=self._corrigir_saldo,
        ).pack(side="left", padx=(9, 0))
        self._posicoes = ctk.CTkLabel(
            wallet, text="", wraplength=870, justify="left",
            text_color=TEXT_SECONDARY,
        )
        self._posicoes.pack(anchor="w", padx=12, pady=(0, 12))

        novo = self._box("3 · NÃO POSSUI HISTÓRICO NEM SALDOS?")
        ctk.CTkLabel(
            novo, text=(
                "Comece com a carteira vazia e registre apenas operações reais. "
                "Não será incluído saldo ou aporte fictício."
            ), text_color=TEXT_SECONDARY, wraplength=850, justify="left",
        ).pack(anchor="w", padx=12)
        ctk.CTkButton(
            novo, text="Começar com carteira vazia",
            fg_color=BG_INPUT, command=self._on_begin_empty,
        ).pack(anchor="w", padx=12, pady=12)
        mov = self._box("4 · TRANSFERÊNCIAS E VENDAS DE CUSTÓDIA EXTERNA")
        ctk.CTkLabel(
            mov, text=(
                "Somente saldos externos já declarados. Transferir não é comprar. "
                "Venda credita USDT no destino informado; taxas em USDT ou no ativo "
                "são explícitas. Não movimenta nem reescreve o CSV."
            ), text_color=TEXT_SECONDARY, wraplength=870, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 9))
        campos = ctk.CTkFrame(mov, fg_color="transparent")
        campos.pack(fill="x", padx=12)
        self._tipo_movimento = ctk.CTkOptionMenu(
            campos, values=["transferencia", "venda"],
            width=185, fg_color=BG_INPUT, button_color=BTC_ORANGE,
        )
        self._tipo_movimento.grid(row=1, column=0, padx=5, pady=(0, 9))
        ctk.CTkLabel(
            campos, text="Operação", text_color=TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w", padx=5)
        definicoes = [
            ("Ativo movimentado", "BTC"),
            ("Origem (custódia)", "Cold wallet"),
            ("Destino (custódia/USDT)", "Corretora X"),
            ("Quantidade enviada/vendida", "0.025"),
            ("Taxa cobrada no ativo", "0 (se comprovadamente zero)"),
            ("Receita bruta em USDT", "0 para transferência"),
            ("Corretagem em USDT", "0 se documentadamente zero"),
            ("Data do movimento", "AAAA-MM-DD"),
            ("Justificativa/comprovante", "Extrato ou TXID de referência"),
        ]
        self._mov_campos = {}
        for index, (label, placeholder) in enumerate(definicoes):
            pos=index+1
            row=pos//3*2
            col=pos%3
            ctk.CTkLabel(
                campos, text=label, text_color=TEXT_SECONDARY,
            ).grid(row=row, column=col, sticky="w", padx=5)
            inp=ctk.CTkEntry(
                campos, width=220, placeholder_text=placeholder,
                fg_color=BG_INPUT, border_color=BORDER,
            )
            inp.grid(row=row+1,column=col,sticky="w",padx=5,pady=(0,8))
            self._mov_campos[label]=inp
        self._mov_campos["Data do movimento"].insert(
            0,datetime.now().strftime("%Y-%m-%d")
        )
        ctk.CTkButton(
            mov, text="Registrar movimentação verificada",
            command=self._salvar_movimento, fg_color=BTC_ORANGE,
            text_color=BG_SURFACE,
        ).pack(anchor="w", padx=14, pady=(6,12))
        self._movimentos_resumo=ctk.CTkLabel(
            mov,text="Nenhuma movimentação.",text_color=TEXT_SECONDARY,
            wraplength=870,justify="left",
        )
        self._movimentos_resumo.pack(anchor="w",padx=12,pady=(0,12))
        self.atualizar()

    def _box(self, title):
        box = ctk.CTkFrame(
            self, fg_color=BG_CARD, border_color=BORDER,
            border_width=1, corner_radius=8,
        )
        box.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(
            box, text=title, text_color=BTC_ORANGE,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 7))
        return box

    def atualizar(self):
        try:
            diag = self._db._store.diagnostico_integridade()
            iniciais = self._db.carregar_posicoes_iniciais()
            externos = self._db.carregar_posicoes_externas()
            movimentos = self._db.carregar_movimentos_custodia()
            self._movimentos_resumo.configure(text=(
                f"{len(movimentos)} movimentações externas registradas. "
                "Todas preservadas no SQLite; transferências e vendas "
                "não se tornam compras do CSV."
            ))
            self._estado.configure(text=(
                f"SQLite: {diag['operacoes_atuais']} operações; "
                f"{len(iniciais)} saldos iniciais; "
                f"{len(externos)} saldos externos; "
                f"CSV importado: {'sim' if diag['importacao'] else 'não'}; "
                f"integridade: {diag['status']}."
            ))
            self._posicoes.configure(text=(
                "Saldos registrados: "
                + ("  |  ".join(
                    f"{x['Moeda']} {x['Quantidade']} ({x['Custodia']}) "
                    + ("• custo não informado" if x['Custo_Total_USDT'] is None
                       else f"• custo {x['Custo_Total_USDT']} USDT")
                    for x in iniciais
                ) if iniciais else "nenhum")
                + ("  |  EXTERNOS AO CSV: " + "  |  ".join(
                    f"{x['Moeda']} {x['Quantidade']} ({x['Custodia']})"
                    + (" • custo desconhecido" if x["Custo_Total_USDT"] is None
                       else f" • custo {x['Custo_Total_USDT']} USDT")
                    for x in externos
                ) if externos else "")
            ))
        except Exception as exc:
            self._estado.configure(text=f"Erro de integridade: {exc}", text_color=NEON_RED)

    def _escolher_csv(self):
        filename = filedialog.askopenfilename(
            title="Selecione o CSV ORIGINAL da instalação antiga",
            filetypes=[("Arquivo CSV", "*.csv"), ("Todos os arquivos", "*.*")],
        )
        if not filename:
            return
        try:
            self._previa = self._db.prever_csv(filename)
            p = self._previa
            self._resumo_csv.configure(
                text=(f"Arquivo: {p['arquivo']}\n"
                      f"Registros: {p['quantidade']} · Moedas: {', '.join(p['moedas'])}\n"
                      f"Período: {p['primeira_data']} a {p['ultima_data']}\n"
                      f"SHA-256: {p['sha256']}\n"
                      f"Linhas idênticas: {p['duplicatas_identicas']} "
                      "(não serão removidas automaticamente)"),
                text_color=CYAN,
            )
            self._btn_importar.configure(state="normal")
        except Exception as exc:
            self._previa = None
            self._btn_importar.configure(state="disabled")
            messagebox.showerror("CSV não autorizado", str(exc))

    def _importar_csv(self):
        p = self._previa
        if p is None:
            return
        if not messagebox.askyesno(
            "Confirmar histórico original",
            f"Importar {p['quantidade']} registros do CSV para o SQLite?\n\n"
            "O original será preservado. Uma cópia de segurança auditável "
            "será criada antes da importação.\n\n"
            "Não misturaremos outro saldo inicial nesta carteira.",
        ):
            return
        try:
            result = self._db.confirmar_csv(p["arquivo"], p["sha256"])
            self._previa = None
            self._btn_importar.configure(state="disabled")
            self.atualizar()
            self._on_change()
            if result.get("aviso_backup_sqlite"):
                messagebox.showwarning(
                    "Migração concluída com alerta",
                    f"{result['importadas']} operações foram gravadas. "
                    + result["aviso_backup_sqlite"],
                )
            else:
                messagebox.showinfo(
                    "Histórico preservado",
                    f"{result['importadas']} operações importadas com CSV original "
                    "e snapshot SQLite verificados; nenhuma linha foi removida.",
                )
        except Exception as exc:
            messagebox.showerror("Importação não concluída", str(exc))

    def _salvar_saldo(self):
        vals = {k: e.get().strip() for k, e in self._campos.items()}
        externa = self._externo_flag.get()
        if not messagebox.askyesno(
            "Confirmar posição externa" if externa else "Confirmar saldo inicial",
            f"Registrar {vals['Quantidade']} {vals['Ativo']} na "
            f"custódia '{vals['Custódia']}'?\n"
            + ("Declaro que NÃO consta no CSV ou em outro saldo. "
               "Não duplica o patrimônio já registrado."
               if externa else "Saldo de primeiro acesso, sem compras fictícias."),
        ):
            return
        try:
            registrar = (self._db.registrar_posicao_externa if externa
                        else self._db.registrar_posicao_inicial)
            parametros = {
                "moeda":vals["Ativo"],"quantidade":vals["Quantidade"],
                "custodia":vals["Custódia"],"data_posicao":vals["Data do saldo"],
                "custo_total_usdt":vals["Custo total USDT (opcional)"] or None,
            }
            if externa:
                parametros["confirmacao_independente"] = True
            resultado = registrar(**parametros)
            if resultado.get("aviso_backup_sqlite"):
                messagebox.showwarning(
                    "Saldo salvo, atenção ao backup",
                    resultado["aviso_backup_sqlite"],
                )
            self.atualizar()
            self._on_change()
        except Exception as exc:
            messagebox.showerror("Saldo não registrado", str(exc))

    def _salvar_movimento(self):
        vals={k:e.get().strip() for k,e in self._mov_campos.items()}
        tipo=self._tipo_movimento.get()
        if not messagebox.askyesno(
            "Movimentação externa documentada",
            f"Registrar {tipo} de {vals['Quantidade enviada/vendida']} "
            f"{vals['Ativo movimentado']} em "
            f"{vals['Origem (custódia)']}?\\n"
            "Origem e destino serão conferidos pelo saldo externo. "
            "O CSV original ficará intacto.",
        ):
            return
        try:
            r=self._db.registrar_movimento_custodia(
                tipo=tipo, moeda=vals["Ativo movimentado"],
                origem=vals["Origem (custódia)"],
                destino=vals["Destino (custódia/USDT)"],
                quantidade=vals["Quantidade enviada/vendida"],
                data_utc=vals["Data do movimento"],
                taxa_ativo=vals["Taxa cobrada no ativo"],
                receita_usdt=vals["Receita bruta em USDT"] if tipo=="venda" else "0",
                taxa_usdt=vals["Corretagem em USDT"] if tipo=="venda" else "0",
                observacao=vals["Justificativa/comprovante"],
            )
            if r.get("aviso_backup_sqlite"):
                messagebox.showwarning("Movimentação registrada",
                                       r["aviso_backup_sqlite"])
            self.atualizar()
            self._on_change()
        except Exception as exc:
            messagebox.showerror("Movimentação recusada",str(exc))

    def _corrigir_saldo(self):
        vals = {k: e.get().strip() for k,e in self._campos.items()}
        origem = "externa" if self._externo_flag.get() else "inicial"
        motivo = self._motivo_correcao.get().strip()
        if len(motivo) < 8:
            messagebox.showwarning("Motivo obrigatório",
                                   "Explique o ajuste em pelo menos 8 caracteres.")
            return
        if not messagebox.askyesno(
            "Correção registrada em auditoria",
            "Confirmar alteração de quantidade ou custo? "
            "O valor anterior e o motivo ficarão preservados em SQLite. "
            "Será feito backup ANTES da alteração.",
        ):
            return
        try:
            resultado = self._db.corrigir_posicao(
                origem=origem, moeda=vals["Ativo"],
                custodia=vals["Custódia"],
                quantidade=vals["Quantidade"],
                custo_total_usdt=vals["Custo total USDT (opcional)"] or None,
                motivo=motivo,
            )
            if resultado.get("aviso_backup_sqlite"):
                messagebox.showwarning("Alteração concluída",
                                       resultado["aviso_backup_sqlite"])
            self.atualizar()
            self._on_change()
        except Exception as exc:
            messagebox.showerror("Correção cancelada", str(exc))

    def _informar_custo(self):
        vals = {k:e.get().strip() for k,e in self._campos.items()}
        origem = "externa" if self._externo_flag.get() else "inicial"
        saldos = (self._db.carregar_posicoes_externas() if origem=="externa"
                  else self._db.carregar_posicoes_iniciais())
        alvo = next((s for s in saldos if s["Moeda"]==vals["Ativo"].upper()
                     and s["Custodia"]==vals["Custódia"]),None)
        if alvo is None:
            messagebox.showwarning("Saldo inexistente",
                                   "Selecione o mesmo ativo e custódia já cadastrados.")
            return
        if not vals["Custo total USDT (opcional)"]:
            messagebox.showwarning("Custo documentado",
                                   "Informe o custo TOTAL documentado em USDT.")
            return
        self._campos["Quantidade"].delete(0,"end")
        self._campos["Quantidade"].insert(0,str(alvo["Quantidade"]))
        if not self._motivo_correcao.get().strip():
            self._motivo_correcao.insert(0,"Custo histórico documentado pelo usuário")
        self._corrigir_saldo()
