'use strict';
const $ = id => document.getElementById(id);
let files = {}, current = '', commands = [], mapping = {}, sw = 0, busy = false, last = null;
const storageKey = 'nexys-lab-project-v1';
function toast(message) { $('toast').textContent = message; $('toast').classList.add('show'); setTimeout(() => $('toast').classList.remove('show'), 3000); }
function save() {
  try { localStorage.setItem(storageKey, JSON.stringify({files, current, top: $('top').value, mode: $('mode').value, mapping})); $('saved').textContent = '● Saved locally'; }
  catch { $('saved').textContent = 'Storage full · export your project'; }
}
function resetHistory() { commands = []; last = null; renderBoard({}); $('result').textContent = 'Session reset'; }
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
  const editor = $('editor'); $('lines').textContent = editor.value.split('\n').map((_, i) => i + 1).join('\n'); $('lines').scrollTop = editor.scrollTop;
  const before = editor.value.slice(0, editor.selectionStart).split('\n'); $('cursor').textContent = `Ln ${before.length}, Col ${before.at(-1).length + 1}`;
}
$('editor').addEventListener('input', () => { if (current) files[current] = $('editor').value; resetHistory(); updateLines(); save(); });
$('editor').addEventListener('scroll', updateLines); $('editor').addEventListener('click', updateLines); $('editor').addEventListener('keyup', updateLines);
$('editor').addEventListener('keydown', e => { if (e.key === 'Tab') { e.preventDefault(); const a = e.target.selectionStart, b = e.target.selectionEnd; e.target.setRangeText('    ', a, b, 'end'); e.target.dispatchEvent(new Event('input')); } });
$('new-file').onclick = () => { const name = prompt('File name, for example counter.vhd'); if (!name) return; if (!/^[\w.-]+\.(vhd|vhdl|xdc|txt)$/i.test(name)) return toast('Use a .vhd, .vhdl, .xdc or .txt file name'); if (name in files) return toast('File already exists'); files[name] = ''; openFile(name); resetHistory(); };
$('delete-file').onclick = () => { if (current && confirm(`Delete ${current}?`)) { delete files[current]; resetHistory(); openFile(Object.keys(files)[0] || ''); } };
function download(name, text, type = 'text/plain') { const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
$('export').onclick = () => download('nexys-project.json', JSON.stringify({files, top: $('top').value, mode: $('mode').value, mapping}, null, 2), 'application/json');
$('download-vcd').onclick = () => last?.vcd ? download('signals.vcd', last.vcd) : toast('Run a simulation first');
$('import').onclick = () => $('upload').click();
$('upload').onchange = async e => {
  try {
    for (const file of e.target.files) {
      if (file.size > 1000000) throw Error('File exceeds 1 MB');
      const text = await file.text();
      if (file.name.endsWith('.json')) { const project = JSON.parse(text); if (!project.files || typeof project.files !== 'object') throw Error('Invalid project JSON'); files = project.files; mapping = project.mapping || {}; $('top').value = project.top || 'elevator_top'; $('mode').value = project.mode || 'board'; }
      else { if (!/^[\w.-]+\.(vhd|vhdl|xdc|txt)$/i.test(file.name)) throw Error('Unsupported file type'); if (file.name in files && !confirm(`Replace ${file.name}?`)) continue; files[file.name] = text; }
    }
    resetHistory(); openFile(Object.keys(files)[0]); modeChanged(false); toast('Files imported');
  } catch (err) { toast(err.message); }
  e.target.value = '';
};
async function loadExample(ask = true) {
  if (ask && !confirm('Replace the current project with the elevator example? Export your edits first.')) return;
  const response = await fetch('/api/example'); const project = await response.json(); files = project.files; mapping = {}; $('top').value = 'elevator_top'; $('mode').value = 'board'; resetHistory(); openFile('elevator_top.vhd'); modeChanged(false);
}
$('example').onclick = () => loadExample().catch(e => toast(e.message));
function modeChanged(resetTop = true) { const board = $('mode').value === 'board'; $('duration-label').hidden = board; $('step').disabled = !board; if (resetTop) $('top').value = board ? 'elevator_top' : 'tb_fsm'; resetHistory(); save(); }
$('mode').onchange = () => modeChanged(); $('top').onchange = () => { resetHistory(); mapping = {}; save(); }; $('fast').onchange = () => { resetHistory(); $('timing-note').textContent = $('fast').checked ? 'Temporary simulation copies: 1 s → 10 µs, debounce → 200 ns. Original files stay unchanged. Other designs keep their own timing constants.' : 'Real timing: a one-second simulation requires 100 million clock cycles and may exceed the runtime limit.'; };
for (const button of document.querySelectorAll('[data-tab]')) button.onclick = () => {
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('selected', b === button));
  for (const tab of ['console', 'waves', 'mapping']) $(tab).hidden = tab !== button.dataset.tab;
};
for (let i = 0; i < 16; i++) {
  const led = document.createElement('div'); led.className = 'led-unit'; led.innerHTML = `<div id="led-${i}" class="led"></div><span class="tiny">${i}</span>`; $('leds').append(led);
  const unit = document.createElement('div'); unit.className = 'led-unit'; const button = document.createElement('button'); button.className = 'switch'; button.setAttribute('aria-label', `Switch ${i}`); button.setAttribute('aria-pressed', 'false'); button.innerHTML = '<i></i>';
  button.onclick = () => { sw ^= 1 << i; button.classList.toggle('on', !!(sw & (1 << i))); button.setAttribute('aria-pressed', String(!!(sw & (1 << i)))); $('switch-value').textContent = '0x' + sw.toString(16).padStart(4, '0').toUpperCase(); };
  const label = document.createElement('span'); label.className = 'tiny'; label.textContent = i; unit.append(button, label); $('switches').append(unit);
}
const polygons = ['5,1 20,1 17,4 8,4','21,2 21,17 18,15 18,5','21,21 21,36 18,33 18,23','5,37 20,37 17,34 8,34','3,21 6,23 6,33 3,36','3,2 6,5 6,15 3,17','5,19 8,16 17,16 20,19 17,21 8,21'];
for (let i = 7; i >= 0; i--) { const digit = document.createElement('div'); digit.className = 'digit'; digit.id = `digit-${i}`; digit.innerHTML = `<svg viewBox="0 0 26 40">${polygons.map((p,j) => `<polygon data-segment="${j}" points="${p}"/>`).join('')}<circle cx="24" cy="37" r="1.3" fill="#364439"/></svg>`; $('display').append(digit); }
function integer(val) { return val && /^[01]+$/.test(val) ? parseInt(val, 2) : null; }
function renderBoard(result) {
  const values = result.wave?.values || {}; const ports = result.ports || [];
  const valueFor = target => { const p = ports.find(p => result.mapping?.[p.name] === target); if (!p) return null; const key = Object.keys(values).find(k => k.startsWith('lab_board_tb.io_' + p.name.toLowerCase()) && !k.includes('.dut.')); return integer(values[key]); };
  const door = valueFor('door'); const leds = valueFor('led') ?? (door || 0);
  for (let i = 0; i < 16; i++) $(`led-${i}`).classList.toggle('on', !!(leds & (1 << i)));
  $('door-status').textContent = door === null ? 'NO OUTPUT / NOT RUN' : door ? 'DOOR OPEN' : 'DOOR CLOSED';
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
  for (let i = 0; i < 8; i++) $(`digit-${i}`).querySelectorAll('polygon').forEach((p,j) => p.classList.toggle('on', digits[i] !== undefined && !(digits[i] & (1 << j))));
}
function renderMapping(result) {
  $('mapping-fields').replaceChildren();
  const options = ['clock', 'sw', 'btnC', 'btnU', 'btnL', 'btnR', 'btnD', 'led', 'segment', 'an', 'dp', 'door', 'zero', 'unused'];
  for (const p of result.ports || []) {
    const row = document.createElement('div'); row.className = 'map-row'; const label = document.createElement('label'); label.textContent = `${p.name} (${p.direction}, ${p.width} bit)`; const select = document.createElement('select');
    for (const option of options.filter(v => p.direction === 'in' ? ['clock','sw','btnC','btnU','btnL','btnR','btnD','zero'].includes(v) : ['led','segment','an','dp','door','unused'].includes(v))) { const opt = document.createElement('option'); opt.value = option; opt.textContent = option; select.append(opt); }
    select.value = result.mapping[p.name]; select.onchange = () => { mapping[p.name] = select.value; resetHistory(); save(); }; row.append(label, select); $('mapping-fields').append(row);
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
  if (busy) return; busy = true; $('run').disabled = true; $('step').disabled = true; $('run').textContent = '◌ Simulating…'; $('result').textContent = 'GHDL running';
  const oldCommands = commands.slice(); commands.push(...extra);
  try {
    const res = await fetch('/api/run', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files, top:$('top').value, mode:$('mode').value, duration:$('duration').value, fast:$('fast').checked, commands, mapping})});
    const result = await res.json(); if (!res.ok || result.error) throw Error(result.error || res.statusText);
    $('console').textContent = (result.overrides?.length ? 'ACCELERATED TIMING (temporary copies only):\n' + result.overrides.join('\n') + '\n\n' : '') + result.log;
    $('result').textContent = result.ok ? '● Simulation passed' : '● ' + result.phase + ' failed'; $('result').style.color = result.ok ? '#b5ec69' : '#fa897f';
    last = result;
    if (!result.ok) { commands = oldCommands; document.querySelector('[data-tab="console"]').click(); }
    if (result.board) { mapping = result.mapping; renderBoard(result); renderMapping(result); }
    renderWaves(result.wave); save();
  } catch (error) { commands = oldCommands; $('console').textContent = error.message; $('result').textContent = 'Simulation error'; document.querySelector('[data-tab="console"]').click(); }
  finally { busy = false; $('run').disabled = false; $('step').disabled = $('mode').value !== 'board'; $('run').innerHTML = '▶ Run simulation <kbd>Ctrl ↵</kbd>'; }
}
$('run').onclick = () => run(); $('step').onclick = () => run([{sw, buttons:[], ticks:1}]); $('reset').onclick = () => { resetHistory(); if ($('mode').value === 'board') run(); };
document.querySelectorAll('[data-button]').forEach(button => button.onclick = async () => { if ($('mode').value !== 'board') return toast('Select Board mode first'); button.classList.add('pressed'); await run([{sw,buttons:[button.dataset.button],ticks:0},{sw,buttons:[],ticks:0}]); button.classList.remove('pressed'); });
document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); } });
async function init() {
  try { const saved = JSON.parse(localStorage.getItem(storageKey)); if (saved?.files && Object.keys(saved.files).length) { files = saved.files; mapping = saved.mapping || {}; $('top').value = saved.top || 'elevator_top'; $('mode').value = saved.mode || 'board'; openFile(saved.current || Object.keys(files)[0]); modeChanged(false); } else await loadExample(false); }
  catch { await loadExample(false); }
  try { const health = await (await fetch('/api/health', {cache:'no-store'})).json(); $('app-version').textContent = 'FPGA WORKSPACE · v' + (health.app_version || 'unknown'); if (!health.ok) { $('console').textContent = health.error; $('result').textContent = 'GHDL setup required'; toast('GHDL is unavailable. See Terminal for setup instructions.'); } } catch { toast('Backend is unavailable. Start python3 server.py'); }
}
init();
