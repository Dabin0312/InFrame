"""Exercise the normal control boundary with injected commands and wall-clock camera outages."""
import argparse
import json
import math
from pathlib import Path
import threading
import time

import numpy as np
from bridge import Decision, MotionGuard, MockSport, FRAME_TTL
from devices import ROOT, FrontCamera, LocalPolicy, MockVideo
from runtime import run_session, RecordingCamera


def limit_and_fault_cases():
    cases=[]
    def record(label, exercise, sport=None):
        now=[100.]
        events=[]
        guard=MotionGuard(sport if sport is not None else MockSport(),lambda:now[0],events.append)
        guard.start()
        exercise(guard,now)
        cases.append(dict(case=label,reason=guard.reason,stop_confirmed=guard.stop_confirmed,events=events))

    for action,expected in [((2.5,4.,0),(.4,0.,1.)),((-.5,-4.,0),(0.,0.,-1.)),
                            ((.12,-.32,0),(.12,0.,-.32))]:
        def bounds(g,t):
            g.accept(Decision(0,t[0],action))
            assert g.sport.twist==expected and not g.reason
            g.stop('case_end')
        record('command '+str(action),bounds)

    def terminal(g,t):
        g.accept(Decision(0,t[0],(.4,1.,1)))
        assert g.reason=='goal_stop' and g.sport.twist==(0.,0.,0.)
        g.accept(Decision(1,t[0]+.1,(.4,0,0)))
        assert g.sport.twist==(0.,0.,0.)
    record('STOP priority and late input',terminal)

    for payload in [(math.nan,0.,0),(.1,math.inf,0),(.1,.2,9)]:
        def invalid(g,t):
            g.accept(Decision(0,t[0],(.25,0,0)))
            t[0]+=.25
            g.accept(Decision(1,t[0],payload))
            assert g.reason=='invalid_action' and g.sport.twist==(0.,0.,0.)
        record('invalid '+str(payload),invalid)

    for label,stamp,seq in [('duplicated sequence',100.25,0),('old capture',99.9,1),('future capture',100.4,1)]:
        def stale(g,t):
            g.accept(Decision(0,t[0],(.3,0,0)))
            t[0]=100.25
            g.accept(Decision(seq,stamp,(.4,0,0)))
            assert g.reason=='invalid_or_stale_frame' and g.sport.twist==(0.,0.,0.)
        record(label,stale)

    def boundary(g,t):
        g.accept(Decision(0,t[0],(.3,.2,0)))
        t[0]=100.499999
        g.tick()
        assert g.reason is None
        t[0]=100.5
        g.accept(Decision(1,t[0],(.4,0,0)))
        assert g.reason=='frame_timeout' and g.sport.twist==(0.,0.,0.)
    record('timeout at exact boundary and late decision',boundary)

    class Unreliable(MockSport):
        def __init__(self, persistent=False):
            super().__init__()
            self.stops=0
            self.persistent=persistent
        def Move(self,vx,vy,vyaw):
            return 17
        def StopMove(self):
            self.stops+=1
            return 0 if self.stops==1 or (self.stops>2 and not self.persistent) else 11
    for persistent in (False,True):
        def rpc(g,t):
            g.accept(Decision(0,t[0],(.4,.3,0)))
            assert g.reason=='move_failed' and g.stop_confirmed!=persistent
        record('SDK Move error; stop '+('unconfirmed' if persistent else 'retry'),rpc,Unreliable(persistent))
    return cases


def realtime_one(fault, model, frames):
    # All commands before fault injection come from the actual frozen policy.
    events=[]
    sport=MockSport()
    guard=MotionGuard(sport,emit=events.append)
    release=threading.Event()
    resumed=threading.Event()
    injected=[]
    frame_number=0
    def inject():
        if not injected:
            injected.append(time.monotonic())
    def rgb():
        nonlocal frame_number
        frame=frames[frame_number]
        frame_number+=1
        return frame
    mock=MockVideo(rgb)
    class FaultVideo:
        def GetImageSample(self):
            if sport.twist[0]>.2 and fault!='policy_block':
                inject()
                if fault=='camera_block':
                    release.wait(3.)
                    resumed.set()
                elif fault=='camera_error':
                    return 29,b''
                elif fault=='corrupt_image':
                    return 0,b'bad camera bytes'
            return mock.GetImageSample()
    class StallPolicy:
        def act(self,image):
            if sport.twist[0]>.2 and fault=='policy_block':
                inject()
                release.wait(3.)
                resumed.set()
            return model.act(image)
    model.model.reset()
    try:
        state=run_session(FrontCamera(FaultVideo()),StallPolicy(),guard)
        assert len(injected)==1 and state['stop_confirmed']
        last_move=next(e for e in reversed(events) if e['rpc']=='Move')
        terminal=events[-1]
        assert terminal['rpc']=='StopMove' and terminal['ok'] and sport.twist==(0.,0.,0.)
        assert last_move['args'][0]>.2
        delay=terminal['t']-last_move['captured']
        if fault.endswith('block'):
            assert state['reason']=='frame_timeout' and FRAME_TTL-.00001<=delay<FRAME_TTL+.10
        else:
            assert state['reason']=='camera_error' and delay<FRAME_TTL, (fault,state,delay)
        original_count=len(events)
    finally:
        release.set()
    if fault.endswith('block'):
        assert resumed.wait(.5)
        time.sleep(.03)
    assert len(events)==original_count
    return dict(fault=fault,delay_from_last_rgb_ms=1000*delay,
                from_missing_call_ms=1000*(terminal['t']-injected[0]),
                last_v=last_move['args'][0],last_yaw=last_move['args'][2],events=events,**state)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    checks=limit_and_fault_cases()
    model=LocalPolicy()
    frames=RecordingCamera(ROOT/'results/habitat/media/FRESH-015-rgb.npz').frames
    live=[]
    for fault in ['camera_block']*10+['policy_block','camera_error','corrupt_image']:
        result=realtime_one(fault,model,frames)
        live.append(result)
        print(fault,round(result['delay_from_last_rgb_ms'],2),'ms',flush=True)
    measurements=[r['delay_from_last_rgb_ms'] for r in live if r['fault']=='camera_block']
    result=dict(logic_cases=len(checks),logic=checks,wall_clock=live,
                camera_silence_ms=dict(n=len(measurements),min=min(measurements),
                                       median=float(np.median(measurements)),max=max(measurements)))
    with args.out.open('x') as fp:
        json.dump(result,fp,indent=2,ensure_ascii=False,allow_nan=False)

if __name__=='__main__':
    main()
