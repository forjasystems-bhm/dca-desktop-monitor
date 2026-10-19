from datetime import datetime
from decimal import Decimal
import unittest

from gui.janela_registro_logica import interpretar_cambio, interpretar_data_operacao

AGORA = datetime(2026, 10, 19, 14, 0, 0)


class DataOperacaoTests(unittest.TestCase):
    def test_empty_means_now(self):
        self.assertEqual(interpretar_data_operacao('', AGORA), '2026-10-19 14:00:00')

    def test_brazilian_and_iso_formats(self):
        casos = {
            '18/10/2026 19:30': '2026-10-18 19:30:00',
            '18/10/2026 19:30:32': '2026-10-18 19:30:32',
            '18/10/2026': '2026-10-18 12:00:00',
            '2026-10-18 19:30:32': '2026-10-18 19:30:32',
            '2026-10-18': '2026-10-18 12:00:00',
            '  18/10/2026   19:30 ': '2026-10-18 19:30:00',
        }
        for texto, esperado in casos.items():
            self.assertEqual(interpretar_data_operacao(texto, AGORA), esperado)

    def test_future_and_invalid_dates_are_rejected(self):
        for texto in ('20/10/2026 10:00', '31/02/2026', '18-10-2026', 'ontem'):
            with self.assertRaises(ValueError):
                interpretar_data_operacao(texto, AGORA)


class CambioTests(unittest.TestCase):
    def test_empty_means_current_quote(self):
        self.assertIsNone(interpretar_cambio(''))

    def test_comma_and_dot(self):
        self.assertEqual(interpretar_cambio('5,26'), Decimal('5.26'))
        self.assertEqual(interpretar_cambio('5.2592'), Decimal('5.2592'))

    def test_invalid_rates_are_rejected(self):
        for texto in ('abc', '0', '1', '1,10', '-5', 'nan', 'inf'):
            with self.assertRaises(ValueError):
                interpretar_cambio(texto)


if __name__ == '__main__':
    unittest.main()
