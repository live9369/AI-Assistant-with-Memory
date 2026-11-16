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
 async event(type,event={preventDefault(){}}){for(const fn of this.listeners[type]||[])await fn(event);if(this.attrs['on'+type])await this.attrs['on'+type](event);}
 reportValidity(){return true;}
 get textContent(){return this.children.map(x=>x instanceof Element?x.textContent:String(x)).join(' ');}
 set textContent(value){this.children=[value];}
}
const el=(tag,attrs={},...children)=>new Element(tag,attrs,...children);
let root;const calls=[];const notices=[];const checks=[];
const find=(id,node=root)=>{if(!(node instanceof Element))return null;if(node.id===id)return node;for(const child of node.children){const found=find(id,child);if(found)return found;}return null;};
const ctx={labels:{pending:'待处理'},crypto:globalThis.crypto,setInterval:()=>{},setTimeout:()=>{},el,state:{modelDirty:false},safe:fn=>fn,button:(text,fn,kind='',attrs={})=>el('button',{...attrs,onclick:fn},text),select:(id,options,value)=>el('select',{id,value},options.map(([v,label])=>el('option',{value:v},label))),textInput:(id,value,attrs)=>el('input',{id,value,...attrs}),field:(label,node,hint)=>el('label',{},label,node,hint),panel:(title,node)=>el('section',{},title,node),heading:(...c)=>el('h1',{},...c),notice:(...c)=>el('aside',{},...c),pairs:items=>el('dl',{},items.map(([a,b])=>el('div',{},a,b))),busy:async(node,fn)=>fn(),confirmAction:async()=>true,notify:text=>notices.push(text),loadView:async()=>{},$:selector=>selector==='#content'?root:find(selector.slice(1)),renderModel:()=>el('div',{},'Other model'),encodeURIComponent,Math,Number,api:async(path,body)=>{calls.push({path,body});if(path==='/v1/codex/authorize')return {scope:'instance',available:true,logged_in:false,login_state:'pending',user_code:'TEST-4321',expires_in:299};if(path==='/v1/codex/authorize/cancel')return {scope:'instance',available:true,logged_in:false,login_state:'cancelled'};if(path.startsWith('/v1/codex/status'))return {scope:'local',available:true,logged_in:true,plan:'prolite',login_state:'idle'};if(path==='/v1/codex/test')return {available:true,configuration_current:true,usage:{latency_ms:123,input_tokens:20,output_tokens:10}};return {};
}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function renderCodexModel(')),ctx);

const originalApi=ctx.api;const messages=[];ctx.api=async(path,body)=>{
 calls.push({path,body});
 if(path==='/v1/chats')return {items:[]};
 if(path.endsWith('/messages')){messages.push({role:'user',text:body.text,state:'pending'});return {activity_id:'activity-1'};}
 if(path.startsWith('/v1/chats/'))return {thread_id:'thread',messages,last_activity_id:messages.length?'activity-1':null,can_send:!messages.length};
 return originalApi(path,body);
};
ctx.state.chatId='thread';ctx.state.chatDraft='';const node=await ctx.renderChat();root=el('main',{},node);await node.refreshChat();
assert(find('chat-input'));assert(!find('chat-send').disabled);checks.push('Chat form and empty state render');
find('chat-input').value='hello';await find('chat-input').event('input');await node.refreshChat();assert.equal(find('chat-input').value,'hello');checks.push('Polling preserves unsent draft');
await find('chat-form').event('submit');const sent=calls.find(c=>c.path.endsWith('/messages'));assert.equal(sent.body.text,'hello');assert.equal(sent.body.expected_last_activity_id,null);assert(sent.body.idempotency_key);assert(!('history' in sent.body));checks.push('Send uses message key and revision without provider history');
assert.equal(find('chat-input').value,'');assert(find('chat-send').disabled);checks.push('Saved draft clears and pending turn blocks second send');
messages.push({role:'assistant',text:'Hello user',waiting_reason:'waiting'});await node.refreshChat();assert(find('chat-messages').textContent.includes('Hello user'));checks.push('Accepted reply is displayed by polling');
const report={scope:'component fixtures; no browser rendering',passed:checks.length,checks};await writeFile(new URL('../../outputs/acceptance/chat-ui-acceptance.json',import.meta.url),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
