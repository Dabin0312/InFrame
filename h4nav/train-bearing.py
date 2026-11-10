"""Distill local route and exploratory bearings from training-only floor geometry."""

import argparse, json, math
from pathlib import Path
import cv2
import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
import torch
from torch import nn
from torch.nn import functional as F
from peripheral import BearingHead, PeripheralVision


def teacher(samples, target_index=2):
    tris = json.loads((Path(__file__).parent.parent / "spatial/floor.json").read_text())["tris"]
    scale = 5
    points = np.asarray(tris)[:, :, [0, 2]]
    origin = points.min((0, 1)) - 1
    size = np.ceil((points.max((0, 1)) - origin + 1) * scale).astype(int)
    canvas = np.zeros(tuple((size[::-1] * 5).tolist()), np.uint8)
    for t in points:
        cv2.fillConvexPoly(canvas, np.rint((t - origin) * scale * 5).astype("int32"), 255)
    floor = canvas[::5, ::5]
    clearance = cv2.distanceTransform(floor, cv2.DIST_L2, 5) / scale
    zs, xs = np.where(clearance > 0.22)
    space = np.stack((xs, zs), 1) / scale + origin
    ids = np.full(floor.shape, -1, int)
    ids[zs, xs] = np.arange(len(xs))
    starts = []
    ends = []
    cost = []
    for dx, dz in [(0, 1), (1, 0), (1, 1), (1, -1)]:
        dest = ids[zs + dz, xs + dx]
        ok = (dest >= 0) & (ids[zs + dz, xs] >= 0) & (ids[zs, xs + dx] >= 0)
        starts.extend(ids[zs[ok], xs[ok]])
        ends.extend(dest[ok])
        cost.extend(math.hypot(dx, dz) * (1 + 0.3 / (0.2 + clearance[zs[ok], xs[ok]])))
    graph = sparse.coo_matrix((cost, (starts, ends)), shape=(len(xs), len(xs))).tocsr()
    tree = cKDTree(space)
    positions = np.array([[s["x"], s["z"]] for s in samples])
    targets = np.array([s["anchors"][target_index] for s in samples])
    start = tree.query(positions)[1]
    end = tree.query(targets)[1]
    # Two broad interior regions, obtained from floor extent and clearance, cover the long gallery.
    interior = space[clearance[zs, xs] > 1.25]
    mid = np.median(interior, axis=0)
    patrol = tree.query([[mid[0], np.quantile(interior[:, 1], q)] for q in (0.12, 0.88)])[1]
    explore = np.where(
        np.linalg.norm(positions - space[patrol[0]], axis=1)
        > np.linalg.norm(positions - space[patrol[1]], axis=1),
        patrol[0],
        patrol[1],
    )

    def direction(target_nodes, goals):
        _, pred = dijkstra(
            graph, directed=False, indices=np.unique(target_nodes), return_predecessors=True
        )
        lookup = {n: i for i, n in enumerate(np.unique(target_nodes))}
        out = []
        for k, (a, b) in enumerate(zip(start, target_nodes)):
            walk = a
            waypoint = goals[k]
            if a != b:
                for _ in range(14):
                    nxt = pred[lookup[b], walk]
                    if nxt < 0:
                        break
                    walk = nxt
                    if walk == b:
                        break
                    if np.linalg.norm(space[walk] - positions[k]) >= 1.45:
                        waypoint = space[walk]
                        break
            vec = waypoint - positions[k]
            angle = np.arctan2(-vec[0], -vec[1]) - samples[k]["yaw"]
            out.append([np.cos(angle), np.sin(angle)])
        return np.array(out, dtype="float32")

    return np.stack((direction(explore, space[explore]), direction(end, targets)), 1)


def main():
    p = argparse.ArgumentParser()
    for name in ["data", "vision", "out"]:
        p.add_argument(name, type=Path)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--device", default="mps")
    a = p.parse_args()
    torch.set_num_threads(3)
    torch.manual_seed(3439)
    rng = np.random.default_rng(321)
    dev = a.device
    samples = json.loads((a.data / "poses.json").read_text())
    y = torch.from_numpy(teacher(samples))
    mask = PeripheralVision().to(dev)
    mask.load_state_dict(torch.load(a.vision, weights_only=True, map_location=dev))
    mask.eval()
    inputs = []
    visible = []
    for ids in np.array_split(np.arange(len(samples)), 150):
        rgb = []
        vis = []
        for i in ids:
            rgb.append(cv2.cvtColor(cv2.imread(str(a.data / f"{i}.png")), cv2.COLOR_BGR2RGB))
            vis.append(cv2.countNonZero(cv2.imread(str(a.data / f"{i}-mask.png"), 0)) >= 8)
        with torch.no_grad():
            inputs.append(
                BearingHead.observation(torch.from_numpy(np.stack(rgb)).to(dev), mask.segment).cpu()
            )
        visible.extend(vis)
    data = torch.cat(inputs)
    visible = torch.tensor(visible)
    order = np.random.default_rng(8795).permutation(len(data))
    val, train = order[: len(order) // 8], order[len(order) // 8 :]
    net = BearingHead().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.0017)
    best = 10
    a.out.mkdir(parents=True, exist_ok=True)
    for ep in range(a.epochs):
        net.train()
        if ep == int(0.65 * a.epochs):
            opt.param_groups[0]["lr"] = 0.00055
        for ids in np.array_split(rng.permutation(train), int(np.ceil(len(train) / 64))):
            x = data[ids].to(dev)
            target = y[ids].to(dev)
            v = visible[ids].to(dev)
            if rng.random() < 0.5:
                x = x.flip([3])
                target = target * torch.tensor([1.0, -1.0], device=dev)
            b = net(x)
            loss = F.mse_loss(b[:, 0], target[:, 0]) + F.mse_loss(b[v, 1], target[v, 1])
            opt.zero_grad()
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            est = torch.cat([net(data[ids].to(dev)).cpu() for ids in np.array_split(val, 12)])
            angles = torch.rad2deg(torch.acos(F.cosine_similarity(est, y[val], dim=2).clamp(-1, 1)))
            scores = [angles[:, 0].median().item(), angles[visible[val], 1].median().item()]
            metric = sum(scores) / 100
            if metric < best:
                best = metric
                torch.save(net.state_dict(), a.out / "bearing.pt")
                (a.out / "bearing-fit.json").write_text(
                    json.dumps(
                        dict(
                            epoch=ep + 1,
                            median_angle_degrees=scores,
                            split_seed=8795,
                            train=len(train),
                            validation=len(val),
                        ),
                        indent=2,
                    )
                    + "\n"
                )
        print(ep + 1, scores, flush=True)


if __name__ == "__main__":
    main()
