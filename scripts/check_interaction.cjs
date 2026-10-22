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
    door: document.getElementById('door-status').textContent,
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
    await page.waitForFunction(() =>
      document.getElementById('editor').value.includes('entity elevator_top'));
    await page.selectOption('#timing', 'interactive');
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
    assert.match(await page.locator('#input-status').textContent(), /GO (queued|delivered)/i,
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
      if (state.ones === three && state.tens === zero && /door open/i.test(state.door)) {
        arrival = (Date.now() - start) / 1000;
        finalState = state;
        break;
      }
      await page.waitForTimeout(50);
    }
    assert.notEqual(firstMovement, null, 'The actual seven-segment output never moved from floor 00');
    assert.notEqual(arrival, null, 'The elevator never reached 03 with its door open within 10 seconds');
    assert.ok(firstMovement >= 0.45 && firstMovement <= 3.5,
      `First floor should appear near one wall second; observed ${firstMovement}s`);
    assert.ok(arrival >= 2 && arrival <= 7,
      `Arrival at floor 3 should take about three wall seconds; observed ${arrival}s`);
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
    const boardSeconds = (parseFloat(resumedTime) - parseFloat(pausedTime)) * 10000;
    assert.ok(boardSeconds >= 0.3 && boardSeconds <= 0.9,
      `After 0.6 wall seconds, expected about 0.6 logical board seconds, without catching up the 1.1-second pause; observed ${boardSeconds}`);
    console.log(JSON.stringify({ resumedBoardSeconds: boardSeconds, resumedWallSeconds: 0.6,
      goIssuedDuringFrame: true }));

    await page.click('#run');
    await page.selectOption('#timing', 'original');
    assert.equal(await page.locator('#timing').inputValue(), 'original');
    assert.deepEqual(errors, [], 'Unexpected browser JavaScript errors');
    console.log('PASS: real VHDL switch → in-flight GO → 03, input feedback, continuous timing, pause/resume without catch-up, and original-mode selection');
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
