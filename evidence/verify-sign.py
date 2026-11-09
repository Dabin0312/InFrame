"""Validate one Fire seq-01 map anchor on later, unused RGB-D views.

Run with a 3DMatch 7-scenes-fire directory, YOLOE weights and MobileCLIP.
Output masks come from the detector; no mask after frame 39 enters the fit.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation


def inside_margin_anchor(masks, depth, poses, K):
    # Carve a sampled visual hull using only the reference interval.
    first = masks[0][1]
    v, u = np.where(first)
    xx, yy = np.meshgrid(np.arange(u.min(), u.max()+1, 4), np.arange(v.min(), v.max()+1, 4))
    xy = np.c_[xx.ravel(), yy.ravel()]
    xy = xy[first[xy[:, 1], xy[:, 0]]]
    depth_band = np.quantile(depth[first & (depth > .15) & (depth < 6)], [.05, .95])
    depths = np.arange(*depth_band, .013)
    rays = np.einsum("ni,ji->nj", np.c_[xy, np.ones(len(xy))], np.linalg.inv(K))
    points = (depths[:, None, None] * rays[None]).reshape(-1, 3)
    points = np.einsum("ni,ji->nj",points,poses[0][:3, :3]) + poses[0][:3, 3]
    scores = []
    for i, mask in masks:
        uv, z = project(points, poses[i], K)
        h, w = mask.shape
        valid = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
        margin = cv2.distanceTransform(mask.astype('uint8'), cv2.DIST_L2, 5)
        s = np.zeros(len(points))
        x, y = uv[valid].T
        s[valid] = margin[y, x] / max(1, margin.max())
        scores.append(s)
    score = np.min(scores, axis=0) + .1 * np.mean(scores, axis=0)
    if score.max() <= 0:
        raise ValueError('No region jointly supported by the reference silhouettes')
    return np.median(points[score >= .98 * score.max()], axis=0)


def project(points, pose, K):
    camera = np.einsum("ni,ij->nj",points - pose[:3, 3],pose[:3, :3])
    projected = np.einsum("ni,ji->nj",camera,K)
    return np.rint(projected[:, :2] / np.maximum(1e-8, projected[:, 2:])).astype(int), camera[:, 2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cache', type=Path, help='Optional cached YOLOE masks from this exact sequence')
    parser.add_argument('--weights', default='yoloe-11s-seg.pt')
    args = parser.parse_args()
    prefix = lambda i: args.scene/'seq-01'/f'frame-{i:06}'
    rgb = lambda i: cv2.imread(str(prefix(i))+'.color.png')
    depth = lambda i: cv2.imread(str(prefix(i))+'.depth.png', -1)/1000.
    K = np.loadtxt(args.scene/'camera-intrinsics.txt')
    traj = Path(__file__).resolve().parents[1]/'outputs/InFrame_Fire_2단계/src/CameraTrajectory.txt'
    poses = {}
    for ts, x, y, z, *quat in np.loadtxt(traj):
        p = np.eye(4); p[:3, :3] = Rotation.from_quat(quat).as_matrix(); p[:3, 3] = [x, y, z]
        poses[round((ts-1)*30)] = p
    if args.cache:
        def mask(i):
            path = args.cache/f'mask-{i}.npz'
            return np.load(path)['mask'] if path.exists() else None
    else:
        from ultralytics import YOLOE
        net = YOLOE(args.weights)
        net.set_classes(['wet floor sign'], net.get_text_pe(['wet floor sign']))
        def mask(i):
            result = net.predict(rgb(i), conf=.25, imgsz=640, retina_masks=True, verbose=False)[0]
            if not len(result.boxes): return None
            return result.masks.data[result.boxes.conf.argmax()].cpu().numpy().astype(bool)
    first = mask(0)
    def hist(region):
        hsv = cv2.cvtColor(rgb(0), cv2.COLOR_BGR2HSV)
        counts = cv2.calcHist([hsv], [0, 1], region.astype('uint8'), [36, 16], [0, 180, 0, 256])
        return cv2.GaussianBlur(counts, (3, 3), .7) / max(1, region.sum())
    fg = hist(cv2.erode(first.astype('uint8'), np.ones((7, 7), np.uint8)).astype(bool))
    bg = hist(cv2.dilate(first.astype('uint8'), np.ones((63, 63), np.uint8)).astype(bool) & ~first)
    probability = fg / (fg + bg + .00001)
    views, centers = [], []
    previous = first
    for i in range(40):
        m = mask(i)
        if m is None:
            hsv = cv2.cvtColor(rgb(i), cv2.COLOR_BGR2HSV)
            likelihood = probability[(hsv[:, :, 0]//5).clip(0, 35), hsv[:, :, 1]//16]
            near = cv2.dilate(previous.astype('uint8'), np.ones((29, 29), np.uint8))
            closed = cv2.morphologyEx(((likelihood > .7) & (near > 0)).astype('uint8'), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            n, labels, stats, _ = cv2.connectedComponentsWithStats(closed)
            if n < 2: continue
            m = labels == (1+np.argmax(stats[1:, 4]))
            if m.sum() < .48*previous.sum(): continue
        elif i % 5 == 0:
            d = depth(i)
            y, x = np.where(cv2.erode(m.astype('uint8'), np.ones((5, 5), np.uint8)) & (d > .15) & (d < 6))
            x, y = x[::8], y[::8]
            cam = (np.einsum("ni,ji->nj", np.c_[x, y, np.ones(len(x))], np.linalg.inv(K))) * d[y, x, None]
            centers.append(np.median(np.einsum("ni,ji->nj",cam,poses[i][:3, :3]) + poses[i][:3, 3], axis=0))
        previous = m
        if i % 3 == 0 or i == 39: views.append((i, m))
    baseline = np.median(centers, axis=0)
    updated = inside_margin_anchor(views, depth(0), poses, K)
    result = dict(reference_frames=[i for i, _ in views], baseline_xyz=baseline.tolist(), updated_xyz=updated.tolist(), frames=[])
    sheet = Image.new('RGB', (960, 260), 'white')
    for i in range(40, 80):
        m = mask(i)
        row = dict(frame=i, previously_tested=i%5==0, detected=m is not None)
        if m is not None:
            xy, z = project(np.stack([baseline, updated]), poses[i], K)
            row['inside'] = [bool(t>0 and 0<=x<640 and 0<=y<480 and m[y,x]) for (x,y),t in zip(xy,z)]
            row['uv'] = xy.tolist()
            if i in [65, 70, 75]:
                img = rgb(i); contours, _ = cv2.findContours(m.astype('uint8'), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(img, contours, -1, (255,210,65), 2)
                for pt,color in zip(xy, [(10,65,255),(50,245,95)]):
                    cv2.circle(img, tuple(pt), 8, (40,40,40), -1);cv2.circle(img, tuple(pt), 5, color, -1)
                j=(i-65)//5;sheet.paste(Image.fromarray(img[:,:,::-1]).resize((320,240)), (j*320,20))
                ImageDraw.Draw(sheet).text((j*320+8,3), f'Fire {i}  |  orange: previous   green: updated', fill='black')
        result['frames'].append(row)
    args.output.mkdir(parents=True,exist_ok=True)
    sheet.save(args.output/'sign-reprojection.jpg',quality=94)
    (args.output/'sign-reprojection.json').write_text(json.dumps(result,indent=2)+'\n')
    for prev in [True,False]:
        group=[r for r in result['frames'] if r['previously_tested']==prev];det=[r for r in group if r['detected']]
        print(prev,len(group),len(det),np.sum([r['inside'] for r in det],axis=0))

if __name__=='__main__':
    main()
