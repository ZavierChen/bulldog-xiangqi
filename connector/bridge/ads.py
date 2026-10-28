"""Detect the observed ad card's own close button, never its content button."""
import os
from vision import cv2,np,HERE

class Ads:
    def __init__(self):
        folder=os.path.join(HERE,'ui_templates')
        self.label=cv2.imdecode(np.fromfile(os.path.join(folder,'ad-label.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
        self.close=cv2.imdecode(np.fromfile(os.path.join(folder,'ad-close.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
    def present(self,image):
        """Recognize the card footer even if its close control is not ready yet."""
        height,width=image.shape[:2]
        white=cv2.inRange(image,(233,233,233),(255,255,255))
        contours,_=cv2.findContours(white,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour)
            if not(width*.3<w<width*.7 and h>height*.08 and height*.25<y<height*.8):continue
            if abs(x+w/2-width/2)>width*.08:continue
            roi=hsv[y:y+h,x:x+w]
            green=cv2.inRange(roi,(40,120,90),(90,255,255))
            cs,_=cv2.findContours(green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            if any(w*.35<cv2.boundingRect(c)[2]<w*.85 and 2<cv2.boundingRect(c)[2]/max(1,cv2.boundingRect(c)[3])<8 for c in cs):return True
        return False
    def button(self,image):
        if self.label is None or self.close is None:return None
        mask=cv2.inRange(image,(233,233,233),(255,255,255))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);height,width=gray.shape
        matches=[]
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour);scale=w/327
            if w<width*.2 or w>width*.9 or h<60*scale or not .4<scale<4:continue
            # The white component may be only the footer: creative images above it
            # change on every impression. Locate the SDK close control relative to
            # the card width/right edge, independently of the creative pixels.
            left=max(0,round(x+w-70*scale));top=max(0,round(y-420*scale))
            roi=gray[top:min(height,round(y+5*scale)),left:min(width,round(x+w+20*scale))]
            close=cv2.resize(self.close,(max(1,round(31*scale)),max(1,round(31*scale))))
            if roi.shape[0]>=close.shape[0] and roi.shape[1]>=close.shape[1]:
                _,v,_,(cx,cy)=cv2.minMaxLoc(cv2.matchTemplate(roi,close,cv2.TM_CCOEFF_NORMED))
                px=left+cx+close.shape[1]/2;py=top+cy+close.shape[0]/2
                # A centered card footer plus the external circular X are two
                # independent anchors. Do not match a close icon inside an ad.
                if (v>.94 and abs(x+w/2-width/2)<width*.08
                    and x+w-45*scale<px<x+w+2*scale
                    and y-410*scale<py<y-8*scale):
                    matches.append((v,(px,py)))
            # Legacy full-white cards additionally expose the SDK label.
            left=max(0,round(x-3*scale));top=max(0,round(y-3*scale))
            roi=gray[top:min(height,round(y+45*scale)),left:min(width,round(x+w*.3))]
            label=cv2.resize(self.label,(max(1,round(31*scale)),max(1,round(21*scale))))
            if roi.shape[0]<label.shape[0] or roi.shape[1]<label.shape[1]:continue
            _,score,_,_=cv2.minMaxLoc(cv2.matchTemplate(roi,label,cv2.TM_CCOEFF_NORMED))
            if score<.90:continue
            # Its close control is outside the upper-right edge, not in the card.
            left=max(0,round(x+w-70*scale));top=max(0,round(y-65*scale))
            roi=gray[top:min(height,round(y+5*scale)),left:min(width,round(x+w+20*scale))]
            close=cv2.resize(self.close,(max(1,round(31*scale)),max(1,round(31*scale))))
            if roi.shape[0]<close.shape[0] or roi.shape[1]<close.shape[1]:continue
            _,score,_,(cx,cy)=cv2.minMaxLoc(cv2.matchTemplate(roi,close,cv2.TM_CCOEFF_NORMED))
            if score>.93:matches.append((score,(left+cx+close.shape[1]/2,top+cy+close.shape[0]/2)))
        return max(matches,key=lambda p:p[0])[1] if matches else None
