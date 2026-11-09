"""Photometric evidence of translation after removing commanded camera rotation."""
import math
import cv2
import numpy as np
W,H=80,60
F=W*.5/math.tan(math.radians(39))
Y,X=np.indices((H,W))
RAYS=np.stack(((X+.5-W/2)/F,-(Y+.5-H/2)/F,-np.ones((H,W))),axis=-1).astype('f4')
def pitch(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[1,0,0],[0,c,-s],[0,s,c]],np.float32)
P=pitch(-.20)
def translation_error(previous,current,angle):
    c,s=math.cos(angle),math.sin(angle)
    R=P.T@np.array([[c,0,s],[0,1,0],[-s,0,c]],np.float32)@P
    r=RAYS@R.T
    u=(W/2-.5)+F*r[:,:,0]/(-r[:,:,2])
    v=(H/2-.5)-F*r[:,:,1]/(-r[:,:,2])
    a=cv2.cvtColor(previous,cv2.COLOR_RGB2GRAY).astype('f4')
    b=cv2.cvtColor(current,cv2.COLOR_RGB2GRAY).astype('f4')
    ref=cv2.remap(a,u,v,cv2.INTER_LINEAR)
    valid=(u>2)&(u<W-3)&(v>2)&(v<H-3)&(Y>17)
    err=np.abs(cv2.GaussianBlur(ref,(3,3),.8)-cv2.GaussianBlur(b,(3,3),.8))
    return float(err[valid].mean())
