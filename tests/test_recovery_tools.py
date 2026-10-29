import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'connector/bridge'))
from vision import np,cv2,BoardBox
from manual_grid import grid_box
from skin_store import SkinStore
from piece_ocr import Appearance,red_ink
from visual_stability import stable_pieces
from tracker import replay_positions
from sandbox_model import START
from test_manual_recognition import render
from manual_vision import complete_from_history
from tracker import moved


class RecoveryToolTests(unittest.TestCase):
    def test_legal_history_fills_only_small_unique_uncertainty(self):
        _,board,_=replay_positions(START,['b0c2'])
        positions=[(r,c) for r in range(10) for c in range(9) if board[r][c]!='_']
        labels=[board[r][c] for r,c in positions];index=positions.index((7,2));labels[index]=None
        result=complete_from_history(positions,labels,[board,moved(board,'a6a5')],False)
        self.assertEqual(result[index],'N')
        wrong=labels.copy();wrong[positions.index((0,0))]='c'
        self.assertIsNone(complete_from_history(positions,wrong,[board],False))
        self.assertIsNone(complete_from_history(positions,[None]*len(labels),[board],False))
    def test_content_relative_points_survive_letterboxing_change(self):
        config={'version':2,'reference_size':[1200,640],'corners':[[.375,.1],[.625,.9]],'content_corners':[[.125,.1],[.875,.9]]}
        wide=np.zeros((640,1200,3),np.uint8);wide[:,400:800]=60
        portrait=np.full((640,400,3),60,np.uint8)
        self.assertEqual(grid_box(config,wide.shape,wide),BoardBox((450,64,300,512),'manual'))
        self.assertEqual(grid_box(config,portrait.shape,portrait),BoardBox((50,64,300,512),'manual'))
        old=dict(config);old.pop('content_corners')
        with self.assertRaises(ValueError):grid_box(old,portrait.shape)

    def test_background_effect_does_not_invalidate_stable_piece_bodies(self):
        _,board,_=replay_positions(START,[]);first=render(board);second=first.copy()
        second[310:350,:]=(10,250,150)
        box=BoardBox((60,60,480,540),'manual')
        self.assertTrue(stable_pieces(first,second,board,box,False))
        second=first.copy();second[578:622,278:322]=0
        self.assertFalse(stable_pieces(first,second,board,box,False))

    def test_skin_profiles_reload_without_an_opening_board(self):
        image=cv2.imdecode(np.fromfile(str(ROOT/'connector/bridge/frame-alt.png'),np.uint8),1)
        patches=[]
        for row,col in ((9,1),(0,2)):
            x=round(37+col*78.9);y=round(40+row*77.8);patches.append(image[y-21:y+21,x-21:x+21])
        with tempfile.TemporaryDirectory() as directory:
            matcher=Appearance(False);matcher.store=SkinStore(directory);matcher.learn(patches,['N','b'],persist=True)
            restored=Appearance(False);restored.store=SkinStore(directory)
            self.assertTrue(restored.load_matching(patches));self.assertEqual(restored.read(patches),['N','b'])
            with np.load(next(Path(directory).glob('*.npz')),allow_pickle=False) as data:self.assertEqual(set(data.files),{'features','labels'})

    def test_translated_glyph_and_colored_rim_keep_identity(self):
        image=cv2.imdecode(np.fromfile(str(ROOT/'connector/bridge/frame-alt.png'),np.uint8),1)
        patches=[]
        for row,col in ((9,1),(0,2)):
            x=round(37+col*78.9);y=round(40+row*77.8);patches.append(image[y-21:y+21,x-21:x+21])
        matcher=Appearance(False);matcher.learn(patches,['N','b'])
        shifted=[cv2.warpAffine(p,np.array([[1,0,2],[0,1,-3]],np.float32),(42,42),borderMode=cv2.BORDER_REPLICATE) for p in patches]
        cv2.circle(shifted[1],(21,21),20,(0,0,255),2)
        self.assertLessEqual(red_ink(shifted[1]),10)
        self.assertEqual(matcher.read(shifted),['N','b'])


if __name__=='__main__':unittest.main()
