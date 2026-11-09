"""Run frozen 4-frame policies with the original evaluator and RGB-only pipe."""
import argparse,contextlib,subprocess,sys
from common import ROOT,S5,WORK,read,write,sha
from evaluate import RemotePolicy,World,trial

class UpdatedWorker(RemotePolicy):
    def __init__(self,python,checkpoint):
        self.process=subprocess.Popen([str(python),str(ROOT/'src/worker.py'),str(checkpoint)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)

def run(args):
    for mode in args.modes:
        if (args.out/mode).exists() or (args.out/(mode+'.json')).exists():
            raise FileExistsError(f'Existing {mode} rollouts in {args.out}. Choose a new output directory.')
    spec=read(ROOT/'학습구역.json')
    if args.split=='fresh':
        assert sha(ROOT/'봉인_출발점.json')==spec['holdout_sha256']
        lock=read(ROOT/'모델봉인.json')
        assert sha(S5/'checkpoints/student-4.pt')==lock['before'] and sha(ROOT/'weights/recovery.pt')==lock['after']
        from freeze import artifacts
        assert all(sha(path)==lock[key] for key,path in artifacts().items())
        packaged=ROOT/'src/policy.py'
        assert not packaged.exists() or sha(packaged)==lock['baseline_policy']
        cases=read(ROOT/'봉인_출발점.json')['cases']
    else:cases=spec[args.split+'_cases']
    w=World('castle',register=False)
    try:
        for mode in args.modes:
            ckpt=S5/'checkpoints/student-4.pt' if mode=='before' else ROOT/'weights/recovery.pt'
            cls=RemotePolicy if mode=='before' else UpdatedWorker
            with contextlib.closing(cls(args.torch_python,ckpt)) as policy:
                result=[]
                for case in cases:
                    folder=args.out/mode/case['id']
                    r=trial(w,policy,case,4,folder);result.append(r)
                    if len(result)%15==0:print(mode,len(result),sum(x['success'] for x in result),flush=True)
                write(args.out/(mode+'.json'),result)
    finally:w.close()
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('split',choices=['train','dev','fresh']);p.add_argument('out',type=__import__('pathlib').Path);p.add_argument('modes',nargs='+',choices=['before','after'])
    p.add_argument('--torch-python',default=str(ROOT.parent.parent/'work/fire-models/env/bin/python'))
    run(p.parse_args())
