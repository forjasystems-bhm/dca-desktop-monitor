"""Análises financeiras auditáveis a partir das operações locais existentes.

Atenção: P/L realizado e movimentações históricas são valores em USDT.
Não há marcação a mercado retrospectiva nem conversão histórica BRL aqui.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class ErroAnaliseFinanceira(ValueError):
    """Impede exibir números silenciosamente incorretos."""


ZERO = Decimal("0")


def _data(valor: str | date | None, nome: str) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(valor)
    except (ValueError, TypeError) as exc:
        raise ErroAnaliseFinanceira(f"{nome} inválida; informe AAAA-MM-DD.") from exc


def _decimal(registro: dict, chave: str, linha: int, positivo: bool = True) -> Decimal:
    try:
        resultado = Decimal(str(registro[chave]))
        if not resultado.is_finite() or (positivo and resultado <= ZERO):
            raise InvalidOperation
        return resultado
    except (InvalidOperation, KeyError, ValueError, TypeError) as exc:
        raise ErroAnaliseFinanceira(f"Registro {linha}: {chave} inválido.") from exc


def calcular_analise_por_periodo(
    operacoes: list[dict[str, Any]],
    inicio: str | date | None = None,
    fim: str | date | None = None,
) -> dict[str, Any]:
    """Usa custo médio móvel, histórico integral até o fim e movimentos do intervalo.

    Uma venda realizada dentro do intervalo precisa conhecer as compras anteriores.
    Compras de ativos não são aportes externos na carteira: USDT é contabilizado
    separadamente. Não inferir BRL histórico a partir do câmbio atual.
    """
    data_inicio = _data(inicio, "Data inicial")
    data_fim = _data(fim, "Data final")
    if data_inicio is not None and data_fim is not None and data_inicio > data_fim:
        raise ErroAnaliseFinanceira("A data inicial não pode ser posterior à final.")

    campos = (
        "compras_historicas", "vendas_historicas", "realizado_historico",
        "compras_periodo", "vendas_periodo", "realizado_periodo",
        "quantidade", "custo_aberto", "operacoes_periodo",
    )

    def estado():
        return {
            "compras_historicas": ZERO,
            "vendas_historicas": ZERO,
            "realizado_historico": ZERO,
            "compras_periodo": ZERO,
            "vendas_periodo": ZERO,
            "realizado_periodo": ZERO,
            "quantidade": ZERO,
            "custo_aberto": ZERO,
            "operacoes_periodo": 0,
        }

    ativos = defaultdict(estado)
    aportes = ZERO
    saques = ZERO
    registros = []
    for linha, op in enumerate(operacoes, start=2):
        try:
            timestamp = datetime.strptime(str(op["Data"]), "%Y-%m-%d %H:%M:%S")
            moeda = str(op["Moeda"]).strip().upper()
            tipo = str(op["Operacao"]).strip().lower()
        except (KeyError, TypeError, ValueError) as exc:
            raise ErroAnaliseFinanceira(f"Registro {linha}: data ou identificação inválida.") from exc
        if not moeda or tipo not in ("compra", "venda"):
            raise ErroAnaliseFinanceira(f"Registro {linha}: moeda ou operação inválida.")
        quantidade = _decimal(op, "Quantidade", linha)
        valor = _decimal(op, "Valor_USDT", linha)
        registros.append((timestamp, linha, moeda, tipo, quantidade, valor))

    # O índice conserva a ordem original para operações com o mesmo timestamp.
    registros.sort(key=lambda x: (x[0], x[1]))
    for timestamp, linha, moeda, tipo, quantidade, valor in registros:
        data_op = timestamp.date()
        if data_fim is not None and data_op > data_fim:
            continue
        dentro = (data_inicio is None or data_op >= data_inicio)
        if moeda == "USDT":
            if dentro:
                if tipo == "compra":
                    aportes += valor
                else:
                    saques += valor
            continue

        s = ativos[moeda]
        if tipo == "compra":
            s["quantidade"] += quantidade
            s["custo_aberto"] += valor
            s["compras_historicas"] += valor
            if dentro:
                s["compras_periodo"] += valor
                s["operacoes_periodo"] += 1
        else:
            if s["quantidade"] == ZERO or quantidade > s["quantidade"]:
                raise ErroAnaliseFinanceira(
                    f"Registro {linha}: venda de {moeda} excede a posição disponível."
                )
            custo_venda = s["custo_aberto"] * quantidade / s["quantidade"]
            realizado = valor - custo_venda
            s["quantidade"] -= quantidade
            s["custo_aberto"] -= custo_venda
            if s["quantidade"] == ZERO:
                s["custo_aberto"] = ZERO
            s["vendas_historicas"] += valor
            s["realizado_historico"] += realizado
            if dentro:
                s["vendas_periodo"] += valor
                s["realizado_periodo"] += realizado
                s["operacoes_periodo"] += 1

    totais = {campo: ZERO if campo != "operacoes_periodo" else 0 for campo in campos}
    for estado_moeda in ativos.values():
        for campo in campos:
            totais[campo] += estado_moeda[campo]

    return {
        "inicio": data_inicio,
        "fim": data_fim,
        "ativos": dict(sorted(ativos.items())),
        "totais": totais,
        "aportes_periodo_usdt": aportes,
        "saques_periodo_usdt": saques,
        "unidade": "USDT",
    }
