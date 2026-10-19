import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
class PersistentConfigurationTests(unittest.TestCase):
    def test_f16_changes_are_in_user_data_not_application_package(self):
        from config.carregar_json import _get_config_path,_carregar_config,salvar_config
        with TemporaryDirectory() as folder,patch.dict(os.environ,{'DCA_MONITOR_DATA_DIR':folder}):
            path=_get_config_path()
            self.assertEqual(path.parent,Path(folder).resolve())
            config=_carregar_config();config['moedas']=['BTC','USDT']
            salvar_config(config)
            self.assertEqual(_carregar_config()['moedas'],['BTC','USDT'])
