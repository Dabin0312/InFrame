"""Distil exploration and pursuit bearings from Castle training cameras."""

import argparse, json, runpy
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from torch.nn import functional as F
from panel import SearchVision


def main():
    args = argparse.ArgumentParser()
    args.add_argument("data", type=Path)
    args.add_argument("out", type=Path)
    args.add_argument("--epochs", type=int, default=18)
    args.add_argument("--device", default="mps")
    a = args.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rows = json.loads((a.data / "labels.json").read_text())
    samples = [dict(**r["p"], anchors=r["anchors"]) for r in rows]
    teacher = runpy.run_path(str(Path(__file__).with_name("train-bearing.py")))["teacher"]
    vectors = torch.from_numpy(teacher(samples, target_index=1))
    imgs = torch.from_numpy(
        np.stack(
            [
                np.asarray(Image.open(a.data / f"{i}-rgb.png").convert("RGB"))
                for i in range(len(rows))
            ]
        )
    )
    masks = []
    for i in range(len(rows)):
        m = np.asarray(Image.open(a.data / f"{i}-mask.png").convert("L")) > 127
        masks.append(m.reshape(30, 4, 40, 4).max((1, 3)))
    masks = torch.from_numpy(np.stack(masks)).float().unsqueeze(1)
    visible = torch.tensor([r["pixels"] >= 14 for r in rows]).float()
    torch.manual_seed(81051)
    rng = np.random.default_rng(391146)
    order = rng.permutation(len(rows))
    val, train = np.split(order, [len(rows) // 8])
    net = SearchVision().to(a.device)
    opt = torch.optim.AdamW(net.parameters(), lr=0.0016)
    best = np.inf
    for ep in range(a.epochs):
        if ep == 10:
            opt.param_groups[0]["lr"] = 0.00055
        if ep == 15:
            opt.param_groups[0]["lr"] = 0.00025
        for training, ids in [(True, rng.permutation(train)), (False, val)]:
            net.train(training)
            metrics = []
            with torch.set_grad_enabled(training):
                for batch in np.array_split(ids, int(np.ceil(len(ids) / 36))):
                    x = imgs[batch].to(a.device)
                    m = masks[batch].to(a.device)
                    y = vectors[batch].to(a.device)
                    seen = visible[batch].to(a.device)
                    if training and rng.random() < 0.5:
                        x = x.flip([2])
                        m = m.flip([3])
                        y = y * torch.tensor([1.0, -1.0], device=a.device)
                    z, v = net(x)
                    prob = z.sigmoid()
                    focal = (
                        F.binary_cross_entropy_with_logits(z, m, reduction="none")
                        * (prob - m).abs().detach().square()
                    )
                    seg = (focal * m).sum() / m.sum().clamp(min=1) + 24 * (
                        focal * (1 - m)
                    ).mean()
                    explore = F.mse_loss(v[:, :2], y[:, 0])
                    pursue = (
                        (v[:, 2:4] - y[:, 1]).square().mean(1) * seen
                    ).sum() / seen.sum().clamp(min=1)
                    visibility = F.binary_cross_entropy_with_logits(v[:, 4], seen)
                    loss = seg + 1.2 * explore + pursue + 0.6 * visibility
                    if training:
                        opt.zero_grad()
                        loss.backward()
                        opt.step()
                    metrics.append(
                        [
                            float(loss.detach().cpu()),
                            float(explore.detach().cpu()),
                            float(pursue.detach().cpu()),
                        ]
                    )
            if not training:
                stat = np.mean(metrics, axis=0)
                print(ep + 1, stat, flush=True)
                if stat[0] < best:
                    best = float(stat[0])
                    torch.save(net.state_dict(), a.out / "search-vision.pt")
                    (a.out / "panel-fit.json").write_text(
                        json.dumps(
                            dict(
                                epoch=ep + 1,
                                train=len(train),
                                validation=len(val),
                                loss=best,
                                seed=872165,
                            ),
                            indent=2,
                        )
                        + "\n"
                    )


if __name__ == "__main__":
    main()
