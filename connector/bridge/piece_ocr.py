"""On-demand local Chinese glyph recognition with the existing DirectML runtime."""
import os,math
from vision import cv2,np,ort,HERE
from skin_store import SkinStore

MODEL=os.path.join(os.path.dirname(HERE),'models','ch_PP-OCRv4_rec.onnx')
GLYPHS={'车':'R','車':'R','俥':'R','马':'N','馬':'N','傌':'N','相':'B','象':'B','仕':'A','士':'A','帅':'K','帥':'K','将':'K','將':'K','炮':'C','砲':'C','兵':'P','卒':'P'}


def session(path,use_gpu):
    options=ort.SessionOptions();options.intra_op_num_threads=2
    providers=['CPUExecutionProvider']
    if use_gpu and 'DmlExecutionProvider' in ort.get_available_providers():
        options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        providers=[('DmlExecutionProvider',{'device_id':0}),'CPUExecutionProvider']
    return ort.InferenceSession(path,sess_options=options,providers=providers)


def red_ink(patch):
    # Only the glyph body contributes: gold rims and selection rings may have
    # red hue, but are not evidence for the side of the piece.
    margin=max(1,round(min(patch.shape[:2])*.24))
    hsv=cv2.cvtColor(patch[margin:-margin,margin:-margin],cv2.COLOR_BGR2HSV)
    return int(np.count_nonzero(((hsv[:,:,0]<12)|(hsv[:,:,0]>170))&(hsv[:,:,1]>110)&(hsv[:,:,2]>75)))


class PieceOCR:
    def __init__(self,use_gpu=True):
        if not os.path.isfile(MODEL):raise ValueError('中文文字模型未安装，请运行 install_dependencies.bat 或 tools/install_ocr.py')
        self.model=session(MODEL,use_gpu);self.input=self.model.get_inputs()[0].name
        self.characters=['blank']+self.model.get_modelmeta().custom_metadata_map['character'].splitlines()+[' ']
        self.backend=self.model.get_providers()[0]

    def read(self,patches):
        inputs=[]
        for patch in patches:
            for margin in (2,5):
                crop=patch[margin:-margin,margin:-margin]
                value=cv2.resize(crop,(48,48)).astype(np.float32)/127.5-1
                array=np.zeros((3,48,64),np.float32);array[:,:,:48]=value.transpose(2,0,1);inputs.append(array)
        results=[]
        for offset in range(0,len(inputs),16):
            predictions=self.model.run(None,{self.input:np.asarray(inputs[offset:offset+16])})[0]
            for prediction in predictions:
                indices=prediction.argmax(1);tokens=[(int(token),float(prediction[i,token])) for i,token in enumerate(indices) if token and (i==0 or token!=indices[i-1])]
                text=''.join(self.characters[index] for index,_ in tokens).strip()
                score=min((score for _,score in tokens),default=0)
                results.append((GLYPHS.get(text),score,text))
        combined=[]
        for i,patch in enumerate(patches):
            choices=[v for v in results[i*2:i*2+2] if v[0] and v[1]>=.85]
            if not choices or len({v[0] for v in choices})>1:combined.append(None);continue
            kind,score,text=max(choices,key=lambda v:v[1])
            if text in ('帅','帥','仕','相','兵'):red=True
            elif text in ('将','將','卒'):red=False
            else:red=red_ink(patch)>10
            combined.append(kind if red else kind.lower())
        return combined


class Appearance:
    shifts=tuple((dx,dy) for dy in range(-3,4) for dx in range(-3,4))
    def __init__(self,use_gpu=True):
        self.model=session(os.path.join(HERE,'appearance.onnx'),use_gpu)
        self.backend=self.model.get_providers()[0];self.references=None;self.labels=[]
        self.store=SkinStore()

    @staticmethod
    def features(patches):
        features=[]
        for patch in patches:
            small=cv2.resize(patch[4:-4,4:-4],(32,32)).astype(np.float32)/255
            gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
            edge=cv2.Laplacian(gray,cv2.CV_32F)
            color=small[:,:,2]-small[:,:,1];color-=color.mean()
            value=np.concatenate(((gray-gray.mean()).ravel(),edge.ravel(),color.ravel()))
            value/=max(float(np.linalg.norm(value)),1e-6);features.append(value)
        return np.asarray(features,np.float32)

    def learn(self,patches,labels,persist=False):
        self.references=self.features(patches);self.labels=list(labels)
        if persist:
            try:self.store.save(self.references,self.labels)
            except OSError:pass

    def load_matching(self,patches):
        query=self.metric_features(self.shifted_features(patches));best=None
        for references,labels in self.store.load():
            scores=self.model.run(None,{'patches':query,'references':self.metric_features(references)})[0].reshape(len(patches),len(self.shifts),-1).max(1)
            maxima=scores.max(1);quality=float(np.median(maxima))
            if float((maxima>.82).mean())>=.8 and quality>.88 and (best is None or quality>best[0]):best=(quality,references,labels)
        if best is None:return False
        _,self.references,self.labels=best;return True

    def shifted_features(self,patches):
        shifted=[]
        for patch in patches:
            for dx,dy in self.shifts:
                shifted.append(cv2.warpAffine(patch,np.array([[1,0,dx],[0,1,dy]],np.float32),(patch.shape[1],patch.shape[0]),borderMode=cv2.BORDER_REPLICATE))
        return self.features(shifted)

    @staticmethod
    def metric_features(values):
        # Subpixel rendering changes the Laplacian much more than the glyph.
        # Keep edge detail, but let the centered glyph/color carry more weight.
        # Reweight both sides at read time so existing local profiles stay valid.
        values=values.copy();values[:,1024:2048]*=.5
        y,x=np.ogrid[:32,:32]
        body=(((x-15.5)**2+(y-15.5)**2)<15**2).astype(np.float32).ravel()
        values*=np.tile(body,3)
        values/=np.maximum(np.linalg.norm(values,axis=1,keepdims=True),1e-6)
        return values

    def read(self,patches,min_score=.68):
        scores=self.model.run(None,{'patches':self.metric_features(self.shifted_features(patches)),'references':self.metric_features(self.references)})[0].reshape(len(patches),len(self.shifts),-1).max(1)
        output=[]
        for patch,row in zip(patches,scores):
            by_class={p:max(float(v) for v,label in zip(row,self.labels) if label==p) for p in set(self.labels)}
            ranked=sorted(by_class.items(),key=lambda p:p[1],reverse=True)
            if red_ink(patch)>10:
                red=[p for p in ranked if p[0].isupper()]
                if red:ranked=red
            best,score=ranked[0]
            # Red/black variants of the same glyph may be almost identical in
            # shape. The ambiguity margin compares distinct piece kinds.
            rivals=[v for p,v in ranked if p.upper()!=best.upper()]
            gap=score-max(rivals) if rivals else 1
            output.append(best if score>min_score and gap>.025 else None)
        return output
