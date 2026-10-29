import time

PHASES={'capture':'截图与双帧确认','ad_scan':'检查广告','scene':'判断界面类型','popup_scan':'检查升级提示','continue_scan':'检查续局按钮','board_sync':'识别棋盘与同步走棋历史','search':'引擎选招','move_recheck':'复核回合与落子条件','click':'执行落子','wait_turn':'等待头像/计时确认本方回合','wait_opponent':'等待对方走棋','wait_accept':'等待游戏确认落子','wait_ui':'等待当前界面响应或超时','idle':'等待下一帧','recover':'恢复连接或等待动画'}

PHASES['ponder_stop']='停止后台预判与接管引擎'
PHASES['points_popup_scan']='检查积分加速提示'
PHASES['wait_manual']='等待手动走一步指令'

class CycleTrace:
    def __init__(self,notify,clock=time.monotonic):
        self.clock=clock;self.notify=notify;self.current=None;self.start=clock();self.previous=self.start;self.elapsed={}
    def stage(self,name):
        now=self.clock()
        if self.current:self.elapsed[self.current]=self.elapsed.get(self.current,0)+now-self.previous
        self.current=name;self.previous=now;self.notify(('phase',(PHASES.get(name,name),now)))
    def finish(self):
        now=self.clock()
        if self.current:self.elapsed[self.current]=self.elapsed.get(self.current,0)+now-self.previous
        self.current=None
        return {'total_seconds':round(now-self.start,6),'stages':{k:round(v,6) for k,v in self.elapsed.items()}}
