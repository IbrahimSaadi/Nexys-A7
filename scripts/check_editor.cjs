'use strict';
const {chromium}=require('playwright');const assert=require('node:assert/strict');
const url=process.env.NEXYS_LAB_URL||'http://127.0.0.1:8022';
const broken=`library ieee;
use ieee.std_logic_1164.all;
entity tb_check is end;
architecture sim of tb_check is
 signal n : integer := 0
begin
 process begin
  assert false report "expected failure" severity failure;
  wait;
 end process;
end;`;
async function main(){
 const browser=await chromium.launch({headless:true,...(process.env.NEXYS_CHROMIUM?{executablePath:process.env.NEXYS_CHROMIUM}:process.platform==='linux'?{executablePath:'/usr/bin/chromium',args:['--no-sandbox']}:{})});
 const page=await browser.newPage({viewport:{width:1600,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const project={files:{'tb_check.vhd':broken,'other.vhd':'-- <img src=x onerror=alert(1)>\nentity other is end; architecture sim of other is begin end;'},top:'tb_check',mode:'testbench'};
 try{
  await page.goto(url);await page.locator('#upload').setInputFiles({name:'project.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});
  await page.waitForFunction(()=>document.getElementById('editor').value.includes('signal n'));
  assert.ok(await page.locator('.vhdl-keyword').count()>0);assert.ok(await page.locator('.vhdl-type').count()>0);assert.ok(await page.locator('.vhdl-number').count()>0);
  const colors=await page.evaluate(()=>['keyword','type','number'].map(k=>getComputedStyle(document.querySelector('.vhdl-'+k)).color));assert.equal(new Set(colors).size,3);
  await page.click('#run');await page.waitForFunction(()=>document.getElementById('result').textContent.includes('failed'));
  await page.click('#problems-tab');assert.match(await page.locator('#problem-list').innerText(),/ERROR.*Syntax/s);
  await page.locator('#files button').filter({hasText:'other.vhd'}).click();assert.equal(await page.locator('#syntax-highlight img').count(),0);assert.ok((await page.locator('#syntax-highlight').textContent()).includes('<img'));
  await page.locator('.problem-location').first().click();assert.equal(await page.locator('#filename').textContent(),'tb_check.vhd');
  assert.ok(await page.locator('#lines .line-error').count()>0);assert.match(await page.locator('#cursor').textContent(),/Ln [56],/);
  if(process.env.NEXYS_SCREENSHOT)await page.screenshot({path:process.env.NEXYS_SCREENSHOT,fullPage:true});
  const fixed=broken.replace('integer := 0\n','integer := 0;\n');await page.fill('#editor',fixed);
  assert.equal(await page.locator('#problems-tab').textContent(),'Problems (0)');assert.equal(await page.locator('#lines .line-error').count(),0);
  await page.click('#run');await page.waitForFunction(()=>document.getElementById('result').textContent.includes('failed'));await page.click('#problems-tab');
  await page.getByLabel('Category',{exact:true}).selectOption('Assertion');assert.match(await page.locator('#problem-list').innerText(),/expected failure/);
  await page.getByLabel('Severity',{exact:true}).selectOption('warning');assert.match(await page.locator('#problem-list').innerText(),/No diagnostics match/);
  await page.getByLabel('Severity',{exact:true}).selectOption('All');await page.getByLabel('Category',{exact:true}).selectOption('All');
  await page.fill('#editor',fixed.replace('assert false','assert true'));await page.click('#run');await page.waitForFunction(()=>document.getElementById('result').textContent.includes('passed'));
  await page.click('#problems-tab');assert.equal(await page.locator('#problem-list .error').count(),0);
  // Native textarea edits, tabs and scrolling remain aligned with the color layer.
  await page.fill('#editor','-- '+ 'x'.repeat(240)+'\n'+Array.from({length:80},(_,i)=>'signal item_'+i+' : integer := '+i+';').join('\n'));
  await page.locator('#editor').press('Control+End');await page.locator('#editor').press('Tab');assert.ok((await page.locator('#editor').inputValue()).endsWith('    '));
  await page.locator('#editor').evaluate(e=>{e.scrollTop=500;e.scrollLeft=300;e.dispatchEvent(new Event('scroll'));});
  const aligned=await page.evaluate(()=>{const e=document.getElementById('editor'),p=document.getElementById('syntax-highlight'),g=document.getElementById('lines');const m=new DOMMatrix(getComputedStyle(p).transform);return Math.abs(m.m41+e.scrollLeft)<1&&Math.abs(m.m42+e.scrollTop)<1&&Math.abs(g.scrollTop-e.scrollTop)<1;});assert.ok(aligned);
  assert.deepEqual(errors,[]);console.log('PASS: colored editor, real GHDL syntax/assertion diagnostics, navigation, severity/category filters, stale-result clearing, safe source rendering and scroll alignment.');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
