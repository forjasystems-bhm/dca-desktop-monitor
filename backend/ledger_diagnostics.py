"""Read-only discrepancies in historic CSV/SQLite; no automatic correction."""
from __future__ import annotations
from decimal import Decimal
from backend.operation_integrity import validar_campos, ErroIntegridadeFinanceira

LIMITE_DIVERGENCIA_ESTIMAVEL = Decimal("0.05")


def moedas_estimaveis(pendencias: list[dict]) -> tuple[set, set]:
    estimaveis, bloqueadas = set(), set()
    for issue in pendencias:
        (estimaveis if issue.get("estimavel") else bloqueadas).add(issue["moeda"])
    return estimaveis - bloqueadas, bloqueadas

def diagnosticar_operacoes(operacoes: list[dict]) -> list[dict]:
    """One actionable issue per non-conforming operation.

    It must never rewrite a value, infer fees, remove operations or cancel
    synchronization of unrelated legitimate records.
    """
    issues = []
    for indice, op in enumerate(operacoes, 1):
        try:
            validar_campos(op, indice)
        except ErroIntegridadeFinanceira as exc:
            delta = None
            estimavel = False
            try:
                if str(op.get("Moeda", "")).upper() not in ("USDT", "USDC"):
                    valor = Decimal(str(op["Valor_USDT"]))
                    qtd = Decimal(str(op["Quantidade"]))
                    preco = Decimal(str(op["Preco"]))
                    if all(x.is_finite() for x in (valor, qtd, preco)):
                        delta = qtd * preco - valor
                        estimavel = (
                            valor > 0 and qtd > 0 and preco > 0
                            and abs(delta) <= valor * LIMITE_DIVERGENCIA_ESTIMAVEL
                        )
            except (ArithmeticError, ValueError, KeyError, TypeError):
                pass
            if estimavel:
                try:
                    validar_campos(op, indice, conferir_relacao=False)
                except (ErroIntegridadeFinanceira, ArithmeticError, ValueError,
                        KeyError, TypeError):
                    estimavel = False
            issues.append({
                "operacao": indice,
                "moeda": str(op.get("Moeda", "")).upper(),
                "data": str(op.get("Data", "")),
                "erro": str(exc),
                "diferenca_usdt": delta,
                "estimavel": estimavel,
                "orientacao": (
                    "Confira extrato e comprovante de execução. "
                    "Se houver corretagem, documente separadamente; "
                    "não altere Valor_USDT nem invente taxa sem evidência."
                ),
            })
    return issues
