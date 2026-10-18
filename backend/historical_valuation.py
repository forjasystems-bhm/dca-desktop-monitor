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
    iniciais = (
        armazem.listar_posicoes_iniciais()
        if hasattr(armazem, "listar_posicoes_iniciais") else []
    )
    externos = (
        armazem.listar_posicoes_externas()
        if hasattr(armazem, "listar_posicoes_externas") else []
    )
    movimentos = (
        armazem.listar_movimentos_custodia()
        if hasattr(armazem, "listar_movimentos_custodia") else []
    )
    analise = calcular_analise_por_periodo(
        transacoes, fim=data_ref, saldos_iniciais=iniciais,
        saldos_externos=externos, movimentos_custodia=movimentos,
    )
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
            nao_realizado = (
                None if ativo in analise["ativos_sem_custo"] else valor - custo
            )
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

    # USDC é um saldo independente, não uma compra de cripto financiada em USDT.
    quantidade_usdc = analise["saldo_usdc"]
    if quantidade_usdc > ZERO:
        cotacao = cotacoes.get("USDC")
        if cotacao is None:
            ausentes.append("USDC")
            valor_usdc = None
        else:
            valor_usdc = quantidade_usdc * cotacao["preco"]
            mercado_aberto += valor_usdc
        itens["USDC"] = {
            "quantidade": quantidade_usdc,
            "custo_aberto": None,
            "valor_mercado": valor_usdc,
            "nao_realizado": None,
            "lucro_realizado": None,
            "cotacao": cotacao,
            "transferencia_externa": True,
        }

    # Reconstrução do saldo em USDT APENAS até o dia analisado.
    # Este histórico considera as operações do CSV legado, sem inferir taxas.
    caixa = analise["saldo_usdt_inicial"]
    from backend.trading_fees import taxa_da_operacao
    for op in transacoes:
        if date.fromisoformat(str(op["Data"])[:10]) > data_ref:
            continue
        valor = Decimal(str(op["Valor_USDT"]))
        tipo = str(op["Operacao"]).lower()
        moeda = str(op["Moeda"]).upper()
        if moeda == "USDT":
            caixa += valor if tipo == "compra" else -valor
        elif moeda == "USDC":
            # Sem paridade implícita: valor nominal USDC não liquida caixa USDT.
            continue
        else:
            taxa = taxa_da_operacao(op)
            caixa += -(valor + taxa) if tipo == "compra" else valor - taxa

    alertas = []
    if ausentes:
        alertas.append(
            "Faltam fechamentos históricos UTC em: " + ", ".join(sorted(ausentes))
        )
    if quantidade_usdc < ZERO:
        alertas.append(
            "Saldo USDC histórico negativo; confira aportes e retiradas "
            "antes de consolidar o patrimônio."
        )
    if caixa < ZERO:
        alertas.append(
            "Saldo USDT histórico negativo: possíveis movimentos anteriores "
            "ao início do registro. Reconcilie antes de apurar patrimônio total."
        )
    completo = not alertas
    total = caixa + mercado_aberto if completo else None
    lucro_nr = (
        mercado_aberto - custo_aberto
        if completo and not analise["base_de_custo_incompleta"]
        else None
    )

    # Aggregate includes actual custody disposals only when their opening cost
    # is known. Keep the imported-CSV realized amount separately auditable.
    lucro_csv = analise["totais"]["realizado_historico"]
    lucro_externo = analise["lucro_custodia_usdt"]
    lucro_realizado = (
        lucro_csv + lucro_externo if lucro_externo is not None else None
    )
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
        "lucro_realizado": lucro_realizado,
        "lucro_realizado_csv": lucro_csv,
        "base_de_custo_incompleta": analise["base_de_custo_incompleta"],
        "saldos_externos_declarados": analise["saldos_externos_declarados"],
        "movimentacoes_custodia": analise["movimentacoes_custodia"],
        "lucro_custodia_usdt": analise["lucro_custodia_usdt"],
        "saldo_usdc": quantidade_usdc,
        "operacoes_sem_taxa_documentada": analise["operacoes_sem_taxa_documentada"],
        "resultado_total": (
            lucro_realizado + lucro_nr
            if lucro_nr is not None and lucro_realizado is not None else None
        ),
    }
