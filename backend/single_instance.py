"""Non-destructive, per-user single instance lock for desktop startup.

OS-level advisory locks are released on process death; a stale lock file
never means that an instance is still running. The SQLite ledger is untouched.
"""
from pathlib import Path
import os
import sys


class OutraInstanciaAberta(RuntimeError):
    pass


class TravaInstancia:
    def __init__(self, data_dir: Path):
        self.caminho=Path(data_dir).expanduser().resolve()/".instance.lock"
        self._fd=None

    @property
    def ativa(self):
        return self._fd is not None

    def adquirir(self):
        if self._fd is not None:
            return
        self.caminho.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(str(self.caminho),os.O_RDWR|os.O_CREAT,0o600)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd,b" ")
            os.lseek(fd,0,os.SEEK_SET)
            if sys.platform=="win32":
                import msvcrt
                msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._fd=fd
        except (OSError,IOError) as exc:
            os.close(fd)
            raise OutraInstanciaAberta(
                "O DCA Monitor já pode estar aberto nesta conta. "
                "Verifique a janela ou o ícone da bandeja antes de iniciar novamente."
            ) from exc
        except BaseException:
            os.close(fd)
            raise

    def liberar(self):
        fd,self._fd=self._fd,None
        if fd is None:
            return
        try:
            os.lseek(fd,0,os.SEEK_SET)
            if sys.platform=="win32":
                import msvcrt
                msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self):
        self.adquirir()
        return self

    def __exit__(self,*_exc):
        self.liberar()
