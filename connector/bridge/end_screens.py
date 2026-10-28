"""Recognize the game's bottom continuation control independently of ad content."""
import os
from vision import cv2,np,HERE

class EndScreens:
    def __init__(self):
        path=os.path.join(HERE,'ui_templates','continue-alt.png')
        image=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_GRAYSCALE)
        # Only the fixed lettering is learned. Neither advertisements nor the
        # result banner/avatar identity participate in template matching.
        self.text=image[30:79,109:285]
        self.confirm=cv2.imdecode(np.fromfile(os.path.join(HERE,'ui_templates','upgrade-alt-text.png'),np.uint8),0)
        self.title=cv2.imdecode(np.fromfile(os.path.join(HERE,'ui_templates','upgrade-alt-title.png'),np.uint8),0)
        self.last_features=None

    def continuation(self,image):
        return self._button(image,self.text)

    def upgrade(self,image):
        point=self._button(image,self.confirm)
        if point is None:return None
        # A generic confirmation is actionable only with the upgrade title too.
        scale=self.last_features['width']/392
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        roi=gray[round(image.shape[0]*.12):round(image.shape[0]*.48),round(image.shape[1]*.12):round(image.shape[1]*.88)]
        t=cv2.resize(self.title,None,fx=scale,fy=scale)
        if roi.shape[0]<t.shape[0] or roi.shape[1]<t.shape[1]:return None
        _,score,_,_=cv2.minMaxLoc(cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED))
        return point if score>.92 else None

    def _button(self,image,text):
        height,width=image.shape[:2];y0=round(height*.70)
        roi=image[y0:];hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
        gold=cv2.inRange(hsv,(12,65,45),(43,255,255))
        contours,_=cv2.findContours(gold,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);best=None
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour);y+=y0
            if not (width*.35<w<width*.8 and 2.7<w/h<5.2):continue
            if abs(x+w/2-width/2)>width*.10:continue
            # Normalize the located button before reading its text; resizing or
            # moving the window no longer requires a whole-screen scale sweep.
            crop=cv2.resize(gray[y:y+h,x:x+w],(392,110))
            scores=cv2.matchTemplate(crop[15:95,85:310],text,cv2.TM_CCOEFF_NORMED)
            _,score,_,_=cv2.minMaxLoc(scores)
            if score<.86:continue
            candidate=(score,(x+w/2,y+h/2),w)
            if best is None or score>best[0]:best=candidate
        self.last_features={'gold_frame':True,'bottom_center':True,'text_score':round(best[0],3),'width':best[2]} if best else None
        return best[1] if best else None
