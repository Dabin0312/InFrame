import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
S4 = ROOT.parent / 'InFrame_4단계'
S5 = ROOT.parent / 'InFrame_5단계'
WORK = ROOT.parent.parent / 'work/recovery6'
sys.path.extend([str(S5/'src'),str(S4/'src')])

def read(p):
    return json.loads(p.read_text())
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def block(p):
    import math
    return math.floor(float(p[0])/2),math.floor(float(p[2])/2)
