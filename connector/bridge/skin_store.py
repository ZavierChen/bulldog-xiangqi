"""Private, persistent appearance features; no board positions or account data."""
from pathlib import Path
import hashlib,os,tempfile
from vision import np,HERE


class SkinStore:
    def __init__(self,path=None):self.path=Path(path) if path else Path(HERE)/'local_data/skins'
    def save(self,features,labels):
        features=np.asarray(features,np.float32);labels=np.asarray(labels,dtype='U1')
        key=hashlib.sha256(features.tobytes()+labels.tobytes()).hexdigest()[:24]
        self.path.mkdir(parents=True,exist_ok=True);target=self.path/(key+'.npz')
        if target.exists():return
        fd,name=tempfile.mkstemp(dir=self.path,suffix='.tmp');os.close(fd)
        try:
            with open(name,'wb') as f:np.savez_compressed(f,features=features,labels=labels)
            os.replace(name,target)
        finally:
            if os.path.exists(name):os.remove(name)
    def load(self):
        if not self.path.exists():return []
        profiles=[]
        for path in sorted(self.path.glob('*.npz'),key=lambda p:p.stat().st_mtime,reverse=True)[:32]:
            try:
                with np.load(path,allow_pickle=False) as data:
                    features=data['features'];labels=data['labels'].tolist()
                if features.ndim!=2 or features.shape[1]!=3072 or not 2<=len(labels)<=256 or len(features)!=len(labels):continue
                if any(p not in 'RNBAKCPrnbakcp' for p in labels) or not np.isfinite(features).all():continue
                profiles.append((features.astype(np.float32),labels))
            except (ValueError,OSError,KeyError):continue
        return profiles
