from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

_FORMATOS_DATA = (
    ("%d/%m/%Y %H:%M:%S", False), ("%d/%m/%Y %H:%M", False), ("%d/%m/%Y", True),
    ("%Y-%m-%d %H:%M:%S", False), ("%Y-%m-%d %H:%M", False), ("%Y-%m-%d", True),
)


def interpretar_data_operacao(texto: str, agora: datetime) -> str:
    texto = " ".join(texto.split())
    if not texto:
        return agora.strftime("%Y-%m-%d %H:%M:%S")
    for formato, so_dia in _FORMATOS_DATA:
        try:
            data = datetime.strptime(texto, formato)
        except ValueError:
            continue
        if so_dia:
            data = data.replace(hour=12)
        if data > agora:
            raise ValueError("A data da operação não pode estar no futuro.")
        return data.strftime("%Y-%m-%d %H:%M:%S")
    raise ValueError("Data inválida. Use DD/MM/AAAA HH:MM, por exemplo 18/10/2026 19:30.")


def interpretar_cambio(texto: str) -> Optional[Decimal]:
    texto = texto.strip().replace(",", ".")
    if not texto:
        return None
    try:
        cambio = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError("Dólar inválido. Use o valor em reais, por exemplo 5,26.") from exc
    if not cambio.is_finite() or cambio <= Decimal("1.1"):
        raise ValueError("Dólar inválido. Use o valor em reais, por exemplo 5,26.")
    return cambio
