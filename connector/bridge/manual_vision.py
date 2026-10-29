"""Grid-based recognition: verified opening labels, GPU appearance and glyph OCR."""
import hashlib,copy,time
from collections import OrderedDict
from vision import Recognizer,cv2,np,CLASSES,LIMITS
from manual_grid import grid_box
from tracker import replay_positions,moved
from piece_ocr import Appearance,PieceOCR,red_ink

START='rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1'


def oriented(board):
    flat=sum(board,[])
    if flat.count('K')!=1 or flat.count('k')!=1:raise ValueError('将帅识别不完整；请使用标准开局学习皮肤，或检查两点位置')
    if any(flat.count(p)>limit for p,limit in LIMITS.items()):raise ValueError('棋子数量超出规则，等待稳定画面')
    r=next(r for r in range(10) if 'K' in board[r]);b=next(r for r in range(10) if 'k' in board[r])
    if r>=7 and b<=2:return board,False
    if r<=2 and b>=7:return [list(reversed(row)) for row in reversed(board)],True
    raise ValueError('将帅所在区域不合理，请重新定位棋盘')


def opening_board(occupied,flipped,moves):
    _,start,_=replay_positions(START,[])
    matches=[]
    for move in [None]+list(moves):
        board=moved(start,move) if move else start
        shown=[list(reversed(row)) for row in reversed(board)] if flipped else board
        mask={(r,c) for r in range(10) for c in range(9) if shown[r][c]!='_'}
        if mask==occupied:matches.append(shown)
    return matches[0] if len(matches)==1 else None

def complete_from_history(positions,labels,candidates,flipped):
    unknown=sum(p in (None,'_') for p in labels)
    if not unknown or unknown>max(1,len(labels)*.1):return None
    matches={}
    for board in candidates:
        shown=[list(reversed(row)) for row in reversed(board)] if flipped else board
        occupied={(r,c) for r in range(10) for c in range(9) if shown[r][c]!='_'}
        if occupied!=set(positions):continue
        inferred=[shown[r][c] for r,c in positions]
        if all(a in (None,'_') or a==b for a,b in zip(labels,inferred)):
            matches[tuple(inferred)]=inferred
    return next(iter(matches.values())) if len(matches)==1 else None


class ManualRecognizer(Recognizer):
    def __init__(self,calibration,opening_moves,use_gpu=True):
        super().__init__(use_gpu)
        self.calibration=calibration;self.opening_moves=opening_moves;self.use_gpu=use_gpu
        self.appearance=Appearance(use_gpu);self.ocr=None;self.references=[];self.reference_labels=[]
        self.source='等待两点棋盘';self.failed_key=None;self.failed_message=None
        self.backend=f'两点定位 / {self.appearance.backend}'
        self.frame_cache=OrderedDict();self.context={};self.partial_board=None;self.last_flipped=calibration.get('bottom_color')=='b';self.next_profile_check=0
        self.history_candidates=None

    def locate(self,image):return grid_box(self.calibration,image.shape,image),1.
    def practice_turn(self,image,box,flipped):return None
    def observe_turn_pair(self,*args):pass
    def practice_complete(self,*args):return False
    def live_hint(self,image):return False
    def reset_game(self):
        self.failed_key=None;self.failed_message=None;self.frame_cache.clear();self.context={}

    def normalized(self,image,box):
        x,y,w,h=box;sx,sy=384/w,432/h
        matrix=np.array([[sx,0,31-x*sx],[0,sy,28-y*sy]],np.float32)
        return cv2.warpAffine(image,matrix,(447,495),borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def patches(boardimg,positions):return [boardimg[28+r*48-21:28+r*48+21,31+c*48-21:31+c*48+21] for r,c in positions]
    @staticmethod
    def occupied(boardimg):
        gray=cv2.GaussianBlur(cv2.cvtColor(boardimg,cv2.COLOR_BGR2GRAY),(5,5),1)
        circles=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1,33.6,param1=100,param2=22,minRadius=14,maxRadius=27)
        positions=set()
        if circles is not None:
            for cx,cy,radius in circles[0]:
                col=round((cx-31)/48);row=round((cy-28)/48)
                if 0<=col<9 and 0<=row<10 and abs(cx-31-col*48)<10 and abs(cy-28-row*48)<10:positions.add((row,col))
        return positions

    def remember(self,key,board,flipped):
        self.frame_cache[key]=(copy.deepcopy(board),flipped)
        while len(self.frame_cache)>8:self.frame_cache.popitem(last=False)
        shown=[list(reversed(row)) for row in reversed(board)] if flipped else board
        self.context={(r,c):shown[r][c] for r in range(10) for c in range(9) if shown[r][c]!='_'}
        self.last_flipped=flipped;self.current_signature=tuple(tuple(row) for row in board)

    def learn_confirmed(self,image,board,flipped):
        box=self.locate(image)[0];boardimg=self.normalized(image,box)
        shown=[list(reversed(row)) for row in reversed(board)] if flipped else board
        positions=[(r,c) for r in range(10) for c in range(9) if shown[r][c]!='_']
        observed=self.occupied(boardimg);expected=set(positions)
        if observed-expected or len(observed&expected)<max(2,len(expected)*.9):
            raise ValueError('当前画面的棋子位置与校正棋盘不一致，可能仍有特效或对方已经走棋；请核对后再次确认')
        samples=sorted(observed&expected)
        self.appearance.learn(self.patches(boardimg,samples),[shown[r][c] for r,c in samples],persist=True)
        self.failed_key=None;self.source='已确认的手动棋盘 / '+self.appearance.backend
        self.remember(hashlib.sha256(boardimg.tobytes()).digest(),board,flipped)
        return box

    def read(self,image,box=None):
        box=box or self.locate(image)[0]
        boardimg=self.normalized(image,box)
        key=hashlib.sha256(boardimg.tobytes()).digest()
        if key in self.frame_cache:
            board,flipped=copy.deepcopy(self.frame_cache[key]);self.current_signature=tuple(tuple(row) for row in board)
            return board,flipped,box
        if key==self.failed_key:raise ValueError(self.failed_message)
        gray=cv2.GaussianBlur(cv2.cvtColor(boardimg,cv2.COLOR_BGR2GRAY),(5,5),1)
        circles=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1,33.6,param1=100,param2=22,minRadius=14,maxRadius=27)
        occupied=set()
        if circles is not None:
            for cx,cy,radius in circles[0]:
                col=round((cx-31)/48);row=round((cy-28)/48)
                if 0<=col<9 and 0<=row<10 and abs(cx-31-col*48)<10 and abs(cy-28-row*48)<10:occupied.add((row,col))
        if self.appearance.references is not None and self.context:
            missing=sorted(set(self.context)-occupied)
            if missing:
                recovered=self.appearance.read(self.patches(boardimg,missing),min_score=.95)
                occupied.update(pos for pos,piece in zip(missing,recovered) if piece==self.context[pos])
        if len(occupied)<2:raise ValueError('两点棋盘未识别到足够棋子，请确认点选的是棋子中心交叉点')
        positions=sorted(occupied)
        patches=self.patches(boardimg,positions)
        labels=None;trusted_opening=False
        if self.appearance.references is None or not self.context:
            bottom=self.calibration.get('bottom_color','auto')
            top_ink=sum(red_ink(p) for p,(r,c) in zip(patches,positions) if r<5)
            bottom_ink=sum(red_ink(p) for p,(r,c) in zip(patches,positions) if r>=5)
            flip=(bottom=='b') if bottom!='auto' else (top_ink>bottom_ink if max(top_ink,bottom_ink)>20 and abs(top_ink-bottom_ink)>20 else None)
            if flip is not None:self.last_flipped=flip
            initial=opening_board(occupied,flip,self.opening_moves) if flip is not None else None
            if initial is not None:
                labels=[initial[r][c] for r,c in positions];self.source='开局外观学习（允许红方已走一步）'
                trusted_opening=True
            elif self.appearance.references is None and time.monotonic()>=self.next_profile_check:
                self.next_profile_check=time.monotonic()+1
                if self.appearance.load_matching(patches):labels=self.appearance.read(patches);self.source='已保存的皮肤 / '+self.appearance.backend
        else:
            labels=self.appearance.read(patches);self.source='本局皮肤外观匹配 / '+self.appearance.backend
        if labels is None and self.appearance.references is not None:labels=self.appearance.read(patches)
        if labels is None or any(p is None for p in labels):
            # Existing neural classifier can recognize familiar glyph styles even
            # when the board frame itself was never supported.
            data=[]
            for p in patches:
                value=cv2.cvtColor(cv2.resize(p[2:-2,2:-2],(48,48)),cv2.COLOR_BGR2RGB).astype(np.float32)/255
                data.append(value.transpose(2,0,1))
            logits=self.model.run(None,{'images':np.asarray(data)})[0]
            prob=np.exp(logits-logits.max(1,keepdims=True));prob/=prob.sum(1,keepdims=True)
            guesses=[CLASSES[int(p.argmax())] if p.max()>.9 else None for p in prob]
            labels=guesses if labels is None else [a or b for a,b in zip(labels,guesses)]
            self.source='棋子分类与皮肤匹配 / '+self.model.get_providers()[0]
        try:
            if any(p is None or p=='_' for p in labels) and self.history_candidates:
                completed=complete_from_history(positions,labels,self.history_candidates(),self.last_flipped)
                if completed is not None:labels=completed;self.source='合法历史辅助 / '+self.appearance.backend
            if any(p is None or p=='_' for p in labels):
                if self.ocr is None:self.ocr=PieceOCR(self.use_gpu)
                indices=[i for i,p in enumerate(labels) if p is None or p=='_']
                decoded=self.ocr.read([patches[i] for i in indices])
                for i,piece in zip(indices,decoded):labels[i]=piece
                self.source=f'中文文字识别 / {self.ocr.backend}'
            partial=[['_']*9 for _ in range(10)]
            for (r,c),piece in zip(positions,labels):partial[r][c]=piece or '_'
            self.partial_board=[list(reversed(row)) for row in reversed(partial)] if self.last_flipped else partial
            if any(p is None or p=='_' for p in labels):raise ValueError('部分棋子被特效遮挡或字体不确定；可等待稳定，或点击“手动校正并续接”')
            shown=[['_']*9 for _ in range(10)]
            for (r,c),piece in zip(positions,labels):shown[r][c]=piece
            board,flipped=oriented(shown)
        except ValueError as error:
            self.failed_key=key;self.failed_message=str(error);raise
        if self.appearance.references is None or trusted_opening:
            self.references=patches;self.reference_labels=labels;self.appearance.learn(patches,labels,persist=trusted_opening)
        self.remember(key,board,flipped)
        return board,flipped,box
