"""Replace only the six RGB difference reductions in the frozen multi-goal H4."""
from pathlib import Path
from hashlib import sha256
import onnx
from onnx import helper, numpy_helper, TensorProto
import numpy as np

root = Path(__file__).resolve().parent
source = root / 'escape-h4.onnx'
model = onnx.load(source)
graph = model.graph
# Columns: current vs t-1, t-2, t-3; t-1 vs t-3.
uses = {
    'prior/old/old/h4//parent/ReduceMean': [0, 1, 2],
    'prior/old/old/h4//ReduceMean_1': 3,
    'prior/old/old/h4//ReduceMean': 0,
    'prior/old/pursuit//ReduceMean': 0,
    'prior/pursuit//ReduceMean': 0,
    'escape//ReduceMean': 0,
}
graph.input.append(helper.make_tensor_value_info('visual_change', TensorProto.FLOAT, [1, 4]))
replaced = set()
for node in graph.node:
    if node.name in uses:
        assert node.op_type == 'ReduceMean'
        name = node.name + '/lag'
        graph.initializer.append(numpy_helper.from_array(np.array(uses[node.name], dtype=np.int64), name))
        replaced.add(node.name)
        node.CopyFrom(helper.make_node('Gather', ['visual_change', name], list(node.output), name=node.name, axis=1))
assert replaced == uses.keys()
# Drop the now-dead differencing operations, retaining all learned weights.
needed = {v.name for v in graph.output}
retained = []
for n in reversed(graph.node):
    if needed.intersection(n.output):
        retained.append(n)
        needed.update(n.input)
del graph.node[:]
graph.node.extend(reversed(retained))
weights = [v for v in graph.initializer if v.name in needed]
del graph.initializer[:]
graph.initializer.extend(weights)
onnx.checker.check_model(model)
out = root / 'transfer-h4.onnx'
onnx.save(model, out)
print(out.name, sha256(out.read_bytes()).hexdigest())
