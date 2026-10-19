"""Distribution remains blocked; only a user-authorized test artifact is permitted."""
PACKAGING_AUTHORIZED = False
PREVIEW_WORKFLOW = "windows-homologation-preview.yml"

def exigir_autorizacao_distribuicao():
    if not PACKAGING_AUTHORIZED:
        raise RuntimeError('Distribuição bloqueada: autorização independente e revisão humana obrigatórias.')

def verificar_workflows(root):
    """Reject releases/installers and packaging outside the scoped personal QA job.

    F19 administrative rulesets remain a separate gate; this is not global
    branch protection. The exception produces a temporary, unsigned personal
    preview artifact only, without GitHub Release or installer.
    """
    import re
    from pathlib import Path
    packaging = re.compile(
        r'pyinstaller|nuitka|cx_freeze|iscc|makensis', re.I
    )
    publishing = re.compile(
        r'gh\s+release\s+create|action-gh-release|upload-release-asset|softprops/',
        re.I,
    )
    required = (
        "name: Windows downloadable homologation preview",
        "  pull_request:",
        "contents: read",
        "DCA-PREVIEW-MODE",
        "DCA-Monitor-PREVIEW",
        "actions/upload-artifact@v4",
        "test/dca-windows-download-preview",
        "8c13295aaac2ac4bcb98ead1723e713a8ae42eb2",
    )
    for path in (Path(root)/'.github'/'workflows').glob('*.y*ml'):
        source = path.read_text(encoding='utf-8')
        active = '\n'.join(line for line in source.splitlines()
                           if not line.lstrip().startswith('#'))
        if publishing.search(active):
            raise RuntimeError('Publicação não autorizada: ' + str(path))
        if packaging.search(active):
            if path.name != PREVIEW_WORKFLOW or not all(
                mark in active for mark in required
            ):
                raise RuntimeError('Workflow de distribuição não autorizado: ' + str(path))
