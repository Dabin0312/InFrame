"""Pure observation-to-action module. It has no simulator dependencies."""
from collections import deque
from pathlib import Path
import math
import numpy as np
from PIL import Image
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 80, 60
DT = 0.25
GOALS = {"소화기": 0}

def resize(rgb):
    return np.asarray(Image.fromarray(np.asarray(rgb)).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR))

class VisionPolicy(nn.Module):
    def __init__(self):
        super().__init__()
        layers = []
        widths = [3, 16, 24, 32, 48]
        for inc, out in zip(widths, widths[1:]):
            layers.extend([nn.Conv2d(inc, out, 3, stride=2, padding=1), nn.GroupNorm(4, out), nn.SiLU()])
        self.vision = nn.Sequential(*layers, nn.Flatten(), nn.Linear(48*4*5,128), nn.LayerNorm(128), nn.SiLU())
        self.goal = nn.Embedding(len(GOALS),8)
        self.history = nn.GRU(128,96,batch_first=True)
        self.head = nn.Sequential(nn.Linear(128+96+8,128), nn.LayerNorm(128), nn.SiLU(), nn.Linear(128,4))

    def forward(self, images, names):
        # N,T,H,W,C. Both policies use identical layers and have identical parameter counts.
        batch, length = images.shape[:2]
        x=images.reshape(-1,HEIGHT,WIDTH,3).permute(0,3,1,2).float()/127.5-1
        features = self.vision(x.contiguous(memory_format=torch.channels_last)).reshape(batch,length,128)
        history,_ = self.history(features)
        return self.head(torch.cat((features[:,-1],history[:,-1],self.goal(names)), dim=1))

def commands(pred):
    # Heads are supervised on ego-relative steering, remaining motion and STOP.
    sin_yaw, cos_yaw, log_range, stop_logit = [float(v) for v in pred]
    remaining = math.expm1(float(np.clip(log_range,0,4)))
    if stop_logit >= 0 and remaining <= .65:
        return (0.,0.,1)
    yaw = math.atan2(sin_yaw,cos_yaw)
    omega = float(np.clip(1.8*yaw,-1,1))
    if abs(yaw) >= math.radians(48):
        return (0.,omega,0)
    alignment = max(0.,math.cos(yaw))
    speed = float(np.clip(remaining/DT,.14,.4))*alignment
    return (speed,omega,0)

class Student:
    def __init__(self,checkpoint):
        saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
        self.model=VisionPolicy().eval()
        self.model.load_state_dict(saved['state'])
        self.frames=deque(maxlen=saved['history'])
    def reset(self):
        self.frames.clear()
    @torch.inference_mode()
    def act(self,rgb,goal):
        idx=GOALS[goal]
        frame=resize(rgb)
        self.frames.append(frame)
        while len(self.frames)<self.frames.maxlen:
            self.frames.appendleft(frame)
        x=torch.from_numpy(np.stack(self.frames))[None]
        pred=self.model(x,torch.tensor([idx]))[0].numpy()
        return commands(pred)
