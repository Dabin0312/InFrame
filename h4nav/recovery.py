"""H4 with a learned recurrent motion residual. All external observations are RGB and goal text."""
import torch
from torch import nn
from torch.nn import functional as F

class MotionMemory(nn.Module):
    width = 40
    def __init__(self):
        super().__init__()
        self.memory = nn.GRU(7, self.width, batch_first=True)
        self.head = nn.Linear(self.width, 4)

    def forward(self, previous_action, delta, state):
        # Smooth features retain sensitivity to weak changes without requiring identical pixels.
        motion = torch.exp(-delta.clamp(min=0) / 1.5)
        features = torch.cat((previous_action, motion), dim=-1)
        encoded, state = self.memory(features, state)
        return self.head(encoded), state

class RecoveryH4(nn.Module):
    def __init__(self, base, recovery):
        super().__init__()
        self.base = base
        self.recovery = recovery

    def forward(self, rgb, goal_embedding, rgb_goal_proposals, previous_action, memory):
        logits = self.base(rgb, goal_embedding, rgb_goal_proposals)
        images = rgb.float()
        delta = (images[:,-1:] - images[:,:3].flip([1])).abs().mean(dim=(2,3,4))
        motion, new_memory = self.recovery(previous_action[:,None], delta[:,None], memory)
        # Classes are keep, advance, left and right. A residual cannot increase STOP evidence.
        preference = motion[:,0,1:] - motion[:,0,:1]
        residual = F.pad(2.5*F.relu(preference), (0,1))
        return logits+residual, new_memory
