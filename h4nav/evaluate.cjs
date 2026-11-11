const {chromium} = require('playwright-core');
const fs = require('node:fs');
const path = require('node:path');

async function evaluate(directory, policy='current', suite='recovery') {
  if (!directory || !['current','baseline','peripheral','bin','panel','chair','escape'].includes(policy) || !['recovery','peripheral','bin','panel','chair','escape'].includes(suite)) throw Error('Usage: node evaluate.cjs NEW_DIRECTORY [current|baseline|peripheral|bin|panel|chair|escape] [recovery|peripheral|bin|panel|chair|escape]');
  fs.mkdirSync(directory);
  const browser = await chromium.launch({channel:'chrome', args:process.platform==='darwin'?['--use-angle=metal']:[]});
  try {
    const page = await browser.newPage();
    await page.goto((process.env.BASE_URL || 'http://localhost:8000') + '/demo/');
    await page.evaluate(async policy => {window.env = await (await import('../h4nav/run.mjs')).experiment({policy});}, policy);
    let layouts=['gallery','fresh','transfer',...Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname,'holdout.json'))).layouts)];
    const prompts=['chair','trash can','fire extinguisher','microwave','trash can'];
    if(suite==='peripheral'){
      layouts.push(...Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname,'edge-holdout.json'))).layouts));
      layouts.push(...Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname,'confirmation.json'))).layouts));
      prompts.push('fire extinguisher');
    }
    if(suite==='bin')layouts=['blind7','unseen2',...Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname,'bin-holdout.json'))).layouts)];
    if(suite==='panel')layouts=['bin17','bin19','bin21','bin23','bin24',...Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname,'panel-holdout.json'))).layouts)];
    if(suite==='chair'||suite==='escape'){
      const origins=suite==='escape'?['chair2']:['panel7','panel22'];
      layouts=[...origins,...Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname,suite+'-holdout.json'))).layouts)];
      prompts.push('fire extinguisher','chair');
    }
    for (const layout of layouts) {
      for (const [i,prompt] of prompts.entries()) {
        if((suite==='bin'||suite==='panel')&&i===3)continue;
        if((suite==='chair'||suite==='escape')&&![0,1,2,6].includes(i))continue;
        const result = await page.evaluate(config => window.env.run(config), {layout, prompt, removed: i === 4 ? 1 : i === 5 ? 2 : i === 6 ? 0 : -1});
        fs.writeFileSync(path.join(directory, layout + '-' + i + '.json'), JSON.stringify(result));
      }
    }
  } finally { await browser.close(); }
}
evaluate(...process.argv.slice(2)).catch(error => {console.error(error); process.exitCode=1;});
