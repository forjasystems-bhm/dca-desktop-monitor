"""Smoke test for a manually downloaded, unsigned Windows preview executable.

Synthetic empty data only. No access to real CSV, no release or installer.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time

if sys.platform != "win32":
    raise SystemExit("This check runs on the Windows GitHub runner only.")

root = Path(__file__).resolve().parent.parent
package = root / "dist" / "DCA-Monitor-PREVIEW"
exe = package / "DCA-Monitor-PREVIEW.exe"
marker = package / "DCA-PREVIEW-MODE"
if not exe.is_file() or not marker.is_file():
    raise SystemExit("Preview EXE or DCA-PREVIEW-MODE marker absent.")
if (package / "preview-data" / "portfolio.sqlite3").exists():
    raise SystemExit("Packaged preview contains an existing portfolio!")

# Freeze launch must select dedicated personal-test data, not LOCALAPPDATA.
env = os.environ.copy()
env.pop("DCA_MONITOR_DATA_DIR", None)
expected = package / "preview-data" / "portfolio.sqlite3"

def visible_for(pid):
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32 = ctypes.windll.user32
    def collect(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            found.append(buff.value)
        return True
    user32.EnumWindows(callback_type(collect), 0)
    return found

proc = subprocess.Popen([str(exe)], cwd=str(package), env=env)
try:
    deadline = time.monotonic() + 110
    saw_gui = False
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Frozen Windows preview terminated early: {proc.returncode}")
        titles = visible_for(proc.pid)
        if any("Portfolio CRIPTO" in x for x in titles):
            saw_gui = True
        if saw_gui and expected.is_file():
            break
        time.sleep(1)
    if not saw_gui:
        raise RuntimeError("No DCA GUI window appeared for frozen executable.")
    if not expected.is_file():
        raise RuntimeError("No isolated preview-data/portfolio.sqlite3 was created.")
    if expected.stat().st_size == 0:
        raise RuntimeError("Frozen preview created an empty SQLite placeholder.")
    print("FROZEN_PREVIEW_GUI=PASS")
    print("FROZEN_PREVIEW_ISOLATED_SQLITE=PASS")
finally:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=12)
