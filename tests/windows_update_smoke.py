"""Real packaged updater, backup, fresh GUI handshake and native Desktop shortcut.

Only an isolated synthetic wallet and GitHub-hosted runner Desktop are used.
The old-version argument models the requesting version; both helper and candidate
are the newly built binary. This is not a claim that the 1.0.0 binary can update.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
from contextlib import closing
import json
import os
import subprocess
import sys
import sqlite3
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app_lifecycle import APP_VERSION
from backend.backend import DataManager
from backend.update_install import preparar_instalacao, sha256


def carteira(path):
    # Existing startup reasserts PRAGMA user_version, changing the SQLite change
    # counter (header bytes 27/95), even when schema and every row are identical.
    # Compare the COMPLETE logical database, including audit/identity/sequences.
    with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()==('ok',)
        return list(conn.iterdump()),conn.execute('PRAGMA user_version').fetchone()


def fechar_janela(pid):
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def close(hwnd,_):
        owner=wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and ctypes.windll.user32.IsWindowVisible(hwnd):
            ctypes.windll.user32.PostMessageW(hwnd,0x0010,0,0)
        return True
    ctypes.windll.user32.EnumWindows(callback_type(close),0)


def main():
    assert sys.platform=='win32'
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    archive=ROOT/f'DCA-Monitor-v{APP_VERSION}-Windows-x64.zip'
    source=ROOT/'dist/DCA-Monitor/DCA-Monitor.exe'
    with tempfile.TemporaryDirectory(prefix='dca-update-real-') as temp:
        root=Path(temp).resolve()/'Carteira João'
        root.mkdir()
        local=root/'local';local.mkdir()
        env={**os.environ,'LOCALAPPDATA':str(local)}
        dm=DataManager(data_dir=root/'wallet',auto_import_legacy=False)
        assert dm.salvar_operacao(['2026-01-01 12:00:00','USDT','compra',
                                  '10.123456789123456789','5','10.123456789123456789','5'])
        bank_before=carteira(dm.arquivo_db)
        name=archive.name
        info=dict(download_disponivel=True,versao_publicada=APP_VERSION,pacote=dict(
            nome=name,url=f'https://github.com/tiolusystems/dca-desktop-monitor/releases/download/v{APP_VERSION}/{name}',
            tamanho=archive.stat().st_size,sha256=sha256(archive)))
        plan=preparar_instalacao(info,archive,dm.arquivo_db,
             version_atual='1.0.0',raiz=local/'Programs/DCA-Monitor/versions',origem=source)
        action=Path(plan['acao'])
        process=subprocess.Popen([str(source),'--maintenance-update',str(action)],env=env,cwd=source.parent)
        shortcut=None;candidate=None;receipt=None;reopened=None
        try:
            assert process.wait(timeout=150)==0,action.read_text(encoding="utf-8")
            receipt=json.loads(action.read_text(encoding="utf-8"))
            assert receipt['state']=='installed',receipt
            candidate=kernel.OpenProcess(0x100000|0x1000,False,receipt['pid'])
            assert candidate
            shortcut=Path(receipt['shortcut']['atalho'])
            assert Path(receipt['backup']['pacote']).is_file()
            assert carteira(dm.arquivo_db)==bank_before
            assert shortcut.is_file()
            # Inspect the real .lnk via the same native COM API Explorer uses.
            quote=str(shortcut).replace("'","''")
            inspection=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
                "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "+
                "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('"+quote+
                "'); @{target=$s.TargetPath;icon=$s.IconLocation;arguments=$s.Arguments} | ConvertTo-Json -Compress"],
                capture_output=True,text=True,encoding='utf-8',check=True,timeout=20)
            link=json.loads(inspection.stdout)
            expected=str(Path(plan['destino'])/'DCA-Monitor.exe')
            assert link['target']==expected,link
            assert link['icon'].split(',')[0]==expected,link
            assert not link['arguments'],link
            # Close the real new GUI normally; never terminate it as success evidence.
            fechar_janela(receipt['pid'])
            assert ctypes.windll.kernel32.WaitForSingleObject(candidate,30000)==0
            assert carteira(dm.arquivo_db)==bank_before
            print('WINDOWS_REAL_UPDATE_BACKUP_GUI_RECEIPT_SHORTCUT=PASS')
            print('WINDOWS_REAL_UPDATE_PRECISE_SQLITE_AND_NORMAL_CLOSE=PASS')
            # A regular launch also exercises the first-run automatic shortcut,
            # without the synthetic-wallet suppression used by archive smoke.
            reopened=subprocess.Popen([expected],cwd=Path(expected).parent,
                env={**env,'DCA_MONITOR_DATA_DIR':str(dm.arquivo_db.parent)})
            marker=dm.arquivo_db.parent/'desktop-setup.json'
            deadline=time.monotonic()+60
            while not marker.is_file() and time.monotonic()<deadline:
                assert reopened.poll() is None,'Regular launch exited early'
                time.sleep(.25)
            assert marker.is_file(),'Automatic Desktop shortcut did not run'
            assert json.loads(marker.read_text('utf-8'))['criado']
            fechar_janela(reopened.pid)
            assert reopened.wait(timeout=30)==0
            assert carteira(dm.arquivo_db)==bank_before
            print('WINDOWS_REAL_FIRST_RUN_AUTOMATIC_SHORTCUT_AND_REOPEN=PASS')
        finally:
            if reopened and reopened.poll() is None:
                fechar_janela(reopened.pid)
                try:reopened.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    reopened.kill();reopened.wait()  # FAILED test cleanup only
            if candidate:
                if kernel.WaitForSingleObject(candidate,0)!=0:
                    fechar_janela(receipt['pid'])
                    if kernel.WaitForSingleObject(candidate,10000)!=0:
                        # Only after a FAILED assertion; never evidence of graceful exit.
                        subprocess.run(['taskkill','/PID',str(receipt['pid']),'/T','/F'],
                                       capture_output=True,timeout=15)
                kernel.CloseHandle(candidate)
            if process.poll() is None:
                process.kill();process.wait()  # failure cleanup only
            if shortcut and shortcut.is_file():shortcut.unlink()


if __name__=='__main__':main()
