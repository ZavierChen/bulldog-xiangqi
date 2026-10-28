"""Gradual foreground extensions after repeated non-positive midgame scores."""
import statistics
from collections import deque

class ThinkingBudget:
    def __init__(self,seconds,enabled=True):
        self.base=max(1,min(30,float(seconds)));self.enabled=enabled
        self.factor=1.;self.scores=deque(maxlen=4);self.last_key=None
        self.reason='基础预算'
        self.game_initial=None

    @staticmethod
    def opening(tracker):
        if len(tracker.moves)>=20:return False
        # A midgame attachment may have no opening history. A materially reduced
        # initial board is already out of opening; otherwise delay conservatively.
        initial=getattr(tracker,'initial','').split(' ')[0]
        count=sum(c.isalpha() for c in initial)
        return count>=28 or not initial

    def milliseconds(self,tracker):
        initial=getattr(tracker,'initial',None)
        if initial!=self.game_initial:
            self.game_initial=initial;self.factor=1.;self.scores.clear();self.last_key=None
            self.reason='基础预算'
        if not self.enabled or self.opening(tracker):
            self.factor=1.;self.scores.clear();self.reason='开局保持基础预算' if self.enabled else '动态加时已关闭'
        return round(min(30,self.base*self.factor)*1000)

    def record(self,tracker,evaluation):
        if not self.enabled or self.opening(tracker) or evaluation is None:return
        key=(tracker.initial,tuple(tracker.moves))
        if key==self.last_key:return
        self.last_key=key
        score=evaluation['score']
        if evaluation['score_type']=='mate':score=10000 if score>0 else -10000
        self.scores.append(score)
        if len(self.scores)<3:self.reason='收集连续评分，暂不加时';return
        recent=list(self.scores)[-3:];median=statistics.median(recent)
        if all(v<=0 for v in recent):
            target=3 if median<=-250 else 2 if median<=-100 else 1.5 if median<=-30 else 1.25
            self.factor=min(target,self.factor+.5) if target>=self.factor else max(target,self.factor-.25)
            self.reason='连续三次评分不占优，逐步加时'
        elif all(v>=50 for v in list(self.scores)[-2:]):
            self.factor=max(1.,self.factor-.5);self.reason='局面回稳，逐步恢复基础预算'
        else:self.reason='评分波动，保持当前预算'
