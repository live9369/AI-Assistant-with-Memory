"""Provider-independent structured action output contract."""
from digital_life.domain.contracts import validate_action,ContractError,probability,text

SCHEMA={'type':'object','additionalProperties':False,'required':['schema_version','action','explanation'],
 'properties':{'schema_version':{'type':'integer','const':1},'explanation':{'type':'string'},
 'action':{'type':'object','additionalProperties':False,'required':['tool','arguments'],
 'properties':{'tool':{'enum':['write_note','read_file','list_files','wait','ask']},'arguments':{'type':'object'}}}}}

def action_schema(tool,properties,required):
    return {'type':'object','additionalProperties':False,'required':['tool','arguments'],'properties':{
      'tool':{'type':'string','const':tool},'arguments':{'type':'object','additionalProperties':False,'properties':properties,'required':required}}}
SCHEMA['properties']['action']={'anyOf':[
    action_schema('write_note',{'path':{'type':'string'},'text':{'type':'string'}},['path','text']),
    action_schema('read_file',{'path':{'type':'string'}},['path']),
    action_schema('list_files',{'path':{'type':'string'}},[]),
    action_schema('wait',{'reason':{'type':'string'}},['reason']),
    action_schema('ask',{'reason':{'type':'string'}},['reason'])]}

def validate_legacy(value):
    if not isinstance(value,dict) or set(value)!={'schema_version','action','explanation'} or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise ContractError('invalid inference result')
    if not isinstance(value['explanation'],str) or len(value['explanation'])>16000: raise ContractError('invalid explanation')
    validate_action(value['action']); return value


from digital_life.domain.project_files import PROPERTIES as PROJECT_PROPERTIES
for _name,_properties in PROJECT_PROPERTIES.items():
    SCHEMA['properties']['action']['anyOf'].append(action_schema(_name,_properties,list(_properties)))

# V2 is selected only for exploration requests. Legacy task contracts remain V1.
import copy
EXPLORATION_SCHEMA=copy.deepcopy(SCHEMA)
EXPLORATION_SCHEMA['properties']['schema_version']['const']=2
candidate={'type':'object','additionalProperties':False,
 'properties':{'question':{'type':'string'},'verification':{'type':'string'},
 'expected_gain':{'type':'number','minimum':0,'maximum':1},
 'cost':{'type':'number','minimum':0,'maximum':1},
 'evidence_refs':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':4}},
 'required':['question','verification','expected_gain','cost','evidence_refs']}
EXPLORATION_SCHEMA['properties']['exploration']={'type':'object','additionalProperties':False,
 'properties':{'candidates':{'type':'array','items':candidate,'maxItems':4},
 'disposition':{'type':'string','enum':['continue','resolved','dormant']},
 'assessment':{'type':'string'},'evidence_refs':{'type':'array','items':{'type':'string'},'maxItems':8}},
 'required':['candidates','disposition','assessment','evidence_refs']}
EXPLORATION_SCHEMA['required'].append('exploration')

def schema_for(request):
    return EXPLORATION_SCHEMA if request.get('output_schema_version')==2 else SCHEMA

def validate(value):
    if not isinstance(value,dict) or type(value.get('schema_version')) is not int: raise ContractError('invalid output version')
    if value['schema_version']==1: return validate_legacy(value)
    if value['schema_version']!=2 or set(value)!={'schema_version','action','explanation','exploration'}: raise ContractError('invalid exploration result')
    validate_legacy(dict(schema_version=1,action=value['action'],explanation=value['explanation']))
    e=value['exploration']
    if not isinstance(e,dict) or set(e)!={'candidates','disposition','assessment','evidence_refs'}: raise ContractError('invalid exploration fields')
    if e['disposition'] not in ('continue','resolved','dormant'): raise ContractError('invalid exploration disposition')
    text(e['assessment'],2000)
    def refs(items,minimum=0,maximum=8):
        if not isinstance(items,list) or not minimum<=len(items)<=maximum: raise ContractError('invalid evidence list')
        for item in items: text(item,128)
        if len(set(items))!=len(items): raise ContractError('duplicate evidence reference')
    refs(e['evidence_refs'])
    if not isinstance(e['candidates'],list) or len(e['candidates'])>4: raise ContractError('too many questions')
    for c in e['candidates']:
        if not isinstance(c,dict) or set(c)!={'question','verification','expected_gain','cost','evidence_refs'}: raise ContractError('invalid candidate')
        text(c['question'],1000); text(c['verification'],1000)
        probability(c['expected_gain']); probability(c['cost']); refs(c['evidence_refs'],1,4)
    return value

# V3 is explicitly selected for evidence-linked cognition; V1/V2 remain unchanged.
COGNITION_SCHEMA=copy.deepcopy(SCHEMA)
COGNITION_SCHEMA['properties']['schema_version']['const']=3
_claim={'type':'object','additionalProperties':False,'required':['subject','predicate','value','source_ref','quote','kind'],'properties':{
 'subject':{'type':'string'},'predicate':{'type':'string'},'value':{'type':'string'},'source_ref':{'type':'string'},'quote':{'type':'string'},'kind':{'enum':['reported','hypothesis']}}}
_prediction={'type':'object','additionalProperties':False,'required':['outcome','probability','due_seconds'],'properties':{'outcome':{'type':'string'},'probability':{'type':'number','minimum':0,'maximum':1},'due_seconds':{'type':'integer','minimum':1,'maximum':86400}}}
_plan={'type':'object','additionalProperties':False,'required':['action','expected','depends_on'],'properties':{'action':copy.deepcopy(SCHEMA['properties']['action']),'expected':{'type':'string'},'depends_on':{'type':'array','items':{'type':'integer','minimum':0}}}}
COGNITION_SCHEMA['properties']['cognition']={'type':'object','additionalProperties':False,'required':['claims','questions','predictions','plan'],'properties':{'claims':{'type':'array','maxItems':8,'items':_claim},'questions':{'type':'array','maxItems':8,'items':{'type':'string'}},'predictions':{'type':'array','maxItems':4,'items':_prediction},'plan':{'type':'array','maxItems':8,'items':_plan}}}
COGNITION_SCHEMA['required'].append('cognition')
_previous_schema_for=schema_for
_previous_validate=validate

def schema_for(request):
    return COGNITION_SCHEMA if request.get('output_schema_version')==3 else _previous_schema_for(request)

def validate(value):
    if not isinstance(value,dict) or value.get('schema_version')!=3:return _previous_validate(value)
    if type(value['schema_version']) is not int or set(value)!={'schema_version','action','explanation','cognition'}:raise ContractError('invalid cognition output')
    validate_legacy(dict(schema_version=1,action=value['action'],explanation=value['explanation']))
    c=value['cognition']
    if not isinstance(c,dict) or set(c)!={'claims','questions','predictions','plan'}:raise ContractError('invalid cognition fields')
    for name,maximum in [('claims',8),('questions',8),('predictions',4),('plan',8)]:
        if not isinstance(c[name],list) or len(c[name])>maximum:raise ContractError('cognition list limit')
    for claim in c['claims']:
        if not isinstance(claim,dict) or set(claim)!={'subject','predicate','value','source_ref','quote','kind'} or claim['kind'] not in ('reported','hypothesis'):raise ContractError('invalid cognition claim')
        for key in ('subject','predicate','value','source_ref','quote'):text(claim[key],2000 if key in ('value','quote') else 240)
    for question in c['questions']:text(question,2000)
    for prediction in c['predictions']:
        if not isinstance(prediction,dict) or set(prediction)!={'outcome','probability','due_seconds'}:raise ContractError('invalid cognition prediction')
        text(prediction['outcome'],2000);probability(prediction['probability'])
        if type(prediction['due_seconds']) is not int or not 1<=prediction['due_seconds']<=86400:raise ContractError('invalid prediction deadline')
    for i,step in enumerate(c['plan']):
        if not isinstance(step,dict) or set(step)!={'action','expected','depends_on'}:raise ContractError('invalid cognition plan')
        validate_action(step['action']);text(step['expected'],2000)
        if not isinstance(step['depends_on'],list) or any(type(x) is not int or not 0<=x<i for x in step['depends_on']):raise ContractError('invalid plan dependency')
    return value

# V4: persistent self-directed directions, separate from legacy file exploration.
REFLECTION_SCHEMA=copy.deepcopy(SCHEMA)
REFLECTION_SCHEMA['properties']['schema_version']['const']=4
_direction={'type':'object','additionalProperties':False,'properties':{
 'title':{'type':'string'},'kind':{'enum':['reflect','explore','create','relate','maintain']},
 'next_step':{'type':'string'},'expected_gain':{'type':'number','minimum':0,'maximum':1},
 'cost':{'type':'number','minimum':0,'maximum':1},'evidence_refs':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':8}}}
_direction['required']=list(_direction['properties'])
REFLECTION_SCHEMA['properties']['reflection']={'type':'object','additionalProperties':False,'properties':{
 'directions':{'type':'array','items':_direction,'maxItems':4},
 'decision':{'enum':['continue','branch','switch','pause','finish']},
 'understanding':{'type':'string'},'next_step':{'type':'string'},'reason':{'type':'string'},
 'reopen_condition':{'type':'string'},'evidence_refs':{'type':'array','items':{'type':'string'},'maxItems':8}}}
REFLECTION_SCHEMA['properties']['reflection']['required']=list(REFLECTION_SCHEMA['properties']['reflection']['properties'])
REFLECTION_SCHEMA['required'].append('reflection')
_v3_schema_for=schema_for
_v3_validate=validate
def schema_for(request):
    return REFLECTION_SCHEMA if request.get('output_schema_version')==4 else _v3_schema_for(request)
def validate(value):
    if not isinstance(value,dict) or value.get('schema_version')!=4:return _v3_validate(value)
    if type(value['schema_version']) is not int or set(value)!={'schema_version','action','explanation','reflection'}:raise ContractError('invalid reflection output')
    validate_legacy(dict(schema_version=1,action=value['action'],explanation=value['explanation']))
    r=value['reflection'];fields=REFLECTION_SCHEMA['properties']['reflection']['properties']
    if not isinstance(r,dict) or set(r)!=set(fields):raise ContractError('invalid reflection fields')
    if r['decision'] not in fields['decision']['enum']:raise ContractError('invalid reflection decision')
    for key in ('understanding','next_step','reason','reopen_condition'):
        if not isinstance(r[key],str) or len(r[key])>2000:raise ContractError('invalid reflection text')
    def refs(v,minimum=0):
        if not isinstance(v,list) or not minimum<=len(v)<=8 or any(not isinstance(x,str) or not x or len(x)>128 for x in v) or len(set(v))!=len(v):raise ContractError('invalid reflection sources')
    refs(r['evidence_refs'])
    if not isinstance(r['directions'],list) or len(r['directions'])>4:raise ContractError('too many directions')
    for d in r['directions']:
        if not isinstance(d,dict) or set(d)!=set(_direction['properties']) or d['kind'] not in _direction['properties']['kind']['enum']:raise ContractError('invalid direction')
        text(d['title'],1000);text(d['next_step'],1000);probability(d['expected_gain']);probability(d['cost']);refs(d['evidence_refs'],1)
    return value

# V5 separates a completed step from the lifecycle of its parent inquiry.
INQUIRY_SCHEMA=copy.deepcopy(REFLECTION_SCHEMA)
INQUIRY_SCHEMA['properties']['schema_version']['const']=5
_inquiry={'type':'object','additionalProperties':False,'properties':{
 'prediction':{'type':'string'},'observation':{'type':'string'},'revision':{'type':'string'},
 'remaining_questions':{'type':'array','items':{'type':'string'},'maxItems':4},
 'next_attempts':{'type':'array','items':{'type':'string'},'maxItems':4},
 'direction_status':{'enum':['ready','paused','finished']},
 'finish_basis':{'enum':['not_finished','goal_achieved','no_valuable_next_step','blocked']}}}
_inquiry['required']=list(_inquiry['properties'])
INQUIRY_SCHEMA['properties']['inquiry']=_inquiry
INQUIRY_SCHEMA['required'].append('inquiry')
_v4_schema_for=schema_for
_v4_validate=validate
def schema_for(request):
    if request.get('output_schema_version')!=5:return _v4_schema_for(request)
    schema=copy.deepcopy(INQUIRY_SCHEMA)
    context=request.get('exploration',{})
    if context.get('mode')=='continuous':
        allowed=list(dict.fromkeys(context.get('allowed_evidence_refs',[])))
        fields=schema['properties']['reflection']['properties']
        if allowed:
            fields['evidence_refs']['items']={'type':'string','enum':allowed}
            fields['directions']['items']['properties']['evidence_refs']['items']={'type':'string','enum':allowed}
        else:
            fields['evidence_refs']['maxItems']=0
            fields['directions']['maxItems']=0
    return schema
def validate(value):
    if not isinstance(value,dict) or value.get('schema_version')!=5:return _v4_validate(value)
    if type(value['schema_version']) is not int or set(value)!={'schema_version','action','explanation','reflection','inquiry'}:raise ContractError('invalid inquiry result')
    _v4_validate({k:(4 if k=='schema_version' else v) for k,v in value.items() if k!='inquiry'})
    q=value['inquiry']
    if not isinstance(q,dict) or set(q)!=set(_inquiry['properties']):raise ContractError('invalid inquiry fields')
    for k in ('prediction','observation','revision'):
        if not isinstance(q[k],str) or len(q[k])>2000:raise ContractError('invalid inquiry text')
    for k in ('remaining_questions','next_attempts'):
        if not isinstance(q[k],list) or len(q[k])>4:raise ContractError('invalid inquiry list')
        for item in q[k]:text(item,1000)
    for k in ('direction_status','finish_basis'):
        if q[k] not in _inquiry['properties'][k]['enum']:raise ContractError('invalid inquiry state')
    if q['direction_status']=='finished' and q['finish_basis'] not in ('goal_achieved','no_valuable_next_step'):raise ContractError('direction finish needs basis')
    return value

# V6: bounded learning proposals; M03 remains the sole acceptance owner.
_v5_schema_for=schema_for
_v5_validate=validate
LEARNING_SCHEMA=copy.deepcopy(INQUIRY_SCHEMA)
LEARNING_SCHEMA['properties']['schema_version']['const']=6
_learning_claim={'type':'object','additionalProperties':False,'properties':{
 'subject':{'type':'string'},'predicate':{'type':'string'},'value':{'type':'string'},
 'kind':{'enum':['reported','hypothesis','method']},'source_ref':{'type':'string'},'quote':{'type':'string'},
 'valid_at':{'type':'string'},'context_contains':{'type':'string'}}}
_learning_claim['required']=list(_learning_claim['properties'])
LEARNING_SCHEMA['properties']['learning']={'type':'object','additionalProperties':False,'required':['claims'],'properties':{'claims':{'type':'array','maxItems':4,'items':_learning_claim}}}
LEARNING_SCHEMA['required'].append('learning')

def schema_for(request):
    if request.get('output_schema_version')!=6:return _v5_schema_for(request)
    schema=_v5_schema_for(dict(request,output_schema_version=5))
    schema['properties']['schema_version']['const']=6
    schema['properties']['learning']=copy.deepcopy(LEARNING_SCHEMA['properties']['learning']);schema['required'].append('learning')
    sources=list(request.get('learning_sources',{}))
    if sources:schema['properties']['learning']['properties']['claims']['items']['properties']['source_ref']={'type':'string','enum':sources}
    else:schema['properties']['learning']['properties']['claims']['maxItems']=0
    return schema

def validate(value):
    if not isinstance(value,dict) or value.get('schema_version')!=6:return _v5_validate(value)
    if type(value['schema_version']) is not int or set(value)!=set(LEARNING_SCHEMA['properties']):raise ContractError('invalid learning output')
    _v5_validate({k:(5 if k=='schema_version' else v) for k,v in value.items() if k!='learning'})
    learning=value['learning']
    if not isinstance(learning,dict) or set(learning)!={'claims'} or not isinstance(learning['claims'],list) or len(learning['claims'])>4:raise ContractError('invalid learning claims')
    for c in learning['claims']:
        if not isinstance(c,dict) or set(c)!=set(_learning_claim['properties']) or c['kind'] not in ('reported','hypothesis','method'):raise ContractError('invalid learning claim')
        for key in ('subject','predicate','source_ref'):text(c[key],240)
        for key in ('value','quote'):text(c[key],2000)
        for key,limit in [('valid_at',64),('context_contains',240)]:
            if not isinstance(c[key],str) or len(c[key])>limit:raise ContractError('invalid learning scope')
        if c['valid_at']:
            from datetime import datetime
            try:datetime.fromisoformat(c['valid_at'].replace('Z','+00:00'))
            except ValueError:raise ContractError('invalid learning effective time') from None
        if c['kind']=='method':text(c['context_contains'],240)
    return value

# Advertise project actions only in an explicitly authorized project packet.
_project_base_schema_for=schema_for
def schema_for(request):
    schema=copy.deepcopy(_project_base_schema_for(request))
    allowed=set(request.get('project_access',{}).get('tools',[]))
    def restrict(node):
        if isinstance(node,dict):
            if 'anyOf' in node:
                node['anyOf']=[variant for variant in node['anyOf'] if (variant.get('properties',{}).get('tool',{}).get('const') not in PROJECT_PROPERTIES or variant['properties']['tool']['const'] in allowed)]
            for value in node.values():restrict(value)
        elif isinstance(node,list):
            for value in node:restrict(value)
    restrict(schema)
    acceptance=request.get('deployment_acceptance')
    if acceptance:
        nonce=acceptance['nonce']
        schema['properties']['action']={'anyOf':[action_schema('wait',{'reason':{'type':'string','enum':['deployment-acceptance:'+nonce]}},['reason'])]}
        schema['properties']['explanation']={'type':'string','enum':['DEPLOYMENT_OK:'+nonce]}
        for group in ('cognition','learning'):
            for key,value in schema['properties'].get(group,{}).get('properties',{}).items():
                if value.get('type')=='array':value['maxItems']=0
    return schema
