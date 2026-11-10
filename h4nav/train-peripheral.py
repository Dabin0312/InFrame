"""Fit the acquisition head on independent instance-supervised Castle renders."""

import argparse, hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from torch.nn import functional as F
from model import GoalH4
from recovery import MotionMemory, RecoveryH4
from peripheral import PeripheralVision, PeripheralH4, BearingHead, TurnRecovery


def export(net, base_path, motion_path, dest, bearing_path):
    st = torch.load(base_path, map_location="cpu", weights_only=True)
    base = GoalH4(st["prototypes"])
    base.load_state_dict(st)
    motion = MotionMemory()
    motion.load_state_dict(torch.load(motion_path, weights_only=True, map_location="cpu"))
    bearing = BearingHead()
    bearing.load_state_dict(torch.load(bearing_path, weights_only=True, map_location="cpu"))
    turns = TurnRecovery()
    turns.load_state_dict(
        torch.load(bearing_path.with_name("turns.pt"), weights_only=True, map_location="cpu")
    )
    model = PeripheralH4(RecoveryH4(base, motion), net, bearing, turns).eval()
    inputs = (
        torch.zeros(1, 4, 60, 80, 3, dtype=torch.uint8),
        torch.ones(1, 512),
        torch.zeros(1, 4, 5),
        torch.tensor([[1.0, 0.0, 0.0, 0.0]]),
        torch.zeros(1, 1, motion.width + 4),
        torch.zeros(1, 120, 160, 3, dtype=torch.uint8),
    )
    torch.onnx.export(
        model,
        inputs,
        str(dest),
        input_names=[
            "rgb",
            "goal_embedding",
            "rgb_goal_proposals",
            "previous_action",
            "memory",
            "camera",
        ],
        output_names=["action_logits", "next_memory"],
        opset_version=17,
        dynamo=False,
    )


def main():
    p = argparse.ArgumentParser()
    for key in ["dataset", "base", "motion", "out"]:
        p.add_argument(key, type=Path)
    p.add_argument("--recovery-sequences", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=16)
    p.add_argument("--device", default="mps")
    a = p.parse_args()
    torch.manual_seed(876)
    torch.set_num_threads(3)
    rng = np.random.default_rng(876)
    dev = a.device
    dist = json.loads((a.dataset / "distances.json").read_text())
    n = len(dist)
    imgs = np.empty((n, 120, 160, 3), np.uint8)
    masks = np.empty((n, 60, 80), np.uint8)
    actions = []
    for i, dr in enumerate(dist):
        imgs[i] = np.asarray(Image.open(a.dataset / f"{i}.png").convert("RGB"))
        m = np.asarray(Image.open(a.dataset / f"{i}-mask.png").convert("L")) > 127
        yy, xx = np.nonzero(m)
        masks[i] = m.reshape(60, 2, 80, 2).max((1, 3))
        if len(xx) < 8:
            act = 0
        else:
            mid = (xx.min() + xx.max()) / 320
            act = 2 if mid < 0.405 else 3 if mid > 0.595 else 4 if dr <= 1.00 and len(xx) >= 80 else 1
        actions.append(act)
    order = np.random.default_rng(8795).permutation(n)
    val, train = order[: n // 8], order[n // 8 :]
    imgs = torch.from_numpy(imgs)
    masks = torch.from_numpy(masks)
    labels = torch.tensor(actions)
    net = PeripheralVision().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.0022)
    a.out.mkdir(exist_ok=True, parents=True)
    best = -1
    valid = []
    selected = 0
    for ep in range(a.epochs):
        net.train()
        if ep == int(0.7 * a.epochs):
            opt.param_groups[0]["lr"] = 0.00065
        for ids in np.array_split(rng.permutation(train), int(np.ceil(len(train) / 48))):
            x = imgs[ids].to(dev)
            y = masks[ids, None].float().to(dev)
            t = labels[ids].to(dev)
            if rng.random() < 0.5:
                x = x.flip([2])
                y = y.flip([3])
                t = torch.where(t == 2, 3, torch.where(t == 3, 2, t))
            scores, grid = net(x)
            prob = grid.sigmoid()
            diff = (prob.detach() - y).abs().pow(2) * F.binary_cross_entropy_with_logits(
                grid, y, reduction="none"
            )
            seg = (diff * y).sum() / y.sum().clamp(min=1) + 12 * (diff * (1 - y)).mean()
            loss = (
                F.cross_entropy(scores, t, weight=torch.tensor([1.0, 1.0, 1.0, 1.0, 2.0], device=dev))
                + seg * 1.4
            )
            opt.zero_grad()
            loss.backward()
            opt.step()
        net.eval()
        conf = np.zeros((5, 5), int)
        with torch.no_grad():
            for ids in np.array_split(val, 16):
                pred = net(imgs[ids].to(dev))[0].argmax(1).cpu().numpy()
                np.add.at(conf, (labels[ids].numpy(), pred), 1)
        recall = conf.diagonal() / np.maximum(conf.sum(1), 1)
        metric = recall.mean()
        print(ep + 1, recall.round(3), flush=True)
        if metric > best:
            best = metric
            selected = ep + 1
            valid = conf.tolist()
            torch.save(net.cpu().state_dict(), a.out / "vision.pt")
            net.to(dev)
    net.cpu().load_state_dict(torch.load(a.out / "vision.pt", weights_only=True))
    dest = a.out / "peripheral.onnx"
    import subprocess, sys

    subprocess.run(
        ["node", str(Path(__file__).with_name("training-poses.mjs")), str(a.dataset)], check=True
    )
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("train-bearing.py")),
            str(a.dataset),
            str(a.out / "vision.pt"),
            str(a.out),
            "--device",
            a.device,
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("train-turns.py")),
            str(a.recovery_sequences),
            str(a.out),
        ],
        check=True,
    )
    export(net, a.base, a.motion, dest, a.out / "bearing.pt")
    stats = dict(
        training_seed=541337,
        split_seed=8795,
        train=len(train),
        validation=len(val),
        epoch=selected,
        validation_confusion_defer_forward_left_right_stop=valid,
        bearing=json.loads((a.out / "bearing-fit.json").read_text()),
        turn_recovery=json.loads((a.out / "turn-fit.json").read_text()),
        model_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
    )
    (a.out / "peripheral-fit.json").write_text(json.dumps(stats, indent=2) + "\n")


if __name__ == "__main__":
    main()
