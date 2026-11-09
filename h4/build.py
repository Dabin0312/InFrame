"""Compose frozen visual encoders and trained action head into a single RGB policy graph."""
import argparse,json,hashlib
from pathlib import Path
import onnx
from onnx import compose
def build(repo,fit):
    old=onnx.load(repo/'demo/policy.onnx');encoder=onnx.load(repo/'spatial/extinguisher.onnx');decision=onnx.load(fit/'decision.onnx')
    # onnx.compose requires matching IR versions even when both models use the same ONNX opset.
    for m in [old,encoder,decision]:m.ir_version=max(old.ir_version,encoder.ir_version,decision.ir_version)
    encoder=compose.add_prefix(encoder,'semantic/')
    merged=compose.merge_models(old,encoder,io_map=[])
    final=compose.merge_models(merged,decision,io_map=[('semantic/boxes','boxes'),('base','base'),('dock','dock')],prefix2='action/',outputs=['base','corr','dock','action/next_memory','action/policy_stop','action/stop_logit','action/observation'])
    onnx.checker.check_model(final);out=repo/'h4/policy.onnx';onnx.save(final,out)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    lock={'model':sha(out),'original':sha(repo/'demo/policy.onnx'),'semantic_encoder':sha(repo/'spatial/extinguisher.onnx'),'split':sha(repo/'h4/split.json'),'labels':sha(repo/'h4/annotations.json'),'fit':json.loads((fit/'fit.json').read_text()),'operating_point_logit':0}
    (repo/'h4/frozen.json').write_text(json.dumps(lock,indent=2)+'\n');print(lock)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('repo',type=Path);p.add_argument('fit',type=Path);a=p.parse_args();build(a.repo,a.fit)
