import sys,os,time,unittest,tkinter as tk
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'connector/bridge'))
from sandbox_model import SandboxModel,START,score_order
from tracker import Engine
from app import App

@unittest.skipUnless((ROOT/'engine/pikafish.exe').exists(),'official engine not installed')
class EngineAndUiTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.app=App(self.root)
    def tearDown(self):self.app.close()
    def test_three_timed_candidates_and_visualization(self):
        engine=Engine(str(ROOT/'engine/pikafish.exe'),threads=2,hash_mb=64)
        try:
            lines=engine.top_moves(START,450,3)
            self.assertEqual(len(lines),3);self.assertEqual(len({v['pv'][0] for v in lines}),3)
            self.assertEqual([score_order(v) for v in lines],sorted([score_order(v) for v in lines],reverse=True))
            legal=engine.legal(START,[]);self.assertTrue(all(v['pv'][0] in legal for v in lines))
            self.assertTrue(all(sum(v['wdl'])==1000 for v in lines))
            sandbox=self.app.sandbox;sandbox.events.put(('hints',sandbox.generation,(lines,'w')));sandbox.poll()
            self.assertEqual(len(sandbox.board.find_withtag('hint_arrow')),3)
            before=sandbox.model.export();sandbox.select_hint(1);sandbox.apply_hint()
            self.assertNotEqual(sandbox.model.export(),before);self.assertFalse(sandbox.hints)
        finally:engine.close()
    def test_tabs_and_no_idle_search(self):
        self.assertEqual([self.app.notebook.tab(i,'text') for i in range(3)],['连接对局','沙盒摆棋','设置与诊断'])
        sandbox=self.app.sandbox;self.assertIsNone(sandbox.engine)
        sandbox.clear()
        with patch('sandbox.Engine',side_effect=AssertionError('invalid board spawned an engine')):sandbox.analyze()
        self.assertFalse(sandbox.busy);self.assertIsNone(sandbox.engine)
    def test_stale_hint_and_flip_coordinates(self):
        sandbox=self.app.sandbox;old=sandbox.generation
        sandbox.model.place(6,0,'_');sandbox.invalidate()
        sandbox.events.put(('hints',old,([], 'w')));sandbox.poll();self.assertFalse(sandbox.hints)
        view=sandbox.board
        for flipped in (False,True):
            view.flipped=flipped
            for row,col in ((0,0),(9,8),(4,4)):
                self.assertEqual(view.square(*view.center(row,col)),(row,col))
    def test_connection_blocks_sandbox_search(self):
        self.app.running=True;self.app.sandbox.analyze()
        self.assertFalse(self.app.sandbox.busy);self.assertIn('停止连接',self.app.sandbox.status.get())
        self.app.running=False

if __name__=='__main__':unittest.main()
