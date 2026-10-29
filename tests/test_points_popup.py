"""Synthetic offer cards exercise detection without publishing game screenshots."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'connector/bridge'))
from popups import Popups
from screen_flow import ScreenFlow
from vision import cv2,np


class PointsPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.detector=Popups()

    def image(self,scale=1,title=True,close=True,body_title=False):
        card=np.full((480,560,3),(235,248,255),np.uint8)
        if title:
            t=self.detector.points_title;h,w=t.shape
            row=240 if body_title else 42
            card[row:row+h,200:200+w]=cv2.cvtColor(t,cv2.COLOR_GRAY2BGR)
        if close:
            p=ROOT/'connector/bridge/ui_templates/points-close.png'
            icon=cv2.imdecode(np.fromfile(str(p),np.uint8),cv2.IMREAD_COLOR)
            card[7:64,500:557]=icon
        cv2.rectangle(card,(100,320),(460,410),(40,220,50),-1)
        image=np.full((1336,728,3),30,np.uint8)
        image[445:925,84:644]=card
        return cv2.resize(image,None,fx=scale,fy=scale)

    def test_close_location_across_scales(self):
        for scale in (.6,1,1.4):
            with self.subTest(scale=scale):
                point=self.detector.points(self.image(scale))
                self.assertIsNotNone(point)
                self.assertLess(abs(point[0]-(84+528.5)*scale),3)
                self.assertLess(abs(point[1]-(445+35.5)*scale),3)

    def test_needs_title_and_own_red_close_control(self):
        for options in ({'title':False},{'close':False},{'body_title':True}):
            with self.subTest(options=options):self.assertIsNone(self.detector.points(self.image(**options)))
        self.assertIsNone(self.detector.points(np.zeros((1000,700,3),np.uint8)))

    def test_optional_chain_after_points_does_not_skip_upgrade(self):
        now=[0.];flow=ScreenFlow(clock=lambda:now[0])
        self.assertIsNone(flow.next())
        flow.ended();self.assertEqual(flow.next(),'ad')
        flow.points_closed();self.assertIsNone(flow.next())
        now[0]=.36;self.assertEqual(flow.next(),'upgrade')
        now[0]=.9;flow.missed('upgrade')
        now[0]=1.01;self.assertEqual(flow.next(),'continue')


if __name__=='__main__':unittest.main()
