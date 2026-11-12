"""Local CPU inference with the same text, proposal and H4 ONNX weights as Castle."""
from collections import deque
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np
import onnxruntime as ort

from bridge import PERIOD

PROJECT = Path(__file__).resolve().parents[3]
SPATIAL = PROJECT/'spatial'
TWISTS = ((0.22/PERIOD, 0, 0), (0, np.pi/12/PERIOD, 0),
          (0, -np.pi/12/PERIOD, 0), (0, 0, 1))


def visual_change(a,b):
    residual=0.
    for ch in range(3):
        old=a[:,:,ch].ravel()
        new=b[:,:,ch].ravel()
        count=np.bincount(old,minlength=256)
        means=np.bincount(old,weights=new,minlength=256)/np.maximum(1,count)
        residual+=np.maximum(0,np.abs(new-means[old])-1).sum()
    return residual/a.size


def session(source):
    options=ort.SessionOptions()
    options.intra_op_num_threads=3
    options.inter_op_num_threads=1
    return ort.InferenceSession(source,sess_options=options,providers=['CPUExecutionProvider'])


def encode_goal(goal):
    # Share the browser's exact CLIP BPE vocabulary, aliases and token IDs.
    script="""import fs from 'node:fs';
    import {resolveGoal,tokenizer} from './spatial/prompt.mjs';
    const g=await resolveGoal(process.argv[1]);
    console.log(JSON.stringify(Array.from(tokenizer(fs.readFileSync('spatial/prompt-merges.txt','utf8'))(g.prompt))));"""
    ids=json.loads(subprocess.check_output(['node','--input-type=module','-e',script,'--',goal],cwd=PROJECT))
    manifest=json.loads((SPATIAL/'prompt-model.json').read_text())
    encoder=session(b''.join((SPATIAL/file).read_bytes() for file in manifest['text']))
    return encoder.run(['embedding'],{'tokens':np.array([ids],np.int32)})[0]


class MultiGoalH4:
    def __init__(self, goal):
        self.embedding=encode_goal(goal)
        self.detector=session(str(SPATIAL/'prompt-vision.onnx'))
        self.policy=session(str(PROJECT/'h4nav/transfer-h4.onnx'))
        self.reset()
        self.act(np.zeros((120,160,3),np.uint8))
        self.reset()

    def reset(self):
        self.frames=deque(maxlen=4)
        self.proposals=deque(maxlen=4)
        self.actions=[]
        self.memory=np.zeros((1,1,44),np.float32)
        self.search=np.zeros((1,9),np.float32)
        self.escape=np.zeros((1,20),np.float32)

    def proposal(self,rgb):
        # 160×120 -> 416×312 plus 52 pixels of padding above and below.
        letter=np.full((416,416,3),114,np.uint8)
        letter[52:364]=cv2.resize(rgb,(416,312),interpolation=cv2.INTER_LINEAR_EXACT)
        image=np.ascontiguousarray(letter.transpose(2,0,1)[None],dtype=np.float32)/255
        boxes=self.detector.run(['boxes'],{'rgb':image,'embedding':self.embedding})[0][0]
        # H4 consumes only the highest-scoring eligible box. NMS preserves it.
        for i in np.argsort(-boxes[4],kind='stable'):
            x,y,w,h,score=map(float,boxes[:5,i])
            if not np.isfinite(score) or score<.25: break
            x0,x1=max(0,(x-w/2)/2.6),min(160,(x+w/2)/2.6)
            y0,y1=max(0,(y-h/2-52)/2.6),min(120,(y+h/2-52)/2.6)
            if x1-x0>=5 and y1-y0>=6:
                return [score,(x1+x0)/320,(y1+y0)/240,(x1-x0)/160,(y1-y0)/120]
        return [0.]*5

    def act(self,rgb):
        if rgb.shape!=(120,160,3) or rgb.dtype!=np.uint8:
            raise ValueError('Expected uint8 160 × 120 RGB')
        small=cv2.resize(rgb,(80,60),interpolation=cv2.INTER_AREA)
        box=self.proposal(rgb)
        for _ in range(4 if not self.frames else 1):
            self.frames.append(small);self.proposals.append(box)
        a,b,c,d=self.frames
        last=np.zeros((1,4),np.float32)
        last[0,self.actions[-1]+1 if self.actions else 0]=1
        inputs=dict(camera=rgb[None],rgb=np.stack(self.frames)[None],goal_embedding=self.embedding,
                    rgb_goal_proposals=np.array([self.proposals],np.float32),previous_action=last,
                    memory=self.memory,search_memory=self.search,escape_memory=self.escape,
                    visual_change=np.array([[visual_change(c,d),visual_change(b,d),
                                            visual_change(a,d),visual_change(a,c)]],np.float32))
        logits,self.memory,self.search,self.escape=self.policy.run(
            ['action_logits','next_memory','next_search_memory','next_escape_memory'],inputs)
        if not np.isfinite(logits).all():raise ValueError('Non-finite H4 logits')
        action=int(np.argmax(logits))
        self.actions.append(action)
        return TWISTS[action]
