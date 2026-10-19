"""Immutable package defaults plus an atomic user-owned configuration."""
import json
import logging
import os
from pathlib import Path
import tempfile
from backend.storage_sqlite import diretorio_dados_padrao
logger=logging.getLogger(__name__)
DEFAULT_PATH=Path(__file__).resolve().parent/'config.json'

def salvar_config(config):
    if not isinstance(config,dict) or not isinstance(config.get('moedas'),list) or not config['moedas']:
        raise ValueError('Configuração de moedas inválida.')
    path=diretorio_dados_padrao()/'user-config.json';path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.config-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(config,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
    finally:Path(temp).unlink(missing_ok=True)

def _get_config_path():
    path=diretorio_dados_padrao()/'user-config.json'
    if not path.exists():
        # Existing package settings are copied once; the shipped file is never
        # rewritten. Source/preview/installed apps follow the same data policy.
        salvar_config(json.loads(DEFAULT_PATH.read_text(encoding='utf-8-sig')))
    return path

def _carregar_config():
    data=json.loads(_get_config_path().read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('moedas'),list):
        raise ValueError('Configuração local inválida; restaure a cópia verificada.')
    return data

def _carregar_moedas_config():return ['Todas']+_carregar_config().get('moedas',[])
def _carregar_cores_moedas():return _carregar_config().get('cores_moedas',{})
