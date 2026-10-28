"""Fetch the pinned official engine and verify archive and installed files."""
import argparse,hashlib,shutil,tempfile,urllib.request
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/official-pikafish/Pikafish/releases/download/Pikafish-2026-09-06/Pikafish.2026-09-06.7z'
ARCHIVE_SHA='41952bbfe2520faceb5902c69e6ab4845cc999841d2b49a95cc1be7867a25e5b'
FILES={'pikafish.exe':('Pikafish-Windows-x86-64-universal.exe','0d57d64c212e78f96cba9e5e4f140d8872f8faa42ea631a27ab6c5db08509da3'),
       'pikafish.nnue':('pikafish.nnue','7d13d73569a9b571ba0eb20cf1596247bc2a42738967e61afef6482b231e900e')}

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def install(destination,archive=None):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    if all((destination/name).exists() and digest(destination/name)==value[1] for name,value in FILES.items()):
        print('Official engine already installed and verified.');return
    import py7zr
    with tempfile.TemporaryDirectory(prefix='bulldog-engine-') as folder:
        temp=Path(folder);download=Path(archive) if archive else temp/'engine.7z'
        if not archive:
            print('Downloading official Pikafish release...')
            urllib.request.urlretrieve(URL,download)
        if digest(download)!=ARCHIVE_SHA:raise RuntimeError('Engine archive SHA256 mismatch')
        with py7zr.SevenZipFile(download) as z:
            names=z.getnames();targets=[]
            for name in names:
                normalized=name.replace('\\','/');parts=PurePosixPath(normalized)
                if parts.is_absolute() or '..' in parts.parts or ':' in normalized:raise RuntimeError('Unsafe archive path')
            for original,_ in FILES.values():
                matches=[name for name in names if PurePosixPath(name.replace('\\','/')).name==original]
                if len(matches)!=1:raise RuntimeError('Engine archive layout has changed')
                targets+=matches
            z.extract(path=temp/'extracted',targets=targets)
        for name,(original,expected) in FILES.items():
            matches=list((temp/'extracted').rglob(original))
            if len(matches)!=1 or digest(matches[0])!=expected:raise RuntimeError(f'Invalid engine file: {name}')
            shutil.copy2(matches[0],destination/name)
        print('Official engine installed; both SHA256 checks passed.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--destination',type=Path,default=ROOT/'engine');parser.add_argument('--archive',type=Path)
    args=parser.parse_args();install(args.destination,args.archive)
