"""Shared, scalable xiangqi board with logical coordinates and move overlays."""
import math,tkinter as tk

LABEL={'R':'车','N':'马','B':'相','A':'仕','K':'帅','C':'炮','P':'兵','r':'車','n':'馬','b':'象','a':'士','k':'将','c':'炮','p':'卒'}
COLORS=('#15856e','#3970bd','#b27a17')

class BoardView(tk.Canvas):
    def __init__(self,parent,on_square=None,on_drag=None,**kwargs):
        super().__init__(parent,bg='#f3dfbd',highlightthickness=0,**kwargs)
        self.board=[['_']*9 for _ in range(10)];self.flipped=False;self.last_move=None
        self.arrows=[];self.selected_hint=0;self.selection=None
        self.on_square=on_square;self.on_drag=on_drag;self.pressed=None
        self.bind('<Configure>',lambda event:self.redraw())
        self.bind('<ButtonPress-1>',self.press);self.bind('<ButtonRelease-1>',self.release)
        self.bind('<Button-3>',lambda e:self.clicked(e,'erase'))

    def geometry_values(self):
        w=max(100,self.winfo_width());h=max(100,self.winfo_height())
        if w<=100:w=int(self.cget('width'))
        if h<=100:h=int(self.cget('height'))
        s=max(18,min((w-70)/8,(h-80)/9));return (w-8*s)/2,(h-9*s)/2,s
    def center(self,row,col):
        ox,oy,s=self.geometry_values()
        if self.flipped:row,col=9-row,8-col
        return ox+col*s,oy+row*s
    def square(self,x,y):
        ox,oy,s=self.geometry_values();col=round((x-ox)/s);row=round((y-oy)/s)
        if not(0<=row<10 and 0<=col<9) or abs(x-(ox+col*s))>s*.48 or abs(y-(oy+row*s))>s*.48:return None
        return (9-row,8-col) if self.flipped else (row,col)
    def set_position(self,board,flipped=False,last_move=None):
        self.board=[row.copy() for row in board];self.flipped=flipped;self.last_move=last_move;self.redraw()
    def press(self,event):self.pressed=self.square(event.x,event.y)
    def release(self,event):
        dest=self.square(event.x,event.y);origin=self.pressed;self.pressed=None
        if origin is not None and dest is not None and origin!=dest and self.on_drag:self.on_drag(origin,dest)
        elif dest is not None and self.on_square:self.on_square(*dest,'place')
    def clicked(self,event,action):
        square=self.square(event.x,event.y)
        if square is not None and self.on_square:self.on_square(*square,action)
    def redraw(self):
        self.delete('all');ox,oy,s=self.geometry_values();ink='#80643f';width=max(1,round(s/40))
        self.create_rectangle(ox-6,oy-6,ox+8*s+6,oy+9*s+6,outline=ink,width=2)
        for row in range(10):self.create_line(ox,oy+row*s,ox+8*s,oy+row*s,fill=ink,width=width)
        for col in range(9):
            segments=((0,9),) if col in (0,8) else ((0,4),(5,9))
            for a,b in segments:self.create_line(ox+col*s,oy+a*s,ox+col*s,oy+b*s,fill=ink,width=width)
        for row in (0,7):
            self.create_line(ox+3*s,oy+row*s,ox+5*s,oy+(row+2)*s,fill=ink)
            self.create_line(ox+5*s,oy+row*s,ox+3*s,oy+(row+2)*s,fill=ink)
        for row,col in [(2,1),(2,7),(7,1),(7,7)]+[(r,c) for r in (3,6) for c in (0,2,4,6,8)]:
            for dx in (-1,1):
                if (col==0 and dx<0) or (col==8 and dx>0):continue
                for dy in (-1,1):
                    x=ox+col*s;y=oy+row*s;u=s*.11;v=s*.23
                    self.create_line(x+dx*u,y+dy*v,x+dx*u,y+dy*u,x+dx*v,y+dy*u,fill=ink)
        self.create_text(ox+2*s,oy+4.5*s,text='楚 河',font=('Microsoft YaHei',max(12,round(s*.35))),fill=ink)
        self.create_text(ox+6*s,oy+4.5*s,text='汉 界',font=('Microsoft YaHei',max(12,round(s*.35))),fill=ink)
        for col in range(9):
            self.create_text(ox+col*s,oy-22,text=str(col+1) if not self.flipped else '一二三四五六七八九'[col],fill=ink,font=('Microsoft YaHei',9))
            self.create_text(ox+col*s,oy+9*s+24,text='九八七六五四三二一'[col] if not self.flipped else str(9-col),fill=ink,font=('Microsoft YaHei',9))
        if self.last_move:
            for i in (0,2):
                x,y=self.center(9-int(self.last_move[i+1]),ord(self.last_move[i])-97)
                self.create_rectangle(x-s*.47,y-s*.47,x+s*.47,y+s*.47,outline='#18876d',width=3)
        for r in range(10):
            for c in range(9):
                p=self.board[r][c]
                if p=='_':continue
                x,y=self.center(r,c);radius=s*.405;color='#b02b25' if p.isupper() else '#292c32'
                self.create_oval(x-radius+1,y-radius+2,x+radius+1,y+radius+2,fill='#b99c71',outline='')
                self.create_oval(x-radius,y-radius,x+radius,y+radius,fill='#fff1d3',outline=color,width=2)
                self.create_oval(x-radius+4,y-radius+4,x+radius-4,y+radius-4,outline=color)
                self.create_text(x,y,text=LABEL[p],font=('Microsoft YaHei',max(12,round(s*.37)),'bold'),fill=color)
        if self.selection is not None:
            x,y=self.center(*self.selection)
            self.create_rectangle(x-s*.47,y-s*.47,x+s*.47,y+s*.47,outline='#7951a1',width=3)
        for rank,move in enumerate(self.arrows):
            start=self.center(9-int(move[1]),ord(move[0])-97);end=self.center(9-int(move[3]),ord(move[2])-97)
            dx=end[0]-start[0];dy=end[1]-start[1];distance=math.hypot(dx,dy)
            if distance==0:continue
            ux=dx/distance;uy=dy/distance;color=COLORS[rank%3];chosen=rank==self.selected_hint
            self.create_line(start[0]+ux*s*.32,start[1]+uy*s*.32,end[0]-ux*s*.28,end[1]-uy*s*.28,
                fill=color,width=5 if chosen else 3,arrow=tk.LAST,arrowshape=(13,16,6),tags=('hint_arrow',))
            mx=(start[0]+end[0])/2-uy*(rank-1)*8;my=(start[1]+end[1])/2+ux*(rank-1)*8
            self.create_oval(mx-10,my-10,mx+10,my+10,fill=color,outline='white',width=2,tags=('hint_rank',))
            self.create_text(mx,my,text=str(rank+1),fill='white',font=('Microsoft YaHei',9,'bold'),tags=('hint_rank',))
