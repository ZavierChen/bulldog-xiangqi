import os,sys,time,threading,queue,json,tkinter as tk
from tkinter import ttk
from vision import Recognizer,fen,move_pixels
from tracker import Engine,position_key
from controller import Bridge
from rounds import Rounds
from recovery import Recovery,friendly
from popups import Popups
from ads import Ads
from timing import CycleTrace
from screen_flow import ScreenFlow
from pondering import Ponder
from thinking_budget import ThinkingBudget
from board_bootstrap import CalibrationRequired
from position_analysis import format_analysis

HERE=os.path.dirname(__file__)
ENGINE=os.environ.get('PIKAFISH_ENGINE',os.path.join(os.path.dirname(os.path.dirname(HERE)),'engine','pikafish.exe'))
LABEL={'R':'车','N':'马','B':'相','A':'仕','K':'帅','C':'炮','P':'兵','r':'車','n':'馬','b':'象','a':'士','k':'将','c':'炮','p':'卒'}
def recommended_threads():return max(1,(os.cpu_count() or 1)-2)
def thought_summary(seconds,source):
    names={'ponder_cache':'后台多分支命中，未重新搜索','pv_cache':'预判命中，未重新搜索','position_cache':'复用已算着法，未重新搜索','opening_book':'开局库，未重新搜索','engine':'引擎计算','stopped':'已停止','invalid':'结果未采用'}
    return f'本次思考：{seconds:.3f} 秒（{names.get(source,source)}）'
class App:
    def __init__(self,root):
        self.root=root
        self.events=queue.Queue();self.stop=threading.Event();self.running=False
        self.commands=queue.Queue()
        self.status=tk.StringVar(value='打开天天象棋棋盘后点击开始；Esc 可停止。')
        self.seconds=tk.IntVar(value=2);self.threads=tk.IntVar(value=recommended_threads())
        self.thinking_started=None;self.thinking_text=tk.StringVar(value='本次思考：尚未开始')
        self.phase_started=None;self.phase_name='尚未开始';self.phase_text=tk.StringVar(value='当前阶段：尚未开始')
        self.latency_text=tk.StringVar(value='本步总用时：尚未落子')
        self.game_limit=tk.IntVar(value=1);self.unlimited=tk.BooleanVar(value=False)
        self.auto_reconnect=tk.BooleanVar(value=True)
        self.use_gpu=tk.BooleanVar(value=True)
        self.fallback_seconds=tk.IntVar(value=30)
        self.ponder_enabled=tk.BooleanVar(value=True);self.ponder_branches=tk.IntVar(value=3)
        self.ponder_economical=tk.BooleanVar(value=True);self.dynamic_time=tk.BooleanVar(value=True)
        self.ponder_text=tk.StringVar(value='后台预判：等待对方回合')
        self.budget_text=tk.StringVar(value='思考预算：等待局面')
        self.fallback_first=tk.StringVar(value='我方先手')
        self.connection_text=tk.StringVar(value='先识别棋盘；本方固定为画面下方，无头像时按所选先手接入')
        self.analysis_key=None;self.analysis_title=tk.StringVar(value='局面分析（复用现有搜索；概率为引擎估计）')
        self.red_analysis=tk.StringVar(value=format_analysis(None,None)[0]);self.black_analysis=tk.StringVar(value=format_analysis(None,None)[1])
        try:
            with open(os.path.join(HERE,'settings.json'),encoding='utf-8') as f:settings=json.load(f)
            for name in ('seconds','threads','game_limit','unlimited','auto_reconnect','use_gpu','fallback_seconds','ponder_enabled','ponder_branches','ponder_economical','dynamic_time','fallback_first'):
                if name in settings:getattr(self,name).set(settings[name])
        except (OSError,ValueError,tk.TclError):pass
        self.last_move=None;self.view_flipped=False
        self.position_label=tk.StringVar(value='等待识别局面')
        self.connected_board=[['_']*9 for _ in range(10)];self.connected_side='w'
        from workspace_ui import build_shell
        build_shell(self,root,ENGINE)
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.poll)
        self.draw(self.connected_board)
    def draw(self,board):
        self.connected_board=[row.copy() for row in board]
        self.board_view.set_position(board,self.view_flipped,self.last_move)
    def copy_to_sandbox(self):
        if not any(piece!='_' for row in self.connected_board for piece in row):
            self.status.set('请先连接并识别一个棋盘。');return
        self.sandbox.load(self.connected_board,self.connected_side or 'w');self.notebook.select(self.sandbox)
    def start(self):
        if self.running:return
        if self.sandbox.busy:self.status.set('沙盒正在分析，请先停止沙盒提示。');return
        try:seconds=max(1,min(30,int(self.seconds.get())));threads=max(1,min(os.cpu_count() or 1,int(self.threads.get())))
        except (ValueError,tk.TclError):self.status.set('请输入有效秒数和线程数');return
        try:limit=0 if self.unlimited.get() else max(1,int(self.game_limit.get()))
        except (ValueError,tk.TclError):self.status.set('请输入有效局数');return
        self.running=True;self.stop.clear();self.status.set('正在启动并寻找棋盘…')
        while not self.commands.empty():self.commands.get_nowait()
        try:
            with open(os.path.join(HERE,'settings.json'),'w',encoding='utf-8') as f:
                json.dump({name:getattr(self,name).get() for name in ('seconds','threads','game_limit','unlimited','auto_reconnect','use_gpu','fallback_seconds','ponder_enabled','ponder_branches','ponder_economical','dynamic_time','fallback_first')},f)
        except OSError:pass
        threading.Thread(target=self.run,args=(seconds,threads,limit,self.auto_reconnect.get(),self.use_gpu.get(),self.fallback_seconds.get(),self.ponder_enabled.get(),self.ponder_branches.get(),self.ponder_economical.get(),self.dynamic_time.get(),self.connection_config()),daemon=True).start()
    def connection_config(self,manual=False):
        return {'mode':'manual' if manual else 'auto','player':'bottom','initial_turn':'other' if self.fallback_first.get()=='对方先手' else 'ours'}
    def fallback_changed(self):
        try:
            path=os.path.join(HERE,'settings.json')
            try:
                with open(path,encoding='utf-8') as f:settings=json.load(f)
            except (OSError,ValueError):settings={}
            settings['fallback_first']=self.fallback_first.get()
            with open(path+'.tmp','w',encoding='utf-8') as f:json.dump(settings,f)
            os.replace(path+'.tmp',path)
        except OSError:pass
        if self.running:
            self.commands.put(self.connection_config(manual=True));self.status.set('已更新先手设置，正在按当前棋盘重新接入…')
    def choose(self,bridge,ms):
        started=time.monotonic();self.events.put(('thinking_start',started))
        engine=bridge.tracker.engine;previous=getattr(engine,'on_evaluation',None)
        key=position_key(bridge.tracker.board,bridge.tracker.side);side=bridge.tracker.side
        engine.on_evaluation=lambda value:self.events.put(('evaluation',{'key':key,'side':side,'evaluation':value}))
        try:move=bridge.prepare(ms)
        except Exception:
            self.events.put(('thinking_end',(time.monotonic()-started,'invalid')));raise
        finally:engine.on_evaluation=previous
        elapsed=time.monotonic()-started
        evaluation=getattr(bridge.tracker,'last_evaluation',None)
        if evaluation:self.events.put(('evaluation',{'key':position_key(bridge.tracker.board,bridge.tracker.side),'side':bridge.tracker.side,'evaluation':evaluation}))
        self.events.put(('thinking_end',(elapsed,bridge.tracker.last_source)))
        return move,elapsed
    def run(self,seconds,threads,limit,auto_reconnect,use_gpu=True,fallback_seconds=30,ponder_enabled=True,ponder_branches=3,ponder_economical=True,dynamic_time=True,connection=None):
        engine=None;ponder=None;bridge=None
        connection=dict(connection or {'mode':'auto','player':'bottom','initial_turn':'w'})
        commands=getattr(self,'commands',queue.Queue());recalibrate=False
        log=open(os.path.join(HERE,'session.jsonl'),'a',encoding='utf-8',buffering=1)
        def event(kind,**data):
            record={'time':time.time(),'kind':kind,**data};log.write(json.dumps(record,ensure_ascii=False)+'\n')
        try:
            from windows_io import Window,u
            window=Window();window.focus();time.sleep(.6)
            recognizer=Recognizer(use_gpu=use_gpu);event('recognizer_started',backend=recognizer.backend)
            engine=Engine(ENGINE,threads=threads,hash_mb=512);bridge=Bridge(recognizer,engine,history_path=os.path.join(HERE,'game-history.json'),**connection)
            if ponder_enabled:
                ponder=Ponder(ENGINE,threads,ponder_branches,min_seconds=seconds,notify=lambda data:self.events.put(('ponder',data)),economical=ponder_economical)
            else:self.events.put(('ponder',{'state':'disabled'}))
            submitted=0;last_error=None;pending_since=None
            recovery=Recovery();popups=Popups();ads=Ads();last_popup=0;last_ad=0;probe_used=False;sync_failures=0
            rounds=Rounds(limit)
            flow=ScreenFlow(fallback_seconds)
            budget=ThinkingBudget(seconds,dynamic_time)
            own_key=None;own_seen=None;turn_compute=0
            while not self.stop.is_set():
                if u.GetAsyncKeyState(0x1B)&0x8001:self.stop.set();break
                trace=CycleTrace(self.events.put)
                try:
                    while not commands.empty():
                        connection=commands.get_nowait();recalibrate=True
                        bridge.mode=connection['mode'];bridge.player='bottom';bridge.initial_turn=connection['initial_turn']
                        flow.board_ok()
                        if ponder:ponder.clear()
                    task=flow.next()
                    if ponder and flow.mode not in ('board','enter'):ponder.clear()
                    if flow.mode not in ('board','enter') and task is None:
                        trace.stage('wait_ui');self.stop.wait(.2);continue
                    trace.stage('capture')
                    first,rect=window.capture();self.stop.wait(.12);second,rect2=window.capture()
                    if rect!=rect2:raise ValueError('窗口正在移动，重新定位')
                    if task:event('screen_flow_scan',stage=task,expected=flow.mode)
                    if task in ('ad','fallback'):trace.stage('ad_scan')
                    ad1=ads.button(first) if task in ('ad','fallback') else None
                    ad2=ads.button(second) if task in ('ad','fallback') else None
                    if ad1 and ad2 and max(abs(a-b) for a,b in zip(ad1,ad2))<3:
                        recovery.lost(time.time())
                        if time.monotonic()-last_ad>2:
                            fresh,rect3=window.capture();point=ads.button(fresh)
                            if rect3!=rect or not point or max(abs(a-b) for a,b in zip(point,ad2))>=3:raise ValueError('广告关闭按钮正在变化')
                            if self.stop.is_set():break
                            window.click(point,rect);window.park(rect);last_ad=time.monotonic();event('ad_closed')
                            flow.ad_closed()
                            self.events.put(('status','已关闭广告，正在确认继续游戏入口…'));self.stop.wait(.3)
                        else:flow.ad_wait();self.stop.wait(.1)
                        continue
                    if task and (ads.present(first) or ads.present(second)):
                        self.events.put(('status','广告仍在遮挡，等待关闭入口；暂不点击后方按钮。'))
                        flow.ad_wait()
                        self.stop.wait(.2);continue
                    if task in ('upgrade','fallback'):trace.stage('popup_scan')
                    popup1=popups.upgrade(first) if task in ('upgrade','fallback') else None
                    popup2=popups.upgrade(second) if task in ('upgrade','fallback') else None
                    if popup1 and popup2 and max(abs(a-b) for a,b in zip(popup1,popup2))<3:
                        recovery.lost(time.time())
                        if time.time()-last_popup>2:
                            fresh,rect3=window.capture();point=popups.upgrade(fresh)
                            if rect3!=rect or not point or max(abs(a-b) for a,b in zip(point,popup2))>=3:raise ValueError('弹窗正在变化')
                            if self.stop.is_set():break
                            window.click(point,rect);window.park(rect);last_popup=time.time();event('upgrade_dismissed')
                            flow.upgrade_closed()
                            self.events.put(('status','已关闭升级提示，正在恢复连接…'));time.sleep(.6)
                        continue
                    if task in ('continue','fallback'):trace.stage('continue_scan')
                    button1=recognizer.continue_button(first) if task in ('continue','fallback') else None
                    button2=recognizer.continue_button(second) if task in ('continue','fallback') else None
                    if button1 and button2 and max(abs(a-b) for a,b in zip(button1,button2))<3:
                        if not rounds.result():
                            event('limit_reached',games=rounds.finished);self.events.put(('status',f'已完成 {rounds.finished} 局，达到设定局数。'));break
                        if rounds.continuation():
                            fresh,rect3=window.capture();button3=recognizer.continue_button(fresh)
                            if ads.button(fresh) is not None or ads.present(fresh):
                                rounds.continue_sent=False;raise ValueError('广告遮挡续局按钮，先关闭广告')
                            if rect3!=rect or not button3 or max(abs(a-b) for a,b in zip(button2,button3))>=3:
                                rounds.continue_sent=False;raise ValueError('续战按钮变化，等待稳定')
                            if self.stop.is_set():break
                            window.click(button3,rect);window.park(rect);event('continue_clicked',games=rounds.finished,features=recognizer.end_screens.last_features)
                            flow.continued()
                            bridge=Bridge(recognizer,engine,history_path=os.path.join(HERE,'game-history.json'),**connection);pending_since=None
                            self.events.put(('status',f'已完成 {rounds.finished} 局，正在进入下一局…'));self.stop.wait(.4)
                        else:flow.missed('continue')
                        continue
                    if task:flow.missed(task)
                    trace.stage('board_sync')
                    try:
                        if recalibrate:
                            bridge.resync_pair(first,second);pending_since=None;probe_used=False;recalibrate=False
                            event('first_player_changed',ours=bridge.ours,turn=bridge.tracker.side)
                        state=bridge.observe_pair(first,second);sync_failures=0
                    except ValueError as sync_error:
                        if getattr(bridge,'observed_board',None) is not None:self.events.put(('board_info',(bridge.observed_board,None,None,bridge.flipped)))
                        previous_mode=flow.mode;flow.board_failed()
                        if flow.mode!=previous_mode:event('screen_flow_started',reason='four_failed_board_reads')
                        if any(t in str(sync_error) for t in ('无法唯一对应','未能匹配本方走法','头像提示与局面')):
                            sync_failures+=1
                            if sync_failures>=3:
                                old_moves=bridge.resync_pair(first,second);pending_since=None;probe_used=False;sync_failures=0
                                event('position_resynced',previous_moves=old_moves)
                        raise
                    if state!='complete':flow.board_ok(fen(bridge.tracker.board,bridge.tracker.side) if state=='waiting' else None)
                    paused=recovery.restored(time.time())
                    if paused:
                        if pending_since:pending_since+=paused
                        event('reconnected',paused_seconds=round(paused,2))
                    if state in ('ready','waiting') and rounds.continue_sent:rounds.new_game()
                    self.events.put(('board_info',(bridge.tracker.board,bridge.tracker.moves[-1] if bridge.tracker.moves else None,bridge.tracker.side,bridge.flipped)))
                    self.events.put(('connection_info',(getattr(bridge,'turn_source','走法历史'),bridge.ours)))
                    event('observed',state=state,fen=fen(bridge.tracker.board,bridge.tracker.side),moves=bridge.tracker.moves)
                    if ponder:
                        if state=='waiting':ponder.start(bridge.tracker)
                        elif state=='ready':
                            trace.stage('ponder_stop')
                            hint=ponder.match(bridge.tracker)
                            if hint:event('background_hit',opponent_move=bridge.tracker.moves[-1],reply=hint['move'],rank=hint['rank'],depth=hint['depth'],background_seconds=round(hint['seconds'],3))
                            adopted=ponder.promote(engine)
                            if adopted is not engine:
                                engine=adopted;bridge.engine=engine;bridge.tracker.engine=engine
                                event('background_engine_adopted',process_id=engine.process.pid)
                        else:ponder.clear()
                    if bridge.tracker.side==bridge.ours:
                        key=fen(bridge.tracker.board,bridge.tracker.side)
                        if key!=own_key:own_key=key;own_seen=trace.start;turn_compute=0
                    else:own_key=None;own_seen=None;turn_compute=0
                    last_error=None
                    if state=='awaiting_move':
                        trace.stage('wait_accept')
                        bootstrap=getattr(bridge,'provisional',False) or connection['mode']=='manual'
                        if pending_since and time.time()-pending_since>(2 if bootstrap else 8):
                            if bridge.may_move(None):
                                if not probe_used:
                                    _,destination=move_pixels(bridge.pending,bridge.box,bridge.flipped)
                                    if self.stop.is_set():break
                                    window.click(destination,rect);window.park(rect);probe_used=True;pending_since=time.time()
                                    event('recover_destination',move=bridge.pending)
                                else:
                                    if bootstrap:raise CalibrationRequired('落子未生效，棋盘已保留；请改选“我方先手/对方先手”后重新开始连接')
                                    event('retry_unaccepted_move',move=bridge.pending);bridge.pending=None;pending_since=None;probe_used=False
                    elif state=='turn_unconfirmed':
                        if not bridge.tracker.has_plan():
                            milliseconds=budget.milliseconds(bridge.tracker);bridge.tracker.refine=budget.factor>1
                            trace.stage('search');_,spent=self.choose(bridge,milliseconds);turn_compute+=spent
                            budget.record(bridge.tracker,bridge.tracker.last_evaluation)
                            event('prepared_before_turn_confirmation',seconds=round(spent,6),source=bridge.tracker.last_source)
                        trace.stage('wait_turn');self.events.put(('status','着法已算好，等待头像/计时确认后落子。'))
                    elif state=='ready':
                        milliseconds=budget.milliseconds(bridge.tracker);bridge.tracker.refine=budget.factor>1
                        self.events.put(('budget',(milliseconds/1000,budget.reason)))
                        event('thinking_budget',seconds=milliseconds/1000,factor=budget.factor,reason=budget.reason)
                        trace.stage('search');move,decision_seconds=self.choose(bridge,milliseconds);turn_compute+=decision_seconds
                        budget.record(bridge.tracker,bridge.tracker.last_evaluation)
                        decision_ms=round(decision_seconds*1000)
                        if self.stop.is_set():break
                        if not commands.empty():continue
                        trace.stage('move_recheck')
                        # Recheck the board and geometry immediately before selecting a piece.
                        fresh,rect3=window.capture();board,flipped,box=recognizer.read(fresh)
                        if board!=bridge.tracker.board or flipped!=bridge.flipped or box!=bridge.box or rect3!=rect:raise ValueError('计算期间棋盘或窗口变化，重新识别')
                        if not bridge.may_move(None):raise ValueError('行棋历史尚未确认本方走棋')
                        origin,destination=move_pixels(move,box,flipped)
                        bridge.submitted(move);pending_since=time.time();probe_used=False
                        trace.stage('click')
                        window.click(origin,rect);time.sleep(.18)
                        if self.stop.is_set():break
                        window.click(destination,rect);window.park(rect)
                        submitted+=1
                        total=time.monotonic()-(own_seen if own_seen is not None else trace.start)
                        self.events.put(('latency',(total,turn_compute)))
                        event('submitted',move=move,count=submitted,excluded_repetitions=bridge.tracker.filtered_reasons,decision_source=bridge.tracker.last_source,decision_ms=decision_ms,decision_seconds=round(decision_seconds,6),turn_elapsed_seconds=round(total,6),turn_compute_seconds=round(turn_compute,6),non_compute_seconds=round(max(0,total-turn_compute),6))
                        source={'ponder_cache':'后台多分支命中','pv_cache':'预判命中','position_cache':'复用已算着法','opening_book':'开局库','engine':'引擎计算'}[bridge.tracker.last_source]
                        protection=f'已避开 {len(bridge.tracker.filtered)} 个循环着法；' if bridge.tracker.filtered else ''
                        self.events.put(('status',f'{source}：已落子 {move}，{protection}等待棋盘确认；本次已走 {submitted} 步。'))
                    elif state=='complete':
                        flow.ended()
                        if not rounds.result():
                            self.events.put(('status',f'已完成 {rounds.finished} 局，达到设定局数。'));event('limit_reached',games=rounds.finished);break
                        self.events.put(('status',f'练习题已完成；本次已走 {submitted} 步。打开下一题后会继续识别。'))
                    else:
                        trace.stage('wait_opponent')
                        self.events.put(('status',f'已同步局面，等待本方走棋；本次已走 {submitted} 步。'))
                    self.stop.wait(.08)
                except (ValueError,OSError) as e:
                    if ponder:ponder.pause()
                    trace.stage('recover')
                    msg=str(e)
                    recovery.lost(time.time())
                    if auto_reconnect and any(t in msg for t in ('前台','窗口已关闭','只打开一个')) and recovery.attempt(time.time()):
                        if window.reconnect():event('focus_recovered')
                    if msg!=last_error:event('waiting',reason=msg);last_error=msg
                    self.events.put(('status',friendly(msg)));self.stop.wait(.10)
                finally:
                    event('pipeline_timing',**trace.finish())
            event('stopped',count=submitted)
        except Exception as e:
            if bridge is not None and getattr(bridge,'observed_board',None) is not None:self.events.put(('board_info',(bridge.observed_board,None,None,bridge.flipped)))
            event('error',reason=str(e));self.events.put(('status','已停止：'+str(e)))
        finally:
            if ponder:ponder.close()
            if engine:engine.close()
            log.close();self.events.put(('thinking_cancelled',time.monotonic()));self.events.put(('done',None))
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='board':self.draw(value)
                elif kind=='thinking_start':self.thinking_started=value
                elif kind=='thinking_end':
                    seconds,source=value;self.thinking_started=None;self.thinking_text.set(thought_summary(seconds,source))
                elif kind=='thinking_cancelled':
                    if self.thinking_started is not None:
                        self.thinking_text.set(thought_summary(max(0,value-self.thinking_started),'stopped'));self.thinking_started=None
                elif kind=='phase':
                    self.phase_name,self.phase_started=value
                    self.phase_text.set('当前阶段：'+self.phase_name)
                elif kind=='latency':
                    total,compute=value
                    self.latency_text.set(f'本步总用时：{total:.3f} 秒｜选招 {compute:.3f} 秒｜其他等待 {max(0,total-compute):.3f} 秒')
                elif kind=='board_info':
                    board,self.last_move,side,self.view_flipped=value
                    self.connected_side=side
                    previous='尚未跟踪'
                    if self.last_move:
                        p=board[9-int(self.last_move[3])][ord(self.last_move[2])-97]
                        previous=('红方' if p.isupper() else '黑方')+LABEL.get(p,'棋子')+' '+self.last_move[:2]+' → '+self.last_move[2:]
                    key=position_key(board,side) if side in ('w','b') else None
                    if key!=self.analysis_key:
                        self.analysis_key=key;red,black=format_analysis(None,None);self.red_analysis.set(red);self.black_analysis.set(black)
                        self.analysis_title.set('局面分析（等待现有搜索结果；概率为引擎估计）')
                    self.position_label.set(('红方走棋' if side=='w' else '黑方走棋' if side=='b' else '棋盘已识别，走棋方待校准')+'　上一步：'+previous)
                    self.draw(board)
                elif kind=='status':self.status.set(value)
                elif kind=='connection_info':
                    source,ours=value;self.connection_text.set(f'接入：{source}｜下方为本方（{"红" if ours=="w" else "黑"}）')
                elif kind=='evaluation':self.show_evaluation(value)
                elif kind=='budget':
                    seconds,reason=value;self.budget_text.set(f'本步思考预算：{seconds:.2f} 秒｜{reason}')
                elif kind=='ponder':
                    state=value['state']
                    if state=='thinking':
                        self.ponder_text.set(f'后台预判：{len(value["lines"])} 分支｜深度 {value["depth"]}｜已算 {value["seconds"]:.1f} 秒')
                        if value.get('key') and value.get('lines'):self.show_evaluation({'key':value['key'],'side':value['side'],'evaluation':value['lines'][0]})
                    elif state=='starting':self.ponder_text.set(f'后台预判：正在分析 {value["branches"]} 分支，使用 {value["threads"]} 线程')
                    elif state=='hit':self.ponder_text.set(f'后台预判：命中第 {value["rank"]} 分支｜深度 {value["depth"]}｜后台 {value["seconds"]:.1f} 秒')
                    elif state=='budget':self.ponder_text.set(f'后台预判：{"评分与主应手已稳定" if value["reason"]=="stable" else "已达预算"}，暂存结果｜{value["seconds"]:.1f} 秒')
                    else:self.ponder_text.set({'idle':'后台预判：等待对方回合','paused':'后台预判：已暂停，等待棋盘稳定','disabled':'后台预判：已关闭','continue':'后台预判：接管已有缓存，继续计算实际局面','miss':'后台预判：对方偏离分支，正常计算','error':'后台预判：暂不可用，正常计算'}.get(state,'后台预判：等待对方回合'))
                elif kind=='done':
                    self.running=False;self.phase_started=None;self.phase_text.set('当前阶段：已停止');self.ponder_text.set('后台预判：已停止')
        except queue.Empty:pass
        if self.thinking_started is not None:self.thinking_text.set(f'正在思考：{time.monotonic()-self.thinking_started:.2f} 秒')
        self.root.after(100,self.poll)
    def show_evaluation(self,value):
        if value['key']!=self.analysis_key:return
        red,black=format_analysis(value['evaluation'],value['side'])
        self.red_analysis.set(red);self.black_analysis.set(black)
        self.analysis_title.set(f'局面分析（引擎估计·深度 {value["evaluation"].get("depth",0)}）')
    def close(self):
        self.stop.set();self.sandbox.close()
        self.root.destroy()
if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
