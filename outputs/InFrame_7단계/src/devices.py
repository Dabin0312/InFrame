"""Compressed Go2 front image → contiguous RGB; explicit SDK wiring for integration."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT/'frozen'
LOCK_SHA = 'cec5c063b43f44b965a9f7c5b57d246eaa35d3f477f8aa88765d0c2ba10bd573'


def verify_policy():
    lock_data = (FROZEN/'stage6-lock.json').read_bytes()
    if hashlib.sha256(lock_data).hexdigest()!=LOCK_SHA:
        raise ValueError('Unexpected stage 6 model lock')
    lock = json.loads(lock_data)
    files = {'recovery.pt':'after','policy.py':'baseline_policy','visual_motion.py':'visual_motion',
             'recovery_policy.py':'controller','worker.py':'worker'}
    out = {}
    for name,key in files.items():
        digest = hashlib.sha256((FROZEN/name).read_bytes()).hexdigest()
        if digest!=lock[key]:
            raise ValueError(f'Stage 6 digest differs: {name}')
        out[name] = digest
    return out


class LocalPolicy:
    def __init__(self):
        verify_policy()
        sys.path.insert(0,str(FROZEN))
        import torch
        from recovery_policy import RecoveryStudent
        torch.set_num_threads(1)
        self.model = RecoveryStudent(FROZEN/'recovery.pt')
        self.model.act(np.zeros((144,192,3),np.uint8),'소화기')
        self.model.reset()

    def act(self, rgb):
        action = self.model.act(rgb,'소화기')
        return struct.unpack('<ffB', struct.pack('<ffB', *action))


class FrontCamera:
    def __init__(self, video, clock=time.monotonic):
        self.video, self.clock = video, clock

    def read(self):
        # Start-of-request monotonic time conservatively includes camera and decode latency.
        stamp = self.clock()
        code, data = self.video.GetImageSample()
        if code!=0:
            raise OSError(f'GetImageSample returned {code}')
        payload = bytes(data)
        if not (payload.startswith(bytes.fromhex('ffd8ff')) or payload.startswith(bytes.fromhex('89504e470d0a1a0a'))):
            raise ValueError('Missing camera JPEG/PNG header')
        with Image.open(BytesIO(payload), formats=('JPEG','PNG')) as image:
            if image.width<2 or image.height<2:
                raise ValueError('Invalid RGB image sample')
            image = image.convert('RGB')
            if image.size!=(192,144):
                image = ImageOps.fit(image,(192,144),method=Image.Resampling.BILINEAR)
            rgb = np.array(image, dtype=np.uint8, order='C')
        return stamp, rgb


class MockVideo:
    def __init__(self, camera_rgb):
        self.camera_rgb = camera_rgb

    def GetImageSample(self):
        image = Image.fromarray(self.camera_rgb())
        out = BytesIO()
        image.save(out, format='PNG', compress_level=1)
        return 0, out.getvalue()


def unitree_clients(interface):
    if not interface:
        raise ValueError('An explicit network interface is required for DDS')
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.go2.sport.sport_client import SportClient
    from unitree_sdk2py.go2.video.video_client import VideoClient
    ChannelFactoryInitialize(0, interface)
    sport, video = SportClient(), VideoClient()
    for client in (sport,video):
        client.SetTimeout(0.10)
        client.Init()
    return sport, video
