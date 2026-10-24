/* Local VHDL highlighting and compiler diagnostic presentation. No network dependencies. */
(function(root){
'use strict';
const keywords=new Set(('abs access after alias all and architecture array assert assume assume_guarantee attribute begin block body buffer bus case component configuration constant context cover default disconnect downto else elsif end entity exit fairness file for force function generate generic group guarded if impure in inertial inout is label library linkage literal loop map mod nand new next nor not null of on open or others out package parameter port postponed procedure process property protected pure range record register reject release rem report restrict restrict_guarantee return rol ror select sequence severity shared signal sla sll sra srl strong subtype then to transport type unaffected units until use variable vmode vprop vunit wait when while with xnor xor').split(' '));
const types=new Set('bit bit_vector boolean character integer natural positive real time string severity_level std_logic std_ulogic std_logic_vector std_ulogic_vector signed unsigned ufixed sfixed float float32 float64 line text'.split(' '));
const escape=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function highlight(source,vhdl=true){
 if(!vhdl)return escape(source);
 const token=/--[^\r\n]*|(?:\d+)?(?:[us]?[boxd])?"(?:""|[^"\r\n])*"|'[^\r\n]'|\\[^\r\n\\]*\\|\b\d[\d_]*#[\da-f_.]+#(?:e[+-]?[\d_]+)?|\b\d[\d_]*(?:\.\d[\d_]*)?(?:e[+-]?[\d_]+)?|\b[a-z][a-z\d_]*\b|[<>=:+*/&|?'-]+/gi;
 let html='',offset=0;
 for(const m of source.matchAll(token)){
  html+=escape(source.slice(offset,m.index));const text=m[0],word=text.toLowerCase();let kind='';
  if(text.startsWith('--'))kind='comment';
  else if(text.includes('"')||/^'.'$/.test(text))kind='string';
  else if(/^\d/.test(text))kind='number';
  else if(keywords.has(word))kind='keyword';
  else if(types.has(word))kind='type';
  else if(/^(true|false|ns|ps|fs|us|ms|sec|min|hr|note|warning|error|failure)$/i.test(text))kind='literal';
  else if(/^[<>=:+*/&|?'-]+$/.test(text))kind='operator';
  html+=kind?'<span class="vhdl-'+kind+'">'+escape(text)+'</span>':escape(text);offset=m.index+text.length;
 }
 return html+escape(source.slice(offset));
}
function category(message){
 if(/assertion|assert\b|severity\s*(?:failure|error)/i.test(message))return 'Assertion';
 if(/bound check|out of (?:bounds|range)|index.*(?:range|bound)|division by zero|divide by zero|overflow|simulation failed/i.test(message))return 'Runtime';
 if(/cannot find (?:resource )?library|library.*(?:not found|missing)|unit .*not found in library|synopsys package|package .*not (?:found|analysed|analyzed)|cannot find.*package/i.test(message))return 'Library';
 if(/no declaration|not declared|undeclared|unknown identifier|cannot find declaration|identifier .*not found/i.test(message))return 'Name';
 if(/syntax|unexpected|expected|missing .*;|missing.*(?:end|semicolon)|parse error/i.test(message))return 'Syntax';
 if(/type|overload|width|length|size mismatch|cannot match|can't match|cannot convert|can't resolve/i.test(message))return 'Type / size';
 if(/not bound|binding|port.*(?:association|map|connect)|formal|actual|elaborat|cannot find entity|not analysed|not analyzed|multiple drivers/i.test(message))return 'Binding';
 if(/not found|could not launch|cannot.*(?:launch|start)|DLL|timed? out|time limit|exceeded|GHDL_PATH|Vivado.*launcher/i.test(message))return 'Tool / setup';
 return 'General';
}
function parse(log,failed=false){
 const items=[];
 const add=(severity,message,file=null,line=null,column=null,code=null)=>items.push({severity:/failure|fatal|error/i.test(severity)?'error':/warn/i.test(severity)?'warning':'note',message:message.trim(),file,line:line?Number(line):null,column:column?Number(column):null,code,category:category(message)});
 for(const raw of String(log||'').split(/\r?\n/)){
  const text=raw.trim();if(!text||text.startsWith('$ '))continue;
  // GHDL analysis and runtime: file:line:column[:@time]:(report/assertion severity): message.
  let m=/^(.+?\.vhdl?):(\d+):(\d+):(?:@[^:]+:)?\s*(?:\((report|assertion)\s+(note|warning|error|failure)\):\s*|(warning|error|note|fatal):\s*)?(.*)$/i.exec(text);
  if(m){add(m[5]||m[6]||'error',(m[4]==='assertion'?'Assertion: ':'')+m[7],m[1],m[2],m[3]);continue;}
  // Some compiler versions omit the column.
  m=/^(?!(?:ERROR|CRITICAL WARNING|WARNING|INFO|Note|Failure|Fatal):)(.+?\.vhdl?):(\d+):\s*(?:(warning|error|note|fatal):\s*)?(.*)$/i.exec(text);
  if(m){add(m[3]||'error',m[4],m[1],m[2]);continue;}
  // Native GHDL can put the runtime location on the following stack line.
  m=/^from:\s+.*?\bat\s+(.+?\.vhdl?):(\d+)(?::(\d+))?\s*$/i.exec(text);
  if(m&&items.length){const item=items.at(-1);if(!item.file){item.file=m[1];item.line=Number(m[2]);item.column=m[3]?Number(m[3]):null;}continue;}
  // Vivado compiler: ERROR: [VRFC 10-...] message [C:/path/file.vhd:line[:column]].
  m=/^(ERROR|CRITICAL WARNING|WARNING|INFO|Note|Failure|Fatal):\s*(?:\[([^\]]+)\]\s*)?(.*)$/i.exec(text);
  if(m){
   if(m[1].toUpperCase()==='INFO')continue;
   let message=m[3];const loc=/\[([^\]]+\.vhdl?):(\d+)(?::(\d+))?\]\s*$/i.exec(message);
   if(loc)message=message.slice(0,loc.index).trim();
   add(m[1],message,loc?.[1],loc?.[2],loc?.[3],m[2]);
   if(/^failure$/i.test(m[1]))items.at(-1).category='Assertion';
   continue;
  }
  // XSim runtime follows the message with Time/Process/File details.
  m=/\bFile:\s*(.+?\.vhdl?)(?:\s+Line:\s*(\d+))?\s*$/i.exec(text);
  if(m&&items.length){const item=items.at(-1);if(!item.file){item.file=m[1];item.line=Number(m[2]||(/\/line__(\d+)/.exec(text)||[])[1])||null;}continue;}
  m=/^(?:.*(?:ghdl|xsim|xelab)(?:\.exe)?):(?:\s*)?(error|warning|fatal):\s*(.*)$/i.exec(text);
  if(m){const loc=/\bat\s+([^()\r\n]+?\.vhdl?):(\d+)(?::(\d+))?\s*$/i.exec(m[2]);add(m[1],m[2],loc?.[1],loc?.[2],loc?.[3]);}
 }
 if(failed&&!items.some(i=>i.severity==='error'))add('error',String(log||'Simulation failed. See Terminal for details.').trim());
 const seen=new Set();return items.filter(i=>{const key=JSON.stringify(i);if(seen.has(key))return false;seen.add(key);return true;});
}
// Advice is explanatory, never a source rewrite or a claim of semantic correctness.
function advice(item){
 const message=item.message;
 if(item.severity==='note')return null;
 const rules=[
  [/semicolon|';'.*expected|missing.*;/i,'Check the end of this statement and the preceding line. Add a semicolon only where a declaration or statement ends; do not add one after then or loop.'],
  [/no declaration|not declared|undeclared|unknown identifier|cannot find declaration/i,'Check spelling and scope. Declare the signal, variable or constant before use. If it belongs to a package, check its library and use clauses. VHDL identifiers are case-insensitive.'],
  [/bound check|out of (?:bounds|range)|index.*(?:range|bound)/i,'Check the reported index, vector bounds and generic values. Use signal\'length, signal\'range or signal\'high where appropriate. A runtime bound failure may occur on an assignment as well as an index.'],
  [/division by zero|divide by zero/i,'Check the divisor at the failing simulation time. Guard the operation against zero or correct the value that produces it.'],
  [/width|length|size mismatch/i,'Compare the lengths and ranges on both sides. For signed or unsigned arithmetic, consider resize(value, target\'length); choose truncation and sign behavior deliberately.'],
  [/synopsys package/i,'Consider IEEE numeric_std with signed or unsigned arithmetic. Legacy Synopsys packages require compiler support and may conflict with numeric_std; do not mix arithmetic packages blindly.'],
  [/cannot find (?:resource )?library|unit .*not found in library|package .*not (?:found|analysed|analyzed)|cannot find.*package/i,'Import the missing package source and check its library name. Compile dependencies before the units that use them; verify library IEEE; and the required use clause for IEEE types.'],
  [/not bound|binding|port.*(?:association|map|connect)|formal|actual|cannot find entity|not analysed|not analyzed/i,'Check the selected top entity, entity/component names, port names, directions and types, and generic values. Ensure the entity source is included and compiled successfully.'],
  [/multiple drivers/i,'Find all processes and concurrent assignments driving this signal. Use one owner where appropriate; resolved std_logic can combine drivers but conflicting values may produce X.'],
  [/assertion|severity\s*(?:failure|error)/i,'Read the assertion condition and its report, then inspect the stimulus and signal values at the reported time. An assertion failure may reveal a design bug or an incorrect test expectation.'],
  [/type|overload|cannot match|can't match|cannot convert|can't resolve/i,'Compare the operand and destination types. With numeric_std, use unsigned(vector) or signed(vector) for arithmetic and std_logic_vector(result) for conversion back. Use to_unsigned or to_signed for integers with an explicit width.'],
  [/expected|unexpected|syntax|parse error/i,'Inspect this token and the preceding statement. Check punctuation and matching end if, end case, end loop and end process. Fix the earliest syntax error first; later messages may be consequences.'],
  [/overflow/i,'Check the arithmetic range and destination type. Widen the operands before the operation when needed; widening only the result may be too late.'],
  [/DLL|could not launch|cannot.*(?:launch|start)|GHDL_PATH/i,'Check the simulator installation and its dependencies. With the portable edition, try Start-Nexys-Lab-Compatible.cmd and keep the complete runtime folder together.']
 ];
 const match=rules.find(([pattern])=>pattern.test(message));
 return match?match[1]:null;
}
function sourceContext(item,files){
 const leaf=name=>String(name||'').replace(/\\/g,'/').split('/').at(-1).toLowerCase();
 const entry=Object.entries(files||{}).find(([name])=>leaf(name)===leaf(item.file));
 if(!entry||!item.line)return null;
 const lines=entry[1].split(/\r?\n/),index=item.line-1;
 if(index<0||index>=lines.length)return null;
 return lines.slice(Math.max(0,index-1),index+2).map((text,n)=>`${Math.max(0,index-1)+n+1} | ${text}`).join('\n');
}
function mount({editor,paint,gutter,filename,panel,badge,onNavigate,getFiles=()=>({})}){
 let items=[],cached='',cachedLanguage=null,hasRun=false;
 const summary=document.createElement('p');summary.id='problem-summary';summary.setAttribute('role','status');
 const toolbar=document.createElement('div');toolbar.className='problem-filters';
 function filter(label,values){const wrapper=document.createElement('label');wrapper.textContent=label+' ';const select=document.createElement('select');select.setAttribute('aria-label',label);for(const value of values){const option=document.createElement('option');option.value=value;option.textContent=value;select.append(option);}select.onchange=render;wrapper.append(select);toolbar.append(wrapper);return select;}
 const severity=filter('Severity',['All','error','warning','note']);
 const kind=filter('Category',['All','Syntax','Name','Type / size','Library','Binding','Runtime','Assertion','Tool / setup','General']);
 const list=document.createElement('div');list.id='problem-list';
 const hint=document.createElement('p');hint.className='problem-hint';hint.textContent='Categories are inferred from compiler messages. Run validates the code; highlighting alone does not. Full output is retained in Terminal.';
 panel.replaceChildren(summary,toolbar,list,hint);
 const basename=name=>String(name||'').replace(/\\/g,'/').split('/').at(-1).toLowerCase();
 function sync(){paint.style.transform=`translate(${-editor.scrollLeft}px, ${-editor.scrollTop}px)`;gutter.scrollTop=editor.scrollTop;}
 function refresh(){
  const source=editor.value,vhdl=/\.vhdl?$/i.test(filename());
  if(source!==cached||vhdl!==cachedLanguage){paint.innerHTML=highlight(source,vhdl)+'\n';cached=source;cachedLanguage=vhdl;}
  const fragment=document.createDocumentFragment();
  for(let n=1;n<=source.split('\n').length;n++){
   const row=document.createElement('span');row.textContent=n;const matches=items.filter(i=>i.line===n&&basename(i.file)===basename(filename()));
   if(matches.length){row.className='line-'+(matches.some(i=>i.severity==='error')?'error':matches.some(i=>i.severity==='warning')?'warning':'note');row.title=matches.map(i=>i.message).join('\n');}
   fragment.append(row);
  }
  gutter.replaceChildren(fragment);sync();
 }
 function render(){
  const errors=items.filter(i=>i.severity==='error').length,warnings=items.filter(i=>i.severity==='warning').length;
  badge.textContent=`Problems (${items.length})`;
  summary.textContent=hasRun?`${errors} errors · ${warnings} warnings · ${items.length-errors-warnings} notes`:'Run to check the current source. Previous results are cleared when the design changes.';
  list.replaceChildren();
  for(const item of items.filter(i=>(severity.value==='All'||i.severity===severity.value)&&(kind.value==='All'||i.category===kind.value))){
   const row=document.createElement('div');row.className='problem-row '+item.severity;
   const meta=document.createElement('strong');meta.textContent=item.severity.toUpperCase()+' · '+item.category+(item.code?' · '+item.code:'');
   const message=document.createElement('div');message.textContent=item.message;
   row.append(meta,message);
   const context=sourceContext(item,getFiles());
   if(context){const preview=document.createElement('pre');preview.className='problem-source';preview.textContent=context;row.append(preview);}
   const suggestion=advice(item);
   if(suggestion){const help=document.createElement('p');help.className='problem-advice';help.textContent='Suggested checks: '+suggestion;row.append(help);}
   if(item.file){const jump=document.createElement('button');jump.className='problem-location';jump.textContent=item.file+(item.line?':'+item.line:'')+(item.column?':'+item.column:'');jump.onclick=()=>onNavigate(item);row.append(jump);}
   list.append(row);
  }
  if(hasRun&&!list.children.length){const empty=document.createElement('p');empty.textContent=items.length?'No diagnostics match the selected filters.':'No compiler diagnostics reported. Testbench coverage determines functional correctness.';list.append(empty);}
  refresh();
 }
 editor.addEventListener('scroll',sync);render();
 return {refresh,sync,clear(){items=[];hasRun=false;render();},setLog(log,failed=false){items=parse(log,failed);hasRun=true;render();return items;}};
}
const api={highlight,parse,category,advice,sourceContext,mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.NexysEditor=api;
})(typeof window!=='undefined'?window:globalThis);
