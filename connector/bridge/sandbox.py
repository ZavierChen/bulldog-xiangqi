"""Local board editor and on-demand, three-candidate engine coach."""
import queue,threading,time,tkinter as tk
from tkinter import ttk,simpledialog
from board_view import BoardView,LABEL,COLORS
from sandbox_model import SandboxModel,parse_fen,validate,move_name,START
from tracker import Engine
from position_analysis import format_analysis

class Sandbox(ttk.Frame):
    def __init__(self,parent,engine_path,threads,can_analyze=lambda:True):
        super().__init__(parent,padding=12)
        self.engine_path=engine_path;self.thread_count=threads;self.can_analyze=can_analyze
        self.model=SandboxModel();self.engine=None;self.worker=None;self.events=queue.Queue()
        self.busy=False;self.closed=False;self.generation=0;self.cancelled=threading.Event();self.hints=[];self.selected=0;self.origin=None
        self.tool=tk.StringVar(value='move');self.side=tk.StringVar(value='红方');self.seconds=tk.IntVar(value=3)
        self.status=tk.StringVar(value='选择棋子后点击棋盘摆放；也可以直接拖动棋子。右键删除。')
        self.recovery_callback=None
        self.summary=tk.StringVar(value='摆好局面后点击“电脑提示”，按评分给出下一步的三种选择。')
        self.recovery_cancel=None
        self.analysis_red=tk.StringVar(value='红方：评分暂无｜胜率暂无');self.analysis_black=tk.StringVar(value='黑方：评分暂无｜胜率暂无')
        toolbar=ttk.Frame(self);toolbar.pack(fill='x',pady=(0,10))
        ttk.Label(toolbar,text='沙盒摆棋',style='Section.TLabel').pack(side='left')
        for text,command in (('初始棋局',self.reset),('清空',self.clear),('撤销',self.undo),('翻转',self.flip),('导入 FEN',self.import_fen),('复制 FEN',self.export_fen)):
            ttk.Button(toolbar,text=text,command=command,style='Small.TButton').pack(side='left',padx=3)
        body=ttk.Frame(self);body.pack(fill='both',expand=True)
        left=ttk.Frame(body);left.pack(side='left',fill='both',expand=True,padx=(0,14))
        self.board=BoardView(left,width=510,height=550,on_square=self.square,on_drag=self.drag)
        self.board.pack(fill='both',expand=True)
        ttk.Label(left,textvariable=self.status,wraplength=530,style='Muted.TLabel').pack(fill='x',pady=(8,0))
        right=ttk.Frame(body,width=360);right.pack(side='right',fill='y');right.pack_propagate(False)
        ttk.Label(right,text='棋子工具',style='Section.TLabel').pack(anchor='w')
        tools=ttk.Frame(right);tools.pack(fill='x',pady=(5,8))
        for text,value in (('移动棋子','move'),('删除','erase')):
            ttk.Radiobutton(tools,text=text,value=value,variable=self.tool,command=self.clear_selection).pack(side='left',padx=(0,10))
        palette=ttk.Frame(right);palette.pack(fill='x')
        self.palette_buttons={}
        for row,pieces in enumerate(('RNBAKCP','rnbakcp')):
            for col,piece in enumerate(pieces):
                button=tk.Button(palette,text=LABEL[piece],font=('Microsoft YaHei',15,'bold'),fg='#ac2c27' if row==0 else '#292b34',bg='#fff7e7',activebackground='#e5d7ed',relief='flat',width=2,pady=3,
                    command=lambda p=piece:self.select_piece(p))
                button.grid(row=row,column=col,padx=2,pady=2);self.palette_buttons[piece]=button
        ttk.Separator(right).pack(fill='x',pady=12)
        config=ttk.Frame(right);config.pack(fill='x')
        ttk.Label(config,text='当前走棋').pack(side='left')
        side=ttk.Combobox(config,textvariable=self.side,values=('红方','黑方'),state='readonly',width=5);side.pack(side='left',padx=5);side.bind('<<ComboboxSelected>>',self.change_side)
        ttk.Label(config,text='秒').pack(side='right')
        ttk.Spinbox(config,from_=1,to=15,textvariable=self.seconds,width=3).pack(side='right',padx=4)
        actions=ttk.Frame(right);actions.pack(fill='x',pady=10)
        self.analyze_button=ttk.Button(actions,text='电脑提示 · 3 种建议',command=self.analyze,style='Accent.TButton');self.analyze_button.pack(side='left',fill='x',expand=True)
        ttk.Button(actions,text='停止',command=self.cancel,style='Small.TButton').pack(side='left',padx=(6,0))
        ttk.Label(right,textvariable=self.summary,wraplength=350,style='Muted.TLabel').pack(fill='x')
        self.recovery_bar=ttk.Frame(right)
        ttk.Button(self.recovery_bar,text='确认棋盘并续接',command=self.confirm_recovery,style='Accent.TButton').pack(side='left',fill='x',expand=True)
        ttk.Button(self.recovery_bar,text='取消校正',command=self.cancel_recovery,style='Small.TButton').pack(side='left',padx=5)
        self.cards=[]
        for rank in range(3):
            button=tk.Button(right,text=f'{rank+1}  等待分析',anchor='w',justify='left',wraplength=320,padx=12,pady=11,relief='flat',bg='white',fg=COLORS[rank],font=('Microsoft YaHei',10),command=lambda i=rank:self.select_hint(i))
            button.pack(fill='x',pady=(8,0));self.cards.append(button)
        ttk.Button(right,text='走选中的这一步（仅沙盒）',command=self.apply_hint).pack(fill='x',pady=10)
        ttk.Label(right,text='局面估计',style='Section.TLabel').pack(anchor='w',pady=(2,4))
        ttk.Label(right,textvariable=self.analysis_red,foreground='#a92626',wraplength=350).pack(anchor='w')
        ttk.Label(right,textvariable=self.analysis_black,wraplength=350).pack(anchor='w')
        ttk.Label(right,text='箭头 1 / 2 / 3 对应评分排序。点击建议卡突出显示；这些是同一手的三个候选，不是连续三步。',wraplength=350,style='Muted.TLabel').pack(fill='x',pady=10)
        self.refresh();self.after(80,self.poll)

    def refresh(self):
        self.board.set_position(self.model.board,self.board.flipped)
        self.side.set('红方' if self.model.side=='w' else '黑方')
    def begin_recovery(self,callback,cancel):
        self.recovery_callback=callback;self.recovery_cancel=cancel
        self.recovery_bar.pack(fill='x',pady=6,before=self.cards[0])
        self.summary.set('手动恢复：修正棋子并选择当前走棋方，确认后恢复连接。')
        self.status.set('连接已暂停，保留局面与计算。可以拖动、增删棋子或导入 FEN。')
    def confirm_recovery(self):
        try:validate(self.model.board,self.model.side)
        except ValueError as error:self.status.set(str(error));return
        if self.recovery_callback:self.recovery_callback([row.copy() for row in self.model.board],self.model.side)
    def end_recovery(self):
        self.recovery_callback=None;self.recovery_cancel=None;self.recovery_bar.pack_forget()
    def cancel_recovery(self):
        callback=self.recovery_cancel;self.end_recovery()
        if callback:callback()
    def invalidate(self):
        self.generation+=1;self.cancel();self.hints=[];self.board.arrows=[];self.origin=None;self.board.selection=None
        self.analysis_red.set('红方：评分暂无｜胜率暂无');self.analysis_black.set('黑方：评分暂无｜胜率暂无')
        self.summary.set('局面已改变，重新点击“电脑提示”。')
        for i,card in enumerate(self.cards):card.configure(text=f'{i+1}  等待分析',bg='white')
        self.refresh()
    def clear_selection(self):self.origin=None;self.board.selection=None;self.board.redraw()
    def select_piece(self,piece):
        self.tool.set(piece);self.clear_selection();self.status.set(('红方' if piece.isupper() else '黑方')+LABEL[piece]+'：点击棋盘摆放，右键删除。')
    def square(self,row,col,action):
        tool=self.tool.get()
        if action=='erase' or tool=='erase':self.model.place(row,col,'_');self.invalidate();return
        if tool not in ('move','erase'):self.model.place(row,col,tool);self.invalidate();return
        if self.origin is None:
            if self.model.board[row][col]!='_':self.origin=(row,col);self.board.selection=self.origin;self.board.redraw()
        else:
            self.model.move(self.origin,(row,col));self.invalidate()
    def drag(self,origin,destination):self.model.move(origin,destination);self.invalidate()
    def change_side(self,event=None):
        new='w' if self.side.get()=='红方' else 'b'
        if new!=self.model.side:self.model.remember();self.model.side=new;self.invalidate()
    def reset(self):
        board,side=parse_fen(START);self.model.load(board,side);self.invalidate();self.status.set('已恢复标准开局。')
    def clear(self):
        self.model.load([['_']*9 for _ in range(10)],'w');self.invalidate();self.status.set('棋盘已清空；分析前须摆好红帅和黑将。')
    def undo(self):self.model.undo();self.invalidate();self.status.set('已撤销上一次摆棋。')
    def flip(self):self.board.flipped=not self.board.flipped;self.board.redraw()
    def load(self,board,side):self.model.load(board,side);self.invalidate();self.status.set('已复制连接棋盘，可自由编辑后分析。')
    def import_fen(self):
        value=simpledialog.askstring('导入沙盒局面','粘贴 FEN（须包含 w / b 走棋方）：',parent=self)
        if value:
            try:board,side=parse_fen(value);self.load(board,side)
            except ValueError as e:self.status.set(str(e))
    def export_fen(self):
        self.clipboard_clear();self.clipboard_append(self.model.export());self.status.set('FEN 已复制到剪贴板。')
    def analyze(self):
        if self.busy:self.status.set('正在分析；停止后可以重新计算。');return
        if not self.can_analyze():self.status.set('连接对局仍在运行，请先停止连接，再分析沙盒。');return
        try:
            validate(self.model.board,self.model.side);seconds=max(1,min(15,int(self.seconds.get())));threads=max(1,int(self.thread_count()))
        except (ValueError,tk.TclError) as e:self.status.set(str(e));return
        self.cancelled=threading.Event();self.busy=True;self.analyze_button.configure(state='disabled')
        generation=self.generation;position=self.model.export();side=self.model.side
        self.summary.set('正在比较 3 个候选走法…');self.status.set('正在分析；编辑棋盘会取消并清除旧建议。')
        def work():
            try:
                if self.engine is None or self.engine.process.poll() is not None:self.engine=Engine(self.engine_path,threads=threads,hash_mb=256)
                else:self.engine.configure_threads(threads)
                if self.cancelled.is_set():return
                lines=self.engine.top_moves(position,seconds*1000,3)
                if not self.cancelled.is_set():self.events.put(('hints',generation,(lines,side)))
            except Exception as error:self.events.put(('error',generation,str(error)))
            finally:
                if self.closed and self.engine:self.engine.close()
                self.events.put(('done',generation,None))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def cancel(self):
        self.cancelled.set()
        if self.busy and self.engine:
            try:self.engine.send('stop')
            except (OSError,ValueError):pass
    def select_hint(self,index):
        if index>=len(self.hints):return
        self.selected=index;self.board.selected_hint=index;self.board.redraw()
        for i,card in enumerate(self.cards):card.configure(bg='#eee5f5' if i==index else 'white')
    def apply_hint(self):
        if not self.hints or self.busy:return
        self.model.apply(self.hints[self.selected]['pv'][0]);self.invalidate();self.status.set('已在沙盒走出该步；未操作外部游戏。')
    def poll(self):
        if self.closed:return
        try:
            while True:
                kind,generation,value=self.events.get_nowait()
                if kind=='done':
                    self.busy=False;self.analyze_button.configure(state='normal')
                    if generation==self.generation and self.cancelled.is_set():self.status.set('已停止分析，保留当前摆棋。');self.summary.set('提示已取消。')
                if generation!=self.generation:continue
                if kind=='hints':
                    self.hints,side=value;self.selected=0;self.board.arrows=[v['pv'][0] for v in self.hints]
                    for i,line in enumerate(self.hints):
                        score=(f'杀棋 {line["score"]:+d}' if line['score_type']=='mate' else f'评分 {line["score"]/100:+.2f}')
                        wdl=line.get('wdl');win=f' · 胜 {wdl[0]/10:.1f}% / 和 {wdl[1]/10:.1f}%' if wdl else ''
                        self.cards[i].configure(text=f'{i+1}  {move_name(self.model.board,line["pv"][0])}   {line["pv"][0][:2]} → {line["pv"][0][2:]}\n{score}{win}')
                    for i in range(len(self.hints),3):self.cards[i].configure(text=f'{i+1}  当前局面不足 3 个合法走法')
                    red,black=format_analysis(self.hints[0],side);self.analysis_red.set(red);self.analysis_black.set(black)
                    self.summary.set(f'{"红方" if side=="w" else "黑方"}走棋 · 深度 {self.hints[0]["depth"]} · 按当前方评分排序')
                    self.select_hint(0);self.status.set('分析完成。点击建议卡查看箭头，或继续摆棋。')
                elif kind=='error':self.status.set(value);self.summary.set('未能分析，请检查摆棋或引擎文件。')
        except queue.Empty:pass
        self.after(80,self.poll)
    def close(self):
        self.closed=True;self.cancel()
        if self.engine:self.engine.close()
        if self.worker and self.worker.is_alive():self.worker.join(.8)
