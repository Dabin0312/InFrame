"""Fit bin arrival evidence on paired RGB renders and merge it into the deployed H4 graph."""

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnx
import torch
from onnx import compose, helper
from PIL import Image
from torch import nn
from torch.nn import functional as F


class BinEvidence(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 16, 5, 2, 2),
            nn.GroupNorm(4, 16),
            nn.SiLU(),
            nn.Conv2d(16, 24, 3, 2, 1),
            nn.GroupNorm(4, 24),
            nn.SiLU(),
            nn.Conv2d(24, 32, 3, padding=1),
            nn.GroupNorm(4, 32),
            nn.SiLU(),
            nn.Conv2d(32, 24, 3, padding=1),
            nn.GroupNorm(4, 24),
            nn.SiLU(),
        )
        self.mask = nn.Conv2d(24, 1, 1)
        self.head = nn.Sequential(nn.Linear(60, 64), nn.LayerNorm(64), nn.SiLU(), nn.Linear(64, 1))

    def forward(self, camera):
        x = camera.permute(0, 3, 1, 2).float() / 127.5 - 1
        z = self.mask(self.encoder(x))
        m = z.sigmoid()
        return (
            self.head(
                torch.cat(
                    (
                        F.max_pool2d(m, (6, 8)).flatten(1),
                        F.avg_pool2d(m, (6, 8)).flatten(1),
                        F.avg_pool1d(m.amax(2), 4).flatten(1),
                    ),
                    1,
                )
            ),
            z,
        )


class BinStop(nn.Module):
    def __init__(self, net, bin_text):
        super().__init__()
        self.visual = net
        self.register_buffer("bin_text", bin_text)

    def forward(self, camera, goal_embedding, parent_logits):
        visual, _ = self.visual(camera)
        cosine = F.cosine_similarity(goal_embedding, self.bin_text, dim=1)
        affinity = ((cosine - 0.82) / 0.18).clamp(0, 1)[:, None]
        # Both the four-frame arrival prior and foreground evidence contribute to STOP.
        # Limit the prior's margin when the camera resembles the removed member of a training pair.
        best_move = parent_logits[:, :3].amax(1, keepdim=True)
        original_margin = parent_logits[:, 3:] - best_move
        supported = torch.minimum(original_margin + 0.6 * F.relu(visual), 1.8 * visual)
        return parent_logits + F.pad(affinity * (supported - original_margin), (3, 0))


def export_h4(model, root, out):
    # Join only on public H4 inputs and action scores. No simulator state crosses this boundary.
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bin.onnx"
        torch.onnx.export(
            model.eval(),
            (torch.zeros(1, 120, 160, 3, dtype=torch.uint8), torch.zeros(1, 512), torch.zeros(1, 4)),
            str(path),
            input_names=["camera", "goal_embedding", "parent_actions"],
            output_names=["action_logits"],
            opset_version=17,
            dynamo=False,
        )
        source = onnx.load(root)
        extra = onnx.load(path)
    parent = compose.add_prefix(source, "h4/")
    addon = compose.add_prefix(extra, "bin/")
    wires = [("h4/action_logits", "bin/parent_actions")]
    graph = compose.merge_graphs(parent.graph, addon.graph, wires)
    rename = {"h4/" + v.name: v.name for v in source.graph.input}
    rename.update(
        {
            "bin/camera": "camera",
            "bin/goal_embedding": "goal_embedding",
            "bin/action_logits": "action_logits",
            "h4/next_memory": "next_memory",
        }
    )
    overlap = {"bin/camera", "bin/goal_embedding"}
    inputs = [v for v in graph.input if v.name not in overlap]
    del graph.input[:]
    graph.input.extend(inputs)
    for node in graph.node:
        for field in (node.input, node.output):
            for i, name in enumerate(field):
                field[i] = rename.get(name, name)
    for field in (graph.input, graph.output, graph.value_info):
        for value in field:
            value.name = rename.get(value.name, value.name)
    result = helper.make_model(graph, opset_imports=source.opset_import, ir_version=source.ir_version)
    onnx.checker.check_model(result)
    onnx.save(result, out)


def main():
    p = argparse.ArgumentParser()
    for name in ["data", "parent", "prototypes", "out"]:
        p.add_argument(name, type=Path)
    p.add_argument("--epochs", type=int, default=14)
    p.add_argument("--device", default="mps")
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    torch.manual_seed(71139)
    rng = np.random.default_rng(71139)
    torch.set_num_threads(3)
    labels = json.loads((a.data / "labels.json").read_text())
    n = len(labels)
    photos = np.empty((n, 2, 120, 160, 3), np.uint8)
    masks = np.zeros((n, 2, 30, 40), np.uint8)
    target = np.zeros((n, 2), np.float32)
    for i, row in enumerate(labels):
        for j, name in enumerate(["present", "absent"]):
            photos[i, j] = np.asarray(Image.open(a.data / f"{i}-{name}.png").convert("RGB"))
        m = np.asarray(Image.open(a.data / f"{i}-mask.png").convert("L")) > 127
        masks[i, 0] = m.reshape(30, 4, 40, 4).max((1, 3))
        b = row["box"]
        target[i, 0] = (
            row["pixels"] >= 80 and row["distance"] <= 1.35 and abs((b[0] + b[2]) / 320 - 0.5) <= 0.25
        )
    order = np.random.default_rng(6997).permutation(n)
    val, train = order[: n // 8], order[n // 8 :]
    photos = torch.from_numpy(photos)
    masks = torch.from_numpy(masks)
    y = torch.from_numpy(target)
    net = BinEvidence().to(a.device)
    opt = torch.optim.AdamW(net.parameters(), lr=0.0017)
    best = -float("inf")
    for ep in range(a.epochs):
        net.train()
        if ep == a.epochs * 2 // 3:
            opt.param_groups[0]["lr"] = 0.00055
        for ids in np.array_split(rng.permutation(train), int(np.ceil(len(train) / 24))):
            x = photos[ids].to(a.device).reshape(-1, 120, 160, 3)
            m = masks[ids].to(a.device).reshape(-1, 1, 30, 40).float()
            t = y[ids].flatten().to(a.device)
            if rng.random() < 0.5:
                x = x.flip([2])
                m = m.flip([3])
            # Apply the same photometric perturbation to the two images of a pair.
            x = (x.float() * float(rng.uniform(0.91, 1.09)) + float(rng.uniform(-7, 7))).clamp(0, 255)
            logit, z = net(x)
            v = logit.flatten()
            pred = z.sigmoid()
            seg = ((pred - m).abs().detach() ** 2) * F.binary_cross_entropy_with_logits(
                z, m, reduction="none"
            )
            mask_loss = (seg * m).sum() / m.sum().clamp(min=1) + 12 * (seg * (1 - m)).mean()
            paired = v.reshape(-1, 2)
            valid = t[::2]
            rank = (F.relu(2 - paired[:, 0] + paired[:, 1]) * valid).sum() / valid.sum().clamp(min=1)
            loss = (
                F.binary_cross_entropy_with_logits(v, t, pos_weight=torch.tensor(2.0, device=a.device))
                + mask_loss
                + 0.12 * rank
            )
            opt.zero_grad()
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            scores = torch.cat(
                [
                    net(photos[ids].reshape(-1, 120, 160, 3).to(a.device))[0].reshape(-1, 2).cpu()
                    for ids in np.array_split(val, 18)
                ]
            )
            truth = y[val].bool()
            dec = scores > 0
            tp = int((truth & dec).sum())
            fp = int((~truth & dec).sum())
            fn = int((truth & ~dec).sum())
            removed_fp = int(dec[:, 1].sum())
            metric = 2 * tp / max(1, 2 * tp + fp + fn) - removed_fp / len(val)
            if metric > best:
                best = metric
                stats = dict(
                    epoch=ep + 1,
                    train_pairs=len(train),
                    validation_pairs=len(val),
                    true_positive=tp,
                    false_positive=fp,
                    false_negative=fn,
                    removed_false_positive=removed_fp,
                )
                torch.save(net.state_dict(), a.out / "bin-evidence.pt")
        print(ep + 1, tp, fp, fn, removed_fp, flush=True)
    net.cpu().load_state_dict(
        torch.load(a.out / "bin-evidence.pt", map_location="cpu", weights_only=True)
    )
    st = torch.load(a.prototypes, map_location="cpu", weights_only=True)
    model = BinStop(net, st["prototypes"][1:2])
    model_path = a.out / "bin-h4.onnx"
    export_h4(model, a.parent, model_path)
    stats.update(
        sampling_seed=36980911,
        split_seed=6997,
        model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        parent_sha256=hashlib.sha256(a.parent.read_bytes()).hexdigest(),
    )
    (a.out / "bin-fit.json").write_text(json.dumps(stats, indent=2) + "\n")


if __name__ == "__main__":
    main()
