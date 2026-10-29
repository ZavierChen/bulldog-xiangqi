"""Detect the observed ad card's own close button, never its content button."""
import os
from vision import cv2,np,HERE

class Ads:
    def __init__(self):
        folder=os.path.join(HERE,'ui_templates')
        self.label=cv2.imdecode(np.fromfile(os.path.join(folder,'ad-label.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
        self.close=cv2.imdecode(np.fromfile(os.path.join(folder,'ad-close.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
        self.close_core=self.close[5:26,5:26] if self.close is not None else None
        self.last_features=None
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
        self.last_features=None
        if self.label is None or self.close is None:return None
        mask=cv2.inRange(image,(233,233,233),(255,255,255))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);height,width=gray.shape
        matches=[]
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour);scale=w/327
            if w<width*.2 or w>width*.9 or h<60*scale or not .4<scale<4:continue
            if abs(x+w/2-width/2)>width*.08:continue
            # Find the SDK's fixed label above either a footer or a full-white
            # card. Creative artwork and a changing translucent backdrop are
            # deliberately excluded from both identity and close matching.
            left=max(0,round(x-3*scale));top=max(0,round(y-420*scale))
            roi=gray[top:min(height,round(y+45*scale)),left:min(width,round(x+w*.3))]
            label=cv2.resize(self.label,(max(1,round(31*scale)),max(1,round(21*scale))))
            if roi.shape[0]<label.shape[0] or roi.shape[1]<label.shape[1]:continue
            _,score,_,(_,ly)=cv2.minMaxLoc(cv2.matchTemplate(roi,label,cv2.TM_CCOEFF_NORMED))
            anchor='sdk_label'
            marker_y=top+ly
            if score<.90:
                # Some SDK creatives print their label over changing artwork.
                # In that known layout the white action footer sits directly
                # below a 16:9 creative. Require the footer's centered green
                # action, then search only above that creative's top edge.
                if not .45<h/w<.85:continue
                hsv=cv2.cvtColor(image[y:y+h,x:x+w],cv2.COLOR_BGR2HSV)
                green=cv2.inRange(hsv,(40,120,90),(90,255,255))
                buttons,_=cv2.findContours(green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                if not any(w*.35<cv2.boundingRect(c)[2]<w*.85 and 2<cv2.boundingRect(c)[2]/max(1,cv2.boundingRect(c)[3])<8 for c in buttons):continue
                marker_y=y-w*9/16+9*scale;anchor='footer_16_9'
            left=max(0,round(x+w-70*scale));top=max(0,round(marker_y-75*scale))
            roi=gray[top:min(height,round(marker_y+3*scale)),left:min(width,round(x+w+20*scale))]
            # One-pixel resampling changes the small X substantially. Consider
            # neighboring sizes without lowering its similarity threshold.
            for delta in (-1,0,1):
                size=max(3,round(21*scale)+delta);close=cv2.resize(self.close_core,(size,size))
                if roi.shape[0]<size or roi.shape[1]<size:continue
                _,close_score,_,(cx,cy)=cv2.minMaxLoc(cv2.matchTemplate(roi,close,cv2.TM_CCOEFF_NORMED))
                px=left+cx+size/2;py=top+cy+size/2
                patch=roi[cy:cy+size,cx:cx+size]
                if (close_score>.94 and int(patch.max())-int(patch.min())>70
                    and x+w-45*scale<px<x+w+2*scale
                    and marker_y-65*scale<py<marker_y-8*scale):
                    matches.append((close_score,(px,py),{'anchor':anchor,'sdk_label_score':round(score,3),'close_core_score':round(close_score,3),'scale':round(scale,3)}))
        if not matches:return None
        best=max(matches,key=lambda p:p[0]);self.last_features=best[2]
        return best[1]
