"""Compare piece bodies, not animated backgrounds or selection rings."""
from vision import cv2,np,move_pixels


def stable_pieces(first,second,board,box,flipped):
    if first.shape!=second.shape:return False
    step=min(box[2]/8,box[3]/9) if getattr(box,'profile','')=='manual' else min(box[2]/9,box[3]/10)
    radius=max(4,round(step*.22))
    for row in range(10):
        for col in range(9):
            if board[row][col]=='_':continue
            move=f'{chr(97+col)}{9-row}'*2;x,y=move_pixels(move,box,flipped)[0];x=round(x);y=round(y)
            left=max(0,x-radius);top=max(0,y-radius);right=min(first.shape[1],x+radius);bottom=min(first.shape[0],y+radius)
            a=first[top:bottom,left:right];b=second[top:bottom,left:right]
            if a.size==0 or b.size==0:return False
            a=cv2.GaussianBlur(cv2.cvtColor(a,cv2.COLOR_BGR2GRAY),(3,3),0).astype(np.float32)
            b=cv2.GaussianBlur(cv2.cvtColor(b,cv2.COLOR_BGR2GRAY),(3,3),0).astype(np.float32)
            a=(a-a.mean())/(a.std()+10);b=(b-b.mean())/(b.std()+10)
            if float(np.mean(np.abs(a-b)))>.32:return False
    return True
