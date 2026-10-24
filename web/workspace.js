(function(){
 'use strict';
 const main=document.querySelector('main'),handle=document.getElementById('output-resizer');
 const panel=document.querySelector('.right'),toggle=document.getElementById('board-size');
 const key='nexys-lab-workspace-v1';
 let state={results:32,compact:false};
 try{const saved=JSON.parse(localStorage.getItem(key));if(saved&&Number.isFinite(saved.results))state.results=Math.max(20,Math.min(65,saved.results));state.compact=saved?.compact===true;}catch{}
 function save(){try{localStorage.setItem(key,JSON.stringify(state));}catch{}}
 function resize(value){state.results=Math.max(20,Math.min(65,value));main.style.setProperty('--results-height',state.results+'%');handle.setAttribute('aria-valuenow',Math.round(state.results));}
 function board(){panel.classList.toggle('compact-board',state.compact);toggle.setAttribute('aria-pressed',String(state.compact));toggle.textContent=state.compact?'Expand board':'Compact board';}
 handle.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();handle.setPointerCapture(event.pointerId);document.body.classList.add('resizing');});
 handle.addEventListener('pointermove',event=>{if(!handle.hasPointerCapture(event.pointerId))return;const rect=main.getBoundingClientRect();resize((rect.bottom-event.clientY)/rect.height*100);});
 function finish(event){if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);document.body.classList.remove('resizing');save();}
 handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);
 handle.addEventListener('lostpointercapture',()=>document.body.classList.remove('resizing'));
 handle.addEventListener('keydown',event=>{const changes={ArrowUp:5,ArrowDown:-5};if(event.key in changes){event.preventDefault();resize(state.results+changes[event.key]);save();}else if(event.key==='Home'||event.key==='End'){event.preventDefault();resize(event.key==='Home'?20:65);save();}});
 toggle.addEventListener('click',()=>{state.compact=!state.compact;board();save();});
 resize(state.results);board();
})();
