// Historical links keep their original policies, layouts and case numbers.
const studies={
  recovery:{file:'comparison.json',policy:'current',cases:[0,1,2,3,4],layout:'fresh',selected:1},
  peripheral:{file:'peripheral-report.json',policy:'peripheral',cases:[0,1,2,3,4,5],layout:'unseen2',selected:2},
  escape:{file:'escape-report.json',policy:'escape',cases:[0,1,2,6],layout:'chair2',selected:0},
  chair:{file:'chair-report.json',policy:'chair',cases:[0,1,2,6],layout:'panel7',selected:0},
  panel:{file:'panel-report.json',policy:'panel',cases:[0,1,2,4],layout:'bin21',selected:1},
  bin:{file:'bin-report.json',policy:'bin',cases:[0,1,2,4],layout:'blind7',selected:4}
};
export async function openStudy(embedded=null){
  const params=new URLSearchParams(location.search),scene=params.get('scene');
  const inferred=!scene||/^escape\d+$/.test(scene)?'escape':/^chair\d+$/.test(scene)?'chair':/^panel\d+$/.test(scene)?'panel':/^bin\d+$/.test(scene)?'bin':/^(edge|blind)/.test(scene)?'peripheral':'recovery';
  const chosen=params.get('study')??inferred;
  if(!Object.hasOwn(studies,chosen))throw Error('등록된 비교 실험을 선택하세요.');
  const read=async path=>{
    const response=await fetch(new URL(path,import.meta.url));
    if(!response.ok)throw Error('검증 기록을 읽을 수 없습니다.');
    return response.json();
  };
  const [report,floor]=embedded??await Promise.all([read(studies[chosen].file),read('../spatial/floor.json')]);
  const id=report.study??'recovery',cache=new Map();
  async function pairs(layout){
    if(!Object.hasOwn(report.layouts,layout))throw Error('등록된 배치를 선택하세요.');
    if(report.pairs)return report.pairs.filter(pair=>pair.layout===layout);
    if(!cache.has(layout))cache.set(layout,read(report.traces[layout]).catch(e=>{cache.delete(layout);throw e;}));
    return cache.get(layout);
  }
  return {report,floor,pairs,id,...studies[id]};
}
