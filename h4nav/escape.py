"""Visual subgoals and local path directions learned from Castle training views."""

import torch
from torch import nn
from torch.nn import functional as F


class EscapeVision(nn.Module):
    def __init__(self):
        super().__init__()

        def conv(a, b, s):
            return nn.Sequential(
                nn.Conv2d(a, b, 3, s, 1), nn.GroupNorm(4, b), nn.SiLU()
            )

        self.stem = nn.Sequential(conv(3, 16, 2), conv(16, 24, 2), conv(24, 24, 1))
        self.context = nn.Sequential(conv(24, 36, 2), conv(36, 48, 2))
        self.masks = nn.Sequential(conv(72, 32, 1), nn.Conv2d(32, 3, 1))
        self.scene = nn.Sequential(
            nn.Flatten(),
            nn.Linear(48 * 4 * 5, 192),
            nn.LayerNorm(192),
            nn.SiLU(),
            nn.Linear(192, 4),
        )
        self.objects = nn.Sequential(
            nn.Linear(48 * 4 * 5 + 3 * 40 + 3 * 30, 192),
            nn.LayerNorm(192),
            nn.SiLU(),
            nn.Linear(192, 6),
        )

    def forward(self, camera):
        feat = self.stem(camera.permute(0, 3, 1, 2).float() / 127.5 - 1)
        context = self.context(feat)
        mask = self.masks(
            torch.cat([feat, F.interpolate(context, size=(30, 40), mode="nearest")], 1)
        )
        views = mask.sigmoid()
        surroundings = F.avg_pool2d(context, 2).flatten(1)
        obj = self.objects(
            torch.cat(
                [surroundings, views.amax(2).flatten(1), views.amax(3).flatten(1)], 1
            )
        )
        return self.scene(surroundings), mask, obj[:, :3], obj[:, 3:]


class Waypoint(nn.Module):
    """Predict the first direction to a visually estimated relative destination."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(4 + 4 * 8, 144),
            nn.SiLU(),
            nn.Linear(144, 144),
            nn.SiLU(),
            nn.Linear(144, 96),
            nn.SiLU(),
            nn.Linear(96, 2),
        )

    def forward(self, start, displacement):
        v = torch.cat([start, displacement], 1)
        scales = torch.tensor([2.0, 4.0, 8.0, 16.0], device=v.device)
        angles = v.unsqueeze(2) * scales
        return self.net(
            torch.cat([v, angles.sin().flatten(1), angles.cos().flatten(1)], 1)
        )
