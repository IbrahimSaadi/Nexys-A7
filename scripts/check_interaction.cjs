#!/usr/bin/env node
'use strict';

// Run against an already-started server. This test executes real VHDL through
// the app, rather than replacing API responses or emulating the elevator.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const url = process.env.NEXYS_LAB_URL || 'http://127.0.0.1:8011';
const screenshot = process.env.NEXYS_SCREENSHOT;
const executablePath = process.env.NEXYS_CHROMIUM ||
  (process.platform === 'linux' ? '/usr/bin/chromium' : undefined);

async function boardState(page) {
  return page.evaluate(() => ({
    ones: Array.from(document.querySelectorAll('#digit-0 polygon.on'))
      .map(polygon => polygon.dataset.segment).join(','),
    tens: Array.from(document.querySelectorAll('#digit-1 polygon.on'))
      .map(polygon => polygon.dataset.segment).join(','),
    door: document.getElementById('led-0').classList.contains('on'),
    time: document.getElementById('sim-time').textContent,
  }));
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
    ...(process.platform === 'linux' ? { args: ['--no-sandbox'] } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(url);
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForFunction(() => document.getElementById('input-status').textContent.includes('Add or import'));
    // Deliberately short timers in this test project's source keep the test
    // quick. The application must execute those sources without overrides.
    const project=await (await page.request.get(url+'/api/example')).json();
    for(const name of Object.keys(project.files)) {
      project.files[name]=project.files[name]
        .replace(/(constant DIVISOR\s*:\s*integer\s*:=\s*)100000000/i,(_,prefix)=>prefix+'10000')
        .replace(/(constant DEBOUNCE_CYCLES\s*:\s*integer\s*:=\s*)2000000/i,(_,prefix)=>prefix+'200')
        .replace(/(constant SCAN_DIV\s*:\s*integer\s*:=\s*)50000/i,(_,prefix)=>prefix+'5');
    }
    project.top='elevator_top';project.mode='board';project.timing='original';
    await page.locator('#upload').setInputFiles({name:'regression.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});
    await page.waitForFunction(()=>document.querySelectorAll('.signals-row').length===8);
    await page.click('[data-tab="signals"]');
    await page.fill('#frame-quantum','10000');
    await page.getByRole('button', { name: 'Switch 0', exact: true }).click();
    await page.getByRole('button', { name: 'Switch 1', exact: true }).click();

    // Hold one real simulator response until after GO is clicked. No HDL/API
    // result is mocked: this deterministically exercises a click arriving while
    // the previous frame is still in flight at the client.
    let frameHeld = false;
    let heldRequest = null;
    let heldRequestFinished = false;
    let announceHeld;
    let releaseHeld;
    const held = new Promise(resolve => { announceHeld = resolve; });
    const release = new Promise(resolve => { releaseHeld = resolve; });
    page.on('requestfinished', request => {
      if (request === heldRequest) heldRequestFinished = true;
    });
    await page.route('**/api/live/advance', async route => {
      if (frameHeld) return route.continue();
      frameHeld = true;
      heldRequest = route.request();
      assert.ok(!heldRequest.postDataJSON().buttons.includes('btnU'),
        'The held frame must predate the GO input');
      const response = await route.fetch();
      announceHeld();
      await release;
      await route.fulfill({ response });
    });
    await page.click('#run');
    await page.waitForFunction(() =>
      !document.getElementById('run').disabled &&
      /stop/i.test(document.getElementById('run').textContent));
    let frameTimeout;
    try {
      await Promise.race([held, new Promise((_, reject) => {
        frameTimeout = setTimeout(() => reject(Error('No live frame request was captured')), 10000);
      })]);
    } finally { clearTimeout(frameTimeout); }

    const start = Date.now();
    assert.equal(heldRequestFinished, false, 'Expected a frame to be in flight before GO');
    await page.click('[data-button="btnU"]');
    assert.equal(heldRequestFinished, false, 'GO must be issued before the previous frame finishes');
    assert.match(await page.locator('#input-status').textContent(), /BTNU.*(queued|delivered)/i,
      'GO must produce visible input feedback');
    releaseHeld();

    let firstMovement = null;
    let arrival = null;
    let finalState;
    const zero = '0,1,2,3,4,5';
    const three = '0,1,2,3,6';
    while (Date.now() - start < 10000) {
      const state = await boardState(page);
      if (state.ones && state.ones !== zero && firstMovement === null) {
        firstMovement = (Date.now() - start) / 1000;
      }
      if (state.ones === three && state.tens === zero && state.door) {
        arrival = (Date.now() - start) / 1000;
        finalState = state;
        break;
      }
      await page.waitForTimeout(50);
    }
    assert.notEqual(firstMovement, null, 'The actual seven-segment output never moved from floor 00');
    assert.notEqual(arrival, null, 'The elevator never reached 03 with its door open within 10 seconds');
    assert.equal(await page.locator('#timing').count(),0,'No design-specific timing selector');
    console.log(JSON.stringify({ firstMovementSeconds: firstMovement, arrivalSeconds: arrival,
      display: '03', door: finalState.door }));

    await page.click('#pause');
    // Allow an already-sent frame to settle, then verify no further HDL time advances.
    await page.waitForTimeout(600);
    const pausedTime = (await boardState(page)).time;
    await page.waitForTimeout(500);
    assert.equal((await boardState(page)).time, pausedTime, 'Pause must freeze HDL time');
    if (screenshot) await page.screenshot({ path: screenshot, fullPage: true });
    await page.click('#pause');
    await page.waitForTimeout(600);
    const resumedTime = (await boardState(page)).time;
    const boardSeconds = (parseFloat(resumedTime) - parseFloat(pausedTime));
    assert.ok(boardSeconds > 0,
      `HDL time must advance after resuming; observed ${boardSeconds}`);
    console.log(JSON.stringify({ resumedBoardSeconds: boardSeconds, resumedWallSeconds: 0.6,
      goIssuedDuringFrame: true }));

    await page.click('#run');
    assert.equal(await page.locator('#timing').count(),0);
    assert.deepEqual(errors, [], 'Unexpected browser JavaScript errors');
    console.log('PASS: real VHDL switch → in-flight GO → 03, input feedback, continuous timing, pause/resume without catch-up, and source-defined timing');
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
