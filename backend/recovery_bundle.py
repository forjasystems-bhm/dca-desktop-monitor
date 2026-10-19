"""Portable verified DCA recovery into a NEW directory; never overwrite data."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from backend.backup_sqlite import criar_backup_sqlite
from backend.database_identity import validar_banco_dca

CONFIGS=('app-settings.json','user-config.json')
ALLOWED={'portfolio.sqlite3','original.csv',*CONFIGS}
def digest(data):return hashlib.sha256(data).hexdigest()

def exportar_pacote(banco,destino):
    db=Path(banco).resolve();out=Path(destino).resolve()
    if out.exists():raise RuntimeError('Pacote de destino já existe; não sobrescrever.')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.dca-package-') as tmp:
        tmp=Path(tmp);snapshot=criar_backup_sqlite(db,tmp)
        copied=Path(snapshot['backup']);identity=validar_banco_dca(copied)
        data={'portfolio.sqlite3':copied.read_bytes()}
        with closing(sqlite3.connect(copied)) as conn:
            origins=conn.execute('SELECT sha256,caminho_backup FROM importacoes_legadas').fetchall()
        if len(origins)>1:raise RuntimeError('Proveniência CSV ambígua.')
        if origins:
            sha,path=origins[0];content=Path(path).read_bytes()
            if digest(content)!=sha:raise RuntimeError('CSV auditável divergente.')
            data['original.csv']=content
        for name in CONFIGS:
            file=db.parent/name
            if file.is_file():
                content=file.read_bytes();json.loads(content);data[name]=content
        manifest={'formato':'DCA-RECOVERY-1',**identity,
                  'gerado_em_utc':datetime.now(timezone.utc).isoformat(),
                  'arquivos':{n:digest(b) for n,b in data.items()}}
        temp=tmp/'bundle.zip'
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
            for name,content in data.items():archive.writestr(name,content)
        with temp.open('rb+') as stream:os.fsync(stream.fileno())
        os.link(temp,out)
    return {'pacote':str(out),'sha256':digest(out.read_bytes()),'uuid':identity['uuid']}

def recuperar_pacote(pacote,destino):
    target=Path(destino).resolve()
    if target.exists():raise RuntimeError('Recuperação requer uma pasta NOVA.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent,prefix='.dca-recover-') as tmp:
        stage=Path(tmp)
        with zipfile.ZipFile(pacote) as archive:
            names=archive.namelist()
            if (len(names)!=len(set(names)) or set(names)-ALLOWED-{'manifest.json'}
                or 'manifest.json' not in names or any(i.file_size>512*1024*1024 for i in archive.infolist())):
                raise RuntimeError('Estrutura do pacote inválida.')
            manifest=json.loads(archive.read('manifest.json'))
            if manifest.get('formato')!='DCA-RECOVERY-1' or set(names)!=(set(manifest['arquivos'])|{'manifest.json'}):
                raise RuntimeError('Manifesto do pacote inválido.')
            for name,sha in manifest['arquivos'].items():
                content=archive.read(name)
                if digest(content)!=sha:raise RuntimeError('Hash divergente: '+name)
                (stage/name).write_bytes(content)
        db=stage/'portfolio.sqlite3';identity=validar_banco_dca(db,carteira_esperada=manifest['uuid'])
        with closing(sqlite3.connect(db)) as conn:
            records=conn.execute('SELECT sha256 FROM importacoes_legadas').fetchall()
            if records:
                original=stage/'original.csv'
                if not original.is_file() or len(records)!=1 or digest(original.read_bytes())!=records[0][0]:
                    raise RuntimeError('Pacote sem CSV auditável obrigatório.')
                path=str(target/'original.csv')
                conn.execute('UPDATE importacoes_legadas SET caminho_origem=?,caminho_backup=?',(path,path));conn.commit()
        for name in CONFIGS:
            if (stage/name).exists():json.loads((stage/name).read_text(encoding='utf-8'))
        (stage/'data-identity.json').write_text(json.dumps(
            {'formato':'DCA-DATA-IDENTITY-1','banco':'portfolio.sqlite3','uuid':identity['uuid']}),encoding='utf-8')
        (stage/'recovery-receipt.json').write_text(json.dumps({'manifesto_original':manifest,
            'banco_remapeado_sha256':digest(db.read_bytes()),
            'nota':'Somente caminhos de proveniência remapeados; registros financeiros preservados.'},ensure_ascii=False),encoding='utf-8')
        target.mkdir()  # exclusive; never merge into an existing installation
        (target/"RECOVERY-INCOMPLETE").write_text("Recuperação ainda não concluída",encoding="utf-8")
        for file in stage.iterdir():
            with file.open('rb') as source,(target/file.name).open('xb') as output:
                for chunk in iter(lambda:source.read(1024*1024),b''):output.write(chunk)
                output.flush();os.fsync(output.fileno())
        (target/"RECOVERY-INCOMPLETE").unlink()
    return {'diretorio':str(target),'uuid':identity['uuid'],'ativado':False}
