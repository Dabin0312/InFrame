import {goals} from './goals.mjs';

const known=new Map(Object.entries(goals).flatMap(([key,g])=>[g.label,g.prompt,key].map(word=>[word,key])));
const korean=new Map(Object.entries({'미끄럼 주의 표지판':'wet floor sign','미끄럼주의 표지판':'wet floor sign','그림':'painting','그림 액자':'framed painting','전자레인지':'microwave','라바콘':'traffic cone','교통 콘':'traffic cone'}));

export async function resolveGoal(input){
  let label=input.normalize('NFKC').trim().replace(/\s+/g,' ');
  if(!label||label.length>80)throw Error('물체 이름을 1–80자로 입력하세요.');
  const key=known.get(label.toLowerCase());
  if(key)return {key,...goals[key]};
  let prompt=korean.get(label)??label;
  if(/[가-힣ㄱ-ㅎㅏ-ㅣ]/u.test(prompt)){
    const options={sourceLanguage:'ko',targetLanguage:'en'},api=globalThis.Translator;
    if(!api||await api.availability(options)==='unavailable')throw Error('이 브라우저에서 한영 번역을 사용할 수 없어요. 물체의 영어 이름으로 실행해 주세요.');
    const translator=await api.create(options);
    try{prompt=(await translator.translate(label)).trim();}finally{translator.destroy();}
  }
  if(!/[a-z]/i.test(prompt)||/[^\x20-\x7e]/.test(prompt))throw Error('검출기에 전달할 영어 물체 이름을 입력해 주세요.');
  return {key:'custom',label,prompt:prompt.toLowerCase(),prefix:'T'};
}

// OpenAI CLIP byte-level BPE. IDs follow merge order in the model vocabulary.
export function tokenizer(merges){
  const bytes=[];
  for(let i=0;i<256;i++)if(i>=33&&i<=126||i>=161&&i<=172||i>=174)bytes.push(i);
  const chars=bytes.map(i=>String.fromCharCode(i));
  for(let i=0,n=256;i<256;i++)if(!bytes.includes(i)){bytes.push(i);chars.push(String.fromCharCode(n++));}
  const byteChar=new Map(bytes.map((v,i)=>[v,chars[i]]));
  const pairs=merges.trim().split('\n');
  const rank=new Map(pairs.map((v,i)=>[v,i]));
  const ids=new Map([...chars,...chars.map(c=>c+'</w>'),...pairs.map(p=>p.replace(' ',''))].map((c,i)=>[c,i]));
  return text=>{
    const result=[49406];
    for(const token of text.toLowerCase().match(/'s|'t|'re|'ve|'m|'ll|'d|\p{L}+|\p{N}|[^\s\p{L}\p{N}]+/gu)??[]){
      let word=Array.from(new TextEncoder().encode(token),v=>byteChar.get(v));word[word.length-1]+='</w>';
      while(word.length>1){
        let best=Infinity,first,second;
        for(let i=1;i<word.length;i++){const r=rank.get(word[i-1]+' '+word[i]);if(r<best){best=r;first=word[i-1];second=word[i];}}
        if(best===Infinity)break;
        const next=[];for(let i=0;i<word.length;i++){if(word[i]===first&&word[i+1]===second){next.push(first+second);i++;}else next.push(word[i]);}
        word=next;
      }
      result.push(...word.map(w=>ids.get(w)));
    }
    const tokens=new Int32Array(77);result.splice(76);result.push(49407);tokens.set(result);return tokens;
  };
}
