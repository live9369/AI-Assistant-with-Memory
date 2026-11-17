const $ = (selector, root = document) => root.querySelector(selector);
const state = {connected:false, session:0, view:'overview', load:0, overview:null, modelDirty:false,
  tab:'activities', filters:{activities:{},approvals:{},logs:{}}, cursors:{activities:null,approvals:null,logs:null}, stacks:{activities:[],approvals:[],logs:[]}};
const labels = {pending:'待处理',running:'进行中',waiting_input:'等待输入',waiting_tool:'等待工具',paused:'已暂停',completed:'已完成',failed:'失败',cancelled:'已取消',
  approved:'已批准',rejected:'已拒绝',expired:'已过期',healthy:'正常',stressed:'受压',degraded:'降级',critical:'危急',recovering:'恢复中',unknown:'证据不足',
  locked:'禁止唤醒',stopped:'已停止',registered:'运行已登记',idle:'待机',info:'信息',warning:'提醒',error:'错误',prepared:'已准备',succeeded:'成功'};
const tones = {pending:'warn',running:'blue',waiting_input:'warn',waiting_tool:'blue',paused:'muted',completed:'good',failed:'bad',cancelled:'muted',approved:'good',
  rejected:'muted',expired:'warn',healthy:'good',stressed:'warn',degraded:'bad',critical:'bad',recovering:'blue',unknown:'muted',locked:'warn',stopped:'muted',registered:'blue',idle:'muted',info:'muted',warning:'warn',error:'bad'};
const toolNames = {write_note:'写入笔记',read_file:'读取文件',list_files:'列出文件'};
const healthNames = {identity:'身份',memory:'记忆关联',storage:'数据库',resources:'存储资源',workspace:'工作目录',behavior_permissions:'行为与权限',continuity:'连续性',relationships_commitments:'关系与承诺',cognition:'认知质量',dependencies:'模型依赖'};
let toastTimer, dialogResolve;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key,value] of Object.entries(attrs)) {
    if (value === undefined || value === null) continue;
    if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(),value);
    else if (key === 'class') node.className = value;
    else if (['value','checked','disabled','hidden'].includes(key)) node[key] = value;
    else node.setAttribute(key,String(value));
  }
  for (const child of children.flat(Infinity)) if (child !== undefined && child !== null) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
function badge(value, text) { return el('span',{class:'badge '+(tones[value] || 'muted')},text || labels[value] || value); }
function button(text, action, kind = 'secondary', attrs = {}) { return el('button',{type:'button',class:'button '+kind,onclick:safe(action),...attrs},text); }
function safe(fn) { return async (...args) => { try { await fn(...args); } catch (error) { if (error.name !== 'AbortError') notify(error.message || '请求未完成，请重试。','error'); } }; }
function notify(message,kind='success') { clearTimeout(toastTimer); const node=$('#toast'); node.textContent=message; node.className='toast'+(kind==='error'?' error':''); node.hidden=false; toastTimer=setTimeout(()=>node.hidden=true,6500); }
async function busy(node, fn) { const disabled=node.disabled; $('#toast').hidden=true;$('#toast').textContent='';node.disabled=true; node.setAttribute('aria-busy','true'); try { return await fn(); } finally { if(node.isConnected){node.disabled=disabled;node.removeAttribute('aria-busy');} } }
function time(value) { if(!value) return '—'; const date=new Date(value); return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}); }
function query(params={}) { const search=new URLSearchParams(); for(const [key,value] of Object.entries(params)) if(value!==null&&value!==undefined&&value!=='')search.set(key,String(value)); return search.size?'?'+search.toString():''; }
async function api(path,body,raw=false,quietAuth=false) {
  const session=state.session; const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),path==='/v1/codex/test'?610000:25000);
  try {
    const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal,cache:'no-store'});
    if(session!==state.session) throw new DOMException('连接已改变','AbortError');
    if(!response.ok){const data=await response.json(); const error=new Error(data.error?.message || '请求失败，请刷新后重试。');error.code=data.error?.code;error.status=response.status;if(error.code==='INVALID_TOKEN'&&!quietAuth)disconnect();throw error;}
    const value=raw ? await response.text() : await response.json();
    if(session!==state.session) throw new DOMException('连接已改变','AbortError');
    return value;
  } catch(error) { if(error.name==='AbortError' && session===state.session) throw new Error('请求已超时，可手动重试；写入结果请先刷新核对。'); if(error instanceof TypeError) throw new Error('无法连接本机服务，请确认服务仍在运行。'); throw error; }
  finally { clearTimeout(timeout); }
}
function heading(title,subtitle,...actions) { return el('div',{class:'page-heading'},el('div',{},el('h1',{},title),el('p',{},subtitle)),el('div',{class:'heading-actions'},actions)); }
function notice(title,description,warning=false) { return el('div',{class:'notice'+(warning?' warning':'')},el('span',{'aria-hidden':'true'},warning?'◇':'○'),el('div',{},el('strong',{},title),description?el('p',{},description):null)); }
function panel(title,body,action) { return el('section',{class:'panel'},el('div',{class:'panel-heading'},el('h2',{},title),action),el('div',{class:'panel-body'},body)); }
function pairs(items) { return el('dl',{class:'key-values'},items.map(([name,value])=>el('div',{},el('dt',{},name),el('dd',{},value)))); }
function field(title,input,hint,extra='') { return el('label',{class:'field '+extra},el('span',{},title),input,hint?el('small',{},hint):null); }
function select(id,options,value='') { return el('select',{id,value},options.map(([id,label])=>el('option',{value:id,selected:id===value?'selected':null},label))); }
function textInput(id,value='',attrs={}) { return el('input',{id,type:'text',value,autocomplete:'off',...attrs}); }
function technical(value,title='技术详情') { return el('details',{},el('summary',{},title),el('pre',{},JSON.stringify(value,null,2))); }
function empty(title,description) { return el('div',{class:'empty'},el('strong',{},title),description); }
function loading() { return el('div',{class:'loading'},'正在读取…'); }

const dialog=$('#dialog');
dialog.addEventListener('close',()=>{if(!dialog.open){dialog.replaceChildren();if(dialogResolve){dialogResolve(false);dialogResolve=null;}} });
function closeDialog() { if(dialog.open)dialog.close();dialog.replaceChildren(); }
function openDialog(title,body,actions=[]) {
  if(dialogResolve){dialogResolve(false);dialogResolve=null;}
  dialog.replaceChildren(el('div',{class:'dialog-header'},el('h2',{id:'dialog-title'},title),button('×',closeDialog,'quiet',{'aria-label':'关闭弹窗'})),
    el('div',{class:'dialog-body'},body),el('div',{class:'dialog-footer'},actions.length?actions:[button('关闭',closeDialog)]));
  if(!dialog.open)dialog.showModal();
}
function confirmAction(title,description,confirmText='确认',danger=false) {
  return new Promise(resolve=>{openDialog(title,el('p',{},description),[
    button('返回',()=>{dialogResolve=null;closeDialog();resolve(false);}),
    button(confirmText,()=>{dialogResolve=null;closeDialog();resolve(true);},danger?'danger':'')]);dialogResolve=resolve;});
}
function updateHeader(data) {
  const headingLabel=$('.instance-line .eyebrow');if(headingLabel)headingLabel.textContent='实例';
  state.overview=data; $('#instance-name').textContent=data.name; const tag=$('#runtime-badge');tag.textContent=labels[data.runtime_status]||data.runtime_status;tag.className='badge '+(tones[data.runtime_status]||'muted');
  const count=$('#approval-badge');count.textContent=data.pending_approvals;count.hidden=!data.pending_approvals;
  $('#last-updated').textContent='最近刷新 '+time(new Date().toISOString());
}
function disconnect() {
  state.account=null;state.chatId=null;state.chatDraft='';state.chatKey=null;state.session++;state.connected=false;state.modelDirty=false;state.overview=null;state.stopRequestKey=null;state.load++;
  closeDialog();$('#instance-name').textContent='尚未连接';$('#runtime-badge').textContent='未连接';$('#runtime-badge').className='badge muted';$('#approval-badge').hidden=true;
  $('#refresh').disabled=true;$('#stop').disabled=true;$('#disconnect').hidden=true;$('#auto-refresh').checked=false;$('#last-updated').textContent='等待连接';renderConnect();
}
async function renderConnect() {
  const session=state.session;
  for(const item of document.querySelectorAll('[data-view]'))item.hidden=true;
  $('#stop').hidden=true;$('#content').replaceChildren(loading());
  try {
    const status=await api('/v1/auth/status');if(session!==state.session)return;
    if(!status.accounts_enabled){$('#content').replaceChildren(panel('账户未启用',el('p',{},'请先使用CLI安装账户模块，再刷新页面。')));return;}
    if(status.root_setup_required){$('#content').replaceChildren(el('section',{class:'panel connect-card'},rootSetupForm()));return;}
    try {await connectAccount(true);return;}catch(error){if(session!==state.session)return;if(![401,403].includes(error.status))throw error;}
    $('#content').replaceChildren(el('section',{class:'panel connect-card'},accountLoginForm()));
  }catch(error){if(session===state.session)$('#content').replaceChildren(panel('暂时无法连接',el('div',{},el('p',{},error.message),button('重试',()=>renderConnect()))));}
}

const navigationToggle=$('#navigation-toggle');
if(navigationToggle)navigationToggle.addEventListener('click',()=>{
  const expanded=navigationToggle.getAttribute('aria-expanded')!=='true';
  navigationToggle.setAttribute('aria-expanded',String(expanded));
  navigationToggle.textContent=expanded?'收起导航':'展开导航';
  $('#navigation').classList.toggle('is-expanded',expanded);
});
async function navigate(view) {
  if(state.modelDirty && !await confirmAction('离开当前配置页？','未保存的表单修改将被丢弃。','离开'))return;
  state.modelDirty=false;state.view=view;
  if(navigationToggle){navigationToggle.setAttribute('aria-expanded','false');navigationToggle.textContent='展开导航';$('#navigation').classList.remove('is-expanded');}
  for(const item of document.querySelectorAll('[data-view]')){if(item.dataset.view===view)item.setAttribute('aria-current','page');else item.removeAttribute('aria-current');}
  if(state.connected)await loadView();
}
async function loadView(prefetched) {
  if(!state.connected)return;const ticket=++state.load;const view=state.view;const content=$('#content');content.replaceChildren(loading());
  try {
    if(state.account){
      state.account=(await api('/v1/auth/me')).account;
      if(!['chat','account','accounts','memories'].includes(view)&&state.account.role!=='root')return navigate('chat');
      if(['chat','account','accounts','memories'].includes(view)){
        const headingLabel=$('.instance-line .eyebrow');if(headingLabel)headingLabel.textContent='账户';
        $('#instance-name').textContent=state.account.display_name+' · '+({root:'最高权限',admin:'管理员',member:'普通账户',guest:'访客'}[state.account.role]||state.account.role);$('#runtime-badge').textContent='已登录';$('#runtime-badge').className='badge muted';$('#last-updated').textContent='最近刷新 '+time(new Date().toISOString());
        const node=view==='chat'?await renderChat():view==='account'?await renderAccount():view==='accounts'?await renderAccounts():await renderAccountMemories();
        if(ticket===state.load&&state.connected)content.replaceChildren(node);return;
      }
    }
    const overview=prefetched || await api('/v1/overview');if(ticket!==state.load)return;updateHeader(overview);
    let node;
    if(view==='overview')node=renderOverview(overview);
    else if(view==='chat')node=await renderChat();
    else if(view==='activities')node=await renderActivities();
    else if(view==='model'){const [data,templates]=await Promise.all([api('/v1/model/configuration'),api('/v1/model/templates')]);node=renderModel(data,templates);}
    else if(view==='settings')node=await renderInstanceSettings();
    else if(view==='health')node=renderHealth(await api('/v1/health'));
    else node=await renderLogs();
    if(ticket===state.load && state.connected)content.replaceChildren(node);
  }catch(error){if(ticket===state.load&&state.connected){content.replaceChildren(heading('暂时无法读取','当前页面没有自动执行其他操作。'),notice('请求未完成',error.message,true),button('重新读取',()=>loadView()));}throw error;}
}
function renderOverview(data) {
  const model=data.model.configuration;const backend={ollama:'本地 Ollama',llamacpp:'本地 llama.cpp',remote_chat:'远程 API',codex_cli:'Codex 订阅推理',unconfigured:'未配置'}[model.backend]||'未配置';
  const stats=el('div',{class:'stats-grid'},[
    ['进行中的活动',data.active_activities,'含等待与暂停中的活动'],['待审阅操作',data.pending_approvals,'仅包含当前仍可决定的审批'],['已完成活动',data.activity_counts.completed||0,'已持久记录的完成状态'],['健康状态',labels[data.health.state]||'证据不足',data.health.stale?'尚无新鲜检查结果':'最近一次多维检查']
  ].map(([name,value,meta])=>el('div',{class:'stat'},el('span',{class:'stat-label'},name),el('strong',{class:'stat-value'+(typeof value==='string'?' word':'')},value),el('span',{class:'stat-meta'},meta))));
  const timeline=el('ol',{class:'timeline'},data.recent_events.map(item=>el('li',{},el('span',{class:'timeline-title'},item.title),el('time',{},time(item.recorded_at)))));
  const lock=data.wake_disabled || data.restore_reconciliation_required;
  return el('div',{},heading('总览','查看运行状态与最近活动。',button('处理待审阅操作',()=>{state.tab='approvals';return navigate('activities');},'')),
    lock?notice('实例已锁定','查看与编辑不会解除唤醒锁。',true):null,stats,
    el('div',{class:'columns'},panel('最近发生',data.recent_events.length?timeline:empty('暂无事件','后续操作会在这里留下记录。'),button('全部日志',()=>navigate('logs'),'quiet small')),
      panel('当前接入',pairs([['接入方式',backend],['模型',model.model==='unconfigured'?'尚未配置':model.model],['配置版本',data.model.version],['用户控制',data.control.user_stopped?'已保持停止':'允许已授权的外部运行'],['健康检查',data.health.checked_at?time(data.health.checked_at):'尚未检查']]),button('管理配置',()=>navigate('model'),'quiet small'))));
}
function resetPage(key) {state.cursors[key]=null;state.stacks[key]=[];}
function pagination(key,data) {
  return el('div',{class:'pagination'},el('span',{},'本页 '+data.items.length+' 条'),el('div',{},
    button('上一页',async()=>{state.cursors[key]=state.stacks[key].pop()??null;await loadView();},'secondary small',{disabled:!state.stacks[key].length}),
    button('下一页',async()=>{state.stacks[key].push(state.cursors[key]);state.cursors[key]=data.next_cursor;await loadView();},'secondary small',{disabled:!data.has_more})));
}
function table(headers,rows,label) {return el('div',{class:'table-wrap'},el('table',{'aria-label':label},el('thead',{},el('tr',{},headers.map(name=>el('th',{scope:'col'},name)))),el('tbody',{},rows)));}
async function renderActivities() {
  const key=state.tab,approvals=key==='approvals',filters=state.filters[key];
  const data=await api('/v1/'+(approvals?'approvals':'activities')+query({...filters,cursor:state.cursors[key],limit:20}));
  const status=select('activity-filter-status',[['','全部状态'],...(approvals?['pending','approved','rejected','expired','cancelled']:['pending','running','waiting_input','waiting_tool','paused','completed','failed','cancelled']).map(value=>[value,labels[value]])],filters[approvals?'status':'state']||'');
  const search=textInput('activity-filter-q',filters.q||'',{placeholder:approvals?'按任务或工具搜索':'按任务内容搜索',maxlength:200});
  const filterForm=el('form',{class:'filters',onsubmit:safe(async event=>{event.preventDefault();state.filters[key]={[approvals?'status':'state']:status.value,q:search.value};resetPage(key);await loadView();})},
    field('搜索',search,null,'grow'),field('状态',status),el('button',{type:'submit',class:'button secondary'},'筛选'),button('重置',async()=>{state.filters[key]={};resetPage(key);await loadView();},'quiet'));
  const rows=data.items.map(item=>el('tr',{},
    el('td',{},el('span',{class:'cell-main'},item.task||'未命名任务'),el('code',{class:'cell-sub'},item.id.slice(0,12))),
    approvals?el('td',{},toolNames[item.tool]||item.tool):null,
    el('td',{},badge(approvals?item.status:item.state)),el('td',{},time(approvals?item.expires_at:item.recorded_at)),
    el('td',{},el('div',{class:'row-actions'},approvals?
      button(item.can_decide?'审阅操作':'查看审批',()=>openApproval(item.id),'secondary small',{'data-approval':item.id}):
      [button('查看过程',()=>openActivity(item.id),'secondary small',{'data-activity':item.id}),button('取消活动',()=>cancelActivity(item),'quiet small',{disabled:!item.can_cancel})]))));
  return el('div',{},heading('活动与审批','跟踪一次活动，核对每一个将要发生的操作。',button('新建任务',newTask,'', {id:'new-task'})),
    el('div',{class:'tabs'},button('活动记录',async()=>{state.tab='activities';await loadView();},'quiet tab'+(!approvals?' active':''),{id:'activities-tab'}),button('操作审批',async()=>{state.tab='approvals';await loadView();},'quiet tab'+(approvals?' active':''),{id:'approvals-tab'})),
    filterForm,el('section',{class:'panel'},rows.length?table(approvals?['关联任务','工具','状态','有效期','处理']:['任务','状态','创建时间','处理'],rows,approvals?'操作审批列表':'活动列表'):empty(approvals?'暂无匹配的审批':'暂无匹配的活动',approvals?'审批由实际思考活动产生，面板不会生成虚构提案。':'可以先保存一个任务；保存不会自动推理。'),pagination(key,data)));
}
function newTask() {
  let key=crypto.randomUUID();const input=el('textarea',{id:'task-text',rows:5,required:true,maxlength:16000,placeholder:'描述需要保存的任务…',oninput:()=>{key=crypto.randomUUID();}});
  const save=button('保存任务',async()=>{if(!input.reportValidity())return;await busy(save,async()=>{await api('/v1/events',{text:input.value,idempotency_key:key});closeDialog();resetPage('activities');state.tab='activities';await loadView();notify('任务已保存，未启动思考或执行。');});},'',{id:'save-task'});
  openDialog('新建任务',el('div',{},notice('只保存待办','此操作不会唤醒实例。'),field('任务内容',input)),[button('返回',closeDialog),save]);
}
async function cancelActivity(item) {
  if(!await confirmAction('取消这个活动？','取消后不再推进后续步骤；已经发生的外部作用不会被撤销。','确认取消',true))return;
  await api('/v1/activities/'+encodeURIComponent(item.id)+'/cancel',{expected_revision:item.revision});closeDialog();await loadView();notify('活动已取消。');
}
async function openActivity(id) {
  const data=await api('/v1/activities/'+encodeURIComponent(id));
  const transitions=data.transitions.map(item=>el('li',{},el('span',{class:'timeline-title'},(labels[item.from_state]||item.from_state)+' → '+(labels[item.to_state]||item.to_state)),el('time',{},time(item.recorded_at))));
  const body=el('div',{},pairs([['任务',data.task],['当前状态',badge(data.state)],['创建时间',time(data.recorded_at)],['截止时间',time(data.deadline)]]),
    el('h3',{class:'section-title'},'它的回应'),renderActivityReplies(data.responses||[]),
    el('h3',{class:'section-title'},'活动过程'),transitions.length?el('ol',{class:'timeline'},transitions):el('p',{class:'subtle'},'已保存任务，尚无后续状态变化。'),
    el('h3',{class:'section-title'},'思考与步骤'),el('p',{class:'subtle'},data.thoughts.length?'已记录 '+data.thoughts.length+' 个思考请求、'+data.steps.length+' 个步骤。':'尚无思考请求。保存任务不会自动调用模型。'),
    button('查看思考执行详情',()=>openThoughts(data.id),'secondary',{id:'activity-thoughts'}),
    technical({id:data.id,revision:data.revision,steps:data.steps,thoughts:data.thoughts}));
  openDialog('活动详情',body,[button('关闭',closeDialog),button('取消活动',()=>cancelActivity(data),'danger-outline',{disabled:!data.can_cancel})]);
}
async function openApproval(id) {
  const data=await api('/v1/approvals/'+encodeURIComponent(id));
  const reason=el('textarea',{id:'approval-reason',rows:2,maxlength:1000,placeholder:'可选：记录决定的原因'});const checked=el('input',{type:'checkbox',id:'approval-reviewed'});
  const approve=button('批准此操作',()=>decide('approved'),' ',{id:'approve-decision',disabled:true});
  const reject=button('拒绝此操作',()=>decide('rejected'),'danger-outline',{id:'reject-decision',disabled:!data.can_decide});
  checked.addEventListener('change',()=>{approve.disabled=!checked.checked||!data.can_decide;});
  async function decide(decision) {
    approve.disabled=true;reject.disabled=true;
    try {
      await api('/v1/approvals/'+encodeURIComponent(id)+'/decision',{decision,expected_revision:data.revision,expected_arguments_hash:data.arguments_hash,reason:reason.value});
      closeDialog();await loadView();notify(decision==='approved'?'已批准并记录；面板未启动执行进程。':'已拒绝此操作。');
    }catch(error){if(error.status===409){await openApproval(id);}else {approve.disabled=!checked.checked||!data.can_decide;reject.disabled=!data.can_decide;}throw error;}
  }
  const body=el('div',{},pairs([['关联任务',data.task],['工具',toolNames[data.tool]||data.tool],['审批状态',badge(data.status)],['有效期',time(data.expires_at)]]),
    el('h3',{class:'section-title'},'请核对操作参数'),el('pre',{id:'approval-arguments'},JSON.stringify(data.arguments,null,2)),
    pairs([['作用范围',data.scope.root||'—']]),technical({arguments_hash:data.arguments_hash,proposal_revision:data.proposal_revision},'参数校验摘要'),
    el('div',{class:'hint'},data.can_decide?'批准会进入执行队列；只有另行获准运行的工作进程才可能执行。禁止唤醒锁继续生效。':'此审批已决定、过期或不再可用，不能再次批准。'),
    data.can_decide?el('div',{},el('h3',{class:'section-title'},'决定记录'),field('处理说明',reason),el('label',{class:'check-line'},checked,el('span',{},'我已核对工具、参数和作用范围。'))):null);
  openDialog('审阅操作',body,[button('关闭',closeDialog),reject,approve]);
}
function renderModel(data,templates,draft=null) {
  if((draft||data.configuration).backend==='codex_cli')return renderCodexModel(data,templates,draft);
  const current=draft || data.configuration;const config=current.backend==='unconfigured'?{}:current;const backend=config.backend||'';
  const backendField=select('model-backend',[['','请选择接入方式'],['ollama','本地 Ollama'],['llamacpp','本地 llama.cpp'],['remote_chat','远程 API'],['codex_cli','Codex 订阅推理']],backend);
  const model=textInput('model-name',config.model||'',{required:true,placeholder:'模型名称或供应商模型标识'});
  const address=textInput('model-base-url',config.base_url||'',{type:'url',required:true,placeholder:backend==='remote_chat'?'https://供应商地址/v1':'http://127.0.0.1:11434'});
  const numeric=(id,value,min,max,step='1')=>el('input',{id,type:'number',value,min,max,step,required:true});
  const timeout=numeric('model-timeout',config.timeout??120,1,600),output=numeric('model-output',config.max_output_tokens??2048,1,backend==='remote_chat'?32768:8192);
  const context=numeric('model-context',config.context_window??8192,2048,backend==='remote_chat'?262144:32768),temperature=numeric('model-temperature',config.temperature??0,0,2,'0.1');
  const keyEnv=textInput('model-key-env',config.api_key_env||'DIGITAL_LIFE_LLM_API_KEY',{pattern:'[A-Z][A-Z0-9_]{2,127}',required:true});
  const remoteEnabled=el('input',{id:'model-enabled',type:'checkbox',checked:config.enabled===true});
  const format=select('model-format',[['json_schema','JSON Schema'],['json_object','JSON Object']],config.response_format||'json_schema');
  const tokenParameter=select('model-token-parameter',[['max_tokens','max_tokens'],['max_completion_tokens','max_completion_tokens']],config.token_parameter||'max_tokens');
  const responseModels=textInput('model-accepted-models',(config.accepted_response_models||[]).join(', '),{placeholder:'可选；多个名称以逗号分隔'});
  const template=select('model-template',[['','选择一个模板'],...templates.items.map(item=>[item.id,item.label])]);
  const form=el('form',{id:'model-form'});const unsaved=el('span',{class:'subtle',id:'model-unsaved'},draft?'有未保存的修改':'当前表单与已保存配置一致');
  function markDirty(){state.modelDirty=true;unsaved.textContent='有未保存的修改';}
  form.addEventListener('input',markDirty);form.addEventListener('change',markDirty);
  backendField.addEventListener('change',()=>{
    if(backendField.value==='codex_cli'){$('#content').replaceChildren(renderCodexModel(data,templates,{backend:'codex_cli',model:'',enabled:false,timeout:120,max_input_bytes:262144}));return;}
    const target=templates.items.find(item=>item.configuration.backend===backendField.value);
    if(target){$('#content').replaceChildren(renderModel(data,templates,target.configuration));state.modelDirty=true;}
  });
  function values() {
    const value={backend:backendField.value,model:model.value.trim(),base_url:address.value.trim(),timeout:Number(timeout.value),max_output_tokens:Number(output.value),context_window:Number(context.value),temperature:Number(temperature.value)};
    if(value.backend==='remote_chat'){Object.assign(value,{api_key_env:keyEnv.value.trim(),enabled:remoteEnabled.checked,response_format:format.value,token_parameter:tokenParameter.value});const accepted=responseModels.value.split(',').map(v=>v.trim()).filter(Boolean);if(accepted.length)value.accepted_response_models=accepted;}
    return value;
  }
  const validateButton=button('离线校验',async()=>{if(!form.reportValidity())return;await busy(validateButton,async()=>{await api('/v1/model/validate',{configuration:values()});notify('表单校验通过，未联网或调用模型。');});},'secondary',{id:'validate-model'});
  const save=el('button',{id:'save-model',type:'submit',class:'button',disabled:!data.can_edit},'保存新版本');
  form.addEventListener('submit',safe(async event=>{event.preventDefault();if(!form.reportValidity())return;
    const configuration=values();await api('/v1/model/validate',{configuration});
    if(!await confirmAction('保存新的模型配置？','这会追加配置版本，不联网、不推理。已有思考请求不会改用新路由。','保存新版本'))return;
    await busy(save,async()=>{await api('/v1/model/configuration',{configuration,expected_configuration_id:data.configuration_id});state.modelDirty=false;await loadView();notify('模型配置已保存，未检查网络或启动推理。');});
  }));
  const grid=el('div',{class:'form-grid'},field('接入方式',backendField),field('模型名称',model),field('服务地址',address,'填写服务根地址；远程模板通常包含 /v1。','span-two'),
    field('请求超时（秒）',timeout),field('输出上限',output),field('本地输入检查上限（字节）',context,'这是项目的字节检查上限，不是模型 token 窗口；本地模型同时沿用该值设置运行窗口。'),field('采样温度',temperature));
  if(backend==='remote_chat')grid.append(field('密钥环境变量名称',keyEnv,'只填写变量名，面板不接收真实API密钥。','span-two'),field('输出形式',format),field('输出预算字段',tokenParameter),
    field('允许的响应模型名称',responseModels,'留空时仅接受所配置模型名。','span-two'),el('label',{class:'check-line span-two'},remoteEnabled,el('span',{},'允许此配置使用远程服务。实际调用时会发送本次任务、所选记忆和情境。')));
  const configuredCredential=backend==='remote_chat'?el('div',{class:'form-notice'},'已保存配置的密钥变量：'+(data.credential_present?'当前服务进程可读取':'当前服务进程未发现；面板不会显示其值')):null;
  form.append(grid,el('div',{class:'form-actions'},validateButton,save,unsaved));
  if(draft)state.modelDirty=true;
  const probeButton=button('检查已保存配置的清单',async()=>{
    if(!await confirmAction('检查模型清单？','此操作可能访问已配置的模型服务，但不进行生成。未保存的表单不会用于此次检查。','检查清单'))return;
    await busy(probeButton,async()=>{const result=await api('/v1/model/probe',{expected_configuration_id:data.configuration_id});notify(result.available?'模型清单可访问；尚未验证生成质量。':result.reason,result.available?'success':'error');if(!state.modelDirty)await loadView();});
  },'secondary',{id:'probe-model'});
  const probe=data.last_probe;
  return el('div',{},heading('模型配置','接入方式、调用预算和版本记录分开管理。'),
    !data.can_edit?notice('当前配置不可修改','请先停止运行，并等待活动进程退出。离线校验仍可使用。',true):notice('保存配置不会启动模型','仅创建新配置版本；远程接入需要明确启用并由进程环境提供密钥。'),
    el('section',{class:'panel'},el('div',{class:'panel-heading'},el('h2',{},'接入参数'),el('div',{class:'template-tools'},template,button('载入模板',async()=>{const selected=templates.items.find(item=>item.id===template.value);if(!selected){notify('请先选择一个模板。','error');return;}if(state.modelDirty&&!await confirmAction('载入模板？','当前未保存的修改将被替换。','载入'))return;$('#content').replaceChildren(renderModel(data,templates,selected.configuration));},'secondary small'))),
      el('div',{class:'panel-body'},configuredCredential,form)),
    panel('已保存版本与服务检查',pairs([['当前版本',data.version],['保存时间',time(data.recorded_at)],['清单检查',probe?badge(probe.available?'healthy':'degraded',probe.available?'清单可访问':'未通过'):'尚未检查'],['检查时间',time(probe?.checked_at)],['验证范围','清单可访问不等于生成质量通过。']]),probeButton));
}
function renderHealth(data) {
  const reasons={identity:['身份锚点与当前实例对应。','身份锚点需要核对。'],memory:['当前记忆修订关联完整。','记忆关联需要核对。'],storage:['数据库和外键检查通过。','数据库完整性需要处理。'],resources:['存储空间满足当前最低保留要求。','可用存储空间低于保留要求。'],workspace:['受控工具工作目录可用。','工作目录不可用或存在路径异常。'],behavior_permissions:['已记录的动作有授权，结果明确。','存在授权或未知执行结果需要核对。'],continuity:['当前未发现恢复核对阻断。','恢复副本需要先核对身份与外部作用。'],relationships_commitments:['未发现已登记的逾期活动承诺。','存在逾期承诺需要处理。']};
  const check=button('重新检查健康',async()=>{await busy(check,async()=>{await api('/v1/health/check',{});await loadView();notify('本地健康检查已记录，未连接模型或启动进程。');});},'',{id:'check-health'});
  return el('div',{},heading('健康','分别看待必要功能、证据缺口与需要处理的问题。',check),
    data.stale?notice(data.checked_at?'检查结果已超过有效期':'尚未进行健康检查',data.checked_at?'可以按需重新检查；过期结果不能视为当前健康证明。':'读取页面不自动执行检查，也不会将未知项显示为正常。',true):notice('检查结果已记录','本轮只做本地观测，未知维度仍需额外证据。'),
    el('p',{class:'health-time'},'最近检查：'+time(data.checked_at)+' · 观测有效期 '+data.ttl_seconds+' 秒'),
    el('div',{class:'health-grid'},Object.entries(data.dimensions).map(([name,item])=>{
      const text=item.state==='unknown'?(name==='cognition'?'需要独立任务评测，不能由进程存在判定。':name==='dependencies'?'尚未取得依赖清单检查证据。':'尚无足够的该维度检查证据。'):(reasons[name]?.[item.state==='healthy'?0:1]||'请查看具体检查依据。');
      return el('article',{class:'health-card'},el('header',{},el('h2',{},healthNames[name]||name),badge(item.state)),el('p',{},text),technical({reason:item.reason,assessment:item.assessment},'检查依据'));
    })));
}
async function renderLogs() {
  const filters=state.filters.logs;
  const data=await api('/v1/logs'+query({...filters,cursor:state.cursors.logs,limit:30}));
  const level=select('logs-level',[['','全部等级'],['info','信息'],['warning','提醒'],['error','错误']],filters.level||'');
  const search=textInput('logs-q',filters.q||'',{placeholder:'事件类型或来源，如 activity',maxlength:200});
  const activity=textInput('logs-activity',filters.activity_id||'',{placeholder:'可选：关联活动编号',maxlength:200});
  const toLocal=value=>value?new Date(new Date(value).getTime()-new Date(value).getTimezoneOffset()*60000).toISOString().slice(0,16):'';
  const from=el('input',{id:'logs-from',type:'datetime-local',value:toLocal(filters.from)}),to=el('input',{id:'logs-to',type:'datetime-local',value:toLocal(filters.to)});
  const form=el('form',{class:'filters',onsubmit:safe(async event=>{event.preventDefault();state.filters.logs={q:search.value,level:level.value,activity_id:activity.value,from:from.value?new Date(from.value).toISOString():'',to:to.value?new Date(to.value).toISOString():''};resetPage('logs');await loadView();})},
    field('搜索',search,null,'grow'),field('等级',level),field('关联活动',activity),field('开始时间',from),field('结束时间',to),el('button',{type:'submit',class:'button secondary',id:'filter-logs'},'筛选'),button('重置',async()=>{state.filters.logs={};resetPage('logs');await loadView();},'quiet'));
  const rows=data.items.map(item=>el('tr',{},el('td',{},time(item.recorded_at)),el('td',{},badge(item.level)),el('td',{},el('span',{class:'cell-main'},item.title),el('code',{class:'cell-sub'},item.event_type)),el('td',{},item.activity_id?el('code',{},item.activity_id.slice(0,10)):'—'),el('td',{},button('查看详情',async()=>{const detail=await api('/v1/logs/'+item.event_seq);openDialog('日志详情',el('div',{},pairs([['事件',detail.title],['时间',time(detail.recorded_at)],['等级',badge(detail.level)],['事件类型',detail.event_type],['关联活动',detail.activity_id||'—']]),el('h3',{class:'section-title'},'脱敏记录'),el('pre',{},JSON.stringify(detail.payload,null,2))));},'secondary small',{'data-log':item.event_seq}))));
  const exportButton=button('导出筛选结果',async()=>{await busy(exportButton,async()=>{const text=await api('/v1/logs/export'+query({...state.filters.logs,limit:500}),undefined,true);const url=URL.createObjectURL(new Blob([text],{type:'application/x-ndjson'}));const a=el('a',{href:url,download:'yuan-chu-00-logs-'+new Date().toISOString().slice(0,10)+'.jsonl'});document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('已导出最近最多500条匹配日志，敏感内容已隐藏。');});},'secondary',{id:'export-logs',disabled:!data.items.length});
  return el('div',{},heading('日志','按条件定位事件，保留过程与可核对的结果。',exportButton),form,
    el('section',{class:'panel'},rows.length?table(['时间','等级','事件','关联活动','详情'],rows,'日志列表'):empty('暂无匹配日志','可调整时间、等级或关键词重新筛选。'),pagination('logs',data)),
    el('p',{class:'hint'},'等级按事件类别推导。默认列表不展示任务正文；详情与导出经过脱敏。'));
}

document.querySelectorAll('[data-view]').forEach(item=>item.addEventListener('click',safe(()=>navigate(item.dataset.view))));
$('#refresh').addEventListener('click',safe(async()=>{if(state.modelDirty&&!await confirmAction('重新读取配置？','未保存的修改将丢弃。','重新读取'))return;state.modelDirty=false;await busy($('#refresh'),()=>loadView());}));
$('#stop').addEventListener('click',safe(async()=>{if(!await confirmAction('保持实例停止？','持久记录用户停止。不会解除禁止唤醒锁，也不会启动版本回退。','保持停止',true))return;await busy($('#stop'),async()=>{state.stopRequestKey=state.stopRequestKey||crypto.randomUUID();await api('/v1/control/stop',{idempotency_key:state.stopRequestKey});state.stopRequestKey=null;await loadView();notify('已记录用户停止状态。');});}));
$('#disconnect').addEventListener('click',safe(async()=>{if(state.account)await api('/v1/auth/logout',{});disconnect();notify('已退出登录。');}));
setInterval(safe(async()=>{if(state.connected&&$('#auto-refresh').checked&&!['model','chat','settings'].includes(state.view)&&!dialog.open&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))await loadView();}),15000);
renderConnect();

function renderCodexModel(data,templates,draft=null) {
  const config=draft||data.configuration;const form=el('form',{id:'model-form'});
  const backend=select('model-backend',[['codex_cli','Codex 订阅推理'],['ollama','本地 Ollama'],['llamacpp','本地 llama.cpp'],['remote_chat','远程 API']],'codex_cli');
  backend.addEventListener('change',()=>{const target=templates.items.find(i=>i.configuration.backend===backend.value);if(target)$('#content').replaceChildren(renderModel(data,templates,target.configuration));});
  const model=textInput('model-name',config.model||'',{required:true,placeholder:'例如 gpt-6.1-sol'});
  const scope=select('codex-auth-scope',[['local','本机已有登录'],['instance','此实例独立授权']],data.codex_auth_scope||'local');
  const timeout=el('input',{id:'model-timeout',type:'number',min:1,max:600,required:true,value:config.timeout??120});
  const context=el('input',{id:'model-context',type:'number',min:2048,max:262144,required:true,value:config.max_input_bytes??config.context_window??262144});
  const enabled=el('input',{id:'model-enabled',type:'checkbox',checked:config.enabled===true});
  const unsaved=el('span',{id:'model-unsaved',class:'subtle'},draft?'有未保存的修改':'当前表单与已保存配置一致');
  function dirty(){state.modelDirty=true;unsaved.textContent='有未保存的修改';}
  form.addEventListener('input',dirty);form.addEventListener('change',dirty);
  const budgetMode=select('codex-budget-mode',[['hard_limits','严格硬限额（Codex暂不可用）'],['post_usage','调用后核账（超限或未知时停止）']],config.budget_mode||'hard_limits');
  form.append(field('用量保护',budgetMode),el('p',{class:'muted'},'调用后核账不能限制已经产生的服务端消耗；原额度不变，超限或未知时不接纳结果并停止。'));
  function body(){return {configuration:{backend:'codex_cli',model:model.value.trim(),enabled:enabled.checked,timeout:Number(timeout.value),max_input_bytes:Number(context.value),budget_mode:budgetMode.value},codex_auth_scope:scope.value};}
  const validate=button('离线校验',async()=>{if(form.reportValidity())await busy(validate,async()=>{await api('/v1/model/validate',body());notify('配置校验通过，未授权或调用模型。');});},'secondary',{id:'validate-model'});
  const save=el('button',{id:'save-model',type:'submit',class:'button',disabled:!data.can_edit},'保存新版本');
  form.addEventListener('submit',safe(async event=>{event.preventDefault();if(!form.reportValidity())return;
    if(!await confirmAction('保存Codex模型配置？','保存不会登录、调用模型或唤醒实例。','保存新版本'))return;
    await busy(save,async()=>{await api('/v1/model/configuration',{...body(),expected_configuration_id:data.configuration_id});state.modelDirty=false;await loadView();notify('Codex配置已保存。');});
  }));
  form.append(el('div',{class:'form-grid'},field('接入方式',backend),field('模型名称',model),field('授权来源',scope,'本机登录可直接复用；新的设备码登录只写入此实例独立授权目录。','span-two'),field('请求超时（秒）',timeout),field('完整输入上限（UTF-8 字节）',context,'max_input_bytes：默认 262144（256 KiB）；含项目提示词，正文预留 1024 字节。不含 Codex 固定上下文，也不是模型 token 窗口。'),el('label',{class:'check-line span-two'},enabled,el('span',{},'允许此配置使用Codex订阅额度。'))),el('div',{class:'form-actions'},validate,save,unsaved));
  const auth=el('div',{id:'codex-auth-status'},el('p',{},'尚未检查登录状态。'));
  function showAuth(result){
    const names={idle:'无待处理授权',pending:'等待你在官方网页确认',completed:'授权已完成',cancelled:'授权已取消',expired:'本地授权会话已过期',failed:'授权未完成'};
    auth.replaceChildren(pairs([['授权来源',result.scope==='instance'?'此实例独立授权':'本机已有登录'],['登录状态',result.available?(result.logged_in?'已登录 ChatGPT':result.auth_type==='apiKey'?'当前为API Key登录，需使用ChatGPT授权':'未登录 ChatGPT'):'暂时无法检查'],['套餐',({prolite:'Pro',pro:'Pro',plus:'Plus',business:'Business',enterprise:'Enterprise'})[result.plan]||result.plan||'未提供'],['授权进度',names[result.login_state]||'未知']]));
    if(result.reason)auth.append(el('p',{},result.reason));
    if(result.login_state==='pending')auth.append(el('div',{class:'notice warning'},el('div',{},el('strong',{},'设备码：'),el('code',{id:'codex-device-code'},result.user_code),el('p',{},'在官方页面输入此代码；约 '+result.expires_in+' 秒后本地会话失效。'),el('a',{id:'codex-verification-link',href:'https://auth.openai.com/codex/device',target:'_blank',rel:'noopener noreferrer'},'打开官方授权页面'))));
  }
  const refresh=button('查看登录状态',async()=>{await busy(refresh,async()=>showAuth(await api('/v1/codex/status?scope='+encodeURIComponent(scope.value))));},'secondary',{id:'codex-status'});
  const authorize=button('设备码授权',async()=>{
    if(!await confirmAction('开始此实例的独立授权？','将在官方服务生成设备码。你需要在官方网页确认；不会覆盖本机已有登录，也不会唤醒实例。','获取设备码'))return;
    await busy(authorize,async()=>{const result=await api('/v1/codex/authorize',{});scope.value='instance';dirty();showAuth(result);});
  },'secondary',{id:'codex-authorize',disabled:!data.can_edit});
  const cancel=button('取消待处理授权',async()=>{await busy(cancel,async()=>showAuth(await api('/v1/codex/authorize/cancel',{})));},'secondary',{id:'codex-cancel',disabled:!data.can_edit});
  scope.addEventListener('change',()=>auth.replaceChildren(el('p',{},'来源已切换，请重新检查。')));
  const result=el('div',{id:'codex-test-result'},'尚未测试已保存配置。');
  const test=button('测试已保存连接',async()=>{
    if(!await confirmAction('执行一次Codex连接测试？','这会消耗订阅额度。只发送固定测试题，不读取生命记忆、不执行动作、不唤醒实例。使用已保存配置，未保存修改不会参与。','开始测试'))return;
    await busy(test,async()=>{const value=await api('/v1/codex/test',{expected_configuration_id:data.configuration_id,confirm_inference:true});if(!result.isConnected)return;result.replaceChildren(pairs([['结果',value.available?'连接和结构化输出通过':'连接测试未通过'],['配置版本',value.configuration_current?'仍为当前配置':'配置已变化，请重新核对'],['耗时',value.usage?Math.round(value.usage.latency_ms)+' 毫秒':'未提供'],['输入／输出token',value.usage?(value.usage.input_tokens??'未知')+' / '+(value.usage.output_tokens??'未知'):'未提供']]));if(value.reason)result.append(el('p',{},value.reason));});
  },'secondary',{id:'codex-test',disabled:!data.can_edit||data.configuration.backend!=='codex_cli'});
  if(draft)state.modelDirty=true;
  return el('div',{},heading('模型配置','Codex设备码授权与独立推理。'),notice('配置、授权与测试分开进行','保存不推理；登录不代表模型权限或额度充足。每次测试都会创建新会话。'),panel('接入配置',form),panel('ChatGPT 登录与设备码',el('div',{},auth,el('div',{class:'form-actions'},refresh,authorize,cancel))),panel('连接测试',el('div',{},result,test)));
}

function renderActivityReplies(responses) {
  if(!responses.length)return el('p',{class:'subtle'},'尚无思考回应。');
  return el('div',{id:'activity-replies'},responses.map(item=>el('article',{class:'notice'},el('div',{},
    el('small',{},time(item.recorded_at)),
    item.reply?el('p',{class:'life-reply'},item.reply):el('p',{},item.unavailable?'回应记录暂不可用。':item.error_code?'本次思考未成功。':'尚无已接受的回应。'),
    item.waiting_reason?el('p',{class:'subtle'},'等待原因：'+item.waiting_reason):null,
    item.error_code?el('p',{class:'subtle'},'错误类型：'+item.error_code):null))));
}

async function renderChat() {
  state.chatId=state.account?.thread_id||state.chatId||crypto.randomUUID();
  const list=await api('/v1/chats');const id=state.chatId;
  const threads=select('chat-thread',[...list.items.map((item,index)=>[item.thread_id,'会话 '+(index+1)+' · '+time(item.updated_at)]),...(!list.items.some(i=>i.thread_id===id)?[[id,'新会话']]:[])],id);
  threads.addEventListener('change',safe(async()=>{if(state.chatDraft&&!await confirmAction('切换会话？','未发送文字将丢弃。','切换')){threads.value=id;return;}state.chatDraft='';state.chatKey=null;state.chatId=threads.value;await loadView();}));
  const fresh=button('新会话',async()=>{if(state.chatDraft&&!await confirmAction('新建会话？','未发送文字将丢弃。','新建'))return;state.chatDraft='';state.chatKey=null;state.chatId=crypto.randomUUID();await loadView();},'secondary',{id:'chat-new'});
  const transcript=el('div',{id:'chat-messages',class:'chat-messages','aria-live':'polite'});
  const status=el('p',{id:'chat-status',class:'subtle'});const input=el('textarea',{id:'chat-input',rows:3,maxlength:4000,required:true,placeholder:'想对它说些什么？',value:state.chatDraft||'',oninput:()=>{state.chatDraft=input.value;state.chatKey=null;}});
  const send=el('button',{id:'chat-send',type:'submit',class:'button'},'发送');
  let latest=null;let sending=false;let reading=false;let signature='';
  async function refresh(){
    if(reading||!transcript.isConnected)return;reading=true;
    try{const data=await api('/v1/chats/'+id);if(!transcript.isConnected||state.chatId!==id)return;latest=data;
      const next=JSON.stringify(data.messages);if(signature!==next){const follow=!signature||transcript.scrollHeight-transcript.scrollTop-transcript.clientHeight<80;signature=next;transcript.replaceChildren(...(data.messages.length?data.messages.map(item=>el('article',{class:'chat-message '+item.role},el('strong',{},item.role==='user'?'你':item.role==='assistant'?'助手':'状态'),el('p',{class:'life-reply'},item.text),el('div',{class:'chat-message-footer'},item.role==='user'?el('small',{},labels[item.state]||item.state):null,item.waiting_reason?el('small',{},'等待原因：'+item.waiting_reason):null,item.activity_id&&(item.role!=='user'||item.state!=='completed')?button('查看思考',()=>openThoughts(item.activity_id),'quiet small'):null))): [el('p',{class:'subtle'},'从一句问候开始。实例运行时会处理消息，回复将显示在这里。')]));if(follow)transcript.scrollTop=transcript.scrollHeight;}
      send.disabled=sending||!data.can_send;status.textContent=data.can_send?'每次思考独立调用，记忆由系统接续。':'正在处理，回应将自动更新。需要审批时请查看活动。';
    }finally{reading=false;}
  }
  const form=el('form',{id:'chat-form',onsubmit:safe(async event=>{event.preventDefault();if(!input.reportValidity()||sending||!latest?.can_send)return;
    sending=true;send.disabled=true;const text=input.value;state.chatKey=state.chatKey||crypto.randomUUID();
    try{await api('/v1/chats/'+id+'/messages',{text,idempotency_key:state.chatKey,expected_last_activity_id:latest.last_activity_id});if(input.value===text){input.value='';state.chatDraft='';state.chatKey=null;}await refresh();}
    finally{sending=false;if(send.isConnected)send.disabled=!latest?.can_send;}
  })},field('消息',input,'支持多轮交流；需要执行的操作仍须按权限审批。'),send);
  const conversation=panel('对话记录',el('div',{},transcript,status,form));conversation.classList.add('chat-panel');
  const node=el('div',{class:'chat-page'},heading('交流',state.account?'与助手的持续对话':'公开回复会自动显示。',state.account?el('span',{class:'chat-scope'},state.account.username+' 的会话'):fresh),state.account?null:field('会话',threads),conversation);
  node.refreshChat=refresh;setTimeout(safe(refresh),0);return node;
}
setInterval(safe(async()=>{
  if(state.connected&&state.view==='chat'&&!document.hidden){const node=$('#content').firstElementChild;if(node?.refreshChat)await node.refreshChat();}
}),2500);

async function openThoughts(activity) {
  const data=await api('/v1/activities/'+encodeURIComponent(activity)+'/thoughts');
  const body=el('div',{},el('p',{class:'execution-note'},'查看当时的输入、输出与特征，不会重新调用模型。'),
    data.items.length?el('div',{class:'execution-list'},data.items.map((item,index)=>el('article',{class:'execution-row'},
      el('div',{},el('strong',{},'思考 '+(index+1)),el('p',{},time(item.recorded_at))),
      badge(item.state),button('查看详情',()=>openThoughtDetail(item.id,activity),'secondary small',{'data-thought':item.id})))):el('p',{class:'subtle'},'尚无思考记录。'));
  openDialog('思考执行记录',body);
}
async function openThoughtDetail(id,activity) {
  const data=await api('/v1/thoughts/'+encodeURIComponent(id));
  openDialog('本次思考：输入、输出与特征',renderThoughtDetail(data),[button('返回执行列表',()=>openThoughts(activity)),button('刷新状态',()=>openThoughtDetail(id,activity)),button('关闭',closeDialog)]);
}
function thoughtTable(headers, rows) {
  return el('div',{style:'overflow-x:auto'},el('table',{class:'data-table'},el('thead',{},el('tr',{},headers.map(h=>el('th',{scope:'col'},h)))),el('tbody',{},rows.map(row=>el('tr',{},row.map(cell=>el('td',{},cell)))))));
}
function thoughtMeter(value,min,max,label) {
  const valid=typeof value==='number'&&Number.isFinite(value)&&value>=min&&value<=max;
  if(!valid)return el('span',{},'未记录有效数值');
  return el('div',{},el('meter',{min,max,value,'aria-label':label,style:'width:100%;min-width:120px'},String(value)),el('span',{},' '+value.toFixed(3)));
}
function thoughtConversation(value) {
  const messages=Array.isArray(value?.messages)?value.messages:[];
  const roles={user:'对方',assistant:'实例',system:'系统记录',tool:'工具返回'};
  return el('div',{class:'thought-conversation'},
    el('p',{class:'thought-footnote'},'按当时传入顺序展示 '+messages.length+' 条消息'+(value?.omitted_messages?'；更早 '+value.omitted_messages+' 条未进入本次输入。':'。')),
    messages.length?el('ol',{class:'thought-transcript','aria-label':'本轮思考参考的近期交流'},messages.map((message,index)=>el('li',{class:'thought-message '+(message.role==='assistant'?'from-instance':'from-other')},
      el('div',{class:'thought-message-meta'},el('strong',{},roles[message.role]||message.role||'未记录发言方'),el('span',{},'第 '+(index+1)+' 条'),message.recorded_at?el('time',{},time(message.recorded_at)):null),
      el('div',{class:'thought-message-text'},readableThought(message.text??message.content??'未记录消息内容')),
      Object.keys(message).some(key=>!['role','text','content','recorded_at'].includes(key))?el('details',{class:'thought-message-source'},el('summary',{},'查看关联记录'),readableThought(Object.fromEntries(Object.entries(message).filter(([key])=>!['role','text','content','recorded_at'].includes(key))))):null
    ))):el('p',{},'本轮没有传入此前交流。'),
    el('details',{class:'thought-message-source'},el('summary',{},'会话范围与引用说明'),readableThought(Object.fromEntries(Object.entries(value||{}).filter(([key])=>key!=='messages')))));
}
function thoughtFeatureChart(field,value) {
  if(field==='conversation_context')return thoughtConversation(value);
  if(field==='exploration'&&value?.mode==='continuous')return el('div',{},el('p',{},'本轮按持久方向承接思考；模型解释不等于事实已验证。'),thoughtTable(['方向','当前理解','下一步','状态'],value.direction?[[value.direction.title,value.direction.understanding||'尚无阶段理解',value.direction.next_step,({thinking:'思考中',ready:'可继续',paused:'已暂存',finished:'已结束',waiting_tool:'等待工具'})[value.direction.state]||value.direction.state]]:[]),el('details',{},el('summary',{},'查看其他方向与来源'),readableThought(value.known_directions)));
  if(field==='personality'&&value&&typeof value==='object') {
    const names={openness:'开放性',conscientiousness:'尽责性',extraversion:'外向性',agreeableness:'宜人性',emotional_stability:'情绪稳定性'};
    return el('div',{},el('p',{class:'subtle'},'人格刻度 −1 至 +1；0 为中间倾向。不是人格优劣评分。'),thoughtTable(['维度','本轮倾向'],Object.entries(value).map(([key,item])=>[names[key]||key,thoughtMeter(item?.value,-1,1,names[key]||key)])));
  }
  if(field==='states'&&value&&typeof value==='object')return thoughtTable(['状态','数值','单位','有效性','采集时间','失效时间'],Object.entries(value).map(([key,item])=>[key,readableThought(item?.value),item?.unit??'未记录',item?.fresh===true?'有效':item?.fresh===false?'已过期':'未知',time(item?.observed_at),time(item?.expires_at)]));
  if(field==='selected_memories'&&Array.isArray(value))return thoughtTable(['记忆内容','选择依据','来源记录'],value.map(item=>[readableThought(item.content),item.selection_reason??'未记录',el('details',{},el('summary',{},'查看来源'),readableThought({revision_id:item.revision_id,source_kind:item.source_kind}))]));
  if(field==='cognition_snapshot'&&Array.isArray(value))return thoughtTable(['认知内容','确认状态','依据与候选'],value.map(item=>{
    let content=item.content;try{content=JSON.parse(content);}catch{}
    return [readableThought(content),item.acceptance_state==='held'?'待确认':item.acceptance_state==='accepted'?'已确认':item.acceptance_state??'未知',el('details',{},el('summary',{},'查看记录'),readableThought(item))];
  }));
  if(field==='values'&&Array.isArray(value))return thoughtTable(['价值维度','本轮激活值'],value.map(item=>[item.definition??item.name??item.dimension_id??'未记录名称',readableThought(item.activation)]));
  if(field==='goal_regulation'&&value)return el('div',{},pairs([['可否推进',value.eligible===true?'可以':value.eligible===false?'暂缓':'未知'],['动机强度',value.intensity??'未记录'],['持续倾向',value.persistence??'未记录'],['目标评分',value.score??'未记录']]),el('details',{},el('summary',{},'查看依据和预算'),readableThought(value)));
  return readableThought(value);
}
function thoughtBehaviorCharts(records) {
  const tools={wait:'等待',ask:'询问',read_file:'读取文件',list_files:'查看目录',write_note:'写入笔记'};
  return el('div',{},records.map(record=>{
    const value=record.value??record;
    if(!Array.isArray(value.candidates))return readableThought(value);
    return thoughtTable(['候选行为','选择概率','是否允许','最终选择'],value.candidates.map((item,index)=>[tools[item.action?.tool]||item.action?.tool||'未知',typeof item.probability==='number'?el('div',{},thoughtMeter(item.probability,0,1,'候选概率'),(item.probability*100).toFixed(1)+'%'):'未记录',item.eligible===true?'允许':item.eligible===false?'不允许':'未知',index===value.selected_index?'已选中':'—']));
  }));
}
function readableThought(value, depth=0) {
  const names={task:'本轮任务',text:'内容',content:'内容',value:'数值',fresh:'是否有效',unit:'单位',explanation:'模型公开说明',action:'建议行为',tool:'行为',arguments:'行为内容',reason:'说明',prediction:'事前预期',observation:'实际观察说明',revision:'理解修订',remaining_questions:'尚未解决的问题',next_attempts:'可尝试的下一步',direction_status:'方向状态',finish_basis:'结束依据',reflection:'自持思考',directions:'新方向',decision:'本轮决策',understanding:'本轮理解',next_step:'下一步',reopen_condition:'重新开启条件',title:'方向',expected_gain:'预期收获',cost:'预计成本',kind:'类型',evidence_refs:'依据记录',assessment:'评估说明',disposition:'处理结论',candidates:'候选项',probability:'概率',selected_index:'选中候选序号（从0开始）',selected:'是否选中',score:'分数',eligible:'是否允许',features:'参与因素',factors:'分数来源',claims:'信息判断',questions:'待确认问题',predictions:'预测',plan:'计划',subject:'对象',predicate:'属性',quote:'来源原文',messages:'近期交流',role:'发言方',openness:'开放性',conscientiousness:'尽责性',extraversion:'外向性',agreeableness:'宜人性',emotional_stability:'情绪稳定性',intensity:'动机强度',states:'运行状态',enabled:'是否启用',diagnosis:'健康诊断',dimensions:'各项检查',state:'状态',scope:'适用范围',input_tokens:'输入 token',output_tokens:'输出 token',latency_ms:'调用耗时（毫秒）',model:'模型',missing:'是否缺失',strength:'强度',instructions:'本轮要求'};
  const words={wait:'等待',ask:'询问',user:'用户',assistant:'实例回复',continue:'继续深入',branch:'产生分支',switch:'切换方向',pause:'暂存',finish:'结束探索',reflect:'反思',explore:'探索',create:'创作',relate:'联系经历',maintain:'维护',dormant:'暂不推进',healthy:'正常',unknown:'未知',held:'待确认'};
  if(value===null||value===undefined)return el('span',{class:'subtle'},'未记录');
  if(typeof value!=='object')return el('div',{style:'white-space:pre-wrap;overflow-wrap:anywhere'},typeof value==='boolean'?(value?'是':'否'):(words[value]??String(value)));
  if(depth>6)return el('details',{},el('summary',{},'展开详细记录'),readableThought(value,0));
  if(Array.isArray(value))return value.length?el('ol',{class:'thought-record-list'},value.map(item=>el('li',{class:'thought-record-item'},readableThought(item,depth+1)))):el('p',{class:'subtle'},'本次为空');
  return el('div',{class:'thought-record-fields'},Object.entries(value).map(([key,item])=>/(?:_ref|_refs|_id|_hash)$/.test(key)?el('details',{},el('summary',{},'来源或记录编号：'+key),readableThought(item,depth+1)):el('section',{class:'thought-record-field'},el('strong',{},names[key]||key),readableThought(item,depth+1))));
}
function renderThoughtDetail(data) {
  const input=data.input?.available?data.input.value:null;
  const fields={task:'当前任务',observation:'收到的信息',instructions:'本轮要求',conversation_context:'近期交流',personality:'人格倾向',personality_growth:'人格成长',values:'价值取向',selected_memories:'召回记忆',memory_quality:'记忆质量',behavior_policy:'行为影响因素',habit_suggestions:'习惯建议',habit_learning:'习惯学习',states:'运行状态',tools:'可用行为',motivation:'动机',goal_regulation:'目标与动机',relationships:'人物与关系',learning_feedback:'学习反馈',health:'健康',self_maintenance:'自我维持',identity:'身份',self_knowledge:'自身运行说明',reply_preferences:'交流偏好',exploration:'自主探索',autonomy_agenda:'自主安排',cognition_snapshot:'已有认知',cognition_sources:'信息依据',task_loop:'任务进度',cognitive_influence:'来源影响权重'};
  const status={provided:'已进入输入',empty:'本次为空',not_in_request:'未进入本次输入',unavailable:'记录不可用',valid:'通过',accepted:'已采用',stale:'已过期，未采用',duplicate:'重复结果，未重复采用',held:'待确认'};
  const resultBody=item=>{
    const value=item.parsed_output?.available?item.parsed_output.value:item.response?.available?item.response.value:null;
    return el('section',{},pairs([['接收时间',time(item.received_at)],['校验',status[item.validation_state]||item.validation_state||'未知'],['是否采用',status[item.acceptance]||item.acceptance||'未知']]),
      value?el('div',{},el('h4',{},'公开回复 / 模型说明'),readableThought(value.explanation??'未记录公开说明'),value.exploration?el('div',{},el('h4',{},'探索判断'),readableThought(value.exploration)):null,value.inquiry?el('div',{},el('h4',{},'预期、观察与后续问题'),readableThought(value.inquiry)):null,value.reflection?el('div',{},el('h4',{},'方向与本轮推进'),readableThought(value.reflection)):null,value.cognition?el('div',{},el('h4',{},'本轮认知记录'),readableThought(value.cognition)):null,el('h4',{},'模型建议行为'),readableThought(value.action)):el('p',{},'没有可读取的输出。'),
      item.validation_errors?.length?readableThought(item.validation_errors):null);
  };
  const root=el('div',{id:'thought-inspection',class:'thought-reader'});
  const content=el('div',{id:'thought-reader-content',class:'thought-reader-content'});
  const navigation=el('nav',{class:'thought-reader-nav','aria-label':'思考详情分类'});
  const preview=(text,label)=>{
    const value=typeof text==='string'?text:'未记录';
    if(value.length<=240)return el('p',{class:'thought-prose'},value);
    return el('div',{},el('p',{class:'thought-prose'},value.slice(0,240)+'…'),el('details',{class:'thought-more'},el('summary',{},label||'阅读完整内容'),el('p',{class:'thought-prose'},value)));
  };
  const latest=data.results.at(-1);
  const output=latest?.parsed_output?.available?latest.parsed_output.value:latest?.response?.available?latest.response.value:null;
  const usage=data.usage.at(-1);
  const views={
    overview:()=>el('div',{},el('div',{class:'thought-section-heading'},el('h3',{},'本轮概览'),el('p',{},'先看它处理了什么，以及留下了什么结果。')),
      el('section',{class:'thought-task'},el('h4',{},'本轮任务'),preview(input?.task??data.input?.reason??'输入不可用','展开完整任务')),
      el('section',{class:'thought-answer'},el('h4',{},'模型说明与回复'),preview(output?.explanation??output?.exploration?.assessment??'尚无可读取的结果。','阅读完整回复')),
      el('div',{class:'thought-facts'},pairs([['结果',latest?(status[latest.acceptance]||latest.acceptance):'尚未返回'],['模型调用耗时',typeof usage?.latency_ms==='number'?(usage.latency_ms/1000).toFixed(2)+' 秒':'未记录'],['参考记忆',Array.isArray(input?.selected_memories)?input.selected_memories.length+' 条':'未记录'],['调用方式',input?.context_mode==='fresh_request'?'独立调用':'以记录为准']])),
      el('p',{class:'thought-footnote'},'这是当时保存的记录，不是模型隐藏推理。')),
    inputs:()=>el('div',{},el('div',{class:'thought-section-heading'},el('h3',{},'参考信息'),el('p',{},'按需展开一组。进入输入不代表已证明影响程度。')),
      ...data.features.map(group=>{
        const provided=group.items.filter(item=>item.state==='provided');
        const detail=el('details',{class:'thought-accordion'},el('summary',{},el('span',{},group.name),el('span',{class:'thought-count'},provided.length?provided.length+' 项已提供':'本次未提供')));
        let built=false;
        detail.addEventListener('toggle',()=>{if(detail.open&&!built){built=true;detail.append(el('div',{class:'thought-accordion-body'},group.items.map(item=>el('section',{class:'thought-field'},el('h4',{},fields[item.field]||item.field),item.state==='provided'?thoughtFeatureChart(item.field,item.value):el('p',{class:'subtle'},status[item.state]||'未知')))));}});
        return detail;
      })),
    decisions:()=>el('div',{},el('div',{class:'thought-section-heading'},el('h3',{},'行为与结果'),el('p',{},'区分模型建议和系统实际选择。')),
      data.behavior_decisions?.length?thoughtBehaviorCharts(data.behavior_decisions):el('p',{},'未记录概率决策；自主探索以模型评估和专用流程为准。'),
      ...data.results.map((item,index)=>el('details',{class:'thought-accordion'},el('summary',{},'结果 '+(index+1)+'：'+(status[item.acceptance]||item.acceptance)),el('div',{class:'thought-accordion-body'},resultBody(item))))),
    calls:()=>el('div',{},el('div',{class:'thought-section-heading'},el('h3',{},'调用记录'),el('p',{},'核对状态、用量和异常。')),
      data.attempts.length?thoughtTable(['尝试','状态','模型','发送','结束','错误'],data.attempts.map(item=>[item.attempt_no,labels[item.state]||item.state,item.model,time(item.sent_at),time(item.finished_at),item.error_code||'无记录'])):el('p',{},'尚未发送调用。'),
      el('h4',{},'模型用量'),data.usage.length?thoughtTable(['耗时','输入 token','输出 token'],data.usage.map(item=>[typeof item.latency_ms==='number'?(item.latency_ms/1000).toFixed(2)+' 秒':'未记录',item.input_tokens??'未记录',item.output_tokens??'未记录'])):el('p',{},'尚无用量记录。'),
      el('details',{class:'thought-diagnostics'},el('summary',{},'排查数据（原始记录）'),technical(data,'展开完整原始记录')))
  };
  const buttons=[];
  for(const [key,title] of [['overview','概览'],['inputs','参考信息'],['decisions','行为与结果'],['calls','调用记录']]){
    const item=button(title,()=>show(key),'quiet',{'aria-controls':'thought-reader-content','aria-pressed':key==='overview'?'true':'false',autofocus:key==='overview'?'':null});buttons.push([key,item]);navigation.append(item);
  }
  function show(key){for(const [name,node] of buttons)node.setAttribute('aria-pressed',String(name===key));content.replaceChildren(views[key]());}
  root.append(el('header',{class:'thought-reader-meta'},badge(data.request.state,labels[data.request.state]||data.request.state),el('span',{},input?.exploration?'自主探索':input?.conversation_context?'对话思考':'任务思考'),el('time',{},time(data.request.recorded_at))),el('div',{class:'thought-reader-layout'},navigation,content));
  show('overview');return root;
}


async function connectAccount(quietAuth=false) {
  const data=await api('/v1/auth/me',undefined,false,quietAuth);state.account=data.account;state.chatId=data.account.thread_id;state.chatDraft='';state.chatKey=null;
  state.connected=true;state.view='chat';$('#refresh').disabled=false;$('#stop').disabled=data.account.role!=='root';$('#disconnect').hidden=false;
  for(const item of document.querySelectorAll('[data-view]'))item.hidden=!['chat','account','memories'].includes(item.dataset.view)&&!(item.dataset.view==='accounts'&&['root','admin'].includes(data.account.role))&&data.account.role!=='root';
  $('#stop').hidden=data.account.role!=='root';await navigate('chat');
}
function rootSetupForm() {
  const password=el('input',{id:'setup-password',type:'password',minlength:12,maxlength:256,autocomplete:'new-password',required:true});
  const confirm=el('input',{id:'setup-password-confirm',type:'password',minlength:12,maxlength:256,autocomplete:'new-password',required:true});
  const submit=el('button',{type:'submit',class:'button'},'设置并进入');
  const form=el('form',{onsubmit:safe(async event=>{event.preventDefault();if(!form.reportValidity())return;if(password.value!==confirm.value)throw new Error('两次密码不一致。');await busy(submit,async()=>{await api('/v1/auth/setup',{new_password:password.value});password.value='';confirm.value='';await connectAccount();});})},
    el('h1',{},'首次设置 root 密码'),el('p',{},'设置后即可使用 root 账户登录当前实例。'),field('密码，至少12个字符',password),field('再次输入密码',confirm),submit);
  return form;
}
function accountLoginForm() {
  const name=el('input',{id:'account-username',value:'root',autocomplete:'username',required:true});
  const password=el('input',{id:'account-password',type:'password',autocomplete:'current-password',required:true});
  const form=el('form',{onsubmit:safe(async e=>{e.preventDefault();if(!form.reportValidity())return;await api('/v1/auth/login',{username:name.value,password:password.value});password.value='';await connectAccount();})},
    el('h2',{},'账户登录'),field('用户名',name),field('密码',password),el('button',{type:'submit',class:'button'},'登录'));
  return form;
}
async function renderAccount() {
  const me=(await api('/v1/auth/me')).account;
  const old=el('input',{type:'password',autocomplete:'current-password',required:!me.bootstrap});
  const pass=el('input',{type:'password',minlength:12,maxlength:256,autocomplete:'new-password',required:true});
  const confirm=el('input',{type:'password',minlength:12,maxlength:256,autocomplete:'new-password',required:true});
  const form=el('form',{onsubmit:safe(async e=>{e.preventDefault();if(!form.reportValidity())return;if(pass.value!==confirm.value)throw new Error('两次密码不一致。');await api('/v1/account/password',{current_password:old.value,new_password:pass.value});old.value='';pass.value='';confirm.value='';disconnect();notify('密码已更新，请重新登录。');})},field('当前密码',old),field('新密码，至少12个字符',pass),field('重复新密码',confirm),el('button',{type:'submit',class:'button'},'更新密码'));
  return el('div',{},heading('我的账户','账户与现实身份、亲属关系分别记录。'),panel('账户资料',pairs([['用户名',me.username],['显示名',me.display_name],['权限',({root:'最高权限',admin:'管理员',member:'普通账户',guest:'访客'})[me.role]||me.role],['固定会话',me.thread_id]])),panel(me.password_configured?'修改密码':'设置密码',form));
}
async function renderAccounts() {
  const data=await api('/v1/accounts');const root=state.account.role==='root';
  const rows=data.items.map(item=>{
    const canManage=root||['member','guest'].includes(item.role);
    const actions=el('div',{class:'account-row-actions'});
    if(canManage&&item.role!=='root'){
      actions.append(button(item.status==='active'?'禁用':'启用',async()=>{if(!await confirmAction(item.status==='active'?'禁用此账户？':'启用此账户？',item.status==='active'?'此账户将无法继续登录，已有登录会失效。':'此账户将恢复登录权限。','确认'))return;await api('/v1/accounts/'+item.id,{expected_revision:item.revision,status:item.status==='active'?'disabled':'active'});await loadView();},'secondary small'));
      const roles=select('role-'+item.id,(root?['admin','member','guest']:['member','guest']).map(r=>[r,({root:'最高权限',admin:'管理员',member:'普通账户',guest:'访客'})[r]||r]),item.role);
      roles.setAttribute('aria-label',item.username+' 的账户类型');
      actions.append(roles,button('保存类型',async()=>{await api('/v1/accounts/'+item.id,{expected_revision:item.revision,role:roles.value});await loadView();},'secondary small'));
      actions.append(button('重置密码',()=>{const password=el('input',{type:'password',minlength:12,maxlength:256,required:true,autocomplete:'new-password'});openDialog('重置 '+item.username+' 的密码',field('新密码',password),[button('保存',async()=>{if(!password.reportValidity())return;await api('/v1/accounts/'+item.id+'/password',{new_password:password.value});password.value='';closeDialog();notify('已重置，该账户旧登录已失效。');})]);},'secondary small'));
    }
    return el('tr',{},el('td',{},item.username),el('td',{},item.display_name),el('td',{},({root:'最高权限',admin:'管理员',member:'普通账户',guest:'访客'})[item.role]||item.role),el('td',{},item.status==='active'?'已启用':item.status==='disabled'?'已禁用':item.status),el('td',{},actions));
  });
  const name=el('input',{required:true,pattern:'[a-z0-9][a-z0-9_.-]{2,31}',autocomplete:'off'}),display=el('input',{required:true,maxlength:80}),role=select('new-account-role',(root?['admin','member','guest']:['member','guest']).map(r=>[r,({root:'最高权限',admin:'管理员',member:'普通账户',guest:'访客'})[r]||r]),'member'),pass=el('input',{type:'password',minlength:12,maxlength:256,required:true,autocomplete:'new-password'});
  const create=el('form',{onsubmit:safe(async e=>{e.preventDefault();if(!create.reportValidity())return;await api('/v1/accounts',{username:name.value,display_name:display.value,role:role.value,password:pass.value});pass.value='';await loadView();notify('账户已创建，已分配唯一固定会话。');})},field('用户名，3—32位小写英文、数字或._-',name),field('显示名',display),field('账户类型',role),field('初始密码，至少12个字符',pass),el('button',{type:'submit',class:'button'},'创建账户'));
  return el('div',{},heading('账户管理','root唯一；管理员共享全部记忆域，普通账户私有域相互隔离。'),panel('账户列表',table(['用户名','显示名','类型','状态','操作'],rows,'账户列表')),panel('创建账户',create));
}
async function renderAccountMemories(before) {
  const data=await api('/v1/account/memories'+(before?'?before='+before:''));const manager=['root','admin'].includes(state.account.role);
  const rows=data.items.map(item=>el('tr',{},el('td',{},item.content),el('td',{},item.domain.domain==='shared'?'共享域':item.domain.domain==='private'?'私有域':item.domain.domain),el('td',{},item.domain.owner_account_id),el('td',{},manager?button(item.domain.domain==='shared'?'撤回共享':'设为共享',async()=>{const domain=item.domain.domain==='shared'?'private':'shared';if(!await confirmAction('修改记忆共享范围？',domain==='shared'?'这条内容将允许所有账户召回，来源约束仍然有效。':'撤回后停止后续召回；已经展示给他人的内容无法收回。','确认'))return;await api('/v1/account/memories/domain',{memory_id:item.id,domain,expected_revision:data.policy_revision});await loadView();},'secondary small'):'只读')));
  const node=el('div',{},heading('记忆域','仅展示当前账户和生命系统都可读取的记忆。'),panel('可读记忆',table(['内容','域','所属账户','共享'],rows,'可读记忆')));
  if(data.next_before)node.append(button('下一页',async()=>$('#content').replaceChildren(await renderAccountMemories(data.next_before))));
  return node;
}

if(typeof window!=='undefined')window.addEventListener('beforeunload',event=>{if(state.modelDirty||state.chatDraft){event.preventDefault();event.returnValue='';}});

// Root-owned instance settings. Every write is explicit and independently versioned.
async function renderInstanceSettings() {
  const data=await api('/v1/instance/settings');
  const lifecycle=await instanceLifecyclePanel();
  const page=el('div',{class:'instance-settings'});
  const current=data.sections.find(s=>s.id===state.settingsGroup)||data.sections[0];
  state.settingsGroup=current.id;
  const navigation=el('div',{class:'settings-navigation','aria-label':'实例配置分组'});
  let lastGroup;
  for(const section of data.sections){
    if(lastGroup!==section.group){navigation.append(el('p',{class:'settings-group-title'},section.group));lastGroup=section.group;}
    navigation.append(button(section.title,async()=>{
      if(state.modelDirty&&!await confirmAction('切换配置分组？','本组未保存的修改将被丢弃。','切换分组'))return;
      state.modelDirty=false;state.settingsGroup=section.id;await loadView();
    },'secondary settings-nav-item',{'aria-pressed':section.id===current.id?'true':'false'}));
  }
  const picker=select('settings-group-picker',data.sections.map(s=>[s.id,s.title]),current.id);
  picker.addEventListener('change',safe(async()=>{
    if(state.modelDirty&&!await confirmAction('切换配置分组？','本组未保存的修改将被丢弃。','切换分组')){picker.value=current.id;return;}
    state.modelDirty=false;state.settingsGroup=picker.value;await loadView();
  }));
  const pickerField=field('配置分组',picker,'选择需要查看或调整的一组设置。','settings-picker');
  const form=el('form',{class:'settings-form',id:'instance-settings-form'});
  const errors=el('div',{class:'notice warning',role:'alert',tabindex:'-1',hidden:true});
  const controls=new Map();const advanced=new Map();
  const fields=el('fieldset',{disabled:!data.can_apply,class:'settings-fields'});
  fields.append(el('legend',{class:'sr-only'},current.title));
  const grid=el('div',{class:'form-grid'});fields.append(grid);
  function markDirty(){state.modelDirty=true;status.textContent='有未保存的修改';}
  function getValue(spec,input){
    if(spec.type==='bool')return input.checked;
    if(spec.type==='multi')return Array.from(input.querySelectorAll('input')).filter(n=>n.checked).map(n=>n.value);
    if(spec.type==='lines')return input.value.split('\n').map(x=>x.trim()).filter(Boolean);
    if(['number','integer'].includes(spec.type))return input.value===''?null:Number(input.value);
    return input.value;
  }
  for(const spec of current.fields){
    const value=current.values[spec.key],id='setting-'+current.id+'-'+spec.key.replace(/[^\w-]/g,'-');let input,node;
    if(spec.type==='bool'){
      input=el('input',{id,type:'checkbox',checked:value===true});
      node=el('label',{class:'settings-toggle',for:id},el('span',{},el('strong',{},spec.label),spec.hint?el('small',{},spec.hint):null),input);
    } else if(spec.type==='multi'){
      input=el('fieldset',{class:'settings-tools'});input.append(el('legend',{},spec.label));
      for(const [key,label] of spec.choices){const check=el('input',{type:'checkbox',value:key,checked:value.includes(key)});input.append(el('label',{class:'check-line'},check,el('span',{},label)));}
      node=input;
    } else {
      if(spec.type==='choice')input=select(id,spec.choices,value);
      else if(['textarea','lines'].includes(spec.type))input=el('textarea',{id,rows:spec.type==='lines'?5:4,value:spec.type==='lines'?value.join('\n'):value,maxlength:spec.max_length||10000});
      else input=el('input',{id,type:['number','integer'].includes(spec.type)?'number':'text',value,min:spec.min,max:spec.max,step:spec.step,maxlength:spec.max_length,required:spec.type!=='text'||spec.key==='name'});
      node=field(spec.label,input,spec.hint||(['number','integer'].includes(spec.type)?'可调范围：'+spec.min+' 至 '+spec.max:null),['textarea','lines'].includes(spec.type)?'span-two':'');
      input.addEventListener('blur',()=>{if(input.checkValidity)input.setAttribute('aria-invalid',input.checkValidity()?'false':'true');});
    }
    controls.set(spec.key,{spec,input});
    if(spec.advanced){
      if(!advanced.has(spec.advanced)){
        const box=el('div',{class:'form-grid'});const detail=el('details',{class:'settings-advanced'},el('summary',{},spec.advanced),box);advanced.set(spec.advanced,box);fields.append(detail);
      }
      advanced.get(spec.advanced).append(node);
    } else grid.append(node);
  }
  if(current.id==='budget'){
    const toggle=controls.get('budget_enabled').input;
    const update=()=>{for(const key of ['tokens','tool_calls','attempts','duration_seconds'])controls.get(key).input.disabled=!data.can_apply||!toggle.checked;};
    toggle.addEventListener('change',update);update();
  }
  const reason=el('textarea',{id:'settings-reason',rows:2,maxlength:2000,required:true,placeholder:'例如：为较长的源码检查预留更多本地预算。'});
  const confirmed=el('input',{id:'settings-confirmed',type:'checkbox',required:true});
  fields.append(el('div',{class:'settings-confirmation'},field('修改原因',reason,'与修改前后值一起记入日志。'),el('label',{class:'check-line'},confirmed,el('span',{},'我确认这是人工配置，已核对修改范围；不是测评或学习效果。'))));
  const status=el('span',{class:'subtle',role:'status'},'当前表单与已保存设置一致');
  const save=el('button',{type:'submit',class:'button',disabled:!data.can_apply},'保存并应用');
  form.append(errors,fields,el('div',{class:'form-actions'},save,button('重新读取',async()=>{
    if(state.modelDirty&&!await confirmAction('重新读取？','未保存的修改将被丢弃。','重新读取'))return;
    state.modelDirty=false;await loadView();
  },'secondary'),status));
  form.addEventListener('input',markDirty);form.addEventListener('change',markDirty);
  form.addEventListener('submit',safe(async event=>{
    event.preventDefault();errors.hidden=true;
    if(!form.reportValidity())return;
    const values=Object.fromEntries([...controls].map(([key,{spec,input}])=>[key,getValue(spec,input)]));
    const changed=current.fields.filter(s=>JSON.stringify(values[s.key])!==JSON.stringify(current.values[s.key]));
    if(!changed.length){notify('本组没有需要保存的修改。');return;}
    const describe=v=>typeof v==='boolean'?(v?'开启':'关闭'):Array.isArray(v)?v.join('、'):String(v);
    const summary=changed.map(s=>s.label+'：'+describe(current.values[s.key])+' → '+describe(values[s.key])).join('\n');
    if(!await confirmAction('保存“'+current.title+'”？',summary+'\n\n将停止实例、保存本组设置并重新启动。已有记忆和历史保留。','保存并应用'))return;
    await busy(save,async()=>{
      try{
        const operation=await api('/v1/instance/settings/'+current.id+'/apply',{values,expected_revision:current.revision,reason:reason.value.trim(),confirmed:confirmed.checked});
        state.modelDirty=false;await watchInstanceOperation(operation,errors);await loadView();
      }catch(error){errors.replaceChildren(el('strong',{},'未保存'),el('p',{},error.message));errors.hidden=false;errors.focus();throw error;}
    });
  }));
  const links=el('div',{class:'settings-related'},data.related_pages.map(item=>button(item.label,()=>navigate(item.view),'secondary small')));
  page.append(heading('实例配置','查看当前设置，按组调整并保留修改记录。'),
    lifecycle,
    pickerField,el('div',{class:'settings-layout'},navigation,el('section',{class:'panel settings-editor'},el('div',{class:'panel-heading'},el('div',{},el('h2',{},current.title),el('p',{class:'subtle'},current.description),el('p',{class:'settings-version'},'版本 '+current.revision.slice(0,10)+' · 保存并应用后重启'))),el('div',{class:'panel-body'},form))),
    el('details',{class:'settings-help'},el('summary',{},'应用说明与其他管理入口'),el('p',{},'保存并应用将停止实例、保存本组设置并启动原部署。已有记忆和历史保留，禁止唤醒锁不会自动解除。'),links,el('p',{class:'settings-boundaries'},'始终保留：'+data.protected_rules.join('；')+'。')));
  return page;
}

async function watchInstanceOperation(operation,target) {
  const terminal=['succeeded','failed','recovered','interrupted','cancelled'];
  target.hidden=false;target.setAttribute('role','status');
  let current=operation;
  while(true){
    target.replaceChildren(el('strong',{},current.message||'正在处理'),current.error?el('p',{},current.error):null,current.recovery_error?el('p',{},current.recovery_error):null);
    if(terminal.includes(current.state))break;
    await new Promise(resolve=>setTimeout(resolve,1000));
    const status=await api('/v1/instance/lifecycle');
    if(!status.operation||status.operation.id!==operation.id){target.append(el('p',{},'操作记录已更新，请重新读取状态。'));return;}
    current=status.operation;
  }
  if(current.state==='succeeded')notify(current.message);
  else if(current.state==='recovered')notify(current.message,true);
  else throw new Error(current.message);
}
async function instanceLifecyclePanel() {
  const data=await api('/v1/instance/lifecycle');
  const running=Boolean(data.control.active_process_run_id);
  const progress=el('div',{class:'notice',role:'status',hidden:!data.operation},data.operation?.message||'');
  const actions=el('div',{class:'form-actions'});
  for(const [action,label] of [['start','启动'],['stop','停止'],['restart','重启']]){
    const control=button(label,async()=>{
      if(state.modelDirty){notify('请先保存配置或重新读取，避免丢失当前修改。',true);return;}
      if(!await confirmAction(label+'实例？',action==='stop'?'实例会等待当前执行返回后停止。面板继续运行。':'使用原有部署启动；不会清空记忆、账户或历史。','确认'+label))return;
      for(const item of actions.querySelectorAll('button'))item.disabled=true;
      try{const operation=await api('/v1/instance/lifecycle/'+action,{confirmed:true});await watchInstanceOperation(operation,progress);await loadView();}
      finally{for(const item of actions.querySelectorAll('button'))item.disabled=false;}
    },action==='stop'?'secondary':'button',{disabled:action==='start'?running:!running});
    actions.append(control);
  }
  if(data.operation&&!['succeeded','failed','recovered','interrupted','cancelled'].includes(data.operation.state)){
    for(const item of actions.querySelectorAll('button'))item.disabled=true;
    watchInstanceOperation(data.operation,progress).then(()=>{if(state.view==='settings'&&!state.modelDirty)loadView();}).catch(error=>{progress.textContent=error.message;});
  }
  return el('section',{class:'lifecycle-bar','aria-label':'实例运行控制'},el('div',{class:'lifecycle-status'},badge(data.wake_disabled?'locked':running?'running':'stopped'),el('span',{},data.wake_disabled?'禁止唤醒锁已启用':running?'实例正在运行':'实例已停止')),actions,progress);
}
