"""Repeat cases with differing initial raw hashes using one shared live render."""
import contextlib
import numpy as np
from PIL import Image
from common import ROOT, S5, WORK, read, write
from evaluate import World, RemotePolicy, trial
from run import UpdatedWorker
from freeze import artifacts
from common import sha

class FirstImage:
    def __init__(self, world, image):
        self.world = world
        self.image = image
        self.pending = True

    def __getattr__(self, name):
        return getattr(self.world, name)

    def rgb(self):
        if self.pending:
            self.pending = False
            return self.image.copy()
        return self.world.rgb()

def main():
    lock = read(ROOT/'모델봉인.json')
    assert all(sha(path)==lock[key] for key,path in artifacts().items())
    world = World('castle', register=False)
    report = []
    executable = ROOT.parent.parent/'work/fire-models/env/bin/python'
    try:
        for split, folder, cases in [
            ('fresh',ROOT/'episodes',read(ROOT/'봉인_출발점.json')['cases']),
            ('train',WORK/'train',read(ROOT/'학습구역.json')['train_cases'])
        ]:
            paired = zip(read(folder/'before.json'),read(folder/'after.json'),cases)
            for a,b,case in paired:
                if a['initial_rgb_sha256']==b['initial_rgb_sha256']:
                    continue
                world.reset(np.asarray(case['start_xyz']),case['start_yaw'])
                frame = world.rgb().copy()
                output = ROOT/'integrity'/case['id']
                output.mkdir(parents=True, exist_ok=True)
                Image.fromarray(frame).save(output/'first.png')
                reruns = []
                for mode, cls, ckpt, original in [
                    ('before', RemotePolicy, S5/'checkpoints/student-4.pt', a),
                    ('after', UpdatedWorker, ROOT/'weights/recovery.pt', b)
                ]:
                    with contextlib.closing(cls(executable, ckpt)) as policy:
                        rerun = trial(FirstImage(world, frame),policy,case,4,output/mode)
                    reruns.append(rerun)
                    assert (rerun['reason'],rerun['collisions'])==(original['reason'],original['collisions'])
                assert reruns[0]['initial_rgb_sha256']==reruns[1]['initial_rgb_sha256']
                report.append(dict(split=split,case=case['id'],shared_hash=reruns[0]['initial_rgb_sha256'],
                                   outcomes=[r['reason'] for r in reruns],collisions=[r['collisions'] for r in reruns]))
    finally:
        world.close()
    write(ROOT/'동일첫프레임_재검증.json',report)

if __name__=='__main__':
    main()
