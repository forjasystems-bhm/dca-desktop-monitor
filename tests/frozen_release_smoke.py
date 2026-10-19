"""Run a frozen real Windows/Linux binary against a disposable blank SQLite."""
from pathlib import Path
import os
import platform
import subprocess
import tempfile
import time
import sqlite3
from contextlib import closing

root = Path(__file__).resolve().parent.parent
is_win = platform.system() == "Windows"
binary = root/"dist"/"DCA-Monitor"/("DCA-Monitor.exe" if is_win else "DCA-Monitor")
if not binary.is_file():
    raise RuntimeError("DCA packaged binary absent")
with tempfile.TemporaryDirectory(prefix="dca-release-smoke-") as temp:
    data=Path(temp)/"wallet"
    env=os.environ.copy()
    env["DCA_MONITOR_DATA_DIR"]=str(data)
    child=subprocess.Popen([str(binary)],cwd=str(binary.parent),env=env,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+75
        db=data/"portfolio.sqlite3"
        while time.monotonic()<deadline:
            if child.poll() is not None:
                raise RuntimeError(f"Frozen app exited unexpectedly: {child.returncode}")
            if db.is_file() and db.stat().st_size>0:
                with closing(sqlite3.connect(db)) as con:
                    result=con.execute("PRAGMA quick_check").fetchone()[0]
                    if result=="ok":
                        break
            time.sleep(0.5)
        else:
            raise RuntimeError("Frozen app did not initialize a valid isolated SQLite")
        time.sleep(3)
        if child.poll() is not None:
            raise RuntimeError("Frozen app terminated after initial SQLite")
        with closing(sqlite3.connect(db)) as con:
            assert con.execute("SELECT COUNT(*) FROM operacoes").fetchone()[0]==0
        print("RELEASE_FROZEN_STARTUP=PASS")
        print("RELEASE_FINANCIAL_DATA_ISOLATED=PASS")
    finally:
        if is_win:
            # A frozen PyInstaller binary can have a bootloader parent and
            # Python child. terminate() only kills the parent; its child keeps
            # the SQLite file open. Stop the entire disposable smoke-test tree.
            subprocess.run(
                ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=15,
            )
            try:
                child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=12)
            # Windows releases SQLite file handles asynchronously.
            time.sleep(1)
        elif child.poll() is None:
            child.terminate()
            try: child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=12)
