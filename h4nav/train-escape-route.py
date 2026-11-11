"""Distill local detour directions using random pairs on the training floor."""

import argparse, json, math
from pathlib import Path
import cv2, numpy as np, torch
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from torch.nn import functional as F
from escape import Waypoint


def teachings(floor_file):
    rng = np.random.default_rng(335817)
    tri = np.array(json.loads(floor_file.read_text())["tris"])[:, :, [0, 2]]
    origin = tri.min((0, 1)) - 1
    scale = 5
    size = np.ceil((tri.max((0, 1)) + 1 - origin) * scale).astype(int)
    img = np.zeros(tuple(size[::-1] * 5), np.uint8)
    for t in tri:
        cv2.fillConvexPoly(img, np.rint((t - origin) * scale * 5).astype(np.int32), 255)
    free = img[::5, ::5]
    clear = cv2.distanceTransform(free, cv2.DIST_L2, 5) / scale
    z, x = np.where(clear > 0.21)
    pts = np.column_stack([x, z]) / scale + origin
    ids = np.full(free.shape, -1)
    ids[z, x] = np.arange(len(x))
    rows = []
    cols = []
    cost = []
    for dx, dz in [(0, 1), (1, 0), (1, 1), (1, -1)]:
        end = ids[z + dz, x + dx]
        ok = (end >= 0) & (ids[z + dz, x] >= 0) & (ids[z, x + dx] >= 0)
        rows.extend(ids[z[ok], x[ok]])
        cols.extend(end[ok])
        cost.extend(
            math.hypot(dx, dz)
            * (
                1
                + 0.34
                / (
                    0.05
                    + np.minimum(clear[z[ok], x[ok]], clear[z[ok] + dz, x[ok] + dx])
                )
            )
        )
    graph = sparse.coo_matrix((cost, (rows, cols)), shape=(len(x), len(x))).tocsr()
    examples = []
    for targets in np.array_split(rng.permutation(len(x)), 24):
        dist, pred = dijkstra(
            graph, directed=False, indices=targets, return_predecessors=True
        )
        for j, target in enumerate(targets):
            delta = pts[target] - pts
            length = np.linalg.norm(delta, axis=1)
            source = np.flatnonzero(
                (length > 0.65) & (length < 12) & np.isfinite(dist[j])
            )
            src = rng.choice(source, min(len(source), 110), replace=False)
            at = src.copy()
            for _ in range(13):
                moving = (np.linalg.norm(pts[at] - pts[src], axis=1) < 1.35) & (
                    at != target
                )
                at[moving] = pred[j, at[moving]]
            # The first waypoint is represented in a horizontal, room-aligned frame.
            direction = pts[at] - pts[src]
            direction /= np.linalg.norm(direction, axis=1, keepdims=True).clip(1e-5)
            examples.append(
                np.column_stack(
                    [(pts[src] - [2, 14]) / [6, 8], delta[src] / [6, 8], direction]
                )
            )
    return np.concatenate(examples).astype(np.float32)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--device", default="cpu")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    data = teachings(Path(__file__).parent.parent / "spatial/floor.json")
    rng = np.random.default_rng(95173)
    torch.manual_seed(42687)
    torch.set_num_threads(3)
    x = torch.from_numpy(data).to(a.device)
    ids = rng.permutation(len(x))
    val, train = np.split(ids, [len(ids) // 12])
    net = Waypoint().to(a.device)
    opt = torch.optim.AdamW(net.parameters(), lr=0.002)
    best = 10.0
    for epoch in range(22):
        if epoch in [12, 18]:
            for g in opt.param_groups:
                g["lr"] *= 0.4
        for fit, indices in [(True, rng.permutation(train)), (False, val)]:
            stats = []
            with torch.set_grad_enabled(fit):
                for batch in np.array_split(indices, math.ceil(len(indices) / 1024)):
                    v = x[batch]
                    out = net(v[:, :2], v[:, 2:4])
                    loss = (out - v[:, 4:]).square().mean()
                    if fit:
                        opt.zero_grad()
                        loss.backward()
                        opt.step()
                    stats.append(loss.item())
            if not fit:
                score = float(np.mean(stats))
                print(epoch + 1, score, flush=True)
                if score < best:
                    best = score
                    torch.save(net.state_dict(), a.out / "escape-route.pt")
                    (a.out / "route-fit.json").write_text(
                        json.dumps(
                            dict(
                                epoch=epoch + 1,
                                training_pairs=len(train),
                                validation_pairs=len(val),
                                direction_mse=score,
                            ),
                            indent=2,
                        )
                    )


if __name__ == "__main__":
    main()
