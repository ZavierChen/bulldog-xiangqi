"""Window adapter used by the standalone practice application."""
import ctypes,time,os
from ctypes import wintypes
from PIL import ImageGrab
import numpy as np
u=ctypes.windll.user32
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.GetForegroundWindow.restype=wintypes.HWND
u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
u.IsWindow.argtypes=[wintypes.HWND]
u.SetForegroundWindow.argtypes=[wintypes.HWND]
u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]

class Window:
    def __init__(self):
        self.hwnd=None
        self.lost_foreground=None;self.lost_at=0
        try:self.bind()
        except ValueError:pass
    def bind(self):
        found=[]
        callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        @callback
        def visit(hwnd,_):
            title=ctypes.create_unicode_buffer(512);u.GetWindowTextW(hwnd,title,512)
            if title.value in ('天天象棋','象棋') and u.IsWindowVisible(hwnd):found.append(hwnd)
            return True
        u.EnumWindows(visit,0)
        if len(found)!=1:raise ValueError('请只打开一个支持的象棋窗口（天天象棋或象棋）')
        self.hwnd=found[0]
    def rect(self):
        if not u.IsWindow(self.hwnd):self.bind()
        if u.IsIconic(self.hwnd):raise ValueError('天天象棋已最小化，等待恢复窗口')
        r=wintypes.RECT();u.GetWindowRect(self.hwnd,ctypes.byref(r))
        if r.right-r.left<100 or r.bottom-r.top<100:raise ValueError('天天象棋窗口被最小化')
        return r.left,r.top,r.right,r.bottom
    def focus(self):
        if self.hwnd:u.SetForegroundWindow(self.hwnd)
    def capture(self):
        if u.GetForegroundWindow()!=self.hwnd:raise ValueError('正在等待恢复天天象棋前台连接')
        rect=self.rect();im=np.asarray(ImageGrab.grab(bbox=rect,all_screens=True))[:,:,::-1].copy()
        return im,rect
    def reconnect(self):
        try:
            if not u.IsWindow(self.hwnd):self.bind()
            foreground=u.GetForegroundWindow()
            if foreground==self.hwnd:self.lost_foreground=None;return True
            if self.lost_foreground!=foreground:self.lost_foreground=foreground;self.lost_at=time.monotonic()
            if u.GetAsyncKeyState(0x01)&0x8000:return False
            pid=wintypes.DWORD();u.GetWindowThreadProcessId(foreground,ctypes.byref(pid))
            if pid.value==os.getpid() and time.monotonic()-self.lost_at<4:return False
            if u.IsIconic(self.hwnd):return False
            self.focus()
            return u.GetForegroundWindow()==self.hwnd
        except ValueError:return False
    def click(self,point,rect):
        if self.rect()!=rect or u.GetForegroundWindow()!=self.hwnd:raise ValueError('窗口位置或焦点变化，取消点击')
        x,y=point;u.SetCursorPos(round(rect[0]+x),round(rect[1]+y))
        u.mouse_event(2,0,0,0,0);u.mouse_event(4,0,0,0,0)
    def park(self,rect):u.SetCursorPos(rect[2]-30,rect[1]+65)
