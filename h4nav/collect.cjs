const { chromium } = require('playwright-core');
const fs = require('node:fs');
const path = require('node:path');
const [profile, directory] = process.argv.slice(2);
const configs = { broad: [1650, 18371], near: [2450, 84013] };

async function collect() {
  if (!directory || !(Object.hasOwn(configs, profile)||['recovery','peripheral'].includes(profile))) throw Error('Usage: node collect.cjs broad|near|recovery|peripheral NEW_DIRECTORY');
  fs.mkdirSync(directory);
  const browser = await chromium.launch({channel: 'chrome', args: process.platform==='darwin'?['--use-angle=metal']:[]});
  try {
    const page = await browser.newPage();
    await page.goto((process.env.BASE_URL || 'http://localhost:8000') + '/demo/');
    if (profile === 'peripheral') {
      const distances=[];
      await page.exposeFunction('sample', ({i,rgb,mask,distance})=>{
        fs.writeFileSync(path.join(directory,i+'.png'),Buffer.from(rgb,'base64'));
        fs.writeFileSync(path.join(directory,i+'-mask.png'),Buffer.from(mask,'base64'));
        distances.push(distance);
      });
      await page.evaluate(async ()=>{
        const {collectPeripheral}=await import('../h4nav/collect-peripheral.mjs');
        await collectPeripheral(window.sample);
      });
      fs.writeFileSync(path.join(directory,'distances.json'),JSON.stringify(distances));
      return;
    }
    if (profile === 'recovery') {
      const episodes = [];
      await page.exposeFunction('record', sequence => episodes.push(sequence));
      await page.evaluate(async () => {
        const {collectRecovery} = await import('../h4nav/collect-recovery.mjs');
        await collectRecovery(window.record);
      });
      fs.writeFileSync(path.join(directory, 'sequences.json'), JSON.stringify(episodes));
      return;
    }
    await page.exposeFunction('saveSequence', record => {
      for (const [step, frame] of record.rows.entries()) {
        fs.writeFileSync(path.join(directory, record.i + '-' + step + '.jpg'), Buffer.from(frame.photo, 'base64'));
        delete frame.photo;
      }
      fs.appendFileSync(path.join(directory, 'labels.ndjson'), JSON.stringify(record) + '\n');
    });
    await page.evaluate(async ([n, seed, profile]) => {
      const {collect} = await import('../h4nav/collect.mjs');
      await collect(n, seed, window.saveSequence, profile);
    }, [...configs[profile], profile]);
  } finally { await browser.close(); }
}
collect().catch(error => { console.error(error); process.exitCode = 1; });
