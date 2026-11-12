"""4 Hz policy producer; an independent supervisor owns every motion command."""
import argparse
import json
import queue
import signal
import threading
import time
from pathlib import Path

import numpy as np
from bridge import Decision, MotionGuard, MockSport, PERIOD, POLL, FRAME_TTL, MAX_FORWARD, MAX_YAW
from devices import FrontCamera, LocalPolicy, MockVideo, ROOT, unitree_clients


def run_session(camera, policy, guard, cancelled=None):
    cancelled = cancelled if cancelled is not None else threading.Event()
    finished = threading.Event()
    outputs = queue.Queue(maxsize=1)

    def produce():
        sequence = 0
        while not finished.is_set():
            cycle = time.monotonic()
            try:
                captured, rgb = camera.read()
            except Exception as exc:
                packet = ('camera_error', repr(exc))
            else:
                if finished.is_set():
                    return
                try:
                    decision = Decision(sequence, captured, tuple(policy.act(rgb)))
                    packet = ('decision',decision)
                except Exception as exc:
                    packet = ('policy_error',repr(exc))
            if finished.is_set():
                return
            try:
                outputs.put(packet,timeout=POLL)
            except queue.Full:
                # An old decision is still waiting. Never enqueue a backlog of movements.
                return
            if packet[0]!='decision':
                return
            sequence += 1
            finished.wait(max(0., PERIOD-(time.monotonic()-cycle)))

    worker = threading.Thread(target=produce,name='rgb-policy',daemon=True)
    detail = None
    try:
        guard.start()
        if not guard.reason and not cancelled.is_set():
            worker.start()
        while not guard.reason and not cancelled.is_set():
            guard.tick()
            if guard.reason:
                break
            until_expiry = max(0., guard.last_capture+FRAME_TTL-guard.clock())
            try:
                tag,value = outputs.get(timeout=min(POLL,until_expiry))
            except queue.Empty:
                continue
            if cancelled.is_set():
                break
            if tag=='decision':
                guard.accept(value)
            else:
                detail = value
                guard.stop(tag)
    finally:
        finished.set()
        if not guard.reason:
            guard.stop('session_closed')
        if worker.is_alive():
            worker.join(timeout=POLL)
    return dict(reason=guard.reason,stop_confirmed=guard.stop_confirmed,detail=detail)


class RecordingCamera:
    def __init__(self, path):
        with np.load(path) as recording:
            self.frames = recording['rgb']
        self.index = 0

    def rgb(self):
        if self.index >= len(self.frames):
            raise EOFError('End of camera recording')
        rgb = self.frames[self.index]
        self.index += 1
        return rgb


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--backend',choices=['mock','go2'],default='mock')
    p.add_argument('--interface')
    p.add_argument('--forward-limit',type=float,default=MAX_FORWARD)
    p.add_argument('--yaw-limit',type=float,default=MAX_YAW)
    p.add_argument('--log',type=Path)
    p.add_argument('--goal', help='Run the multi-goal H4 using this text prompt')
    p.add_argument('--recording', type=Path, help='NPZ containing a uint8 rgb sequence')
    args = p.parse_args()
    if args.goal and args.backend == 'mock' and not args.recording:
        p.error('Provide the Castle RGB recording for this goal with --recording')
    if args.backend=='go2' and not args.interface:
        p.error('Specify the DDS network interface for go2')
    if not (0<args.forward_limit<=MAX_FORWARD and 0<args.yaw_limit<=MAX_YAW):
        p.error('Limits must be within the project envelope')
    cancelled = threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig, lambda *_: cancelled.set())
    if args.goal:
        from multigoal import MultiGoalH4
        model = MultiGoalH4(args.goal)
    else:
        model = LocalPolicy()
    if args.backend=='go2':
        sport,video = unitree_clients(args.interface)
    else:
        sport = MockSport()
        video = MockVideo(RecordingCamera(args.recording or ROOT/'results/habitat/media/FRESH-015-rgb.npz').rgb)
    events = []
    guard = MotionGuard(sport,emit=events.append,forward=args.forward_limit,yaw=args.yaw_limit)
    result = run_session(FrontCamera(video, size=(160,120) if args.goal else (192,144)),model,guard,cancelled)
    if args.goal:
        result.update(goal=args.goal, actions=model.actions)
    if args.log:
        with args.log.open('x',encoding='utf-8') as fp:
            json.dump(dict(result=result,events=events),fp,ensure_ascii=False,indent=2)
    print(json.dumps(dict(backend=args.backend,calls=len(events),**result),ensure_ascii=False))
    if not result['stop_confirmed'] or result['reason']!='goal_stop':
        raise SystemExit(1)

if __name__=='__main__':
    main()
