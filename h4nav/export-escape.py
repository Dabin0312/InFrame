"""Compose a shared, RGB-conditioned detour into the goal-conditioned H4 graph."""

import argparse, tempfile
from pathlib import Path
import onnx, torch
from onnx import compose, helper
from torch import nn
from torch.nn import functional as F
from escape import EscapeVision, Waypoint


class EscapeH4(nn.Module):
    def __init__(self, vision, route, prototypes):
        super().__init__()
        self.vision = vision
        self.route = route
        self.register_buffer("goals", F.normalize(prototypes))

    def forward(
        self,
        camera,
        rgb,
        goal_embedding,
        previous_action,
        escape_memory,
        parent_actions,
        bin_features,
    ):
        (
            x,
            z,
            s,
            c,
            fwd,
            left,
            age,
            known,
            avoid,
            side,
            init,
            stalls,
            quiet,
            normal,
            phase,
            remaining,
            clearance,
            passing,
            trail_f,
            trail_l,
        ) = escape_memory.unbind(1)
        scene, masks, visibility, ranges = self.vision(camera)
        cosine = F.normalize(goal_embedding) @ self.goals.T
        relevant = cosine.amax(1) > 0.82
        choose = F.one_hot(cosine.argmax(1), 3).float()
        prob = (masks.sigmoid() * choose[:, :, None, None]).sum(1)
        peaks = prob.amax(1)
        xs = torch.linspace(-1.0, 1.0, 40, device=camera.device)
        weights = peaks.pow(4)
        u = (weights * xs).sum(1) / weights.sum(1).clamp_min(1e-5)
        dist = (ranges * choose).sum(1).clamp(-1, 2.6).exp()
        conf = (visibility * choose).sum(1)
        seen = (conf > 1.0) & (peaks.amax(1) > 0.64)
        is_bin = choose[:, 1] > 0.5
        bin_support = bin_features[:, 4] > 0.3
        seen = seen & (~is_bin | bin_support)
        pixels = (prob > 0.49).float().sum((1, 2))
        turn = (previous_action[:, 2] - previous_action[:, 3]) * 0.2617994
        st, ct = turn.sin(), turn.cos()
        moved = previous_action[:, 1] > 0.5
        stalled = moved & (
            (rgb[:, -1].float() - rgb[:, -2].float()).abs().mean((1, 2, 3)) < 0.6
        )
        progress = (moved & ~stalled).float() * 0.22
        # Integrate the last action. Correct the scene orientation/position using RGB.
        sf, cf = s * ct + c * st, c * ct - s * st
        orientation = F.normalize(
            torch.stack([sf, cf], 1) * 0.87
            + F.normalize(scene[:, 2:], dim=1)
            * torch.where(init > 0, 0.13, 1.0)[:, None],
            dim=1,
        )
        s, c = orientation.unbind(1)
        x = torch.where(
            init > 0,
            (x - progress * s) * 0.86 + 0.14 * (scene[:, 0] * 6 + 2),
            scene[:, 0] * 6 + 2,
        )
        z = torch.where(
            init > 0,
            (z - progress * c) * 0.86 + 0.14 * (scene[:, 1] * 8 + 14),
            scene[:, 1] * 8 + 14,
        )
        # This vector is relative to the robot. It originates in a camera observation,
        # and can survive turns where the object vanishes behind a corner.
        backed = fwd - progress
        fwd, left = backed * ct + left * st, left * ct - backed * st
        ang = torch.atan(-u * 0.80978)
        alpha = torch.where((known > 0) & (age < 9), 0.68, 1.0)
        fwd = torch.where(seen, (1 - alpha) * fwd + alpha * dist * ang.cos(), fwd)
        left = torch.where(seen, (1 - alpha) * left + alpha * dist * ang.sin(), left)
        age = torch.where(seen, 0.0, age + 1)
        known = torch.where(seen, 1.0, known)
        direct = torch.atan2(left, fwd)
        estimated_range = torch.sqrt(fwd.square() + left.square())
        dx, dz = -fwd * s - left * c, -fwd * c + left * s
        route = self.route(
            torch.stack([(x - 2) / 6, (z - 14) / 8], 1),
            torch.stack([dx / 6, dz / 8], 1),
        )
        rx, rz = route.unbind(1)
        detour = torch.atan2(-rx * c + rz * s, -rx * s - rz * c)
        angle = torch.where(estimated_range < 1.85, direct, detour)
        tracking = (known > 0) & (age < 48) & ((estimated_range > 0.60) | seen)
        # Hold one passing side until a few forward steps have cleared the boundary.
        # Only the difference between consecutive RGB frames signals a stalled step.
        stalls = torch.where(
            stalled,
            torch.clamp(stalls + 1, max=8.0),
            (stalls - 0.09 * progress / 0.22).clamp_min(0),
        )
        new_side = torch.where(detour >= 0, 1.0, -1.0)
        side = torch.where(stalled & ((avoid <= 0) | (stalls < 1.1)), new_side, side)
        avoid = torch.where(stalled, 8.0, (avoid - 1.0).clamp_min(0))
        avoid_turn = avoid > 4
        steering = torch.where(angle.abs() < 0.19, 0, torch.where(angle > 0, 1, 2))
        recovery = torch.where(avoid_turn, torch.where(side > 0, 1, 2), 0)
        quiet = torch.where(tracking, torch.zeros_like(quiet), quiet + 1)
        # Take a sweep before committing to an unexplored heading. The parent
        # resumes movement between sweeps if no visual evidence is acquired.
        scan = (~tracking) & (torch.remainder(quiet - 1, 52) < 24)
        steering = torch.where(scan, torch.ones_like(steering), steering)
        steering = torch.where(avoid > 0, recovery, steering)
        # Follow one side across consecutive turns rather than reacquiring the
        # same obstructed heading. Progress counts completed forward actions.
        normal = torch.atan2((normal - turn).sin(), (normal - turn).cos())
        intended = torch.where(phase == 1, normal + passing * clearance, normal)
        unexpected = torch.atan2(intended.sin(), intended.cos()).abs() > 0.66
        trail_f, trail_l = (
            0.975 * (trail_f * ct + trail_l * st) + progress,
            0.975 * (trail_l * ct - trail_f * st),
        )
        # Successful lateral travel tells us which way we were already clearing
        # the obstruction when visual estimates from two views disagree.
        preferred = torch.where(
            trail_l.abs() > 0.38, torch.where(trail_l > 0, 1.0, -1.0), new_side
        )
        begin = (
            stalled
            & tracking
            & (choose[:, 0] > 0.5)
            & ((phase <= 0) | (phase == 3) | unexpected)
        )
        side_step = (phase == 1) & stalled & ~begin
        retry_corner = (phase == 2) & stalled & ~begin
        remaining = remaining - ((phase > 0) & (progress > 0)).float()
        finish_side = (phase == 1) & (remaining <= 0)
        finish_pass = (phase == 2) & (remaining <= 0)
        finish_aim = (phase == 3) & ((remaining <= 0) | (age > 24))
        phase = torch.where(finish_aim, 0.0, phase)
        phase = torch.where(finish_pass, 3.0, phase)
        phase = torch.where(finish_side, 2.0, phase)
        phase = torch.where(begin | retry_corner, 1.0, phase)
        normal = torch.where(begin, 0.0, normal)
        passing = torch.where(begin, preferred, passing)
        clearance = torch.where(begin | retry_corner, 1.8325957, clearance)
        # Move away from the edge first, then curve around its near corner.
        near_corner = (phase == 1) & (remaining == 5) & (progress > 0) & ~begin
        clearance = torch.where(near_corner, 1.308997, clearance)
        clearance = torch.where(
            side_step, (clearance + 0.2617994).clamp(max=3.14159), clearance
        )
        reverse_probe = side_step & (clearance >= 3.13)
        passing = torch.where(reverse_probe, -passing, passing)
        clearance = torch.where(reverse_probe, 1.83, clearance)
        remaining = torch.where(finish_side, 10.0, remaining)
        remaining = torch.where(finish_pass, 12.0, remaining)
        remaining = torch.where(begin, 8.0, torch.where(retry_corner, 4.0, remaining))
        edge_angle = torch.where(
            phase == 1,
            normal + passing * clearance,
            torch.where(phase == 2, normal, direct),
        )
        edge_angle = torch.atan2(edge_angle.sin(), edge_angle.cos())
        edge_action = torch.where(
            edge_angle.abs() < 0.18, 0, torch.where(edge_angle > 0, 1, 2)
        )
        steering = torch.where(phase > 0, edge_action, steering)
        motion = F.one_hot(steering, 3).float() * 7 - 3.0
        active = relevant & (tracking | (avoid > 0) | scan | (phase > 0))
        moves = torch.where(active[:, None], motion, parent_actions[:, :3])
        margin = parent_actions[:, 3] - parent_actions[:, :3].amax(1)
        supported = seen & (pixels >= 8) & (u.abs() < 0.51)
        learned_stop = supported & (dist < 1.11) & (pixels >= 18) & ~is_bin
        # A close, centered visual confirmation can also complete a detour.
        # Earlier H4's STOP is retained when both visual branches support it.
        consent = supported | ((conf > -0.5) & (pixels >= 10) & (u.abs() < 0.52))
        stop_margin = torch.where(
            learned_stop,
            1.0,
            torch.where(consent | is_bin, margin, margin.clamp(max=-0.2)),
        )
        stop = torch.where(relevant, moves.amax(1) + stop_margin, parent_actions[:, 3])
        next_state = torch.stack(
            [
                x,
                z,
                s,
                c,
                fwd,
                left,
                age,
                known,
                avoid,
                side,
                torch.ones_like(init),
                stalls,
                quiet,
                normal,
                phase,
                remaining,
                clearance,
                passing,
                trail_f,
                trail_l,
            ],
            1,
        )
        return torch.cat([moves, stop[:, None]], 1), next_state


def export(parent, weights, prototypes, out):
    v = EscapeVision()
    v.load_state_dict(
        torch.load(weights / "escape-vision.pt", weights_only=True, map_location="cpu")
    )
    w = Waypoint()
    w.load_state_dict(
        torch.load(weights / "escape-route.pt", weights_only=True, map_location="cpu")
    )
    prot = torch.load(prototypes, weights_only=True, map_location="cpu")["prototypes"][
        :3
    ]
    net = EscapeH4(v, w, prot).eval()
    names = [
        "camera",
        "rgb",
        "goal_embedding",
        "previous_action",
        "escape_memory",
        "parent_actions",
        "bin_features",
    ]
    args = (
        torch.zeros((1, 120, 160, 3), dtype=torch.uint8),
        torch.zeros((1, 4, 60, 80, 3), dtype=torch.uint8),
        torch.zeros(1, 512),
        torch.zeros(1, 4),
        torch.zeros(1, 20),
        torch.zeros(1, 4),
        torch.zeros(1, 5),
    )
    orig = onnx.load(parent)
    with tempfile.TemporaryDirectory() as d:
        file = Path(d) / "escape.onnx"
        torch.onnx.export(
            net,
            args,
            str(file),
            input_names=names,
            output_names=["action_logits", "next_escape_memory"],
            opset_version=17,
            dynamo=False,
        )
        head = compose.add_prefix(onnx.load(file), "escape/")
    # Reuse the bin visibility already computed in the frozen parent graph.
    bin_output = "old/pursuit//vision/bearings/bearings.3/Gemm_output_0"
    assert any(bin_output in n.output for n in orig.graph.node)
    orig.graph.output.append(
        helper.make_tensor_value_info(bin_output, onnx.TensorProto.FLOAT, [1, 5])
    )
    base = compose.add_prefix(orig, "prior/")
    graph = compose.merge_graphs(
        base.graph,
        head.graph,
        [
            ("prior/action_logits", "escape/parent_actions"),
            ("prior/" + bin_output, "escape/bin_features"),
        ],
    )
    keep = [x for x in graph.input if x.name not in {"escape/" + s for s in names[:4]}]
    del graph.input[:]
    graph.input.extend(keep)
    rename = {
        "prior/" + v.name: v.name
        for v in list(orig.graph.input) + list(orig.graph.output)
        if v.name != "action_logits"
    }
    rename.update(
        {"escape/" + s: s for s in names[:-1] + ["action_logits", "next_escape_memory"]}
    )
    for node in graph.node:
        for field in (node.input, node.output):
            for i, k in enumerate(field):
                field[i] = rename.get(k, k)
    for field in (graph.input, graph.output, graph.value_info):
        for v in field:
            v.name = rename.get(v.name, v.name)
    model = helper.make_model(
        graph, opset_imports=orig.opset_import, ir_version=orig.ir_version
    )
    onnx.checker.check_model(model)
    onnx.save(model, out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("parent", "weights", "prototypes", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    export(a.parent, a.weights, a.prototypes, a.out)
