"""Speculate on several opponent replies without blocking board recognition."""
import time,threading
from tracker import Engine,moved,position_key
from ponder_policy import PonderPolicy

class Ponder:
    def __init__(self,path,threads,branches=3,min_seconds=2,notify=lambda value:None,engine_factory=Engine,economical=True):
        self.path=path;self.threads=max(1,threads)
        self.ready_for_promotion=False
        self.branches=max(2,min(5,int(branches)));self.min_seconds=max(.3,float(min_seconds))
        self.notify=notify;self.factory=engine_factory;self.engine=None;self.thread=None
        self.stop=threading.Event();self.lock=threading.Lock();self.closed=False
        self.root=None;self.results=None;self.started=0;self.last_notice=0;self.retry_at=0
        self.economical=economical;self.completed=False;self.paused=False

    def start(self,tracker):
        key=(tracker.initial,tuple(tracker.moves),position_key(tracker.board,tracker.side))
        if self.root and self.root['identity']==key and self.completed:return
        if self.thread and self.thread.is_alive():
            if self.root and self.root['identity']==key:return
            self.cancel()
            if self.thread.is_alive():return
        if self.closed or time.monotonic()<self.retry_at:return
        same_root=bool(self.root and self.root['identity']==key)
        if not same_root:
            self.root={'identity':key,'initial':tracker.initial,'moves':tracker.moves.copy(),
                       'board':[row.copy() for row in tracker.board],'side':tracker.side,
                       'searched_seconds':0,'policy':PonderPolicy.from_budget(self.min_seconds)}
            self.results=None
        self.stop=threading.Event();self.started=time.monotonic();self.last_notice=0
        self.completed=False
        self.paused=False
        self.notify({'state':'resumed' if same_root else 'starting','branches':self.branches,'threads':self.threads})
        self.thread=threading.Thread(target=self._run,args=(self.root,self.stop),daemon=True);self.thread.start()

    def _run(self,root,stop):
        pending={};timer=None;policy=root.get('policy') or PonderPolicy.from_budget(self.min_seconds)
        spent=root.get('searched_seconds',0);search_started=None
        try:
            if self.engine is None:self.engine=self.factory(self.path,threads=self.threads,hash_mb=512)
            if stop.is_set() or self.closed:return
            self.engine.set_background(True)
            engine=self.engine;self.started=time.monotonic();search_started=self.started
            elapsed=lambda:spent+time.monotonic()-search_started
            def finish(reason):
                if stop.is_set() or self.root is not root:return
                self.completed=True;stop.set()
                try:engine.send('stop')
                except (OSError,ValueError):pass
                self.notify({'state':'budget','reason':reason,'seconds':elapsed()})
            def info(value):
                if stop.is_set():return
                depth=value['depth'];rank=value['rank'];count=value['branches']
                pending.setdefault(depth,{})[rank]=value
                # Publish coherent iterations only: each branch at the same depth.
                if not all(i in pending[depth] for i in range(1,count+1)):return
                lines=[pending[depth][i] for i in range(1,count+1)]
                if any(len(line['pv'])<2 for line in lines):return
                with self.lock:
                    if self.root is not root or stop.is_set():return
                    if self.results and depth<self.results['depth']:return
                    result={'depth':depth,'lines':lines,'seconds':elapsed(),'key':root['identity'][2],'side':root['side']}
                    result['analysis_ready']=policy.observe(result) if self.economical else depth>=12 and result['seconds']>=self.min_seconds
                    result['stable_replies']=policy.ready_moves.copy() if self.economical else [line['pv'][0] for line in lines]
                    self.results=result
                for old in list(pending):
                    if old<depth:del pending[old]
                now=time.monotonic()
                if now-self.last_notice>=.3:
                    self.last_notice=now;self.notify({'state':'thinking',**self.results})
                if self.economical and result['analysis_ready']:finish('stable')
            if self.economical:
                timer=threading.Timer(max(.01,policy.maximum-spent),lambda:finish('time_cap'));timer.daemon=True;timer.start()
            self.engine.analyze(root['initial'],root['moves'],self.branches,stop,info)
        except Exception as error:
            if not stop.is_set():
                self.notify({'state':'error','message':str(error)});self.retry_at=time.monotonic()+10
            if self.engine:
                self.engine.close();self.engine=None
        finally:
            if search_started is not None:root['searched_seconds']=spent+time.monotonic()-search_started
            if timer:timer.cancel()
            if self.closed and self.engine:self.engine.close();self.engine=None

    def cancel(self,grace=.8):
        self.stop.set()
        worker=self.thread
        if worker and worker.is_alive():
            engine=self.engine
            if engine:
                try:engine.send('stop')
                except (OSError,ValueError):pass
            worker.join(grace)
            if worker.is_alive() and engine:
                engine.close();worker.join(.3)
                if self.engine is engine:self.engine=None

    def match(self,tracker):
        self.cancel()
        with self.lock:
            root=self.root;result=self.results;self.root=None;self.results=None
        tracker.ponder_hint=None
        self.ready_for_promotion=bool(root and tracker.initial==root['initial'] and len(tracker.moves)==len(root['moves'])+1 and tracker.moves[:-1]==root['moves'])
        enough=result and result.get('analysis_ready',result['depth']>=12 and result['seconds']>=self.min_seconds)
        if (not root or not result or not enough
            or tracker.initial!=root['initial']):
            if self.ready_for_promotion:self.notify({'state':'continue'})
            return None
        for line in result['lines']:
            pv=line['pv'];prefix=root['moves']+[pv[0]]
            if tracker.moves!=prefix:continue
            if pv[0] not in result.get('stable_replies',[v['pv'][0] for v in result['lines']]):
                self.notify({'state':'continue'});return None
            expected=moved(root['board'],pv[0]);side='b' if root['side']=='w' else 'w'
            key=position_key(expected,side)
            if position_key(tracker.board,tracker.side)!=key:continue
            hint={'initial':root['initial'],'prefix':prefix,'key':key,'move':pv[1],
                  'continuation':pv[1:],'depth':line['depth'],'rank':line['rank'],
                  'score':line['score'],'score_type':line['score_type'],'seconds':result['seconds'],'wdl':line.get('wdl')}
            tracker.ponder_hint=hint
            self.notify({'state':'hit',**hint});return hint
        self.notify({'state':'miss'});return None

    def promote(self,foreground):
        """Move the searched hash table into foreground use; keep two engines."""
        if not self.ready_for_promotion or (self.thread and self.thread.is_alive()):return foreground
        self.ready_for_promotion=False;candidate=self.engine
        if candidate is None or candidate.process.poll() is not None:return foreground
        candidate.set_background(False)
        self.engine=foreground
        return candidate

    def clear(self):
        active=self.root is not None or bool(self.thread and self.thread.is_alive())
        self.cancel();self.root=None;self.results=None
        self.ready_for_promotion=False;self.completed=False;self.paused=False
        if active:self.notify({'state':'idle'})
    def pause(self):
        active=bool(self.thread and self.thread.is_alive());self.cancel(grace=2.)
        self.paused=True
        if active:self.notify({'state':'paused'})
    def expected_lines(self,tracker):
        if tracker is None:return []
        with self.lock:
            root=self.root;result=self.results
            if not root or not result or root['initial']!=tracker.initial:return []
            return [{'initial':root['initial'],'prefix':root['moves'].copy(),'pv':line['pv'].copy(),
                     'reuse':bool(result.get('analysis_ready') and line['pv'][0] in result.get('stable_replies',[]))}
                    for line in result['lines']]
    def close(self):
        self.closed=True;self.clear()
        if self.engine:self.engine.close();self.engine=None
