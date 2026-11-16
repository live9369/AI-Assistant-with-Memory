"""Account audience and memory-domain enforcement for the native runtime."""
from contextlib import contextmanager
from functools import wraps
import json
from digital_life.domain.contracts import Forbidden, Conflict
from digital_life.application.accounts.accounts import Accounts,enabled,public


def active(store):
    if not enabled(store.root):return False
    if 'acct_activity_owners' not in store.columns:raise Forbidden('account projection is incomplete')
    from digital_life.application.learning.runtime import qualified_plane_required
    if qualified_plane_required(store):raise Forbidden('protected runtime account adapter is not implemented')
    return True

def principal(store,account=None):
    auth=Accounts(store.root,store.instance_id)
    try:
        row=auth.row(account or auth.root_id())
        if row['status']!='active':raise Forbidden('account is inactive')
        return public(row)
    finally:auth.close()

def current(store):
    return getattr(store,'_account_audience',None)

def privileged(store):
    row=current(store)
    return row is None or row['role'] in ('root','admin')

def effective_reader(store):
    row=current(store)
    return row['id'] if row else store.config()['self_actor']

@contextmanager
def audience(store,account):
    if not active(store):yield;return
    row=principal(store,account);previous=current(store)
    if previous and previous['id']==row['id'] and previous['revision']!=row['revision']:raise Forbidden('account changed while preparing activity')
    store._account_audience=row
    try:yield row
    finally:store._account_audience=previous

def activity_owner(store,activity):
    row=store.db.execute('SELECT account_id,scope_tier FROM acct_activity_owners WHERE activity_id=?',(activity,)).fetchone()
    if row:return row['account_id'],row['scope_tier']
    auth=Accounts(store.root,store.instance_id)
    try:return auth.root_id(),'privileged'
    finally:auth.close()

def visible_activity(store,activity):
    if not active(store) or privileged(store):return True
    row=current(store);owner,tier=activity_owner(store,activity)
    return owner==row['id'] and tier=='scoped'

def own_activity(store,activity):
    if not active(store):return True
    row=current(store)
    return row is not None and activity_owner(store,activity)[0]==row['id']

def activity_scope(method):
    @wraps(method)
    def wrapped(self,activity,*args,**kwargs):
        if not active(self.s):return method(self,activity,*args,**kwargs)
        owner,_=activity_owner(self.s,activity)
        with audience(self.s,owner):
            assert_features(self.s,activity)
            return method(self,activity,*args,**kwargs)
    return wrapped

def assert_features(store,activity):
    if privileged(store):return
    # These global learning projections are not silently exposed to scoped users.
    from digital_life.application.behavior.personality_growth import PersonalityGrowth
    from digital_life.application.behavior.habit_learning import HabitLearning
    from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
    from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
    from digital_life.application.memory.memory_quality import MemoryQuality
    from digital_life.application.autonomy.task_loop import TaskLoop
    from digital_life.application.autonomy.exploration import Exploration
    if any(module(store).config()['enabled'] for module in (PersonalityGrowth,HabitLearning,AutonomyAgenda,SelfMaintenance,MemoryQuality)) or TaskLoop(store).config(activity) or Exploration(store).binding(activity):
        raise Forbidden('this global learning context has no scoped account adapter')

def bind_activity(store,activity,actor=None):
    if not active(store):return
    row=current(store) or principal(store)
    if actor is not None and actor!=row['id']:raise Forbidden('account actor mismatch')
    tier='privileged' if row['role'] in ('root','admin') else 'scoped'
    store.db.execute('INSERT INTO acct_activity_owners(activity_id,account_id,scope_tier) VALUES(?,?,?)',(activity,row['id'],tier))

def add_turn(store,activity):
    if not active(store):return
    owner,_=activity_owner(store,activity)
    store.db.execute('INSERT OR IGNORE INTO acct_conversation_turns(account_id,activity_id) VALUES(?,?)',(owner,activity))

def source_owner(store,ref):
    row=store.db.execute('SELECT account_id,scope_tier FROM acct_object_owners WHERE object_id=?',(ref,)).fetchone()
    if row:return row['account_id'],row['scope_tier']
    if store.db.execute('SELECT id FROM activities WHERE id=? AND instance_id=?',(ref,store.instance_id)).fetchone():return activity_owner(store,ref)
    row=store.db.execute('SELECT a.id FROM activities a WHERE a.instance_id=? AND a.trigger_event_id=?',(store.instance_id,ref)).fetchone()
    if row:return activity_owner(store,row[0])
    row=store.db.execute('SELECT source_actor_id FROM perception_signals WHERE id=? AND instance_id=?',(ref,store.instance_id)).fetchone()
    if row:
        auth=Accounts(store.root,store.instance_id)
        try:
            account=auth.db.execute('SELECT id,role FROM accounts WHERE id=?',(row[0],)).fetchone()
            if account:return account['id'],'privileged' if account['role'] in ('root','admin') else 'scoped'
        finally:auth.close()
    row=store.db.execute('SELECT q.activity_id FROM thought_results r JOIN thought_requests q ON q.id=r.request_id AND q.instance_id=r.instance_id WHERE r.id=? AND r.instance_id=?',(ref,store.instance_id)).fetchone()
    if row:return activity_owner(store,row[0])
    row=store.db.execute('SELECT activity_id FROM runtime_events WHERE id=? AND instance_id=?',(ref,store.instance_id)).fetchone()
    if row and row[0]:return activity_owner(store,row[0])
    auth=Accounts(store.root,store.instance_id)
    try:return auth.root_id(),'privileged'
    finally:auth.close()

def source_allowed(store,ref):
    if not active(store) or privileged(store):return True
    memory=store.db.execute('SELECT memory_id FROM memory_revisions WHERE instance_id=? AND id=?',(store.instance_id,ref)).fetchone()
    if memory:return can_recall(store,memory[0])
    row=current(store)
    if row['role']=='guest':return False
    owner,tier=source_owner(store,ref)
    return tier=='scoped' and owner==row['id']

def memory_domain(store,memory):
    row=store.db.execute('SELECT domain,owner_account_id,scope_tier FROM acct_memory_domains WHERE memory_id=?',(memory,)).fetchone()
    if row:return dict(row)
    auth=Accounts(store.root,store.instance_id)
    try:return {'domain':'private','owner_account_id':auth.root_id(),'scope_tier':'privileged'}
    finally:auth.close()

def memory_readers(store,memory,base,explicit=False):
    if not active(store):return base
    domain=memory_domain(store,memory);auth=Accounts(store.root,store.instance_id)
    try:rows=auth.db.execute("SELECT id,role FROM accounts WHERE status='active'").fetchall()
    finally:auth.close()
    admins={r['id'] for r in rows if r['role'] in ('root','admin')}
    all_ids={r['id'] for r in rows};life=store.config()['self_actor']
    allowed=set(admins)|{life}
    if domain['domain']=='shared':allowed|=all_ids
    elif domain['scope_tier']=='scoped':allowed|={r['id'] for r in rows if r['role']=='member' and r['id']==domain['owner_account_id']}
    # Explicit source withdrawal from the life remains effective even for root.
    policy_base=(set(base)|admins) if explicit else (all_ids|{life})
    return allowed & policy_base

def can_recall(store,memory,actor=None):
    from digital_life.application.services.memory import Memory
    readers=Memory(store).readers(memory)
    return (actor or effective_reader(store)) in readers and store.config()['self_actor'] in readers

def tag_memory(store,memory,evidence):
    if not active(store):return
    row=store.row('evidence_items',evidence);ref=row['origin_object_id'] or row['artifact_id']
    if ref:owner,tier=source_owner(store,ref)
    else:
        account=current(store) or principal(store);owner=account['id'];tier='privileged' if account['role'] in ('root','admin') else 'scoped'
    store.db.execute("INSERT INTO acct_memory_domains VALUES(?,'private',?,?)",(memory,owner,tier))

def tag_object(store,ref,activity):
    if not active(store):return
    owner,tier=activity_owner(store,activity)
    store.db.execute('INSERT OR REPLACE INTO acct_object_owners VALUES(?,?,?,?)',(ref,owner,tier,activity))

def packet_stamp(store):
    account=current(store) or principal(store)
    return {'id':account['id'],'username':account['username'],'display_name':account['display_name'],'role':account['role'],'revision':account['revision'],'memory_policy_revision':store.db.execute('SELECT revision FROM acct_policy_state WHERE id=1').fetchone()[0],'identity_scope':'local authenticated account, not real-world identity or kinship'}

def prepare_payload(store,payload):
    if not active(store):return
    payload['account_context']=packet_stamp(store)
    from digital_life.application.accounts.cognitive_influence import prepare
    prepare(store,payload)
    if not privileged(store):
        # Individual measurements from another account are not global public traits.
        selected={}
        for name,value in payload.get('states',{}).items():
            if name.startswith(('R.','W.','F.')):selected[name]=value
            elif ':' in name and source_allowed(store,name.split(':',1)[1]):selected[name]=value
        payload['states']=selected
        payload['state_domain_scope']='global substrate plus authorized individual measurements; unobserved groups remain unknown'
    if current(store)['role']!='root':payload['instructions']+=' 此账户仅可交流，action只能wait或ask；账户权限由系统决定，不能执行文件、命令或其他工具。'
    payload['instructions']+=' account_context是当前发言者的认证账户资料，不代表现实身份或亲属关系；记忆域仅允许使用本次提供的可读信息，不推测其他账户私有内容。'

def check_payload(store,payload):
    if not active(store):return
    from digital_life.application.accounts.cognitive_influence import check
    check(store,payload)
    expected=payload.get('account_context')
    if not expected or packet_stamp(store)!=expected:raise Forbidden('account or memory-domain authorization changed')
    account=principal(store,expected['id'])
    if account['revision']!=expected['revision'] or account['role']!=expected['role']:raise Forbidden('account authorization superseded')
    for memory in payload.get('selected_memories',[]):
        row=store.row('memory_revisions',memory['revision_id'])
        if not can_recall(store,row['memory_id']):raise Forbidden('account memory source revoked')
    from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
    for belief in payload.get('cognition_snapshot',[]):
        for ref in [belief['current_revision_id']]+[r['id'] for r in belief.get('candidates',[])]:
            if not CognitiveUpdates(store).readable_revision(ref):raise Forbidden('account cognition source revoked')

def check_output(store,output):
    if active(store) and current(store)['role']!='root' and output['action']['tool'] not in ('wait','ask'):raise Forbidden('only root may request system actions')
