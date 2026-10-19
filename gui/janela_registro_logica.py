import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation, getcontext
from tkinter import messagebox
from typing import Any, Callable, List, Optional

from backend.tipo_operacao import TipoOperacao
from gui.janela_registro_ui import JanelaRegistroUI

getcontext().prec = 18
logger = logging.getLogger(__name__)


class JanelaRegistro(JanelaRegistroUI):

    def __init__(
        self,
        parent: Any,
        data_manager: Any,
        price_manager: Any,
        analysis_engine: Any,
        moedas_suportadas: List[str],
        on_change: Optional[Callable] = None,
    ):
        self._data_manager = data_manager
        self._price_manager = price_manager
        self._engine = analysis_engine
        self._on_change = on_change or (lambda: None)
        self._qtd_max_travada: Optional[Decimal] = None

        super().__init__(
            parent=parent,
            moedas_suportadas=moedas_suportadas,
            on_moeda_changed=self._ao_mudar_moeda,
            on_tipo_changed=self._ao_mudar_tipo,
            on_calcular=self._calcular_quantidade,
            on_salvar=self._salvar,
        )

    def _eh_stablecoin(self, moeda: str) -> bool:
        return moeda in ("USDT", "USDC")

    def atualizar(self) -> None:
        self._atualizar_saldo_disponivel()

    def _ao_mudar_moeda(self, event=None) -> None:
        self._qtd_max_travada = None
        self.set_combo_tipo_value("")
        self.set_combo_tipo_state("disabled")
        self.set_entry_preco("", state_after="disabled")
        self.set_entry_valor("", )
        self.set_entry_valor_state("disabled")
        self.set_label_quantidade("", "Info.TLabel")
        self.set_label_saldo("")
        self.set_label_ajuda("")
        self.set_label_erro_saldo("")
        self.set_btn_salvar_state("disabled")
        self.set_taxa_corretagem_state("disabled")
        self.set_taxa_corretagem_state("normal")
        self._entry_taxa_corretagem.delete(0, "end")
        self.set_taxa_corretagem_state("disabled")
        self.set_label_preco_titulo("Preço Unitário:")
        self.set_label_valor_titulo("VALOR (USDT)")

        moeda = self.get_moeda()
        if not moeda:
            return

        if self._eh_stablecoin(moeda):
            self.set_combo_tipo_values(TipoOperacao.labels_usdt())
            self.set_label_valor_titulo(f"UNIDADES ({moeda})")
            self.set_label_preco_titulo(f"{moeda}/BRL (informado):")
            if moeda == "USDT":
                fx = (self._price_manager.taxa_brl_para_avaliacao()
                      if hasattr(self._price_manager, "taxa_brl_para_avaliacao")
                      else self._price_manager.preco_brl)
                self.set_entry_preco(f"{fx:.4f}" if fx else "")
                self.set_label_preco_atual(
                    f"USDT/BRL R${fx:.4f}" if fx else "Informe câmbio USDT/BRL real"
                )
            else:
                # Nunca preencher USDC/BRL a partir da paridade teórica
                # USDT/USD. Sem cotação documentada, operador informa a sua.
                self.set_entry_preco("")
                self.set_label_preco_atual("USDC/BRL manual")
            self.set_label_ajuda(
                f"Entrada/saída de {moeda} na própria unidade. "
                "Não converte automaticamente USDC em USDT."
            )
        else:
            self.set_combo_tipo_values(TipoOperacao.labels_crypto())
            self.set_taxa_corretagem_state("normal")
            preco = self._price_manager.get_preco(moeda)
            self.set_entry_preco_state("normal")
            if preco:
                self.set_label_preco_atual(f"Atual: ${preco:.4f}")
                self.set_entry_preco(f"{preco:.6f}")
            else:
                self.set_label_preco_atual("Preço indisponível")

    def _ao_mudar_tipo(self, event=None) -> None:
        self._qtd_max_travada = None
        self.set_entry_valor("")
        self.set_label_quantidade("", "Info.TLabel")
        self.set_label_erro_saldo("")
        self.set_btn_salvar_state("disabled")

        moeda = self.get_moeda()
        if not self._eh_stablecoin(moeda):
            self.set_label_ajuda("")

        self._atualizar_saldo_disponivel()
        self._verificar_venda_total()

    def _verificar_venda_total(self) -> None:
        tipo_label = self.get_tipo_label()
        if not tipo_label:
            return
        tipo = TipoOperacao.from_label(tipo_label)
        moeda = self.get_moeda()

        if tipo is not TipoOperacao.VENDA_TOTAL or not moeda or self._eh_stablecoin(moeda):
            self._calcular_quantidade()
            return

        try:
            operacoes = self._data_manager.carregar_operacoes()
            portfolio = self._engine.calcular_portfolio(operacoes, self._price_manager.precos_cache, saldos_iniciais=self._data_manager.carregar_posicoes_iniciais(),
                    saldos_externos=self._data_manager.carregar_posicoes_externas(),
                    movimentos_custodia=self._data_manager.carregar_movimentos_custodia())
            saldo_exato = Decimal(str(portfolio.get(moeda, {}).get("quantidade_final", 0)))

            if saldo_exato <= 0:
                messagebox.showwarning("Aviso", f"Você não possui saldo de {moeda} para vender.")
                self.set_combo_tipo_value(TipoOperacao.VENDA.label)
                self._calcular_quantidade()
                return

            self._qtd_max_travada = saldo_exato

            preco_str = self.get_preco_str()
            if preco_str:
                try:
                    preco = Decimal(preco_str)
                    valor_sugerido = saldo_exato * preco
                    self.set_entry_valor(f"{valor_sugerido:.4f}")
                except InvalidOperation:
                    pass

            self._calcular_quantidade()

        except Exception as e:
            logger.error(f"Erro ao processar venda total: {e}")

    def _atualizar_saldo_disponivel(self) -> None:
        moeda = self.get_moeda()
        tipo_label = self.get_tipo_label()
        if not tipo_label:
            self.set_label_saldo("")
            return
        tipo = TipoOperacao.from_label(tipo_label)

        if tipo in (TipoOperacao.VENDA, TipoOperacao.VENDA_TOTAL) and moeda and not self._eh_stablecoin(moeda):
            try:
                operacoes = self._data_manager.carregar_operacoes()
                portfolio = self._engine.calcular_portfolio(operacoes, self._price_manager.precos_cache, saldos_iniciais=self._data_manager.carregar_posicoes_iniciais(),
                    saldos_externos=self._data_manager.carregar_posicoes_externas(),
                    movimentos_custodia=self._data_manager.carregar_movimentos_custodia())
                saldo = portfolio.get(moeda, {}).get("quantidade_final", 0)
                self.set_label_saldo(f"Saldo: {saldo:.8f} {moeda}")
            except Exception:
                self.set_label_saldo("")
        else:
            self.set_label_saldo("")

    def _calcular_quantidade(self, event=None) -> None:
        try:
            moeda = self.get_moeda()
            tipo_label = self.get_tipo_label()
            if not tipo_label:
                self.set_label_quantidade("", "Info.TLabel")
                self.set_btn_salvar_state("disabled")
                return

            tipo = TipoOperacao.from_label(tipo_label)
            valor_str = self.get_valor_str()
            preco_str = self.get_preco_str()

            if tipo is TipoOperacao.VENDA_TOTAL and self._qtd_max_travada is not None:
                self.set_label_quantidade(
                    f"🔒 {self._qtd_max_travada:.8f} {moeda} serão zerados exatamente.",
                    "Travado.TLabel",
                )
                self.set_label_ajuda("💡 Digite no campo Valor (USDT) o que a corretora te pagou após a taxa.")
                self._verificar_estado_botao()
                return

            if not self._eh_stablecoin(moeda):
                self.set_label_ajuda("")

            if not valor_str or not preco_str:
                self.set_label_quantidade("", "Info.TLabel")
                self.set_btn_salvar_state("disabled")
                return

            valor = Decimal(valor_str)
            preco = Decimal(preco_str)

            if valor > 0 and preco > 0:
                if self._eh_stablecoin(moeda):
                    qtd = valor
                    texto = f"= {float(qtd):.2f} {moeda}  (cotação informada R${float(preco):.4f}/{moeda})"
                else:
                    qtd = valor / preco
                    texto = f"≈ {float(qtd):.8f} unidades"
                self.set_label_quantidade(texto, "Info.TLabel")
                self._verificar_saldo_inline(tipo, moeda, valor)
            else:
                self.set_label_quantidade("", "Info.TLabel")
                self.set_btn_salvar_state("disabled")

        except (InvalidOperation, ZeroDivisionError):
            self.set_label_quantidade("", "Info.TLabel")
            self.set_btn_salvar_state("disabled")

    def _verificar_saldo_inline(self, tipo: TipoOperacao, moeda: str, valor: Decimal) -> None:
        if tipo is TipoOperacao.VENDA and moeda == "USDC":
            try:
                from backend.stablecoin_ledger import saldos_stablecoins
                registro = self._data_manager.carregar_operacoes_precisas()
                saldo = saldos_stablecoins(registro)["saldos"]["USDC"]
                if valor > saldo:
                    self.set_label_erro_saldo(
                        f"⚠ Saque maior que o saldo: {saldo} USDC disponíveis."
                    )
                    self.set_btn_salvar_state("disabled")
                    return
            except Exception as exc:
                self.set_label_erro_saldo(f"⚠ Não foi possível verificar USDC: {exc}")
                self.set_btn_salvar_state("disabled")
                return
            self.set_label_erro_saldo("")
            self._verificar_estado_botao()
            return
        if tipo is not TipoOperacao.VENDA or self._eh_stablecoin(moeda):
            self.set_label_erro_saldo("")
            self._verificar_estado_botao()
            return
        try:
            operacoes = self._data_manager.carregar_operacoes()
            portfolio = self._engine.calcular_portfolio(operacoes, self._price_manager.precos_cache, saldos_iniciais=self._data_manager.carregar_posicoes_iniciais(),
                    saldos_externos=self._data_manager.carregar_posicoes_externas(),
                    movimentos_custodia=self._data_manager.carregar_movimentos_custodia())
            saldo = Decimal(str(portfolio.get(moeda, {}).get("quantidade_final", 0)))
            preco_str = self.get_preco_str()
            preco = Decimal(preco_str) if preco_str else Decimal("0")
            if preco > 0:
                qtd_solicitada = valor / preco
                if qtd_solicitada > saldo:
                    falta = qtd_solicitada - saldo
                    self.set_label_erro_saldo(f"⚠ Saldo insuficiente! Faltam {float(falta):.8f} {moeda}")
                    self.set_btn_salvar_state("disabled")
                    return
            self.set_label_erro_saldo("")
            self._verificar_estado_botao()
        except Exception:
            self.set_label_erro_saldo("")
            self._verificar_estado_botao()

    def _verificar_estado_botao(self) -> None:
        try:
            valor = Decimal(self.get_valor_str())
            preco = Decimal(self.get_preco_str())
            state = "normal" if valor > 0 and preco > 0 else "disabled"
            self.set_btn_salvar_state(state)
        except InvalidOperation:
            self.set_btn_salvar_state("disabled")

    def _validar(self) -> list:
        erros = []
        if not self.get_moeda():
            erros.append("Selecione uma moeda")
        if not self.get_tipo_label():
            erros.append("Selecione o tipo de operação")
        try:
            if Decimal(self.get_valor_str()) <= 0:
                erros.append("Valor deve ser maior que zero")
        except InvalidOperation:
            erros.append("Valor deve ser um número válido")
        try:
            if Decimal(self.get_preco_str()) <= 0:
                erros.append("Preço deve ser maior que zero")
        except InvalidOperation:
            erros.append("Preço deve ser um número válido")
        taxa_texto = self.get_taxa_corretagem_str()
        if taxa_texto:
            try:
                taxa = Decimal(taxa_texto)
                if not taxa.is_finite() or taxa < 0:
                    erros.append("Taxa de corretagem USDT deve ser não negativa e finita.")
            except InvalidOperation:
                erros.append("Taxa de corretagem USDT inválida.")
            if self._eh_stablecoin(self.get_moeda()):
                erros.append("Taxa de corretagem somente para compra/venda de criptoativos.")
        return erros

    def _salvar(self) -> None:
        erros = self._validar()
        if erros:
            messagebox.showerror("Erro de Validação", "\n".join(erros))
            return

        try:
            moeda = self.get_moeda().strip().upper()
            tipo = TipoOperacao.from_label(self.get_tipo_label())
            tipo_csv = tipo.csv_value
            valor = Decimal(self.get_valor_str())
            preco = Decimal(self.get_preco_str())
            taxa_brl = (
                preco if self._eh_stablecoin(moeda)
                else (
                    self._price_manager.taxa_brl_para_avaliacao()
                    if hasattr(self._price_manager, "taxa_brl_para_avaliacao")
                    else self._price_manager.preco_brl
                ) or Decimal("0")
            )

            if self._eh_stablecoin(moeda):
                quantidade = valor
            elif tipo is TipoOperacao.VENDA_TOTAL and self._qtd_max_travada is not None:
                quantidade = self._qtd_max_travada
            else:
                quantidade = valor / preco

            data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Strings decimais até o SQLite: evita perda de precisão por float.
            operacao = [
                data_hora, moeda, tipo_csv,
                str(valor), str(preco), str(quantidade), str(taxa_brl),
                self.get_taxa_corretagem_str() or None,
            ]

            if not self._data_manager.salvar_operacao(operacao):
                detalhe = getattr(self._data_manager, "ultimo_erro", None)
                messagebox.showerror(
                    "Operação não registrada",
                    detalhe or "Os dados não passaram pela validação financeira.",
                )
                return

            if tipo is TipoOperacao.VENDA_TOTAL:
                msg = f"Venda Total executada! Saldo de {moeda} zerado com sucesso."
            elif self._eh_stablecoin(moeda):
                msg = f"{'Depósito' if tipo_csv == 'compra' else 'Saque'} de {quantidade:,.2f} {moeda} registrado!"
            else:
                msg = f"{tipo_csv.title()} de {moeda} registrada com sucesso!"

            messagebox.showinfo("Sucesso", msg)
            aviso=getattr(self._data_manager,"ultimo_aviso_backup",None)
            if aviso:messagebox.showwarning("Gravação confirmada — backup pendente",aviso,parent=self)
            self._limpar()
            self._on_change()

        except Exception as e:
            logger.exception("Erro ao salvar operação")
            messagebox.showerror("Erro", f"Erro inesperado: {e}")

    def _limpar(self) -> None:
        self._qtd_max_travada = None
        self.limpar_campos()

    def atualizar_lista_moedas(self, novas_moedas: list) -> None:
        moeda_atual = super().atualizar_lista_moedas(novas_moedas)
        if moeda_atual and moeda_atual not in novas_moedas:
            self._limpar()