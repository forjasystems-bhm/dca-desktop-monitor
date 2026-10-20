"""Per-user Windows updates: verified side-by-side files, offline backup, GUI receipt.

Never replaces a running binary or restores an older database automatically.
No administrator rights, PowerShell policy bypass or silent network installation.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

from backend.app_lifecycle import APP_VERSION, comparar_versoes
from backend.single_instance import TravaInstancia, OutraInstanciaAberta


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sem_vinculos(path):
    """Resolve only after rejecting symlinks and Windows junctions in ancestors."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Pasta com vínculo não permitida: ' + str(part))
        if part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Pasta com reparse point não permitida.')
    return path.resolve()


def raiz_instalacoes():
    if sys.platform != 'win32' or not os.environ.get('LOCALAPPDATA'):
        raise RuntimeError('Instalação assistida disponível no Windows.')
    return sem_vinculos(Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'DCA-Monitor' / 'versions')


def conferir_pasta(folder, *, version, commit):
    folder = sem_vinculos(folder)
    manifest = json.loads((folder / 'distribution-manifest.json').read_text('utf-8'))
    if (manifest.get('format') != 'DCA-DISTRIBUTION-1' or
            manifest.get('version') != version or manifest.get('commit') != commit or
            not re.fullmatch('[a-f0-9]{40}', str(commit))):
        raise ValueError('Origem ou versão do pacote inválida.')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Manifesto de arquivos vazio.')
    actual = set()
    for file in folder.rglob('*'):
        sem_vinculos(file)
        if file.is_file():
            actual.add(file.relative_to(folder).as_posix())
    if actual != set(files) | {'distribution-manifest.json'}:
        raise ValueError('Pacote incompleto ou com arquivos inesperados.')
    for name, digest in files.items():
        parts = PurePosixPath(name)
        if (parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name or
                not re.fullmatch('[a-f0-9]{64}', str(digest)) or
                sha256(folder / name) != digest):
            raise ValueError('Integridade do pacote inválida: ' + name)
    if not (folder / 'DCA-Monitor.exe').is_file():
        raise ValueError('Executável Windows ausente.')
    return manifest


def extrair_windows(archive, destination, *, version, digest):
    """Authenticate archive bytes before extracting anything; destination is new."""
    archive = Path(archive)
    destination = sem_vinculos(destination)
    if sha256(archive) != digest:
        raise ValueError('SHA-256 divergente; nada foi instalado.')
    if destination.exists():
        raise FileExistsError('Versão já preparada; não sobrescrever.')
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        names = set()
        total = 0
        for entry in entries:
            name = entry.filename
            parts = PurePosixPath(name)
            canonical = name.casefold().rstrip('/')
            if (not parts.parts or parts.parts[0] != 'DCA-Monitor' or
                    parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name or
                    any(p.endswith((' ', '.')) or p.split('.')[0].upper() in
                        {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),
                         *(f'LPT{i}' for i in range(1,10))} for p in parts.parts) or
                    stat.S_ISLNK(entry.external_attr >> 16) or canonical in names or
                    parts.suffix.lower() in ('.csv','.db','.sqlite3') or
                    'DCA-PREVIEW-MODE' in parts.parts):
                raise ValueError('Caminho inseguro ou dados pessoais no pacote.')
            names.add(canonical)
            total += entry.file_size
            if total > 2_000_000_000 or len(entries) > 30000:
                raise ValueError('Pacote expandido excessivo.')
        if package.getinfo('DCA-Monitor/distribution-manifest.json').file_size > 4_000_000:
            raise ValueError('Manifesto excessivo.')
        manifest = json.loads(package.read('DCA-Monitor/distribution-manifest.json'))
        if manifest.get('version') != version:
            raise ValueError('Versão do manifesto não corresponde à Release.')
        # Exclusive directory creation: never merges a new package with old files.
        destination.mkdir(parents=True)
        for entry in entries:
            target = destination.joinpath(*PurePosixPath(entry.filename).parts[1:])
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, target.open('xb') as output:
                import shutil
                shutil.copyfileobj(source, output)
    return conferir_pasta(destination, version=version, commit=manifest.get('commit'))


def preparar_instalacao(info, archive, banco, *, version_atual=APP_VERSION,
                       raiz=None, origem=None):
    from backend.windows_lifecycle import verificar_separacao_dados
    version = info.get('versao_publicada', '')
    if not info.get('download_disponivel') or not comparar_versoes(version_atual, version)['elegivel']:
        raise ValueError('Não há atualização superior autorizada.')
    asset = info.get('pacote') or {}
    name = f'DCA-Monitor-v{version}-Windows-x64.zip'
    expected = f'https://github.com/tiolusystems/dca-desktop-monitor/releases/download/v{version}/{name}'
    archive = Path(archive).resolve()
    if (asset.get('nome') != name or asset.get('url') != expected or archive.name != name or
            not re.fullmatch('[a-f0-9]{64}', str(asset.get('sha256'))) or
            archive.stat().st_size != asset.get('tamanho')):
        raise ValueError('Pacote oficial Windows incompatível.')
    base = sem_vinculos(raiz if raiz is not None else raiz_instalacoes())
    db = sem_vinculos(banco)
    verificar_separacao_dados(base, db)
    source = sem_vinculos(origem or sys.executable)
    verificar_separacao_dados(source.parent, db)
    token = secrets.token_hex(16)
    target = base / (version + '-' + token)
    manifest = extrair_windows(archive, target, version=version, digest=asset['sha256'])
    actions = db.parent / 'updates'
    actions.mkdir(exist_ok=True)
    action = actions / (token + '.json')
    record = dict(format='DCA-UPDATE-1', token=token, version=version,
                  previous_version=version_atual, commit=manifest['commit'],
                  target=str(target), source=str(source), bank=str(db),
                  archive=str(archive), sha256=asset['sha256'], state='prepared')
    with action.open('x', encoding='utf-8') as out:
        json.dump(record, out)
    return {'acao': str(action), 'destino': str(target), 'versao': version}


def iniciar_instalacao(action):
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        raise RuntimeError('Utilize o aplicativo Windows empacotado.')
    subprocess.Popen([sys.executable, '--maintenance-update', str(action)],
                     cwd=str(Path(sys.executable).parent), close_fds=True,
                     creationflags=subprocess.CREATE_NO_WINDOW)


def _salvar(action, record):
    temp = action.with_suffix('.tmp')
    with temp.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, action)


def executar_instalacao(action, *, timeout=90):
    """Runs as a separate frozen process after the old GUI exits gracefully."""
    from backend.recovery_bundle import exportar_pacote, recuperar_pacote
    from backend.windows_lifecycle import verificar_separacao_dados
    from config.install import install_windows
    action = sem_vinculos(action)
    record = json.loads(action.read_text('utf-8'))
    token = record.get('token', '')
    if (record.get('format') != 'DCA-UPDATE-1' or record.get('state') != 'prepared' or
            not re.fullmatch('[a-f0-9]{32}', token) or action.name != token + '.json'):
        raise ValueError('Solicitação de atualização inválida ou já utilizada.')
    bank = sem_vinculos(record['bank'])
    if action.parent != bank.parent / 'updates':
        raise ValueError('Solicitação fora da pasta de dados.')
    source = sem_vinculos(record['source'])
    if source != Path(sys.executable).resolve():
        raise ValueError('Auxiliar não corresponde ao aplicativo que solicitou a troca.')
    target = sem_vinculos(record['target'])
    if (target.parent != raiz_instalacoes() or
            target.name != record['version'] + '-' + token or
            not comparar_versoes(record['previous_version'], record['version'])['elegivel']):
        raise ValueError('Destino de atualização inválido.')
    verificar_separacao_dados(target, bank)
    lock = TravaInstancia(bank.parent)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                lock.adquirir()
                break
            except OutraInstanciaAberta:
                if time.monotonic() >= deadline:
                    raise RuntimeError('O aplicativo continua aberto; atualização cancelada.')
                time.sleep(.2)
        # Validate again after the old GUI has closed and all writes have stopped.
        conferir_pasta(target, version=record['version'], commit=record['commit'])
        backup = bank.parent / 'updates' / (token + '-backup.zip')
        record['backup'] = exportar_pacote(bank, backup)
        with tempfile.TemporaryDirectory(prefix='dca-update-recovery-') as tmp:
            recuperar_pacote(backup, Path(tmp) / 'check')
        record['state'] = 'starting'
        _salvar(action, record)
    except Exception as exc:
        record.update(state='failed', error=str(exc))
        _salvar(action, record)
        raise
    finally:
        lock.liberar()
    # Candidate uses the SAME data directory and the normal single-instance lock.
    env = os.environ.copy()
    env['DCA_MONITOR_DATA_DIR'] = str(bank.parent)
    child = None
    try:
        child = subprocess.Popen([str(target / 'DCA-Monitor.exe'),
                                  '--update-ready', str(action), token],
                                 cwd=str(target), env=env, close_fds=True)
        receipt = action.with_suffix('.ready.json')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if receipt.is_file():
                ready = json.loads(receipt.read_text('utf-8'))
                if ready != dict(token=token, version=record['version'],
                                 executable=str(target / 'DCA-Monitor.exe'), pid=child.pid):
                    raise ValueError('Confirmação da nova versão inválida.')
                if child.poll() is not None:
                    raise RuntimeError('A nova versão fechou antes da ativação.')
                result = install_windows(executavel=target / 'DCA-Monitor.exe', anterior=source)
                if not result['criado'] and not result.get('proprio'):
                    raise RuntimeError(result['status'])
                record.update(state='installed', shortcut=result, pid=child.pid)
                _salvar(action, record)
                return record
            if child.poll() is not None:
                raise RuntimeError('A nova versão não conseguiu abrir.')
            time.sleep(.2)
        raise RuntimeError('Nova versão sem confirmação; atalho anterior preservado.')
    except Exception as exc:
        # The candidate may have migrated SQLite. NEVER reopen old code or restore
        # a snapshot over newer writes automatically. Keep both folders and backup.
        record.update(state='failed', error=str(exc))
        _salvar(action, record)
        raise


def confirmar_abertura(root, app, action, token):
    """Acknowledges only the real GUI and the intended wallet, without test data."""
    action = sem_vinculos(action)
    record = json.loads(action.read_text('utf-8'))
    if (record.get('token') != token or record.get('state') != 'starting' or
            record.get('version') != APP_VERSION or
            Path(record['target']) / 'DCA-Monitor.exe' != Path(sys.executable).resolve() or
            Path(record['bank']).resolve() != app.data_manager.arquivo_db.resolve() or
            action.parent != app.data_manager.arquivo_db.parent.resolve() / 'updates'):
        raise ValueError('Confirmação de atualização incompatível.')
    def ready():
        if not app._closing and root.winfo_viewable():
            from backend.database_identity import validar_banco_dca
            validar_banco_dca(app.data_manager.arquivo_db)
            receipt = action.with_suffix('.ready.json')
            temporary = receipt.with_suffix('.tmp')
            with temporary.open('x', encoding='utf-8') as out:
                json.dump(dict(token=token, version=APP_VERSION,
                               executable=str(Path(sys.executable).resolve()), pid=os.getpid()), out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, receipt)
        else:
            root.after(250, ready)
    root.after(1000, ready)
