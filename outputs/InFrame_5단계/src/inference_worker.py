"""RGB and goal are the only values delivered by this pipe to the model process."""
import struct,sys
import torch,numpy as np
from policy import Student

def main():
    torch.set_num_threads(1)
    student=Student(sys.argv[1])
    source,sink=sys.stdin.buffer,sys.stdout.buffer
    while True:
        tag=source.read(1)
        if not tag:break
        if tag==b'R':
            goal=source.readline().decode('utf8').strip()
            student.reset()
        elif tag==b'F':
            raw=source.read(144*192*3)
            if len(raw)!=144*192*3:raise EOFError('Incomplete camera observation')
            frame=np.frombuffer(raw,np.uint8).reshape(144,192,3)
            sink.write(struct.pack('<ffB',*student.act(frame,goal)));sink.flush()
        else:raise ValueError('Invalid input message')
if __name__=='__main__':main()
