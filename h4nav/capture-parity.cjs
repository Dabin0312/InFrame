// Record the normal closed-loop Castle run before replay through the Go2 camera API.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright-core');
async function main() {
  const [origin, directory, layout = 'escape13'] = process.argv.slice(2);
  const browser = await chromium.launch({channel:'chrome', args: process.platform === 'darwin' ? ['--use-angle=metal'] : []});
  try {
    const page = await browser.newPage();
    await page.goto(origin + '/spatial/floor.json');
    const sim = await page.evaluateHandle(async () => (await import('/h4nav/run.mjs')).experiment());
    for (const [id,prompt] of [['chair','chair'],['bin','trash can'],['extinguisher','fire extinguisher']]) {
      const record = await sim.evaluate(async (sim, options) => {
        const frames = [];
        const result = await sim.run(options, canvas => frames.push(canvas.toDataURL('image/png').split(',')[1]));
        return {frames, result};
      }, {layout, prompt});
      const folder = path.join(directory,id);
      fs.mkdirSync(folder,{recursive:true});
      record.frames.forEach((frame,i)=>fs.writeFileSync(path.join(folder,i+'.png'),Buffer.from(frame,'base64')));
      fs.writeFileSync(path.join(folder,'sim.json'),JSON.stringify(record.result));
      console.log(id,record.result.steps,record.result.success);
    }
    await sim.evaluate(sim => sim.close());
  } finally {await browser.close();}
}
main().catch(err=>{console.error(err);process.exitCode=1;});
