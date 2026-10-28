import time

class Rounds:
    """Count each confirmed result once and latch a single continuation request."""
    def __init__(self,limit):
        if limit<0:raise ValueError('局数不能为负数')
        self.limit=limit;self.finished=0;self.counted=False;self.continue_sent=False;self.continue_at=0
    def result(self):
        if not self.counted:self.finished+=1;self.counted=True
        return self.limit==0 or self.finished<self.limit
    def new_game(self):self.counted=False;self.continue_sent=False;self.continue_at=0
    def continuation(self,now=None):
        now=time.monotonic() if now is None else now
        if not self.counted or (self.continue_sent and now-self.continue_at<3):return False
        if self.limit and self.finished>=self.limit:return False
        self.continue_sent=True;self.continue_at=now;return True
