from pathlib import Path
import sys,json
from PIL import Image,ImageDraw
base=Path(__file__).resolve().parents[2]/'InFrame_Fire_2단계'
sys.path.insert(0,str(base/'src'))
from geometry import read_masks
from results import marked,font
def main(out,scene):
    canvas=Image.new('RGB',(1120,750),'#f4f6f3');draw=ImageDraw.Draw(canvas)
    draw.text((30,13),'Fire   /   놓쳤던 소화기의 사진 연결',font=font(39),fill='#173940')
    for j,(dataset,cache,title) in enumerate([(base,base/'masks','기존'),(out,out/'masks','개선 후')]):
        records={r['photo']:r for r in json.loads((dataset/'links.json').read_text())}
        draw.text((34+j*552,79),title,font=font(26),fill='#234149')
        for i,(key,box) in enumerate([('seq-02_000040',(185,55,539,355)),('seq-03_000540',(49,15,400,249))]):
            seq,num=key.split('_');src=Image.open(scene/seq/f'frame-{num}.color.png');_,m=read_masks(cache,key)
            im=marked(src,records[key]['links'],m).crop(box);im.thumbnail((498,234))
            x=34+j*552;y=116+i*306
            canvas.paste(im,(x,y));ids=' · '.join(sorted(l['id'] for l in records[key]['links'])) or '위치 추정 보류'
            draw.text((x,y+238),f'{key}     {ids}',font=font(22),fill='#294853')
    canvas.save(out/'개선사례.png')
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
