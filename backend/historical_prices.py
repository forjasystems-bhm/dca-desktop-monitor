"""Cotações Binance fechadas em UTC, persistidas e rastreáveis.

Consulta retrospectiva nunca usa ticker/preço atual, nem aproximações silenciosas.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


class ErroCotacaoHistorica(ValueError):
    """Resposta histórica inválida, incompleta ou não disponível."""


def validar_data_encerrada(data_ref: date, hoje_utc: date | None = None) -> None:
    if not isinstance(data_ref, date) or isinstance(data_ref, datetime):
        raise ErroCotacaoHistorica("Informe uma data válida.")
    hoje = hoje_utc or datetime.now(timezone.utc).date()
    if data_ref >= hoje:
        raise ErroCotacaoHistorica(
            "Apenas datas UTC integralmente encerradas podem receber fechamento diário."
        )


def candle_binance_diario(
    exchange: Any, ativo: str, data_ref: date, *, hoje_utc: date | None = None
) -> dict:
    """Busca o fechamento OHLCV de UMA data UTC; recusa candle divergente.

    CCXT fetch_ohlcv normalmente retorna [abertura_ms, open, high, low, close, volume].
    A consulta usa o timestamp da abertura UTC, NÃO a cotação 'last' atual.
    """
    validar_data_encerrada(data_ref, hoje_utc)
    simbolo = str(ativo).strip().upper()
    if not simbolo or simbolo == "USDT" or not simbolo.isascii() or not simbolo.isalnum():
        raise ErroCotacaoHistorica(f"Ativo inválido ou sem par histórico: {ativo!r}.")
    inicio_ms = int(datetime.combine(data_ref, time.min, timezone.utc).timestamp() * 1000)
    par = f"{simbolo}/USDT"
    try:
        candles = exchange.fetch_ohlcv(par, timeframe="1d", since=inicio_ms, limit=1)
    except Exception as exc:
        raise ErroCotacaoHistorica(f"Não foi possível obter {par} em {data_ref}: {exc}") from exc
    if not isinstance(candles, (list, tuple)) or len(candles) != 1:
        raise ErroCotacaoHistorica(f"Sem candle diário confirmado de {par} em {data_ref}.")
    candle = candles[0]
    if not isinstance(candle, (list, tuple)) or len(candle) < 6:
        raise ErroCotacaoHistorica(f"Candle incompleto de {par}.")
    try:
        if int(candle[0]) != inicio_ms:
            raise ErroCotacaoHistorica(f"Candle de outra data para {par}; não interpolar.")
        close = Decimal(str(candle[4]))
        if not close.is_finite() or close <= 0:
            raise ErroCotacaoHistorica(f"Fechamento inválido de {par}.")
        volume = Decimal(str(candle[5]))
        if not volume.is_finite() or volume < 0:
            raise ErroCotacaoHistorica(f"Volume inválido de {par}.")
    except ErroCotacaoHistorica:
        raise
    except (ValueError, TypeError, InvalidOperation, OverflowError) as exc:
        raise ErroCotacaoHistorica(f"Resposta OHLCV inválida de {par}.") from exc
    return {
        "data_utc": data_ref.isoformat(),
        "ativo": simbolo,
        "moeda_cotacao": "USDT",
        "preco": str(close),
        "fonte": "Binance/CCXT:OHLCV:1d:close",
        "abertura_utc_ms": inicio_ms,
        "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
    }


def buscar_e_persistir_fechamentos(
    armazem: Any, exchange: Any, data_ref: date,
    ativos: list[str] | tuple[str, ...], *, hoje_utc: date | None = None
) -> int:
    """Busca somente cotações ausentes; confirma lote integral ou não grava nada."""
    validar_data_encerrada(data_ref, hoje_utc)
    nomes = sorted(set(str(m).strip().upper() for m in ativos if str(m).strip().upper() != "USDT"))
    if not nomes:
        return 0
    existentes = armazem.ler_cotacoes_historicas(data_ref)
    novos = [
        candle_binance_diario(exchange, nome, data_ref, hoje_utc=hoje_utc)
        for nome in nomes if nome not in existentes
    ]
    if novos:
        armazem.salvar_cotacoes_historicas(novos, hoje_utc=hoje_utc)
    return len(novos)
