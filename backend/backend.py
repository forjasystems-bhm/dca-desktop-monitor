from pathlib import Path
import csv
import os
from typing import Dict, List
from collections import defaultdict
import logging
import math
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    # pyrefly: ignore [missing-import]
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    logger.warning("A biblioteca 'ccxt' não está instalizada. Os preços das moedas não serão atualizados.")
    print("Para instalar, execute: pip install ccxt")

class DataManager:
    """Interface de compatibilidade para as telas; persistência nova em SQLite."""

    def __init__(self, arquivo_csv: str = "meu_diario_operacoes.csv",
                 *, data_dir=None, legacy_csv=None,
                 auto_import_legacy: bool = True):
        from backend.storage_sqlite import ArmazemSQLite, diretorio_dados_padrao

        raiz_projeto = Path(__file__).resolve().parent.parent
        self.arquivo_csv = (
            Path(legacy_csv) if legacy_csv is not None
            else raiz_projeto / "db" / arquivo_csv
        )
        self.headers = ['Data', 'Moeda', 'Operacao', 'Valor_USDT', 'Preco',
                        'Quantidade', 'Taxa_BRL']
        self._store = ArmazemSQLite(
            Path(data_dir) if data_dir is not None else diretorio_dados_padrao(),
            self.arquivo_csv, auto_importar_legado=auto_import_legacy,
        )
        self.arquivo_db = self._store.arquivo_db
        self.ultimo_erro = None

    def criar_arquivo_se_necessario(self):
        # Compatibilidade: banco já inicializado no construtor.
        return None

    def carregar_operacoes(self) -> List[Dict]:
        # Falhas de integridade não podem ser mascaradas como carteira vazia.
        return self._store.listar()

    def carregar_operacoes_precisas(self) -> List[Dict]:
        """API de cálculo histórico exato; não converte números a float."""
        return self._store.listar_preciso()

    def importar_csv_legado(self, caminho: str) -> int:
        return self._store.importar_csv(Path(caminho))

    def exportar_csv(self, destino: str) -> None:
        self._store.exportar_csv(Path(destino))

    def prever_csv(self, caminho: str) -> dict:
        return self._store.prever_importacao_csv(Path(caminho))

    def confirmar_csv(self, caminho: str, sha256: str) -> dict:
        return self._store.importar_csv_conferido(Path(caminho), sha256)

    def carregar_posicoes_iniciais(self) -> List[Dict]:
        return self._store.listar_posicoes_iniciais()

    def registrar_posicao_inicial(self, **campos) -> dict:
        return self._store.registrar_posicao_inicial(**campos)

    def carregar_posicoes_externas(self) -> List[Dict]:
        return self._store.listar_posicoes_externas()

    def registrar_posicao_externa(self, **campos) -> dict:
        return self._store.registrar_posicao_externa(**campos)

    def registrar_movimento_custodia(self, **campos) -> dict:
        return self._store.registrar_movimento_custodia(**campos)

    def carregar_movimentos_custodia(self) -> List[Dict]:
        return self._store.listar_movimentos_custodia()

    def corrigir_posicao(self, **campos) -> dict:
        return self._store.corrigir_posicao(**campos)

    def carregar_auditoria_posicoes(self) -> List[Dict]:
        return self._store.listar_auditoria_posicoes()

    def _executar_mutacao(self, descricao: str, operacao):
        from backend.operation_integrity import ErroIntegridadeFinanceira
        from backend.storage_sqlite import ErroArmazenamento

        self.ultimo_erro = None
        try:
            sucesso = operacao()
            if not sucesso:
                self.ultimo_erro = "Operação não encontrada; recarregue o histórico."
            return sucesso
        except (ErroIntegridadeFinanceira, ErroArmazenamento) as exc:
            self.ultimo_erro = str(exc)
            logger.warning("%s rejeitada: %s", descricao, exc)
            return False
        except Exception:
            self.ultimo_erro = (
                "Falha inesperada de gravação. Os dados anteriores foram preservados."
            )
            logger.exception("Falha ao %s; transação revertida", descricao)
            return False

    def excluir_operacao(self, indice: int) -> bool:
        return self._executar_mutacao(
            "excluir", lambda: self._store.excluir(indice)
        )

    def atualizar_operacao(self, indice: int, nova_operacao: Dict) -> bool:
        return self._executar_mutacao(
            "alterar", lambda: self._store.substituir(indice, nova_operacao)
        )

    def salvar_operacao(self, operacao: List) -> bool:
        return self._executar_mutacao(
            "salvar", lambda: self._store.inserir(operacao)
        )

class PriceManager:
    """Cache de cotações com validade e estado explícitos.

    Falhas de rede não tornam o último preço válido para avaliação de mercado.
    A leitura histórica é independente deste cache.
    """
    VALIDADE_SEGUNDOS = 180

    def __init__(self, exchange_name: str = "binance"):
        self.exchange = None
        self.precos_cache = {}
        self.cotacoes_atualizadas_em = {}
        self.falhas_cotacao = set()
        self.ultima_atualizacao = None
        self.preco_brl = 0.0
        self._brl_atualizado_em = None
        self._brl_falhou = True
        self.setup_exchange(exchange_name)

    def setup_exchange(self, exchange_name: str):
        if not CCXT_AVAILABLE:
            return
        try:
            if exchange_name.lower() == "binance":
                self.exchange = ccxt.binance({
                    "rateLimit": 1200,
                    "enableRateLimit": True,
                    "timeout": 10000,
                })
            logger.info("Exchange %s configurada", exchange_name)
        except Exception:
            logger.exception("Falha ao configurar exchange %s", exchange_name)

    @staticmethod
    def _preco_positivo(valor):
        try:
            decimal = Decimal(str(valor))
            if not decimal.is_finite() or decimal <= 0:
                return None
            preco = float(decimal)
            return preco if math.isfinite(preco) and preco > 0 else None
        except (ValueError, InvalidOperation, TypeError, OverflowError):
            return None

    @staticmethod
    def _dentro_do_prazo(instante, agora, max_age):
        if instante is None or instante.tzinfo is None:
            return False
        idade = (agora - instante).total_seconds()
        return 0 <= idade <= max_age

    def invalidar_cotacoes(self, moedas: List[str]) -> None:
        """A rede falhou: cache permanece para diagnóstico, não para avaliação."""
        self.falhas_cotacao.update(
            str(m).upper() for m in moedas if str(m).upper() != "USDT"
        )
        self._brl_falhou = True

    def atualizar_precos(self, moedas: List[str]) -> bool:
        if not self.exchange:
            self.invalidar_cotacoes(moedas)
            return False

        sucesso = True
        for moeda in moedas:
            moeda = moeda.upper()
            if moeda == "USDT":
                self.precos_cache["USDT"] = 1.0
                continue
            try:
                ticker = self.exchange.fetch_ticker(f"{moeda}/USDT")
                preco = self._preco_positivo(ticker.get("last"))
                if preco is None:
                    raise ValueError("ticker sem cotação positiva/finita")
                self.precos_cache[moeda] = preco
                self.cotacoes_atualizadas_em[moeda] = datetime.now(timezone.utc)
                self.falhas_cotacao.discard(moeda)
            except Exception as exc:
                self.falhas_cotacao.add(moeda)
                sucesso = False
                logger.warning("Cotação %s indisponível (cache não validado): %s", moeda, exc)

        try:
            ticker_brl = self.exchange.fetch_ticker("USDT/BRL")
            preco_brl = self._preco_positivo(ticker_brl.get("last"))
            if preco_brl is None:
                raise ValueError("ticker USDT/BRL sem cotação positiva/finita")
            self.preco_brl = preco_brl
            self._brl_atualizado_em = datetime.now(timezone.utc)
            self._brl_falhou = False
        except Exception as exc:
            self._brl_falhou = True
            sucesso = False
            logger.warning("USDT/BRL indisponível (cache não validado): %s", exc)

        if sucesso:
            self.ultima_atualizacao = datetime.now(timezone.utc)
        return sucesso

    def precos_para_avaliacao(self, *, agora=None, max_age=None):
        """Entrega apenas cotações atuais comprovadas, jamais cache stale."""
        agora = agora or datetime.now(timezone.utc)
        prazo = self.VALIDADE_SEGUNDOS if max_age is None else max_age
        validos = {"USDT": 1.0}
        for moeda, valor in self.precos_cache.items():
            if moeda == "USDT" or moeda in self.falhas_cotacao:
                continue
            if (self._preco_positivo(valor) is not None
                and self._dentro_do_prazo(
                    self.cotacoes_atualizadas_em.get(moeda), agora, prazo
                )):
                validos[moeda] = float(valor)
        return validos

    def taxa_brl_para_avaliacao(self, *, agora=None, max_age=None):
        if self._brl_falhou:
            return None
        agora = agora or datetime.now(timezone.utc)
        prazo = self.VALIDADE_SEGUNDOS if max_age is None else max_age
        if not self._dentro_do_prazo(self._brl_atualizado_em, agora, prazo):
            return None
        return self._preco_positivo(self.preco_brl)

    def get_preco(self, moeda: str) -> float | None:
        return self.precos_para_avaliacao().get(moeda.upper())

    def validar_moeda(self, simbolo: str) -> bool:
        if not CCXT_AVAILABLE or not self.exchange:
            return True
        try:
            self.exchange.fetch_ticker(f"{simbolo.upper()}/USDT")
            return True
        except Exception:
            return False

class AnalysisEngine:
    @staticmethod
    def _preco_disponivel(valor):
        """Rejeita ausente, zero, preço negativo e não finito."""
        try:
            dec = Decimal(str(valor))
            if not dec.is_finite() or dec <= 0:
                return None
            preco = float(dec)
            return preco if math.isfinite(preco) and preco > 0 else None
        except (ValueError, InvalidOperation, TypeError, OverflowError):
            return None

    @staticmethod
    def calcular_portfolio(operacoes: List[Dict], precos_atuais: Dict[str, float],
                          saldos_iniciais: List[Dict] | None = None,
                          saldos_externos: List[Dict] | None = None,
                          movimentos_custodia: List[Dict] | None = None) -> Dict:
        saldos_iniciais = saldos_iniciais or []
        saldos_externos = saldos_externos or []
        movimentos_custodia = movimentos_custodia or []
        if not operacoes and not saldos_iniciais and not saldos_externos:
            return {}
        from backend.custody_ledger import apurar_custodia
        custodia = apurar_custodia(saldos_externos, movimentos_custodia)
        externos_apurados = custodia["saldos"]
        saldo_caixa = AnalysisEngine.calcular_saldo_usdt(
            operacoes, saldos_iniciais=saldos_iniciais,
        )["saldo_atual"] + float(sum((
            Decimal(str(r["Quantidade"])) for r in externos_apurados
            if str(r["Moeda"]).upper() == "USDT"
        ), Decimal("0")))
        por_moeda = defaultdict(list)
        abertura = defaultdict(lambda: {"quantidade": Decimal("0"), "custo": Decimal("0"),
                                       "incompleto": False})
        for initial in saldos_iniciais:
            moeda = str(initial["Moeda"]).upper()
            if moeda in ("USDT", "USDC"):
                continue
            v = abertura[moeda]
            v["quantidade"] += Decimal(str(initial["Quantidade"]))
            custo = initial.get("Custo_Total_USDT")
            if custo is None or str(custo).strip() == "":
                v["incompleto"] = True
            else:
                v["custo"] += Decimal(str(custo))
        for op in sorted(operacoes, key=lambda x: x["Data"]):
            if op["Moeda"] not in ("USDT", "USDC"):
                por_moeda[op["Moeda"]].append(op)
        from backend.stablecoin_ledger import saldos_stablecoins
        stable = saldos_stablecoins(operacoes)
        saldo_usdc = stable["saldos"]["USDC"] + sum((
            Decimal(str(x["Quantidade"])) for x in saldos_iniciais
            if str(x["Moeda"]).upper() == "USDC"
        ), Decimal("0")) + sum((
            Decimal(str(x["Quantidade"])) for x in externos_apurados
            if str(x["Moeda"]).upper() == "USDC"
        ), Decimal("0"))
        resultado = {}
        totais = {
            "investido_liquido": 0.0,
            "realizado": 0.0,
            "nao_realizado": 0.0,
            "valor_atual": float(saldo_caixa),
            "compras_historicas_usdt": 0.0,
            "vendas_historicas_usdt": 0.0,
            "cotacoes_pendentes": [],
            "avaliacao_completa": True,
            "caixa_usdt": float(saldo_caixa),
            "caixa_usdc": float(saldo_usdc),
            "base_de_custo_incompleta": saldo_usdc > 0 or any(
                v["incompleto"] for v in abertura.values()
            ) or any(x.get("Custo_Total_USDT") is None
                     for x in externos_apurados if x["Moeda"] not in ("USDT","USDC"))
              or not custodia["resultado_completo"],
            "saldos_externos_declarados": len(saldos_externos),
            "movimentacoes_custodia": custodia["movimentacoes"],
            "resultado_custodia_usdt": (
                float(custodia["lucro_vendas_externas_usdt"]
                      - custodia["custo_taxas_transferencias_usdt"])
                if custodia["lucro_vendas_externas_usdt"] is not None else None
            ),
            "custo_taxas_transferencias_usdt": (
                float(custodia["custo_taxas_transferencias_usdt"])
                if custodia["custo_taxas_transferencias_usdt"] is not None else None
            ),
        }
        for moeda in sorted(set(por_moeda) | set(abertura)):
            ops = por_moeda.get(moeda, [])
            preco = AnalysisEngine._preco_disponivel(precos_atuais.get(moeda))
            inicial = abertura.get(moeda, {})
            analise = AnalysisEngine._analisar_moeda(
                ops, preco, quantidade_inicial=inicial.get("quantidade", Decimal("0")),
                custo_inicial=inicial.get("custo", Decimal("0")),
                custo_desconhecido=inicial.get("incompleto", False),
            )
            resultado[moeda] = analise
            if analise["custo_posicao_final"] is not None:
                totais["investido_liquido"] += analise["custo_posicao_final"]
            if analise["lucro_realizado"] is not None:
                totais["realizado"] += analise["lucro_realizado"]
            totais["compras_historicas_usdt"] += analise["total_comprado_usdt"]
            totais["vendas_historicas_usdt"] += analise["total_vendido_usdt"]
            if analise["valor_atual_posicao"] is None:
                totais["cotacoes_pendentes"].append(moeda)
            else:
                totais["valor_atual"] += analise["valor_atual_posicao"]
                if analise["lucro_nao_realizado"] is not None:
                    totais["nao_realizado"] += analise["lucro_nao_realizado"]
        # Reconcile additional custody AFTER legacy trades. Do not alter
        # realized historical P/L or invent a buy or a USDT funding entry.
        externals = defaultdict(lambda: {"q": Decimal("0"), "cost": Decimal("0"), "unknown": False})
        for lot in externos_apurados:
            coin = str(lot["Moeda"]).upper()
            if coin in ("USDT","USDC"):
                continue
            t = externals[coin]
            t["q"] += Decimal(str(lot["Quantidade"]))
            cost = lot.get("Custo_Total_USDT")
            if cost is None or str(cost).strip() == "":
                t["unknown"] = True
            else:
                t["cost"] += Decimal(str(cost))
        for coin, ext in externals.items():
            old = resultado.get(coin)
            if old is None:
                old = AnalysisEngine._analisar_moeda([], AnalysisEngine._preco_disponivel(precos_atuais.get(coin)))
                resultado[coin] = old
            qty = Decimal(str(old["quantidade_final"])) + ext["q"]
            base = old.get("custo_posicao_final")
            unknown = ext["unknown"] or base is None
            cost = None if unknown else Decimal(str(base)) + ext["cost"]
            spot = AnalysisEngine._preco_disponivel(precos_atuais.get(coin))
            old.update({
                "quantidade_final": float(qty),
                "custodia_externa_declarada": float(ext["q"]),
                "base_de_custo_incompleta": bool(unknown),
                "custo_posicao_final": None if unknown else float(cost),
                "pmc_final": None if unknown else float(cost / qty),
                "preco_de_mercado": spot, "cotacao_disponivel": spot is not None,
                "valor_atual_posicao": None if spot is None else float(qty) * spot,
            })
            old["lucro_nao_realizado"] = (
                None if spot is None or unknown
                else old["valor_atual_posicao"] - float(cost)
            )
            old["lucro_total"] = (
                None if old["lucro_nao_realizado"] is None
                or old["lucro_realizado"] is None
                else old["lucro_nao_realizado"] + old["lucro_realizado"]
            )
            if not unknown:
                totais["investido_liquido"] += float(ext["cost"])
                if spot is not None:
                    totais["nao_realizado"] += float(ext["q"]) * spot - float(ext["cost"])
            if spot is None:
                if coin not in totais["cotacoes_pendentes"]:
                    totais["cotacoes_pendentes"].append(coin)
            else:
                totais["valor_atual"] += float(ext["q"]) * spot

        totais["realizado_csv"] = totais["realizado"]
        if custodia["lucro_vendas_externas_usdt"] is not None:
            totais["realizado"] += totais["resultado_custodia_usdt"]
        else:
            totais["realizado"] = None
        if saldo_usdc > 0:
            preco_usdc = AnalysisEngine._preco_disponivel(precos_atuais.get("USDC"))
            valor_usdc = float(saldo_usdc * Decimal(str(preco_usdc))) if preco_usdc is not None else None
            resultado["USDC (Caixa)"] = {
                "quantidade_final": float(saldo_usdc),
                "valor_atual_posicao": valor_usdc,
                "custo_posicao_final": None,
                "operacoes": [],
                "lucro_realizado": None,
                "lucro_nao_realizado": None,
                "lucro_total": None,
                "preco_de_mercado": preco_usdc,
                "pmc_final": None,
                "total_comprado_usdt": 0.0,
                "total_vendido_usdt": 0.0,
                "transferencia_externa": True,
            }
            if valor_usdc is None:
                totais["cotacoes_pendentes"].append("USDC")
            else:
                totais["valor_atual"] += valor_usdc
        if totais["cotacoes_pendentes"]:
            totais["cotacoes_pendentes"].sort()
            totais["avaliacao_completa"] = False
            totais["valor_atual"] = None
            totais["nao_realizado"] = None
        elif totais["base_de_custo_incompleta"]:
            # Valor de mercado é conhecido; rentabilidade não é.
            totais["nao_realizado"] = None
        if saldo_caixa > 0.01:
            resultado["USDT (Caixa)"] = {
                "quantidade_final": float(saldo_caixa),
                "valor_atual_posicao": float(saldo_caixa),
                "custo_posicao_final": 0.0,
                "operacoes": [],
                "lucro_realizado": 0.0,
                "lucro_nao_realizado": 0.0,
                "lucro_total": 0.0,
                "preco_de_mercado": 1.0,
            }
        resultado["totais"] = totais
        return resultado

    @staticmethod
    def calcular_saldo_usdt(operacoes: List[Dict],
                            saldos_iniciais: List[Dict] | None = None) -> Dict:
        saldo_usdt = sum((
            Decimal(str(x["Quantidade"])) for x in (saldos_iniciais or [])
            if str(x["Moeda"]).upper() == "USDT"
        ), Decimal("0"))
        historico_movimentacao = []
        from backend.trading_fees import taxa_da_operacao
        for op in sorted(operacoes, key=lambda x: x['Data']):
            valor_usdt = Decimal(str(op['Valor_USDT']))
            moeda = op['Moeda']
            tipo = op['Operacao']
            taxa = taxa_da_operacao(op)
            if moeda == 'USDT':
                if tipo == 'compra':
                    saldo_usdt += valor_usdt
                    historico_movimentacao.append({
                        'data': op['Data'], 'tipo': 'deposito_usdt', 'valor': float(valor_usdt),
                        'saldo_apos': float(saldo_usdt), 'descricao': f"Depósito de ${float(valor_usdt):,.2f} USDT"
                    })
                elif tipo == 'venda':
                    saldo_usdt -= valor_usdt
                    historico_movimentacao.append({
                        'data': op['Data'], 'tipo': 'saque_usdt', 'valor': float(valor_usdt),
                        'saldo_apos': float(saldo_usdt), 'descricao': f"Saque de ${float(valor_usdt):,.2f} USDT"
                    })
            elif moeda == "USDC":
                # Depósitos e saques de USDC não movimentam a conta USDT.
                continue
            else:
                if tipo == 'compra':
                    saldo_usdt -= valor_usdt + taxa
                    historico_movimentacao.append({
                        'data': op['Data'], 'tipo': 'compra_crypto', 'moeda': moeda, 'valor': float(valor_usdt),
                        'saldo_apos': float(saldo_usdt), 'descricao': f"Compra {moeda}: -${float(valor_usdt + taxa):,.2f} USDT"
                        + (f" (taxa {taxa} USDT)" if taxa else "")
                    })
                elif tipo == 'venda':
                    saldo_usdt += valor_usdt - taxa
                    historico_movimentacao.append({
                        'data': op['Data'], 'tipo': 'venda_crypto', 'moeda': moeda, 'valor': float(valor_usdt),
                        'saldo_apos': float(saldo_usdt), 'descricao': f"Venda {moeda}: +${float(valor_usdt - taxa):,.2f} USDT"
                        + (f" (taxa {taxa} USDT)" if taxa else "")
                    })
        return {
            'saldo_atual': float(saldo_usdt),
            'historico': historico_movimentacao
        }

    @staticmethod
    def validar_saldo_suficiente(operacoes: List[Dict], nova_compra_valor: float) -> Dict:
        saldo_info = AnalysisEngine.calcular_saldo_usdt(operacoes)
        saldo_atual = saldo_info['saldo_atual']
        return {
            'saldo_suficiente': saldo_atual >= nova_compra_valor,
            'saldo_atual': saldo_atual,
            'valor_necessario': nova_compra_valor,
            'diferenca': saldo_atual - nova_compra_valor
        }

    @staticmethod
    def calcular_distribuicao_portfolio(
        operacoes: List[Dict], precos_atuais: Dict[str, float],
        saldos_iniciais: List[Dict] | None = None,
        saldos_externos: List[Dict] | None = None,
        movimentos_custodia: List[Dict] | None = None,
    ) -> Dict:
        """Uma participação percentual só existe se TODAS as posições estão cotadas."""
        if not operacoes and not saldos_iniciais and not saldos_externos:
            return {
                "distribuicao": {}, "total_valor_portfolio": 0.0,
                "avaliacao_completa": True, "cotacoes_pendentes": [],
            }
        carteira = AnalysisEngine.calcular_portfolio(
            operacoes, precos_atuais, saldos_iniciais=saldos_iniciais,
            saldos_externos=saldos_externos,
            movimentos_custodia=movimentos_custodia,
        )
        totais = carteira["totais"]
        if not totais["avaliacao_completa"]:
            return {
                "distribuicao": {},
                "total_valor_portfolio": None,
                "total_investido": None,
                "avaliacao_completa": False,
                "cotacoes_pendentes": list(totais["cotacoes_pendentes"]),
            }
        distribuicao = {}
        total_crypto = 0.0
        for moeda, info in carteira.items():
            if moeda in ("totais", "USDT (Caixa)"):
                continue
            valor = info["valor_atual_posicao"]
            if info["quantidade_final"] > 0 and valor is not None and valor > 0:
                label = "USDC" if moeda == "USDC (Caixa)" else moeda
                distribuicao[label] = {
                    "valor_atual": valor,
                    "quantidade": info["quantidade_final"],
                }
                total_crypto += valor
        caixa = totais["caixa_usdt"]
        if caixa > 0:
            distribuicao["USDT"] = {"valor_atual": caixa, "quantidade": caixa}
        total = totais["valor_atual"]
        for info in distribuicao.values():
            info["percentual"] = 100 * info["valor_atual"] / total if total > 0 else 0
        return {
            "distribuicao": distribuicao,
            "total_investido": total_crypto,
            "total_valor_portfolio": total,
            "avaliacao_completa": True,
            "cotacoes_pendentes": [],
        }

    @staticmethod
    def _analisar_moeda(ops: List[Dict], preco_atual: float,
                        quantidade_inicial=Decimal("0"), custo_inicial=Decimal("0"),
                        custo_desconhecido=False) -> Dict:
        custo_total = Decimal(str(custo_inicial))
        quantidade_total = Decimal(str(quantidade_inicial))
        lucro_realizado = Decimal('0')
        total_comprado = Decimal('0')
        total_vendido = Decimal('0')
        pmc = (custo_total / quantidade_total if quantidade_total > 0 else Decimal("0"))
        operacoes_processadas = []
        from backend.trading_fees import taxa_da_operacao
        for op in ops:
            valor = Decimal(str(op['Valor_USDT']))
            taxa = taxa_da_operacao(op)
            preco = Decimal(str(op['Preco']))
            qtd = Decimal(str(op['Quantidade']))
            if op['Operacao'] == 'compra':
                total_comprado += valor
                custo_total += valor + taxa
                quantidade_total += qtd
                pmc = custo_total / quantidade_total if quantidade_total > 0 else Decimal('0')
                operacoes_processadas.append({
                    'tipo': 'compra', 'data': op['Data'], 'quantidade': float(qtd),
                    'preco': float(preco), 'valor': float(valor), 'pmc_apos': float(pmc)
                })
            elif op['Operacao'] == 'venda':
                if quantidade_total <= 0 or pmc <= 0:
                    operacoes_processadas.append({
                        'tipo': 'venda', 'data': op['Data'], 'quantidade': float(qtd),
                        'preco': float(preco), 'valor': float(valor), 'erro': 'Venda sem posição prévia'
                    })
                    continue
                custo_da_venda = qtd * pmc
                lucro_venda = valor - taxa - custo_da_venda
                total_vendido += valor
                lucro_realizado += lucro_venda
                custo_total -= custo_da_venda
                quantidade_total -= qtd
                if quantidade_total == 0:
                    custo_total = Decimal('0')
                    pmc = Decimal('0')
                operacoes_processadas.append({
                    'tipo': 'venda', 'data': op['Data'], 'quantidade': float(qtd),
                    'preco': float(preco), 'valor': float(valor), 'lucro': float(lucro_venda)
                })
        qtd_final = float(quantidade_total)
        custo_final = float(custo_total) if quantidade_total > Decimal("1e-9") else 0.0
        aberta = qtd_final > 1e-9
        preco_validado = AnalysisEngine._preco_disponivel(preco_atual)
        if not aberta:
            valor_atual = 0.0
            lucro_nao_realizado = 0.0
        elif preco_validado is None:
            valor_atual = None
            lucro_nao_realizado = None
        else:
            valor_atual = qtd_final * preco_validado
            lucro_nao_realizado = None if custo_desconhecido else valor_atual - custo_final
        realizado = float(lucro_realizado) if not custo_desconhecido else None
        return {
            "operacoes": operacoes_processadas,
            "quantidade_final": qtd_final,
            "pmc_final": None if custo_desconhecido else float(pmc),
            "custo_posicao_final": None if custo_desconhecido else custo_final,
            "saldo_inicial_declarado": float(quantidade_inicial),
            "base_de_custo_incompleta": bool(custo_desconhecido),
            "valor_atual_posicao": valor_atual,
            "lucro_realizado": realizado,
            "lucro_nao_realizado": lucro_nao_realizado,
            "lucro_total": (
                realizado + lucro_nao_realizado
                if lucro_nao_realizado is not None and realizado is not None else None
            ),
            "preco_de_mercado": preco_validado if aberta else None,
            "cotacao_disponivel": not aberta or preco_validado is not None,
            "total_comprado_usdt": float(total_comprado),
            "total_vendido_usdt": float(total_vendido),
        }


    @staticmethod
    def calcular_pl_usdt_brl(operacoes: List[Dict], preco_brl_atual: float) -> None:
        """Resultado REAL em BRL indisponível sem origem e custo fiscal documentados.

        Transferências USDT não comprovam aquisição por reais. Aplicar câmbio
        atual a operações passadas criaria um lucro histórico fictício.
        A UI pode converter apenas o PATRIMÔNIO ATUAL para BRL à vista.
        """
        return None
