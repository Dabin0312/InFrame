"""Export YOLOE-11s + MobileCLIP-B(LT) for ONNX Runtime Web.
Run in a directory containing yoloe-11s-seg.pt and mobileclip_blt.ts.
Use Ultralytics 8.3.200 with its CLIP tokenizer dependency, torch 2.8 and ONNX.
"""
from pathlib import Path
import torch, onnx, numpy as np
from onnx import numpy_helper as nh,helper
from ultralytics import YOLOE
import clip
import argparse, gzip, json, hashlib, shutil
torch.set_num_threads(3)
args=argparse.ArgumentParser(description=__doc__)
args.add_argument('--output',required=True,type=Path)
args.add_argument('--bpe',required=True,type=Path,help='Path to CLIP bpe_simple_vocab_16e6.txt.gz')
root=args.parse_args();bpe=root.bpe;root=root.output;root.mkdir(parents=True,exist_ok=True)
encoder=torch.jit.load('mobileclip_blt.ts',map_location='cpu').eval()
encoder=torch.jit.freeze(encoder)
tokens=clip.tokenize(['wet floor sign'])
def export(mod,ins,names,out):
 file=root/(out+'.onnx')
 torch.onnx.export(mod,ins,str(file),input_names=names,output_names=['embedding'] if out=='text' else ['boxes','proto'],opset_version=17,dynamo=False)
 graph=onnx.load(file);prefix=[]
 # TorchScript stores frozen parameters as Constant nodes; expose them as initializers.
 for node in list(graph.graph.node):
  if node.op_type=='Constant' and node.attribute[0].type==onnx.AttributeProto.TENSOR:
   t=node.attribute[0].t;a=nh.to_array(t)
   if a.dtype==np.float32 and a.size>=1024:
    graph.graph.initializer.append(nh.from_array(a,node.output[0]));graph.graph.node.remove(node)
 for w in list(graph.graph.initializer):
  a=nh.to_array(w)
  if a.dtype!=np.float32 or a.ndim<2 or a.size<512 or not np.isfinite(a).all():continue
  axis=0 if a.ndim>2 or a.shape[0]>10000 else 1
  other=tuple(i for i in range(a.ndim) if i!=axis)
  scale=np.maximum(abs(a).max(axis=other,keepdims=True)/127,1e-10).astype(np.float32);q=np.rint(a/scale).clip(-127,127).astype(np.int8);n=w.name
  graph.graph.initializer.remove(w);sc=scale.ravel()
  graph.graph.initializer.extend([nh.from_array(q,n+'_q'),nh.from_array(sc,n+'_scale'),nh.from_array(np.zeros_like(sc,dtype='int8'),n+'_zero')])
  prefix.append(helper.make_node('DequantizeLinear',[n+'_q',n+'_scale',n+'_zero'],[n],axis=axis))
 old=list(graph.graph.node);del graph.graph.node[:];graph.graph.node.extend(prefix+old)
 onnx.checker.check_model(graph);onnx.save(graph,root/(out+'-web.onnx'))
 print(out, (root/(out+'-web.onnx')).stat().st_size,flush=True)
class Detect(torch.nn.Module):
 def __init__(self):
  super().__init__();self.net=YOLOE('yoloe-11s-seg.pt').model.eval();head=self.net.model[-1];head.nc=1;head.export=True;head.format='onnx'
 def forward(self,rgb,embedding):
  return self.net.predict(rgb,tpe=embedding.reshape(1,1,512))
net=Detect().eval()
with torch.no_grad():
 emb=encoder(tokens);image=torch.zeros(1,3,416,416);net(image,emb)
 export(net,(image,emb),['rgb','embedding'],'vision');export(encoder,(tokens,),['tokens'],'text')
p=s=root
model=(p/'text-web.onnx').read_bytes()
parts=[model[i:i+16*1024**2] for i in range(0,len(model),16*1024**2)]
for i,part in enumerate(parts): (s/f'prompt-text-{i}.bin').write_bytes(part)
shutil.copy(p/'vision-web.onnx',s/'prompt-vision.onnx')
bpe=gzip.decompress(bpe.read_bytes()).decode().splitlines()[1:49152-256-2+1]
(s/'prompt-merges.txt').write_text('\n'.join(bpe))
(s/'prompt-model.json').write_text(json.dumps(dict(text=[f'prompt-text-{i}.bin' for i in range(len(parts))],size=len(model),sha256=hashlib.sha256(model).hexdigest(),vision='prompt-vision.onnx'),indent=2)+'\n')
