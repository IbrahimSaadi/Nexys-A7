'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const url=process.env.NEXYS_LAB_URL||'http://127.0.0.1:8016';
const source=`library ieee; use ieee.std_logic_1164.all;
entity dynamic_board is generic(WIDTH:positive:=96); port(reference_clock:in std_logic;
direction,enable,trigger:in std_logic; data_in:in std_logic_vector(WIDTH-1 downto 0);
data_out:out std_logic_vector(WIDTH-1 downto 0); gpio_bus:inout std_logic_vector(7 downto 0);
colors:out std_logic_vector(2 downto 0); indicator:out std_logic); end;
architecture rtl of dynamic_board is begin data_out<=not data_in;indicator<=direction xor enable;
gpio_bus<="ZZZZ1010";colors<="101";end;`;
const xdc=`set_property PACKAGE_PIN M18 [get_ports trigger]
set_property PACKAGE_PIN J15 [get_ports direction]
set_property PACKAGE_PIN L16 [get_ports enable]
set_property PACKAGE_PIN H17 [get_ports indicator]
set_property PACKAGE_PIN R12 [get_ports {colors[0]}]
set_property PACKAGE_PIN M16 [get_ports {colors[1]}]
set_property PACKAGE_PIN N15 [get_ports {colors[2]}]
set_property PACKAGE_PIN C17 [get_ports {gpio_bus[0]}]`;
async function generalGuidance(page){
 const text=await page.locator('#input-status, #timing-note, #usage-help, #board-status').allTextContents();
 assert.doesNotMatch(text.join(' '),/floor|door|destination|\bGO\b|elevator/i);
 assert.match(await page.locator('[data-button="btnC"]').getAttribute('aria-label'),/^BTNC(?: · rst)?$/);
}
async function main(){
 const browser=await chromium.launch({headless:true,...(process.env.NEXYS_CHROMIUM?{executablePath:process.env.NEXYS_CHROMIUM}:process.platform==='linux'?{executablePath:'/usr/bin/chromium',args:['--no-sandbox']}:{})});
 const page=await browser.newPage({viewport:{width:1600,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);await page.waitForFunction(()=>document.getElementById('input-status').textContent.includes('Add or import'));
  assert.equal(await page.locator('#editor').inputValue(),'');await generalGuidance(page);
  page.once('dialog',dialog=>dialog.accept());await page.click('#example');
  await page.waitForFunction(()=>document.getElementById('editor').value.includes('entity elevator_top'));
  await page.click('#inspect');
  await page.waitForFunction(()=>document.querySelectorAll('.signals-row').length>0);
  await generalGuidance(page);
  page.once('dialog',dialog=>dialog.accept());await page.click('#new-project');
  assert.equal(await page.locator('.signals-row').count(),0);
  assert.equal(await page.locator('#mapping-fields select').count(),0);
  assert.equal(await page.locator('#entity-options option').count(),0);
  assert.equal(await page.locator('#timing').count(),0);await generalGuidance(page);
  await page.locator('#upload').setInputFiles([{name:'board.vhd',mimeType:'text/plain',buffer:Buffer.from(source)},{name:'board.xdc',mimeType:'text/plain',buffer:Buffer.from(xdc)}]);
  await page.waitForFunction(()=>document.getElementById('top').value==='dynamic_board'&&document.querySelectorAll('.signals-row').length===9);
  await generalGuidance(page);
  await page.evaluate(()=>{const key='nexys-lab-project-v1';const data=JSON.parse(localStorage.getItem(key));data.timing='interactive';localStorage.setItem(key,JSON.stringify(data));});
  await page.reload();await page.waitForFunction(()=>document.getElementById('top').value==='dynamic_board');await generalGuidance(page);
  await page.selectOption('#mode','testbench');await generalGuidance(page);
  await page.selectOption('#mode','board');await page.click('#inspect');
  await page.click('[data-tab="signals"]');await page.fill('#project-generics','{"WIDTH":128}');await page.click('#inspect');
  await page.waitForFunction(()=>document.querySelector('[data-port="data_in"] .signals-port-meta').textContent.includes('128'));
  await page.locator('[data-port="reference_clock"] summary').click();await page.getByLabel('Clock on reference_clock',{exact:true}).check();await page.getByLabel('Clock period for reference_clock',{exact:true}).fill('40');await page.locator('[data-port="reference_clock"] button').filter({hasText:/Apply clock|Update clock/}).click();
  await page.fill('#frame-quantum','1000');
  const started=page.waitForRequest(r=>r.url().endsWith('/api/live/start'));
  await page.click('#run');assert.equal((await started).postDataJSON().timing,'original');await page.waitForFunction(()=>document.getElementById('result').textContent.includes('Running'));
  await page.click('[data-button="btnU"]');
  await page.waitForFunction(()=>/BTNU.*trigger.*delivered/.test(document.getElementById('input-status').textContent));await generalGuidance(page);
  await page.getByRole('button',{name:'Switch 0',exact:true}).click();await page.waitForFunction(()=>document.getElementById('led-0').classList.contains('on'));
  await page.getByRole('button',{name:'Switch 1',exact:true}).click();await page.waitForFunction(()=>!document.getElementById('led-0').classList.contains('on'));
  assert.equal(await page.locator('#rgb-0').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 0, 255)');
  await page.click('[data-tab="signals"]');
  const pattern='0123456789ABCDEF0123456789ABCDEF';const expected=((1n<<128n)-1n ^ BigInt('0x'+pattern)).toString(16).toUpperCase().padStart(32,'0');
  await page.getByLabel('Drive data_in',{exact:true}).fill('0x'+pattern);await page.getByLabel('Drive data_in',{exact:true}).press('Enter');
  await page.waitForFunction(value=>document.querySelector('[data-port="data_out"] .signals-hex').textContent==='0x'+value,expected);
  await page.getByLabel('Drive gpio_bus',{exact:true}).fill('0x5A');await page.getByLabel('Drive gpio_bus',{exact:true}).press('Enter');
  await page.waitForFunction(()=>document.querySelector('[data-port="gpio_bus"] .signals-hex').textContent==='0x5A');
  await page.getByLabel('Drive gpio_bus',{exact:true}).fill('0x50');await page.getByLabel('Drive gpio_bus',{exact:true}).press('Enter');
  await page.waitForFunction(()=>document.querySelector('[data-port="gpio_bus"] .signals-binary').textContent.includes('X'));
  assert.equal(await page.getByLabel('Clock period for reference_clock',{exact:true}).inputValue(),'40');
  await page.click('[data-tab="pins"]');assert.ok((await page.locator('#pin-catalog').textContent()).includes('207'));
  assert.ok((await page.locator('#pin-catalog').textContent()).includes('RAW'));
  if(process.env.NEXYS_SCREENSHOT)await page.screenshot({path:process.env.NEXYS_SCREENSHOT,fullPage:true});
  await page.click('#run');assert.deepEqual(errors,[]);
  console.log('PASS: independent XDC switch bits, arbitrary port names, 128-bit generics/input/output, resolved inout contention, 25MHz custom clock, RGB output and 207-pin catalog.');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
