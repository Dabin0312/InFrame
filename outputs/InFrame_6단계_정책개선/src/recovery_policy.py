"""Four-RGB-frame student with an RGB-only local clearance and steering head."""
from collections import deque
import math
import numpy as np
import torch
from torch import nn
from common import S5
from policy import VisionPolicy,resize,commands,GOALS
from visual_motion import translation_error

OFFSETS=np.deg2rad([-90,-60,-45,-30,-15,0,15,30,45,60,90])
class CorrectionNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.vision=VisionPolicy().vision
        self.head=nn.Sequential(nn.Linear(128,128),nn.LayerNorm(128),nn.SiLU(),nn.Linear(128,14))
    def forward(self,images):
        x=images.float().permute(0,3,1,2)/127.5-1
        return self.head(self.vision(x.contiguous(memory_format=torch.channels_last)))

def steering(base,corr,config):
    v,omega,stop=commands(base)
    if stop:return v,omega,stop
    yaw=math.atan2(base[0],base[1])
    expert=math.atan2(corr[0],corr[1])
    ranges=.72/(1+np.exp(-np.clip(corr[3:],-18,18)))
    front=float(np.interp(omega*.125,OFFSETS,ranges))
    r=math.expm1(float(np.clip(base[2],0,4)))
    risk=float(np.clip((config['guard']+.20-front)/.30,0.,1.))
    # Preserve the demonstrator's learned final alignment close to the registered view.
    weight=(config['blend']+(.66-config['blend'])*risk)*float(np.clip((r-.5)/.65,0,1))
    vector=(1.-weight)*np.array([math.sin(yaw),math.cos(yaw)])+weight*np.array([math.sin(expert),math.cos(expert)])
    desired=math.atan2(vector[0],vector[1])
    # Angles near +pi and -pi both point behind the robot.
    # Use a single turn direction there to avoid alternating left/right over the branch cut.
    if abs(desired)>math.radians(config['behind']):
        return 0.,1.,0
    if front<config['guard'] and abs(desired)<math.radians(80):
        # For nearby boundaries, prefer the most goal-aligned direction with enough free travel.
        quality=np.cos(OFFSETS-desired)+1.65*np.minimum(ranges/.55,1.)
        choice=int(np.argmax(quality))
        if ranges[choice] < .23:
            return 0.,1.,0
        desired=float(OFFSETS[choice])
    omega=float(np.clip(1.8*desired,-1.,1.))
    if abs(desired)>=math.radians(48) or front<.10:
        if abs(omega)<.2:omega=1.
        return 0.,omega,0
    speed=float(np.clip(r/.25,.14,.4))*max(0.,math.cos(desired))
    return min(speed,max(.04,(front-.075)/.25)),omega,0

class DockNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.vision=VisionPolicy().vision
        self.head=nn.Sequential(nn.Linear(128,96),nn.LayerNorm(96),nn.SiLU(),nn.Linear(96,4))
    def forward(self,images):
        x=images.float().permute(0,3,1,2)/127.5-1
        return self.head(self.vision(x.contiguous(memory_format=torch.channels_last)))

class RecoveryStudent:
    def __init__(self,path):
        obj=torch.load(path,map_location='cpu',weights_only=True)
        self.base=VisionPolicy().eval()
        self.base.load_state_dict(obj['base'])
        self.correction=CorrectionNet().eval()
        self.correction.load_state_dict(obj['correction'])
        self.dock=DockNet().eval()
        self.dock.load_state_dict(obj['dock'])
        self.config=obj['config']
        self.frames=deque(maxlen=4);self.recent=deque(maxlen=3)
        self.reset()
    def reset(self):
        self.frames.clear();self.recent.clear()
        self.turn_left=0;self.progress_left=0;self.sign=1
    def decide(self,base,corr,dock,motion):
        proposal=steering(base,corr,self.config)
        if proposal[2]:return proposal
        # The terminal head is a visual estimate of valid range and target alignment.
        near,ready=dock[:2]
        if near>1. and ready>.9:
            return 0.,0.,1
        if near>1.2:
            yaw=math.atan2(dock[2],dock[3])
            if abs(yaw)>.20:
                if abs(yaw)>2.35:yaw=abs(yaw)
                return 0.,float(np.clip(1.8*yaw,-1,1)),0
        ranges=.72/(1+np.exp(-np.clip(corr[3:],-18,18)))
        # A repeated-view translation failure is detected solely with successive RGBs
        # and the policy's own command. The simulator's collision bit never enters the worker.
        blocked=bool(self.recent and self.recent[-1][0]>.14 and motion<1.6)
        angles=[a[1] for a in self.recent]+[proposal[1]]
        toggling=(len(angles)==4 and all(abs(a)>.60 for a in angles)
                  and all(a*b<0 for a,b in zip(angles,angles[1:]))
                  and all(a[0]<.03 for a in self.recent))
        if blocked or (toggling and not self.turn_left and not self.progress_left):
            # Favor the open side. If openings are comparable use the learned route bearing.
            left=float(ranges[8:].mean());right=float(ranges[:3].mean())
            if abs(left-right)>.10:self.sign=1 if left>right else -1
            else:self.sign=1 if corr[0]>=0 else -1
            self.turn_left=7 if blocked else 6
            self.progress_left=4 if blocked else 2
        if self.turn_left:
            self.turn_left-=1
            return 0.,float(self.sign),0
        if self.progress_left:
            self.progress_left-=1
            if ranges[5]>.24:return .28,0.,0
        return proposal
    @torch.inference_mode()
    def act(self,rgb,goal):
        im=resize(rgb)
        motion=100.
        if self.frames and self.recent and self.recent[-1][0]>.14:
            motion=translation_error(self.frames[-1],im,self.recent[-1][1]*.25)
        self.frames.append(im)
        while len(self.frames)<4:self.frames.appendleft(im)
        x=torch.from_numpy(np.stack(self.frames))[None]
        base=self.base(x,torch.tensor([GOALS[goal]]))[0].numpy()
        corr=self.correction(x[:,-1])[0].numpy()
        dock=self.dock(x[:,-1])[0].numpy()
        action=self.decide(base,corr,dock,motion)
        self.recent.append(action)
        return action
