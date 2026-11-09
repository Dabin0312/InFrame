"""Run the pinned vendor Go2 client methods behind an in-memory RPC boundary (no DDS)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from io import BytesIO

import numpy as np
from PIL import Image
from bridge import Decision, MotionGuard
from devices import FrontCamera, unitree_clients

REVISION='814556d15970dd2ecf1c9984e845ca02ab07e206'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('sdk_checkout',type=Path)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    sdk=args.sdk_checkout.resolve()
    rev=subprocess.check_output(['git','-C',str(sdk),'rev-parse','HEAD'],text=True).strip()
    if rev!=REVISION:
        raise RuntimeError('Use the documented SDK revision')
    package=sdk/'unitree_sdk2py'
    # Import the unmodified sport/video modules, substituting only transport/registration.
    for name in ('unitree_sdk2py','unitree_sdk2py.core','unitree_sdk2py.rpc','unitree_sdk2py.go2'):
        module=types.ModuleType(name)
        module.__path__=[str(sdk/name.replace('.','/'))]
        sys.modules[name]=module
    rpc=types.ModuleType('unitree_sdk2py.rpc.client')
    channel=types.ModuleType('unitree_sdk2py.core.channel')
    calls=[]
    channel.ChannelFactoryInitialize=lambda domain,interface:calls.append(['dds_init_spy',domain,interface])
    rgb=np.full((240,320,3),[214,67,36],np.uint8)
    encoded=BytesIO()
    Image.fromarray(rgb).save(encoded,format='JPEG',quality=97)

    class RPCProbe:
        def __init__(self,service,lease):
            self.service=service
        def SetTimeout(self,value):
            calls.append(['timeout',self.service,value])
        def _SetApiVerson(self,value):
            calls.append(['version',self.service,value])
        def _RegistApi(self,*args):
            pass
        def _CallBinary(self,api,args):
            calls.append(['binary',self.service,api,args])
            return 0,list(encoded.getvalue())
        def _CallNoReply(self,api,args):
            calls.append(['no_reply',self.service,api,json.loads(args)])
            return 0
        def _Call(self,api,args):
            calls.append(['rpc',self.service,api,json.loads(args)])
            return 0,''
    rpc.Client=RPCProbe
    sys.modules[rpc.__name__]=rpc
    sys.modules[channel.__name__]=channel
    sport,video=unitree_clients('fixture0')
    clock=lambda: 4.
    guard=MotionGuard(sport,clock)
    guard.start()
    stamp,image=FrontCamera(video,clock).read()
    assert image.shape==(144,192,3) and image.dtype==np.uint8 and image.flags.c_contiguous
    assert np.abs(image[70,90].astype(float)-rgb[0,0]).max()<=3
    guard.accept(Decision(1,stamp,(.6,-1.8,0)))
    guard.stop('contract_test')
    assert calls[0]==['dds_init_spy',0,'fixture0']
    assert [r for r in calls if r[0] in ('rpc','no_reply','binary')]==[
        ['rpc','sport',1003,{}],['binary','videohub',1001,[]],
        ['no_reply','sport',1008,{'x':.4,'y':0.,'z':-1.}],['rpc','sport',1003,{}]]
    files=['go2/sport/sport_client.py','go2/sport/sport_api.py','go2/video/video_client.py','go2/video/video_api.py']
    hashes={}
    for key in files:
        original=subprocess.check_output(['git','-C',str(sdk),'show',REVISION+':unitree_sdk2py/'+key])
        assert original==(package/key).read_bytes()
        hashes[key]=hashlib.sha256(original).hexdigest()
    args.out.write_text(json.dumps(dict(revision=rev,imports=hashes,rpc_calls=calls,
        jpeg_rgb=image[70,90].tolist(),dds_transport='replaced by RPC probe; no NIC opened'),indent=2)+'\n')
    print('Passed upstream GetImageSample, Move (no reply), StopMove; no DDS connection.')

if __name__=='__main__':
    main()
