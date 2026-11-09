"""Text-prompted extinguisher detection and box-prompted SAM 2 masks on Fire."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor, Sam2Model, Sam2Processor

MAP = [('seq-01', i) for i in range(0, 80, 10)]
NEAR = [('seq-02', i) for i in range(0, 80, 10)]
WIDE = [('seq-02', i) for i in range(100, 1000, 100)] + [('seq-03', i) for i in range(0, 1000, 90)] + [('seq-04', i) for i in sorted([*range(0,1000,125), *range(60,1000,125)])]
PROMPT = 'a fire extinguisher.'
DINO_REV = 'a2bb814dd30d776dcf7e30523b00659f4f141c71'
SAM_REV = 'de431c4043854a71d8101e17995dfe596bf101a5'


def photo(scene, seq, i):
    return scene / seq / f'frame-{i:06}.color.png'


def name(seq, i):
    return f'{seq}_{i:06}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scene', type=Path)
    parser.add_argument('cache', type=Path)
    parser.add_argument('--dino', default='IDEA-Research/grounding-dino-tiny')
    parser.add_argument('--sam', default='facebook/sam2.1-hiera-tiny')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--controls', type=Path, help='directory of controlled occlusion images')
    args = parser.parse_args()
    args.cache.mkdir(exist_ok=True, parents=True)
    torch.set_num_threads(6)
    dp = AutoProcessor.from_pretrained(args.dino, revision=DINO_REV)
    detector = AutoModelForZeroShotObjectDetection.from_pretrained(args.dino, revision=DINO_REV).eval().to(args.device)
    sp = Sam2Processor.from_pretrained(args.sam, revision=SAM_REV)
    segmenter = Sam2Model.from_pretrained(args.sam, revision=SAM_REV).eval().to(args.device)
    files = [(name(seq,i), photo(args.scene,seq,i)) for seq,i in MAP+NEAR+WIDE]
    if args.controls:
        files = [(p.stem,p) for p in sorted(args.controls.glob('*.png'))]
    for key,path in files:
        dest = args.cache / key
        if dest.with_suffix('.json').exists() and dest.with_suffix('.npz').exists():
            continue
        img = Image.open(path).convert('RGB')
        with torch.inference_mode():
            inp = dp(images=img, text=PROMPT, return_tensors='pt').to(args.device)
            out = detector(**inp)
            det = dp.post_process_grounded_object_detection(out, inp.input_ids, threshold=.15, text_threshold=.15, target_sizes=[img.size[::-1]])[0]
            boxes = det['boxes'].cpu().numpy()
            scores = det['scores'].cpu().numpy()
            masks = np.zeros((0, img.height, img.width), dtype=bool)
            if len(boxes):
                s_in = sp(images=img, input_boxes=[boxes.tolist()], return_tensors='pt').to(args.device)
                s_out = segmenter(**s_in, multimask_output=False)
                masks = sp.post_process_masks(s_out.pred_masks.cpu(), s_in.original_sizes.cpu())[0][:,0].numpy().astype(bool)
        # DINO can give several boxes for one item. Deduplicate by actual mask overlap.
        kept = []
        for j in np.argsort(-scores):
            m = masks[j]
            if m.sum() < 100:
                continue
            if any((m & masks[k]).sum() / (m | masks[k]).sum() > .60 for k in kept):
                continue
            kept.append(int(j))
        np.savez_compressed(dest.with_suffix('.npz'), masks=np.packbits(masks[kept], axis=-1))
        dest.with_suffix('.json').write_text(json.dumps([
            {'box_xyxy': boxes[j].tolist(), 'detector_score':float(scores[j]), 'mask_pixels':int(masks[j].sum())} for j in kept]))
        print(key, len(kept), [round(float(scores[j]),2) for j in kept], flush=True)


if __name__ == '__main__':
    main()
