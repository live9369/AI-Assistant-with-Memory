/** Real Chrome/CDP acceptance. All instance and browser-profile data are temporary. */
import {spawn,spawnSync} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir,rm,readdir,stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const OUT=join(ROOT,'outputs/acceptance');
const CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const checks=[];const runtimeErrors=[];let server,chrome,cdp;
async function hashes(folder,prefix=''){
  const result={};for(const item of await readdir(folder,{withFileTypes:true})){const name=join(prefix,item.name);if(item.isDirectory())Object.assign(result,await hashes(join(folder,item.name),name));else if(item.isFile())result[name]=createHash('sha256').update(await readFile(join(folder,item.name))).digest('hex');}return result;
}
function assert(value,message){if(!value)throw new Error(message);}
function pass(name){checks.push({name,passed:true});console.log('PASS '+name);}
async function waitFile(path,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){try{return await readFile(path,'utf8');}catch{}await delay(75);}throw new Error('Timed out waiting for isolated service readiness');}
class CDP {
  constructor(url){this.ws=new WebSocket(url);this.id=0;this.pending=new Map();this.ready=new Promise((res,rej)=>{this.ws.addEventListener('open',res,{once:true});this.ws.addEventListener('error',rej,{once:true});});this.ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const value=this.pending.get(message.id);if(value){clearTimeout(value.timer);this.pending.delete(message.id);message.error?value.reject(new Error(message.error.message)):value.resolve(message.result);}}else if(message.method==='Runtime.exceptionThrown')runtimeErrors.push(message.params.exceptionDetails.text);});}
  async call(method,params={}){await this.ready;const id=++this.id;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error('CDP timeout: '+method));},20000);this.pending.set(id,{resolve,reject,timer});this.ws.send(JSON.stringify({id,method,params}));});}
  async evaluate(expression){const result=await this.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;}
  async wait(expression,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(await this.evaluate(expression))return;await delay(60);}throw new Error('Browser condition not reached: '+expression);}
  async clickExpression(expression){const box=await this.evaluate(`(()=>{const node=${expression};if(!node)throw new Error('Target missing');if(node.disabled)throw new Error('Target disabled');node.scrollIntoView({block:'center'});const r=node.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);await this.call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...box});await this.call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...box});}
  click(selector){return this.clickExpression(`document.querySelector(${JSON.stringify(selector)})`);}
  textButton(text,root='document'){return this.clickExpression(`Array.from((${root}).querySelectorAll('button')).find(node=>node.textContent.trim()===${JSON.stringify(text)})`);}
  async fill(selector,value){await this.evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});if(!input)throw new Error('Input missing');input.value=${JSON.stringify(value)};input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
  async screenshot(name,width){await this.evaluate('document.querySelector("#toast").hidden=true');const height=await this.evaluate('Math.max(document.documentElement.scrollHeight,window.innerHeight)');const result=await this.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width,height,scale:1}});await writeFile(join(OUT,'screenshots',name+'.png'),Buffer.from(result.data,'base64'));}
  close(){this.ws.close();}
}
async function stop(child,group=false){if(!child||child.exitCode!==null||child.signalCode!==null)return;const ended=new Promise(res=>child.once('exit',res));try{group?process.kill(-child.pid,'SIGTERM'):child.kill('SIGTERM');}catch{}await Promise.race([ended,delay(3500)]);if(child.exitCode===null&&child.signalCode===null){try{group?process.kill(-child.pid,'SIGKILL'):child.kill('SIGKILL');}catch{}await Promise.race([ended,delay(1500)]);}}

const temp=await mkdtemp(join(tmpdir(),'digital-life-panel-'));
const formalBefore=await hashes(join(ROOT,'work/primordial00'));
assert(formalBefore.WAKE_DISABLED,'Formal wake lock missing; no browser test started');
await mkdir(join(OUT,'screenshots'),{recursive:true});await mkdir(join(temp,'downloads'));
const report={version:'0.5.0',checks,formal_instance_unchanged:false,formal_wake_lock_unchanged:false,runtime_started:false,remote_api_contacted:false};
try{
  const ready=join(temp,'panel-ready.json');
  server=spawn('python3',[join(ROOT,'scripts/development/dashboard_fixture.py'),'--root',join(temp,'instance'),'--ready',ready],{cwd:ROOT,stdio:['ignore','ignore','pipe']});
  let serverErrors='';server.stderr.on('data',data=>serverErrors+=String(data));
  const info=JSON.parse(await waitFile(ready));
  const profile=join(temp,'browser-profile');
  chrome=spawn(CHROME,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions','--no-proxy-server','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'--window-size=1440,1040',info.url],{cwd:temp,detached:true,stdio:['ignore','ignore','ignore']});
  const port=Number((await waitFile(join(profile,'DevToolsActivePort'))).split('\n')[0]);
  const tabs=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();const target=tabs.find(item=>item.type==='page');
  cdp=new CDP(target.webSocketDebuggerUrl);await cdp.call('Runtime.enable');await cdp.call('Page.enable');
  await cdp.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1040,deviceScaleFactor:1,mobile:false});
  await cdp.call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:join(temp,'downloads'),eventsEnabled:true});
  await cdp.wait('!!document.querySelector("#connect")');
  await cdp.fill('#controller-token','incorrect-isolated-token');await cdp.click('#connect');await cdp.wait('document.querySelector("#toast").textContent.includes("控制令牌无效")');pass('invalid-token feedback');
  await cdp.fill('#controller-token',info.token);await cdp.click('#connect');await cdp.wait('document.querySelector("h1")?.textContent==="总览"');
  assert(await cdp.evaluate('document.querySelector("#runtime-badge").textContent==="禁止唤醒"'),'Lock status not visible');
  assert(await cdp.evaluate('localStorage.length===0&&sessionStorage.length===0&&!location.search'),'Credentials persisted in browser storage');pass('authenticated overview and memory-only token');
  await cdp.screenshot('dashboard-overview',1440);
  await cdp.click('#navigation [data-view="activities"]');await cdp.wait('!!document.querySelector("#new-task")');
  assert(await cdp.evaluate('!window.panelInjected&&document.querySelectorAll("img").length===0'),'Untrusted task rendered as HTML');pass('activities and untrusted text safety');
  await cdp.click('#new-task');await cdp.fill('#task-text','浏览器隔离测试任务');await cdp.click('#save-task');await cdp.wait('document.querySelector("#toast").textContent.includes("任务已保存")');pass('save task without inference');
  await cdp.click('[data-activity="'+info.refs.pending+'"]');await cdp.wait('document.querySelector("#dialog-title")?.textContent==="活动详情"');await cdp.textButton('取消活动','document.querySelector("#dialog")');await cdp.textButton('确认取消','document.querySelector("#dialog")');await cdp.wait('document.querySelector("#toast").textContent.includes("活动已取消")');pass('activity details and guarded cancellation');
  await cdp.click('#approvals-tab');await cdp.wait('!!document.querySelector("[data-approval]")');await cdp.click('[data-approval="'+info.refs.approve.approval+'"]');await cdp.wait('!!document.querySelector("#approval-reviewed")');
  assert(await cdp.evaluate('document.querySelector("#approve-decision").disabled'),'Approval not gated by review');await cdp.screenshot('dashboard-approval',1440);
  await cdp.click('#approval-reviewed');await cdp.click('#approve-decision');await cdp.wait('document.querySelector("#toast").textContent.includes("已批准")');pass('approval argument review and decision');
  await cdp.click('[data-approval="'+info.refs.reject.approval+'"]');await cdp.wait('!!document.querySelector("#reject-decision")');await cdp.click('#reject-decision');await cdp.wait('document.querySelector("#toast").textContent.includes("已拒绝")');pass('rejection');
  await cdp.click('[data-approval="'+info.refs.expire.approval+'"]');await cdp.wait('document.querySelector("#dialog")?.open');assert(await cdp.evaluate('document.querySelector("#approve-decision").disabled&&document.querySelector("#reject-decision").disabled'),'Expired approval still enabled');
  await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await cdp.wait('!document.querySelector("#dialog").open');pass('expired approval and keyboard close');
  await cdp.click('#navigation [data-view="model"]');await cdp.wait('!!document.querySelector("#model-form")');await cdp.fill('#model-name','panel-browser-model');await cdp.click('#validate-model');await cdp.wait('document.querySelector("#toast").textContent.includes("校验通过")');
  await cdp.click('#save-model');await cdp.wait('document.querySelector("#dialog-title")?.textContent.includes("保存新的模型")');await cdp.textButton('保存新版本','document.querySelector("#dialog")');await cdp.wait('document.querySelector("#toast").textContent.includes("配置已保存")');pass('offline validation and versioned model save');
  await cdp.fill('#model-backend','remote_chat');await cdp.wait('!!document.querySelector("#model-key-env")');await cdp.fill('#model-name','remote-browser-fixture');await cdp.fill('#model-base-url','https://not-contacted.invalid/v1');
  assert(await cdp.evaluate('!document.querySelector("#model-enabled").checked&&document.querySelector("#model-key-env").type==="text"'),'Remote form default changed');
  await cdp.click('#save-model');await cdp.wait('document.querySelector("#dialog").open');await cdp.textButton('保存新版本','document.querySelector("#dialog")');await cdp.wait('document.querySelector("#toast").textContent.includes("配置已保存")&&document.querySelector("#model-unsaved")?.textContent.includes("当前表单")&&document.querySelector("#model-name")?.value==="remote-browser-fixture"');pass('remote configuration remains disabled and key-free');
  await cdp.click('#probe-model');await cdp.wait('document.querySelector("#dialog").open');await cdp.textButton('检查清单','document.querySelector("#dialog")');await cdp.wait('document.querySelector("#toast").textContent.includes("清单检查未通过")');pass('explicit disabled-provider probe feedback');await cdp.screenshot('dashboard-model',1440);
  await cdp.fill('#model-name','unsaved-model');await cdp.click('#navigation [data-view="health"]');await cdp.wait('document.querySelector("#dialog-title")?.textContent.includes("离开模型配置")');await cdp.textButton('离开','document.querySelector("#dialog")');await cdp.wait('!!document.querySelector("#check-health")');pass('unsaved model edit navigation guard');
  assert(await cdp.evaluate('document.body.textContent.includes("尚未进行健康检查")'),'Health GET performed implicit check');await cdp.click('#check-health');await cdp.wait('document.querySelector("#toast").textContent.includes("健康检查已记录")');
  assert(await cdp.evaluate('document.querySelectorAll(".health-card").length===10&&Array.from(document.querySelectorAll(".health-card")).find(n=>n.textContent.includes("认知质量")).textContent.includes("证据不足")'),'Unknown health evidence lost');pass('explicit health scan and honest unknown state');await cdp.screenshot('dashboard-health',1440);
  await cdp.click('#navigation [data-view="logs"]');await cdp.wait('!!document.querySelector("#logs-q")');await cdp.fill('#logs-q','fixture.privacy');await cdp.click('#filter-logs');await cdp.wait('document.querySelectorAll("[data-log]").length===1');
  await cdp.click('[data-log]');await cdp.wait('document.querySelector("#dialog-title")?.textContent==="日志详情"');
  assert(await cdp.evaluate('!document.querySelector("#dialog").textContent.includes("fixture-never-export-api-secret")&&!document.querySelector("#dialog").textContent.includes("private task body")&&document.querySelector("#dialog").textContent.includes("[已隐藏]")'),'Log detail leaked private values');
  await cdp.textButton('关闭','document.querySelector("#dialog")');await cdp.click('#export-logs');await cdp.wait('document.querySelector("#toast").textContent.includes("已导出")');
  let download;for(let i=0;i<50;i++){download=(await readdir(join(temp,'downloads'))).find(name=>name.endsWith('.jsonl'));if(download)break;await delay(100);}assert(download,'Browser export did not download');const exported=await readFile(join(temp,'downloads',download),'utf8');assert(!exported.includes('fixture-never-export-api-secret')&&!exported.includes('private task body'),'Export leaked private data');pass('log filtering, detail and real download redaction');
  await cdp.fill('#logs-q','no-such-event-89531');await cdp.click('#filter-logs');await cdp.wait('document.body.textContent.includes("暂无匹配日志")');pass('empty filtered logs');
  await cdp.fill('#logs-q','');await cdp.click('#filter-logs');await cdp.wait('document.querySelectorAll("[data-log]").length>1');await cdp.screenshot('dashboard-logs',1440);
  await cdp.call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await cdp.click('#navigation [data-view="overview"]');await cdp.wait('document.querySelector("h1")?.textContent==="总览"');
  assert(await cdp.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),'Mobile page overflows horizontally');await cdp.screenshot('dashboard-mobile',390);pass('mobile navigation and responsive overview');
  await cdp.click('#navigation [data-view="activities"]');await cdp.wait('!!document.querySelector("#new-task")');assert(await cdp.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),'Mobile table overflows page');pass('mobile table contained scrolling');
  await cdp.click('#stop');await cdp.wait('document.querySelector("#dialog").open');await cdp.textButton('保持停止','document.querySelector("#dialog")');await cdp.wait('document.querySelector("#toast").textContent.includes("用户停止")');pass('persistent stop without unlock');
  await cdp.click('#disconnect');await cdp.wait('!!document.querySelector("#connect")');assert(await cdp.evaluate('document.querySelector("#controller-token").value===""&&localStorage.length===0&&document.querySelector("#dialog").childElementCount===0'),'Disconnect did not clear credentials');pass('disconnect clears credentials and view');
  assert(runtimeErrors.length===0,'Browser runtime errors: '+runtimeErrors.join(';'));assert(!serverErrors.includes('Traceback'),'HTTP server raised an unhandled error');pass('no uncaught browser or server errors');
  const proof=spawnSync('python3',['-c',`import sys,json\nfrom digital_life.infrastructure.persistence.sqlite_store import Store\nfrom digital_life.application.monitoring.management import Management\ns=Store(sys.argv[1]);print(json.dumps({'wake_disabled':(s.root/'WAKE_DISABLED').exists(),'action_attempts':len(s.rows('action_attempts')),'thought_requests':len(s.rows('thought_requests')),'control':Management(s).control()['active_process_run_id']}));s.close()`,join(temp,'instance')],{cwd:ROOT,encoding:'utf8'});
  assert(proof.status===0,proof.stderr);const data=JSON.parse(proof.stdout);assert(data.wake_disabled&&data.action_attempts===0&&data.thought_requests===3&&data.control===null,'Panel started life execution');report.isolated_instance_proof=data;pass('locked fixture has no new inference, tools or runtime');
}catch(error){report.error=String(error.stack||error);process.exitCode=1;console.error(report.error);if(cdp){try{report.browser_text=await cdp.evaluate('document.body.innerText');await cdp.screenshot('dashboard-failure',await cdp.evaluate('window.innerWidth'));}catch{}}}
finally{
  if(cdp)cdp.close();await stop(chrome,true);await stop(server);
  const after=await hashes(join(ROOT,'work/primordial00'));report.formal_instance_unchanged=JSON.stringify(formalBefore)===JSON.stringify(after);report.formal_wake_lock_unchanged=formalBefore.WAKE_DISABLED===after.WAKE_DISABLED;
  report.browser_stopped=!chrome||chrome.exitCode!==null||chrome.signalCode!==null;report.http_server_stopped=!server||server.exitCode!==null||server.signalCode!==null;
  report.successful=!report.error&&report.formal_instance_unchanged&&report.formal_wake_lock_unchanged&&report.browser_stopped&&report.http_server_stopped;
  await writeFile(join(OUT,'dashboard-browser-acceptance.json'),JSON.stringify(report,null,2)+'\n');await rm(temp,{recursive:true,force:true});
  if(!report.successful)process.exitCode=1;console.log('Saved dashboard browser acceptance: '+checks.length+' checks, successful='+report.successful);
}
