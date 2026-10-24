const test=require('node:test'),assert=require('node:assert/strict');
const {formatValue,valueAt,segments,timeLabel}=require('./web/wave-viewer.js');
test('wide buses preserve exact numeric values and signed interpretation',()=>{
 assert.equal(formatValue('1'.repeat(128),'decimal'),((1n<<128n)-1n).toString());
 assert.equal(formatValue('1'.repeat(128),'signed'),'-1');
 assert.equal(formatValue('00001111'),'0x0F');
 assert.equal(formatValue('10XZ'),'10XZ');
});
test('cursor uses preceding event and last delta at the same time',()=>{
 const events=[[10,'a','0'],[20,'a','1'],[20,'a','0'],[30,'a','1']];
 assert.equal(valueAt(events,9),null);assert.equal(valueAt(events,20),'0');
 assert.equal(valueAt(events,40),'1');
 assert.deepEqual(segments(events,21,29),[[21,29,'0']]);
});
test('truncated history never invents earlier values',()=>{
 assert.deepEqual(segments([[20,'a','1']],10,30),[[10,20,null],[20,30,'1']]);
 assert.equal(timeLabel(10000000),'10 ns');
 assert.equal(timeLabel(2500),'2.5 ps');
});
