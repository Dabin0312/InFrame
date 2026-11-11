const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright-core');

async function replay({ original, prefix }) {
  const { ask } = await import('../spatial/rpc.mjs');
  const { castle } = await import('../h4nav/castle.mjs');
  const sim = await castle(160, 120);
  const worker = new Worker('../h4nav/worker.mjs?policy=escape', { type: 'module' });
  const signal = new AbortController().signal;
  const pose = { ...original.start };
  const trace = [];
  let previous = -1, blockedAfter = 0, takeoverPhoto, firstStop = false;

  try {
    sim.place(original.anchors);
    await ask(worker, { type: 'start', prompt: original.prompt, w: 160, h: 120 }, signal);
    for (let step = 0; step < 120; step++) {
      if (step <= prefix && ['x', 'z', 'yaw'].some(key =>
        Math.abs(pose[key] - original.trace[step][key]) > 1e-6)) {
        throw Error('The replay departed from the original path before handoff.');
      }
      const pixels = sim.render(pose).data.buffer;
      if (step === prefix) takeoverPhoto = sim.ctx.canvas.toDataURL();
      const decision = await ask(worker, { type: 'frame', pixels, executedPrevious: previous }, signal, [pixels]);
      const action = step < prefix ? original.trace[step].a : decision.action;
      trace.push({ ...pose, a: action });
      previous = action;
      if (action === 3) {
        firstStop = true;
        break;
      }
      if (!sim.move(pose, action) && step >= prefix) blockedAfter++;
    }
    sim.render(pose);
    const photo = sim.ctx.canvas.toDataURL();
    return { prefix, firstStep: prefix + 1, takeoverPhoto, firstStop, steps: trace.length,
      additionalSteps: trace.length - prefix, blockedAfter, trace, endpoint: pose, photo, audit: sim.score(pose, 0) };
  } finally {
    worker.terminate();
    sim.dispose();
  }
}

async function main() {
  const record = JSON.parse(fs.readFileSync(path.join(__dirname, 'chair-trial-chair2.json')));
  const original = record.find(row => row.case === 0).after;
  const browser = await chromium.launch({
    channel: 'chrome', args: process.platform === 'darwin' ? ['--use-angle=metal'] : [],
  });
  try {
    const page = await browser.newPage();
    await page.goto((process.env.BASE_URL || 'http://localhost:8000') + '/demo/');
    // Only this test forces actions. Feed the executed action back into H4 on
    // the next frame, including during the prefix where the old policy drives.
    const source = fs.readFileSync(path.join(__dirname, 'worker.mjs'), 'utf8');
    const hook = "else if(data.type==='frame'){";
    if (!source.includes(hook)) throw Error('Cannot locate the frame handler.');
    await page.route('**/h4nav/worker.mjs*', req => req.fulfill({
      contentType: 'text/javascript',
      body: source.replace(hook, hook + 'previousAction=data.executedPrevious;'),
    }));
    const runs = [];
    for (const prefix of [49, 79]) {
      const run = await page.evaluate(replay, { original, prefix });
      runs.push(run);
      console.log(prefix, run.steps, run.firstStop, run.audit.distance, run.blockedAfter);
    }
    const output = process.argv[2] || path.join(__dirname, 'escape-handoff.json');
    fs.writeFileSync(output, JSON.stringify(runs) + '\n');
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
