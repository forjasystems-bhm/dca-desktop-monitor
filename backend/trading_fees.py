"""Comissão explícita paga em USDT; câmbio Taxa_BRL nunca é comissão."""
from decimal import Decimal, InvalidOperation

CAMPO = "Taxa_Corretagem_USDT"

class ErroTaxaOperacional(ValueError):
    pass

def taxa_informada(op):
    v = op.get(CAMPO)
    return v is not None and str(v).strip() != ""

def taxa_da_operacao(op):
    v = op.get(CAMPO)
    if v is None or str(v).strip() == "":
        return Decimal("0")  # O valor não informado permanece ausente no banco.
    try:
        taxa = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ErroTaxaOperacional("Taxa de corretagem em USDT inválida.") from exc
    if not taxa.is_finite() or taxa < 0:
        raise ErroTaxaOperacional("Taxa de corretagem deve ser finita e não negativa.")
    if str(op.get("Moeda", "")).upper() in ("USDT", "USDC"):
        raise ErroTaxaOperacional(
            "A taxa de corretagem em USDT somente vale para compra/venda de criptoativos."
        )
    if str(op.get("Operacao", "")).lower() == "venda":
        try:
            bruto = Decimal(str(op["Valor_USDT"]))
        except (InvalidOperation, ValueError, TypeError, KeyError) as exc:
            raise ErroTaxaOperacional("Valor bruto de venda inválido.") from exc
        if taxa > bruto:
            raise ErroTaxaOperacional("Taxa não pode superar o valor bruto da venda.")
    return taxa
