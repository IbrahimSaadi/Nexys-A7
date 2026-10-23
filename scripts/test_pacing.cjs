'use strict';
const assert=require('node:assert/strict');
const {Controller,mergeWave}=require('../web/pacing.js');
const c=new Controller();
assert.equal(c.interval(1000000,true),10000);
c.observe(10000,100);assert.ok(c.interval(1000000,true)<10000,'Slow simulation reduces batch latency');
for(let i=0;i<20;i++){const ns=c.interval(1000000,true);c.observe(ns,0.01);}
assert.ok(c.interval(1000000,true)>10000,'Fast simulation increases useful batch work');
assert.ok(c.interval(1000000,true)<=1000000);
assert.equal(c.interval(1000,false),1000);assert.equal(c.interval(1000,false,30),30);
for(const bad of [0,9,11,10000001,NaN,Infinity])assert.throws(()=>c.interval(bad,true));
c.reset();assert.equal(c.interval(1000000,true),10000);
let wave={values:{q:'0'},events:[[0,'q','0']],end:0};
for(let i=1;i<4100;i++)wave=mergeWave(wave,{mode:'delta',values:{q:'1'},events:[[i,'q','1']],end:i});
assert.equal(wave.events.length,4000);assert.equal(wave.events.at(-1)[0],4099);assert.equal(wave.events[0][0],100);assert.equal(wave.truncated,true);
const full={mode:'history',events:[[1,'x','0']]};assert.equal(mergeWave(wave,full),full);
console.log('PASS: adaptive batches shrink/grow within user bounds, fixed intervals and pending button release are respected, delta waveforms merge without duplication.');
