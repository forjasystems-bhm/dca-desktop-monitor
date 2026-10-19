"""Distribution stays locked until an independently reviewed policy change."""
PACKAGING_AUTHORIZED = False

def exigir_autorizacao_distribuicao():
    if not PACKAGING_AUTHORIZED:
        raise RuntimeError('Distribuição bloqueada: autorização independente e revisão humana obrigatórias.')

def verificar_workflows(root):
    """The consolidation line only tests Python sources and captures UI evidence."""
    import re
    from pathlib import Path
    forbidden=re.compile(r'pyinstaller|nuitka|cx_freeze|iscc|makensis|gh\s+release\s+create|action-gh-release|upload-release-asset|softprops/',re.I)
    for path in (Path(root)/'.github'/'workflows').glob('*.y*ml'):
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.lstrip().startswith('#') and forbidden.search(line):
                raise RuntimeError('Workflow de distribuição não autorizado: '+str(path))
