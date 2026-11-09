"""Package browser exports, the exact policy observations and independently chosen reference stills."""
import argparse, base64, hashlib, json, zipfile
from pathlib import Path
import cv2

HERE = Path(__file__).resolve().parent

def crop_reference(path, seconds):
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"Missing reference at {seconds}s in {path}")
    h,w = frame.shape[:2]
    sw = min(w, int(h*4/3))
    sh = int(sw*3/4)
    y,x = (h-sh)//2,(w-sw)//2
    rgb = cv2.resize(frame[y:y+sh,x:x+sw], (320,240))
    ok, encoded = cv2.imencode('.jpg', rgb, [cv2.IMWRITE_JPEG_QUALITY,92])
    if not ok:
        raise ValueError('Reference encoding failed')
    return 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode()

def plane(p):
    return [round(p[0],6), round(p[2],6)]

def build(media,runs,out):
    split = json.loads((HERE/'split.json').read_text())
    labels = json.loads((HERE/'holdout-labels.json').read_text())['cases']
    cases = []
    with zipfile.ZipFile(out/'replays.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in split['test']:
            label = labels[name]
            path = runs/(name+'.json')
            run = json.loads(path.read_text())
            z.write(path,path.name)
            frames = run['frames']
            case = dict(id=name, **label)
            case['url']='https://huggingface.co/datasets/OpenDriveLab/SparseVideoNav/blob/main/'+split['records'][name]['video_path']
            case['refPhoto']=crop_reference(media/(name+'.mp4'),case['reference'])
            case['referenceSeg']=min(frames,key=lambda f:abs(f['t']-case['reference']))['seg']
            case['segments']=sorted({f['seg'] for f in frames})
            case['path']=[[f['seg'],*plane(f['pose'][12:15])] if f['pose'] else [f['seg']] for f in frames]
            case['points']=[[r['seg'],*plane(r['p'])] for r in run['points']]
            case['targets']=[[r['seg'],*plane(r['p']),r['id']] for r in run['targets']]
            case['media_sha256']=hashlib.sha256((media/(name+'.mp4')).read_bytes()).hexdigest()
            for k,action in [('before','baseline'),('stop','action')]:
                ev = run[k]
                first = next((r for r in frames if r[action] and r[action][2]),None)
                assert (first['t'] if first is not None else None)==(ev['t'] if ev else None)
                case[k] = None if not ev else dict(t=ev['t'],photo=ev['photo'],seg=ev['seg'],
                    p=plane(ev['pose'][12:15]) if ev['pose'] else None,
                    valid=any(a<=ev['t']<=b for a,b in case['windows']))
            cases.append(case)
        for f in ['split.json','frozen.json','holdout-labels.json']:
            z.write(HERE/f,f)
    (out/'results.json').write_text(json.dumps({'cases':cases},ensure_ascii=False,separators=(',',':')))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ['media','runs','out']:
        p.add_argument(n,type=Path)
    a=p.parse_args();build(a.media,a.runs,a.out)
