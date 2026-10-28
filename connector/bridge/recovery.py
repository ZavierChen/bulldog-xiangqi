class Recovery:
    def __init__(self):self.started=None;self.last_attempt=0
    def lost(self,now):
        if self.started is None:self.started=now
    def restored(self,now):
        duration=0 if self.started is None else max(0,now-self.started)
        self.started=None;return duration
    def attempt(self,now):
        if now-self.last_attempt<2:return False
        self.last_attempt=now;return True

def friendly(message):
    if any(t in message for t in ('棋子数量','棋子识别','画面不稳定','将或帅','走棋提示不稳定','头像提示与局面')):
        return '等待棋盘动画结束，稳定后自动继续…'
    if any(t in message for t in ('窗口','前台','棋盘外框')):
        return '正在重新连接并识别棋盘…'
    return '正在重新核对局面，确认后自动继续…'
