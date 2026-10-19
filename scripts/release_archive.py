"""Build and independently extract the complete distributable without wallet data."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app_lifecycle import APP_VERSION


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def archive_name(system=None):
    system=system or platform.system()
    if system not in ('Windows','Linux'):raise ValueError('Sistema não suportado.')
    return f'DCA-Monitor-v{APP_VERSION}-{system}-x64'+('.zip' if system=='Windows' else '.tar.gz')


def check_name(name):
    path=PurePosixPath(name)
    if ('\\' in name or ':' in name or path.is_absolute() or '..' in path.parts
            or not path.parts or path.parts[0]!='DCA-Monitor'):
        raise ValueError('Caminho inválido no pacote: '+name)
    if (path.suffix.lower() in ('.csv','.sqlite3','.db') or
            any(p in ('tests','.git','__pycache__') for p in path.parts) or
            path.name=='DCA-PREVIEW-MODE'):
        raise ValueError('Dado financeiro/teste não permitido no pacote: '+name)


def build_archive(bundle,target,*,commit):
    bundle=Path(bundle).resolve();target=Path(target)
    if target.exists():raise FileExistsError(target)
    files={}
    for file in sorted(bundle.rglob('*')):
        if file.is_dir():continue
        if not file.is_file() or not file.resolve().is_relative_to(bundle):
            raise ValueError('Link ou arquivo fora do pacote.')
        rel=file.relative_to(bundle).as_posix()
        check_name('DCA-Monitor/'+rel)
        if rel!='distribution-manifest.json':files[rel]=digest(file)
    manifest=dict(format='DCA-DISTRIBUTION-1',version=APP_VERSION,commit=commit,files=files)
    (bundle/'distribution-manifest.json').write_text(json.dumps(manifest,sort_keys=True),encoding='utf-8')
    if str(target).endswith('.zip'):
        with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(bundle.rglob('*')):
                if file.is_file():archive.write(file,'DCA-Monitor/'+file.relative_to(bundle).as_posix())
    else:
        # Materialize internal PyInstaller links: extraction requires no links.
        with tarfile.open(target,'x:gz',dereference=True) as archive:
            archive.add(bundle,arcname='DCA-Monitor')
    (target.parent/(target.name+'.sha256')).write_text(digest(target)+'  '+target.name+'\n',encoding='ascii')
    return manifest


def extract_verified(archive_path,destination,*,commit=None):
    source=Path(archive_path);dest=Path(destination)
    if dest.exists():raise FileExistsError(dest)
    entries=[]
    if source.name.endswith('.zip'):
        archive=zipfile.ZipFile(source)
        for entry in archive.infolist():
            if stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Link ZIP recusado.')
            entries.append((entry.filename,entry.is_dir(),entry.file_size,entry))
    else:
        archive=tarfile.open(source,'r:gz')
        for entry in archive.getmembers():
            if not (entry.isdir() or entry.isfile()):raise ValueError('Link/dispositivo TAR recusado.')
            entries.append((entry.name,entry.isdir(),entry.size,entry))
    try:
        seen=set();size=0
        for name,isdir,length,entry in entries:
            check_name(name)
            canonical=PurePosixPath(name).as_posix().casefold().rstrip('/')
            if canonical in seen:raise ValueError('Caminho duplicado no pacote.')
            seen.add(canonical);size+=length
            if size>2_000_000_000:raise ValueError('Pacote expandido excessivo.')
        dest.mkdir()
        for name,isdir,length,entry in entries:
            target=dest.joinpath(*PurePosixPath(name).parts)
            if isdir:target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            data=archive.open(entry) if isinstance(archive,zipfile.ZipFile) else archive.extractfile(entry)
            with data as stream,target.open('xb') as out:shutil.copyfileobj(stream,out)
            if isinstance(archive,tarfile.TarFile):target.chmod(entry.mode & 0o777)
        bundle=dest/'DCA-Monitor'
        manifest=json.loads((bundle/'distribution-manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('format')!='DCA-DISTRIBUTION-1' or manifest.get('version')!=APP_VERSION
                or (commit is not None and manifest.get('commit')!=commit)):
            raise ValueError('Identidade do pacote incompatível.')
        actual={p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()}
        if actual != set(manifest['files'])|{'distribution-manifest.json'}:
            raise ValueError('Conteúdo incompleto ou inesperado.')
        for name,sha in manifest['files'].items():
            if digest(bundle/name)!=sha:raise ValueError('Hash divergente: '+name)
        return bundle,manifest
    finally:archive.close()


if __name__=='__main__':
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    bundle=ROOT/'dist'/'DCA-Monitor'
    shutil.copyfile(ROOT/'docs'/'RELEASE_V1_0_0.md',bundle/'LEIA-ME.md')
    build_archive(bundle,ROOT/archive_name(),commit=commit)
    print('RELEASE_ARCHIVE_COMPLETE='+archive_name())
