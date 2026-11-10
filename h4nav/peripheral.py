"""Goal-conditioned peripheral acquisition inside H4's action graph."""

import torch
from torch import nn
from torch.nn import functional as F


class PeripheralVision(nn.Module):
    def __init__(self):
        super().__init__()
        self.segment = nn.Sequential(
            nn.Conv2d(3, 12, 3, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(12, 16, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(16, 12, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(12, 1, 1),
        )
        self.steer = nn.Sequential(
            nn.Linear(20 * 4 + 6, 80), nn.LayerNorm(80), nn.SiLU(), nn.Linear(80, 5)
        )

    def forward(self, camera):
        x = camera.permute(0, 3, 1, 2).float() / 127.5 - 1
        mask = self.segment(x)
        score = mask.sigmoid()
        # Sector occupancy and evidence peaks preserve small targets on both sides of the frame.
        width = score.amax(2)
        vertical = score.amax(3)
        peaks = F.max_pool1d(width, 4).flatten(1)
        avg = F.avg_pool1d(score.mean(2), 4).flatten(1)
        vp = F.max_pool1d(vertical, 10).flatten(1)
        columns = F.avg_pool1d(width, 4).flatten(1)
        softmass = F.avg_pool1d((score**3).mean(2), 4).flatten(1)
        return self.steer(torch.cat((peaks, avg, columns, softmass, vp), 1)), mask


class PeripheralH4(nn.Module):
    def __init__(self, parent, vision, bearing, turn_recovery):
        super().__init__()
        self.parent = parent
        self.vision = vision
        self.bearing = bearing
        self.turn_recovery = turn_recovery

    def forward(self, rgb, goal_embedding, rgb_goal_proposals, previous_action, memory, camera):
        old, state = self.parent(
            rgb, goal_embedding, rgb_goal_proposals, previous_action, memory[:, :, :40]
        )
        expert, mask = self.vision(camera)
        cosine = F.cosine_similarity(goal_embedding, self.parent.base.prototypes[2:3], dim=1)
        affinity = ((cosine - 0.82) / 0.18).clamp(0, 1).unsqueeze(-1)
        margin = expert[:, 1:].amax(1, keepdim=True) - expert[:, :1]
        weight = ((margin - 0.4) / 2).clamp(0, 1)
        x = camera.permute(0, 3, 1, 2).float() / 127.5 - 1
        geom = torch.cat((F.avg_pool2d(x, 4), F.max_pool2d(mask.sigmoid(), 2)), 1)
        headings = self.bearing(geom)
        heading = headings[:, 0] * (1 - weight) + headings[:, 1] * weight
        fwd, left = heading.unbind(1)
        moving = 8 * torch.stack((0.30 * fwd, left, -left), 1)
        # STOP remains a visually learned action. Route evidence supplies movement only.
        close = (expert[:, 4] - expert[:, 1:4].amax(1)).unsqueeze(1)
        stopping = moving.amax(1, keepdim=True) + close + 10 * (weight - 1)
        # Keep the four-frame H4 action prior, including its GRU. Saturating
        # logits prevent a large recovery score from overwhelming fresh RGB.
        context = 0.5 * torch.tanh(old / 6)
        scores = (1 - affinity) * old + affinity * (context + torch.cat((moving, stopping), 1))
        # Measure a failed commanded advance in two RGB observations. The bypass
        # carries across steps so reacquiring the object cannot cancel it inside an obstacle.
        stalled = (rgb[:, -1].float() - rgb[:, -2].float()).abs().mean((1, 2, 3)) < 0.5
        # Follow the boundary using only actions and image change. A right-hand
        # escape tries a new heading after a stalled step and turns back gradually
        # after free advances. Signed accumulated turns allow a return to pursuit.
        turns, count, pending, recent = memory[0, :, 40:].unbind(1)
        begin = (turns == 0) & stalled & (previous_action[:, 1] > 0.5) & (recent > 0)
        following = turns > 0
        forwarded = previous_action[:, 1] > 0.5
        blocked = following & forwarded & stalled
        free = following & forwarded & (~stalled)
        count = torch.where(free, count + 1, count)
        pending = torch.where(begin, torch.full_like(turns, 5), pending)
        pending = torch.where(blocked, torch.full_like(turns, 2), pending)
        turn_right = pending > 0
        turn_left = following & (count >= 2) & (~turn_right)
        proceed = following & (~turn_left) & (~turn_right)
        bypass = torch.stack((proceed, turn_left, turn_right, torch.zeros_like(turn_right)), 1).float()
        active = (following | begin).float().unsqueeze(1) * affinity
        scores = (1 - active) * scores + active * (bypass * 20 + context)
        images = rgb.float()
        diffs = (images[:, -1:] - images[:, :3].flip([1])).abs().mean((2, 3, 4))
        previous_pair = (images[:, -2] - images[:, 0]).abs().mean((1, 2, 3)).unsqueeze(1)
        alternating = self.turn_recovery(torch.cat((diffs, previous_pair), 1), previous_action)
        confidence = ((alternating - 0.78) / 0.19).clamp(0, 1) * affinity * (1 - active)
        wants_turn = (
            scores[:, 1:3].amax(1, keepdim=True) > torch.maximum(scores[:, :1], scores[:, 3:4])
        ).float()
        # Repeated opposite turns hand movement back to the learned four-frame
        # recovery head long enough to leave the two alternating camera views.
        handoff = (confidence[:, 0] > 0.72) & (wants_turn[:, 0] > 0.5)
        recovering = (turns < 0) | handoff
        scores = torch.where(recovering.unsqueeze(1), old, scores)
        recovery_clock = torch.where(handoff & (turns >= 0), torch.full_like(turns, -12), turns + 1)
        turns = torch.where(
            recovering, recovery_clock, (turns + turn_right.float() - turn_left.float()).clamp(0, 30)
        )
        count = torch.where(turn_left | turn_right, torch.zeros_like(count), count)
        pending = (pending - 1).clamp(min=0)
        recent = torch.where(
            (weight[:, 0] * affinity[:, 0]) > 0.6, torch.full_like(turns, 3), (recent - 1).clamp(min=0)
        )
        return scores, torch.cat(
            (state, torch.stack((turns, count, pending, recent), 1).unsqueeze(0)), 2
        )


class BearingHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(4, 16, 5, 2, 2),
            nn.SiLU(),
            nn.Conv2d(16, 32, 3, 2, 1),
            nn.SiLU(),
            nn.Conv2d(32, 48, 3, 2, 1),
            nn.SiLU(),
            nn.Flatten(),
            nn.Linear(48 * 5 * 4, 128),
            nn.LayerNorm(128),
            nn.SiLU(),
            nn.Linear(128, 4),
        )

    @staticmethod
    def observation(camera, segment):
        x = camera.permute(0, 3, 1, 2).float() / 127.5 - 1
        return torch.cat((F.avg_pool2d(x, 4), F.max_pool2d(segment(x).sigmoid(), 2)), 1)

    def forward(self, x):
        return self.cnn(x).reshape(-1, 2, 2)


class TurnRecovery(nn.Module):
    """Detect a repeated pair of views from four frames and the last command."""

    def __init__(self):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(12, 24), nn.SiLU(), nn.Linear(24, 1))

    def forward(self, delta, previous):
        features = torch.cat((torch.exp(-delta / 2.5), torch.log1p(delta) / 4, previous), dim=-1)
        return self.fc(features).sigmoid()
