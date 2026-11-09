from argparse import ArgumentParser
import torch, onnx, numpy as np
from onnx import numpy_helper as nh, helper
from ultralytics import YOLOE
from pathlib import Path
parser=ArgumentParser(description='Export the selected InFrame detector with Ultralytics 8.3.200')
parser.add_argument('--weights',default='yoloe-11s-seg.pt')
parser.add_argument('--output',default='extinguisher.onnx')
parser.add_argument('--indoor',action='store_true',help='Export chair and trash can class channels')
args=parser.parse_args()
torch.set_num_threads(3)
m=YOLOE(args.weights); m.model.eval()
classes=['chair','trash can'] if args.indoor else ['fire extinguisher']
m.set_classes(classes,m.get_text_pe(classes))
m.model.fuse()
head=m.model.model[-1];head.export=True;head.format='onnx'
class Detector(torch.nn.Module):
    def __init__(self,model):
        super().__init__(); self.net=model
    def forward(self,x):
        return self.net(x)[0][:,:4+len(classes),:]
net=Detector(m.model).eval()
x=torch.zeros(1,3,320,320); print(net(x).shape,flush=True)
torch.onnx.export(net,x,'detector-f32.onnx',input_names=['rgb'],output_names=['boxes'],opset_version=17,dynamo=False)
p=onnx.load('detector-f32.onnx')
# Keep float32 arithmetic, store convolution weights as per-channel affine int8.
prefix=[]
for w in list(p.graph.initializer):
    a=nh.to_array(w)
    if a.ndim!=4 or a.dtype!=np.float32 or a.size<128: continue
    s=np.maximum(np.max(np.abs(a),axis=(1,2,3))/127,1e-12).astype('float32')
    q=np.rint(a/s[:,None,None,None]).clip(-127,127).astype('int8'); n=w.name
    p.graph.initializer.remove(w)
    p.graph.initializer.extend([nh.from_array(q,n+'.q'),nh.from_array(s,n+'.s'),nh.from_array(np.zeros_like(s,dtype='int8'),n+'.z')])
    prefix.append(helper.make_node('DequantizeLinear',[n+'.q',n+'.s',n+'.z'],[n],axis=0))
old=list(p.graph.node);del p.graph.node[:];p.graph.node.extend(prefix+old)
onnx.checker.check_model(p);onnx.save(p,args.output)
