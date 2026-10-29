"""User-operated two-point selection on a snapshot of the chosen window."""
import tkinter as tk
from tkinter import ttk
from PIL import Image,ImageTk
from windows_io import Window,target_windows
from manual_grid import validate_corners,grid_box,content_rect


class GridPicker(tk.Toplevel):
    def __init__(self,root,on_save,previous=None):
        super().__init__(root);self.owner=root;self.on_save=on_save;self.points=[];self.frame=None
        self.title('手动识别 · 两点定位');self.geometry('900x850');self.minsize(650,650)
        self.targets=target_windows();self.target=tk.StringVar();self.bottom=tk.StringVar(value='自动判断')
        toolbar=ttk.Frame(self,padding=10);toolbar.pack(fill='x')
        ttk.Label(toolbar,text='棋局窗口').pack(side='left')
        labels=[f'{t["title"]}  [{t["hwnd"]}]' for t in self.targets]
        combo=ttk.Combobox(toolbar,textvariable=self.target,values=labels,state='readonly',width=38);combo.pack(side='left',padx=8)
        self.target.set(next((label for label,t in zip(labels,self.targets) if t['title']==(previous or {}).get('target',{}).get('title')),next((label for label,t in zip(labels,self.targets) if t['title'] in ('象棋','天天象棋')),labels[0] if labels else '')))
        ttk.Button(toolbar,text='读取窗口截图',command=self.load).pack(side='left')
        ttk.Button(toolbar,text='重新选点',command=self.reset).pack(side='right')
        self.message=tk.StringVar(value='先读取窗口，再点击棋盘左上、右下的交叉点；不要选择外框边缘。')
        ttk.Label(self,textvariable=self.message,padding=8).pack(fill='x')
        self.canvas=tk.Canvas(self,bg='#25212c',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=10)
        self.canvas.bind('<Button-1>',self.click);self.canvas.bind('<Configure>',lambda e:self.paint())
        footer=ttk.Frame(self,padding=10);footer.pack(fill='x')
        ttk.Label(footer,text='下方棋色').pack(side='left')
        ttk.Combobox(footer,textvariable=self.bottom,values=('自动判断','红方','黑方'),state='readonly',width=9).pack(side='left',padx=8)
        ttk.Label(footer,text='确定后默认我方先走；以实际合法变化确认回合。').pack(side='left')
        ttk.Button(footer,text='确定',command=self.confirm).pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.cancel);self.bind('<Escape>',lambda e:self.cancel())
        self.after(100,self.load)

    def load(self):
        try:
            index=[f'{t["title"]}  [{t["hwnd"]}]' for t in self.targets].index(self.target.get())
            self.chosen=self.targets[index];self.window=Window(self.chosen)
        except (ValueError,IndexError) as e:self.message.set('请选择仍然打开的棋局窗口。');return
        self.withdraw();self.owner.withdraw();self.window.focus();self.after(400,self.capture)

    def capture(self):
        try:
            self.frame,self.rect=self.window.capture();self.points=[]
            self.original=Image.fromarray(self.frame[:,:,::-1]);self.message.set('第 1 点：点击左上角交叉点（棋子中心），再点右下角交叉点。')
        except (ValueError,OSError) as e:self.message.set(str(e))
        finally:
            self.owner.deiconify();self.deiconify();self.lift();self.after(100,self.paint)

    def reset(self):self.points=[];self.message.set('重新选择左上、右下两个交叉点。');self.paint()

    def paint(self):
        if self.frame is None:return
        width=max(1,self.canvas.winfo_width());height=max(1,self.canvas.winfo_height())
        self.scale=min(width/self.original.width,height/self.original.height)
        size=(max(1,round(self.original.width*self.scale)),max(1,round(self.original.height*self.scale)))
        self.offset=((width-size[0])/2,(height-size[1])/2)
        self.photo=ImageTk.PhotoImage(self.original.resize(size,Image.Resampling.LANCZOS))
        self.canvas.delete('all');self.canvas.create_image(*self.offset,image=self.photo,anchor='nw')
        for x,y in self.points:
            px=self.offset[0]+x*self.original.width*self.scale;py=self.offset[1]+y*self.original.height*self.scale
            self.canvas.create_oval(px-5,py-5,px+5,py+5,outline='#ea72eb',width=3)
        if len(self.points)==2:
            try:x1,y1,x2,y2=validate_corners(self.points)
            except ValueError:return
            x1=self.offset[0]+x1*self.original.width*self.scale;x2=self.offset[0]+x2*self.original.width*self.scale
            y1=self.offset[1]+y1*self.original.height*self.scale;y2=self.offset[1]+y2*self.original.height*self.scale
            for c in range(9):
                x=x1+(x2-x1)*c/8;self.canvas.create_line(x,y1,x,y2,fill='#df78eb',dash=(4,3))
            for r in range(10):
                y=y1+(y2-y1)*r/9;self.canvas.create_line(x1,y,x2,y,fill='#df78eb',dash=(4,3))

    def click(self,event):
        if self.frame is None:return
        x=(event.x-self.offset[0])/self.scale/self.original.width;y=(event.y-self.offset[1])/self.scale/self.original.height
        if not (0<=x<=1 and 0<=y<=1):return
        if len(self.points)==2:self.points=[]
        self.points.append([x,y]);self.paint()
        self.message.set('第 2 点：点击右下角交叉点。' if len(self.points)==1 else '检查紫色网格是否对齐所有交叉点；正确后点击确定。')

    def confirm(self):
        try:
            validate_corners(self.points)
            calibration={'version':1,'target':self.chosen,'corners':self.points,'reference_size':[self.original.width,self.original.height],
                         'bottom_color':{'红方':'w','黑方':'b'}.get(self.bottom.get(),'auto')}
            left,top,width,height=content_rect(self.frame)
            content_points=[[(x*self.original.width-left)/width,(y*self.original.height-top)/height] for x,y in self.points]
            validate_corners(content_points);calibration['content_corners']=content_points;calibration['version']=2
            grid_box(calibration,self.frame.shape)
        except (ValueError,AttributeError) as e:self.message.set(str(e));return
        self.on_save(calibration);self.destroy()

    def cancel(self):self.owner.deiconify();self.destroy()
