(function (global) {
  'use strict';

  // A raw top-level signal inspector. This module does not emulate peripherals.
  const mounted = new WeakMap();
  const catalogs = new WeakMap();
  let active = null;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function normalizedBits(value, width) {
    if (typeof value === 'number' && (!Number.isSafeInteger(value) || value < 0) || typeof value === 'bigint' && value < 0n) {
      throw new Error('Use a non-negative integer, or an exact hex/binary string for a wide bus.');
    }
    let text = typeof value === 'number' || typeof value === 'bigint' ? BigInt(value).toString(2) : String(value).trim().replace(/_/g, '').replace(/\s+/g, '');
    if (/^0x[0-9a-f]+$/i.test(text) || /^x"[0-9a-f]+"$/i.test(text)) {
      if (/^x"/i.test(text)) text = '0x' + text.slice(2, -1);
      text = BigInt(text).toString(2);
    } else if (/^d:[0-9]+$/i.test(text)) {
      text = BigInt(text.slice(2)).toString(2);
    } else {
      text = text.replace(/^0b/i, '').replace(/^b"([^"]+)"$/i, '$1').toUpperCase();
    }
    if (!/^[01UXZWLH-]+$/.test(text)) {
      throw new Error('Enter binary bits (0/1/X/Z), 0x hexadecimal, or d:decimal.');
    }
    if (text.length > width) throw new Error('Value does not fit in ' + width + ' bits.');
    return text.padStart(width, '0');
  }

  function hexValue(bits) {
    if (!/^[01]+$/.test(bits)) return '—';
    return '0x' + BigInt('0b' + bits).toString(16).toUpperCase().padStart(Math.ceil(bits.length / 4), '0');
  }

  function valueFor(values, name) {
    const wanted = 'lab_board_tb.io_' + name.toLowerCase();
    for (const key of Object.keys(values || {})) {
      const lower = key.toLowerCase();
      if (lower === wanted || lower.startsWith(wanted + '[') || lower.startsWith(wanted + '(')) {
        return String(values[key]);
      }
    }
    return null;
  }

  function mount(container, options) {
    if (!(container instanceof Element)) throw new TypeError('Signal inspector needs a DOM container.');
    if (mounted.has(container)) mounted.get(container).destroy();
    const callbacks = options || {};
    const rows = new Map();
    const inputValues = Object.create(null);
    let clocks = Object.create(null);
    let disposed = false;

    const shell = element('section', 'nexys-signals');
    const heading = element('div', 'signals-heading');
    heading.append(element('strong', '', 'SIGNAL INSPECTOR'));
    const summary = element('span', 'signals-summary', 'No ports discovered');
    heading.append(summary);
    const note = element('p', 'signals-note', 'Raw top-level signals. A visible USB, DDR or other bus is not a behavioral model of that peripheral.');
    const toolbar = element('div', 'signals-toolbar');
    const search = element('input', 'signals-search');
    search.type = 'search';
    search.placeholder = 'Find a port or interface…';
    search.setAttribute('aria-label', 'Find a signal');
    const direction = element('select', 'signals-filter');
    direction.setAttribute('aria-label', 'Filter signal direction');
    for (const [value, label] of [['all', 'All ports'], ['in', 'Inputs'], ['out', 'Outputs'], ['inout', 'Bidirectional']]) {
      const option = element('option', '', label);
      option.value = value;
      direction.append(option);
    }
    toolbar.append(search, direction);
    const list = element('div', 'signals-list');
    const empty = element('p', 'signals-empty', 'Run a design to discover its top-level ports.');
    const status = element('p', 'signals-message');
    status.setAttribute('role', 'status');
    shell.append(heading, note, toolbar, empty, list, status);
    container.append(shell);

    function filter() {
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      for (const row of rows.values()) {
        const match = (!query || (row.port.name + ' ' + row.port.type).toLowerCase().includes(query)) &&
          (direction.value === 'all' || direction.value === row.port.direction || direction.value === 'out' && row.port.direction === 'buffer');
        row.root.hidden = !match;
        visible += Number(match);
      }
      empty.hidden = visible > 0;
      empty.textContent = rows.size ? 'No signals match this filter.' : 'Run a design to discover its top-level ports.';
      summary.textContent = rows.size ? visible + ' / ' + rows.size + ' ports' : 'No ports discovered';
    }
    search.addEventListener('input', filter);
    direction.addEventListener('change', filter);

    function report(message, error) {
      status.textContent = message;
      status.classList.toggle('signals-error', Boolean(error));
    }

    async function commitInput(row) {
      try {
        const bits = normalizedBits(row.editor.value, row.port.width);
        if (typeof callbacks.onInput === 'function') await callbacks.onInput(row.port.name, bits);
        inputValues[row.port.name] = bits;
        row.dirty = false;
        row.editor.value = bits;
        row.editor.removeAttribute('aria-invalid');
        report(row.port.name + ' input queued. The next simulation frame confirms the delivered value.');
      } catch (error) {
        row.editor.setAttribute('aria-invalid', 'true');
        report(error.message || String(error), true);
      }
    }

    function setClockControls(row) {
      if (!row.clockMode || row.clockDirty) return;
      const config = clocks[row.port.name];
      row.clockMode.checked = Boolean(config);
      row.clockPeriod.disabled = !config;
      if (document.activeElement !== row.clockPeriod) row.clockPeriod.value = config ? String(config.period_ns || 10) : '10';
      row.clockApply.textContent = config ? 'Update clock' : 'Apply clock';
      if(row.editor)row.editor.disabled=Boolean(config);
      if(row.apply)row.apply.disabled=Boolean(config);
    }

    function makeRow(port) {
      const row = { port, root: element('article', 'signals-row'), dirty: false };
      row.root.dataset.port = port.name;
      const info = element('div', 'signals-port-info');
      const name = element('code', 'signals-port-name', port.name);
      name.title = port.name;
      const meta = element('span', 'signals-port-meta', port.direction.toUpperCase() + ' · ' + port.width + ' bit' + (port.width === 1 ? '' : 's'));
      const type = element('span', 'signals-port-type', port.type || '');
      info.append(name, meta, type);
      const observed = element('div', 'signals-observed');
      const observedLabel = element('span', 'signals-value-label', port.direction === 'inout' ? 'RESOLVED BUS' : 'OBSERVED');
      row.binary = element('code', 'signals-binary', '—');
      row.hex = element('code', 'signals-hex', '—');
      observed.append(observedLabel, row.binary, row.hex);
      row.root.append(info, observed);
      if (port.direction === 'in' || port.direction === 'inout') {
        const edit = element('div', 'signals-drive');
        const label = element('label', 'signals-value-label', port.direction === 'inout' ? 'EXTERNAL DRIVE · Z RELEASES BUS' : 'INPUT DRIVE');
        row.editor = element('input', 'signals-input');
        row.editor.type = 'text';
        row.editor.spellcheck = false;
        row.editor.autocomplete = 'off';
        row.editor.placeholder = port.width === 1 ? '0, 1 or Z' : '0xFF or binary';
        row.editor.setAttribute('aria-label', 'Drive ' + port.name);
        const fallback = port.direction === 'inout' ? 'Z'.repeat(port.width) : '0'.repeat(port.width);
        try { row.editor.value = normalizedBits(inputValues[port.name] === undefined ? fallback : inputValues[port.name], port.width); }
        catch { row.editor.value = fallback; }
        label.append(row.editor);
        const apply = element('button', 'signals-apply', 'Set input');
        row.apply=apply;
        apply.type = 'button';
        apply.addEventListener('click', () => commitInput(row));
        row.editor.addEventListener('input', () => { row.dirty = true; row.editor.removeAttribute('aria-invalid'); });
        row.editor.addEventListener('keydown', event => {
          if (event.key === 'Enter') { event.preventDefault(); commitInput(row); }
        });
        edit.append(label, apply);
        row.root.append(edit);
        if (port.width === 1 && port.direction === 'in' && typeof callbacks.onClock === 'function') {
          const clock = element('details', 'signals-clock');
          clock.append(element('summary', '', 'Clock source'));
          const controls = element('div', 'signals-clock-controls');
          const enabled = element('label', 'signals-clock-enabled');
          row.clockMode = element('input');
          row.clockMode.type = 'checkbox';
          row.clockMode.setAttribute('aria-label', 'Clock on ' + port.name);
          enabled.append(row.clockMode, document.createTextNode('Generate a clock'));
          const periodLabel = element('label', '', 'Period (ns)');
          row.clockPeriod = element('input', 'signals-clock-period');
          row.clockPeriod.type = 'number';
          row.clockPeriod.min = '0.000002';
          row.clockPeriod.step = '0.000002';
          row.clockPeriod.value = '10';
          row.clockPeriod.disabled = true;
          row.clockPeriod.setAttribute('aria-label', 'Clock period for ' + port.name);
          periodLabel.append(row.clockPeriod);
          row.clockApply = element('button', '', 'Apply clock');
          row.clockApply.type = 'button';
          row.clockMode.addEventListener('change', () => { row.clockDirty = true; row.clockPeriod.disabled = !row.clockMode.checked; });
          row.clockPeriod.addEventListener('input', () => { row.clockDirty = true; });
          row.clockApply.addEventListener('click', async () => {
            const period = Number(row.clockPeriod.value);
            if (row.clockMode.checked && (!Number.isFinite(period) || period<=0 || period>1000000000 || Math.abs(period*500000-Math.round(period*500000))>0.00001)) {
              report('Clock period must be positive and a multiple of 2 fs (0.000002 ns).', true);
              return;
            }
            const value = row.clockMode.checked ? { period_ns: period } : null;
            try {
              await callbacks.onClock(port.name, value);
              if (value) clocks[port.name] = value; else delete clocks[port.name];
              row.clockDirty = false;
              report('Clock configuration saved for ' + port.name + '. Restart simulation to apply it.');
              setClockControls(row);
            } catch (error) { report(error.message || String(error), true); }
          });
          controls.append(enabled, periodLabel, row.clockApply);
          clock.append(controls, element('p', '', 'Clock configuration takes effect when the design is restarted.'));
          row.root.append(clock);
        }
      }
      return row;
    }

    function setInputs(values) {
      for (const [name, value] of Object.entries(values || {})) {
        const row = rows.get(name);
        if (!row) { inputValues[name] = value; continue; }
        let bits;
        try { bits = normalizedBits(value, row.port.width); }
        catch { continue; }
        inputValues[name] = bits;
        if (row && row.editor && !row.dirty && document.activeElement !== row.editor) row.editor.value = bits;
      }
    }

    function update(frame) {
      if (disposed || !frame) return;
      const seen = new Set();
      for (const item of frame.ports || []) {
        const port = { ...item, width: Math.max(1, Number(item.width) || 1), direction: String(item.direction || 'in').toLowerCase() };
        seen.add(port.name);
        let row = rows.get(port.name);
        if (row && (row.port.width !== port.width || row.port.direction !== port.direction || row.port.type !== port.type)) {
          row.root.remove();
          rows.delete(port.name);
          row = null;
        }
        if (!row) {
          row = makeRow(port);
          rows.set(port.name, row);
          list.append(row.root);
          setClockControls(row);
        }
        const value = valueFor(frame.wave && frame.wave.values, port.name) ?? (port.direction==='in' ? frame.input_values?.[port.name] ?? null : null);
        row.binary.textContent = value === null ? '—' : value;
        row.binary.title = value === null ? 'No sampled value yet' : value;
        row.hex.textContent = value === null ? '—' : hexValue(value);
        row.hex.title = row.hex.textContent;
        row.root.classList.toggle('signals-unknown', value !== null && !/^[01]+$/.test(value));
      }
      for (const [name, row] of rows) {
        if (!seen.has(name)) { row.root.remove(); rows.delete(name); delete inputValues[name]; }
      }
      setInputs(frame.input_values || {});
      if (frame.clocks) api.setClocks(frame.clocks);
      filter();
    }

    const api = {
      update,
      setInputs,
      getInputs: () => ({ ...inputValues }),
      setClocks: values => { clocks = { ...(values || {}) }; for (const row of rows.values()) setClockControls(row); },
      getClocks: () => ({ ...clocks }),
      reset: () => { rows.clear(); list.replaceChildren(); for (const name of Object.keys(inputValues)) delete inputValues[name]; clocks = {}; report(''); filter(); },
      destroy: () => { disposed = true; shell.remove(); mounted.delete(container); if (active === api) active = null; },
    };
    mounted.set(container, api);
    active = api;
    return api;
  }

  const groupLabels = {
    clock: 'Clock', switches: 'Slide switches', buttons: 'Buttons and reset', leds: 'User LEDs',
    rgb_leds: 'RGB LEDs', seven_segment: 'Seven-segment display', pmod: 'Pmod connectors',
    xadc: 'XADC-capable pins', vga: 'VGA', micro_sd: 'MicroSD', accelerometer: 'Accelerometer',
    temperature: 'Temperature sensor', microphone: 'Microphone', audio: 'Audio output', uart: 'UART',
    usb_hid_ps2: 'USB HID / PS/2', ethernet: 'Ethernet', qspi_flash: 'QSPI flash', ddr2: 'DDR2 memory', other: 'Other signals',
  };
  const capabilityLabels = {
    raw_signal: 'RAW · no device model', interactive_gpio: 'GPIO control / display',
    multiplex_display: 'Multiplexed display adapter', clock_source: 'Clock source', digital_raw_only: 'DIGITAL LEVELS ONLY',
  };

  function renderCatalog(container, initialCatalog, initialBindings, initialFrame) {
    if (!(container instanceof Element)) throw new TypeError('Pin catalog needs a DOM container.');
    if (catalogs.has(container)) catalogs.get(container).destroy();
    let disposed = false;
    let bindings = initialBindings || {};
    let currentFrame = initialFrame || {};
    let references = new Map();
    const pinRows = new Map(), groups = new Map();
    const shell = element('section', 'nexys-pin-catalog');
    const heading = element('div', 'signals-heading');
    const title = element('strong', '', 'NEXYS A7 PHYSICAL SIGNALS');
    const summary = element('span', 'signals-summary');
    heading.append(title, summary);
    const note = element('p', 'signals-note', 'Pins and sampled digital values are exposed here. RAW means no complete peripheral model: DDR2, USB/HID, Ethernet, SD, SPI and sensors do not become working devices merely by appearing in this catalog.');
    const toolbar = element('div', 'signals-toolbar');
    const search = element('input', 'signals-search');
    search.type = 'search'; search.placeholder = 'Find a signal, package pin, or mapped port…';
    search.setAttribute('aria-label', 'Find a physical board signal');
    const groupFilter = element('select', 'signals-filter');
    groupFilter.setAttribute('aria-label', 'Filter board interface');
    toolbar.append(search, groupFilter);
    const list = element('div', 'pin-groups');
    const empty = element('p', 'signals-empty', 'No physical signals available.');
    const limitations = element('details', 'pin-limitations');
    limitations.append(element('summary', '', 'Catalog scope and hardware sources'));
    const limitationList = element('ul'), sources = element('div', 'pin-sources');
    limitations.append(limitationList, sources);
    shell.append(heading, note, toolbar, empty, list, limitations); container.append(shell);

    function reindex() {
      references = new Map();
      for (const [portName, entries] of Object.entries(bindings.mapping || {})) {
        if (!Array.isArray(entries)) continue;
        entries.forEach((entry, position) => {
          if (!entry || !entry.signal && !entry.pin) return;
          const ref = { port: portName, index: entry.index, position, source: entry.source || 'mapping' };
          const key = entry.signal ? 'signal:' + entry.signal.toLowerCase() : 'pin:' + String(entry.pin).toUpperCase();
          if (!references.has(key)) references.set(key, []);
          references.get(key).push(ref);
        });
      }
      for (const row of pinRows.values()) {
        row.refs = references.get('signal:' + row.record.signal.toLowerCase()) || references.get('pin:' + String(row.record.pin).toUpperCase()) || [];
        row.bound.replaceChildren();
        if (!row.refs.length) row.bound.append(element('span', 'pin-unmapped', 'Not mapped'));
        for (const ref of row.refs) {
          const label = ref.port + (ref.index === null || ref.index === undefined ? '' : '[' + ref.index + ']');
          const tag = element('code', 'pin-port-ref', label); tag.title = 'Mapping source: ' + ref.source; row.bound.append(tag);
        }
      }
    }

    function filter() {
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      for (const group of groups.values()) group.visible = 0;
      for (const row of pinRows.values()) {
        const text = [row.record.signal, row.record.source_name, row.record.pin, groupLabels[row.record.group] || row.record.group,
          row.bound.textContent, row.record.direction, row.record.model].join(' ').toLowerCase();
        const match = (!query || text.includes(query)) && (groupFilter.value === 'all' || groupFilter.value === row.record.group);
        row.root.hidden = !match;
        if (match) { visible++; groups.get(row.record.group).visible++; }
      }
      for (const group of groups.values()) {
        group.root.hidden = group.visible === 0;
        group.count.textContent = group.visible + ' / ' + group.total + ' signals';
        if (query && group.visible) group.root.open = true;
      }
      empty.hidden = visible > 0;
      empty.textContent = pinRows.size ? 'No physical signals match this filter.' : 'No physical signals available.';
      summary.textContent = visible + ' / ' + pinRows.size + ' signal pins';
    }
    search.addEventListener('input', filter); groupFilter.addEventListener('change', filter);

    function setCatalog(catalog) {
      catalog = catalog || {};
      const oldGroup = groupFilter.value;
      const opened = new Set([...groups].filter(([, group]) => group.root.open).map(([name]) => name));
      pinRows.clear(); groups.clear(); list.replaceChildren(); groupFilter.replaceChildren();
      const all = element('option', '', 'All interfaces'); all.value = 'all'; groupFilter.append(all);
      for (const record of Array.isArray(catalog.pins) ? catalog.pins : []) {
        if (!record || typeof record.signal !== 'string') continue;
        const name = record.group || 'other';
        if (!groups.has(name)) {
          const root = element('details', 'pin-group');
          root.open = opened.has(name) || ['clock', 'switches', 'buttons', 'leds', 'seven_segment'].includes(name);
          const groupHeading = element('summary');
          const label = element('span', '', groupLabels[name] || name.replace(/_/g, ' '));
          const count = element('span', 'pin-group-count'); groupHeading.append(label, count);
          const body = element('div', 'pin-group-body');
          const group = { root, body, count, total: 0, visible: 0 };
          root.append(groupHeading, body); list.append(root); groups.set(name, group);
          const option = element('option', '', groupLabels[name] || name.replace(/_/g, ' ')); option.value = name; groupFilter.append(option);
        }
        const group = groups.get(name); group.total++;
        const root = element('article', 'pin-record'); root.dataset.signal = record.signal;
        const identity = element('div', 'pin-identity');
        identity.append(element('code', 'pin-signal', record.signal), element('span', 'pin-pad', 'PIN ' + (record.pin || '—')));
        const dir = String(record.direction || 'configurable');
        const directionLabel = dir === 'in' ? 'IN → FPGA' : dir === 'out' ? 'OUT ← FPGA' : dir === 'inout' ? 'IN / OUT' : 'FROM VHDL DECLARATION';
        const metadata = element('div', 'pin-metadata'); metadata.append(element('span', 'pin-direction', directionLabel));
        const capability = element('span', 'pin-capability' + (['raw_signal', 'digital_raw_only'].includes(record.model) ? ' pin-raw' : ''), capabilityLabels[record.model] || String(record.model || 'Raw signal'));
        capability.title = record.kind === 'analog_capable' ? 'Digital raw levels only; analog voltage behavior is not modeled.' : String(record.iostandard || '');
        metadata.append(capability);
        const bound = element('div', 'pin-bindings'), observed = element('code', 'pin-bit-value', '—');
        observed.setAttribute('aria-label', 'Sampled value of ' + record.signal);
        root.append(identity, metadata, bound, observed); group.body.append(root);
        pinRows.set(record.signal, { root, record, bound, observed, refs: [] });
      }
      if ([...groupFilter.options].some(option => option.value === oldGroup)) groupFilter.value = oldGroup;
      limitationList.replaceChildren(); sources.replaceChildren();
      for (const text of catalog.limitations || []) limitationList.append(element('li', '', String(text)));
      for (const url of catalog.sources || []) {
        try {
          const parsed = new URL(url);
          if (parsed.protocol !== 'https:') continue;
          const link = element('a', '', parsed.hostname + parsed.pathname); link.href = parsed.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; sources.append(link);
        } catch { /* Invalid sources are not navigable links. */ }
      }
      title.textContent = String(catalog.board || 'Nexys A7') + ' · PHYSICAL SIGNALS';
      reindex(); filter(); update(currentFrame);
    }

    function bitValue(ref, frame, byName) {
      const port = byName.get(ref.port.toLowerCase()); if (!port) return null;
      let bits = valueFor(frame.wave && frame.wave.values, port.name);
      if (bits === null) {
        const inputs = frame.input_values || {};
        const key = Object.keys(inputs).find(name => name.toLowerCase() === port.name.toLowerCase());
        if (key !== undefined) { try { bits = normalizedBits(inputs[key], Number(port.width) || 1); } catch { return null; } }
      }
      if (bits === null) return null;
      if (!port.vector || ref.index === null || ref.index === undefined) return bits.length === 1 ? bits : null;
      let left = Number(port.left), right = Number(port.right);
      let numericBounds = port.left !== null && port.left !== undefined && port.right !== null && port.right !== undefined && Number.isInteger(left) && Number.isInteger(right);
      if (!numericBounds) {
        const range = /\(\s*(\d+)\s+(downto|to)\s+(\d+)\s*\)/i.exec(port.type || '');
        if (range) { left = Number(range[1]); right = Number(range[3]); numericBounds = true; }
      }
      const offset = numericBounds ? left > right ? left - Number(ref.index) : Number(ref.index) - left : ref.position;
      return offset >= 0 && offset < bits.length ? bits[offset] : null;
    }

    function update(frame, nextBindings) {
      if (disposed) return;
      currentFrame = frame || {};
      if (nextBindings) { bindings = nextBindings; reindex(); filter(); }
      const byName = new Map((currentFrame.ports || []).map(port => [String(port.name).toLowerCase(), port]));
      for (const row of pinRows.values()) {
        const readings = row.refs.map(ref => bitValue(ref, currentFrame, byName)), known = readings.filter(value => value !== null);
        row.observed.textContent = known.length ? [...new Set(known)].join(' / ') : '—';
        row.observed.title = row.refs.length ? row.refs.map((ref, index) => ref.port + (ref.index === null || ref.index === undefined ? '' : '[' + ref.index + ']') + ': ' + (readings[index] === null ? 'not sampled' : readings[index])).join('\n') : 'No mapped VHDL port';
        row.root.classList.toggle('pin-value-known', known.length > 0 && known.every(value => /^[01]$/.test(value)));
        row.root.classList.toggle('pin-value-unknown', known.some(value => !/^[01]$/.test(value)));
        row.root.classList.toggle('pin-value-conflict', new Set(known).size > 1);
      }
    }

    const api = {
      update, setCatalog,
      setBindings: value => { bindings = value || {}; reindex(); filter(); update(currentFrame); },
      destroy: () => { disposed = true; shell.remove(); catalogs.delete(container); },
    };
    catalogs.set(container, api); setCatalog(initialCatalog); return api;
  }

  global.NexysSignals = {
    mount,
    renderCatalog,
    update: frame => active && active.update(frame),
    setInputs: values => active && active.setInputs(values),
    getInputs: () => active ? active.getInputs() : {},
    setClocks: values => active && active.setClocks(values),
    getClocks: () => active ? active.getClocks() : {},
    reset: () => active && active.reset(),
    destroy: () => active && active.destroy(),
    normalizeBits: normalizedBits,
  };
})(typeof window === 'undefined' ? globalThis : window);
