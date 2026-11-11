"""Train three mask/visibility/range heads and a Castle visual pose encoder.
Inputs are the RGB corpora produced by the chair, panel and peripheral collectors.
"""

import argparse, json, math, random
from pathlib import Path
import cv2, numpy as np, torch
from torch.nn import functional as F
from escape import EscapeVision


def load_cameras(directories):
    rng = np.random.default_rng(311903)
    samples = []
    for k, d in enumerate(directories):
        fire = k == 2
        rows = json.loads((d / ("poses.json" if fire else "labels.json")).read_text())
        families = np.array(
            [i for i, r in enumerate(rows) if r is not None and "pairedWith" not in r]
        )
        order = rng.permutation(families)[:4200]
        split = {int(f): int(j < 480) for j, f in enumerate(order)}
        for i, r in enumerate(rows):
            if r is None or r.get("pairedWith", i) not in split:
                continue
            rgb = cv2.imread(str(d / (f"{i}.png" if fire else f"{i}-rgb.png")))[
                :, :, ::-1
            ].copy()
            m = cv2.imread(str(d / f"{i}-mask.png"), 0) > 127
            pose = r if fire else r["p"]
            x, z, yaw = [pose[key] for key in ("x", "z", "yaw")]
            ax, az = r["anchors"][k]
            distance = math.hypot(x - ax, z - az)
            samples.append(
                (
                    rgb,
                    m.reshape(30, 4, 40, 4).max((1, 3)),
                    k,
                    float(m.sum() >= 12),
                    math.log(max(0.35, distance)),
                    [(x - 2.0) / 6.0, (z - 14.0) / 8.0, math.sin(yaw), math.cos(yaw)],
                    split[r.get("pairedWith", i)],
                )
            )
    return [torch.from_numpy(np.asarray(v)) for v in zip(*samples)]


def main():
    p = argparse.ArgumentParser()
    for x in ["chair", "bin", "fire", "out"]:
        p.add_argument(x, type=Path)
    p.add_argument("--epochs", type=int, default=21)
    p.add_argument("--device", default="mps")
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    torch.manual_seed(221937)
    rng = np.random.default_rng(316002)
    torch.set_num_threads(3)
    x, m, k, vis, logd, pose, split = load_cameras([a.chair, a.bin, a.fire])
    train, val = [np.flatnonzero(split.numpy() == v) for v in (0, 1)]
    net = EscapeVision().to(a.device)
    optim = torch.optim.AdamW(net.parameters(), lr=0.0016)
    best = 1e6
    for ep in range(a.epochs):
        if ep in (11, 17):
            for g in optim.param_groups:
                g["lr"] *= 0.38
        for fitting, ids in ((True, rng.permutation(train)), (False, val)):
            net.train(fitting)
            stats = []
            with torch.set_grad_enabled(fitting):
                for batch in np.array_split(ids, math.ceil(len(ids) / 52)):
                    rgb, mask, idx, seen, dist, pos = [
                        t[batch].to(
                            a.device,
                            dtype=torch.float32 if t.is_floating_point() else t.dtype,
                        )
                        for t in (x, m, k, vis, logd, pose)
                    ]
                    # Supervise the annotated object channel only. Other objects can be present.
                    predicted, seg, confidence, ranges = net(rgb)
                    ix = torch.arange(len(batch), device=a.device)
                    seg = seg[ix, idx]
                    prob = seg.sigmoid()
                    mask = mask.float()
                    bce = (
                        F.binary_cross_entropy_with_logits(seg, mask, reduction="none")
                        * (prob.detach() - mask).square()
                    )
                    segmentation = (bce * mask).sum() / mask.sum().clamp_min(1) + 22 * (
                        bce * (1 - mask)
                    ).mean()
                    learn_range = (
                        (ranges[ix, idx] - dist).abs() * seen
                    ).sum() / seen.sum().clamp_min(1)
                    pose_loss = (predicted - pos).square().mean()
                    loss = (
                        segmentation
                        + 0.55
                        * F.binary_cross_entropy_with_logits(confidence[ix, idx], seen)
                        + 0.75 * learn_range
                        + 3.5 * pose_loss
                    )
                    if fitting:
                        optim.zero_grad()
                        loss.backward()
                        optim.step()
                    stats.append([loss.item(), pose_loss.item(), learn_range.item()])
            if not fitting:
                avg = np.mean(stats, axis=0)
                print(ep + 1, avg, flush=True)
                if avg[0] < best:
                    best = float(avg[0])
                    torch.save(net.state_dict(), a.out / "escape-vision.pt")
                    (a.out / "visual-fit.json").write_text(
                        json.dumps(
                            dict(
                                epoch=ep + 1,
                                train=len(train),
                                validation=len(val),
                                loss=best,
                                pose_mse=avg[1],
                                range_log_mae=avg[2],
                            ),
                            indent=2,
                        )
                    )


if __name__ == "__main__":
    main()
