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
TOL_VENDA_TOTAL = Decimal("0.005")
COLUNAS = ("Data", "Moeda", "Operacao", "Valor_USDT", "Preco", "Quantidade", "Taxa_BRL")


class ErroIntegridadeFinanceira(ValueError):
    """Uma operação tornaria o livro de operações inconsistente."""


def venda_excede_posicao(posicao: Decimal, quantidade: Decimal) -> bool:
    return quantidade - posicao > quantidade * TOL_VENDA_TOTAL


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


def validar_campos(registro: dict, linha: int, *, conferir_relacao=True) -> None:
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
    from backend.trading_fees import taxa_da_operacao, ErroTaxaOperacional
    try:
        taxa_da_operacao(registro)
    except ErroTaxaOperacional as exc:
        raise ErroIntegridadeFinanceira(f"Operação {linha}: {exc}") from exc

    if moeda in ("USDT", "USDC"):
        # Transferência externa; Preco é o câmbio BRL da moeda informada,
        # nunca preço USDT de USDC. Valor_USDT é nominal legado para USDC.
        if abs(quantidade - valor) > TOL_QUANTIDADE:
            raise ErroIntegridadeFinanceira(
                f"Operação {linha}: {moeda} exige Quantidade igual a Valor_USDT "
                "nominal de transferência. Preço é cotação BRL informada, "
                "não uma conversão USDC/USDT."
            )
    elif conferir_relacao:
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


def validar_livro(operacoes: list[dict], saldos_iniciais: list[dict] | None = None,
                  *, divergencias_legadas=()) -> None:
    """Valida TODOS os saldos em ordem temporal antes de confirmar a transação.

    Rejeita saldo USDT negativo no fim de cada dia, venda de quantidade não
    possuída e operações inválidas — inclusive decorrentes de editar o passado.
    """
    registros = []
    for posicao, op in enumerate(operacoes, 1):
        validar_campos(op, posicao, conferir_relacao=posicao not in divergencias_legadas)
        registros.append((str(op["Data"]), posicao, op))
    registros.sort(key=lambda x: (x[0], x[1]))

    caixa = ZERO
    caixa_usdc = ZERO
    posicoes = defaultdict(lambda: ZERO)
    base_desconhecida = set()
    for inicial in saldos_iniciais or []:
        moeda = str(inicial["Moeda"]).upper()
        qtd = Decimal(str(inicial["Quantidade"]))
        if moeda == "USDT":
            caixa += qtd
        elif moeda == "USDC":
            caixa_usdc += qtd
        else:
            posicoes[moeda] += qtd
            if inicial.get("Custo_Total_USDT") is None:
                base_desconhecida.add(moeda)
    for ordem, (data_op, indice, op) in enumerate(registros):
        for inicial in saldos_iniciais or []:
            if str(op["Data"])[:10] < str(inicial["Data"])[:10]:
                raise ErroIntegridadeFinanceira(
                    f"Operação {indice}: data anterior ao saldo inicial declarado "
                    f"em {inicial['Data']}. Não retroagir movimentações sobre "
                    "uma posição que ainda não foi comprovada."
                )
        moeda = str(op["Moeda"]).strip().upper()
        tipo = str(op["Operacao"]).strip().lower()
        valor = Decimal(str(op["Valor_USDT"]))
        qtd = Decimal(str(op["Quantidade"]))
        from backend.trading_fees import taxa_da_operacao
        taxa = taxa_da_operacao(op)
        if moeda == "USDT":
            caixa += qtd if tipo == "compra" else -qtd
        elif moeda == "USDC":
            caixa_usdc += qtd if tipo == "compra" else -qtd
            if caixa_usdc < ZERO:
                raise ErroIntegridadeFinanceira(
                    f"Operação {indice} (USDC, {op['Data']}): "
                    f"saldo USDC negativo ({caixa_usdc}). "
                    "Depósitos USDC não são aportes USDT; concilie a origem."
                )
        elif tipo == "compra":
            caixa -= valor + taxa
            posicoes[moeda] += qtd
        else:
            if moeda in base_desconhecida:
                raise ErroIntegridadeFinanceira(
                    f"Operação {indice} ({moeda}): custo inicial não informado. "
                    "Antes de vender, documente o custo total do saldo inicial; "
                    "não inventar lucro ou custo zero."
                )
            if venda_excede_posicao(posicoes[moeda], qtd):
                raise ErroIntegridadeFinanceira(
                    f"Operação {indice} ({moeda}, {op['Data']}): "
                    "venda superior à posição disponível nessa data."
                )
            posicoes[moeda] -= qtd
            caixa += valor - taxa
        fim_do_dia = (ordem + 1 == len(registros)
                      or registros[ordem + 1][0][:10] != data_op[:10])
        if caixa < ZERO and fim_do_dia:
            raise ErroIntegridadeFinanceira(
                f"Operação {indice} ({moeda}, {op['Data']}): "
                f"saldo USDT negativo no fim do dia {data_op[:10]} ({caixa}). "
                "Registre ou corrija o aporte anterior antes de continuar."
            )
