"""Record implementation and weights selected on training-area development runs before evaluation."""
import argparse
from common import ROOT,S5,WORK,read,write,sha
from assess import summarize_pair

def artifacts():
    return {'before':S5/'checkpoints/student-4.pt','after':ROOT/'weights/recovery.pt',
            'controller':ROOT/'src/recovery_policy.py','visual_motion':ROOT/'src/visual_motion.py',
            'baseline_policy':S5/'src/policy.py','worker':ROOT/'src/worker.py','evaluator':S5/'src/evaluate.py',
            'starts':ROOT/'봉인_출발점.json'}

def main(name):
    metrics,_=summarize_pair(WORK/'dev',after_folder=WORK/name)
    lock={k:sha(p) for k,p in artifacts().items()}
    lock.update(development_run=name,development_metrics=metrics,selection_basis='Training-area development trials only; model weights and code frozen before running either policy on the fresh split.')
    destination=ROOT/'모델봉인.json'
    if destination.exists():assert read(destination)==lock,'A different candidate has already been sealed'
    else:write(destination,lock)
    print(metrics,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('dev_run');main(p.parse_args().dev_run)
