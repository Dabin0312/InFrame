"""One goal and live camera samples in; only the real mock adapter's twist leaves."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/InFrame_7단계/src'))
from bridge import Decision, MockSport, MotionGuard, PERIOD
from multigoal import MultiGoalH4

def serve():
    policy=None
    embeddings={}
    for line in sys.stdin:
        req=json.loads(line)
        if req['type']=='start':
            goal=req['goal']
            if policy is None:
                policy=MultiGoalH4(goal)
                embeddings[goal]=policy.embedding
            elif goal not in embeddings:
                from multigoal import encode_goal
                embeddings[goal]=encode_goal(goal)
            policy.embedding=embeddings[goal]
            policy.reset()
            clock=[0.]
            seq=0
            sport=MockSport()
            guard=MotionGuard(sport,clock=lambda:clock[0])
            guard.start()
            result={'ready':True}
        elif req['type']=='frame':
            with Image.open(io.BytesIO(base64.b64decode(req['png'],validate=True))) as image:
                rgb=np.array(image.convert('RGB'))
            raw=policy.act(rgb)
            guard.accept(Decision(seq,clock[0],raw))
            action=policy.actions[-1]
            if guard.reason!=('goal_stop' if action==3 else None):
                raise ValueError(f'Unexpected guard state {guard.reason}')
            seq+=1
            clock[0]=seq*PERIOD
            result=dict(raw=raw,action=action,sent=sport.twist,rgb=hashlib.sha256(rgb.tobytes()).hexdigest())
        elif req['type']=='end':
            guard.stop('step_limit')
            if not guard.stop_confirmed or sport.twist!=(0.,0.,0.):
                raise RuntimeError('Mock adapter still moving')
            result={'stopReason':guard.reason}
        else:
            raise ValueError('Unknown request')
        print(json.dumps(result),flush=True)

if __name__=='__main__':serve()
