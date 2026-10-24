/* Adjust observation batches, never clock periods or HDL source constants. */
(function(root){
'use strict';
class Controller {
 constructor(){this.reset();}
 reset(){this.next=10000;this.cost=null;}
 interval(maximum,automatic,remaining=Infinity){
  if(!Number.isInteger(maximum)||maximum<10||maximum>10000000||maximum%10)throw Error('Sample interval must be 10 ns–10 ms in multiples of 10 ns.');
  const desired=automatic?Math.min(maximum,this.next):maximum;
  return Math.max(10,Math.floor(Math.min(desired,remaining)/10)*10);
 }
 observe(ns,waitMs){
  if(!(ns>0)||!Number.isFinite(waitMs)||waitMs<0)return;
  const cost=Math.max(waitMs,0.001)/ns;
  this.cost=this.cost===null?cost:0.7*this.cost+0.3*cost;
  // Target at most 20 ms of simulator waiting per request. Grow cautiously;
  // latency is best effort, not a real-time guarantee for arbitrary designs.
  this.next=Math.max(10,Math.min(10000000,Math.floor(Math.max(ns/4,Math.min(ns*2,20/this.cost))/10)*10));
 }
}
class Throughput {
 constructor(){this.reset();}
 reset(){this.samples=[];this.previous=null;}
 observe(ns,activeMs,requestMs){
  const elapsed=this.previous===null?requestMs:Math.max(0,activeMs-this.previous);
  this.previous=activeMs;
  this.samples.push({ns,elapsed,requestMs,time:activeMs});
  while(this.samples.length>1&&this.samples[0].time<activeMs-5000)this.samples.shift();
  const total=this.samples.reduce((sum,s)=>({ns:sum.ns+s.ns,ms:sum.ms+s.elapsed,gap:sum.gap+Math.max(0,s.elapsed-s.requestMs)}),{ns:0,ms:0,gap:0});
  return {speed:total.ns/Math.max(total.ms,0.001)/1e6,betweenMs:total.gap/this.samples.length,windowMs:total.ms};
 }
}
function mergeWave(previous,current){
 if(current.mode!=='delta')return current;
 const events=[...(previous?.events||[]),...current.events];
 return {...current,events:events.slice(-4000),truncated:!!previous?.truncated||current.truncated||events.length>4000};
}
const api={Controller,Throughput,mergeWave};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.NexysPacing=api;
})(typeof window!=='undefined'?window:globalThis);
