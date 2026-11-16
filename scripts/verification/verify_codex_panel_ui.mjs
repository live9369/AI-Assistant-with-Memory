// Component-level interaction checks, without a browser or a real account.
import {readFile,writeFile} from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=await readFile(new URL('../../digital_life/web/app.js',import.meta.url),'utf8');
class Element {
 constructor(tag,attrs={},...children){this.tag=tag;this.attrs=attrs;Object.assign(this,attrs);this.children=[];this.listeners={};this.isConnected=true;this.append(...children);}
 append(...children){this.children.push(...children.flat(Infinity).filter(x=>x!==null&&x!==undefined));}
 replaceChildren(...children){this.children=[];this.append(...children);}
 addEventListener(event,fn){(this.listeners[event]??=[]).push(fn);}
 async event(type,event={preventDefault(){}}){for(const fn of this.listeners[type]||[])await fn(event);if(type==='click'&&this.attrs.onclick)await this.attrs.onclick(event);}
 reportValidity(){return true;}
 get textContent(){return this.children.map(x=>x instanceof Element?x.textContent:String(x)).join(' ');}
 set textContent(value){this.children=[value];}
}
const el=(tag,attrs={},...children)=>new Element(tag,attrs,...children);
let root;const calls=[];const notices=[];const checks=[];
const find=(id,node=root)=>{if(!(node instanceof Element))return null;if(node.id===id)return node;for(const child of node.children){const found=find(id,child);if(found)return found;}return null;};
const ctx={setInterval:()=>{},setTimeout:()=>{},el,state:{modelDirty:false},safe:fn=>fn,button:(text,fn,kind='',attrs={})=>el('button',{...attrs,onclick:fn},text),select:(id,options,value)=>el('select',{id,value},options.map(([v,label])=>el('option',{value:v},label))),textInput:(id,value,attrs)=>el('input',{id,value,...attrs}),field:(label,node,hint)=>el('label',{},label,node,hint),panel:(title,node)=>el('section',{},title,node),heading:(...c)=>el('h1',{},...c),notice:(...c)=>el('aside',{},...c),pairs:items=>el('dl',{},items.map(([a,b])=>el('div',{},a,b))),busy:async(node,fn)=>fn(),confirmAction:async()=>true,notify:text=>notices.push(text),loadView:async()=>{},$:selector=>selector==='#content'?root:find(selector.slice(1)),renderModel:()=>el('div',{},'Other model'),encodeURIComponent,Math,Number,api:async(path,body)=>{calls.push({path,body});if(path==='/v1/codex/authorize')return {scope:'instance',available:true,logged_in:false,login_state:'pending',user_code:'TEST-4321',expires_in:299};if(path==='/v1/codex/authorize/cancel')return {scope:'instance',available:true,logged_in:false,login_state:'cancelled'};if(path.startsWith('/v1/codex/status'))return {scope:'local',available:true,logged_in:true,plan:'prolite',login_state:'idle'};if(path==='/v1/codex/test')return {available:true,configuration_current:true,usage:{latency_ms:123,input_tokens:20,output_tokens:10}};return {};
}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function renderCodexModel(')),ctx);
const data={configuration:{backend:'codex_cli',model:'fixture',enabled:true,timeout:120,context_window:16384},configuration_id:'config-1',codex_auth_scope:'local',can_edit:true};
root=el('main',{},ctx.renderCodexModel(data,{items:[]}));
assert(find('model-name'));assert(find('codex-authorize'));assert(find('codex-test'));checks.push('Codex form and controls rendered');
await find('validate-model').event('click');assert.equal(calls.at(-1).body.configuration.backend,'codex_cli');assert(!('executable' in calls.at(-1).body.configuration));assert(!('auth_home' in calls.at(-1).body.configuration));checks.push('Configuration sends no executable or auth directory');
await find('codex-status').event('click');assert(find('codex-auth-status').textContent.includes('已登录 ChatGPT'));checks.push('Login state displayed');
await find('codex-authorize').event('click');assert.equal(find('codex-auth-scope').value,'instance');assert.equal(find('codex-verification-link').href,'https://auth.openai.com/codex/device');assert.equal(find('codex-device-code').textContent,'TEST-4321');checks.push('Device code uses fixed official link and isolated scope');
await find('codex-cancel').event('click');assert(!find('codex-device-code'));checks.push('Cancellation clears code from displayed component');
await find('model-form').event('submit');assert.equal(calls.at(-1).body.expected_configuration_id,'config-1');assert.equal(calls.at(-1).body.codex_auth_scope,'instance');checks.push('Save pins expected revision and chosen scope');
await find('codex-test').event('click');assert.equal(calls.at(-1).body.confirm_inference,true);assert.equal(calls.at(-1).body.expected_configuration_id,'config-1');assert(find('codex-test-result').textContent.includes('连接和结构化输出通过'));checks.push('Explicit connection test shows usage and pins saved configuration');
root=el('main',{},ctx.renderCodexModel({...data,can_edit:false},{items:[]}));assert(find('save-model').disabled);assert(find('codex-authorize').disabled);assert(find('codex-test').disabled);checks.push('Stopped-state restriction disables mutation controls');
const report={scope:'component fixtures, no browser rendering or OAuth completion',passed:checks.length,checks};
await writeFile(new URL('../../outputs/acceptance/codex-panel-ui-acceptance.json',import.meta.url),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
