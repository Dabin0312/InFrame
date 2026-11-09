"""Export the three trained heads from the v0.7.0 Go2 mock package to ONNX."""
import argparse
import json
import sys
from pathlib import Path
import torch

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('package', type=Path, help='extracted go2-mock directory')
p.add_argument('out', type=Path)
args = p.parse_args()
sys.path.insert(0, str(args.package.resolve() / 'src'))
from devices import verify_policy, FROZEN
verify_policy()
sys.path.insert(0, str(FROZEN))
from recovery_policy import RecoveryStudent

class Heads(torch.nn.Module):
    def __init__(self, student):
        super().__init__()
        self.base = student.base
        self.correction = student.correction
        self.dock = student.dock

    def forward(self, rgb):
        goal = torch.zeros(1, dtype=torch.long)
        return self.base(rgb, goal), self.correction(rgb[:, -1]), self.dock(rgb[:, -1])

student = RecoveryStudent(FROZEN / 'recovery.pt')
args.out.mkdir(parents=True, exist_ok=True)
torch.onnx.export(Heads(student).eval(), torch.zeros((1,4,60,80,3),dtype=torch.uint8),
                  str(args.out/'policy.onnx'), input_names=['rgb'],output_names=['base','corr','dock'],
                  opset_version=17, dynamo=False)
(args.out/'policy.json').write_text(json.dumps(student.config,indent=2)+'\n')
