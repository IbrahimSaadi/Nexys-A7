/* Offline waveform navigation. All times are integer femtoseconds from the backend. */
(function(root){
'use strict';
function formatValue(bits,radix='hex'){
 if(bits==null)return '—';
 if(!/^[01]+$/.test(bits))return bits;
 if(radix==='binary')return bits;
 const n=BigInt('0b'+bits);
 if(radix==='signed')return (bits[0]==='1'?n-(1n<<BigInt(bits.length)):n).toString();
 if(radix==='decimal')return n.toString();
 return '0x'+n.toString(16).toUpperCase().padStart(Math.ceil(bits.length/4),'0');
}
function timeLabel(fs){
 const units=[[1e15,'s'],[1e12,'ms'],[1e9,'µs'],[1e6,'ns'],[1e3,'ps'],[1,'fs']];
 const [scale,unit]=units.find(([s])=>Math.abs(fs)>=s)||units.at(-1);
 return Number((fs/scale).toPrecision(7))+' '+unit;
}
function valueAt(events,time){
 let value=null;for(const event of events){if(event[0]>time)break;value=event[2];}return value;
}
function segments(events,start,end){
 let value=valueAt(events,start),at=start;const result=[];
 for(const [time,,bits] of events){if(time<=start)continue;if(time>end)break;result.push([at,time,value]);at=time;value=bits;}
 result.push([at,end,value]);return result;
}
function mount(container){
 let wave=null,start=0,end=1,fullStart=0,fullEnd=1,a=null,b=null,active='A',radix='hex',selected=new Set(),known=new Set(),indexed=new Map();
 const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
 const controls=make('div',undefined,'wave-controls'),info=make('p',undefined,'wave-capture-info'),plot=make('div',undefined,'wave-plot');
 const measure=make('p',undefined,'wave-measure');measure.setAttribute('role','status');
 function button(text,action){const e=make('button',text);e.type='button';e.onclick=action;controls.append(e);return e;}
 function windowTo(left,right){const width=Math.min(fullEnd-fullStart,Math.max(1,right-left));start=Math.max(fullStart,Math.min(left,fullEnd-width));end=start+width;draw();}
 button('Fit',()=>windowTo(fullStart,fullEnd));
 button('Zoom +',()=>{const center=a!==null&&a>=start&&a<=end?a:(start+end)/2;windowTo(center-(end-start)/4,center+(end-start)/4);});
 button('Zoom −',()=>{const center=(start+end)/2;windowTo(center-(end-start),center+(end-start));});
 button('←',()=>windowTo(start-(end-start)/2,end-(end-start)/2)).setAttribute('aria-label','Pan earlier');
 button('→',()=>windowTo(start+(end-start)/2,end+(end-start)/2)).setAttribute('aria-label','Pan later');
 const radixSelect=make('select');radixSelect.setAttribute('aria-label','Waveform value format');
 for(const [value,text] of [['hex','Hex'],['binary','Binary'],['decimal','Unsigned'],['signed','Signed']]){const option=make('option',text);option.value=value;radixSelect.append(option);}
 radixSelect.onchange=()=>{radix=radixSelect.value;draw();};controls.append(radixSelect);
 const cursorButton=button('Place cursor: A',()=>{active=active==='A'?'B':'A';cursorButton.textContent='Place cursor: '+active;});
 button('Clear cursors',()=>{a=b=null;draw();});
 const choices=make('details'),choiceTitle=make('summary','Choose signals (including internal signals)'),search=make('input'),choiceList=make('div',undefined,'wave-signal-choices');
 search.type='search';search.placeholder='Filter signals…';search.setAttribute('aria-label','Filter waveform signals');search.oninput=renderChoices;
 choices.append(choiceTitle,search,choiceList);container.replaceChildren(controls,info,measure,choices,plot);
 function renderChoices(){choiceList.replaceChildren();const query=search.value.toLowerCase();let count=0;for(const name of known){if(!name.toLowerCase().includes(query))continue;if(count++>=300){choiceList.append(make('p','Filter to narrow the list; showing 300 matches.'));break;}const label=make('label'),check=make('input');check.type='checkbox';check.checked=selected.has(name);check.onchange=()=>{if(check.checked&&selected.size>=64){check.checked=false;return;}check.checked?selected.add(name):selected.delete(name);draw();};label.append(check,document.createTextNode(name));choiceList.append(label);}}
 function svgNode(tag,attrs){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))e.setAttribute(key,value);return e;}
 function draw(){
  info.textContent=!wave?'Run a simulation to inspect signals.':(wave.capture==='sampled'?'LIVE SAMPLES · top-level outputs only; transitions between samples may be missed. Times include the 200 ns startup.':'VCD TRACE · select internal signals below. Values are from recorded events.')+(wave.truncated?' History is truncated; missing earlier values are shown as unknown.':'');
  measure.textContent=`A: ${a===null?'—':timeLabel(a)}   B: ${b===null?'—':timeLabel(b)}   Δt: ${a===null||b===null?'—':timeLabel(Math.abs(b-a))}   View: ${timeLabel(start)} – ${timeLabel(end)}`;
  plot.replaceChildren();if(!wave)return;
  const axis=make('div',undefined,'wave-axis');for(let i=0;i<=4;i++)axis.append(make('span',timeLabel(start+(end-start)*i/4)));plot.append(axis);
  for(const name of selected){
   const events=indexed.get(name)||[],row=make('div',undefined,'debug-wave-row'),label=make('div',undefined,'debug-wave-label');
   const title=make('span',name);title.title=name;const values=make('small',a===null?'Latest: '+formatValue(wave.values[name],radix):'A: '+formatValue(valueAt(events,a),radix)+(b===null?'':' · B: '+formatValue(valueAt(events,b),radix)));label.append(title,values);
   const svg=svgNode('svg',{viewBox:'0 0 800 40',preserveAspectRatio:'none',role:'img','aria-label':name+' waveform; click to place cursor '+active,tabindex:'0'});
   const x=t=>(t-start)/(end-start)*800;
   const visible=segments(events,start,end);
   if(visible.length>3000){const text=svgNode('text',{x:10,y:24,fill:'#ffd17a','font-size':12});text.textContent='Too many transitions — zoom in to inspect this signal';svg.append(text);}else for(const [left,right,bits] of visible){
    const unknown=bits===null||!/^[01]+$/.test(bits),bus=bits!==null&&bits.length>1;
    const edge=Math.min(4,(x(right)-x(left))/2);
    const y=bits==='0'?30:10;
    const path=svgNode('path',{d:bus?`M${x(left)},20 L${x(left)+edge},10 L${x(right)-edge},10 L${x(right)},20 L${x(right)-edge},30 L${x(left)+edge},30 Z`:`M${x(left)},20 L${x(left)},${unknown?20:y} L${x(right)},${unknown?20:y} L${x(right)},20`,stroke:unknown?'#e2b879':'#a7df6d',fill:'none','stroke-width':1.3,'vector-effect':'non-scaling-stroke'});
    if(unknown)path.setAttribute('stroke-dasharray','3 3');svg.append(path);
    if(bus&&x(right)-x(left)>75){const text=svgNode('text',{x:x(left)+5,y:24,fill:'#cee7b5','font-size':11});text.textContent=formatValue(bits,radix);svg.append(text);}
   }
   for(const [stamp,color] of [[a,'#78c8ff'],[b,'#ffa8d9']])if(stamp!==null&&stamp>=start&&stamp<=end)svg.append(svgNode('line',{x1:x(stamp),x2:x(stamp),y1:0,y2:40,stroke:color,'stroke-width':1.5}));
   svg.onclick=event=>{const rect=svg.getBoundingClientRect(),stamp=Math.round(start+Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*(end-start));if(active==='A')a=stamp;else b=stamp;draw();};
   svg.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();if(active==='A')a=Math.round((start+end)/2);else b=Math.round((start+end)/2);draw();}};
   row.append(label,svg);plot.append(row);
  }
  if(!selected.size)plot.append(make('p','Choose a signal to display.'));
 }
 function update(next){
  const reset=!next||!wave||next.end<wave.end;const fit=reset||(start===fullStart&&end===fullEnd);
  wave=next;indexed=new Map();for(const event of next?.events||[]){if(!indexed.has(event[1]))indexed.set(event[1],[]);indexed.get(event[1]).push(event);}
  let choicesChanged=reset;
  if(reset){selected.clear();known.clear();a=b=null;}
  for(const name of Object.keys(next?.values||{})){if(!known.has(name)){choicesChanged=true;if(known.size<20)selected.add(name);}known.add(name);}
  fullStart=next?.truncated&&next.events.length?next.events[0][0]:0;fullEnd=Math.max(fullStart+1,next?.end||1);
  if(fit){start=fullStart;end=fullEnd;}else{const width=Math.min(end-start,fullEnd-fullStart);start=Math.max(fullStart,Math.min(start,fullEnd-width));end=start+width;}
  if(choicesChanged)renderChoices();draw();
 }
 draw();return {update};
}
const api={mount,formatValue,timeLabel,valueAt,segments};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.NexysWaves=api;
})(typeof window!=='undefined'?window:globalThis);
