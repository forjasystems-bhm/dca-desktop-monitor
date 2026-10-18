"""Apuração do patrimônio na data de referência, a partir do SQLite.

Não usa cotações em memória, ticker atual ou conversão BRL contemporânea.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.finance_analytics import calcular_analise_por_periodo
from backend.historical_prices import validar_data_encerrada

ZERO = Decimal("0")


def patrimonio_historico_na_data(
    armazem: Any, data_ref: date, *, hoje_utc: date | None = None
) -> dict:
    """Retorna patrimônios apenas quando TODOS os insumos estão disponíveis.

    Registros CSV legados não trazem fuso: filtramos pela data civil escrita no CSV.
    Cada cotação de mercado deve ser o fechamento do dia UTC correspondente.
    """
    validar_data_encerrada(data_ref, hoje_utc)
    transacoes = armazem.listar_preciso()
    analise = calcular_analise_por_periodo(transacoes, fim=data_ref)
    cotacoes = armazem.ler_cotacoes_historicas(data_ref)
    itens = {}
    ausentes = []
    mercado_aberto = ZERO
    custo_aberto = ZERO
    for ativo, p in analise["ativos"].items():
        quantidade = p["quantidade"]
        custo = p["custo_aberto"]
        cotacao = cotacoes.get(ativo) if quantidade > ZERO else None
        if quantidade > ZERO and cotacao is None:
            ausentes.append(ativo)
            valor = None
            nao_realizado = None
        elif quantidade > ZERO:
            preco = cotacao["preco"]
            valor = quantidade * preco
            nao_realizado = valor - custo
            mercado_aberto += valor
            custo_aberto += custo
        else:
            valor = ZERO
            nao_realizado = ZERO
        itens[ativo] = {
            "quantidade": quantidade,
            "custo_aberto": custo,
            "valor_mercado": valor,
            "nao_realizado": nao_realizado,
            "lucro_realizado": p["realizado_historico"],
            "cotacao": cotacao,
        }

    # Reconstrução do saldo em USDT APENAS até o dia analisado.
    # Este histórico considera as operações do CSV legado, sem inferir taxas.
    caixa = ZERO
    for op in transacoes:
        if date.fromisoformat(str(op["Data"])[:10]) > data_ref:
            continue
        valor = Decimal(str(op["Valor_USDT"]))
        tipo = str(op["Operacao"]).lower()
        moeda = str(op["Moeda"]).upper()
        if moeda == "USDT":
            caixa += valor if tipo == "compra" else -valor
        else:
            caixa += -valor if tipo == "compra" else valor

    alertas = []
    if ausentes:
        alertas.append(
            "Faltam fechamentos históricos UTC em: " + ", ".join(sorted(ausentes))
        )
    if caixa < ZERO:
        alertas.append(
            "Saldo USDT histórico negativo: possíveis movimentos anteriores "
            "ao início do registro. Reconcilie antes de apurar patrimônio total."
        )
    completo = not alertas
    total = caixa + mercado_aberto if completo else None
    lucro_nr = mercado_aberto - custo_aberto if completo else None

    return {
        "data_utc": data_ref.isoformat(),
        "unidade": "USDT",
        "criterio": "fechamento diário Binance UTC, registrado no SQLite",
        "caixa_usdt": caixa,
        "ativos": itens,
        "faltam_cotacoes": sorted(ausentes),
        "alertas": alertas,
        "completo": completo,
        "patrimonio_total": total,
        "lucro_nao_realizado": lucro_nr,
        "lucro_realizado": analise["totais"]["realizado_historico"],
        "resultado_total": (
            analise["totais"]["realizado_historico"] + lucro_nr
            if completo else None
        ),
    }
