from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend.distribution_policy import (
    exigir_autorizacao_distribuicao, verificar_workflows,
)

class DistributionTests(unittest.TestCase):
    def test_source_line_has_no_unapproved_packaging_or_release(self):
        verificar_workflows(Path(__file__).resolve().parent.parent)
        with self.assertRaisesRegex(RuntimeError,'bloqueada'):
            exigir_autorizacao_distribuicao()

    def test_accidental_packaging_workflow_is_rejected(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'.github'/'workflows';folder.mkdir(parents=True)
            (folder/'unsafe.yml').write_text('steps:\n  - run: python -m PyInstaller main.pyw\n')
            with self.assertRaisesRegex(RuntimeError,'não autorizado'):
                verificar_workflows(root)

    def test_same_name_without_strict_preview_marker_is_rejected(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'.github'/'workflows';folder.mkdir(parents=True)
            (folder/'windows-homologation-preview.yml').write_text(
                'steps:\n  - run: python -m PyInstaller main.pyw\n'
            )
            with self.assertRaisesRegex(RuntimeError,'não autorizado'):
                verificar_workflows(root)

    def test_even_preview_cannot_publish_github_release(self):
        source = (Path(__file__).resolve().parent.parent/'.github'
                  /'workflows'/'windows-homologation-preview.yml')
        with TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'.github'/'workflows';folder.mkdir(parents=True)
            (folder/source.name).write_text(
                source.read_text(encoding='utf-8') +
                '\n  - run: gh release create v1.0.0\n',
                encoding='utf-8',
            )
            with self.assertRaisesRegex(RuntimeError,'não autorizada'):
                verificar_workflows(root)
