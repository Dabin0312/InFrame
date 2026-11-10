// The previous study keeps its published URLs. The peripheral study loads one placement at a time.
export async function openStudy(embedded=null){
  const params=new URLSearchParams(location.search),scene=params.get('scene');
  const study=params.get('study')??(scene && !/^(edge|blind)/.test(scene)?'recovery':'peripheral');
  const read=async path=>{
    const response=await fetch(new URL(path,import.meta.url));
    if(!response.ok)throw Error('검증 기록을 읽을 수 없습니다.');
    return response.json();
  };
  const [report,floor]=embedded??await Promise.all([read(study==='recovery'?'comparison.json':'peripheral-report.json'),read('../spatial/floor.json')]);
  const peripheral=report.study==='peripheral',cache=new Map();
  async function pairs(layout){
    if(!Object.hasOwn(report.layouts,layout))throw Error('등록된 배치를 선택하세요.');
    if(report.pairs)return report.pairs.filter(pair=>pair.layout===layout);
    if(!cache.has(layout)){
      cache.set(layout,read(report.traces[layout]).catch(e=>{cache.delete(layout);throw e;}));
    }
    return cache.get(layout);
  }
  return {report,floor,pairs,peripheral};
}
