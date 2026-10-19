"""Read-only DCA schema and wallet identity checks used before recovery."""
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import UUID

# Mandatory financial records; optional future tables must not replace them.
REQUIRED = {
    'operacoes': {'id','data','moeda','operacao','valor_usdt','preco','quantidade','taxa_brl','taxa_corretagem_usdt'},
    'importacoes_legadas': {'sha256','caminho_origem','caminho_backup','quantidade_registros'},
    'cotacoes_historicas': {'data_utc','ativo','preco','fonte'},
    'posicoes_iniciais': {'id','data_posicao','moeda','quantidade','custodia','custo_total_usdt'},
    'posicoes_externas': {'id','data_posicao','moeda','quantidade','custodia','custo_total_usdt'},
    'ajustes_posicoes': {'antes_json','depois_json','motivo','alterado_em_utc'},
    'movimentacoes_custodia': {'id','data_utc','tipo','moeda','origem','destino','quantidade','taxa_ativo','receita_usdt','taxa_usdt','comando_id'},
    'auditoria_operacoes': {'operacao_id','acao','antes_json','depois_json','motivo','operador','alterado_em_utc'},
    'versoes_resultados': {'identidade','data_utc','regras','insumos_json','resultado_json','emitido_em_utc'},
    'identidade_carteira': {'id','uuid'},
}

def validar_banco_dca(arquivo, *, carteira_esperada=None, permitir_antigo=False):
    from backend.storage_sqlite import SCHEMA_VERSION
    path=Path(arquivo).resolve()
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
            version=conn.execute('PRAGMA user_version').fetchone()[0]
            if version != SCHEMA_VERSION and not (permitir_antigo and 8 <= version < SCHEMA_VERSION):
                raise RuntimeError('Backup DCA com versão incompatível; requer migração assistida.')
            for table, required in REQUIRED.items():
                if version < 9 and table == 'auditoria_operacoes':continue
                if version < 10 and table == 'versoes_resultados':continue
                columns={row[1] for row in conn.execute('PRAGMA table_info('+table+')')}
                if not required <= columns:
                    raise RuntimeError('Estrutura DCA inválida: '+table)
            rows=conn.execute('SELECT uuid FROM identidade_carteira WHERE id=1').fetchall()
            if len(rows)!=1:
                raise RuntimeError('Identidade da carteira DCA ausente.')
            identity=str(UUID(rows[0][0]))
            if carteira_esperada is not None and identity != carteira_esperada:
                raise RuntimeError('Backup pertence a outra carteira DCA.')
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise RuntimeError('Integridade SQLite DCA inválida.')
            return {'uuid':identity,'schema':version}
    except (sqlite3.Error,ValueError,OSError) as exc:
        raise RuntimeError('Não foi possível verificar a identidade/estrutura DCA: '+str(exc)) from exc
