"""Download and transcode only the registered evaluation recordings."""
import argparse, json, subprocess
from pathlib import Path
from urllib.request import urlretrieve

REV = 'c986feef0f63cd688d8b0835320516dd9aa76280'
BASE = 'https://huggingface.co/datasets/OpenDriveLab/SparseVideoNav/resolve/'
HERE = Path(__file__).resolve().parent

def fetch(media):
    split = json.loads((HERE/'split.json').read_text())
    media.mkdir(exist_ok=True, parents=True)
    for case in split['test']:
        original = media/(case+'.original.mp4')
        if not original.exists():
            tmp = original.with_suffix('.part')
            urlretrieve(BASE+REV+'/'+split['records'][case]['video_path'],tmp)
            tmp.replace(original)
        subprocess.run(['ffmpeg','-v','error','-y','-threads','2','-i',str(original),'-an',
            '-vf',"fps=16,scale='min(640,iw)':-2",'-c:v','libx264','-threads','2',
            '-crf','18','-g','8','-pix_fmt','yuv420p','-movflags','+faststart',
            str(media/(case+'.mp4'))],check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('media',type=Path);fetch(p.parse_args().media)
