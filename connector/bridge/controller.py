"""State machine for the practice bridge; window I/O is injected by an adapter."""
import os,json,tempfile,copy
from tracker import Tracker,moved,RepetitionBlocked,replay_positions
from vision import cv2,np
from board_bootstrap import resolve,possible_turns
from vision import fen
from visual_stability import stable_pieces

def advance_manual_confirmation(engine,board,side,observed):
    """The opponent may finish one legal move while the editor is open."""
    if observed==board:return board,side,False
    initial=fen(board,side)
    matches=[move for move in engine.legal(initial,[]) if moved(board,move)==observed]
    if len(matches)!=1:raise ValueError('校正后画面与棋盘不一致，且不能唯一对应对方的一步合法走法')
    return observed,('b' if side=='w' else 'w'),True

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
        self.predicted_lines=[];self.last_resync_reused=False
        self.await_initial_change=False
        self.recognition_cache=None
    def recognition_candidates(self):
        if self.tracker is None:return []
        identity=(self.tracker.initial,tuple(self.tracker.moves),self.pending)
        if self.recognition_cache and self.recognition_cache[0]==identity:return self.recognition_cache[1]
        board=self.tracker.board;moves=self.tracker.moves.copy();candidates=[board]
        if self.pending:
            if self.pending not in self.tracker.legal():return candidates
            board=moved(board,self.pending);moves.append(self.pending);candidates.append(board)
        candidates.extend(moved(board,m) for m in self.engine.legal(self.tracker.initial,moves))
        self.recognition_cache=(identity,candidates);return candidates
    def observe_pair(self,first,second):
        self.recognizer.history_candidates=self.recognition_candidates
        a,af,abox=self.recognizer.read(first); b,bf,bbox=self.recognizer.read(second)
        if a!=b or af!=bf or abox!=bbox:raise ValueError('画面不稳定，等待动画或遮挡消失')
        if not stable_pieces(first,second,a,abox,af):raise ValueError('棋子主体仍被特效或动画遮挡，保留局面等待稳定')
        self.flipped=af;self.box=abox
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
        if self.tracker is not None and self.provisional and a!=self.tracker.board:
            if self.pending is None or a!=moved(self.tracker.board,self.pending):self.accept_initial_opponent(a)
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
                old_analysis={name:copy.deepcopy(getattr(self.tracker,name)) for name in ('current_plan','pv_hint','ponder_hint','last_evaluation','last_ponder','expected_lines')}
                self.tracker.accept_move(self.pending)
                try:
                    try:self.tracker.reconcile(a)
                    except ValueError:
                        if not self.tracker.reconcile_known(a,self.predicted_lines):raise
                except Exception:
                    self.tracker.board=before;self.tracker.moves=oldmoves;self.tracker.side=oldside
                    self.tracker.check_positions=oldchecks;self.tracker.seen_positions=oldpositions;self.tracker.save()
                    for name,value in old_analysis.items():setattr(self.tracker,name,value)
                    raise ValueError('落子后的棋盘未能匹配本方走法和对手应手')
                self.pending=None
                self.history_confirmed=True
                self.provisional=False;self.turn_source='本方落子及对手应手已验证'
        elif a!=self.tracker.board:
            try:self.tracker.reconcile(a)
            except ValueError:
                if not self.tracker.reconcile_known(a,self.predicted_lines):raise
            self.history_confirmed=True
        if not complete and turn1 is not None and turn1!=self.tracker.side:
            raise ValueError('头像提示与局面走棋方不一致，等待确认')
        self.observed_board=copy.deepcopy(a)
        if self.output_path:
            path=self.output_path; os.makedirs(os.path.dirname(path),exist_ok=True)
            with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=os.path.dirname(path),delete=False) as f:
                json.dump({'fen':self.tracker.initial,'moves':self.tracker.moves,'side':self.tracker.side},f)
                tmp=f.name
            os.replace(tmp,path)
        self.completed=complete
        if complete:return 'complete'
        if self.history_confirmed:self.await_initial_change=False
        if self.tracker.side!=self.ours:return 'waiting'
        return 'ready' if self.may_move(turn1) else 'turn_unconfirmed'
    def may_move(self,turn):
        if self.await_initial_change:return False
        if self.tracker is None or self.tracker.side!=self.ours:return False
        return turn==self.ours or (turn is None and self.turn_known)
    def accept_initial_opponent(self,board):
        """A failed first probe must not invent an own move in the history."""
        if not self.provisional or self.tracker.moves:return False
        other='b' if self.ours=='w' else 'w'
        before=self.tracker.board
        if other not in possible_turns(before):return False
        initial=fen(before,other)
        matches=[move for move in self.engine.legal(initial,[]) if moved(before,move)==board]
        if len(matches)!=1:return False
        self.tracker=Tracker(self.engine,before,other)
        self.tracker.history_path=self.history_path;self.tracker.accept_move(matches[0])
        self.pending=None;self.history_confirmed=True;self.provisional=False
        self.turn_source='对方实际走法已验证，轮到本方'
        self.await_initial_change=False
        return True
    def prepare(self,ms=3000):
        if self.pending is not None:raise ValueError('上一着还未被棋盘确认')
        if self.tracker.side!=self.ours:raise ValueError('尚未轮到本方')
        move=self.tracker.best_safe(ms)
        if move not in self.tracker.legal():raise ValueError('引擎走法不合法')
        return move
    def resync_pair(self,first,second,preserve_analysis=True):
        self.recognizer.history_candidates=self.recognition_candidates
        a,af,abox=self.recognizer.read(first);b,bf,bbox=self.recognizer.read(second)
        if a!=b or af!=bf or abox!=bbox:raise ValueError('重连画面尚未稳定')
        self.last_resync_reused=False
        old_moves=[] if self.tracker is None else self.tracker.moves.copy()
        expected_ours=('b' if af else 'w') if self.player=='bottom' else self.player
        new_game=False
        if preserve_analysis and self.tracker is not None and self.ours==expected_ours and not self.completed:
            try:
                self.observe_pair(first,second)
                self.last_resync_reused=True
                self.turn_source='重连已核对历史，保留既有计算'
                return old_moves
            except ValueError as error:
                from sandbox_model import START
                new_game=a==replay_positions(START,[])[1] and a!=self.tracker.board
                if not new_game:
                    raise ValueError('变化暂时无法匹配合法历史，保留原棋盘与计算等待稳定；也可手动校正并续接') from error
        hint=None
        if self.mode=='auto':
            if hasattr(self.recognizer,'observe_turn_pair'):self.recognizer.observe_turn_pair(first,second,abox,af)
            one=self.recognizer.practice_turn(first,abox,af);two=self.recognizer.practice_turn(second,bbox,bf)
            if one==two:hint=one
        turn,ours,provisional,source=resolve(a,af,hint,self.history_path,self.mode,self.player,self.initial_turn)
        checks={} if self.tracker is None or new_game else {s:set(v) for s,v in self.tracker.check_positions.items()}
        positions=set() if self.tracker is None or new_game else self.tracker.seen_positions.copy()
        self.tracker=Tracker(self.engine,a,turn,self.history_path);self.ours=ours
        if checks:
            self.tracker.check_positions=checks
        self.tracker.seen_positions.update(positions);self.tracker.save()
        self.pending=None;self.flipped=af;self.box=abox;self.completed=False
        self.history_confirmed=False
        self.turn_known=True
        self.provisional=provisional;self.turn_source=source;self.observed_board=a
        self.await_initial_change=False
        return old_moves
    def submitted(self,move):
        if self.pending is not None:raise ValueError('正在等待上一着')
        if self.tracker.repetition_risk(move):raise RepetitionBlocked('落子前发现重复循环风险，已停止自动落子')
        self.pending=move

    def confirm_board(self,board,side,flipped,box):
        from sandbox_model import validate
        validate(board,side);retained=False
        if self.tracker is not None:
            if self.tracker.board==board and self.tracker.side==side:retained=True
            elif self.tracker.reconcile_known(board,self.predicted_lines,side=side):retained=True
            elif self.tracker.side!=side:
                try:self.tracker.reconcile(board);retained=self.tracker.side==side
                except ValueError:pass
        if not retained:self.tracker=Tracker(self.engine,board,side,self.history_path)
        self.tracker.history_path=self.history_path;self.tracker.save()
        self.ours='b' if flipped else 'w';self.flipped=flipped;self.box=box
        self.pending=None;self.provisional=False;self.await_initial_change=False
        self.turn_known=True;self.history_confirmed=True;self.completed=False;self.observed_board=board
        self.turn_source='手动校正已确认，'+('沿用历史与计算' if retained else '已重建合法局面')
        return retained
