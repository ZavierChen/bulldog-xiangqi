"""Bound speculative work using stable replies and a finite search budget."""
from collections import deque
import json,os

class PonderPolicy:
    def __init__(self,soft_seconds=3,max_seconds=8,stable_seconds=1,score_tolerance=25):
        self.soft=max(.3,float(soft_seconds));self.maximum=max(self.soft,float(max_seconds))
        self.window=max(.15,min(float(stable_seconds),self.soft*.5))
        self.tolerance=score_tolerance;self.history=deque(maxlen=80)
        self.ready_moves=[]

    @classmethod
    def from_budget(cls,seconds):
        tuning={}
        try:
            with open(os.path.join(os.path.dirname(__file__),'ponder-tuning.json'),encoding='utf-8') as f:tuning=json.load(f)
        except (OSError,ValueError):pass
        soft=min(max(.3,seconds),max(1,float(tuning.get('soft_seconds',3))))
        maximum=max(soft,min(max(soft,seconds*2),float(tuning.get('max_seconds',8))))
        return cls(soft,maximum,score_tolerance=max(1,float(tuning.get('score_tolerance_cp',25))))

    def observe(self,result):
        now=result['seconds'];self.history.append(result)
        if now<self.soft or result['depth']<12:return False
        # Equivalent branches may exchange rank. Keep their candidate set and
        # scores stable, then mark each individually stable reply as reusable.
        self.ready_moves=[]
        fingerprint=lambda r:tuple(sorted(line['pv'][0] for line in r['lines']))
        target=fingerprint(result);samples=[]
        for old in reversed(self.history):
            if fingerprint(old)!=target:break
            samples.append(old)
            if now-old['seconds']>=self.window:break
        if len({r['depth'] for r in samples})<3 or now-samples[-1]['seconds']<self.window:return False
        for current in result['lines']:
            move=current['pv'][0];scores=[];replies=[]
            for old in samples:
                line=next(v for v in old['lines'] if v['pv'][0]==move)
                if line['score_type']!=current['score_type']:return False
                scores.append(line['score'])
                replies.append(line['pv'][1])
            tolerance=self.tolerance if current['score_type']=='cp' else 1
            if max(scores)-min(scores)>tolerance:return False
            if all(reply==current['pv'][1] for reply in replies):self.ready_moves.append(move)
        return result['lines'][0]['pv'][0] in self.ready_moves
