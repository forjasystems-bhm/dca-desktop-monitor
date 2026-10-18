"""FIN-06: conciliação do patrimônio e rentabilidade com fluxos externos.

Nenhum percentual é dividido por giro de compras. O Modified Dietz só aparece
quando há histórico fechado de operações, caixa conciliado, posições cotadas,
taxas documentadas e nenhum fluxo externo em USDC sem contrapartida registrada.

O retorno é uma estimativa DIÁRIA desde o primeiro evento, não TWR nem XIRR.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.finance_analytics import calcular_analise_por_periodo
from backend.operation_integrity import ErroIntegridadeFinanceira, validar_livro

ZERO = Decimal("0")
TOLERANCIA_USDT = Decimal("0.0001")


def _decimal_seguro(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def auditar_carteira_atual(
    operacoes: list[dict], portfolio: dict, *, data_referencia: date | None = None
) -> dict:
    """Reconciles gross external flows with actual cash+marked-to-market.

    Internals (buy/sell) are never counted as new capital. Historic fiat FX is
    not inferred; only the USDT ledger is audited here.
    """
    day = data_referencia or date.today()
    resposta = {
        "patrimonio_usdt": None,
        "aportes_externos_usdt": ZERO,
        "retiradas_externas_usdt": ZERO,
        "capital_externo_liquido_usdt": ZERO,
        "resultado_patrimonial_usdt": None,
        "resultado_contabil_usdt": None,
        "desvio_conciliacao_usdt": None,
        "conciliado": False,
        "retorno_dietz_percentual": None,
        "retorno_tipo": "Modified Dietz — estimativa diária desde o início",
        "motivos": [],
        "operacoes_sem_taxa": 0,
    }
    motivos = resposta["motivos"]
    if not isinstance(day, date) or isinstance(day, datetime):
        motivos.append("Data de avaliação inválida.")
        return resposta
    if not operacoes:
        motivos.append("Ainda não existem operações.")
        return resposta

    try:
        validar_livro(operacoes)
    except (ErroIntegridadeFinanceira, ValueError) as exc:
        motivos.append(f"Livro de operações exige conciliação: {exc}")
        return resposta

    try:
        analise = calcular_analise_por_periodo(operacoes)
    except ValueError as exc:
        motivos.append(f"Análise financeira inválida: {exc}")
        return resposta

    resposta["operacoes_sem_taxa"] = analise["operacoes_sem_taxa_documentada"]
    if analise["entradas_periodo_usdc"] or analise["saidas_periodo_usdc"]:
        motivos.append(
            "Movimentos externos de USDC sem valor de aquisição documentado: "
            "não calcular rentabilidade consolidada em USDT."
        )
        return resposta

    totais = portfolio.get("totais", {})
    if not totais.get("avaliacao_completa", False):
        faltas = totais.get("cotacoes_pendentes", [])
        motivos.append(
            "Cotações atuais insuficientes"
            + (": " + ", ".join(faltas) if faltas else ".")
        )
        return resposta
    patrimonio = _decimal_seguro(totais.get("valor_atual"))
    lucro_contabil = _decimal_seguro(totais.get("realizado"))
    nao_realizado = _decimal_seguro(totais.get("nao_realizado"))
    if patrimonio is None or lucro_contabil is None or nao_realizado is None:
        motivos.append("Patrimônio ou P/L não está integralmente disponível.")
        return resposta
    if patrimonio < ZERO:
        motivos.append("Patrimônio negativo: verificar operações e saldos.")
        return resposta
    resposta["patrimonio_usdt"] = patrimonio
    resposta["resultado_contabil_usdt"] = lucro_contabil + nao_realizado

    aportes = ZERO
    retiradas = ZERO
    fluxos = []
    for pos, op in enumerate(operacoes, 1):
        try:
            day_op = date.fromisoformat(str(op["Data"])[:10])
            if day_op > day:
                motivos.append(
                    f"Operação {pos} está no futuro da avaliação: {day_op}."
                )
                return resposta
            if str(op["Moeda"]).upper() == "USDT":
                value = Decimal(str(op["Valor_USDT"]))
                if str(op["Operacao"]).lower() == "compra":
                    aportes += value
                    fluxos.append((day_op, value))
                else:
                    retiradas += value
                    fluxos.append((day_op, -value))
        except (InvalidOperation, ValueError, KeyError, TypeError) as exc:
            motivos.append(f"Fluxo externo {pos} inválido: {exc}")
            return resposta

    net = aportes - retiradas
    resposta["aportes_externos_usdt"] = aportes
    resposta["retiradas_externas_usdt"] = retiradas
    resposta["capital_externo_liquido_usdt"] = net
    diferenca_patrimonial = patrimonio - net
    resposta["resultado_patrimonial_usdt"] = diferenca_patrimonial
    desvio = diferenca_patrimonial - resposta["resultado_contabil_usdt"]
    resposta["desvio_conciliacao_usdt"] = desvio
    tolerancia = max(TOLERANCIA_USDT, abs(patrimonio) * Decimal("0.00000001"))
    if abs(desvio) > tolerancia:
        motivos.append(
            "Patrimônio menos aportes líquidos diverge do P/L contábil: "
            f"{desvio} USDT. Percentual bloqueado."
        )
        return resposta
    resposta["conciliado"] = True

    # Unknown commissions must not be presented as exact NET portfolio returns.
    if resposta["operacoes_sem_taxa"]:
        motivos.append(
            f"{resposta['operacoes_sem_taxa']} negociação(ões) sem corretagem "
            "documentada; retorno líquido não apurado."
        )
        return resposta

    if aportes <= ZERO or not fluxos:
        motivos.append("Sem aportes externos suficientes para apurar retorno.")
        return resposta

    begin = min(d for d, _ in fluxos)
    total_days = (day - begin).days
    if total_days < 1:
        motivos.append("Menos de um dia completo de histórico para estimar retorno.")
        return resposta

    weighted_capital = sum(
        (
            flow * Decimal((day - op_day).days) / Decimal(total_days)
            for op_day, flow in fluxos
        ), ZERO
    )
    if weighted_capital <= ZERO:
        motivos.append("Capital externo ponderado não positivo; retorno indisponível.")
        return resposta
    resposta["retorno_dietz_percentual"] = (
        diferenca_patrimonial / weighted_capital * Decimal("100")
    )
    return resposta
