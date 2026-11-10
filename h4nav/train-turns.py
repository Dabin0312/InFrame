"""Imitate an advance out of alternating turns on independent recovery sequences."""

import sys, json
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from peripheral import TurnRecovery


def main():
    path, out = map(Path, sys.argv[1:])
    sequences = json.loads(path.read_text())
    torch.manual_seed(1517)
    torch.set_num_threads(2)
    d = []
    actions = []
    labels = []
    groups = []
    for i, seq in enumerate(sequences):
        rows = seq["rows"]
        for t, r in enumerate(rows):
            tail = [v["prev"] for v in rows[max(0, t - 2) : t + 1]]
            labels.append(float(tail in ([1, 2, 1], [2, 1, 2])))
            d.append([*r["diff"], rows[max(0, t - 1)]["diff"][1]])
            groups.append(i)
            actions.append(r["prev"] + 1)
    diff = torch.tensor(d)
    y = torch.tensor(labels)[:, None]
    ac = F.one_hot(torch.tensor(actions), 4).float()
    held = np.random.default_rng(218).permutation(len(sequences))[: len(sequences) // 8]
    train = torch.from_numpy(np.flatnonzero(~np.isin(groups, held)))
    val = np.flatnonzero(np.isin(groups, held))
    net = TurnRecovery()
    opt = torch.optim.AdamW(net.parameters(), lr=0.0035)
    best = -1
    for e in range(26):
        for ids in train[torch.randperm(len(train))].split(320):
            delta = (
                diff[ids] * (0.9 + 0.2 * torch.rand_like(diff[ids])) + 0.28 * torch.rand_like(diff[ids])
            ).clamp(min=0)
            pred = net(delta, ac[ids])
            loss = F.binary_cross_entropy(pred, y[ids], weight=1 + 7 * y[ids])
            opt.zero_grad()
            loss.backward()
            opt.step()
        with torch.no_grad():
            p = net(diff[val], ac[val]) > 0.78
            t = y[val].bool()
            tp = (p & t).sum().item()
            fp = (p & ~t).sum().item()
            fn = (~p & t).sum().item()
            f1 = 2 * tp / max(1, 2 * tp + fp + fn)
            if f1 > best:
                best = f1
                torch.save(net.state_dict(), out / "turns.pt")
                (out / "turn-fit.json").write_text(
                    json.dumps(
                        dict(
                            epochs_selected=e + 1,
                            train_sequences=len(sequences) - len(held),
                            validation_sequences=len(held),
                            true_positives=tp,
                            false_positives=fp,
                            false_negatives=fn,
                        ),
                        indent=2,
                    )
                    + "\n"
                )
    print((out / "turn-fit.json").read_text())


if __name__ == "__main__":
    main()
