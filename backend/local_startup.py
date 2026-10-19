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
        # A distribuição não deve importar um CSV empacotado, de exemplo,
        # nem presumir onde ficava a versão antiga. O usuário escolhe o arquivo.
        data_factory = lambda: DataManager(auto_import_legacy=False)
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
    # Backup diário verificado antes de disponibilizar o banco ao usuário.
    from backend.backup_policy import garantir_backup_diario
    garantir_backup_diario(data_mgr.arquivo_db)
    # Must not call .atualizar_precos(), .fetch_ticker(), or historical API.
    price_mgr = price_factory()
    return data_mgr, price_mgr
