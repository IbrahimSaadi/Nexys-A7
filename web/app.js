'use strict';
const $ = id => document.getElementById(id);
let files = {}, current = '', commands = [], mapping = {}, sw = 0, busy = false, last = null;
const storageKey = 'nexys-lab-project-v1';
let projectInfo = null, rawInputs = {}, userClocks = {}, mappingOverrides = {}, pinCatalog = null, catalogView = null;
function xdcControls(name){return(projectInfo?.bindings.mapping[name]||[]).some(b=>b.source==='xdc')||(projectInfo?.bindings.warnings||[]).some(w=>w.toLowerCase().includes(name.toLowerCase())&&/conflict|unknown pin|unresolved/i.test(w));}
const inspector = NexysSignals.mount($('signal-inspector'), {
  onInput(name,bits) { rawInputs[name]=bits;save(); },
  onClock(name,config) {userClocks[name]=config;if(config)delete rawInputs[name];stopLive();$('input-status').textContent='Clock configuration changed. Press Run to apply.';save();}
});
const editorTools = NexysEditor.mount({editor:$('editor'),paint:$('syntax-highlight'),gutter:$('lines'),filename:()=>current,panel:$('problems'),badge:$('problems-tab'),onNavigate:goToProblem});
function showLog(log,failed=false) { $('console').textContent=log; const items=editorTools.setLog(log,failed);if(failed)document.querySelector('[data-tab="problems"]').click();return items; }
function goToProblem(problem) {
  const leaf=String(problem.file).replace(/\\/g,'/').split('/').at(-1).toLowerCase();
  const file=Object.keys(files).find(name=>name.toLowerCase()===leaf);
  if(!file)return toast('This diagnostic refers to a generated or external file, not a project source.');
  openFile(file);
  const lines=files[file].split('\n'),line=Math.max(0,Math.min(lines.length-1,(problem.line||1)-1));
  const start=lines.slice(0,line).reduce((n,text)=>n+text.length+1,0);
  const column=Math.max(0,Math.min(lines[line].length,(problem.column||1)-1));
  const editor=$('editor');editor.focus();editor.setSelectionRange(start+column,problem.column?Math.min(start+column+1,start+lines[line].length):start+lines[line].length);
  const height=parseFloat(getComputedStyle(editor).lineHeight);editor.scrollTop=Math.max(0,line*height-editor.clientHeight/3);editor.scrollLeft=0;
  if(column>60)editor.scrollLeft=(column-20)*parseFloat(getComputedStyle(editor).fontSize)*0.6;
  updateLines();editorTools.sync();
}
function restoreSampling(project){
 $('batch-mode').value=project.batchMode==='fixed'?'fixed':'auto';
 const ns=project.sampleInterval;
 $('frame-quantum').value=Number.isInteger(ns)&&ns>=10&&ns<=10000000&&ns%10===0?ns:1000000;
}
for(const id of ['batch-mode','frame-quantum'])$(id).onchange=()=>{pacing.reset();save();};
function genericValues() {
  const value=JSON.parse($('project-generics').value||'{}');
  if (!value || Array.isArray(value) || typeof value!=='object') throw Error('Generic values must be a JSON object');
  return value;
}
async function inspectProject() {
  const response=await fetch('/api/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files,top:$('top').value,generics:genericValues()})});
  const data=await response.json();if(!response.ok||data.error) throw Error(data.error||'Inspection failed');
  projectInfo=data;$('top').value=data.top;mapping={...data.mapping};for(const[name,target]of Object.entries(mappingOverrides))if(name in mapping&&!xdcControls(name))mapping[name]=target;
  $('entity-options').replaceChildren();for(const name of data.entities){const option=document.createElement('option');option.value=name;$('entity-options').append(option);}
  const preview={ports:data.ports,mapping,clocks:{...data.clocks,...userClocks},input_values:{},wave:{values:{}}};
  inspector.update(preview);inspector.setInputs(rawInputs);inspector.setClocks(preview.clocks);renderMapping(preview);
  if(pinCatalog && NexysSignals.renderCatalog) catalogView=NexysSignals.renderCatalog($('pin-catalog'),pinCatalog,data.bindings,preview);
  if(data.bindings.warnings.length) $('console').textContent='XDC inspection:\n'+data.bindings.warnings.join('\n');
  updateProjectGuidance();save();return data;
}
function physicalInputs(buttons) {
  const result={...rawInputs};
  const clocks={...projectInfo?.clocks,...userClocks};for(const[name,config]of Object.entries(clocks))if(config)delete result[name];
  for(const p of projectInfo?.ports||[]) {
    if(!['in','inout'].includes(p.direction)||Object.hasOwn(rawInputs,p.name))continue;
    const bits=(last?.input_values?.[p.name]||((p.direction==='inout'?'Z':'0').repeat(p.width))).split('');let assigned=false;
    for(const binding of projectInfo.bindings.mapping[p.name]||[]) {
      const signal=binding.signal;let value;
      const match=/^sw\[(\d+)\]$/.exec(signal||'');
      if(match)value=String((sw>>Number(match[1]))&1);
      else if(['btnC','btnU','btnL','btnR','btnD'].includes(signal))value=buttons.includes(signal)?'1':'0';
      else if(signal==='cpu_resetn')value=buttons.includes('cpu_resetn')?'0':'1';
      if(value!==undefined){const pos=p.vector?(p.left<=p.right?binding.index-p.left:p.left-binding.index):0;bits[pos]=value;assigned=true;}
    }
    if(assigned)result[p.name]=bits.join('');
  }
  return result;
}
function releasePhysicalOverride(signal) {
  for(const [name,bits] of Object.entries(projectInfo?.bindings.mapping||{})) if(bits.some(b=>b.signal===signal || (signal==='sw'&&b.signal?.startsWith('sw['))))delete rawInputs[name];
}
const photoKey = 'nexys-lab-board-photo-v1';
function setBoardPhoto(source) {
  $('pcb-art').src = source || 'board.svg';
  $('physical-board').classList.toggle('photo-board',Boolean(source));
  $('physical-board').classList.toggle('manufacturer-photo',source === 'nexys-a7-photo.jpg');
  $('photo-status').textContent = source ? 'Digilent board photograph · controls and display use live VHDL outputs.' : 'Vector view. Choose Board photo to restore the manufacturer photograph.';
}
$('choose-photo').onclick = () => { localStorage.removeItem(photoKey);setBoardPhoto('nexys-a7-photo.jpg'); };
$('upload-photo').onclick = () => $('photo-upload').click();
$('default-art').onclick = () => { localStorage.setItem(photoKey,'vector'); setBoardPhoto(null); };
$('photo-upload').onchange = async event => {
  const file=event.target.files[0]; if(!file) return;
  try {
    if(!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size>3000000) throw Error('Choose a PNG, JPG or WebP image smaller than 3 MB.');
    const source=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read photo'));reader.readAsDataURL(file);});
    const photo=new Image(); photo.src=source; await photo.decode();
    if(Math.abs(photo.width/photo.height-600/550)>.03) throw Error('Use the front-facing reference photo at 600 × 550 (or the same proportions), without a desk or extra margins.');
    setBoardPhoto(source);
    try {localStorage.setItem(photoKey,source);}catch{toast('Photo loaded for this session. Browser storage is full.');}
  }catch(error){toast(error.message);}
  event.target.value='';
};
let liveToken = null, paused = false, liveGeneration = 0, simNs = 0, wallStart = 0, liveTimer = null;
let pausedAt = 0, pausedWall = 0, lastPaint = -Infinity;
const pacing = new NexysPacing.Controller();
const holds = new Map();
const activeWallMs = () => (paused ? pausedAt : performance.now()) - wallStart - pausedWall;
function updateProjectGuidance() {
  const board = $('mode').value === 'board';
  $('usage-help').textContent = board
    ? 'Import VHDL and XDC, inspect the project, select the top entity, then press Run. Use mapped board controls or Signals to drive inputs and observe outputs.'
    : 'Select the testbench entity, simulation engine and duration, then press Run. The testbench supplies stimuli; inspect Terminal and Waveforms for results.';
  for (const button of document.querySelectorAll('[data-button]')) {
    const label = controlLabel(button.dataset.button);
    button.title = label; button.setAttribute('aria-label',label);
  }
}
function controlLabel(signal) {
  const connected = [];
  for (const [name,bits] of Object.entries(projectInfo?.bindings.mapping || {})) {
    for (const bit of bits) if (bit.signal === signal) connected.push(name+(bit.index == null ? '' : '['+bit.index+']'));
  }
  return signal.toUpperCase() + (connected.length ? ' · '+connected.join(', ') : '');
}
function clearInspection() {
  projectInfo = null; inspector.reset(); renderMapping({});
  $('entity-options').replaceChildren();
  if (pinCatalog && NexysSignals.renderCatalog) catalogView=NexysSignals.renderCatalog($('pin-catalog'),pinCatalog,{},{});
}
function newProject() {
  files={};mapping={};mappingOverrides={};rawInputs={};userClocks={};sw=0;
  clearInspection();$('top').value='main';$('mode').value='board';$('project-generics').value='{}';$('batch-mode').value='auto';$('frame-quantum').value='1000000';
  document.querySelectorAll('.switch').forEach(button=>{button.classList.remove('on');button.setAttribute('aria-pressed','false');});
  $('switch-value').textContent='0x0000';$('console').textContent='New project. Add or import VHDL files, then select the top entity.';
  openFile('');modeChanged(false);
}
async function liveRequest(action, body) {
  const response = await fetch('/api/live/' + action, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json(); if (!response.ok || data.error) throw Error(data.error || response.statusText); return data;
}
function stopLive() {
  ++liveGeneration; clearTimeout(liveTimer); const token = liveToken; liveToken = null; holds.clear();
  if (token) liveRequest('stop', {session:token}).catch(()=>{});
  document.querySelectorAll('[data-button]').forEach(b=>b.classList.remove('pressed'));
  $('run').innerHTML = '▶ Run simulation <kbd>Ctrl ↵</kbd>';
}
async function startLive() {
  if (liveToken) { stopLive(); $('result').textContent = 'Stopped'; return; }
  if (busy) return;
  busy = true; editorTools.clear(); $('run').disabled = true; $('result').textContent = 'Compiling VHDL…';
  const generation = ++liveGeneration;
  try {
    const info=await inspectProject();
    const data = await liveRequest('start', {files, top:$('top').value, mapping, timing:'original', generics:genericValues(),clocks:{...info.clocks,...userClocks},inputs:physicalInputs([]),board_bindings:info.bindings.mapping});
    if (generation !== liveGeneration) { await liveRequest('stop',{session:data.session}); return; }
    liveToken = data.session; mapping = data.mapping; simNs = 0; paused = false; holds.clear(); wallStart = performance.now(); pausedWall = 0;lastPaint=-Infinity;pacing.reset();last=data;
    $('input-status').textContent = 'Running · '+$('top').value+'. Drive inputs using the mapped board controls or Signals.';
    $('pause').textContent = 'Ⅱ Pause'; $('run').textContent = '■ Stop simulation'; showLog(data.log);
    renderBoard(data); renderMapping(data); save();
    const pump = async () => {
      if (!liveToken || generation !== liveGeneration) return;
      if (paused) { liveTimer = setTimeout(pump, 100); return; }
      try {
        const begin = performance.now();
        const presses = [...holds].filter(([,press])=>press.remainingNs > 0);
        const buttons = presses.map(([name])=>name);
        const quantum = pacing.interval(Number($('frame-quantum').value),$('batch-mode').value==='auto',Math.min(Infinity,...presses.map(([,press])=>press.remainingNs)));
        const frame = await liveRequest('advance', {session:liveToken, sw, buttons:buttons.filter(b=>b!=='cpu_resetn'), ns:quantum,wave_history:false,inputs:physicalInputs(buttons)});
        if (generation !== liveGeneration) return;
        const requestMs=performance.now()-begin;
        pacing.observe(quantum,frame.performance?.simulator_wait_ms);
        frame.wave=NexysPacing.mergeWave(last?.wave,frame.wave);
        simNs = frame.sim_ns; last = frame;
        for (const [name,press] of presses) if (holds.get(name) === press) { press.remainingNs-=quantum; if(press.remainingNs<=0) holds.delete(name); }
        if (buttons.length) $('input-status').textContent = buttons.map(controlLabel).join('; ')+' delivered to VHDL. Observe your design outputs.';
        const wall = activeWallMs()/1000, sim = simNs/1e9;
        if(performance.now()-lastPaint>=1000/30){
          const uiStart=performance.now();
          renderBoard(frame);
          if(!$('waves').hidden)renderWaves(frame.wave);
          if(!$('signals').hidden)inspector.update(frame);
          if(!$('pins').hidden)catalogView?.update?.(frame);
          $('sim-time').textContent = sim.toFixed(6) + ' s'; $('wall-time').textContent = wall.toFixed(2)+' s';
          $('sim-speed').textContent = (sim/Math.max(wall,0.001)).toFixed(4)+'× · 1 HDL s ≈ '+Math.round(wall/Math.max(sim,1e-9))+' wall s';
          const uiMs=performance.now()-uiStart,metrics=frame.performance||{};
          $('performance-details').textContent='Batch: '+quantum.toLocaleString()+' ns · '+$('batch-mode').value+'\nSimulator wait: '+(metrics.simulator_wait_ms||0).toFixed(1)+' ms · Frame build: '+(metrics.frame_build_ms||0).toFixed(1)+' ms\nHTTP/JSON overhead ≈ '+Math.max(0,requestMs-(metrics.backend_ms||0)).toFixed(1)+' ms · UI update: '+uiMs.toFixed(1)+' ms\nBehind wall time: '+Math.max(0,wall-sim).toFixed(3)+' s';
          lastPaint=performance.now();
        }
        $('result').textContent = paused ? 'Paused' : '● Running · original timing'; $('result').style.color = '#b5ec69';
        document.querySelectorAll('[data-button]').forEach(b=>b.classList.toggle('pressed',holds.has(b.dataset.button)));
        // Never run ahead of wall time; slower simulation remains visibly slower.
        const wait = Math.max(0, sim*1000-activeWallMs());
        liveTimer = setTimeout(pump,wait);
      } catch (error) { if (generation === liveGeneration) { stopLive(); showLog(error.message,true); $('result').textContent = 'Simulator stopped'; } }
    };
    pump();
  } catch (error) { showLog(error.message,true); $('result').textContent = 'Compilation failed'; }
  finally { busy = false; $('run').disabled = false; }
}
function toast(message) { $('toast').textContent = message; $('toast').classList.add('show'); setTimeout(() => $('toast').classList.remove('show'), 3000); }
function save() {
  try { localStorage.setItem(storageKey, JSON.stringify({files, current, top: $('top').value, mode: $('mode').value, timing:'original', mapping,mappingOverrides,rawInputs,userClocks,generics:genericValues(),batchMode:$('batch-mode').value,sampleInterval:Number($('frame-quantum').value),engine:$('engine').value})); $('saved').textContent = '● Saved locally'; }
  catch { $('saved').textContent = 'Storage full · export your project'; }
}
function resetHistory() { stopLive();pacing.reset();$('performance-details').textContent='Run to measure simulator, transfer and interface time.'; editorTools.clear(); commands = []; last = null; simNs = 0; renderBoard({}); renderWaves(null); updateProjectGuidance(); $('result').textContent = 'Session reset'; $('input-status').textContent=Object.keys(files).length ? ($('mode').value==='board'?'Press Run to simulate the selected top entity. Use mapped controls or Signals to drive inputs.':'Select a testbench entity and press Run. Stimuli come from the testbench.') : 'Add or import VHDL files to begin a new project.'; $('sim-time').textContent='0.000000 s'; $('wall-time').textContent='0.00 s'; $('sim-speed').textContent='—'; }
function fileList() {
  $('files').replaceChildren();
  for (const name of Object.keys(files)) {
    const button = document.createElement('button');
    button.className = name === current ? 'active' : '';
    const icon = document.createElement('span'); icon.textContent = /vhdl?$/i.test(name) ? '◇' : '≡';
    button.append(icon, document.createTextNode(name)); button.onclick = () => openFile(name);
    $('files').append(button);
  }
}
function openFile(name) { current = name; $('editor').value = files[name] || ''; $('filename').textContent = name || 'No file selected'; fileList(); updateLines(); save(); }
function updateLines() {
  const editor = $('editor'); editorTools.refresh();
  const before = editor.value.slice(0, editor.selectionStart).split('\n'); $('cursor').textContent = `Ln ${before.length}, Col ${before.at(-1).length + 1}`;
}
$('editor').addEventListener('input', () => { if (current) files[current] = $('editor').value;  clearInspection(); resetHistory(); updateLines(); save(); });
$('editor').addEventListener('click', updateLines); $('editor').addEventListener('keyup', updateLines);
$('editor').addEventListener('keydown', e => { if (e.key === 'Tab') { e.preventDefault(); const a = e.target.selectionStart, b = e.target.selectionEnd; e.target.setRangeText('    ', a, b, 'end'); e.target.dispatchEvent(new Event('input')); } });
$('new-file').onclick = () => { const name = prompt('File name, for example counter.vhd'); if (!name) return; if (!/^[\w.-]+\.(vhd|vhdl|xdc|txt)$/i.test(name)) return toast('Use a .vhd, .vhdl, .xdc or .txt file name'); if (name in files) return toast('File already exists'); files[name] = ''; clearInspection();openFile(name); resetHistory();save(); };
$('new-project').onclick = () => {if(Object.keys(files).length&&!confirm('Create an empty project? Export your current project first to keep a backup.'))return;newProject();};
$('inspect').onclick = () => inspectProject().then(()=>{document.querySelector('[data-tab="signals"]').click();toast('Ports and XDC bindings inspected');}).catch(error=>{$('console').textContent=error.message;toast(error.message);});
$('project-generics').onchange = () => {stopLive();try{genericValues();save();}catch(error){toast(error.message);}};
$('delete-file').onclick = () => { if (current && confirm(`Delete ${current}?`)) { delete files[current]; clearInspection();resetHistory(); openFile(Object.keys(files)[0] || ''); } };
function download(name, text, type = 'text/plain') { const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
$('export').onclick = () => download('nexys-project.json', JSON.stringify({files, top: $('top').value, mode: $('mode').value, timing:'original',mapping,mappingOverrides,rawInputs,userClocks,generics:genericValues(),batchMode:$('batch-mode').value,sampleInterval:Number($('frame-quantum').value)}, null, 2), 'application/json');
$('download-vcd').onclick = () => {
  if (last?.vcd) return download('signals.vcd',last.vcd);
  if (!last?.wave) return toast('Run a simulation first');
  const names=Object.keys(last.wave.values), ids=Object.fromEntries(names.map((n,i)=>[n,'s'+i]));
  let text='$comment Sampled live outputs only; use Testbench mode for full clock-resolution VCD. $end\n$timescale 1 fs $end\n$scope module live_samples $end\n';
  for(const name of names) text+='$var wire '+last.wave.values[name].length+' '+ids[name]+' '+name.replace(/\W/g,'_')+' $end\n';
  text+='$upscope $end\n$enddefinitions $end\n';
  let previous=-1;
  for(const [stamp,name,value] of last.wave.events) { if(stamp!==previous){text+='#'+stamp+'\n';previous=stamp;} text+='b'+value+' '+ids[name]+'\n'; }
  download('live-samples.vcd',text); toast('Exported sampled outputs, not a full clock trace');
};
$('import').onclick = () => $('upload').click();
$('upload').onchange = async e => {
  stopLive();clearInspection();
  try {
    for (const file of e.target.files) {
      if (file.size > 1000000) throw Error('File exceeds 1 MB');
      const text = await file.text();
      if (file.name.endsWith('.json')) { const project = JSON.parse(text); if (!project.files || typeof project.files !== 'object') throw Error('Invalid project JSON'); files = project.files; mapping = project.mapping || {};mappingOverrides=project.mappingOverrides||project.mapping||{};rawInputs=project.rawInputs||{};userClocks=project.userClocks||{};$('project-generics').value=JSON.stringify(project.generics||{});restoreSampling(project); $('top').value = project.top || ''; $('mode').value = project.mode || 'board'; }
      else { if (!/^[\w.-]+\.(vhd|vhdl|xdc|txt)$/i.test(file.name)) throw Error('Unsupported file type'); if (file.name in files && !confirm(`Replace ${file.name}?`)) continue; files[file.name] = text; }
    }
    resetHistory(); openFile(Object.keys(files)[0]); modeChanged(false);await inspectProject();toast('Files imported and ports inspected');
  } catch (err) { resetHistory();save();toast(err.message); }
  e.target.value = '';
};
async function loadExample(ask = true) {
  if (ask && !confirm('Replace the current project with the example project? Export your edits first.')) return;
  const response = await fetch('/api/example'); const project = await response.json(); files = project.files; mapping = {};mappingOverrides={};rawInputs={};userClocks={};clearInspection();$('project-generics').value='{}'; $('top').value = 'elevator_top'; $('mode').value = 'board'; resetHistory(); openFile('elevator_top.vhd'); modeChanged(false);
}
$('example').onclick = () => loadExample().catch(e => toast(e.message));
function modeChanged(resetTop = true) { const board = $('mode').value === 'board'; $('duration-label').hidden = board; $('pause').disabled = !board;$('engine').disabled=board; if (resetTop) { const choices=projectInfo?.entities||[];if(board&&$('top').value.toLowerCase().startsWith('tb'))$('top').value=projectInfo?.suggested_top||$('top').value;else if(!board){const tb=choices.find(name=>name.toLowerCase().startsWith('tb'));if(tb)$('top').value=tb;} } clearInspection();resetHistory(); save(); }
$('mode').onchange = () => modeChanged(); $('top').onchange = () => { clearInspection();resetHistory(); mapping = {}; save(); };
for (const button of document.querySelectorAll('[data-tab]')) button.onclick = () => {
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('selected', b === button));
  for (const tab of ['console', 'problems', 'waves', 'mapping','signals','pins']) $(tab).hidden = tab !== button.dataset.tab;
  if(last?.board){if(button.dataset.tab==='waves')renderWaves(last.wave);if(button.dataset.tab==='signals')inspector.update(last);if(button.dataset.tab==='pins')catalogView?.update?.(last);}
};
for (let i = 0; i < 16; i++) {
  const led = document.createElement('div'); led.className = 'led-unit'; led.innerHTML = `<div id="led-${i}" class="led"></div><span class="tiny">${i}</span>`; $('leds').append(led);
  const unit = document.createElement('div'); unit.className = 'led-unit'; const button = document.createElement('button'); button.className = 'switch'; button.setAttribute('aria-label', `Switch ${i}`); button.setAttribute('aria-pressed', 'false'); button.innerHTML = '<i></i>';
  button.onclick = () => { sw ^= 1 << i;releasePhysicalOverride('sw['+i+']'); button.classList.toggle('on', !!(sw & (1 << i))); button.setAttribute('aria-pressed', String(!!(sw & (1 << i)))); $('switch-value').textContent = '0x' + sw.toString(16).padStart(4, '0').toUpperCase(); };
  const label = document.createElement('span'); label.className = 'tiny'; label.textContent = i; unit.append(button, label); $('switches').append(unit);
}
const polygons = ['5,1 20,1 17,4 8,4','21,2 21,17 18,15 18,5','21,21 21,36 18,33 18,23','5,37 20,37 17,34 8,34','3,21 6,23 6,33 3,36','3,2 6,5 6,15 3,17','5,19 8,16 17,16 20,19 17,21 8,21'];
for (let i = 7; i >= 0; i--) { const digit = document.createElement('div'); digit.className = 'digit'; digit.id = `digit-${i}`; digit.innerHTML = `<svg viewBox="0 0 26 40">${polygons.map((p,j) => `<polygon data-segment="${j}" points="${p}"/>`).join('')}<circle cx="24" cy="37" r="1.3" fill="#364439"/></svg>`; $('display').append(digit); }
function integer(val) { return val && /^[01]+$/.test(val) ? parseInt(val, 2) : null; }
function renderBoard(result) {
  const values = result.wave?.values || {}; const ports = result.ports || [];
  const valueFor = target => { const p = ports.find(p => result.mapping?.[p.name] === target); if (!p) return null; const prefix='lab_board_tb.io_' + p.name.toLowerCase();const key = Object.keys(values).find(k => k===prefix||k.startsWith(prefix+'[')); return integer(values[key]); };
  const board=result.board_values||{};
  const door = valueFor('door'); let leds = valueFor('led') ?? (door || 0);
  for(let i=0;i<16;i++)if(board['led['+i+']']!==undefined){if(board['led['+i+']']==='1')leds|=1<<i;else leds&=~(1<<i);}
  for (let i = 0; i < 16; i++) $(`led-${i}`).classList.toggle('on', !!(leds & (1 << i)));
  $('board-status').textContent = result.ok?'LED BANK · 0x'+leds.toString(16).padStart(4,'0').toUpperCase():'NOT RUNNING';
  for(let i=0;i<2;i++){const rgb=['r','g','b'].map(c=>board['rgb['+i+'].'+c]==='1'?255:0);$('rgb-'+i).style.background='rgb('+rgb.join(',')+')';$('rgb-'+i).style.boxShadow=rgb.some(Boolean)?'0 0 8px rgb('+rgb.join(',')+')':'none';}
  const nibble=group=>{let n=0;for(let i=0;i<4;i++)if(board[group+'['+i+']']==='1')n|=1<<i;return n.toString(16).toUpperCase();};
  $('vga-level').textContent=Object.keys(board).some(k=>k.startsWith('vga_'))?'VGA raw #'+nibble('vga_r')+nibble('vga_g')+nibble('vga_b')+' HS:'+board.vga_hs+' VS:'+board.vga_vs:'VGA: raw signals';
  const history = result.wave?.events || []; const segPort = ports.find(p => result.mapping?.[p.name] === 'segment'); const anPort = ports.find(p => result.mapping?.[p.name] === 'an');
  let seg = null, an = null; const digits = {};
  // Sample after all changes at a timestamp, avoiding delta-cycle display ghosts.
  for (let index = 0; index < history.length;) {
    const time = history[index][0];
    while (index < history.length && history[index][0] === time) {
      const [, name, val] = history[index++];
      if (segPort && name.startsWith('lab_board_tb.io_' + segPort.name.toLowerCase())) seg = integer(val);
      if (anPort && name.startsWith('lab_board_tb.io_' + anPort.name.toLowerCase())) an = integer(val);
    }
    if (seg !== null && an !== null) for (let i = 0; i < 8; i++) if (!(an & (1 << i))) digits[i] = seg;
  }
  if (result.digits) result.digits.forEach((value,i)=>{ const v=integer(value); if(v!==null) digits[i]=v; });
  for (let i = 0; i < 8; i++) $(`digit-${i}`).querySelectorAll('polygon').forEach((p,j) => p.classList.toggle('on', digits[i] !== undefined && !(digits[i] & (1 << j))));
}
function renderMapping(result) {
  $('mapping-fields').replaceChildren();
  const options = ['clock', 'sw', ...Array.from({length:16},(_,i)=>'sw['+i+']'), 'btnC', 'btnU', 'btnL', 'btnR', 'btnD', 'led', 'segment', 'an', 'dp', 'door', 'zero', 'unused'];
  for (const p of result.ports || []) {
    const row = document.createElement('div'); row.className = 'map-row'; const label = document.createElement('label'); label.textContent = `${p.name} (${p.direction}, ${p.width} bit)`; const select = document.createElement('select');
    for (const option of options.filter(v => p.direction === 'in' ? ['clock','sw','btnC','btnU','btnL','btnR','btnD','zero'].includes(v)||v.startsWith('sw[') : ['led','segment','an','dp','door','unused'].includes(v))) { const opt = document.createElement('option'); opt.value = option; opt.textContent = option==='door'?'LED0':option; select.append(opt); }
    select.value = result.mapping[p.name];select.disabled=xdcControls(p.name);if(select.disabled)select.title='Physical XDC bindings take priority. Edit XDC or drive raw inputs in Signals.'; select.onchange = () => { mapping[p.name] = select.value;mappingOverrides[p.name]=select.value; resetHistory(); save(); }; row.append(label, select); $('mapping-fields').append(row);
  }
}
function renderWaves(wave) {
  $('waves').replaceChildren(); const help = document.createElement('div'); help.className = 'wave-help'; help.textContent = `Time: 0–${((wave?.end || 0)/1e6).toFixed(0)} ns · last 20,000 non-clock transitions · download VCD for all signals${wave?.truncated ? ' · preview truncated' : ''}`; $('waves').append(help);
  const signals = Object.keys(wave?.values || {}).filter(k => !k.includes('.dut.') && !k.endsWith('.clk') && !k.endsWith('.io_clk')).slice(0, 28);
  for (const name of signals) {
    const events = wave.events.filter(e => e[1] === name); if (!events.length) continue;
    const row = document.createElement('div'); row.className = 'wave-row'; const label = document.createElement('span'); label.textContent = name.replace(/^lab_board_tb\./, ''); label.title = name;
    const ns = 'http://www.w3.org/2000/svg'; const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 600 36'); svg.setAttribute('preserveAspectRatio', 'none');
    let d = ''; const end = Math.max(1, wave.end);
    events.slice(0, 1000).forEach((event, i) => { const x = event[0]/end*600, next = (events[i+1]?.[0] ?? end)/end*600; const v = integer(event[2]), y = v === 0 ? 27 : 9; d += `${i ? 'L' : 'M'}${x},${y} L${next},${y} `; if (event[2].length > 1 && next-x > 35) { const t = document.createElementNS(ns,'text'); t.setAttribute('x',x+5); t.setAttribute('y','23'); t.setAttribute('fill','#c6e1a9'); t.setAttribute('font-size','10'); t.textContent = v === null ? event[2] : v; svg.append(t); } });
    const path = document.createElementNS(ns, 'path'); path.setAttribute('d',d); path.setAttribute('stroke','#a7df6d'); path.setAttribute('fill','none'); path.setAttribute('stroke-width','1.3'); svg.prepend(path); row.append(label,svg); $('waves').append(row);
  }
}
async function run(extra = []) {
  if ($('mode').value === 'board') return startLive();
  if (busy) return; busy = true; editorTools.clear(); $('run').disabled = true; $('run').textContent = '◌ Simulating…'; $('result').textContent = ($('engine').value==='vivado'?'Vivado XSim':'GHDL')+' running';
  const oldCommands = commands.slice(); commands.push(...extra);
  try {
    const res = await fetch('/api/run', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files, top:$('top').value, mode:$('mode').value, duration:$('duration').value, fast:false, commands, mapping,generics:genericValues(),engine:$('engine').value,vivado_path:$('vivado-path').value})});
    const result = await res.json(); if (!res.ok || result.error) throw Error(result.error || res.statusText);
    showLog(result.log,!result.ok);
    $('result').textContent = result.ok ? '● Simulation passed' : '● ' + result.phase + ' failed'; $('result').style.color = result.ok ? '#b5ec69' : '#fa897f';
    last = result;
    if (!result.ok) { commands = oldCommands; document.querySelector('[data-tab="problems"]').click(); }
    if (result.board) { mapping = result.mapping; renderBoard(result); renderMapping(result); }
    renderWaves(result.wave); save();
  } catch (error) { commands = oldCommands; showLog(error.message,true); $('result').textContent = 'Simulation error'; }
  finally { busy = false; $('run').disabled = false; $('run').innerHTML = '▶ Run simulation <kbd>Ctrl ↵</kbd>'; }
}
$('run').onclick = () => run(); $('pause').onclick = () => { if (!liveToken) return; if(!paused){pausedAt=performance.now();paused=true;}else{pausedWall+=performance.now()-pausedAt;paused=false;} $('pause').textContent = paused ? '▶ Resume' : 'Ⅱ Pause'; $('result').textContent = paused ? 'Paused' : 'Running'; }; $('reset').onclick = () => { resetHistory(); if ($('mode').value === 'board') run(); };
document.querySelectorAll('[data-button]').forEach(button => button.onclick = () => { if (!liveToken) return toast('Press Run to start the continuous clock first');releasePhysicalOverride(button.dataset.button); holds.set(button.dataset.button,{remainingNs:30000000}); button.classList.add('pressed'); $('input-status').textContent = controlLabel(button.dataset.button)+' queued for VHDL.'; });
$('cpu-reset').onclick=()=>{if(!liveToken)return toast('Press Run first');releasePhysicalOverride('cpu_resetn');holds.set('cpu_resetn',{remainingNs:30000000});};
window.addEventListener('pagehide',()=>{if(liveToken)fetch('/api/live/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session:liveToken}),keepalive:true}).catch(()=>{});});
document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); } });
async function init() {
  $('vivado-path').value=localStorage.getItem('nexys-vivado-path')||'';
  try {const savedPhoto=localStorage.getItem(photoKey);setBoardPhoto(savedPhoto==='vector'?null:(savedPhoto||'nexys-a7-photo.jpg'));}catch{setBoardPhoto('nexys-a7-photo.jpg');}
  try { const saved = JSON.parse(localStorage.getItem(storageKey)); if (saved?.files && !Array.isArray(saved.files)) { files = saved.files; mapping = saved.mapping || {};mappingOverrides=saved.mappingOverrides||{};rawInputs=saved.rawInputs||{};userClocks=saved.userClocks||{};$('project-generics').value=JSON.stringify(saved.generics||{});restoreSampling(saved);$('engine').value=saved.engine||'ghdl'; $('top').value = saved.top || 'main'; $('mode').value = saved.mode || 'board';  openFile(saved.current || Object.keys(files)[0]||''); modeChanged(false); } else newProject(); }
  catch { newProject(); }
  try{pinCatalog=await(await fetch('/api/board')).json();if(NexysSignals.renderCatalog)catalogView=NexysSignals.renderCatalog($('pin-catalog'),pinCatalog,{},{});}catch{}
  try { const health = await (await fetch('/api/health', {cache:'no-store'})).json(); $('app-version').textContent = 'FPGA WORKSPACE · v' + (health.app_version || 'unknown'); if (!health.ok) { $('console').textContent = health.error; $('result').textContent = 'GHDL setup required'; toast('GHDL is unavailable. See Terminal for setup instructions.'); } } catch { toast('Backend is unavailable. Start python3 server.py'); }
}
init();
$('detect-engines').onclick=async()=>{try{localStorage.setItem('nexys-vivado-path',$('vivado-path').value);const data=await(await fetch('/api/engines',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vivado_path:$('vivado-path').value})})).json();$('engine-status').textContent='GHDL: '+(data.ghdl.ok?'ready':'not found')+' · XSim: '+(data.vivado.available?'detected; run a testbench to validate':data.vivado.error);}catch(error){$('engine-status').textContent=error.message;}};
$('test-vivado').onclick=async()=>{const button=$('test-vivado');button.disabled=true;$('engine-status').textContent='Compiling and running the installed XSim self-test…';try{const response=await fetch('/api/engines/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vivado_path:$('vivado-path').value})});const data=await response.json();showLog(data.log||data.error||'No test output',!data.ok);$('engine-status').textContent=data.ok?'Vivado XSim self-test passed on this computer.':'Vivado test failed. See Terminal for the exact diagnostic.';document.querySelector('[data-tab="console"]').click();}catch(error){$('engine-status').textContent=error.message;}finally{button.disabled=false;}};
