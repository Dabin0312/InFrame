"""Run the locally built ORB-SLAM3 monocular executable on prepared frames."""

import argparse
import json
import subprocess
from pathlib import Path

import slam_io as sio


def main():
    p = argparse.ArgumentParser()
    p.add_argument("sequence", help="Directory containing rgb.txt and rgb/*.png")
    p.add_argument("config", help="ORB-SLAM3 camera YAML")
    p.add_argument("out", help="Run output directory")
    p.add_argument("--orb-root", help="ORB-SLAM3 repository directory")
    p.add_argument("--anchor-a", type=float)
    p.add_argument("--anchor-b", type=float)
    p.add_argument("--distance-m", type=float)
    args = p.parse_args()
    project = Path(__file__).resolve().parents[2]
    orb = Path(args.orb_root).resolve() if args.orb_root else project / "work/vendor/ORB_SLAM3"
    sequence = Path(args.sequence).resolve()
    config = Path(args.config).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    exe = orb / "Examples/Monocular/mono_tum"
    vocab = orb / "Vocabulary/ORBvoc.txt"
    for required in (sequence / "rgb.txt", config, exe, vocab):
        if not required.exists():
            raise FileNotFoundError(required)
    with (out / "orb_slam3.log").open("w", encoding="utf-8") as log:
        run = subprocess.run([str(exe), str(vocab), str(config), str(sequence)],
                             cwd=out, stdout=log, stderr=subprocess.STDOUT, check=False)
    if run.returncode:
        raise RuntimeError(f"ORB-SLAM3 exit={run.returncode}; see {out / 'orb_slam3.log'}")
    trajectory = out / "FrameTrajectoryEuRoC.txt"
    if not trajectory.exists() or trajectory.stat().st_size == 0:
        raise RuntimeError("No tracked frame trajectory was produced; inspect ORB log and camera calibration")
    export_args = argparse.Namespace(trajectory=str(trajectory), out=str(out / "poses.json"),
                                     format="euroc", anchor_a=args.anchor_a,
                                     anchor_b=args.anchor_b, distance_m=args.distance_m)
    sio.export(export_args)
    sio.export_map(argparse.Namespace(points=str(out / "MapPoints.xyz"),
                                      poses=str(out / "poses.json"), out=str(out / "map_points.json")))
    sio.report(argparse.Namespace(status=str(out / "TrackingStatus.csv"), out=str(out / "tracking_report.json")))
    poses = json.loads((out / "poses.json").read_text(encoding="utf-8"))
    points = json.loads((out / "map_points.json").read_text(encoding="utf-8"))
    print(f"Complete: {len(poses['poses'])} poses, {points['point_count']} sparse map points at {out}")


if __name__ == "__main__":
    main()
