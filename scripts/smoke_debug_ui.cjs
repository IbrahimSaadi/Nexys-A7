const {spawn}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const server=spawn(path.resolve('runtime/python/python.exe'),['server.py','--port','0'],{windowsHide:true});
let output='';server.stdout.on('data',b=>output+=b);server.stderr.on('data',b=>{output+=b;});
let browser,ws,id=0;const requests=new Map(),errors=[];
async function poll(fn){for(let i=0;i<200;i++){const result=await fn();if(result)return result;await delay(100);}throw Error('Timed out');}
function send(method,params={}){return new Promise((resolve,reject)=>{const key=++id;requests.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));});}
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
(async()=>{try{
 const match=await poll(()=>/listening on 127.0.0.1:(\d+)/.exec(output));
 const url='http://127.0.0.1:'+match[1];const profile=fs.mkdtempSync(path.join(os.tmpdir(),'nexys-debug-ui-'));
 browser=spawn(process.env.NEXYS_TEST_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless=new','--disable-gpu','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
 const debugPort=await poll(()=>{try{return fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];}catch{}});
 const targets=await (await fetch('http://127.0.0.1:'+debugPort+'/json')).json();ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>ws.addEventListener('open',r));ws.addEventListener('message',e=>{const msg=JSON.parse(e.data);if(msg.id){const entry=requests.get(msg.id);requests.delete(msg.id);msg.error?entry.reject(msg.error):entry.resolve(msg.result);}if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params);if(msg.method==='Network.loadingFailed')console.log('NETWORK FAILURE '+JSON.stringify(msg.params));});
 await send('Network.enable',{maxTotalBufferSize:1000000,maxResourceBufferSize:100000});await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url});
 await poll(()=>evaluate("typeof init==='function' && document.querySelector('#step-time')!==null"));await delay(600);
 await evaluate(`(async()=>{const example=await(await fetch('/api/example')).json();files=example.files;openFile(Object.keys(files)[0]);$('top').value='elevator_controller';})()`);
 // Select actual discovered top and run through the normal UI path.
 await evaluate("inspectProject().then(info=>{$('top').value=info.suggested_top||info.top;})");
 await evaluate('startLive()');await poll(()=>evaluate('Boolean(liveToken)'));
 if(process.env.NEXYS_TEST_BACKGROUND){
   const initial=await evaluate('simNs');
   await evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))");
   await poll(()=>evaluate('backgroundWake!==null'));
   await send('Page.setWebLifecycleState',{state:'frozen'});
   await delay(5000);
   await send('Page.setWebLifecycleState',{state:'active'});
   await evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))");
   await poll(()=>evaluate('backgroundWake===null'));
   await evaluate("$('pause').click()");await poll(()=>evaluate('paused&&pendingAdvances===0'));
   const advanced=await evaluate('simNs');assert.ok(advanced-initial>1000000,'server must continue while page is frozen');
   console.log('Frozen-page test passed; HDL advanced '+(advanced-initial)+' ns while client execution was suspended.');
   await evaluate("$('pause').click()");
 }
 const soak=Number(process.env.NEXYS_SOAK_SECONDS||0);const samples=[];
 for(let elapsed=0;elapsed<soak;elapsed+=5){await delay(5000);await send('Page.bringToFront');const sample=await evaluate("({simNs,wall:activeWallMs(),speed:$('sim-speed').textContent,metrics:$('performance-details').textContent,hidden:document.hidden,paused,pendingAdvances,live:!!liveToken,result:$('result').textContent,log:$('console').textContent.slice(-500)})");samples.push(sample);if(elapsed%30===0)console.log(JSON.stringify({seconds:elapsed+5,simNs:sample.simNs,speed:sample.speed,hidden:sample.hidden,live:sample.live}));if(!sample.live){console.log(JSON.stringify(sample));console.log(output.slice(-2000));fs.writeFileSync('benchmark-browser-failure.json',JSON.stringify(samples,null,2));throw Error('Live session stopped during soak');}}
 if(samples.length)fs.writeFileSync('benchmark-browser-pacing.json',JSON.stringify(samples,null,2));
 await send('Page.bringToFront');await evaluate("$('pause').click()");await poll(()=>evaluate('paused&&pendingAdvances===0'));
 const before=await evaluate('simNs');await evaluate("$('step-ns').value='1';stepSimulation(false)");assert.equal(await evaluate('simNs'),before+1);
 assert.equal(await evaluate('paused'),true);
 await evaluate("document.querySelector('[data-tab=waves]').click()");
 assert.ok(await evaluate("document.querySelectorAll('.debug-wave-row').length>0"));
 await evaluate("document.querySelector('.debug-wave-row svg').dispatchEvent(new MouseEvent('click',{clientX:500,bubbles:true}))");
 assert.ok((await evaluate("document.querySelector('.wave-measure').textContent")).includes('A:'));
 await evaluate('stopLive()');assert.equal(await evaluate("$('step-time').disabled"),true);
 const screenshot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync('debug-tools-ui.png',Buffer.from(screenshot.data,'base64'));
 assert.deepEqual(errors,[]);console.log('Browser smoke passed: project run, pause, exact 1 ns step, wave rendering, cursor, stop; no JS errors.');
 }finally{if(ws){try{await send('Browser.close');}catch{}ws.close();}if(browser)browser.kill();server.kill();}})().catch(e=>{console.error(e);process.exitCode=1;});
