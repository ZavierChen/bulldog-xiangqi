"""End-of-game checks are driven by failed board reads and state deadlines."""
import time

class ScreenFlow:
    def __init__(self,fallback_seconds=30,clock=time.monotonic):
        self.clock=clock;self.timeout=max(30,float(fallback_seconds))
        self.mode='board';self.due_at=0;self.fallback_at=float('inf')
        self.failures=0;self.failed_at=None;self.stage_at=0
        self.signature=None;self.progress_at=clock();self.probed_at=self.progress_at

    def board_failed(self):
        if self.mode!='board':return
        now=self.clock();self.failures+=1
        if self.failed_at is None:self.failed_at=now
        # Let ordinary capture effects/animations settle before looking for ads.
        if self.failures>=4 and now-self.failed_at>=.5:self.ended()

    def board_ok(self,signature=None):
        now=self.clock();recovering=self.mode!='board'
        self.mode='board';self.failures=0;self.failed_at=None
        self.fallback_at=float('inf')
        if signature is None or signature!=self.signature:
            self.signature=signature;self.progress_at=now;self.probed_at=now
        elif recovering:self.probed_at=now
        elif now-max(self.progress_at,self.probed_at)>=self.timeout:
            # A readable but frozen/result board can otherwise wait forever.
            # Probe ads once, then return straight to play if the board is live.
            self.probed_at=now;self.ended()

    def ended(self):
        if self.mode!='board':return
        now=self.clock();self.mode='ad';self.stage_at=now;self.due_at=now
        self.fallback_at=now+self.timeout

    def next(self):
        now=self.clock()
        if self.mode=='board':return None
        if now>=self.fallback_at:
            self.fallback_at=now+self.timeout
            return 'fallback'
        if now<self.due_at:return None
        if self.mode=='enter':
            # No game appeared after the click: re-detect its entry to retry.
            self.mode='continue';self.stage_at=now
        return self.mode

    def ad_closed(self):self._advance('upgrade',.35)
    def upgrade_closed(self):self._advance('continue',.6)
    def continued(self):self._advance('enter',3)
    def _advance(self,mode,delay):
        now=self.clock();self.mode=mode;self.stage_at=now;self.due_at=now+delay
        self.fallback_at=now+self.timeout

    def ad_wait(self):
        if self.mode!='ad':self.mode='ad';self.stage_at=self.clock()
        self.due_at=self.clock()+1

    def missed(self,task):
        now=self.clock()
        if task=='upgrade' and now-self.stage_at>=.8:
            # Upgrade is optional. Give its entrance animation a short grace.
            self.mode='continue';self.stage_at=now;self.due_at=now+.1
        elif task=='upgrade':self.due_at=now+.4
        elif task=='ad':self.due_at=now+3
        elif task=='continue':self.due_at=now+1
        elif task=='fallback':
            # Unknown/rare order: return to the expected ad-first path. Another
            # full chain is allowed only after the next waiting timeout.
            self.mode='ad';self.stage_at=now;self.due_at=now+3
