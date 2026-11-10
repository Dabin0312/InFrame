"""Text-conditioned four-frame H4. All motion classes, including STOP, come from one head."""
from pathlib import Path
import sys
import torch
from torch import nn
from torch.nn import functional as F
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/InFrame_5단계/src'))
from policy import VisionPolicy

class GoalH4(nn.Module):
    def __init__(self, prototypes, checkpoint=None):
        super().__init__()
        h4=VisionPolicy()
        if checkpoint:h4.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True)['state'])
        self.vision=h4.vision
        self.history=h4.history
        self.register_buffer('prototypes',F.normalize(prototypes,dim=-1))
        self.ground=nn.Sequential(nn.Conv2d(24+32+48,48,3,padding=1),nn.GroupNorm(4,48),nn.SiLU(),
                                  nn.Conv2d(48,32,3,padding=1),nn.GroupNorm(4,32),nn.SiLU(),nn.Conv2d(32,3,1))
        self.evidence=nn.Sequential(nn.Linear(5+20*15+3,128),nn.LayerNorm(128),nn.SiLU(),nn.Linear(128,128))
        self.search=nn.Sequential(nn.Linear(128,96),nn.LayerNorm(96),nn.SiLU(),nn.Linear(96,2))
        self.mix=nn.Linear(2,1)
        self.current=nn.Sequential(nn.Linear(5+20*15+3,96),nn.LayerNorm(96),nn.SiLU())
        self.action=nn.Sequential(nn.Linear(96+96,96),nn.LayerNorm(96),nn.SiLU(),nn.Linear(96,4))
    def encode(self,rgb):
        b,t=rgb.shape[:2];x=rgb.reshape(-1,60,80,3).permute(0,3,1,2).float()/127.5-1
        f1=self.vision[:6](x);f2=self.vision[6:9](f1);f3=self.vision[9:12](f2)
        features=self.vision[12:](f3).reshape(b,t,128)
        grid=self.ground(torch.cat([f1,F.interpolate(f2,size=(15,20),mode='nearest'),F.interpolate(f3,size=(15,20),mode='nearest')],1))
        return features,grid.reshape(b,t,3,15,20)
    def decision(self,features,grid,goal,observations):
        cosine=F.normalize(goal,dim=-1)@self.prototypes.T
        weights=torch.sigmoid(20*(cosine-.63))
        attention=(torch.sigmoid(grid)*weights[:,None,:,None,None]).amax(2).flatten(2)
        t=features.shape[1]
        evidence=torch.cat((attention,observations,weights[:,None].expand(-1,t,-1)),dim=-1)
        seq,_=self.history(.20*features+self.evidence(evidence))
        navigate=self.action(torch.cat((seq,self.current(evidence)),dim=-1))
        explore=self.search(features)
        explore=F.pad(explore,(0,2),value=-7.)
        strength=torch.stack((attention.amax(-1),observations[...,0]),dim=-1)
        # A learned confidence gate combines visually acquired and unseen-target actions inside H4.
        mix=torch.sigmoid(self.mix(strength)+8*(strength.amax(-1,keepdim=True)-.38))
        return mix*navigate+(1-mix)*explore
    def forward(self,rgb,goal,observations):
        features,grid=self.encode(rgb)
        return self.decision(features,grid,goal,observations)[:,-1]
