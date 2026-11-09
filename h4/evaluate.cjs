// Run each reserved recording through the same file picker and export used by visitors.
const {chromium}=require('playwright-core');
const path=require('node:path'),fs=require('node:fs');
const ids=require('./split.json').test;
async function main(){
  const [media,out,base='http://127.0.0.1:8000/']=process.argv.slice(2);
  if(!media||!out)throw Error('Usage: node evaluate.cjs MEDIA OUTPUT [SITE_URL]');
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try{
    for(const id of ids){
      const page=await browser.newPage();
      try{
        await page.goto(new URL('demo/',base).href);
        await page.locator('#file').setInputFiles(path.resolve(media,id+'.mp4'));
        await page.waitForFunction(()=>!document.querySelector('#session').hidden&&document.querySelector('#cancel').hidden,null,{timeout:720000});
        if(!await page.locator('#download').isVisible())throw Error(await page.locator('#status').innerText());
        const pending=page.waitForEvent('download');await page.click('#download');
        await (await pending).saveAs(path.resolve(out,id+'.json'));console.log(id);
      }finally{await page.close();}
    }
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
