"""Draw a simple x-z preview of a InFrame SLAM run (SLAM units)."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("poses")
    parser.add_argument("points")
    parser.add_argument("out")
    args = parser.parse_args()
    poses = json.loads(Path(args.poses).read_text(encoding="utf-8"))["poses"]
    points = json.loads(Path(args.points).read_text(encoding="utf-8"))["points"]
    trajectory = np.array([p["position_slam_units"] for p in poses])[:, [0, 2]]
    cloud = np.array([p["position_slam_units"] for p in points])[:, [0, 2]] if points else np.empty((0, 2))
    if len(trajectory) < 2:
        raise ValueError("Need at least two poses")
    bounds = np.percentile(trajectory, [0, 100], axis=0)
    span = np.maximum(bounds[1] - bounds[0], 1e-3)
    low = bounds[0] - span * 0.15
    high = bounds[1] + span * 0.15
    width = height = 900
    def xy(p):
        q = (np.asarray(p) - low) / (high - low)
        return (int(50 + q[0] * 800), int(850 - q[1] * 800))
    im = Image.new("RGB", (width, height), (250, 251, 252))
    draw = ImageDraw.Draw(im)
    for p in cloud:
        x, y = xy(p)
        if 0 <= x < width and 0 <= y < height:
            draw.point((x, y), fill=(190, 195, 200))
    draw.line([xy(p) for p in trajectory], fill=(30, 100, 205), width=4)
    for p, color in ((trajectory[0], (20, 160, 80)), (trajectory[-1], (220, 50, 40))):
        x, y = xy(p)
        draw.ellipse((x-9, y-9, x+9, y+9), fill=color, outline=(255, 255, 255), width=2)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    im.save(args.out)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
