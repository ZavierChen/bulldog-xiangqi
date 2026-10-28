"""Keep the side to move and move history in sync with observed legal positions."""
import os,re,subprocess,json,tempfile,threading,time
from vision import fen

class RepetitionBlocked(RuntimeError):pass

def read_wdl(line):
    match=re.search(r'\bwdl (\d+) (\d+) (\d+)\b',line)
    if not match:return None
    values=[int(v) for v in match.groups()]
    return values if sum(values)==1000 else None

def position_key(board,side):return fen(board,side).split(' - ')[0]

def replay_positions(initial,moves):
    rows=initial.split()[0].split('/');board=[];side=initial.split()[1]
    for text in rows:
        row=[]
        for char in text:row.extend(['_']*int(char) if char.isdigit() else [char])
        if len(row)!=9:raise ValueError('历史棋盘格式不正确')
        board.append(row)
    if len(board)!=10 or side not in ('w','b'):raise ValueError('历史局面格式不正确')
    keys={position_key(board,side)}
    for move in moves:
        board=moved(board,move);side='b' if side=='w' else 'w';keys.add(position_key(board,side))
    return keys,board,side

class Engine:
    def __init__(self, path, threads=1, hash_mb=256):
        self.last_pv=[];self.last_depth=0;self.last_score=None
        self.on_evaluation=None
        self.threads=max(1,threads)
        self.write_lock=threading.Lock()
        self.close_lock=threading.Lock()
        self.process=subprocess.Popen([path],cwd=os.path.dirname(path),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.send('uci');self.until('uciok')
        self.send(f'setoption name Threads value {max(1,threads)}');self.send(f'setoption name Hash value {hash_mb}')
        self.send('setoption name UCI_ShowWDL value true')
        self.send('isready');self.until('readyok')
    def configure_threads(self,threads):
        threads=max(1,threads)
        if self.threads==threads:return
        self.send(f'setoption name Threads value {threads}');self.send('isready');self.until('readyok');self.threads=threads
    def set_background(self,background):
        if os.name!='nt':return
        import ctypes
        from ctypes import wintypes
        handle=wintypes.HANDLE(int(self.process._handle))
        priority=0x4000 if background else 0x20  # BELOW_NORMAL / NORMAL
        if not ctypes.windll.kernel32.SetPriorityClass(handle,priority):
            raise OSError('无法调整预判引擎优先级')
    def send(self,line):
        with self.write_lock:self.process.stdin.write(line+'\n');self.process.stdin.flush()
    def until(self,prefix,on_line=None):
        lines=[]
        while True:
            line=self.process.stdout.readline()
            if not line:raise RuntimeError('引擎已退出')
            s=line.strip();lines.append(s)
            if on_line:on_line(s)
            if s.startswith(prefix):return lines
    def position(self,initial,moves):
        self.send('position fen '+initial+(' moves '+' '.join(moves) if moves else ''))
    def legal(self,initial,moves):
        self.position(initial,moves);self.send('go perft 1')
        return [m.group(1) for line in self.until('Nodes searched:') if (m:=re.match(r'^([a-i][0-9][a-i][0-9]):\s*\d+',line))]
    def checking(self,initial,moves):
        self.position(initial,moves);self.send('d');self.send('isready')
        lines=self.until('readyok');values=[line.split(':',1)[1].strip() for line in lines if line.startswith('Checkers:')]
        if len(values)!=1:raise ValueError('引擎未能确认将军状态')
        return bool(values[0])
    def best(self,initial,moves,ms,allowed=None):
        if allowed is not None and not allowed:raise RepetitionBlocked('没有可避免长将、长捉循环的走法，已停止自动落子')
        self.position(initial,moves);self.send('go movetime '+str(ms)+(' searchmoves '+' '.join(allowed) if allowed is not None else ''))
        last_notice=[0.]
        def report(line):
            if self.on_evaluation is None or time.monotonic()-last_notice[0]<.3:return
            if 'upperbound' in line or 'lowerbound' in line:return
            match=re.search(r'^info depth (\d+).*?\bscore (cp|mate) (-?\d+)',line)
            if not match or int(match[1])<8 or ' pv ' not in line:return
            last_notice[0]=time.monotonic()
            self.on_evaluation({'depth':int(match[1]),'score_type':match[2],'score':int(match[3]),'wdl':read_wdl(line)})
        lines=self.until('bestmove ',report);move=lines[-1].split()[1]
        if not re.fullmatch('[a-i][0-9][a-i][0-9]',move): raise ValueError('当前局面没有走法')
        self.last_pv=[];self.last_depth=0;self.last_score=None;score_depth=0
        for line in lines:
            match=re.search(r'^info depth (\d+).*\bpv ((?:[a-i][0-9][a-i][0-9](?:\s+|$))+)',line)
            if match:
                pv=match.group(2).split();depth=int(match.group(1))
                if pv and pv[0]==move and depth>=self.last_depth and 'upperbound' not in line and 'lowerbound' not in line:
                    if len(pv)>=3 or not self.last_pv:self.last_pv=pv;self.last_depth=depth
                if pv and pv[0]==move and depth>=score_depth and 'upperbound' not in line and 'lowerbound' not in line:
                    score=re.search(r'\bscore (cp|mate) (-?\d+)',line)
                    if score:self.last_score={'score_type':score[1],'score':int(score[2]),'depth':depth,'wdl':read_wdl(line)};score_depth=depth
        return move
    def close(self):
        with self.close_lock:
            if self.process.poll() is None:self.process.kill();self.process.wait()
            for pipe in (self.process.stdin,self.process.stdout):
                if pipe is not None and not pipe.closed:pipe.close()
    def analyze(self,initial,moves,branches,stop,on_info):
        """Stream MultiPV on a dedicated process; another thread may send stop."""
        count=min(max(1,branches),len(self.legal(initial,moves)))
        if not count or stop.is_set():return
        self.send(f'setoption name MultiPV value {count}');self.send('isready');self.until('readyok')
        if stop.is_set():return
        self.position(initial,moves);self.send('go infinite')
        if stop.is_set():self.send('stop')
        while True:
            raw=self.process.stdout.readline()
            if not raw:raise RuntimeError('后台预判引擎已退出')
            line=raw.strip()
            if line.startswith('bestmove '):break
            if stop.is_set():continue
            match=re.search(r'^info depth (\d+).*?\bmultipv (\d+)\s+score (cp|mate) (-?\d+).*?\bpv ((?:[a-i][0-9][a-i][0-9](?:\s+|$))+)',line)
            if match and 'upperbound' not in line and 'lowerbound' not in line:
                depth,rank,kind,score,pv=match.groups()
                on_info({'depth':int(depth),'rank':int(rank),'score_type':kind,'score':int(score),'pv':pv.split(),'branches':count,'wdl':read_wdl(line)})
        self.send('setoption name MultiPV value 1');self.send('isready');self.until('readyok')

    def top_moves(self,initial,ms,branches=3,on_update=None):
        """A single user-requested, bounded MultiPV search for sandbox hints."""
        legal=self.legal(initial,[]);count=min(max(1,branches),len(legal))
        if not count:raise ValueError('当前方没有合法走法，可能已被将死或困毙')
        pending={};latest=[];last_depth=0;last_notice=0
        def info(line):
            nonlocal latest,last_depth,last_notice
            if 'upperbound' in line or 'lowerbound' in line:return
            match=re.search(r'^info depth (\d+).*?\bmultipv (\d+)\s+score (cp|mate) (-?\d+).*?\bpv ((?:[a-i][0-9][a-i][0-9](?:\s+|$))+)',line)
            if not match:return
            depth,rank,kind,score,pv=match.groups();depth=int(depth);rank=int(rank)
            pending.setdefault(depth,{})[rank]={'depth':depth,'rank':rank,'score_type':kind,'score':int(score),'pv':pv.split(),'wdl':read_wdl(line)}
            if depth<last_depth or not all(i in pending[depth] for i in range(1,count+1)):return
            lines=[pending[depth][i] for i in range(1,count+1)]
            if any(not v['pv'] or v['pv'][0] not in legal for v in lines):return
            if len({v['pv'][0] for v in lines})!=count:return
            latest=lines;last_depth=depth
            if on_update and time.monotonic()-last_notice>.3:last_notice=time.monotonic();on_update(lines)
            for old in list(pending):
                if old<depth:del pending[old]
        self.send(f'setoption name MultiPV value {count}');self.send('isready');self.until('readyok')
        try:
            self.position(initial,[]);self.send(f'go movetime {max(100,int(ms))}');self.until('bestmove ',info)
        finally:
            if self.process.poll() is None:
                self.send('setoption name MultiPV value 1');self.send('isready');self.until('readyok')
        if not latest:raise ValueError('未得到完整候选走法，请增加思考时间后再试')
        from sandbox_model import score_order
        latest=sorted(latest,key=score_order,reverse=True)
        for rank,line in enumerate(latest,1):line['rank']=rank
        return latest

def moved(board,move):
    out=[row.copy() for row in board]
    a=(9-int(move[1]),ord(move[0])-97); b=(9-int(move[3]),ord(move[2])-97)
    if out[a[0]][a[1]]=='_':raise ValueError('走法起点没有棋子')
    out[b[0]][b[1]]=out[a[0]][a[1]];out[a[0]][a[1]]='_'
    return out

class Tracker:
    def __init__(self,engine,board,side,history_path=None):
        if side not in ('w','b'):raise ValueError('不能仅凭静态局面确定走棋方')
        self.engine=engine;self.board=board;self.side=side;self.initial=fen(board,side);self.moves=[]
        self.history_path=history_path;self.check_positions={'w':set(),'b':set()};self.filtered=[]
        self.pv_hint=None;self.ponder_hint=None;self.last_ponder=None;self.current_plan=None;self.last_source='engine'
        self.seen_positions={position_key(board,side)};self.filtered_reasons={}
        self.last_evaluation=None;self.refine=False
        try:
            with open(os.path.join(os.path.dirname(__file__),'opening-book.json'),encoding='utf-8') as f:self.book=json.load(f)['positions']
        except (OSError,ValueError,KeyError):self.book={}
        if history_path:
            try:
                with open(history_path,encoding='utf-8') as f:data=json.load(f)
                if data['current']==fen(board,side):
                    keys,replayed,replayed_side=replay_positions(data['initial'],data['moves'])
                    if replayed!=board or replayed_side!=side:raise ValueError('历史与当前棋盘不一致')
                    checks={s:set(data['checks'][s]) for s in ('w','b')}
                    positions=keys|set(data.get('seen_positions',[]))
                    self.initial=data['initial'];self.moves=data['moves']
                    self.check_positions=checks;self.seen_positions=positions
            except (OSError,ValueError,KeyError,TypeError):pass
    def legal(self):return self.engine.legal(self.initial,self.moves)
    def accept_move(self,move):
        if move not in self.legal():raise ValueError('走法不合法')
        gives_check=self.engine.checking(self.initial,self.moves+[move])
        mover=self.side;self.board=moved(self.board,move);self.moves.append(move);self.side='b' if self.side=='w' else 'w'
        self.current_plan=None
        self.seen_positions.add(position_key(self.board,self.side))
        if gives_check:self.check_positions[mover].add(fen(self.board,self.side).split(' - ')[0])
        else:self.check_positions[mover].clear()
        self.save()
    def save(self):
        if not self.history_path:return
        data={'initial':self.initial,'moves':self.moves,'current':fen(self.board,self.side),'checks':{s:sorted(self.check_positions[s]) for s in ('w','b')},'seen_positions':sorted(self.seen_positions)}
        directory=os.path.dirname(self.history_path);os.makedirs(directory,exist_ok=True)
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=directory,delete=False) as f:
            json.dump(data,f);temporary=f.name
        os.replace(temporary,self.history_path)
    def would_long_check(self,move):
        if not self.check_positions[self.side]:return False
        nextside='b' if self.side=='w' else 'w'
        key=fen(moved(self.board,move),nextside).split(' - ')[0]
        if key not in self.check_positions[self.side]:return False
        return self.engine.checking(self.initial,self.moves+[move])
    def best_safe(self,ms):
        self.last_evaluation=None
        legal=self.legal();allowed=[];self.filtered=[];self.filtered_reasons={}
        for candidate in legal:
            reason=self.repetition_risk(candidate)
            if reason:self.filtered.append(candidate);self.filtered_reasons[candidate]=reason
            else:allowed.append(candidate)
        if not allowed:raise RepetitionBlocked('全部合法着法都涉及重复循环风险，已停止自动落子，请人工接管')
        if self.has_plan():
            candidate=self.current_plan['move']
            if candidate in allowed and (not self.refine or self.current_plan.get('refined',False)):
                self.last_source='position_cache';return candidate
            self.current_plan=None
        hint=self.ponder_hint;self.ponder_hint=None;self.last_ponder=None
        if not self.refine and hint and self.initial==hint['initial'] and self.moves==hint['prefix'] and position_key(self.board,self.side)==hint['key']:
            candidate=hint['move']
            if candidate in allowed:
                self.last_source='ponder_cache';self.last_ponder=hint
                self.last_evaluation={'score_type':hint['score_type'],'score':-hint['score'],'depth':hint['depth']}
                wdl=hint.get('wdl');self.last_evaluation['wdl']=list(reversed(wdl)) if wdl else None
                self.cache_line(hint.get('continuation',[]));return self.remember_plan(candidate)
        hint=self.pv_hint;self.pv_hint=None
        if not self.refine and hint and self.moves==hint['prefix'] and fen(self.board,self.side).split(' - ')[0]==hint['key']:
            candidate=hint['move']
            if candidate in allowed:
                self.last_source='pv_cache';self.cache_line(hint.get('continuation',[]));return self.remember_plan(candidate)
        key=fen(self.board,self.side).split(' - ')[0]
        candidate=self.book.get(key)
        if candidate and not self.refine:
            if candidate in allowed:self.last_source='opening_book';return self.remember_plan(candidate)
        self.last_source='engine';move=self.engine.best(self.initial,self.moves,ms,allowed=allowed if self.filtered else None)
        if move not in allowed:raise RepetitionBlocked('引擎返回了被防循环限制排除的走法，已停止自动落子')
        self.last_evaluation=getattr(self.engine,'last_score',None)
        pv=getattr(self.engine,'last_pv',[])
        if len(pv)>=3 and pv[0]==move and getattr(self.engine,'last_depth',0)>=10:
            self.cache_line(pv[:7])
        return self.remember_plan(move)
    def repetition_risk(self,move):
        nextside='b' if self.side=='w' else 'w'
        if position_key(moved(self.board,move),nextside) in self.seen_positions:return 'repeated_position'
        if self.would_long_check(move):return 'long_check'
        return None
    def has_plan(self):
        return bool(self.current_plan and self.current_plan['prefix']==self.moves and self.current_plan['key']==fen(self.board,self.side))
    def remember_plan(self,move):
        self.current_plan={'key':fen(self.board,self.side),'prefix':self.moves.copy(),'move':move,'refined':self.refine}
        return move
    def cache_line(self,pv):
        if len(pv)<3:return
        predicted=moved(moved(self.board,pv[0]),pv[1])
        self.pv_hint={'prefix':self.moves+pv[:2],'key':fen(predicted,self.side).split(' - ')[0],'move':pv[2],'continuation':pv[2:]}
    def reconcile(self,observed):
        if observed==self.board:return None
        matches=[move for move in self.legal() if moved(self.board,move)==observed]
        if len(matches)!=1:raise ValueError(f'新局面无法唯一对应一步合法棋（{len(matches)} 个候选）')
        self.accept_move(matches[0]);return matches[0]
