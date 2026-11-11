"""Add learned visual navigation and a bounded scan memory to the current H4 action graph."""

import argparse, tempfile
from pathlib import Path
import onnx, torch
from onnx import compose, helper
from torch import nn
from torch.nn import functional as F
from panel import SearchVision


class PanelH4(nn.Module):
    def __init__(self, vision, prototype, chair=False):
        super().__init__()
        self.chair = chair
        self.vision = vision
        self.register_buffer("prototype", prototype)

    def forward(
        self,
        camera,
        rgb,
        goal_embedding,
        rgb_goal_proposals,
        previous_action,
        search_memory,
        parent_actions,
        prior_search_state=None,
    ):
        mask, v = self.vision(camera)
        bins = mask.sigmoid().amax(2)[:, 0]
        xs = torch.linspace(-1, 1, 40, device=camera.device)
        weights = bins.pow(5)
        offset = (weights * xs).sum(1) / weights.sum(1).clamp(min=0.001)
        box = rgb_goal_proposals[:, -1, :]
        detected = (box[:, 0] > 0.21) & ((v[:, 4] > -0.6) | (bins.amax(1) > 0.66))
        use_box = detected & (v[:, 4] < 2.0)
        offset = torch.where(use_box, box[:, 1] * 2 - 1, offset)
        seen = ((v[:, 4] > 2.0) & (bins.amax(1) > 0.63)) | detected
        if self.chair:
            # Background furnishings can trigger a generic chair proposal.
            seen = (v[:, 4] > 1.1) & (bins.amax(1) > 0.58)
            offset = torch.where(
                detected & (v[:, 4] > 2.0) & (v[:, 4] < 4.0), box[:, 1] * 2 - 1, offset
            )
        phase, clock, best, heading, remaining, age, bearing, avoid, stride = (
            search_memory.unbind(1)
        )
        turned = (previous_action[:, 2] - previous_action[:, 3]) * 0.2617994
        bearing = bearing - turned
        age = torch.where(seen, torch.zeros_like(age), age + 1)
        route = torch.atan2(v[:, 3], v[:, 2])
        # Blend an RGB-predicted local route with the image centroid when the
        # teacher-facing visual head predicts a substantial detour.
        aim = torch.where((route.abs() > 0.68) & (v[:, 4] > 2.0), route, -offset * 0.82)
        bearing = torch.where(seen, aim, bearing)
        pursuing = seen | ((age <= 10) & (phase == 3))
        prev_forward = previous_action[:, 1] > 0.5
        change = (rgb[:, -1].float() - rgb[:, -2].float()).abs().mean((1, 2, 3))
        stalled = prev_forward & (change < 0.6)
        avoid = torch.where(stalled, torch.full_like(avoid, 4), avoid)
        stride = torch.where(stalled, torch.full_like(stride, 5), stride)
        blocked = (avoid > 0) | (stride > 0)
        pursuing = pursuing & ~blocked
        # Scan one revolution, remembering the bearing most aligned with the learned
        # open route. Move along the selected heading before scanning the new view.
        restart = (
            (phase == 0)
            | ((phase == 2) & (remaining <= 0))
            | ((phase == 3) & ~pursuing)
        )
        phase = torch.where(restart, 1.0, phase)
        clock = torch.where(restart, torch.zeros_like(clock), clock)
        best = torch.where(restart, torch.full_like(best, -50), best)
        heading = torch.where(restart, torch.zeros_like(heading), heading)
        scanning = phase == 1
        opening = v[:, 0] - 0.35 * v[:, 1].abs()
        update = scanning & (opening > best)
        heading = torch.where(update, clock, heading)
        best = torch.where(update, opening, best)
        end_scan = scanning & (clock >= 23)
        # A positive incremental turn is left. After the 24th observation use the
        # shorter signed rotation back to the stored opening.
        delta = torch.remainder(heading - clock + 12.0, 24.0) - 12.0
        remaining = torch.where(end_scan, torch.full_like(remaining, 11), remaining)
        bearing = torch.where(end_scan & ~seen, delta * 0.2617994, bearing)
        orient = end_scan | (phase == 4)
        forward = orient & (bearing.abs() < 0.18)
        phase = torch.where(end_scan, 4.0, phase)
        phase = torch.where(forward, 2.0, phase)
        steer = torch.where(scanning, 1, 0)
        steer = torch.where(
            orient, torch.where(forward, 0, torch.where(bearing > 0, 1, 2)), steer
        )
        # Do not drop an observed object just because a subsequent turn clipped it.
        pursue = torch.where(bearing.abs() < 0.205, 0, torch.where(bearing > 0, 1, 2))
        steer = torch.where(pursuing, pursue, steer)
        phase = torch.where(pursuing, 3.0, phase)
        steer = torch.where(stride > 0, torch.zeros_like(steer), steer)
        steer = torch.where(avoid > 0, torch.full_like(steer, 2), steer)
        phase = torch.where(blocked, torch.where(age < 10, 3.0, 0.0), phase)
        next_memory = torch.stack(
            (
                phase,
                clock + scanning.float(),
                best,
                heading,
                remaining - ((phase == 2) & prev_forward).float(),
                age,
                bearing,
                (avoid - 1).clamp_min(0),
                (stride - (avoid <= 0).float()).clamp_min(0),
            ),
            1,
        )
        moves = F.one_hot(steer, 3).float() * 8 - 4
        # Preserve the existing learned STOP margin relative to the best movement.
        margin = parent_actions[:, 3:] - parent_actions[:, :3].amax(1, keepdim=True)
        support = (mask.sigmoid() > 0.5).float().sum((1, 2, 3))
        arrival = (v[:, 4] > 1.5) & (support > 60) & (offset.abs() < 0.6)
        stop = 4.0 + torch.where(arrival[:, None], margin, margin.clamp(max=-0.2))
        if self.chair:
            # Arrival is trained with paired removals and occlusion-aware STOP labels.
            foreground = (v[:, 4] > 1.1) & (support > 24) & (offset.abs() < 0.57)
            arrival_margin = torch.where(
                foreground, v[:, 5] - 0.4, torch.full_like(v[:, 5], -5.0)
            )
            # Four-frame H4 action scores influence ambiguous steering and arrival.
            # Mask evidence limits any STOP on an unsupported background view.
            prior = torch.tanh(
                (parent_actions[:, :3] - parent_actions[:, :3].mean(1, keepdim=True))
                / 3.0
            )
            steering = (
                torch.stack(
                    (0.205 - bearing.abs(), bearing - 0.205, -bearing - 0.205), 1
                )
                * 5.0
            )
            moves = torch.where(
                pursuing[:, None], steering.clamp(-5.0, 5.0) + 0.24 * prior, moves
            )
            stop = (
                moves.amax(1, keepdim=True)
                + arrival_margin[:, None]
                + 0.30 * torch.tanh(margin / 3.0)
            )
        scores = torch.cat([moves, stop], 1)
        active = F.cosine_similarity(goal_embedding, self.prototype) > 0.82
        if prior_search_state is not None:
            next_memory = torch.where(active[:, None], next_memory, prior_search_state)
        return torch.where(active[:, None], scores, parent_actions), next_memory


def export(model, parent_path, out):
    source = onnx.load(parent_path)
    args = (
        torch.zeros(1, 120, 160, 3, dtype=torch.uint8),
        torch.zeros(1, 4, 60, 80, 3, dtype=torch.uint8),
        torch.zeros(1, 512),
        torch.zeros(1, 4, 5),
        torch.zeros(1, 4),
        torch.zeros(1, 9),
        torch.zeros(1, 4),
    )
    names = [
        "camera",
        "rgb",
        "goal_embedding",
        "rgb_goal_proposals",
        "previous_action",
        "search_memory",
        "parent_actions",
    ]
    if model.chair:
        args += (torch.zeros(1, 9),)
        names.append("prior_search_state")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "movement.onnx"
        torch.onnx.export(
            model.eval(),
            args,
            str(path),
            input_names=names,
            output_names=["action_logits", "next_search_memory"],
            opset_version=17,
            dynamo=False,
        )
        addon = onnx.load(path)
    p = compose.add_prefix(source, "old/")
    a = compose.add_prefix(addon, "pursuit/")
    connections = [("old/action_logits", "pursuit/parent_actions")]
    shared = set(names[:5])
    if model.chair:
        connections.append(("old/next_search_memory", "pursuit/prior_search_state"))
        shared.add("search_memory")
    graph = compose.merge_graphs(p.graph, a.graph, connections)
    keep = [v for v in graph.input if v.name not in {"pursuit/" + s for s in shared}]
    del graph.input[:]
    graph.input.extend(keep)
    rename = {"old/" + v.name: v.name for v in source.graph.input}
    rename.update(
        {
            "pursuit/" + s: s
            for s in shared | {"action_logits", "search_memory", "next_search_memory"}
        }
    )
    rename["old/next_memory"] = "next_memory"
    for n in graph.node:
        for f in (n.input, n.output):
            for i, name in enumerate(f):
                f[i] = rename.get(name, name)
    for f in (graph.input, graph.output, graph.value_info):
        for v in f:
            v.name = rename.get(v.name, v.name)
    result = helper.make_model(
        graph, opset_imports=source.opset_import, ir_version=source.ir_version
    )
    onnx.checker.check_model(result)
    onnx.save(result, out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("weights", "parent", "prototypes", "out"):
        p.add_argument(k, type=Path)
    p.add_argument("--target", choices=["bin", "chair"], default="bin")
    a = p.parse_args()
    chair = a.target == "chair"
    net = SearchVision(outputs=6 if chair else 5)
    net.load_state_dict(torch.load(a.weights, map_location="cpu", weights_only=True))
    index = 0 if chair else 1
    proto = torch.load(a.prototypes, map_location="cpu", weights_only=True)[
        "prototypes"
    ][index : index + 1]
    export(PanelH4(net, proto, chair=chair), a.parent, a.out)
