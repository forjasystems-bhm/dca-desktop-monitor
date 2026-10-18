"""OPS-01: startup from trusted local records; market data is never a prerequisite."""
from __future__ import annotations


class FalhaInicializacaoLocal(RuntimeError):
    """Local data are unavailable or integrity/provenance checks failed."""


def abrir_carteira_local(*, data_factory=None, price_factory=None):
    """Return (DataManager, PriceManager) without any network request.

    Injection points keep the offline boot contract testable without opening Tk.
    A failed integrity check blocks boot instead of showing an empty portfolio.
    """
    if data_factory is None:
        from backend.backend import DataManager
        data_factory = DataManager
    if price_factory is None:
        from backend.backend import PriceManager
        price_factory = PriceManager

    data_mgr = data_factory()
    diagnostico = data_mgr._store.diagnostico_integridade()
    if diagnostico.get("status") != "OK":
        raise FalhaInicializacaoLocal(
            "Falha de integridade dos dados ou backup. "
            "Nenhum registro foi apagado ou substituído. "
            "Confira o banco SQLite e a cópia do CSV antes de continuar."
        )
    # Must not call .atualizar_precos(), .fetch_ticker(), or historical API.
    price_mgr = price_factory()
    return data_mgr, price_mgr
