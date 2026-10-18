"""FIN-03: validação financeira centralizada de operações e cadeia temporal.

Somente novos lançamentos/edições/exclusões passam pelo portão estrito.
O CSV legado permanece preservado e pode ser conciliado sem adulteração automática.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")
CENTAVO_USDT = Decimal("0.01")
TOL_QUANTIDADE = Decimal("0.00000001")
COLUNAS = ("Data", "Moeda", "Operacao", "Valor_USDT", "Preco", "Quantidade", "Taxa_BRL")


class ErroIntegridadeFinanceira(ValueError):
    """Uma operação tornaria o livro de operações inconsistente."""


def _numero(registro: dict, campo: str, linha: int, *, positivo=True) -> Decimal:
    try:
        numero = Decimal(str(registro[campo]).strip())
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ErroIntegridadeFinanceira(
            f"Operação {linha}: campo {campo} inválido."
        ) from exc
    if not numero.is_finite() or (numero <= ZERO if positivo else numero < ZERO):
        raise ErroIntegridadeFinanceira(
            f"Operação {linha}: {campo} deve ser "
            + ("positivo." if positivo else "não negativo.")
        )
    return numero


def validar_campos(registro: dict, linha: int) -> None:
    """Confere regra específica do CSV: USDT usa Preco como câmbio, não preço unitário."""
    moeda = str(registro.get("Moeda", "")).strip().upper()
    if not moeda or not moeda.isascii() or not moeda.isalnum():
        raise ErroIntegridadeFinanceira(f"Operação {linha}: moeda inválida.")
    tipo = str(registro.get("Operacao", "")).strip().lower()
    if tipo not in ("compra", "venda"):
        raise ErroIntegridadeFinanceira(f"Operação {linha}: tipo inválido.")
    try:
        datetime.strptime(str(registro["Data"]), "%Y-%m-%d %H:%M:%S")
    except (ValueError, KeyError, TypeError) as exc:
        raise ErroIntegridadeFinanceira(f"Operação {linha}: data/hora inválida.") from exc

    valor = _numero(registro, "Valor_USDT", linha)
    preco = _numero(registro, "Preco", linha)
    quantidade = _numero(registro, "Quantidade", linha)
    _numero(registro, "Taxa_BRL", linha, positivo=False)

    if moeda == "USDT":
        # Registro de depósito/saque de USDT: Preco contém USDT/BRL.
        if abs(quantidade - valor) > TOL_QUANTIDADE:
            raise ErroIntegridadeFinanceira(
                f"Operação {linha}: USDT exige Quantidade igual a Valor_USDT. "
                "Preço é a cotação USDT/BRL, não se multiplica pela quantidade."
            )
    elif moeda == "USDC":
        # Cadastro legado é aceito em modo de leitura, mas o modelo de
        # compensação USDC exige uma decisão explícita na FIN-04.
        raise ErroIntegridadeFinanceira(
            f"Operação {linha}: novas alterações em USDC aguardam "
            "a regra contábil FIN-04. Operações históricas permanecem preservadas."
        )
    else:
        # A UI arredonda a quantidade; tolera apenas 1 centavo ou
        # o efeito máximo de arredondar 8 casas decimais.
        diferenca = abs(quantidade * preco - valor)
        # A tolerância nunca supera 0,01% do valor: evita que operações
        # pequenas ou preços unitários extremos admitam desvio material.
        limite = min(
            max(CENTAVO_USDT, preco * TOL_QUANTIDADE),
            max(TOL_QUANTIDADE, valor * Decimal("0.0001")),
        )
        if diferenca > limite:
            raise ErroIntegridadeFinanceira(
                f"Operação {linha} ({moeda}): Valor_USDT divergente. "
                "Deve corresponder a Quantidade × Preço unitário. "
                f"Diferença: {diferenca} USDT (tolerância: {limite} USDT)."
            )


def validar_livro(operacoes: list[dict]) -> None:
    """Valida TODOS os saldos em ordem temporal antes de confirmar a transação.

    Rejeita saldo USDT negativo, venda de quantidade não possuída e operações
    inválidas em qualquer ponto — inclusive decorrentes de editar o passado.
    """
    registros = []
    for posicao, op in enumerate(operacoes, 1):
        validar_campos(op, posicao)
        registros.append((str(op["Data"]), posicao, op))
    registros.sort(key=lambda x: (x[0], x[1]))

    caixa = ZERO
    posicoes = defaultdict(lambda: ZERO)
    for _, indice, op in registros:
        moeda = str(op["Moeda"]).strip().upper()
        tipo = str(op["Operacao"]).strip().lower()
        valor = Decimal(str(op["Valor_USDT"]))
        qtd = Decimal(str(op["Quantidade"]))
        if moeda == "USDT":
            caixa += valor if tipo == "compra" else -valor
        elif tipo == "compra":
            caixa -= valor
            posicoes[moeda] += qtd
        else:
            posicoes[moeda] -= qtd
            if posicoes[moeda] < ZERO:
                raise ErroIntegridadeFinanceira(
                    f"Operação {indice} ({moeda}, {op['Data']}): "
                    "venda superior à posição disponível nessa data."
                )
            caixa += valor
        if caixa < ZERO:
            raise ErroIntegridadeFinanceira(
                f"Operação {indice} ({moeda}, {op['Data']}): "
                f"saldo USDT negativo ({caixa}). Registre ou corrija "
                "o aporte anterior antes de continuar."
            )
