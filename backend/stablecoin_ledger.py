"""FIN-04 — Separate stablecoin balances; no implicit USDC-to-USDT exchange.

The legacy Valor_USDT field means *nominal units* for USDC transfers only.
It is never evidence that USDC was acquired at a 1:1 USDT rate.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation

STABLECOINS = frozenset(("USDT", "USDC"))


class ErroStablecoin(ValueError):
    pass


def _positivo(registro, campo, idx):
    try:
        valor = Decimal(str(registro[campo]))
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise ErroStablecoin(f"Registro {idx}: {campo} inválido.") from exc
    if not valor.is_finite() or valor <= 0:
        raise ErroStablecoin(f"Registro {idx}: {campo} precisa ser positivo e finito.")
    return valor


def saldos_stablecoins(operacoes: list[dict], *, fim=None) -> dict:
    """Return independent quantities and explicit external flows by coin.

    Does not count crypto purchases/sales in the external stablecoin flow.
    The USDT cash result is provided by AnalysisEngine.calcular_saldo_usdt,
    which also includes crypto transaction settlements.
    """
    saldos = {"USDT": Decimal("0"), "USDC": Decimal("0")}
    entradas = {"USDT": Decimal("0"), "USDC": Decimal("0")}
    saidas = {"USDT": Decimal("0"), "USDC": Decimal("0")}
    for idx, row in enumerate(operacoes, 1):
        if fim is not None and str(row["Data"])[:10] > str(fim):
            continue
        moeda = str(row["Moeda"]).strip().upper()
        if moeda not in STABLECOINS:
            continue
        tipo = str(row["Operacao"]).lower()
        if tipo not in ("compra", "venda"):
            raise ErroStablecoin(f"Registro {idx}: movimento {moeda} inválido.")
        quantidade = _positivo(row, "Quantidade", idx)
        valor_nominal = _positivo(row, "Valor_USDT", idx)
        if abs(quantidade - valor_nominal) > Decimal("0.00000001"):
            raise ErroStablecoin(
                f"Registro {idx}: {moeda} exige unidades iguais ao valor nominal."
            )
        if tipo == "compra":
            entradas[moeda] += quantidade
            saldos[moeda] += quantidade
        else:
            saidas[moeda] += quantidade
            saldos[moeda] -= quantidade
    return {"saldos": saldos, "entradas": entradas, "saidas": saidas}
