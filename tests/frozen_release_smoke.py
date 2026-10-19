"""Extract final archive, run its actual GUI, close gracefully and reopen."""
from contextlib import closing
from pathlib import Path
import json
import os
import platform
import secrets
import sqlite3
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_archive import archive_name,extract_verified,digest
from backend.backend import DataManager


def main():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    archive=ROOT/archive_name()
    line=(ROOT/(archive.name+'.sha256')).read_text().split()
    assert line==[digest(archive),archive.name], 'Archive checksum mismatch'
    proofs=[]
    with tempfile.TemporaryDirectory(prefix='dca-release-smoke-') as temp:
        base=Path(temp)
        bundle,manifest=extract_verified(archive,base/'clean-extraction',commit=commit)
        binary=bundle/('DCA-Monitor.exe' if platform.system()=='Windows' else 'DCA-Monitor')
        assert binary.is_file()
        data=base/'isolated-wallet';data.mkdir()
        token=secrets.token_hex(16)
        (data/'package-test-owner.json').write_text(json.dumps({'token':token}))
        env=os.environ.copy();env['DCA_MONITOR_DATA_DIR']=str(data)
        for cycle in range(2):
            proof_path=data/'package-test-result.json';proof_path.unlink(missing_ok=True)
            output=base/f'cycle-{cycle}.log'
            with output.open('wb') as log:
                child=subprocess.Popen([str(binary),'--distribution-self-test',token],
                    cwd=str(base),env=env,stdout=log,stderr=subprocess.STDOUT)
                try:
                    if child.wait(timeout=90)!=0:raise RuntimeError('Frozen app exited with error')
                except BaseException:
                    # Forced cleanup is an error path, never normal-exit evidence.
                    if platform.system()=='Windows':
                        subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=15)
                    elif child.poll() is None:child.kill()
                    child.wait(timeout=15)
                    raise
            text=output.read_text(errors='replace')
            if any(marker in text for marker in ('Traceback','RuntimeError:','Exception in Tkinter','Exception in thread')):
                raise RuntimeError('Packaged runtime error: '+text[-4000:])
            proof=json.loads(proof_path.read_text(encoding='utf-8'))
            assert all(proof.get(k) for k in ('ready','closed','tcl_present','tk_present')),proof
            assert not proof['errors'],proof
            with closing(sqlite3.connect(data/'portfolio.sqlite3')) as conn:
                assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                rows=conn.execute('SELECT quantidade FROM operacoes ORDER BY id').fetchall()
                assert rows==([] if cycle==0 else [('10.123456789123456789',)]),rows
            proofs.append(proof)
            if cycle==0:
                dm=DataManager(data_dir=data,auto_import_legacy=False)
                assert dm.salvar_operacao(['2026-01-01 12:00:00','USDT','compra',
                    '10.123456789123456789','5','10.123456789123456789','5'])
                (data/'app-settings.json').write_text('{"minimizar_para_bandeja":false}')
        assert json.loads((data/'app-settings.json').read_text())=={'minimizar_para_bandeja':False}
        result=dict(commit=commit,archive=archive.name,sha256=digest(archive),
                    manifest_commit=manifest['commit'],cycles=proofs,
                    normal_shutdown=True,sqlite_preserved=True)
        (ROOT/('release-smoke-proof-'+platform.system()+'.json')).write_text(json.dumps(result,indent=2))
    print('RELEASE_CLEAN_EXTRACTION=PASS')
    print('RELEASE_TCL_TK_REAL_GUI=PASS')
    print('RELEASE_GRACEFUL_CLOSE_AND_REOPEN=PASS')
    print('RELEASE_PRECISE_SQLITE_PRESERVATION=PASS')


if __name__=='__main__':main()
