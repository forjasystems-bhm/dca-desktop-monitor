"""OPS-02: second invocation must not create another GUI/price loop."""
from pathlib import Path
import tempfile
import unittest

from backend.single_instance import OutraInstanciaAberta,TravaInstancia


class InstanciaUnicaTests(unittest.TestCase):
    def test_two_lock_handles_for_same_data_dir_are_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            first=TravaInstancia(Path(d))
            second=TravaInstancia(Path(d))
            first.adquirir()
            try:
                self.assertTrue(first.ativa)
                with self.assertRaises(OutraInstanciaAberta):
                    second.adquirir()
                self.assertFalse(second.ativa)
            finally:
                first.liberar()
            second.adquirir()
            self.assertTrue(second.ativa)
            second.liberar()
            self.assertFalse(second.ativa)

    def test_different_user_data_directories_do_not_share_lock(self):
        with tempfile.TemporaryDirectory() as d:
            a=TravaInstancia(Path(d)/"pessoa_a")
            b=TravaInstancia(Path(d)/"pessoa_b")
            with a,b:
                self.assertTrue(a.ativa)
                self.assertTrue(b.ativa)

    def test_second_acquire_same_handle_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            one=TravaInstancia(Path(d))
            one.adquirir()
            one.adquirir()
            self.assertTrue(one.ativa)
            one.liberar()
            one.liberar()


if __name__=="__main__":
    unittest.main()
