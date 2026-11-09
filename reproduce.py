"""Run the numbered InFrame experiments from the extracted release directory."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / 'outputs'
S2 = OUTPUTS / 'InFrame_Fire_2단계'
S2_PLUS = OUTPUTS / 'InFrame_Fire_2단계_개선'
S3 = OUTPUTS / 'InFrame_Fire_3단계'
S4 = OUTPUTS / 'InFrame_4단계'
S5 = OUTPUTS / 'InFrame_5단계'
S6 = OUTPUTS / 'InFrame_6단계_정책개선'
S7 = OUTPUTS / 'InFrame_7단계'
STAGES = ROOT / 'stages'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def run(executable, script, *args):
    command = [str(item) for item in (executable, script, *args)]
    print('→', ' '.join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def run_stage(number, out, sim, model):
    if number == 0:
        print((STAGES/'00-task/README.md').read_text(encoding='utf-8'))
        return
    if number == 1:
        run(sim, STAGES/'01-simulator/run.py', '--out', out/'room')
        ref = STAGES/'02-visual-slam/reference'
        recount = out/'tracking.json'
        run(model, STAGES/'02-visual-slam/slam_io.py', 'report', ref/'TrackingStatus.csv', recount)
        if read(recount) != read(ref/'tracking_report.json'):
            raise RuntimeError('SLAM tracking recount differs from reference')
        return
    if number == 2:
        fire = ROOT/'data/fire'
        controls = out/'controls'
        mapped = out/'map'
        run(model,S2/'src/controls.py',fire,controls)
        run(model,S2/'src/geometry.py',fire,S2/'masks',mapped,'--controls',controls)
        run(model,S2/'src/evaluate.py',mapped,S2/'masks',fire)
        # Re-score the revised system's recorded predictions against human-marked body points.
        scored = out/'corrected'
        scored.mkdir()
        for item in ('links.json','audit_baseline.json'):
            shutil.copy2(S2_PLUS/item,scored/item)
        shutil.copytree(S2_PLUS/'masks',scored/'masks')
        run(model,S2_PLUS/'src/score.py',scored,S2_PLUS/'audit_masks')
        if read(scored/'comparison.json')!=read(S2_PLUS/'comparison.json'):
            raise RuntimeError('Corrected photo scores differ from release')
        return
    if number == 3:
        site = out/S3.name
        shutil.copytree(S3,site)
        ref = out/S2.name
        ref.mkdir()
        for item in ('scene.npz','map.json'):
            shutil.copy2(S2/item,ref/item)
        run(sim,site/'src/simulate.py',site)
        run(model,site/'src/check.py',site)
        return
    if number == 4:
        # The historical verifier writes its report next to the episodes.
        # Keep the release pristine by running it inside a scratch copy.
        clone = out/S4.name
        shutil.copytree(S4,clone)
        run(sim,clone/'src/dataset.py')
        run(sim,clone/'src/verify.py')
        return
    if number == 5:
        target = out/'rollouts'
        run(sim,S5/'src/evaluate.py','--torch-python',model,'--out',target)
        for history in (1,4):
            files=list((target/f'h{history}').glob('*/result.json'))
            if len(files)!=60:
                raise RuntimeError('Missing validation rollouts')
            print(f'{history} RGB ·',dict(Counter(read(f)['reason'] for f in files)))
        return
    if number == 6:
        target=out/'before-after'
        run(sim,S6/'src/run.py','fresh',target,'before','after','--torch-python',model)
        for name in ('before','after'):
            rows=read(target/(name+'.json'))
            print(name, sum(r['success'] for r in rows),'/',len(rows))
        return
    run(model,S7/'src/runtime.py','--backend','mock','--log',out/'mock.json')
    run(model,S7/'src/safety_check.py','--out',out/'safety.json')
    run(sim,S7/'src/sim_check.py','--torch-python',model,'--out',out/'habitat')
    run(sim,S7/'src/audit.py',out/'habitat','--out',out/'audit.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=[*map(str,range(8)),'all'])
    parser.add_argument('--sim-python',default=os.environ.get('SIM_PY',sys.executable))
    parser.add_argument('--model-python',default=os.environ.get('MODEL_PY',sys.executable))
    args=parser.parse_args()
    if args.stage in ('all','2','3','4','5','6','7') and not (S7/'frozen/recovery.pt').exists():
        parser.error('Extract inframe-stages-0-7.zip and run reproduce.py inside its InFrame directory.')
    dest=ROOT/'work/runs'
    dest.mkdir(parents=True,exist_ok=True)
    for n in (range(8) if args.stage=='all' else [int(args.stage)]):
        run_dir=Path(tempfile.mkdtemp(prefix=f'{n:02d}-',dir=dest))
        print(f'[{n}/7] {run_dir}',flush=True)
        run_stage(n,run_dir,args.sim_python,args.model_python)
        print(f'[{n}/7] completed',flush=True)


if __name__=='__main__':
    main()
