const {spawn}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'nexys-app-test-'));
const code="import desktop; desktop.main(port=0, profile="+JSON.stringify(profile.replaceAll('\\','/'))+", extra_browser_args=('--headless=new','--remote-debugging-port=0'))";
const child=spawn(path.resolve('runtime/python/python.exe'),['-c',code],{windowsHide:true});let output='';child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>output+=b);
const exited=new Promise(r=>child.on('exit',r));const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{let socket;try{
 let port;for(let i=0;i<100;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{await delay(100);}}
 assert.ok(port,'app browser started');const pages=await(await fetch('http://127.0.0.1:'+port+'/json')).json();
 const page=pages.find(p=>p.url.startsWith('http://127.0.0.1:'));assert.ok(page,'app loaded local backend');
 assert.equal((await(await fetch(new URL('/api/health',page.url))).json()).ok,true);
 const version=await(await fetch('http://127.0.0.1:'+port+'/json/version')).json();socket=new WebSocket(version.webSocketDebuggerUrl);await new Promise(r=>socket.addEventListener('open',r));socket.send(JSON.stringify({id:1,method:'Browser.close'}));
 const exit=await Promise.race([exited,delay(10000).then(()=>{throw Error('backend stayed alive after app exit');})]);assert.equal(exit,0,output);console.log('App lifecycle passed: isolated window, healthy backend, automatic backend exit.');
 }finally{socket?.close();if(child.exitCode===null)child.kill();}})().catch(e=>{console.error(e);process.exitCode=1;});
