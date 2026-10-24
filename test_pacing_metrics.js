const test=require('node:test'),assert=require('node:assert/strict');
const {Throughput}=require('./web/pacing.js');
test('recent speed includes time outside requests',()=>{
 const stats=new Throughput();
 assert.equal(stats.observe(1000000,20,20).speed,0.05);
 const next=stats.observe(1000000,120,20);
 assert.equal(next.betweenMs,40);
 assert.equal(next.speed,2000000/120/1e6);
});
test('rolling window recovers after a temporary stall',()=>{
 const stats=new Throughput();stats.observe(1000000,20,20);
 assert.ok(stats.observe(1000000,1020,20).speed<0.003);
 let last;
 for(let now=1040;now<=6200;now+=20)last=stats.observe(1000000,now,20);
 assert.equal(last.speed,0.05);assert.equal(last.betweenMs,0);
 stats.reset();assert.equal(stats.observe(1000000,99999,20).speed,0.05);
});
test('live digit rendering uses authoritative values without rescanning history',()=>{
 const fs=require('node:fs'),vm=require('node:vm');
 const source=fs.readFileSync('web/app.js','utf8');
 const begin=source.indexOf('function integer('),end=source.indexOf('function renderMapping(',begin);
 const pixels=new Map();
 const context={$:id=>({classList:{toggle(){}},style:{},querySelectorAll:()=>Array.from({length:7},(_,i)=>({classList:{toggle:(name,on)=>pixels.set(id+':'+i,on)}}))})};
 vm.createContext(context);vm.runInContext(source.slice(begin,end),context);
 const wave={values:{},get events(){throw Error('History must not be rescanned for complete digit values');}};
 context.renderBoard({ok:true,wave,digits:Array(8).fill('1000000')});
 assert.equal(pixels.get('digit-0:0'),true);assert.equal(pixels.get('digit-0:6'),false);
});
