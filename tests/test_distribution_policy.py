from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend.distribution_policy import exigir_autorizacao_distribuicao,verificar_workflows
class DistributionTests(unittest.TestCase):
    def test_source_line_has_no_executable_or_release_workflow(self):
        verificar_workflows(Path(__file__).resolve().parent.parent)
        with self.assertRaisesRegex(RuntimeError,'bloqueada'):
            exigir_autorizacao_distribuicao()
    def test_accidental_packaging_workflow_is_rejected(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'.github'/'workflows';folder.mkdir(parents=True)
            (folder/'unsafe.yml').write_text('steps:\n  - run: python -m PyInstaller main.pyw\n')
            with self.assertRaisesRegex(RuntimeError,'não autorizado'):verificar_workflows(root)
