"""Compare stage 6, stage 7 in-memory inference, and actual adapter receipts on identical live-rendered RGB."""
import argparse
import gzip
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from devices import ROOT, LocalPolicy
from runtime import RecordingCamera

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    s6=ROOT.parent/'InFrame_6단계_정책개선'
    data=ROOT/'results/habitat'
    frames=RecordingCamera(data/'media/FRESH-015-rgb.npz').frames
    trace=json.load(gzip.open(data/'traces/normal/FRESH-015.json.gz','rt'))['steps']
    dispatched=json.loads((ROOT/'results/mock_session.json').read_text())
    moves=[e for e in dispatched['events'] if e['rpc']=='Move']
    worker=subprocess.Popen([sys.executable,str(s6/'src/worker.py'),str(s6/'weights/recovery.pt')],
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        worker.stdin.write('R소화기\n'.encode())
        local=LocalPolicy()
        assert len(frames)==len(trace)==len(moves)+1
        for i,(image,row) in enumerate(zip(frames,trace)):
            worker.stdin.write(b'F'+image.tobytes())
            worker.stdin.flush()
            reference=worker.stdout.read(9)
            current=struct.pack('<ffB',*local.act(image))
            assert reference==current==struct.pack('<ffB',*row['raw'])
            if i<len(moves):
                assert moves[i]['seq']==i and moves[i]['args']==row['sent']
            else:
                assert row['raw'][2]==1 and dispatched['result']['reason']=='goal_stop'
    finally:
        worker.stdin.close()
        if worker.wait(timeout=10):
            raise RuntimeError('Comparison worker failed')
    args.out.write_text(json.dumps(dict(id='FRESH-015',same_rgb_frames=len(frames),
        raw_policy_packets_exact=len(frames),mock_and_sim_move_args_exact=len(moves),final_stop=True),indent=2)+'\n')
    print('Identical input -> identical action packets for',len(frames),'frames.')

if __name__=='__main__':
    main()
