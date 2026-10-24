'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {parse,advice,sourceContext}=require('./web/editor-tools.js');
test('GHDL diagnostics preserve Windows paths and suggest syntax checks',()=>{
 const [item]=parse("C:\\project\\main.vhd:12:8: missing ';' at end of statement");
 assert.equal(item.file,'C:\\project\\main.vhd');
 assert.equal(item.line,12);assert.equal(item.column,8);
 assert.match(advice(item),/semicolon/);
});
test('runtime stack location belongs to the failure',()=>{
 const [item]=parse('ghdl.exe:error: bound check failure\nfrom: work.main(rtl).P0 at C:\\project\\main.vhd:42\nghdl.exe:error: simulation failed',true);
 assert.equal(item.line,42);assert.equal(item.category,'Runtime');
 assert.match(advice(item),/bounds/);
});
test('columnless diagnostics and Vivado locations',()=>{
 assert.equal(parse('main.vhdl:9: warning: unused declaration')[0].severity,'warning');
 const [item]=parse('ERROR: [VRFC 10-1] width mismatch [C:/project/main.vhd:8:4]');
 assert.equal(item.column,4);assert.match(advice(item),/resize/);
});
test('source context respects file and line; returns literal untrusted text',()=>{
 const files={'main.vhd':'first\n<script>\nthird\nfourth'};
 assert.equal(sourceContext({file:'C:/temp/main.vhd',line:2},files),'1 | first\n2 | <script>\n3 | third');
 assert.equal(sourceContext({file:'generated.vhd',line:2},files),null);
 assert.equal(sourceContext({file:'main.vhd',line:99},files),null);
});
test('notes and unfamiliar errors receive no invented solution',()=>{
 assert.equal(advice({severity:'note',message:'assertion passed'}),null);
 assert.equal(advice({severity:'error',message:'unfamiliar diagnostic'}),null);
 assert.match(advice({severity:'error',message:'no declaration for counter'}),/case-insensitive/);
});
