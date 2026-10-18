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
                 *, data_dir=None, legacy_csv=None):
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
            self.arquivo_csv,
        )
        self.arquivo_db = self._store.arquivo_db

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

    def excluir_operacao(self, indice: int) -> bool:
        try:
            return self._store.excluir(indice)
        except Exception:
            logger.exception("Falha ao excluir operação; banco preservado")
            return False

    def atualizar_operacao(self, indice: int, nova_operacao: Dict) -> bool:
        try:
            return self._store.substituir(indice, nova_operacao)
        except Exception:
            logger.exception("Falha ao atualizar operação; banco preservado")
            return False

    def salvar_operacao(self, operacao: List) -> bool:
        try:
            return self._store.inserir(operacao)
        except Exception:
            logger.exception("Falha ao salvar operação; banco preservado")
            return False

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

    def atualizar_precos(self, moedas: List[str]) -> bool:
        if not self.exchange:
            self.falhas_cotacao.update(m.upper() for m in moedas if m.upper() != "USDT")
            self._brl_falhou = True
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
    def calcular_portfolio(operacoes: List[Dict], precos_atuais: Dict[str, float]) -> Dict:
        if not operacoes:
            return {}
        saldo_caixa = AnalysisEngine.calcular_saldo_usdt(operacoes)["saldo_atual"]
        por_moeda = defaultdict(list)
        for op in sorted(operacoes, key=lambda x: x["Data"]):
            if op["Moeda"] != "USDT":
                por_moeda[op["Moeda"]].append(op)
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
        }
        for moeda, ops in por_moeda.items():
            preco = AnalysisEngine._preco_disponivel(precos_atuais.get(moeda))
            analise = AnalysisEngine._analisar_moeda(ops, preco)
            resultado[moeda] = analise
            totais["investido_liquido"] += analise["custo_posicao_final"]
            totais["realizado"] += analise["lucro_realizado"]
            totais["compras_historicas_usdt"] += analise["total_comprado_usdt"]
            totais["vendas_historicas_usdt"] += analise["total_vendido_usdt"]
            if analise["valor_atual_posicao"] is None:
                totais["cotacoes_pendentes"].append(moeda)
            else:
                totais["valor_atual"] += analise["valor_atual_posicao"]
                totais["nao_realizado"] += analise["lucro_nao_realizado"]
        if totais["cotacoes_pendentes"]:
            totais["cotacoes_pendentes"].sort()
            totais["avaliacao_completa"] = False
            totais["valor_atual"] = None
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
    def calcular_saldo_usdt(operacoes: List[Dict]) -> Dict:
        saldo_usdt = Decimal('0')
        historico_movimentacao = []
        for op in sorted(operacoes, key=lambda x: x['Data']):
            valor_usdt = Decimal(str(op['Valor_USDT']))
            moeda = op['Moeda']
            tipo = op['Operacao']
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
            else:
                if tipo == 'compra':
                    saldo_usdt -= valor_usdt
                    historico_movimentacao.append({
                        'data': op['Data'], 'tipo': 'compra_crypto', 'moeda': moeda, 'valor': float(valor_usdt),
                        'saldo_apos': float(saldo_usdt), 'descricao': f"Compra {moeda}: -${float(valor_usdt):,.2f} USDT"
                    })
                elif tipo == 'venda':
                    saldo_usdt += valor_usdt
                    historico_movimentacao.append({
                        'data': op['Data'], 'tipo': 'venda_crypto', 'moeda': moeda, 'valor': float(valor_usdt),
                        'saldo_apos': float(saldo_usdt), 'descricao': f"Venda {moeda}: +${float(valor_usdt):,.2f} USDT"
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
        operacoes: List[Dict], precos_atuais: Dict[str, float]
    ) -> Dict:
        """Uma participação percentual só existe se TODAS as posições estão cotadas."""
        if not operacoes:
            return {
                "distribuicao": {}, "total_valor_portfolio": 0.0,
                "avaliacao_completa": True, "cotacoes_pendentes": [],
            }
        carteira = AnalysisEngine.calcular_portfolio(operacoes, precos_atuais)
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
                distribuicao[moeda] = {
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
    def _analisar_moeda(ops: List[Dict], preco_atual: float) -> Dict:
        custo_total = Decimal('0')
        quantidade_total = Decimal('0')
        lucro_realizado = Decimal('0')
        total_comprado = Decimal('0')
        total_vendido = Decimal('0')
        pmc = Decimal('0')
        operacoes_processadas = []
        for op in ops:
            valor = Decimal(str(op['Valor_USDT']))
            preco = Decimal(str(op['Preco']))
            qtd = Decimal(str(op['Quantidade']))
            if op['Operacao'] == 'compra':
                total_comprado += valor
                custo_total += valor
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
                lucro_venda = valor - custo_da_venda
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
            lucro_nao_realizado = valor_atual - custo_final
        realizado = float(lucro_realizado)
        return {
            "operacoes": operacoes_processadas,
            "quantidade_final": qtd_final,
            "pmc_final": float(pmc),
            "custo_posicao_final": custo_final,
            "valor_atual_posicao": valor_atual,
            "lucro_realizado": realizado,
            "lucro_nao_realizado": lucro_nao_realizado,
            "lucro_total": (
                realizado + lucro_nao_realizado
                if lucro_nao_realizado is not None else None
            ),
            "preco_de_mercado": preco_validado if aberta else None,
            "cotacao_disponivel": not aberta or preco_validado is not None,
            "total_comprado_usdt": float(total_comprado),
            "total_vendido_usdt": float(total_vendido),
        }


    @staticmethod
    def calcular_pl_usdt_brl(operacoes: List[Dict], preco_brl_atual: float) -> Dict | None:
        if preco_brl_atual <= 0:
            return None

        custo_brl       = Decimal('0')
        quantidade_usdt = Decimal('0')
        lucro_realizado = Decimal('0')
        pmc_brl         = Decimal('0')

        for op in sorted(operacoes, key=lambda x: x['Data']):
            tipo     = op['Operacao']
            moeda    = op['Moeda']
            valor    = Decimal(str(op['Valor_USDT']))
            taxa_brl = Decimal(str(op.get('Taxa_BRL') or 0))

            if moeda == 'USDT':
                qtd = Decimal(str(op['Quantidade']))
                
                if tipo == 'compra':
                    taxa_deposito = taxa_brl if taxa_brl > 0 else Decimal(str(preco_brl_atual))
                    
                    custo_brl       += qtd * taxa_deposito
                    quantidade_usdt += qtd
                    pmc_brl = custo_brl / quantidade_usdt if quantidade_usdt > 0 else Decimal('0')
                    
                elif tipo == 'venda' and quantidade_usdt > 0:
                    qtd_saque = min(qtd, quantidade_usdt)
                    
                    custo_venda = qtd_saque * pmc_brl
                    taxa_saque = taxa_brl if taxa_brl > 0 else pmc_brl
                    
                    lucro_realizado += (qtd_saque * taxa_saque) - custo_venda
                    custo_brl       -= custo_venda
                    quantidade_usdt -= qtd_saque

            else:
                if tipo == 'compra' and quantidade_usdt > 0:
                    qtd_gasta = min(valor, quantidade_usdt)
                    custo_venda = qtd_gasta * pmc_brl
                    
                    custo_brl       -= custo_venda
                    quantidade_usdt -= qtd_gasta

                elif tipo == 'venda':
                    if taxa_brl > 0:
                        taxa_entrada = taxa_brl                    
                    elif pmc_brl > 0:
                        taxa_entrada = pmc_brl                    
                    else:
                        taxa_entrada = Decimal(str(preco_brl_atual)) 
                    
                    custo_brl       += valor * taxa_entrada
                    quantidade_usdt += valor
                    pmc_brl = custo_brl / quantidade_usdt if quantidade_usdt > 0 else Decimal('0')


            if quantidade_usdt < Decimal('1e-8'):
                quantidade_usdt = Decimal('0')
                custo_brl       = Decimal('0')
                pmc_brl         = Decimal('0')

        # A contagem de quantidade_usdt acima pode divergir do saldo de caixa real
        # (por causa dos clamps min(...) e do reset quando o saldo zera). O saldo de
        # caixa é a fonte única da verdade; reconciliamos a posição com ele para que
        # quantidade, custo, valor atual e P/L fechem com as demais telas em vez de
        # misturar duas quantidades de USDT diferentes na mesma linha.
        saldo_real = Decimal(str(AnalysisEngine.calcular_saldo_usdt(operacoes)['saldo_atual']))
        if saldo_real <= Decimal('0'):
            return None
        if pmc_brl <= Decimal('0'):
            pmc_brl = Decimal(str(preco_brl_atual))

        qtd_final   = float(saldo_real)
        custo_final = float(saldo_real * pmc_brl)
        valor_atual = qtd_final * preco_brl_atual
        pl_nao_real = valor_atual - custo_final

        return {
            'quantidade_usdt':         qtd_final,
            'pmc_brl':                 float(pmc_brl),
            'custo_posicao_brl':       custo_final,
            'valor_atual_brl':         valor_atual,
            'lucro_nao_realizado_brl': pl_nao_real,
            'lucro_realizado_brl':     float(lucro_realizado),
            'lucro_total_brl':         pl_nao_real + float(lucro_realizado),
            'preco_brl_atual':         preco_brl_atual,
        }