"""Two grid intersections define all 90 squares in window-relative coordinates."""
import math
from vision import BoardBox,np,cv2


def content_rect(image):
    """Ignore side letterboxing; do not confuse a desktop-sized frame with play."""
    height,width=image.shape[:2]
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    active=(gray[round(height*.12):round(height*.88)]>20).mean(0)>.12
    runs=[];start=None
    for i,value in enumerate(np.r_[active,False]):
        if value and start is None:start=i
        elif not value and start is not None:runs.append((start,i));start=None
    if not runs:return 0,0,width,height
    left,right=max(runs,key=lambda run:run[1]-run[0])
    if right-left>width*.85:return 0,0,width,height
    if right-left<width*.15:return 0,0,width,height
    return left,0,right-left,height


def validate_corners(points):
    if len(points)!=2 or any(len(p)!=2 for p in points):raise ValueError('请选择两个棋盘交叉点')
    if any(not math.isfinite(float(v)) for p in points for v in p):raise ValueError('棋盘坐标无效')
    x1,x2=sorted(float(p[0]) for p in points);y1,y2=sorted(float(p[1]) for p in points)
    if not (0<=x1<x2<=1 and 0<=y1<y2<=1):raise ValueError('两个点必须位于窗口内并构成对角线')
    return x1,y1,x2,y2


def grid_box(calibration,shape,image=None):
    x1,y1,x2,y2=validate_corners(calibration['corners'])
    height,width=shape[:2]
    if calibration.get('content_corners') is not None and image is not None:
        x1,y1,x2,y2=validate_corners(calibration['content_corners'])
        left,top,width,height=content_rect(image)
    else:
        left=top=0
        reference=calibration.get('reference_size')
        if reference and abs((width/height)/(reference[0]/reference[1])-1)>.2:
            raise ValueError('窗口布局比例已改变，请重新选两点；原棋盘和计算仍保留')
    x=left+round(x1*width);y=top+round(y1*height)
    w=left+round(x2*width)-x;h=top+round(y2*height)-y
    if w<80 or h<90 or not .5<(w/8)/(h/9)<2:raise ValueError('棋盘范围不合理，请选择左上、右下交叉点')
    return BoardBox((x,y,w,h),'manual')


def center(box,row,col):
    x,y,w,h=box;return x+col*w/8,y+row*h/9
