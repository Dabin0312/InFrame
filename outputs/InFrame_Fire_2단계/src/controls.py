"""Construct explicitly synthetic visibility controls from two held-out Fire RGBs."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw

def create(scene, dest):
    dest.mkdir(parents=True, exist_ok=True)
    # Cover the full silhouette, including hose and handle; preserve background for pose.
    for i in (0, 10):
        im = Image.open(scene / 'seq-02' / f'frame-{i:06}.color.png').convert('RGB')
        boxes = {'A': (294, 174, 373, 314), 'B': (374, 137, 464, 305)}
        for visible, hidden in [('A','B'),('B','A'),('none','AB')]:
            copy = im.copy()
            draw = ImageDraw.Draw(copy)
            for obj in hidden:
                draw.rectangle(boxes[obj], fill=(102,102,102))
            copy.save(dest / f'control_{i:06}_{visible}.png')

if __name__ == '__main__':
    create(Path(sys.argv[1]),Path(sys.argv[2]))
