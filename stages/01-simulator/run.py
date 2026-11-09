"""Render the InFrame sample scene and check navigation and wall collisions."""

import argparse
from pathlib import Path
import json
import math

import habitat_sim
import imageio.v2 as imageio
import magnum as mn
import numpy as np
import trimesh
from PIL import Image, ImageDraw
from habitat_sim.utils.common import quat_from_angle_axis


def box(extents, center, rgba):
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    # trimesh exports z-up geometry to glTF's y-up convention.
    # Supply the inverse transform so Habitat receives the intended y-up room.
    mesh.apply_transform(np.array([
        [1, 0, 0, 0],
        [0, 0, -1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1],
    ], dtype=float))
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.SimpleMaterial(diffuse=np.array(rgba, dtype=np.uint8))
    )
    return mesh


def make_scene(out):
    pieces = [
        box([8, 0.2, 8], [0, -0.1, 0], [195, 195, 190, 255]),
        box([8, 2.8, 0.2], [0, 1.4, -4], [210, 220, 230, 255]),
        box([8, 2.8, 0.2], [0, 1.4, 4], [210, 220, 230, 255]),
        box([0.2, 2.8, 8], [-4, 1.4, 0], [180, 205, 220, 255]),
        box([0.2, 2.8, 8], [4, 1.4, 0], [180, 205, 220, 255]),
        box([1.8, 1.1, 1.2], [-0.5, 0.55, 0], [80, 115, 165, 255]),
        box([0.8, 0.8, 1.3], [1.3, 0.4, 0.2], [130, 100, 75, 255]),
        box([0.35, 0.95, 0.35], [2.7, 0.475, -2.5], [220, 45, 40, 255]),
    ]
    scene_path = out / "sample_room.glb"
    trimesh.Scene({f"part_{i}": m for i, m in enumerate(pieces)}).export(scene_path)
    return scene_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scene_path = make_scene(out)
    sim_cfg = habitat_sim.SimulatorConfiguration()
    sim_cfg.scene_id = str(scene_path)
    sensor = habitat_sim.CameraSensorSpec()
    sensor.uuid = "rgb"
    sensor.sensor_type = habitat_sim.SensorType.COLOR
    sensor.resolution = [480, 640]
    sensor.position = mn.Vector3(0, 1.15, 0)
    agent_cfg = habitat_sim.agent.AgentConfiguration()
    agent_cfg.sensor_specifications = [sensor]
    sim = habitat_sim.Simulator(habitat_sim.Configuration(sim_cfg, [agent_cfg]))
    try:
        nav = habitat_sim.NavMeshSettings()
        nav.set_defaults()
        nav.agent_radius = 0.22
        nav.agent_height = 0.65
        nav.agent_max_climb = 0.10
        nav.agent_max_slope = 45.0
        nav_ok = sim.recompute_navmesh(sim.pathfinder, nav)
        if not nav_ok:
            raise RuntimeError("NavMesh generation failed")
        sim.pathfinder.save_nav_mesh(str(out / "sample_room.navmesh"))

        start = np.array([-2.8, 0.0, 2.7], dtype=np.float32)
        goal = np.array([2.7, 0.0, -2.0], dtype=np.float32)
        print("NAV DEBUG", sim.pathfinder.navigable_area, sim.pathfinder.is_navigable(start), sim.pathfinder.is_navigable(goal), sim.pathfinder.snap_point(start), sim.pathfinder.snap_point(goal), flush=True)
        path = habitat_sim.ShortestPath()
        path.requested_start = start
        path.requested_end = goal
        found = sim.pathfinder.find_path(path)
        if not found:
            raise RuntimeError("No path from start to goal")

        agent = sim.initialize_agent(0)
        points = [np.asarray(p).tolist() for p in path.points]
        for label, point, next_point in [
            ("start", start, np.asarray(path.points[1])),
            ("goal", goal, np.asarray(path.points[-2])),
        ]:
            direction = next_point - point if label == "start" else point - next_point
            yaw = -math.atan2(float(direction[0]), -float(direction[2]))
            state = habitat_sim.AgentState()
            state.position = point
            state.rotation = quat_from_angle_axis(yaw, np.array([0.0, 1.0, 0.0]))
            agent.set_state(state)
            rgba = sim.get_sensor_observations()["rgb"]
            imageio.imwrite(out / f"{label}_rgb.png", rgba[:, :, :3])

        # Ask the navmesh to move through the side wall; it should stop inside.
        wall_start = np.array([3.2, 0.0, 0.0], dtype=np.float32)
        wall_requested = np.array([5.0, 0.0, 0.0], dtype=np.float32)
        wall_actual = np.asarray(sim.pathfinder.try_step(wall_start, wall_requested))
        wall_blocked = bool(np.linalg.norm(wall_requested - wall_actual) > 0.5)
        canvas = Image.new("RGB", (720, 720), (239, 243, 245))
        draw = ImageDraw.Draw(canvas)
        def xy(point):
            return (int((float(point[0]) + 4) * 90), int((float(point[2]) + 4) * 90))
        def rect(x1, z1, x2, z2, color):
            draw.rectangle([xy((x1, 0, z1)), xy((x2, 0, z2))], fill=color)
        rect(-4, -4, 4, -3.9, (85, 102, 115))
        rect(-4, 3.9, 4, 4, (85, 102, 115))
        rect(-4, -4, -3.9, 4, (85, 102, 115))
        rect(3.9, -4, 4, 4, (85, 102, 115))
        rect(-1.4, -0.6, 0.4, 0.6, (80, 115, 165))
        rect(0.9, -0.45, 1.7, 0.85, (130, 100, 75))
        rect(2.525, -2.675, 2.875, -2.325, (220, 45, 40))
        draw.line([xy(p) for p in path.points], fill=(40, 150, 75), width=7)
        for point, color in [(start, (30, 100, 240)), (goal, (230, 45, 40))]:
            x, y = xy(point)
            draw.ellipse((x-10, y-10, x+10, y+10), fill=color, outline=(255,255,255), width=2)
        draw.line([xy(wall_start), xy(wall_requested)], fill=(235, 110, 40), width=5)
        x, y = xy(wall_actual)
        draw.ellipse((x-7, y-7, x+7, y+7), fill=(235, 110, 40))
        canvas.save(out / "topdown_path.png")
        result = {
            "simulator": "Habitat-Sim",
            "version": getattr(habitat_sim, "__version__", "unknown"),
            "platform": "macOS arm64 local",
            "scene": scene_path.name,
            "navmesh_generated": bool(nav_ok),
            "start_navigable": bool(sim.pathfinder.is_navigable(start)),
            "goal_navigable": bool(sim.pathfinder.is_navigable(goal)),
            "path_found": bool(found),
            "path_length_m": round(float(path.geodesic_distance), 3),
            "path_points_m": points,
            "wall_collision_test": {
                "requested_position_m": wall_requested.tolist(),
                "actual_position_m": wall_actual.tolist(),
                "blocked": wall_blocked,
            },
            "renders": ["start_rgb.png", "goal_rgb.png", "topdown_path.png"],
        }
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        assert result["start_navigable"] and result["goal_navigable"]
        assert result["path_found"] and wall_blocked
    finally:
        sim.close()


if __name__ == "__main__":
    main()
