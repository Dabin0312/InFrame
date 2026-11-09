import sys,struct
import numpy as np
import torch
from recovery_policy import RecoveryStudent

def main():
    torch.set_num_threads(1)
    student=RecoveryStudent(sys.argv[1])
    source,sink=sys.stdin.buffer,sys.stdout.buffer
    while True:
        tag=source.read(1)
        if not tag:break
        if tag==b'R':
            goal=source.readline().decode('utf8').strip()
            student.reset()
        elif tag==b'F':
            raw=source.read(144*192*3)
            if len(raw)!=144*192*3:raise EOFError('Incomplete RGB input')
            frame=np.frombuffer(raw,np.uint8).reshape(144,192,3)
            sink.write(struct.pack('<ffB',*student.act(frame,goal)));sink.flush()
        else:raise ValueError('Unknown observation packet')
if __name__=='__main__':main()
