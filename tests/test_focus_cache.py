"""Losing focus cannot erase a verified plan or a matching searched branch."""
import copy,sys,unittest,time
from pathlib import Path
from unittest.mock import MagicMock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'connector/bridge'))
from tracker import Engine,Tracker,moved,replay_positions,position_key
from controller import Bridge,advance_manual_confirmation
from pondering import Ponder
from sandbox_model import START
from vision import np,BoardBox


PV=['a3a4','a6a5','b0c2','b9c7','c2e1']


class FixedSearch:
    def __init__(self,engine):self.engine=engine;self.searches=0;self.last_score=None;self.last_pv=[];self.last_depth=0
    def legal(self,*args):return self.engine.legal(*args)
    def checking(self,*args):return self.engine.checking(*args)
    def best(self,*args,**kwargs):
        self.searches+=1;self.last_score={'score':33,'score_type':'cp','depth':18,'wdl':[200,700,100]}
        self.last_pv=PV.copy();self.last_depth=18;return PV[0]


class Observed:
    def __init__(self,board):self.board=board
    def read(self,image):return copy.deepcopy(self.board),False,BoardBox((0,0,300,300))
    def practice_complete(self,*args):return False
    def practice_turn(self,*args):return None


@unittest.skipUnless((ROOT/'engine/pikafish.exe').exists(),'official engine not installed')
class FocusCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.engine=Engine(str(ROOT/'engine/pikafish.exe'),threads=1,hash_mb=32)
    @classmethod
    def tearDownClass(cls):cls.engine.close()
    def setUp(self):
        _,self.board,_=replay_positions(START,[]);self.fake=FixedSearch(self.engine)

    def bridge(self):
        bridge=Bridge(Observed(self.board),self.fake)
        bridge.tracker=Tracker(self.fake,copy.deepcopy(self.board),'w');bridge.ours='w';bridge.turn_known=True
        bridge.tracker.book={}
        bridge.prepare(500);self.assertEqual(self.fake.searches,1)
        return bridge

    def test_same_board_resync_keeps_plan_score_and_tracker(self):
        bridge=self.bridge();tracker=bridge.tracker
        frame=np.zeros((300,300,3),np.uint8)
        bridge.resync_pair(frame,frame)
        self.assertTrue(bridge.last_resync_reused);self.assertIs(bridge.tracker,tracker)
        self.assertEqual(bridge.prepare(500),'a3a4');self.assertEqual(self.fake.searches,1)
        self.assertEqual(tracker.last_source,'position_cache');self.assertEqual(tracker.last_evaluation['score'],33)
        self.assertTrue(bridge.confirm_board(self.board,'w',False,BoardBox((0,0,300,300))))
        self.assertIs(bridge.tracker,tracker);self.assertEqual(bridge.prepare(500),'a3a4')
        self.assertEqual(self.fake.searches,1)

    def test_multiple_expected_plies_restore_history_and_next_reply(self):
        bridge=self.bridge();tracker=bridge.tracker;board=self.board
        for move in PV[:4]:board=moved(board,move)
        bridge.recognizer.board=board
        frame=np.zeros((300,300,3),np.uint8);bridge.resync_pair(frame,frame)
        self.assertIs(bridge.tracker,tracker);self.assertEqual(tracker.moves,PV[:4])
        self.assertEqual(bridge.prepare(500),PV[4]);self.assertEqual(self.fake.searches,1)
        self.assertEqual(tracker.last_source,'pv_cache')

    def test_unknown_change_does_not_reuse_cached_next_reply(self):
        bridge=self.bridge();tracker=bridge.tracker;changed=moved(moved(self.board,'c3c4'),'a6a5')
        bridge.recognizer.board=changed
        frame=np.zeros((300,300,3),np.uint8)
        with self.assertRaises(ValueError):bridge.resync_pair(frame,frame)
        self.assertFalse(bridge.last_resync_reused)
        self.assertIs(bridge.tracker,tracker);self.assertEqual(tracker.board,self.board)
        bridge.recognizer.board=self.board;bridge.resync_pair(frame,frame)
        self.assertEqual(bridge.prepare(500),'a3a4');self.assertEqual(self.fake.searches,1)

    def test_manual_confirmation_accepts_only_one_unique_legal_change(self):
        after=moved(self.board,'a3a4')
        self.assertEqual(advance_manual_confirmation(self.engine,self.board,'w',after),(after,'b',True))
        self.assertEqual(advance_manual_confirmation(self.engine,self.board,'w',self.board),(self.board,'w',False))
        with self.assertRaises(ValueError):advance_manual_confirmation(self.engine,self.board,'w',moved(after,'a6a5'))

    def test_paused_ponder_keeps_branch_on_same_root_and_hits_reply(self):
        tracker=Tracker(self.fake,copy.deepcopy(self.board),'w');tracker.accept_move('a3a4')
        ponder=Ponder('unused',1)
        identity=(tracker.initial,tuple(tracker.moves),position_key(tracker.board,tracker.side))
        ponder.root={'identity':identity,'initial':tracker.initial,'moves':tracker.moves.copy(),'board':copy.deepcopy(tracker.board),'side':tracker.side}
        result={'analysis_ready':True,'depth':18,'seconds':5,'stable_replies':['a6a5'],
                'lines':[{'pv':['a6a5','b0c2','b9c7'],'depth':18,'rank':1,'score':-22,'score_type':'cp'}]}
        ponder.results=result;old_root=ponder.root;ponder.pause()
        with patch('pondering.threading.Thread') as factory:
            factory.return_value.is_alive.return_value=False
            ponder.start(tracker)
            self.assertIs(ponder.results,result);self.assertIs(ponder.root,old_root)
            tracker.accept_move('a6a5');hint=ponder.match(tracker)
        self.assertEqual(hint['move'],'b0c2')
        self.assertEqual(tracker.best_safe(500),'b0c2');self.assertEqual(tracker.last_source,'ponder_cache')
        self.assertEqual(self.fake.searches,0)

    def test_native_ponder_resume_keeps_process_and_active_search_budget(self):
        tracker=Tracker(self.engine,copy.deepcopy(self.board),'w');tracker.accept_move('a3a4')
        ponder=Ponder(str(ROOT/'engine/pikafish.exe'),1,min_seconds=.3,economical=False)
        try:
            ponder.start(tracker);deadline=time.monotonic()+4
            while ponder.results is None and time.monotonic()<deadline:time.sleep(.01)
            self.assertIsNotNone(ponder.results)
            ponder.pause();root=ponder.root;process=ponder.engine.process.pid
            before=root['searched_seconds'];depth=ponder.results['depth']
            ponder.start(tracker);time.sleep(.05);ponder.pause()
            self.assertIs(ponder.root,root);self.assertEqual(ponder.engine.process.pid,process)
            self.assertGreaterEqual(root['searched_seconds'],before)
            self.assertGreaterEqual(ponder.results['depth'],depth)
        finally:ponder.close()


if __name__=='__main__':unittest.main()
