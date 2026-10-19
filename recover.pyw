"""Explicit offline maintenance; never opens or creates the operational DB."""
from backend.restore_command import executar_assistente_recuperacao
if __name__ == '__main__':
    executar_assistente_recuperacao()
