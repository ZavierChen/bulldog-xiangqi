"""State machine for the practice bridge; window I/O is injected by an adapter."""
import os,json,tempfile
from tracker import Tracker,moved,RepetitionBlocked
from vision import cv2,np
from board_bootstrap import resolve

class Bridge:
    def __init__(self,recognizer,engine,output_path=None,history_path=None,mode='auto',player='bottom',initial_turn='w'):
        self.recognizer=recognizer;self.engine=engine;self.output_path=output_path
        self.tracker=None;self.pending=None;self.flipped=None;self.box=None;self.ours=None
        self.completed=False
        self.history_path=history_path
        self.history_confirmed=False
        self.turn_known=False
        self.mode=mode;self.player=player;self.initial_turn=initial_turn
        self.provisional=False;self.turn_source='等待棋盘';self.observed_board=None
    def observe_pair(self,first,second):
        a,af,abox=self.recognizer.read(first); b,bf,bbox=self.recognizer.read(second)
        if a!=b or af!=bf or abox!=bbox:raise ValueError('画面不稳定，等待动画或遮挡消失')
        x,y,w,h=abox
        before=cv2.cvtColor(first[y:y+h,x:x+w],cv2.COLOR_BGR2GRAY)
        after=cv2.cvtColor(second[y:y+h,x:x+w],cv2.COLOR_BGR2GRAY)
        if float((cv2.absdiff(before,after)>18).mean())>.0025:
            raise ValueError('画面不稳定，棋子动画尚未结束')
        self.observed_board=a;self.flipped=af;self.box=abox
        complete=self.recognizer.practice_complete(first,abox) and self.recognizer.practice_complete(second,bbox)
        if self.completed and a!=self.tracker.board:self.turn_known=False
        if (self.tracker is None or not self.turn_known) and self.mode=='auto':
            if hasattr(self.recognizer,'observe_turn_pair'):self.recognizer.observe_turn_pair(first,second,abox,af)
            turn1=self.recognizer.practice_turn(first,abox,af);turn2=self.recognizer.practice_turn(second,bbox,bf)
            if turn1!=turn2:turn1=turn2=None
        else:turn1=turn2=None
        self.flipped=af;self.box=abox
        if self.completed and self.pending is None and a!=self.tracker.board:
            self.tracker=None;self.completed=False
        if self.tracker is None:
            side,self.ours,self.provisional,self.turn_source=resolve(a,af,turn1,self.history_path,self.mode,self.player,self.initial_turn)
            self.tracker=Tracker(self.engine,a,side,self.history_path);turn1=None
            self.turn_known=True
        elif self.pending is not None:
            predicted=moved(self.tracker.board,self.pending)
            if a==self.tracker.board:return 'awaiting_move'
            if a==predicted:
                self.tracker.accept_move(self.pending);self.pending=None;self.history_confirmed=True
                self.provisional=False;self.turn_source='本方落子已验证'
            else:
                before=self.tracker.board;oldmoves=self.tracker.moves.copy();oldside=self.tracker.side
                oldchecks={s:set(v) for s,v in self.tracker.check_positions.items()}
                oldpositions=self.tracker.seen_positions.copy()
                self.tracker.accept_move(self.pending)
                try:self.tracker.reconcile(a)
                except Exception:
                    self.tracker.board=before;self.tracker.moves=oldmoves;self.tracker.side=oldside
                    self.tracker.check_positions=oldchecks;self.tracker.seen_positions=oldpositions;self.tracker.save()
                    raise ValueError('落子后的棋盘未能匹配本方走法和对手应手')
                self.pending=None
                self.history_confirmed=True
                self.provisional=False;self.turn_source='本方落子及对手应手已验证'
        elif a!=self.tracker.board:
            self.tracker.reconcile(a);self.history_confirmed=True
        if not complete and turn1 is not None and turn1!=self.tracker.side:
            raise ValueError('头像提示与局面走棋方不一致，等待确认')
        if self.output_path:
            path=self.output_path; os.makedirs(os.path.dirname(path),exist_ok=True)
            with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=os.path.dirname(path),delete=False) as f:
                json.dump({'fen':self.tracker.initial,'moves':self.tracker.moves,'side':self.tracker.side},f)
                tmp=f.name
            os.replace(tmp,path)
        self.completed=complete
        if complete:return 'complete'
        if self.tracker.side!=self.ours:return 'waiting'
        return 'ready' if self.may_move(turn1) else 'turn_unconfirmed'
    def may_move(self,turn):
        if self.tracker is None or self.tracker.side!=self.ours:return False
        return turn==self.ours or (turn is None and self.turn_known)
    def prepare(self,ms=3000):
        if self.pending is not None:raise ValueError('上一着还未被棋盘确认')
        if self.tracker.side!=self.ours:raise ValueError('尚未轮到本方')
        move=self.tracker.best_safe(ms)
        if move not in self.tracker.legal():raise ValueError('引擎走法不合法')
        return move
    def resync_pair(self,first,second):
        a,af,abox=self.recognizer.read(first);b,bf,bbox=self.recognizer.read(second)
        if a!=b or af!=bf or abox!=bbox:raise ValueError('重连画面尚未稳定')
        hint=None
        if self.mode=='auto':
            if hasattr(self.recognizer,'observe_turn_pair'):self.recognizer.observe_turn_pair(first,second,abox,af)
            one=self.recognizer.practice_turn(first,abox,af);two=self.recognizer.practice_turn(second,bbox,bf)
            if one==two:hint=one
        turn,ours,provisional,source=resolve(a,af,hint,self.history_path,self.mode,self.player,self.initial_turn)
        old_moves=[] if self.tracker is None else self.tracker.moves.copy()
        checks={} if self.tracker is None else {s:set(v) for s,v in self.tracker.check_positions.items()}
        positions=set() if self.tracker is None else self.tracker.seen_positions.copy()
        self.tracker=Tracker(self.engine,a,turn,self.history_path);self.ours=ours
        if checks:
            self.tracker.check_positions=checks
        self.tracker.seen_positions.update(positions);self.tracker.save()
        self.pending=None;self.flipped=af;self.box=abox;self.completed=False
        self.history_confirmed=False
        self.turn_known=True
        self.provisional=provisional;self.turn_source=source;self.observed_board=a
        return old_moves
    def submitted(self,move):
        if self.pending is not None:raise ValueError('正在等待上一着')
        if self.tracker.repetition_risk(move):raise RepetitionBlocked('落子前发现重复循环风险，已停止自动落子')
        self.pending=move
