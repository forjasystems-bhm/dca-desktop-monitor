"""Governed, separate custody ledger. No rewriting legacy trading operations.

All quantities and costs are Decimal; no inferred purchase, fee, tax basis or
network value. A sale is an external cash event, not a synthetic CSV trade.
"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class ErroMovimentacaoCustodia(ValueError):
    pass


ZERO = Decimal("0")


def numero(valor, nome, *, allow_zero=False):
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErroMovimentacaoCustodia(f"{nome}: número inválido.") from exc
    if not d.is_finite() or d < ZERO or (d == ZERO and not allow_zero):
        raise ErroMovimentacaoCustodia(f"{nome}: requer valor finito "
                                      + ("não negativo." if allow_zero else "positivo."))
    return d


def apurar_custodia(saldos_externos, movimentos=(), *, ate: date | None = None):
    """Reconstruct holdings and cash from attestations and chronological events.

    Returns quantities per custody and cost if provable. Revenue from custody
    disposals remains outside the old CSV ledger. Unknown basis keeps realized
    profit unavailable; unknown dates/cost are never replaced by today's quote.
    """
    lots = defaultdict(lambda: {"quantidade": ZERO, "custo": ZERO})
    ativos_com_custo_incompleto = set()
    for p in saldos_externos or ():
        dia = date.fromisoformat(str(p["Data"])[:10])
        if ate is not None and dia > ate:
            continue
        key = (str(p["Moeda"]).upper(), str(p["Custodia"]))
        qtd = numero(p["Quantidade"], "Quantidade do saldo")
        lot = lots[key]
        lot["quantidade"] += qtd
        c = p.get("Custo_Total_USDT")
        if c is None or str(c).strip() == "":
            lot["custo"] = None
            if key[0] not in ("USDT", "USDC"):
                ativos_com_custo_incompleto.add(key[0])
        elif lot["custo"] is not None:
            lot["custo"] += numero(c, "Custo inicial")

    realizado = ZERO
    custo_taxas_transferencias = ZERO
    resultado_conhecido = True
    transferencias = 0
    vendas = 0
    for m in sorted(movimentos or (), key=lambda r: (r["Data"], int(r.get("ID", 0)))):
        dia = date.fromisoformat(str(m["Data"])[:10])
        if ate is not None and dia > ate:
            continue
        tipo = str(m["Tipo"]).lower()
        coin = str(m["Moeda"]).upper()
        origem = str(m["Origem"])
        destino = str(m["Destino"])
        qtd = numero(m["Quantidade"], "Quantidade movimentada")
        fee_coin = numero(m["Taxa_Ativo"], "Taxa em unidades do ativo", allow_zero=True)
        fee_usdt = numero(m["Taxa_USDT"], "Corretagem em USDT", allow_zero=True)
        bruto = (numero(m["Receita_USDT"], "Receita da venda")
                 if tipo == "venda" else ZERO)
        if tipo not in ("transferencia", "venda") or origem == "" or destino == "":
            raise ErroMovimentacaoCustodia("Tipo ou local de custódia inválido.")
        if origem == destino and tipo == "transferencia":
            raise ErroMovimentacaoCustodia("Transferência para o mesmo local.")
        if tipo == "transferencia" and (bruto or fee_usdt):
            raise ErroMovimentacaoCustodia("Transferência não tem receita nem corretagem USDT.")
        if tipo == "venda" and (coin == "USDT" or fee_usdt >= bruto):
            raise ErroMovimentacaoCustodia("Venda precisa ter receita líquida USDT positiva.")
        source = lots[(coin, origem)]
        total_saida = qtd + fee_coin
        if source["quantidade"] < total_saida:
            raise ErroMovimentacaoCustodia(
                f"{coin} em {origem}: saldo insuficiente; "
                "a venda/transferência não pode utilizar o CSV antigo."
            )
        base = source["custo"]
        custo_venda = None if base is None else base * qtd / source["quantidade"]
        custo_fee = None if base is None else base * fee_coin / source["quantidade"]
        source["quantidade"] -= total_saida
        if base is not None:
            source["custo"] -= custo_venda + custo_fee
            if source["quantidade"] == ZERO:
                source["custo"] = ZERO
        if tipo == "transferencia":
            target = lots[(coin, destino)]
            target["quantidade"] += qtd
            if target["custo"] is None or custo_venda is None:
                target["custo"] = None
            else:
                target["custo"] += custo_venda
            transferencias += 1
            if custo_fee is None:
                resultado_conhecido = False
            else:
                custo_taxas_transferencias += custo_fee
        else:
            # The proceeds exist as real USDT in the nominated destination.
            lots[("USDT", destino)]["quantidade"] += bruto - fee_usdt
            vendas += 1
            if custo_venda is None or custo_fee is None:
                resultado_conhecido = False
            else:
                realizado += bruto - fee_usdt - custo_venda - custo_fee
    resultado = []
    for (coin,local),lot in sorted(lots.items()):
        if lot["quantidade"] <= ZERO:
            continue
        resultado.append({
            "Moeda":coin,"Custodia":local,"Quantidade":str(lot["quantidade"]),
            "Custo_Total_USDT":(str(lot["custo"]) if lot["custo"] is not None else None),
        })
        if coin not in ("USDT","USDC") and lot["custo"] is None:
            ativos_com_custo_incompleto.add(coin)
    return {
        "saldos": resultado,
        "lucro_vendas_externas_usdt": (realizado if resultado_conhecido else None),
        "custo_taxas_transferencias_usdt": (
            custo_taxas_transferencias if resultado_conhecido else None
        ),
        "movimentacoes":transferencias+vendas,
        "vendas":vendas,
        "ativos_sem_custo":sorted(ativos_com_custo_incompleto),
        "resultado_completo":resultado_conhecido,
    }
