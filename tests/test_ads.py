"""Check SDK anchors with synthetic creatives and changing close backgrounds."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'connector/bridge'))
from ads import Ads
from vision import cv2,np


class AdCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ads=Ads()

    def image(self,backdrop=25,scale=1,label=True,close_y=476,action=True):
        image=np.full((1336,728,3),backdrop,np.uint8)
        cv2.rectangle(image,(201,516),(527,902),(255,255,255),-1)
        cv2.rectangle(image,(220,555),(470,675),(50,110,180),-1)
        if action:cv2.rectangle(image,(272,822),(455,861),(70,190,30),-1)
        cv2.line(image,(201,699),(527,699),(140,140,140))
        if label:
            marker=cv2.cvtColor(self.ads.label,cv2.COLOR_GRAY2BGR)
            image[525:546,204:235]=marker
        if close_y is not None:
            # Alter the icon's outer backdrop while retaining its actual X.
            icon=np.full((31,31,3),backdrop,np.uint8)
            icon[5:26,5:26]=cv2.cvtColor(self.ads.close_core,cv2.COLOR_GRAY2BGR)
            image[close_y:close_y+31,497:528]=icon
        return cv2.resize(image,None,fx=scale,fy=scale)

    def test_changing_backdrop_and_scaled_window(self):
        for backdrop in (0,65,140,210):
            for scale in (.7,1,1.35):
                with self.subTest(backdrop=backdrop,scale=scale):
                    point=self.ads.button(self.image(backdrop,scale))
                    self.assertIsNotNone(point)
                    self.assertLess(abs(point[0]-512.5*scale),3)
                    self.assertLess(abs(point[1]-491.5*scale),3)
                    self.assertGreater(self.ads.last_features['close_core_score'],.94)

    def test_requires_sdk_or_action_footer_and_external_x(self):
        self.assertIsNotNone(self.ads.button(self.image(label=False)))
        self.assertEqual(self.ads.last_features['anchor'],'footer_16_9')
        self.assertIsNone(self.ads.button(self.image(label=False,action=False)))
        self.assertIsNone(self.ads.button(self.image(close_y=None)))
        self.assertIsNone(self.ads.button(self.image(close_y=600)))
        self.assertIsNone(self.ads.button(np.zeros((1000,700,3),np.uint8)))


if __name__=='__main__':unittest.main()
