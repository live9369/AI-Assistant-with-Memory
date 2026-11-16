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
 setAttribute(key,value){this.attrs[key]=value;}
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


ctx.badge=(state,label)=>el('span',{},label||state);ctx.time=x=>x||'未记录';ctx.technical=(value,title)=>el('details',{},title,el('pre',{},JSON.stringify(value)));ctx.labels={succeeded:'成功'};
const detail={request:{id:'request-1',state:'succeeded',model_config_id:'pinned-config'},input:{available:true,value:{context_mode:'fresh_request',task:'X'.repeat(6000)}},features:[{name:'人格',items:[{field:'personality',state:'provided',value:{openness:.7}}]},{name:'关系',items:[{field:'relationships',state:'not_in_request',value:null}]}],attempts:[{attempt_no:1,state:'received',model:'fixture'}],results:[{response:{available:true,value:{explanation:'公开回应'}},parsed_output:{available:true,value:{explanation:'公开回应',action:{tool:'wait'}}},validation_state:'valid',acceptance:'accepted'}],usage:[],pinned_model_configuration:{model:'fixture'}};
function inspect(data){
 const view=ctx.renderThoughtDetail(data);root=view;
 assert(view.textContent.includes('本轮概览'));assert(!view.textContent.includes('排查数据'));
 const captured=el('div',{},view.textContent);
 const nav=view.children[1].children[0];
 for(const tab of nav.children){tab.attrs.onclick();
  function expand(node){if(!(node instanceof Element))return;if(node.tag==='details'){node.open=true;for(const fn of node.listeners.toggle||[])fn();}for(const child of node.children)expand(child);}
  expand(view);captured.append(el('span',{},view.textContent));
 }
 return captured;
}
root=inspect(detail);assert(root.textContent.includes('项已提供'));assert(root.textContent.includes('未进入本次输入'));assert(root.textContent.includes('X'.repeat(6000)));assert(root.textContent.includes('公开回应'));assert(root.textContent.includes('尚无用量记录'));checks.push('Historical feature coverage, full long input, output, missing usage displayed');
root=inspect({...detail,input:{available:false,reason:'完整性校验未通过'},results:[],attempts:[{state:'failed',error_code:'Timeout'}]});assert(root.textContent.includes('完整性校验未通过'));assert(root.textContent.includes('尚无可读取的结果'));assert(root.textContent.includes('Timeout'));checks.push('Missing input and failed call shown without fabricated output');

root=inspect({...detail,behavior_decisions:[{available:true,value:{candidates:[{action:{tool:'write_note'},probability:.25},{action:{tool:'wait'},probability:.75}],selected_index:1,draw:.8}}]});assert(root.textContent.includes('选择概率'));assert(root.textContent.includes('已选中'));assert(root.textContent.includes('75.0%'));assert(root.textContent.includes('公开回应'));checks.push('Behavior probabilities and actual selection are shown separately from original model response');


root=inspect({...detail,features:[{name:'人格',items:[{field:'personality_growth',state:'provided',value:{profile:'profile-grown-2',uncertainty:{openness:{n:3,status:'controller-annotated-not-psychometrically-calibrated'}}}}]}]});assert(root.textContent.includes('人格成长'));assert(root.textContent.includes('profile-grown-2'));assert(root.textContent.includes('not-psychometrically-calibrated'));checks.push('Historical personality growth profile and uncertainty provenance remain visible');


root=inspect({...detail,features:[{name:'习惯',items:[{field:'habit_learning',state:'provided',value:{opportunities:[{state:'extinct',acquisition:.3,inhibition:.9,strength:0,revision:'habit-revision-8'}]}}]}]});assert(root.textContent.includes('习惯学习'));assert(root.textContent.includes('extinct'));assert(root.textContent.includes('inhibition'));assert(root.textContent.includes('habit-revision-8'));checks.push('Habit acquisition, inhibitory trace, lifecycle and historical revision remain visible');


root=inspect({...detail,features:[{name:'关系',items:[{field:'relationships',state:'provided',value:{mentions:[{label:'陈明',status:'ambiguous',identity_verified:false}],behavior_reliability:{domain:'behavior',condition:{source:'user'},estimate:.6,n:3,unresolved:false},registry_revision:'people-revision-9'}}]}]});assert(root.textContent.includes('ambiguous'));assert(root.textContent.includes('identity_verified'));assert(root.textContent.includes('behavior_reliability'));assert(root.textContent.includes('people-revision-9'));checks.push('Person ambiguity, conditional relationship evidence and frozen registry revision are shown');


root=inspect({...detail,features:[{name:'选中记忆',items:[{field:'memory_quality',state:'provided',value:{selected:[{revision:'memory-revision-10',parents:[{revision:'source-revision'}],conflicts:[{status:'controller-labelled-unresolved'}]}],retrieval:{mode:'hashed-token-index',candidate_truncated:true}}}]}]});assert(root.textContent.includes('记忆质量'));assert(root.textContent.includes('memory-revision-10'));assert(root.textContent.includes('controller-labelled-unresolved'));assert(root.textContent.includes('candidate_truncated'));checks.push('Memory source revisions, unresolved conflicts and bounded retrieval diagnostics are visible');

root=inspect({...detail,features:[{name:'探索',items:[{field:'autonomy_agenda',state:'provided',value:{commitment:{state:'active',due_at:'2030-01-01T00:00:00.000Z'},declared_interest:{topic:'counts',affinity:.8},measurement_kind:'local-fact-coverage; not psychological learning'}}]}]});assert(root.textContent.includes('自主安排'));assert(root.textContent.includes('declared_interest'));assert(root.textContent.includes('local-fact-coverage'));checks.push('Commitment deadline, declared interest and bounded measurement meaning remain visible');

root=inspect({...detail,features:[{name:'健康',items:[{field:'self_maintenance',state:'provided',value:{auto_repair:true,remaining_repairs:2,diagnosis:{state:'unknown',dimensions:{cognition:{state:'unknown'}}},lifecycle_authority:'CLI only'}}]}]});assert(root.textContent.includes('自我维持'));assert(root.textContent.includes('remaining_repairs'));assert(root.textContent.includes('unknown'));assert(root.textContent.includes('CLI only'));checks.push('Health uncertainty, bounded repair budget and CLI lifecycle authority are shown');

const report={scope:'component fixtures; not browser rendering',passed:checks.length,checks};await writeFile(new URL('../../outputs/acceptance/thought-inspection-ui.json',import.meta.url),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
