"""Independent RGB-only spot check on terminal images; never used by the teacher."""
import argparse,json
from pathlib import Path
from PIL import Image
import torch
from transformers import AutoModelForZeroShotObjectDetection,AutoProcessor
p=argparse.ArgumentParser();p.add_argument('model');a=p.parse_args()
root=Path(__file__).resolve().parents[1];torch.set_num_threads(5)
dp=AutoProcessor.from_pretrained(a.model,local_files_only=True);model=AutoModelForZeroShotObjectDetection.from_pretrained(a.model,local_files_only=True).eval()
allrows=sorted([json.loads(x.read_text()) for x in (root/'episodes').glob('*/episode.json')],key=lambda e:e['id'])
cases={}
for e in allrows:
    # Select one per distinct registered view plus all natural and controlled failures.
    key=e['id'] if not e['success_auto'] else e['scene']+'-'+e['approach_view']
    cases.setdefault(key,e)
out={}
for e in cases.values():
    im=Image.open(root/'episodes'/e['id']/'last.png').convert('RGB');inp=dp(images=im,text='a fire extinguisher.',return_tensors='pt')
    with torch.inference_mode():o=model(**inp)
    detections=dp.post_process_grounded_object_detection(o,inp.input_ids,threshold=.25,text_threshold=.20,target_sizes=[im.size[::-1]])[0]
    out[e['id']]=dict(boxes=detections['boxes'].tolist(),scores=detections['scores'].tolist())
(root/'rgb_spotcheck.json').write_text(json.dumps(dict(model='IDEA-Research/grounding-dino-tiny',revision='a2bb814dd30d776dcf7e30523b00659f4f141c71',prompt='a fire extinguisher.',box_threshold=.25,text_threshold=.20,selection='one success per registered view and all unsuccessful endpoints; not a population metric',results=out),indent=2))
