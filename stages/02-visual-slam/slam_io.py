"""InFrame stage 2 input, calibration, and ORB-SLAM3 trajectory adapter.

Requires OpenCV and NumPy. Run `python slam_io.py --help`.
"""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def prepare(args):
    out = Path(args.out).resolve()
    images = out / "rgb"
    images.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {args.video}")
    native_fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not math.isfinite(native_fps) or native_fps <= 0:
        raise ValueError("Video FPS unavailable; transcode or provide a valid video")
    native_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    native_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if min(native_width, native_height) <= 0:
        raise ValueError("Invalid video dimensions")
    target_fps = args.fps or min(native_fps, 15.0)
    if target_fps <= 0 or target_fps > native_fps * 1.05:
        raise ValueError("Requested FPS must be positive and no higher than source FPS")
    scale = min(1.0, args.max_width / native_width)
    width = round(native_width * scale)
    height = round(native_height * scale)
    manifest = []
    source_index = 0
    last_time = -1.0
    next_sample = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if not math.isfinite(pts) or pts <= last_time:
            pts = source_index / native_fps
        source_index += 1
        last_time = pts
        if pts + 1e-6 < next_sample:
            continue
        next_sample += 1.0 / target_fps
        if scale != 1.0:
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        filename = f"{len(manifest):06d}.png"
        if not cv2.imwrite(str(images / filename), frame):
            raise IOError(f"Cannot save {filename}")
        manifest.append({"timestamp_s": round(pts, 6), "image": f"rgb/{filename}"})
    cap.release()
    if len(manifest) < 2:
        raise ValueError("At least two frames are needed")
    # ORB-SLAM3's mono_tum.cc skips exactly three header lines.
    lines = ["# InFrame RGB sequence", "# timestamp_s image_path", "# generated from video"]
    lines += [f"{item['timestamp_s']:.6f} {item['image']}" for item in manifest]
    (out / "rgb.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    info = {
        "source_video": str(Path(args.video).resolve()),
        "source_width": native_width,
        "source_height": native_height,
        "source_fps": native_fps,
        "image_width": width,
        "image_height": height,
        "sample_fps": target_fps,
        "frame_count": len(manifest),
        "frames": manifest,
    }
    write_json(out / "frames.json", info)
    print(f"Prepared {len(manifest)} frames: {out}")


def combine(args):
    """Join two prepared traversals so ORB-SLAM3 can attempt recovery after a jump."""
    out = Path(args.out).resolve()
    images = out / "rgb"
    images.mkdir(parents=True, exist_ok=True)
    manifests = []
    for source in (Path(args.first).resolve(), Path(args.second).resolve()):
        info = json.loads((source / "frames.json").read_text(encoding="utf-8"))
        manifests.append((source, info))
    if (manifests[0][1]["image_width"], manifests[0][1]["image_height"]) != (manifests[1][1]["image_width"], manifests[1][1]["image_height"]):
        raise ValueError("Both traversals must have the same image size and camera calibration")
    fps = min(float(m[1]["sample_fps"]) for m in manifests)
    lines = ["# InFrame RGB sequence", "# timestamp_s image_path", "# two traversals"]
    frames = []
    offset = 0.0
    for segment_id, (source, info) in enumerate(manifests):
        first_time = info["frames"][0]["timestamp_s"]
        for source_frame in info["frames"]:
            t = offset + source_frame["timestamp_s"] - first_time
            filename = f"{len(frames):06d}.png"
            link = images / filename
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to((source / source_frame["image"]).resolve())
            frames.append({"timestamp_s": round(t, 6), "image": f"rgb/{filename}", "segment_id": segment_id})
            lines.append(f"{t:.6f} rgb/{filename}")
        offset = frames[-1]["timestamp_s"] + 1.0 / fps
    (out / "rgb.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(out / "frames.json", {"image_width": manifests[0][1]["image_width"],
                                      "image_height": manifests[0][1]["image_height"],
                                      "sample_fps": fps, "frame_count": len(frames), "frames": frames})
    print(f"Combined {len(frames)} frames from two traversals: {out}")


def calibrate(args):
    image_paths = sorted(Path(args.images).glob(args.glob))
    if len(image_paths) < 8:
        raise ValueError("Need at least 8 checkerboard views from varied angles")
    cols, rows = args.columns, args.rows
    obj = np.zeros((cols * rows, 3), np.float32)
    obj[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * args.square_m
    object_points, image_points = [], []
    size = None
    used = []
    for image_path in image_paths:
        image = cv2.imread(str(image_path))
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        current_size = (gray.shape[1], gray.shape[0])
        if size is not None and current_size != size:
            raise ValueError("Calibration images have mixed dimensions")
        size = current_size
        found, corners = cv2.findChessboardCorners(gray, (cols, rows))
        if not found:
            continue
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                                   (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
        object_points.append(obj)
        image_points.append(corners)
        used.append(str(image_path))
    if len(used) < 8:
        raise ValueError(f"Checkerboard found in only {len(used)} images; need at least 8")
    rms, camera, dist, _, _ = cv2.calibrateCamera(object_points, image_points, size, None, None)
    result = {
        "model": "pinhole_opencv",
        "width": size[0], "height": size[1],
        "fx": float(camera[0, 0]), "fy": float(camera[1, 1]),
        "cx": float(camera[0, 2]), "cy": float(camera[1, 2]),
        "k1": float(dist.ravel()[0]), "k2": float(dist.ravel()[1]),
        "p1": float(dist.ravel()[2]), "p2": float(dist.ravel()[3]),
        "k3": float(dist.ravel()[4]) if dist.size > 4 else 0.0,
        "rms_px": float(rms), "views_used": len(used), "images_used": used,
        "board_inner_corners": [cols, rows], "square_m": args.square_m,
    }
    write_json(Path(args.out), result)
    print(f"Calibrated with {len(used)} images; RMS={rms:.3f} px")


def make_config(args):
    cam = json.loads(Path(args.camera).read_text(encoding="utf-8"))
    frames = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    required = ("width", "height", "fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2")
    missing = [key for key in required if key not in cam]
    if missing:
        raise ValueError(f"Camera calibration missing: {missing}")
    sx = frames["image_width"] / cam["width"]
    sy = frames["image_height"] / cam["height"]
    if abs(sx - sy) > 0.005:
        raise ValueError("Camera calibration and video have different aspect ratios")
    for key in ("fx", "fy"):
        if cam[key] <= 0:
            raise ValueError(f"{key} must be positive")
    values = {key: cam[key] * (sx if key in ("fx", "cx") else sy)
              for key in ("fx", "fy", "cx", "cy")}
    template = f'''%YAML:1.0
File.version: "1.0"
Camera.type: "PinHole"
Camera1.fx: {values["fx"]:.8f}
Camera1.fy: {values["fy"]:.8f}
Camera1.cx: {values["cx"]:.8f}
Camera1.cy: {values["cy"]:.8f}
Camera1.k1: {cam["k1"]:.8f}
Camera1.k2: {cam["k2"]:.8f}
Camera1.p1: {cam["p1"]:.8f}
Camera1.p2: {cam["p2"]:.8f}
Camera1.k3: {cam.get("k3", 0.0):.8f}
Camera.fps: {frames["sample_fps"]:.6f}
Camera.RGB: 0
Camera.width: {frames["image_width"]}
Camera.height: {frames["image_height"]}
ORBextractor.nFeatures: 1500
ORBextractor.scaleFactor: 1.2
ORBextractor.nLevels: 8
ORBextractor.iniThFAST: 20
ORBextractor.minThFAST: 7
Viewer.KeyFrameSize: 0.05
Viewer.KeyFrameLineWidth: 1.0
Viewer.GraphLineWidth: 0.9
Viewer.PointSize: 2.0
Viewer.CameraSize: 0.08
Viewer.CameraLineWidth: 3.0
Viewer.ViewpointX: 0.0
Viewer.ViewpointY: -0.7
Viewer.ViewpointZ: -1.8
Viewer.ViewpointF: 500.0
'''
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(template, encoding="utf-8")
    print(f"ORB-SLAM3 config: {args.out}")


def read_trajectory(path, timestamp_scale):
    poses = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 8:
            raise ValueError("Expected timestamp tx ty tz qx qy qz qw")
        nums = [float(x) for x in fields]
        if not all(math.isfinite(x) for x in nums):
            raise ValueError("Non-finite trajectory value")
        q = np.array(nums[4:8], dtype=float)
        q /= np.linalg.norm(q)
        poses.append({"timestamp_s": nums[0] * timestamp_scale,
                      "translation_slam": nums[1:4], "quaternion_xyzw": q.tolist()})
    if not poses:
        raise ValueError("Empty trajectory")
    poses.sort(key=lambda p: p["timestamp_s"])
    return poses


def nearest(poses, timestamp):
    pose = min(poses, key=lambda p: abs(p["timestamp_s"] - timestamp))
    if abs(pose["timestamp_s"] - timestamp) > 1.0:
        raise ValueError(f"No keyframe within 1 second of anchor {timestamp}")
    return pose


def export(args):
    poses = read_trajectory(args.trajectory, 1e-9 if args.format == "euroc" else 1.0)
    scale = None
    anchors = None
    if args.anchor_a is not None or args.anchor_b is not None or args.distance_m is not None:
        if any(x is None for x in (args.anchor_a, args.anchor_b, args.distance_m)):
            raise ValueError("Both anchor times and physical distance are required")
        if args.distance_m <= 0:
            raise ValueError("Distance must be positive")
        a, b = nearest(poses, args.anchor_a), nearest(poses, args.anchor_b)
        baseline = float(np.linalg.norm(np.array(a["translation_slam"]) - np.array(b["translation_slam"])))
        if baseline < 1e-6:
            raise ValueError("Anchors have no usable SLAM baseline")
        scale = args.distance_m / baseline
        anchors = {"a_timestamp_s": a["timestamp_s"], "b_timestamp_s": b["timestamp_s"],
                   "physical_distance_m": args.distance_m, "slam_distance": baseline}
    converted = []
    for pose in poses:
        converted.append({"timestamp_s": pose["timestamp_s"],
                          "position": [x * scale for x in pose["translation_slam"]] if scale else None,
                          "position_slam_units": pose["translation_slam"],
                          "quaternion_xyzw": pose["quaternion_xyzw"]})
    result = {"schema_version": 1, "pose_convention": "world_T_camera",
              "coordinate_frame": "ORB-SLAM3 world; orientation not yet gravity-aligned",
              "metric_scale_m_per_slam_unit": scale, "scale_anchors": anchors,
              "source_format": args.format, "poses": converted}
    write_json(Path(args.out), result)
    print(f"Exported {len(poses)} poses; metric scale={scale}")


def export_map(args):
    pose_data = json.loads(Path(args.poses).read_text(encoding="utf-8"))
    scale = pose_data["metric_scale_m_per_slam_unit"]
    points = []
    for line in Path(args.points).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("Expected map point ID and XYZ")
        xyz = [float(x) for x in fields[1:4]]
        if all(math.isfinite(x) for x in xyz):
            points.append({"id": int(fields[0]), "position_slam_units": xyz,
                           "position_m": [x * scale for x in xyz] if scale else None})
    write_json(Path(args.out), {"schema_version": 1, "metric_scale_m_per_slam_unit": scale,
                                "point_count": len(points), "points": points})
    print(f"Exported {len(points)} map points")


def report(args):
    statuses = []
    for line in Path(args.status).read_text(encoding="utf-8").splitlines()[1:]:
        fields = line.split(",")
        if len(fields) != 3:
            raise ValueError("TrackingStatus.csv has invalid row")
        statuses.append((float(fields[0]), int(fields[1]), int(fields[2])))
    lost_to_ok = []
    had_loss = False
    for t, state, _ in statuses:
        if state in (3, 4):
            had_loss = True
        elif state == 2 and had_loss:
            lost_to_ok.append(t)
            had_loss = False
    result = {
        "frame_count": len(statuses),
        "tracked_ok_count": sum(s == 2 for _, s, _ in statuses),
        "tracked_ok_fraction": sum(s == 2 for _, s, _ in statuses) / len(statuses) if statuses else 0,
        "big_map_change_times_s": [t for t, _, changed in statuses if changed],
        "lost_to_ok_times_s": lost_to_ok,
        "interpretation": "A big map change is not by itself proof of loop closure; inspect trajectory and map. Lost-to-OK indicates tracking recovery, which may need visual verification for relocalization.",
    }
    write_json(Path(args.out), result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="Extract frames and TUM rgb.txt from a video")
    p.add_argument("video"); p.add_argument("out")
    p.add_argument("--fps", type=float); p.add_argument("--max-width", type=int, default=960)
    p.set_defaults(func=prepare)
    p = sub.add_parser("combine", help="Join two prepared traversals for recovery testing")
    p.add_argument("first"); p.add_argument("second"); p.add_argument("out")
    p.set_defaults(func=combine)
    p = sub.add_parser("calibrate", help="Calibrate from checkerboard photos")
    p.add_argument("images"); p.add_argument("out")
    p.add_argument("--glob", default="*.jpg"); p.add_argument("--columns", type=int, default=9)
    p.add_argument("--rows", type=int, default=6); p.add_argument("--square-m", type=float, required=True)
    p.set_defaults(func=calibrate)
    p = sub.add_parser("make-config", help="Convert camera.json to ORB-SLAM3 YAML")
    p.add_argument("camera"); p.add_argument("frames"); p.add_argument("out")
    p.set_defaults(func=make_config)
    p = sub.add_parser("export", help="Convert ORB-SLAM3 trajectory to common JSON")
    p.add_argument("trajectory"); p.add_argument("out")
    p.add_argument("--format", choices=("euroc", "tum"), default="euroc")
    p.add_argument("--anchor-a", type=float); p.add_argument("--anchor-b", type=float)
    p.add_argument("--distance-m", type=float)
    p.set_defaults(func=export)
    p = sub.add_parser("export-map", help="Convert sparse map points using the same metric scale")
    p.add_argument("points"); p.add_argument("poses"); p.add_argument("out")
    p.set_defaults(func=export_map)
    p = sub.add_parser("report", help="Summarize ORB-SLAM3 tracking status")
    p.add_argument("status"); p.add_argument("out")
    p.set_defaults(func=report)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
