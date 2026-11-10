"""Visual bearings used to leave wall-facing views and follow the requested bin."""

import torch
from torch import nn
from torch.nn import functional as F


class SearchVision(nn.Module):
    def __init__(self):
        super().__init__()

        def conv(a, b, stride):
            return nn.Sequential(
                nn.Conv2d(a, b, 3, stride, 1), nn.GroupNorm(4, b), nn.SiLU()
            )

        self.stem = nn.Sequential(conv(3, 16, 2), conv(16, 24, 2), conv(24, 24, 1))
        self.context = nn.Sequential(conv(24, 32, 2), conv(32, 40, 2))
        self.mask = nn.Sequential(conv(64, 24, 1), nn.Conv2d(24, 1, 1))
        self.bearings = nn.Sequential(
            nn.Linear(40 * 4 * 5 + 40, 128),
            nn.LayerNorm(128),
            nn.SiLU(),
            nn.Linear(128, 5),
        )

    def forward(self, camera):
        rgb = camera.permute(0, 3, 1, 2).float() / 127.5 - 1
        features = self.stem(rgb)
        context = self.context(features)
        mask = self.mask(
            torch.cat(
                [features, F.interpolate(context, size=(30, 40), mode="nearest")], 1
            )
        )
        peaks = mask.sigmoid().amax(2).flatten(1)
        pooled = F.avg_pool2d(context, (2, 2)).flatten(1)
        return mask, self.bearings(torch.cat([pooled, peaks], 1))
