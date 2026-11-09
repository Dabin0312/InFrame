"""Download just the Fire frames used here, validating each source archive CRC."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile
import argparse, io, struct, zlib
URL='https://3dvision.princeton.edu/projects/2016/3DMatch/downloads/rgbd-datasets/7-scenes-fire.zip'

def read_range(a,b):
    for attempt in range(3):
        try:
            with urlopen(Request(URL,headers={'Range':f'bytes={a}-{b}'}),timeout=40) as f:
                if f.status!=206 or not f.headers['Content-Range'].startswith(f'bytes {a}-{b}/'):
                    raise IOError('The archive server did not honor the byte range')
                data=f.read()
                if len(data)!=b-a+1:raise IOError('Incomplete range')
                return data,int(f.headers['Content-Range'].split('/')[-1])
        except OSError:
            if attempt==2:raise

class Remote(io.RawIOBase):
    def __init__(self): self.pos=0;self.size=read_range(0,0)[1]
    def seek(self,n,whence=0):self.pos=([0,self.pos,self.size][whence])+n;return self.pos
    def tell(self):return self.pos
    def read(self,n=-1):
        end=self.size if n<0 else min(self.size,self.pos+n)
        if self.pos>=end:return b''
        chunk=read_range(self.pos,end-1)[0];self.pos=end;return chunk

def fetch(scene):
    scene.mkdir(parents=True,exist_ok=True)
    files=['camera-intrinsics.txt','seq-01/frame-000000.pose.txt']
    sets=[('seq-01',range(0,80,10),['color.png','depth.png']),
          ('seq-02',[*range(0,80,10),*range(100,1000,100)],['color.png','pose.txt']),
          ('seq-03',range(0,1000,90),['color.png','pose.txt']),
          ('seq-04',sorted([*range(0,1000,125),*range(60,1000,125)]),['color.png','pose.txt'])]
    for seq,ids,types in sets:
        files.extend(f'{seq}/frame-{i:06}.{kind}' for i in ids for kind in types)
    with ZipFile(Remote()) as archive:
        infos={n:archive.getinfo('7-scenes-fire/'+n) for n in files}
    def get(n):
        info=infos[n];p=scene/n
        if p.is_file() and zlib.crc32(p.read_bytes())==info.CRC:return
        start=info.header_offset
        head=read_range(start,start+29)[0]
        if head[:4]!=b'PK\x03\x04':raise IOError('Invalid entry header')
        start+=30+sum(struct.unpack_from('<HH',head,26))
        data=read_range(start,start+info.compress_size-1)[0]
        if info.compress_type==8:data=zlib.decompress(data,-15)
        if len(data)!=info.file_size or zlib.crc32(data)!=info.CRC:raise IOError(n)
        p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.part');tmp.write_bytes(data);tmp.replace(p)
    with ThreadPoolExecutor(5) as pool:list(pool.map(get,files))
    print(f'Checked {len(files)} input files.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('scene',type=Path);fetch(p.parse_args().scene)
