'use strict';
const assert=require('node:assert/strict');
const {highlight,parse,category}=require('../web/editor-tools.js');
const source=`-- entity <img src=x onerror=alert(1)>\nlibrary ieee; signal n: integer := 16#FF#;\nreport "a""b <tag>"; q <= '1'; if rising_edge(clk) then null; end if;`;
const colored=highlight(source);
for(const type of ['comment','keyword','type','number','string','operator'])assert.ok(colored.includes('class="vhdl-'+type+'"'),type);
assert.ok(!colored.includes('<img'));assert.ok(colored.includes('&lt;img'));
const text=colored.replace(/<\/?span[^>]*>/g,'').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');assert.equal(text,source);
assert.equal(highlight('<tag> -- code',false),'&lt;tag&gt; -- code');
const cases=[
 ['bad.vhd:4:7:error: missing ";" at end of declaration','Syntax','error','bad.vhd',4,7],
 ['bad.vhd:9:2: no declaration for "foo"','Name','error','bad.vhd',9,2],
 ['bad.vhd:7:5:error: can\'t match integer literal with type std_ulogic','Type / size','error','bad.vhd',7,5],
 ['ghdl:error: cannot find resource library "lpm"','Library','error',null,null,null],
 ['bad.vhd:9:2:warning: instance is not bound','Binding','warning','bad.vhd',9,2],
 ['ghdl:error: bound check failure at test.vhd:8','Runtime','error','test.vhd',8,null],
 ['tb.vhd:12:3:@10ns:(assertion failure): expected result','Assertion','error','tb.vhd',12,3],
 ['ERROR: [VRFC 10-4982] syntax error near end [F:/My Design/main.vhd:42:8]','Syntax','error','F:/My Design/main.vhd',42,8],
 ['WARNING: [VRFC 10-1] type mismatch [F:\\My Design\\main.vhd:17]','Type / size','warning','F:\\My Design\\main.vhd',17,null],
 ['tb.vhd:2:3:@10ns:(report note): ALL TESTS PASSED','General','note','tb.vhd',2,3],
];
for(const [log,kind,severity,file,line,column] of cases){const result=parse(log);assert.equal(result.length,1,log);assert.deepEqual([result[0].category,result[0].severity,result[0].file,result[0].line,result[0].column],[kind,severity,file,line,column],log);}
let result=parse('Failure: Assertion failed\nTime: 10 ns Iteration: 0 Process: /tb/line__12 File: C:/temp/tb.vhd');assert.equal(result[0].file,'C:/temp/tb.vhd');assert.equal(result[0].line,12);
assert.equal(parse('Failure: expected result')[0].category,'Assertion');
assert.equal(parse('INFO: [VRFC 10-163] Analyzing file\n$ ghdl -a file.vhd').length,0);
assert.equal(parse('bad.vhd:1:1:error: test\nbad.vhd:1:1:error: test').length,1);
assert.equal(parse('unrecognized simulator failure',true)[0].severity,'error');
assert.equal(parse('WARNING: harmless\nbackend stopped',true).length,2);
assert.equal(category('An unrecognized compiler message'),'General');
console.log('PASS: VHDL tokens preserve source, HTML escaping, GHDL/XSim locations and diagnostic categories, deduplication and failure fallback.');
