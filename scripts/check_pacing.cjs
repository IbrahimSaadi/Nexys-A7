'use strict';
const {chromium}=require('playwright');const assert=require('node:assert/strict');
const url=process.env.NEXYS_LAB_URL||'http://127.0.0.1:8023';
const source=`library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity timing_probe is port(clk:in std_logic;q:out std_logic_vector(31 downto 0));end;
architecture rtl of timing_probe is signal n:unsigned(31 downto 0):=(others=>'0');begin
process(clk)begin if rising_edge(clk)then n<=n+1;end if;end process;q<=std_logic_vector(n);end;`;
async function main(){
 const browser=await chromium.launch({headless:true,...(process.env.NEXYS_CHROMIUM?{executablePath:process.env.NEXYS_CHROMIUM}:process.platform==='linux'?{executablePath:'/usr/bin/chromium',args:['--no-sandbox']}:{})});
 const page=await browser.newPage({viewport:{width:1600,height:1100}});const errors=[],frames=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(r.url().endsWith('/api/live/advance'))requests.push(r.postDataJSON());});
 page.on('response',async r=>{if(r.url().endsWith('/api/live/advance')){try{frames.push(await r.json());}catch{}}});
 try{
  await page.goto(url);
  await page.locator('#upload').setInputFiles({name:'timing.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({files:{'probe.vhd':source},top:'timing_probe',mode:'board'}))});
  await page.waitForFunction(()=>document.getElementById('top').value==='timing_probe'&&document.querySelectorAll('.signals-row').length===2);
  await page.click('[data-tab="signals"]');await page.fill('#frame-quantum','1000000');await page.selectOption('#batch-mode','auto');
  const started=page.waitForResponse(r=>r.url().endsWith('/api/live/start'));await page.click('#run');const initial=await(await started).json();
  await page.waitForFunction(()=>document.getElementById('performance-details').textContent.includes('Simulator wait:'));
  for(let i=0;i<100&&frames.length<12;i++)await page.waitForTimeout(50);
  assert.ok(frames.length>=12);assert.equal(requests[0].ns,10000);assert.ok(new Set(requests.map(r=>r.ns)).size>1);
  assert.ok(requests.every(r=>r.wave_history===false&&r.ns>=10&&r.ns<=1000000));
  assert.ok(frames.every(f=>f.wave.mode==='delta'&&f.performance.backend_ms>=0));
  await page.click('#pause');await page.waitForTimeout(300);const count=frames.length;await page.waitForTimeout(250);assert.equal(frames.length,count);
  await page.selectOption('#batch-mode','fixed');await page.fill('#frame-quantum','1000');await page.locator('#frame-quantum').press('Tab');
  const afterPause=requests.length;await page.click('#pause');await page.waitForTimeout(400);await page.click('#pause');await page.waitForTimeout(200);
  assert.ok(requests.length>afterPause);assert.ok(requests.slice(afterPause).every(r=>r.ns===1000));
  let previous=initial;
  for(const frame of frames){const cycles=parseInt(frame.wave.values['lab_board_tb.io_q'],2)-parseInt(previous.wave.values['lab_board_tb.io_q'],2);assert.equal(cycles*10,frame.sim_ns-previous.sim_ns,'Every 100 MHz edge must execute despite adaptive batching');previous=frame;}
  await page.click('[data-tab="waves"]');assert.ok(await page.locator('.wave-row').count()>0);
  await page.click('#run');await page.reload();await page.waitForFunction(()=>document.getElementById('top').value==='timing_probe');
  assert.equal(await page.locator('#batch-mode').inputValue(),'fixed');assert.equal(await page.locator('#frame-quantum').inputValue(),'1000');
  assert.deepEqual(errors,[]);console.log('PASS: real adaptive intervals, incremental transfer, measured timings, exact 100 MHz counter edges, pause/resume, fixed mode and persisted settings.');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
