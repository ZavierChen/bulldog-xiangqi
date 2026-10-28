"""Editable board state, input validation and hint result ordering."""
from collections import Counter
from board_bootstrap import possible_turns
from tracker import replay_positions,moved
from vision import fen

START='rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1'

def parse_fen(text):
    parts=text.strip().split()
    if len(parts)<2 or parts[1] not in ('w','b'):raise ValueError('FEN 须包含走棋方：w 红方，b 黑方')
    rows=parts[0].split('/')
    if len(rows)!=10:raise ValueError('棋盘应有 10 行')
    for row in rows:
        if not row or any(c not in '123456789RNBAKCP rnbakcp'.replace(' ','') for c in row):raise ValueError('FEN 中含有未知棋子或空格数字')
        if sum(int(c) if c.isdigit() else 1 for c in row)!=9:raise ValueError('棋盘每行应有 9 格')
    _,board,side=replay_positions(f'{parts[0]} {parts[1]} - - 0 1',[])
    return board,side

def validate(board,side):
    if len(board)!=10 or any(len(row)!=9 for row in board):raise ValueError('棋盘应为 9 路 10 行')
    counts=Counter(p for row in board for p in row if p!='_')
    if counts['K']!=1 or counts['k']!=1:raise ValueError('分析前请各摆一个红帅和黑将')
    for p,n in counts.items():
        if p not in 'RNBAKCPrnbakcp':raise ValueError('未知棋子')
        if n>({'K':1,'P':5}.get(p.upper(),2)):raise ValueError(f'{p} 的数量超过象棋规则')
    advisors={(9,3),(9,5),(8,4),(7,3),(7,5)}
    bishops={(9,2),(9,6),(7,0),(7,4),(7,8),(5,2),(5,6)}
    for r in range(10):
        for c in range(9):
            p=board[r][c];rr=r if p.isupper() else 9-r
            if p.upper()=='A' and (rr,c) not in advisors:raise ValueError('士/仕只能放在本方九宫的斜线上')
            if p.upper()=='B' and (rr,c) not in bishops:raise ValueError('象/相的位置不合法，不能过河')
            if p.upper()=='P' and (rr>6 or (rr>=5 and c%2)):raise ValueError('兵/卒的位置不合法')
    valid=possible_turns(board)
    if not valid:raise ValueError('将帅位置不合法，或将帅照面；请检查摆棋')
    if side not in valid:raise ValueError('未走棋的一方正在被将军，请切换走棋方或调整棋子')

def score_order(line):
    if line['score_type']=='mate':return 100000-line['score'] if line['score']>0 else -100000+abs(line['score'])
    return line['score']

def move_name(board,move):
    from board_view import LABEL
    r,c=9-int(move[1]),ord(move[0])-97;rr,cc=9-int(move[3]),ord(move[2])-97
    p=board[r][c];red=p.isupper();numbers='一二三四五六七八九' if red else '123456789'
    file=lambda col:numbers[8-col if red else col]
    if r==rr:return LABEL[p]+file(c)+'平'+file(cc)
    direction='进' if (rr<r if red else rr>r) else '退'
    target=file(cc) if p.upper() in 'NBA' else numbers[abs(rr-r)-1]
    return LABEL[p]+file(c)+direction+target

class SandboxModel:
    def __init__(self):
        self.board,self.side=parse_fen(START);self.undo_stack=[]
    def remember(self):
        self.undo_stack.append(([row.copy() for row in self.board],self.side))
        if len(self.undo_stack)>100:self.undo_stack.pop(0)
    def place(self,row,col,piece):
        if self.board[row][col]==piece:return
        self.remember();self.board[row][col]=piece
    def move(self,origin,destination):
        if origin==destination or self.board[origin[0]][origin[1]]=='_':return
        self.remember();self.board[destination[0]][destination[1]]=self.board[origin[0]][origin[1]];self.board[origin[0]][origin[1]]='_'
    def load(self,board,side):
        self.remember();self.board=[row.copy() for row in board];self.side=side
    def undo(self):
        if self.undo_stack:self.board,self.side=self.undo_stack.pop()
    def export(self):return fen(self.board,self.side)
    def apply(self,move):
        self.remember();self.board=moved(self.board,move);self.side='b' if self.side=='w' else 'w'
