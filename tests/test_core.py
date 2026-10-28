import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'connector/bridge'))
from sandbox_model import SandboxModel,START,parse_fen,validate,move_name,score_order
from board_bootstrap import resolve
from position_analysis import format_analysis
from thinking_budget import ThinkingBudget

class SandboxStateTests(unittest.TestCase):
    def test_start_roundtrip_and_undo(self):
        model=SandboxModel();validate(model.board,model.side)
        self.assertEqual(model.export(),START)
        model.move((9,0),(8,0));self.assertEqual(model.board[8][0],'R')
        model.undo();self.assertEqual(model.export(),START)
        model.place(5,1,'N');model.undo();self.assertEqual(model.export(),START)
        model.apply('c3c4');self.assertEqual(model.side,'b')
    def test_invalid_edit_is_rejected_before_engine(self):
        model=SandboxModel();model.board[9][4]='_'
        with self.assertRaisesRegex(ValueError,'帅'):validate(model.board,model.side)
        model=SandboxModel();model.board[9][3]='_';model.board[5][3]='A'
        with self.assertRaisesRegex(ValueError,'士'):validate(model.board,model.side)
        model=SandboxModel();model.board[6][0]='_';model.board[6][1]='P'
        with self.assertRaisesRegex(ValueError,'兵'):validate(model.board,model.side)
        with self.assertRaises(ValueError):parse_fen('9/9 w')
    def test_notation_and_ordering(self):
        model=SandboxModel();self.assertEqual(move_name(model.board,'h2e2'),'炮二平五')
        self.assertGreater(score_order({'score_type':'mate','score':3}),score_order({'score_type':'cp','score':1000}))
        self.assertGreater(score_order({'score_type':'mate','score':-9}),score_order({'score_type':'mate','score':-2}))

class CompatibilityTests(unittest.TestCase):
    def test_bottom_and_relative_first(self):
        board,_=parse_fen(START)
        for flipped in (False,True):
            ours='b' if flipped else 'w'
            for first in ('ours','other'):
                turn,player,_,_=resolve(board,flipped,None,None,'manual','bottom',first)
                self.assertEqual(player,ours)
                self.assertEqual(turn,ours if first=='ours' else ('w' if ours=='b' else 'b'))
    def test_wdl_perspective(self):
        red,black=format_analysis({'score_type':'cp','score':120,'wdl':[300,600,100]},'b')
        self.assertIn('-1.20',red);self.assertIn('10.0%',red)
        self.assertIn('+1.20',black);self.assertIn('30.0%',black)
    def test_opening_does_not_get_extra_time(self):
        from types import SimpleNamespace
        tracker=SimpleNamespace(initial=START,moves=[]);budget=ThinkingBudget(5)
        for n in range(0,20,2):
            tracker.moves=['x']*n;self.assertEqual(budget.milliseconds(tracker),5000)
            budget.record(tracker,{'score_type':'cp','score':-300})
        self.assertEqual(budget.factor,1)

if __name__=='__main__':unittest.main()
