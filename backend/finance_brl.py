"""Historical BRL book: per-trade documented FX, not current spot FX.

Amounts reflect moving-average acquisition costs in BRL. Unavailable FX,
legacy discrepancies, undocumented acquisition basis or commission make
the affected result unavailable; they never become zero or guessed values.
Not a tax return, FX capital-gains assessment, or USDC parity assumption.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")
VALUE_FIELDS = ("compras_historicas", "compras_periodo", "vendas_periodo",
                "realizado_historico", "realizado_periodo", "custo_aberto")

def _num(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None

def _date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))

def apurar_brl_historico(operacoes, *, inicio=None, fim=None,
                         saldos_iniciais=None, saldos_externos=None,
                         movimentos_custodia=None):
    start, end = _date(inicio), _date(fim)
    if start and end and start > end:
        raise ValueError("Período BRL inválido.")
    def new_state():
        return {**{key: ZERO for key in VALUE_FIELDS}, "quantidade": ZERO}
    states = defaultdict(new_state)
    reasons = set()
    for item in (saldos_iniciais or []):
        coin = str(item["Moeda"]).upper()
        if coin in ("USDT", "USDC") or (end and _date(str(item["Data"])[:10]) > end):
            continue
        state = states[coin]
        state["quantidade"] += Decimal(str(item["Quantidade"]))
        state["custo_aberto"] = None
        reasons.add(f"{coin}: saldo anterior sem custo de aquisição em BRL.")
    # External custody has no documented historical BRL ledger. Preserve a
    # clear, conservative unavailable status for its affected asset.
    external_coins = {
        str(i["Moeda"]).upper() for i in (saldos_externos or [])
        if str(i["Moeda"]).upper() not in ("USDT", "USDC")
        and (not end or _date(str(i["Data"])[:10]) <= end)
    }
    external_coins |= {
        str(i["Moeda"]).upper() for i in (movimentos_custodia or [])
        if str(i["Moeda"]).upper() not in ("USDT", "USDC")
        and (not end or _date(str(i["Data"])[:10]) <= end)
    }
    for coin in external_coins:
        state = states[coin]
        state["custo_aberto"] = None
        state["realizado_historico"] = None
        state["realizado_periodo"] = None
        reasons.add(f"{coin}: custódia externa sem escrituração BRL completa.")
    records = sorted(enumerate(operacoes or [], 1),
                     key=lambda row: (str(row[1]["Data"]), row[0]))
    for n, op in records:
        day = _date(str(op["Data"])[:10])
        if end and day > end:
            continue
        coin = str(op["Moeda"]).upper()
        if coin in ("USDT", "USDC"):
            continue
        in_period = start is None or day >= start
        state = states[coin]
        qty = _num(op.get("Quantidade"))
        value = _num(op.get("Valor_USDT"))
        unit = _num(op.get("Preco"))
        fx = _num(op.get("Taxa_BRL"))
        raw_fee = op.get("Taxa_Corretagem_USDT")
        fee = _num(raw_fee) if raw_fee is not None and str(raw_fee).strip() else None
        valid = (qty is not None and qty > ZERO and value is not None and
                 value > ZERO and unit is not None and unit > ZERO and
                 fx is not None and fx > ZERO and
                 (fee is None or fee >= ZERO))
        if not valid:
            reasons.add(f"{coin}, operação {n}: câmbio/valores históricos indisponíveis.")
        if qty is None or qty <= ZERO:
            continue
        # Known divergence requires reconciliation, NOT a fictitious fee.
        if unit is None or value is None or abs(qty * unit - value) > min(
            max(Decimal("0.01"), unit * Decimal("0.00000001")),
            max(Decimal("0.00000001"), value * Decimal("0.0001"))
        ):
            valid = False
            reasons.add(f"{coin}, operação {n}: quantidade × preço diverge de Valor_USDT.")
        is_buy = str(op.get("Operacao", "")).lower() == "compra"
        amount = value * fx if valid else None
        if is_buy:
            if in_period:
                state["compras_periodo"] = (
                    state["compras_periodo"] + amount
                    if state["compras_periodo"] is not None and amount is not None
                    else None)
            state["compras_historicas"] = (
                state["compras_historicas"] + amount
                if state["compras_historicas"] is not None and amount is not None
                else None)
            state["quantidade"] += qty
            basis = (amount + fee * fx) if amount is not None and fee is not None else None
            if state["custo_aberto"] is None or basis is None:
                state["custo_aberto"] = None
                if fee is None:
                    reasons.add(f"{coin}, operação {n}: corretagem não documentada.")
            else:
                state["custo_aberto"] += basis
        else:
            if in_period:
                state["vendas_periodo"] = (
                    state["vendas_periodo"] + amount
                    if state["vendas_periodo"] is not None and amount is not None else None)
            available = state["quantidade"]
            cost = (state["custo_aberto"] * qty / available
                    if available >= qty and available > ZERO and
                    state["custo_aberto"] is not None else None)
            gain = (amount - fee * fx - cost
                    if amount is not None and fee is not None and cost is not None else None)
            for key in ("realizado_historico", "realizado_periodo"):
                if key == "realizado_periodo" and not in_period:
                    continue
                state[key] = (state[key] + gain
                              if state[key] is not None and gain is not None else None)
            if gain is None:
                reasons.add(f"{coin}, operação {n}: lucro BRL não apurável com os dados informados.")
            state["quantidade"] -= qty
            if state["quantidade"] < ZERO:
                reasons.add(f"{coin}, operação {n}: quantidade insuficiente.")
                state["quantidade"] = ZERO
                state["custo_aberto"] = None
            elif state["quantidade"] == ZERO:
                state["custo_aberto"] = ZERO
            elif cost is not None:
                state["custo_aberto"] -= cost
            else:
                state["custo_aberto"] = None
    # Do not sum a known subtotal and label it as a full total.
    totals = {}
    for key in VALUE_FIELDS:
        values = [item[key] for item in states.values()]
        totals[key] = None if any(x is None for x in values) else sum(values, ZERO)
    return {"ativos": dict(sorted(states.items())), "totais": totals,
            "avisos": sorted(reasons), "unidade": "BRL"}
