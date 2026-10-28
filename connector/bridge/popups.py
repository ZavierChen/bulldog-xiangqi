import os
from vision import cv2,np,HERE

class Popups:
    def __init__(self):
        from end_screens import EndScreens
        self.end_screens=EndScreens()
        folder=os.path.join(HERE,'ui_templates')
        self.title=cv2.imdecode(np.fromfile(os.path.join(folder,'upgrade-title.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
        self.confirm=cv2.imdecode(np.fromfile(os.path.join(folder,'upgrade-confirm.png'),np.uint8),cv2.IMREAD_GRAYSCALE)
    def upgrade(self,image):
        point=self.end_screens.upgrade(image)
        if point:return point
        reduction=min(1.,1280/image.shape[1],900/image.shape[0])
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        if reduction<1:gray=cv2.resize(gray,None,fx=reduction,fy=reduction)
        candidates=[]
        for scale in np.arange(.55,1.81,.025):
            w=round(194*scale);h=round(49*scale)
            if w>gray.shape[1] or h>gray.shape[0]:continue
            t=cv2.resize(self.title,(w,h));_,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(gray,t,cv2.TM_CCOEFF_NORMED))
            if score>.94:candidates.append((score,x,y,scale))
        for score,x,y,scale in sorted(candidates,reverse=True):
            ex=x-41*scale;ey=y+494*scale;cw=round(128*scale);ch=round(34*scale);pad=round(8*scale)
            left=max(0,round(ex-pad));top=max(0,round(ey-pad))
            roi=gray[top:min(gray.shape[0],round(ey+ch+pad)),left:min(gray.shape[1],round(ex+cw+pad))]
            if roi.shape[0]<ch or roi.shape[1]<cw:continue
            t=cv2.resize(self.confirm,(cw,ch));_,v,_,(cx,cy)=cv2.minMaxLoc(cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED))
            if v>.94:return ((left+cx+cw/2)/reduction,(top+cy+ch/2)/reduction)
        return None
