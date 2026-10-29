import sys,unittest,tempfile
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'connector/bridge'))
from manual_grid import grid_box,center,validate_corners
from manual_vision import ManualRecognizer,START,opening_board
from vision import cv2,np,move_pixels
from tracker import Engine,replay_positions,moved,Tracker
from controller import Bridge
from board_bootstrap import resolve
from piece_ocr import PieceOCR,MODEL
from skin_store import SkinStore


def render(board,flipped=False):
    shown=[list(reversed(row)) for row in reversed(board)] if flipped else board
    image=np.full((700,600,3),(200,220,235),np.uint8)
    for c in range(9):cv2.line(image,(60+c*60,60),(60+c*60,600),(100,120,140),1)
    for r in range(10):cv2.line(image,(60,60+r*60),(540,60+r*60),(100,120,140),1)
    for r in range(10):
        for c in range(9):
            p=shown[r][c]
            if p=='_':continue
            xy=(60+c*60,60+r*60)
            cv2.circle(image,xy,24,(220,235,245),-1,cv2.LINE_AA)
            cv2.circle(image,xy,24,(20,20,20),2,cv2.LINE_AA)
            cv2.putText(image,p.upper(),(xy[0]-9,xy[1]+8),cv2.FONT_HERSHEY_SIMPLEX,.7,(30,30,200) if p.isupper() else (20,20,20),2,cv2.LINE_AA)
    return image


class ManualGeometryTests(unittest.TestCase):
    def test_grid_and_flipped_click_coordinates(self):
        config={'corners':[[.1,60/700],[.9,600/700]]};box=grid_box(config,(700,600,3))
        self.assertEqual(center(box,9,8),(540,600))
        self.assertEqual(move_pixels('a0a1',box,False),[(60,600),(60,540)])
        self.assertEqual(move_pixels('a0a1',box,True),[(540,60),(540,120)])
        larger=grid_box(config,(1400,1200,3));self.assertEqual(center(larger,9,8),(1080,1200))
        for points in ([],[[.2,.2],[.2,.8]],[[0,0],[2,1]]):
            with self.assertRaises(ValueError):validate_corners(points)

    def test_our_side_default_is_provisional(self):
        _,board,_=replay_positions(START,[])
        turn,ours,provisional,_=resolve(board,True,None,None,'grid','bottom','ours')
        self.assertEqual((turn,ours,provisional),('b','b',True))

    @unittest.skipUnless(Path(MODEL).exists(),'Chinese OCR model not installed')
    def test_chinese_ocr_without_opening_initialization(self):
        image=cv2.imdecode(np.fromfile(str(ROOT/'connector/bridge/frame-alt.png'),np.uint8),cv2.IMREAD_COLOR)
        patches=[]
        for row,col in ((9,1),(0,2)):
            x=round(37+col*78.9);y=round(40+row*77.8)
            patches.append(image[y-21:y+21,x-21:x+21])
        self.assertEqual(PieceOCR(use_gpu=False).read(patches),['N','b'])


@unittest.skipUnless((ROOT/'engine/pikafish.exe').exists(),'official engine not installed')
class ManualRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.skin_patch=patch('piece_ocr.SkinStore',lambda:SkinStore(self.directory.name));self.skin_patch.start()
    def tearDown(self):
        self.skin_patch.stop();self.directory.cleanup()
    @classmethod
    def setUpClass(cls):
        cls.engine=Engine(str(ROOT/'engine/pikafish.exe'),threads=1,hash_mb=32)
        cls.moves=cls.engine.legal(START,[])
    @classmethod
    def tearDownClass(cls):cls.engine.close()

    def test_arbitrary_skin_start_and_one_move_on_black_side(self):
        _,start,_=replay_positions(START,[])
        for board,flip in ((start,False),(moved(start,'a3a4'),True)):
            with self.subTest(flip=flip):
                config={'corners':[[.1,60/700],[.9,600/700]],'bottom_color':'auto'}
                rec=ManualRecognizer(config,self.moves,use_gpu=False)
                result,flipped,box=rec.read(render(board,flip))
                self.assertEqual(result,board);self.assertEqual(flipped,flip)
                self.assertIn('开局外观学习',rec.source)
                after=moved(board,'b9c7' if flip else 'b0c2')
                result,flipped,_=rec.read(render(after,flip))
                self.assertEqual(result,after);self.assertEqual(flipped,flip)

    def test_opponent_change_discards_unsuccessful_own_probe(self):
        _,start,_=replay_positions(START,[])
        bridge=Bridge(None,self.engine,mode='grid',initial_turn='ours')
        bridge.tracker=Tracker(self.engine,start,'b');bridge.ours='b';bridge.provisional=True;bridge.pending='b9c7'
        self.assertTrue(bridge.accept_initial_opponent(moved(start,'a3a4')))
        self.assertEqual(bridge.tracker.moves,['a3a4']);self.assertEqual(bridge.tracker.side,'b')
        self.assertIsNone(bridge.pending);self.assertFalse(bridge.provisional)

    def test_restart_midgame_and_reset_keep_learned_skin(self):
        _,start,_=replay_positions(START,[])
        config={'corners':[[.1,60/700],[.9,600/700]],'bottom_color':'auto'}
        rec=ManualRecognizer(config,self.moves,use_gpu=False);rec.read(render(start))
        _,midgame,_=replay_positions(START,['b0c2','b9c7','h0g2','h9g7'])
        restored=ManualRecognizer(config,self.moves,use_gpu=False)
        self.assertEqual(restored.read(render(midgame))[0],midgame)
        self.assertIn('已保存的皮肤',restored.source)
        references=restored.appearance.references;restored.reset_game()
        self.assertIs(restored.appearance.references,references)
        self.assertEqual(restored.read(render(midgame))[0],midgame)


if __name__=='__main__':unittest.main()
