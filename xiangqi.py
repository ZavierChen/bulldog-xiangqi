import os, re, random, subprocess, threading, queue, tkinter as tk
from tkinter import messagebox, simpledialog
from connector.bridge.branding import apply_brand

ROOT = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(ROOT, 'engine', 'pikafish.exe')
START = 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1'
LABEL = {'r':'車','n':'馬','b':'象','a':'士','k':'将','c':'炮','p':'卒',
         'R':'车','N':'马','B':'相','A':'仕','K':'帅','C':'炮','P':'兵'}

class Game:
    def __init__(self, root):
        self.root = root
        apply_brand(root,'本地象棋')
        root.resizable(False, False)
        self.status = tk.StringVar(value='正在启动引擎…')
        self.base_fen = START
        self.time = tk.IntVar(value=5)
        self.threads = tk.IntVar(value=os.cpu_count() or 1)
        self.level = tk.IntVar(value=5)
        self.auto_black = tk.BooleanVar(value=False)
        self.auto_red = tk.BooleanVar(value=False)
        self.flipped = tk.BooleanVar(value=False)
        self.last_move = tk.StringVar(value='上一步：尚未走棋')
        bar = tk.Frame(root); bar.pack(pady=5)
        tk.Button(bar, text='重新开始', command=self.reset).pack(side='left', padx=5)
        tk.Button(bar, text='悔棋', command=self.undo).pack(side='left', padx=5)
        tk.Button(bar, text='电脑走一步', command=self.engine_move).pack(side='left', padx=5)
        tk.Button(bar, text='翻转棋盘', command=self.flip).pack(side='left', padx=5)
        tk.Button(bar, text='导入局面', command=self.import_position).pack(side='left', padx=5)
        tk.Label(bar, text='电脑思考秒数：').pack(side='left')
        tk.Spinbox(bar, from_=1, to=30, width=4, textvariable=self.time).pack(side='left')
        options = tk.Frame(root); options.pack(pady=2)
        tk.Label(options, text='棋力等级（1–5）：').pack(side='left')
        tk.Spinbox(options, from_=1, to=5, width=4, textvariable=self.level).pack(side='left')
        tk.Label(options, text='    CPU 线程：').pack(side='left')
        tk.Spinbox(options, from_=1, to=os.cpu_count() or 1, width=4, textvariable=self.threads).pack(side='left')
        tk.Checkbutton(options, text='电脑执红', variable=self.auto_red, command=self.auto_changed).pack(side='left')
        tk.Checkbutton(options, text='电脑执黑', variable=self.auto_black, command=self.auto_changed).pack(side='left')
        self.canvas = tk.Canvas(root, width=540, height=600, bg='#eecb91', highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self.click)
        tk.Label(root, textvariable=self.last_move, anchor='w', width=58, fg='#9c360d', font=('Microsoft YaHei', 10, 'bold')).pack(padx=8, pady=(5, 0))
        tk.Label(root, textvariable=self.status, anchor='w', width=58).pack(padx=8, pady=7)
        self.events = queue.Queue(); self.moves = []; self.legal = []; self.selected = None
        self.busy = True; self.generation = 0; self.proc = None
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.draw(); root.after(50, self.poll)
        threading.Thread(target=self.start, daemon=True).start()

    def start(self):
        try:
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            self.proc = subprocess.Popen([ENGINE], cwd=os.path.dirname(ENGINE), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=flags)
            self.send('uci'); self.read_until(lambda s: s == 'uciok')
            self.send('setoption name Threads value '+str(os.cpu_count() or 1)); self.send('setoption name Hash value 512')
            self.send('isready'); self.read_until(lambda s: s == 'readyok')
            self.events.put(('ready', None))
        except Exception as e: self.events.put(('error', str(e)))

    def send(self, cmd):
        self.proc.stdin.write(cmd+'\n'); self.proc.stdin.flush()
    def read_until(self, predicate):
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if not line: raise RuntimeError('引擎已退出')
            s = line.strip(); lines.append(s)
            if predicate(s): return lines
    def position(self, moves):
        self.send('position fen '+self.base_fen + (' moves '+' '.join(moves) if moves else ''))
    def analyze(self, kind, generation, moves, seconds=5, level=5, threads=1):
        try:
            if kind == 'legal':
                self.position(moves)
                self.send('go perft 1')
                lines = self.read_until(lambda s: s.startswith('Nodes searched:'))
                legal = [m.group(1) for s in lines if (m := re.match(r'^([a-i][0-9][a-i][0-9]):\s*\d+', s))]
                self.events.put(('legal', (generation, legal)))
            else:
                # Lower levels search fewer plies and sometimes choose a weaker candidate.
                candidates = (5, 4, 3, 2, 1)[level-1]
                self.send('setoption name Threads value '+str(threads))
                self.send('setoption name MultiPV value '+str(candidates))
                self.position(moves)
                depth = (3, 5, 8, 13, 0)[level-1]
                self.send('go movetime '+str(seconds*1000) + (' depth '+str(depth) if depth else ''))
                lines = self.read_until(lambda s: s.startswith('bestmove '))
                best = lines[-1].split()[1]
                choices = {}
                for line in lines:
                    match = re.search(r'\bmultipv (\d+)\b.*\bpv ([a-i][0-9][a-i][0-9])\b', line)
                    if match: choices[int(match.group(1))] = match.group(2)
                if level < 5 and choices:
                    available = [choices[i] for i in sorted(choices) if i <= candidates]
                    if available: best = random.choice(available)
                self.events.put(('move', (generation, best)))
        except Exception as e: self.events.put(('error', str(e)))
    def request_legal(self):
        self.busy = True; self.status.set('正在检查局面…')
        threading.Thread(target=self.analyze, args=('legal', self.generation, list(self.moves)), daemon=True).start()
    def poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                if kind == 'error':
                    self.busy = True; self.status.set('引擎错误：'+val); messagebox.showerror('引擎错误', val)
                elif kind == 'ready': self.request_legal()
                elif kind == 'legal':
                    gen, legal = val
                    if gen == self.generation:
                        self.legal = legal; self.busy = False
                        if not legal: self.status.set('对局结束：当前一方没有合法走法。')
                        elif self.auto_for_turn(): self.engine_move()
                        else: self.status.set(('红方' if self.red_turn() else '黑方')+'走棋：手动走棋，或点击电脑走一步。')
                elif kind == 'move':
                    gen, move = val
                    if gen == self.generation:
                        if move in ('(none)', '0000'): self.busy=False; self.status.set('对局结束：电脑没有合法走法。')
                        else: self.moves.append(move); self.draw(); self.request_legal()
        except queue.Empty: pass
        self.root.after(50, self.poll)
    def board(self, moves=None):
        b = {}
        for y, row in enumerate(self.base_fen.split()[0].split('/')):
            x = 0
            for c in row:
                if c.isdigit(): x += int(c)
                else: b[(x, y)] = c; x += 1
        for m in (self.moves if moves is None else moves):
            a=(ord(m[0])-97, 9-int(m[1])); z=(ord(m[2])-97, 9-int(m[3]))
            if a in b: b[z] = b.pop(a)
        return b
    def draw(self):
        c=self.canvas; c.delete('all'); ox,oy,step=46,38,56
        for y in range(10): c.create_line(ox,oy+y*step,ox+8*step,oy+y*step,fill='#593719',width=2)
        for x in range(9):
            for a,b in ((0,4),(5,9)) if 0<x<8 else ((0,9),): c.create_line(ox+x*step,oy+a*step,ox+x*step,oy+b*step,fill='#593719',width=2)
        for y in (0,7):
            c.create_line(ox+3*step,oy+y*step,ox+5*step,oy+(y+2)*step,fill='#593719')
            c.create_line(ox+5*step,oy+y*step,ox+3*step,oy+(y+2)*step,fill='#593719')
        c.create_text(ox+4*step,oy+4.5*step,text='楚 河              汉 界',font=('Microsoft YaHei',16),fill='#704a29')
        if self.moves:
            move=self.moves[-1]
            sx,sy=ord(move[0])-97,9-int(move[1]); tx,ty=ord(move[2])-97,9-int(move[3])
            piece=self.board(self.moves[:-1]).get((sx,sy))
            for x,y in ((sx,sy),(tx,ty)):
                if self.flipped.get(): x,y=8-x,9-y
                px,py=ox+x*step,oy+y*step
                c.create_oval(px-27,py-27,px+27,py+27,outline='#15803d',width=4)
            if piece:
                side='红方' if piece.isupper() else '黑方'
                if self.flipped.get(): sx,sy,tx,ty=8-sx,9-sy,8-tx,9-ty
                self.last_move.set(f'上一步：{side}{LABEL[piece]}　第 {sy+1} 行第 {sx+1} 列 → 第 {ty+1} 行第 {tx+1} 列（从左上数）')
        else: self.last_move.set('上一步：尚未走棋')
        for (x,y),piece in self.board().items():
            selected=(x,y)==self.selected
            if self.flipped.get(): x,y=8-x,9-y
            px,py=ox+x*step,oy+y*step
            c.create_oval(px-23,py-23,px+23,py+23,fill='#ffebbd',outline='#d43220' if selected else '#75451f',width=3 if selected else 2)
            c.create_text(px,py,text=LABEL[piece],font=('Microsoft YaHei',20,'bold'),fill='#bd201c' if piece.isupper() else '#252525')
    def click(self, event):
        if self.busy or not self.legal: return
        x=round((event.x-46)/56); y=round((event.y-38)/56)
        if not (0<=x<9 and 0<=y<10) or abs(event.x-(46+x*56))>26 or abs(event.y-(38+y*56))>26: return
        if self.flipped.get(): x,y=8-x,9-y
        board=self.board()
        if self.selected:
            sx,sy=self.selected; move=chr(97+sx)+str(9-sy)+chr(97+x)+str(9-y)
            if move in self.legal:
                self.moves.append(move); self.selected=None; self.draw(); self.request_legal(); return
        piece=board.get((x,y),'')
        self.selected=(x,y) if piece and piece.isupper() == self.red_turn() else None
        self.draw()
    def auto_changed(self):
        if not self.busy and self.auto_for_turn() and self.legal: self.engine_move()
    def auto_for_turn(self):
        return self.auto_red.get() if self.red_turn() else self.auto_black.get()
    def red_turn(self):
        return (self.base_fen.split()[1] == 'w') == (len(self.moves)%2 == 0)
    def import_position(self):
        if self.busy: self.status.set('请等引擎完成当前计算。'); return
        fen=simpledialog.askstring('导入局面', '粘贴中国象棋 FEN（包含走棋方 w 或 b）：', parent=self.root)
        if fen is None: return
        try:
            fields=fen.strip().split()
            rows=fields[0].split('/')
            if len(fields)<2 or fields[1] not in ('w','b') or len(rows)!=10: raise ValueError()
            if any(sum(int(c) if c.isdigit() else 1 for c in row)!=9 or any(c not in '123456789rnbakcpRNBAKCP' for c in row) for row in rows): raise ValueError()
            if fields[0].count('K')!=1 or fields[0].count('k')!=1: raise ValueError()
            normalized=fields[0]+' '+fields[1]+' - - 0 1'
        except (ValueError, IndexError):
            messagebox.showerror('局面格式错误', '请检查 FEN：必须有 10 行、每行 9 格，且各有一个将和帅。'); return
        self.base_fen=normalized; self.generation+=1; self.moves=[]; self.selected=None
        self.auto_red.set(False); self.auto_black.set(False); self.draw(); self.request_legal()
    def flip(self):
        self.flipped.set(not self.flipped.get()); self.draw()
    def engine_move(self):
        if self.busy or not self.legal: return
        self.busy=True; self.selected=None; self.draw(); self.status.set('电脑正在思考…')
        try: seconds=max(1,min(30,int(self.time.get())))
        except (ValueError, tk.TclError): seconds=5
        try: level=max(1,min(5,int(self.level.get())))
        except (ValueError, tk.TclError): level=5
        try: threads=max(1,min(os.cpu_count() or 1,int(self.threads.get())))
        except (ValueError, tk.TclError): threads=os.cpu_count() or 1
        threading.Thread(target=self.analyze,args=('move',self.generation,list(self.moves),seconds,level,threads),daemon=True).start()
    def reset(self):
        if self.busy: self.status.set('请等引擎完成当前计算。'); return
        self.base_fen=START; self.generation+=1; self.moves=[]; self.selected=None; self.draw(); self.request_legal()
    def undo(self):
        if self.busy: self.status.set('请等引擎完成当前计算。'); return
        if self.moves:
            self.auto_red.set(False); self.auto_black.set(False)
            self.generation+=1; self.moves=self.moves[:-1]; self.selected=None; self.draw(); self.request_legal()
    def close(self):
        if self.proc:
            try: self.proc.kill()
            except OSError: pass
        self.root.destroy()

if __name__ == '__main__':
    root=tk.Tk(); Game(root); root.mainloop()
