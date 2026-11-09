"""One command owner. The worker only supplies timestamped RGB decisions."""
from dataclasses import dataclass
import math
import time

FRAME_TTL = 0.50
POLL = 0.02
PERIOD = 0.25
MISSION_LIMIT = 150.0
MAX_FORWARD = 0.4
MAX_YAW = 1.0


@dataclass(frozen=True)
class Decision:
    sequence: int
    captured: float
    action: tuple


class MotionGuard:
    """Run start, tick, accept and stop on the same supervisor thread."""
    def __init__(self, sport, clock=time.monotonic, emit=None, forward=MAX_FORWARD, yaw=MAX_YAW):
        if not (0 < forward <= MAX_FORWARD and 0 < yaw <= MAX_YAW):
            raise ValueError('Speed limits must be positive and within the project limits')
        self.sport, self.clock = sport, clock
        self.emit = emit if emit is not None else (lambda event: None)
        self.forward, self.yaw = forward, yaw
        self.started = None
        self.last_capture = None
        self.sequence = -1
        self.reason = None
        self.stop_confirmed = False

    def rpc(self, method, args, reason, **context):
        issued = self.clock()
        try:
            code = getattr(self.sport, method)(*args)
            ok = type(code) is int and code == 0
            error = None if ok else 'SDK return '+str(code)
        except Exception as exc:
            ok = False
            error = repr(exc)
        self.emit(dict(t=issued, completed=self.clock(), rpc=method, args=list(args),
                       reason=reason, ok=ok, error=error, **context))
        return ok

    def start(self):
        if self.started is not None:
            raise RuntimeError('Create a new session for a new mission')
        self.started = self.clock()
        self.last_capture = self.started
        if not self.rpc('StopMove', (), 'startup'):
            self.stop('startup_stop_failed')

    def stop(self, reason):
        if not self.reason:
            self.reason = reason
        if not self.stop_confirmed:
            for attempt in range(1,4):
                if self.rpc('StopMove', (), self.reason, attempt=attempt):
                    self.stop_confirmed = True
                    break

    def tick(self):
        if self.started is None:
            raise RuntimeError('Session not started')
        if self.reason:
            return
        now = self.clock()
        if now-self.started >= MISSION_LIMIT:
            self.stop('mission_timeout')
        elif now-self.last_capture >= FRAME_TTL:
            self.stop('frame_timeout')

    def accept(self, decision):
        self.tick()
        if self.reason:
            return
        now = self.clock()
        stamp = decision.captured
        if (not math.isfinite(stamp) or stamp>now or now-stamp>=FRAME_TTL
                or stamp<self.last_capture or decision.sequence<=self.sequence
                or (self.sequence>=0 and stamp==self.last_capture)):
            self.stop('invalid_or_stale_frame')
            return
        try:
            raw_v, raw_w, stop = decision.action
            v, w = float(raw_v), float(raw_w)
            if not (math.isfinite(v) and math.isfinite(w) and stop in (0,1)):
                raise ValueError('Invalid action')
        except (TypeError, ValueError, OverflowError):
            self.stop('invalid_action')
            return
        self.last_capture, self.sequence = stamp, decision.sequence
        if stop:
            self.stop('goal_stop')
            return
        limited = (max(0., min(self.forward, v)), 0., max(-self.yaw, min(self.yaw, w)))
        if not self.rpc('Move', limited, 'policy', seq=decision.sequence, captured=stamp, raw=[v,w,0]):
            self.stop('move_failed')


class MockSport:
    """Same callable boundary as SportClient, with a zero-order hold on the last twist."""
    def __init__(self):
        self.twist = (0.,0.,0.)

    def Move(self, vx, vy, vyaw):
        self.twist = (vx, vy, vyaw)
        return 0

    def StopMove(self):
        self.twist = (0.,0.,0.)
        return 0
