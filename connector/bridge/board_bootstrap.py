"""Board-first turn/control assumptions and bounded no-avatar calibration."""
import json
from tracker import replay_positions
from vision import fen

class CalibrationRequired(RuntimeError):pass

def attacked(board,row,col,side):
    for r in range(10):
        for c in range(9):
            p=board[r][c]
            if p=='_' or p.isupper()!=(side=='w'):continue
            dr=row-r;dc=col-c;kind=p.upper()
            if kind in ('R','C','K') and (dr==0 or dc==0):
                sr=0 if not dr else (1 if dr>0 else -1);sc=0 if not dc else (1 if dc>0 else -1)
                if not(sr or sc):continue
                rr,cc=r+sr,c+sc;count=0
                while (rr,cc)!=(row,col):
                    count+=board[rr][cc]!='_';rr+=sr;cc+=sc
                if kind=='R' and count==0:return True
                if kind=='C' and count==1:return True
                if kind=='K' and count==0 and (dc==0 or abs(dr)+abs(dc)==1):return True
            if kind=='N' and sorted((abs(dr),abs(dc)))==[1,2]:
                lr=r+(dr//2 if abs(dr)==2 else 0);lc=c+(dc//2 if abs(dc)==2 else 0)
                if board[lr][lc]=='_':return True
            if kind=='P':
                if dc==0 and dr==(-1 if side=='w' else 1):return True
                if dr==0 and abs(dc)==1 and (r<=4 if side=='w' else r>=5):return True
            if kind=='A' and abs(dr)==abs(dc)==1:return True
            if kind=='B' and abs(dr)==abs(dc)==2 and board[(r+row)//2][(c+col)//2]=='_':return True
    return False

def possible_turns(board):
    red=[(r,c) for r in range(10) for c in range(9) if board[r][c]=='K']
    black=[(r,c) for r in range(10) for c in range(9) if board[r][c]=='k']
    if len(red)!=1 or len(black)!=1:return set()
    if not(7<=red[0][0]<=9 and 3<=red[0][1]<=5 and 0<=black[0][0]<=2 and 3<=black[0][1]<=5):return set()
    # Only the side to move may be in check; this also rejects facing generals
    # before a guessed FEN can be sent to the native engine.
    turns=set()
    if not attacked(board,*black[0],'w'):turns.add('w')
    if not attacked(board,*red[0],'b'):turns.add('b')
    return turns

def saved_turn(board,path):
    if not path:return None
    try:
        with open(path,encoding='utf-8') as f:data=json.load(f)
        _,old,side=replay_positions(data['initial'],data['moves'])
        if old==board and data['current']==fen(board,side):return side
    except (OSError,ValueError,KeyError,TypeError,IndexError):pass
    return None

def resolve(board,flipped,hint,history_path,mode,player,turn):
    valid=possible_turns(board)
    if not valid:raise ValueError('棋盘已识别，但将帅位置或受将关系不合理，等待稳定画面')
    ours=('b' if flipped else 'w') if player=='bottom' else player
    relative=turn in ('ours','other')
    if turn=='ours':turn=ours
    elif turn=='other':turn='b' if ours=='w' else 'w'
    if mode=='grid':
        history=saved_turn(board,history_path)
        if history in valid:return history,ours,False,'两点定位：已有走法历史'
        return (turn if turn in valid else next(iter(valid))),ours,True,'两点定位：先手假设，等待实际变化验证'
    if mode!='auto':
        if turn not in valid:raise CalibrationRequired('棋盘已识别，所选走棋方与受将局面矛盾，请重新指定红/黑走棋')
        return turn,ours,False,'手动指定'
    history=saved_turn(board,history_path)
    if history in valid:return history,ours,False,'已有走法历史'
    if hint in valid:return hint,ours,False,'界面提示'
    if relative and turn not in valid:raise CalibrationRequired('棋盘已识别，所选先手与受将局面矛盾；请改选“我方先手/对方先手”')
    guessed=turn if turn in valid else next(iter(valid))
    return guessed,ours,True,'无头像临时假设'
