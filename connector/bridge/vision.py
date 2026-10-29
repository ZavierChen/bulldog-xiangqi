"""Xiangqi screen recognition prototype. PieceNet weights/code: yingwang/xiangqi-bot (MIT)."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'runtime'))
gpu_runtime=os.path.join(os.path.dirname(os.path.dirname(__file__)),'gpu-runtime')
if os.path.isdir(gpu_runtime):sys.path.insert(0,gpu_runtime)
import cv2, numpy as np
try:import onnxruntime as ort
except ImportError:
    if gpu_runtime in sys.path:sys.path.remove(gpu_runtime)
    for key in list(sys.modules):
        if key=='onnxruntime' or key.startswith('onnxruntime.'):del sys.modules[key]
    import onnxruntime as ort

HERE = os.path.dirname(__file__)
CLASSES = '_RNBAKCPrnbakcp'
LIMITS = {'R': 2, 'N': 2, 'B': 2, 'A': 2, 'C': 2, 'P': 5,
          'r': 2, 'n': 2, 'b': 2, 'a': 2, 'c': 2, 'p': 5}

class BoardBox(tuple):
    def __new__(cls,rect,profile='original'):
        obj=super().__new__(cls,rect);obj.profile=profile;return obj

class Recognizer:
    def __init__(self,use_gpu=True):
        options=ort.SessionOptions();options.intra_op_num_threads=4
        self.backend='CPUExecutionProvider';providers=['CPUExecutionProvider']
        if use_gpu and 'DmlExecutionProvider' in ort.get_available_providers():
            options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            providers=[('DmlExecutionProvider',{'device_id':0}),'CPUExecutionProvider']
        try:self.model=ort.InferenceSession(os.path.join(HERE,'pieces.onnx'),sess_options=options,providers=providers)
        except Exception:self.model=ort.InferenceSession(os.path.join(HERE,'pieces.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        if 'DmlExecutionProvider' in self.model.get_providers():self.backend='RTX 5070 Ti / DirectML device 0'
        self.template=cv2.imdecode(np.fromfile(os.path.join(HERE,'frame.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
        self.turn_template=cv2.imdecode(np.fromfile(os.path.join(HERE,'turn.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
        self.mask=np.zeros(self.template.shape,np.uint8)
        self.mask[:10,:]=255; self.mask[-10:,:]=255; self.mask[:,:10]=255; self.mask[:,-10:]=255
        self.profiles=[('original',self.template,self.mask)]
        alt=os.path.join(HERE,'frame-alt.png')
        if os.path.exists(alt):
            t=cv2.imdecode(np.fromfile(alt,np.uint8),cv2.IMREAD_GRAYSCALE);m=np.zeros(t.shape,np.uint8)
            m[:10,:]=255;m[-10:,:]=255;m[:,:10]=255;m[:,-10:]=255
            self.profiles.append(('alt',t,m))
        self.turn_cache=None;self.turn_cache_at=0;self.turn_signature=None;self.current_signature=None
        self.last_location=None;self.last_location_at=0;self.last_image_shape=None
        self.last_hint_attempt=0
        self.continue_templates=[]
        from end_screens import EndScreens
        self.end_screens=EndScreens()
        assets=os.path.join(HERE,'ui_templates')
        if os.path.isdir(assets):
            for name in os.listdir(assets):
                if name=='continue-again.png':
                    self.continue_templates.append(cv2.imdecode(np.fromfile(os.path.join(assets,name),np.uint8),cv2.IMREAD_GRAYSCALE))

    def continue_button(self,image):
        point=self.end_screens.continuation(image)
        if point:return point
        if not self.continue_templates:return None
        reduction=min(1.,1280/image.shape[1]);gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        if reduction<1:gray=cv2.resize(gray,None,fx=reduction,fy=reduction)
        best=(.97,None)
        for template in self.continue_templates:
            for scale in np.arange(.65,1.76,.05):
                h,w=template.shape;w=round(w*scale);h=round(h*scale)
                if h>gray.shape[0] or w>gray.shape[1]:continue
                t=cv2.resize(template,(w,h));scores=cv2.matchTemplate(gray,t,cv2.TM_CCOEFF_NORMED)
                _,score,_,(x,y)=cv2.minMaxLoc(scores)
                if score>best[0]:best=(score,((x+w/2)/reduction,(y+h/2)/reduction))
        return best[1]

    def live_hint(self,image):
        """Only a fast scene hint: full board and turn checks still precede any move."""
        if self.last_location is None or self.last_image_shape!=image.shape:
            if time.monotonic()-self.last_hint_attempt<2:return False
            self.last_hint_attempt=time.monotonic()
            try:self.locate(image)
            except ValueError:return False
        box=self.last_location[0]
        if box.profile=='alt':return self.alt_avatar_turn(image,box,False) is not None
        return self.practice_turn(image,box,False) is not None

    def locate(self, image):
        if self.last_location and self.last_image_shape==image.shape and time.monotonic()-self.last_location_at<30:
            box,score=self.last_location;x,y,w,h=box
            if 0<=x and 0<=y and x+w<=image.shape[1] and y+h<=image.shape[0]:
                _,template,mask=next(p for p in self.profiles if p[0]==box.profile)
                gray=cv2.cvtColor(image[y:y+h,x:x+w],cv2.COLOR_BGR2GRAY)
                reference=cv2.resize(template,(w,h));valid=cv2.resize(mask,(w,h),interpolation=cv2.INTER_NEAREST)
                _,value,_,_=cv2.minMaxLoc(cv2.matchTemplate(gray,reference,cv2.TM_CCORR_NORMED,mask=valid))
                if np.isfinite(value) and value>.985:return box,value
        best=None
        for name,template,mask in self.profiles:
            try:
                box,score=self._locate_profile(image,template,mask)
                if best is None or score>best[1]:best=(BoardBox(box,name),score)
            except ValueError:pass
        if best is None:raise ValueError('找不到可信的棋盘外框')
        self.last_location=best;self.last_location_at=time.monotonic();self.last_image_shape=image.shape
        return best

    def _locate_profile(self, image, template, mask_image):
        original=image
        reduction=min(1.0,1280/image.shape[1],900/image.shape[0])
        if reduction<1:image=cv2.resize(image,None,fx=reduction,fy=reduction)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        h0,w0=template.shape; best=(-1,None);best_scale=None
        for scale in np.arange(.50,1.76,.025):
            w,h=round(w0*scale),round(h0*scale)
            if w>gray.shape[1] or h>gray.shape[0]: continue
            templ=cv2.resize(template,(w,h)); mask=cv2.resize(mask_image,(w,h),interpolation=cv2.INTER_NEAREST)
            scores=cv2.matchTemplate(gray,templ,cv2.TM_CCORR_NORMED,mask=mask)
            _,score,_,(x,y)=cv2.minMaxLoc(scores)
            if np.isfinite(score) and score>best[0]: best=(score,(x,y,w,h));best_scale=scale
        if best_scale is not None:
            for scale in np.arange(best_scale-.025,best_scale+.026,.0025):
                w,h=round(w0*scale),round(h0*scale)
                if w>gray.shape[1] or h>gray.shape[0] or w<20 or h<20:continue
                templ=cv2.resize(template,(w,h));mask=cv2.resize(mask_image,(w,h),interpolation=cv2.INTER_NEAREST)
                scores=cv2.matchTemplate(gray,templ,cv2.TM_CCORR_NORMED,mask=mask)
                _,score,_,(x,y)=cv2.minMaxLoc(scores)
                if np.isfinite(score) and score>best[0]:best=(score,(x,y,w,h))
        if best[1] is None or best[0]<.985: raise ValueError('找不到可信的棋盘外框')
        x,y,w,h=best[1]
        return (round(x/reduction),round(y/reduction),round(w/reduction),round(h/reduction)),best[0]

    def read(self,image,box=None):
        if box is None: box,_=self.locate(image)
        x,y,w,h=box
        if x<0 or y<0 or x+w>image.shape[1] or y+h>image.shape[0]: raise ValueError('棋盘超出窗口')
        if getattr(box,'profile','original')=='alt':
            crop=cv2.resize(image[y:y+h,x:x+w],(706,799))
            sx=48/78.9;sy=48/77.8
            boardimg=cv2.warpAffine(crop,np.array([[sx,0,31-37*sx],[0,sy,28-40*sy]],np.float32),(447,495),borderMode=cv2.BORDER_REPLICATE)
        else:boardimg=cv2.resize(image[y:y+h,x:x+w],(447,495))
        gray=cv2.GaussianBlur(cv2.cvtColor(boardimg,cv2.COLOR_BGR2GRAY),(5,5),1)
        circles=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1,33.6,param1=100,param2=22,minRadius=15,maxRadius=28 if getattr(box,'profile','original')=='alt' else 23)
        positions=set();centers={}
        if circles is not None:
            for cx,cy,radius in circles[0]:
                col=round((cx-31)/48); row=round((cy-28)/48)
                tolerance=11.5
                if 0<=col<9 and 0<=row<10 and abs(cx-(31+col*48))<tolerance and abs(cy-(28+row*48))<tolerance:
                    positions.add((row,col))
                    distance=(cx-(31+col*48))**2+(cy-(28+row*48))**2
                    if (row,col) not in centers or distance<centers[(row,col)][3]:centers[(row,col)]=(cx,cy,radius,distance)
        if len(positions)<2:raise ValueError('没有识别到足够的棋子')
        occupied=positions
        patches=[]; positions=[(r,c) for r in range(10) for c in range(9)]
        for row,col in positions:
            cx=31+col*48;cy=28+row*48;radius=19
            patch=boardimg[max(0,cy-radius):cy+radius,max(0,cx-radius):cx+radius]
            patch=cv2.cvtColor(cv2.resize(patch,(48,48)),cv2.COLOR_BGR2RGB).astype(np.float32)/255
            patches.append(patch.transpose(2,0,1))
        logits=self.model.run(None,{'images':np.asarray(patches)})[0]
        scores=np.exp(logits-logits.max(axis=1,keepdims=True));probs=scores/scores.sum(axis=1,keepdims=True)
        board=[['_']*9 for _ in range(10)]
        for (row,col),p in zip(positions,probs):
            piece=CLASSES[int(p.argmax())]
            if (row,col) not in occupied and (getattr(box,'profile','original')=='alt' or piece=='_' or float(p.max())<.98):continue
            if piece=='_' or float(p.max())<.8: raise ValueError(f'棋子识别不确定：第 {row+1} 行第 {col+1} 列')
            board[row][col]=piece
        flat=sum(board,[])
        if flat.count('K')!=1 or flat.count('k')!=1: raise ValueError('将或帅识别不完整')
        if any(flat.count(piece)>limit for piece,limit in LIMITS.items()): raise ValueError('棋子数量超出规则')
        red=next((r,c) for r in range(10) for c in range(9) if board[r][c]=='K')
        black=next((r,c) for r in range(10) for c in range(9) if board[r][c]=='k')
        if red[0]>=7 and black[0]<=2: flipped=False
        elif red[0]<=2 and black[0]>=7: flipped=True
        else: raise ValueError('无法确定红黑视角')
        if flipped: board=[list(reversed(row)) for row in reversed(board)]
        self.current_signature=tuple(tuple(row) for row in board)
        return board,flipped,box

    def practice_turn(self,image,box,flipped):
        """Only recognize the observed training banner; unknown banners remain unknown."""
        if getattr(box,'profile','original')=='alt':
            ring=self.alt_avatar_turn(image,box,flipped)
            if ring:return ring
            return self.turn_cache if self.turn_signature==self.current_signature and time.monotonic()-self.turn_cache_at<5 else None
        x,y,w,h=box;scale=w/447
        x1=max(0,round(x+300*scale));x2=min(image.shape[1],round(x+550*scale))
        y1=max(0,round(y-70*scale));y2=max(0,round(y-10*scale))
        crop=cv2.cvtColor(image[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY)
        templ=cv2.resize(self.turn_template,(round(90*scale),round(30*scale)))
        if crop.shape[0]<templ.shape[0] or crop.shape[1]<templ.shape[1]: return None
        _,score,_,_=cv2.minMaxLoc(cv2.matchTemplate(crop,templ,cv2.TM_CCOEFF_NORMED))
        return ('b' if flipped else 'w') if score>.90 else self.avatar_turn(image,box,flipped)

    def observe_turn_pair(self,first,second,box,flipped):
        if getattr(box,'profile','original')!='alt':return
        x,y,w,h=box;sx=w/706;sy=h/799;changes=[]
        for rx,ry,rw,rh in ((435,-130,90,78),(248,921,95,78)):
            left=max(0,round(x+rx*sx));top=max(0,round(y+ry*sy));right=min(first.shape[1],round(x+(rx+rw)*sx));bottom=min(first.shape[0],round(y+(ry+rh)*sy))
            a=first[top:bottom,left:right];b=second[top:bottom,left:right]
            if a.size==0 or a.shape!=b.shape:return
            changes.append(float(cv2.absdiff(a,b).mean()))
        top,bottom=changes;own='b' if flipped else 'w';side=None
        if bottom>.4 and bottom>top*3+.2:side=own
        elif top>.4 and top>bottom*3+.2:side='w' if own=='b' else 'b'
        if side:
            self.turn_cache=side;self.turn_signature=self.current_signature;self.turn_cache_at=time.monotonic()

    def alt_avatar_turn(self,image,box,flipped):
        x,y,w,h=box;sx=w/706;sy=h/799;scores=[]
        for rx,ry in ((70,-92),(641,963)):
            cx=x+rx*sx;cy=y+ry*sy;radius=70*min(sx,sy)
            left=max(0,round(cx-radius));top=max(0,round(cy-radius));right=min(image.shape[1],round(cx+radius+1));bottom=min(image.shape[0],round(cy+radius+1))
            roi=image[top:bottom,left:right]
            if roi.size==0:scores.append(0);continue
            hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV);yy,xx=np.ogrid[:roi.shape[0],:roi.shape[1]]
            dist=np.sqrt((xx-(cx-left))**2+(yy-(cy-top))**2);ring=(dist>radius*.78)&(dist<radius)
            mask=(hsv[:,:,0]>24)&(hsv[:,:,0]<85)&(hsv[:,:,1]>170)&(hsv[:,:,2]>210)
            scores.append(float(mask[ring].mean()) if ring.any() else 0)
        top,bottom=scores;own='b' if flipped else 'w'
        if bottom>.025 and bottom>top*3+.015:return own
        if top>.025 and top>bottom*3+.015:return 'w' if own=='b' else 'b'
        return None

    def avatar_turn(self,image,box,flipped):
        x,y,w,h=box;s=w/447
        scores=[]
        for rx,ry in [(-94,30),(493,354)]:
            left=max(0,round(x+rx*s));top=max(0,round(y+ry*s))
            roi=image[top:round(y+(ry+52)*s),left:round(x+(rx+52)*s)]
            if roi.size==0:scores.append(0);continue
            hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
            mask=(hsv[:,:,0]>40)&(hsv[:,:,0]<85)&(hsv[:,:,1]>170)&(hsv[:,:,2]>170)
            border=np.ones(mask.shape,bool);border[round(mask.shape[0]*.16):-round(mask.shape[0]*.16),round(mask.shape[1]*.16):-round(mask.shape[1]*.16)]=False
            scores.append(float(mask[border].mean()))
        top,bottom=scores
        own='b' if flipped else 'w'
        if bottom>.12 and top<.06:return own
        if top>.12 and bottom<.06:return 'w' if own=='b' else 'b'
        return None

    def practice_complete(self,image,box):
        if getattr(box,'profile','original')=='alt':return False
        x,y,w,h=box;s=w/447
        roi=image[max(0,round(y-60*s)):max(0,round(y-20*s)),max(0,round(x+200*s)):min(image.shape[1],round(x+650*s))]
        if roi.size==0:return False
        hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
        return float(((hsv[:,:,0]>35)&(hsv[:,:,0]<90)&(hsv[:,:,1]>40)).mean())>.8

def fen(board,side):
    if side not in ('w','b'): raise ValueError('轮到哪一方尚未确定')
    rows=[]
    for row in board:
        out=''; count=0
        for piece in row+['!']:
            if piece=='_': count+=1
            else:
                if count:out+=str(count);count=0
                if piece!='!':out+=piece
        rows.append(out)
    return '/'.join(rows)+' '+side+' - - 0 1'

def move_pixels(move,box,flipped):
    x,y,w,h=box
    pts=[]
    for i in (0,2):
        col=ord(move[i])-ord('a'); row=9-int(move[i+1])
        if flipped: col,row=8-col,9-row
        if getattr(box,'profile','original')=='manual':pts.append((x+col*w/8,y+row*h/9))
        elif getattr(box,'profile','original')=='alt':pts.append((x+(37+col*78.9)*w/706,y+(40+row*77.8)*h/799))
        else:pts.append((x+(31+col*48)*w/447, y+(28+row*48)*h/495))
    return pts
