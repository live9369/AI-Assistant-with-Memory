"""Authenticated local M12 maintenance composition; never runs on import.

A controller explicitly authorizes one immutable plan under an already
configured finite policy. Bearer identity does not by itself grant source
ownership or arbitrary module/physical access. Unknown owners fail closed.
"""
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib
from pathlib import Path
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.application.learning.runtime import authenticate_controller
from digital_life.application.learning.propagation import (PropagationAuthority,ManagedErasure,ManagedInventory,LocalOwnerActions,DOMAINS,_attested,_control_row)
from digital_life.application.learning.eligibility import ref,slot
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant,ToolLearningStore,has_registered_revision
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate


class ControllerMaintenanceAuthority(PropagationAuthority):
    """Real credential, current policy/control, immutable grant, local adapters.

    Entries are random private in-memory handles. A JSON module label, grant
    Ref or invented handle cannot manufacture an authenticated owner channel.
    This adapter supports owned memory/signal roots and explicit local targets;
    it does not claim automatic semantic/scientific re-evaluation in all domains.
    """
    def __init__(self,store,exclusion_root,clock=utc):
        self.s=store;self.clock=clock;self.exclusion_root=Path(exclusion_root).resolve();self.entries={};self.storage=ToolLearningStore(store)
        if self.exclusion_root==store.root or store.root in self.exclusion_root.parents:raise Forbidden('maintenance exclusion root must be outside runtime image')

    def _controller(self,bearer):
        actor=authenticate_controller(self.s,bearer)
        if self.s.row('identity_instances',self.s.instance_id)['controller_ref']!=actor:raise Forbidden('not this instance controller')
        return actor

    def _current(self):
        policy=self.s.db.execute('SELECT * FROM policy_epochs WHERE instance_id=?',(self.s.instance_id,)).fetchone()
        if policy is None:raise Forbidden('actual active policy missing')
        version=self.s.row('policy_versions',policy['policy_version_id'])
        control=_control_row(self.s,'SELECT * FROM instance_control_state WHERE instance_ref=?',(self.s.instance_id,))
        if control is None or not control['user_stopped'] or control['active_process_run_id'] is not None:raise Forbidden('M12 maintenance requires stopped instance and no managed process')
        if _control_row(self.s,'SELECT id FROM process_runs WHERE instance_ref=? AND exited_at IS NULL LIMIT 1',(self.s.instance_id,)) is not None:raise Forbidden('unreconciled managed process prevents physical maintenance')
        return dict(policy),version,dict(control)

    def configure(self,bearer,limits):
        """Explicit controller policy authoring, not an inferred default grant."""
        actor=self._controller(bearer);t.obj(limits,('scan','items','bytes','elapsed_ms','attempts'))
        for value in limits.values():t.integer(value,1,2**53-1)
        if limits['attempts']!=1:raise ContractError('local maintenance policy has one finite attempt cap and no model/tool authority')
        with dispatch_gate(self.s.root),self.s.tx():
            active,previous,control=self._current()
            if previous['authority']!=actor:raise Forbidden('controller does not own current policy')
            scope=c.loads(previous['scope']);scope['tool_learning_maintenance_limits']=deepcopy(limits)
            number=self.s.db.execute('SELECT max(version)+1 FROM policy_versions WHERE instance_id=?',(self.s.instance_id,)).fetchone()[0]
            key=self.s.insert('policy_versions',version=number,mode=previous['mode'],scope=scope,effective_at=self.clock(),authority=actor)
            changed=self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1,updated_at=? WHERE instance_id=? AND id=? AND epoch=?',(key,self.clock(),self.s.instance_id,active['id'],active['epoch'])).rowcount
            if changed!=1:raise Conflict('maintenance policy CAS changed')
            self.s.event('maintenance.policy_configured',payload={'policy_id':key,'limits':limits,'controller_id':actor},source='tl.maintenance.control',lane='control')
            self._register_root(actor)
            return ref(self.s,key,'policy_versions')

    def configure_restore_candidate(self,bearer,source_bundle,target):
        """Explicit whole-instance LOCKED-candidate policy, not a plan grant."""
        actor=self._controller(bearer);source=Path(source_bundle).absolute();target=Path(target).absolute()
        if source.is_symlink() or source.resolve()!=source or not source.is_dir() or target.exists() or target.is_symlink() or target.parent.resolve()!=target.parent or self.s.root==target or self.s.root in target.parents:raise Forbidden('restore policy requires canonical managed source and new independent target')
        with dispatch_gate(self.s.root),self.s.tx():
            active,previous,control=self._current()
            if previous['authority']!=actor:raise Forbidden('controller does not own current restore policy')
            scope=c.loads(previous['scope'])
            scope['tool_learning_restore_candidate']={'contract':'TL-RESTORE-CANDIDATE-POLICY-1','purpose':'restore_locked_candidate','instance_id':self.s.instance_id,'source_bundle':str(source),'target':str(target),'scope':'whole_current_database_and_registered_artifacts','retain_control_metadata':True,'external_material_use':False,'wake_authorized':False}
            number=self.s.db.execute('SELECT max(version)+1 FROM policy_versions WHERE instance_id=?',(self.s.instance_id,)).fetchone()[0]
            key=self.s.insert('policy_versions',version=number,mode=previous['mode'],scope=scope,effective_at=self.clock(),authority=actor)
            changed=self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1,updated_at=? WHERE instance_id=? AND id=? AND epoch=?',(key,self.clock(),self.s.instance_id,active['id'],active['epoch'])).rowcount
            if changed!=1:raise Conflict('restore policy changed')
            self.s.event('maintenance.restore_policy_configured',payload={'policy_id':key,'controller_id':actor,'source_bundle':str(source),'target':str(target),'wake_authorized':False},source='tl.maintenance.restore_policy',lane='control')
            return ref(self.s,key,'policy_versions')

    def _source_owner(self,plan,actor):
        barrier=self.s.row('tl_barrier',plan['barrier_id']);change=self.s.row('tl_change',barrier['change_id']);payload=self.storage.read_artifact(change['payload_artifact_id'])
        if barrier['kind']!='erase' or payload['erase_scope']['status']!='known' or payload['erase_scope']['value']['id']!=plan['scope_id'] or barrier['source_epoch']!=plan['source_epoch']:raise Forbidden('plan differs from actual protective erase scope/reason')
        scope=self.s.row('policy_versions',plan['scope_id'])
        if scope['authority']!=actor:raise Forbidden('controller is not the actual erase-scope policy owner')
        self._owned_source(payload['source']['object'],plan['scope_id'],actor)
        return payload['source']

    def _owned_source(self,source,scope_id,actor):
        policy=self.s.row('policy_versions',scope_id)
        if policy['authority']!=actor:raise Forbidden('not the actual erase-scope policy owner')
        kind=source['kind'];row=self.s.row(kind,source['id'])
        if kind in ('memory_items','memory_revisions'):
            from digital_life.application.services import Memory
            item=row if kind=='memory_items' else self.s.row('memory_items',row['memory_id'])
            owner=self.s.row('policy_versions',item['access_policy_ref'])
            if owner['authority']!=actor or actor not in Memory(self.s).readers(item['id']):raise Forbidden('current actual memory owner/ACL does not authorize this controller')
        elif kind=='perception_signals':
            if row['source_actor_id'] not in (actor,self.s.config()['self_actor']):raise Forbidden('foreign source author needs its own authority')
        else:raise Forbidden('actual source-owner maintenance adapter is unavailable')
        return None

    def _fixed_source_materials(self,source,work_id):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        graph=ToolLearningInvalidation(self.s,max_nodes=4096,max_rows=65536)
        nodes,truncated=graph._closure(source,'erase')
        if truncated:raise Forbidden('fixed source ownership closure incomplete')
        allowed={x[0] for x in nodes}|{x[1] for x in nodes if x[1] is not None};work=self.s.row('tl_work',work_id)
        if source['object']['kind']=='perception_signals' and self.s.row('activities',work['source_activity_id'])['trigger_event_id']==source['object']['id']:
            allowed.add(work_id)
        for key in list(allowed):
            identity=self.s.row('object_registry',key);kind=identity['kind']
            if kind not in self.s.columns:raise Forbidden('source material owner adapter unavailable')
            row=self.s.db.execute('SELECT * FROM '+kind+' WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone()
            if row is None:continue
            for column in row.keys():
                if row[column] is not None and (column.endswith('_artifact_id') or column.endswith('_artifact_ref') or column in ('artifact_id','artifact_ref')):
                    if self.s.db.execute('SELECT 1 FROM artifacts WHERE instance_id=? AND id=?',(self.s.instance_id,row[column])).fetchone():allowed.add(row[column])
        return allowed

    def _actual_f1_provenance(self,barrier_id):
        from digital_life.infrastructure.persistence.tool_learning_store import command_fingerprint
        barrier=self.s.row('tl_barrier',barrier_id);change=self.s.row('tl_change',barrier['change_id']);payload=self.storage.read_artifact(change['payload_artifact_id'])
        prepared=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.maintenance.F1.prepared' AND source_event_id=?",(self.s.instance_id,change['id'])).fetchone()
        if prepared is None:raise Forbidden('actual authenticated protective F1 provenance is unavailable; no retroactive recognition')
        value=self.storage.read_artifact(prepared['payload_artifact_id']);request=value['request']
        if prepared['payload_hash']!=c.fingerprint(value) or value['contract']!='TL-PROTECTIVE-F1-PREPARATION-1' or request['payload']!=payload:raise Conflict('protective preparation/change payload mapping differs')
        authorization=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.maintenance.F1' AND source_event_id=?",(self.s.instance_id,request['idempotency_key'])).fetchone()
        if authorization is None:raise Forbidden('actual F1 controller authorization missing')
        auth=self.storage.read_artifact(authorization['payload_artifact_id'])
        if authorization['payload_hash']!=c.fingerprint(auth) or auth['contract']!='TL-CONTROLLER-F1-AUTHORIZATION-1' or auth['request_digest']!=c.fingerprint(request) or auth['command_id']!=request['command_id'] or auth['work_id']!=request['work_ref']['value']['id'] or auth['account_id']!=value['account_id']:raise Conflict('actual F1 authorization binding differs')
        command=self.s.row('tl_command',request['command_id'])
        if command['operation']!='apply_invalidation' or command['state']!='committed' or command['fingerprint']!=command_fingerprint(request) or self.storage.read_artifact(command['principal_artifact_id'])!=request['principal']:raise Forbidden('actual F1 owner command did not commit')
        response=self.storage.read_artifact(command['result_artifact_id'])
        if not any(r['id']==barrier_id and r['kind']=='tl_barrier' for r in response['result_refs']):raise Conflict('actual F1 result does not name this barrier')
        return value

    def verify_origin_work(self,entry,plan,obligation,work):
        self._session(entry,plan);value=self._actual_f1_provenance(plan['barrier_id'])
        if value['request']['work_ref']['value']['id']!=work['id'] or obligation['generation']!=0 or obligation['budget_account_id']!=value['account_id']:raise Forbidden('independent original F1 resources do not bind this work/obligation')

    def authorize(self,bearer,plan,domains=('M12',),actions=None):
        """Create a real, exact M12 grant after authenticated bounded review."""
        actor=self._controller(bearer);plan=deepcopy(plan);domains=tuple(domains);actions={} if actions is None else deepcopy(actions)
        t.array(list(domains),lambda x:t.enum(x,DOMAINS))
        if not domains or len(set(domains))!=len(domains):raise ContractError('explicit unique authorized domains required')
        if set(actions)-set(domains):raise Forbidden('action domain is not delegated')
        checker=ManagedErasure(self.s,self);checker._plan(plan)
        with dispatch_gate(self.s.root):
            root_registration=self._registered_root()
            active,policy,control=self._current();limits=c.loads(policy['scope']).get('tool_learning_maintenance_limits')
            if policy['authority']!=actor:raise Forbidden('current maintenance policy owner does not authorize this controller')
            if type(limits) is not dict or set(limits)!=set(plan['caps']):raise Forbidden('explicit finite current maintenance policy is absent')
            for amount in limits.values():t.integer(amount,1,2**53-1)
            if limits['attempts']!=1 or any(plan['caps'][key]>limits[key] for key in limits):raise Forbidden('explicit finite current maintenance policy exceeded')
            if plan['authority_ref']!=actor or plan['deadline']<=self.clock():raise Forbidden('maintenance controller/deadline differs')
            prior=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.maintenance.controller' AND source_event_id=?",(self.s.instance_id,plan['id'])).fetchone()
            if prior is not None:
                body=self.storage.read_artifact(prior['payload_artifact_id'])
                if prior['payload_hash']!=c.fingerprint(body) or body['plan_digest']!=c.fingerprint(plan) or body['domains']!=list(domains) or body['actions']!=actions:raise Conflict('same maintenance plan key has different grant semantics')
                if body['policy_id']!=policy['id'] or body['policy_epoch']!=active['epoch'] or body['control_revision']!=control['control_revision'] or body['runtime_epoch']!=control['runtime_epoch']:raise Forbidden('old-plan continuation needs a new explicit current M12 continuation grant')
                self._source_owner(plan,actor)
                return self._mint(prior['id'],body,plan)
            amounts={'input_tokens':0,'output_tokens':0,'tool_calls':0,**plan['caps']}
            meter=PhysicalReadMeter(amounts,plan['deadline'],clock=self.clock)
            with meter.installed(self.s):
                source=self._source_owner(plan,actor)
                inventory=ManagedInventory(checker,max_rows=min(65536,plan['caps']['scan']))._discover(source)
                targets={r['id'] for r in inventory['targets']}
                if any(item['target']['id'] not in targets for item in plan['targets']):raise Forbidden('target is outside actual registered source/material inventory')
                provenance=self._actual_f1_provenance(plan['barrier_id'])
                scoped=self._fixed_source_materials(source,provenance['request']['work_ref']['value']['id'])
                if any(item['target']['id'] not in scoped for item in plan['targets']):raise Forbidden('conservative inventory includes an independent owner outside the fixed source scope')
                original_work=self.s.row('tl_work',provenance['request']['work_ref']['value']['id'])
                if original_work['learning_activity_id']!=plan['source_activity']:raise Forbidden('maintenance source activity differs from actual original F1 source work')
                for domain,items in actions.items():
                    for item in items:
                        t.obj(item,('target','action','expected'));self.storage.validate_ref(item['target']);t.string(item['action']);t.integer(item['expected'])
                        if item['target']['id'] not in targets:raise Forbidden('domain action outside source inventory')
                        if domain!='M04' or item['target']['kind'] not in ('tl_representation','tl_representation_head','tl_group','tl_handoff','tl_input_dependency'):raise Forbidden('actual owned domain action adapter unavailable')
                usage=meter.usage()
            if usage is None:raise Forbidden('maintenance grant review usage unknown')
            body={'contract':'TL-CONTROLLER-MAINTENANCE-GRANT-1','plan_id':plan['id'],'plan_digest':c.fingerprint(plan),'barrier_id':plan['barrier_id'],'source_epoch':plan['source_epoch'],
                'controller_id':actor,'policy_id':policy['id'],'policy_epoch':active['epoch'],'control_revision':control['control_revision'],'runtime_epoch':control['runtime_epoch'],
                'exclusion_root':str(self.exclusion_root),'root_registration_id':root_registration['id'],'deadline':plan['deadline'],'domains':list(domains),'actions':actions,'inventory_ids':sorted(targets),'bootstrap_usage':usage}
            with self.s.tx():
                current,_,now=self._current()
                if current!=active or now!=control:raise Conflict('current control/policy changed during exact grant review')
                key=self.s.event('maintenance.controller_authorized',payload=body,source='tl.maintenance.controller',key=plan['id'],lane='control')
            return self._mint(key,body,plan)

    def _mint(self,key,body,plan):
        credential=hashlib.sha256(self.s.root.joinpath('controller.token').read_bytes()).hexdigest()
        result={}
        for domain in body['domains']:
            entry=identifier();self.entries[entry]={'grant_id':key,'body':deepcopy(body),'plan':deepcopy(plan),'module':domain,'credential':credential};result[domain]=entry
        return {'grant_ref':ref(self.s,key,'runtime_events'),'entries':result,'bootstrap_usage':deepcopy(body['bootstrap_usage'])}

    def _session(self,entry,plan=None):
        binding=self.entries.get(entry)
        if binding is None:raise Forbidden('actual authenticated maintenance channel required')
        token=self.s.root/'controller.token'
        if token.is_symlink() or hashlib.sha256(token.read_bytes()).hexdigest()!=binding['credential']:raise Forbidden('controller credential generation changed')
        event=self.s.row('runtime_events',binding['grant_id']);body=self.storage.read_artifact(event['payload_artifact_id'])
        if event['source']!='tl.maintenance.controller' or event['event_type']!='maintenance.controller_authorized' or body!=binding['body'] or event['payload_hash']!=c.fingerprint(body):raise Conflict('actual maintenance grant mapping changed')
        registered=self._registered_root()
        if body['root_registration_id']!=registered['id']:raise Forbidden('grant belongs to another current exclusion root')
        active,policy,control=self._current()
        if body['controller_id']!=self.s.config()['controller'] or policy['id']!=body['policy_id'] or active['epoch']!=body['policy_epoch'] or control['control_revision']!=body['control_revision'] or control['runtime_epoch']!=body['runtime_epoch']:raise Forbidden('maintenance grant has stale current controller/policy/control')
        if body['deadline']<=self.clock():raise Forbidden('maintenance grant expired')
        if plan is not None and c.fingerprint(plan)!=body['plan_digest']:raise Forbidden('maintenance plan/targets/caps differ from exact authenticated grant')
        self._source_owner(binding['plan'],body['controller_id'])
        return binding

    def principal(self,entry):
        binding=self._session(entry);body=binding['body'];actor=ref(self.s,body['controller_id'],'social_actors')
        return {'actor':actor,'module':binding['module'],'recipient':deepcopy(actor),'purpose':'propagate','authorization':ref(self.s,body['policy_id'],'policy_versions')}

    def verify_maintenance(self,entry,plan,stage):
        binding=self._session(entry,plan)
        if binding['module']!='M12' and stage not in ('F2_resource_entry','F2_current_generation'):raise Forbidden('domain delegation is not an M12 physical cleanup grant')
    def initial_usage(self,entry,plan):return deepcopy(self._session(entry,plan)['body']['bootstrap_usage'])
    def verify_inventory(self,entry,plan,stage):
        binding=self._session(entry,plan)
        if binding['module']!='M12':raise Forbidden('inventory/physical verification belongs to M12')
        if any(target['target']['id'] not in binding['body']['inventory_ids'] for target in plan['targets']):raise Forbidden('target inventory grew beyond exact current authorization')
    def verify_target(self,entry,plan,target,stage):
        self.verify_maintenance(entry,plan,stage)
        if target not in plan['targets']:raise Forbidden('target/operation/location differs from authenticated plan')
    def verify_restore(self,entry,instance_id,stage):
        binding=self._session(entry)
        if binding['module']!='M12' or instance_id!=self.s.instance_id:raise Forbidden('actual current M12 restore-exclusion reader required')
        pending=_control_row(self.s,"SELECT id FROM control_commands WHERE instance_ref=? AND source='maintenance-controller' AND kind='maintenance.protective_change_pending' AND state IN ('received','running') LIMIT 1",(instance_id,))
        if pending is not None:raise Forbidden('current protective change has not reached an external exclusion head; restore is blocked')

    def verify(self,entry,operation,request,instance_id,stage):
        binding=self._session(entry)
        if operation!='acknowledge_propagation' or instance_id!=self.s.instance_id or request['principal']!=self.principal(entry):raise Forbidden('not the actual authenticated owned domain request')
        tables={'tl_propagation'}
        if binding['module']=='M04':tables.update(('tl_representation','tl_representation_head','tl_group','tl_handoff','tl_input_dependency'))
        return StorageGrant(binding['module'],frozenset(tables))
    def project_response(self,entry,operation,request,response,instance_id,stage):
        self.verify(entry,operation,request,instance_id,stage);return response
    def verify_propagation(self,entry,request,row,barrier,stage):
        binding=self._session(entry);body=binding['body']
        if row['domain']!=binding['module'] or row['barrier_id']!=body['barrier_id'] or barrier['source_epoch']!=body['source_epoch'] or request['principal']!=self.principal(entry):raise Forbidden('wrong actual domain/reason/epoch/principal')
        current=request['control'];active,policy,control=self._current()
        if current['policy']!={'object':ref(self.s,policy['id'],'policy_versions'),'revision':0,'epoch':active['epoch']} or current['runtime_epoch']!=control['runtime_epoch'] or current['cancelled']:raise Forbidden('F2 control does not bind current actual policy/runtime')
        configuration=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
        if current['configuration']['object']['id']!=configuration['id'] or current['configuration']['object']['kind']!='configuration_versions' or current['configuration']['revision']!=0:raise Forbidden('F2 current configuration binding differs')
    def apply_actions(self,transaction,entry,request,row,minimum,verification):
        binding=self._session(entry)
        for item in binding['body']['actions'].get(binding['module'],[]):LocalOwnerActions.apply(transaction,self.s,binding['module'],item['target'],item['action'],item['expected'])
    def verify_actions(self,entry,request,row,minimum,verification,stage):
        binding=self._session(entry);domain=binding['module'];body=binding['body']
        if verification['boundary']!={'contract':'TL-AUTHENTICATED-LOCAL-DOMAIN-1','grant_id':binding['grant_id'],'domain':domain}:raise Forbidden('verification is not bound to actual authenticated domain grant')
        if any(target['id'] not in body['inventory_ids'] for target in request['payload']['targets']):raise Forbidden('F2 includes unknown source/target owner')
        barrier=self.s.row('tl_barrier',body['barrier_id'])
        if barrier['state']!='active' or barrier['source_epoch']!=body['source_epoch']:raise Forbidden('actual source qualification hold is unavailable')
        for item in verification['per_target']:
            if item['verification']['kind']!='runtime_events' or item['action']!=item['verification']:raise Forbidden('actual domain hold evidence is not a real bound event')
            event=self.s.row('runtime_events',item['verification']['id']);fact=self.storage.read_artifact(event['payload_artifact_id'])
            expected={'contract':'TL-AUTHENTICATED-DOMAIN-HOLD-1','grant_id':binding['grant_id'],'barrier_id':row['barrier_id'],'source_epoch':barrier['source_epoch'],'domain':domain,'state':'active','targets':request['payload']['targets']}
            if event['source']!='tl.maintenance.domain' or event['event_type']!='maintenance.domain_hold_observed' or event['payload_hash']!=c.fingerprint(fact) or fact!=expected:raise Forbidden('actual current domain hold evidence differs')
        if domain=='M12':
            # This is the actual protective qualification gate, not scientific
            # content support or a statement that cleanup is already complete.
            return None
        if domain!='M04':raise Forbidden('actual semantic/domain verification adapter unavailable; keep pending')
        actions=body['actions'].get(domain,[])
        if not actions:raise Forbidden('M04 actual affected-target action inventory is absent')
        for item in actions:
            target=item['target'];actual=self.s.row(target['kind'],target['id'])
            if target['kind']=='tl_representation' and actual['state']!='withdrawn':raise Forbidden('actual representation remains current')
            if target['kind']=='tl_representation_head' and self.s.row('tl_representation',actual['representation_id'])['state']=='ready':raise Forbidden('actual head representation remains ready')
            if target['kind']=='tl_input_dependency' and actual['retention_state']=='allowed':raise Forbidden('actual input remains allowed')
            if target['kind']=='tl_group' and actual['state']!='obsolete':raise Forbidden('actual group remains ready')
            if target['kind']=='tl_handoff' and actual['state'] not in ('obsolete','published','permanent_failure'):raise Forbidden('actual old lease remains usable')
        return None

    def _register_root(self,actor):
        from digital_life.application.lifecycle.control_plane import Control
        root=self.exclusion_root
        if root.is_symlink():raise Forbidden('external control root is a symlink')
        root.mkdir(parents=True,exist_ok=True,mode=0o700);info=root.stat()
        body={'contract':'TL-CURRENT-MAINTENANCE-ROOT-1','instance_id':self.s.instance_id,'root':str(root),'device':info.st_dev,'inode':info.st_ino,'controller_id':actor}
        control=Control(self.s.root,self.s.instance_id)
        try:
            with control.tx():
                key,prior=control.command('maintenance.exclusion_root_registered','maintenance-exclusion-root-v1',body,authority='maintenance-controller')
                if not prior:control.db.execute("UPDATE control_commands SET state='succeeded',finished_at=? WHERE id=?",(self.clock(),key))
                return key
        finally:control.close()

    def _registered_root(self):
        row=_control_row(self.s,"SELECT * FROM control_commands WHERE instance_ref=? AND source='maintenance-controller' AND command_key='maintenance-exclusion-root-v1' AND state='succeeded'",(self.s.instance_id,))
        if row is None:raise Forbidden('no current outside-image control root registration')
        body=c.loads(row['payload'])
        if body.get('contract')!='TL-CURRENT-MAINTENANCE-ROOT-1' or row['payload_hash']!=c.fingerprint(body) or body.get('instance_id')!=self.s.instance_id or body.get('root')!=str(self.exclusion_root) or body.get('controller_id')!=self.s.config()['controller']:raise Forbidden('selected exclusion root differs from current control registration')
        if self.exclusion_root.is_symlink() or not self.exclusion_root.is_dir():raise Forbidden('current registered exclusion root missing')
        info=self.exclusion_root.stat()
        if (info.st_dev,info.st_ino)!=(body['device'],body['inode']):raise Forbidden('registered exclusion root identity replaced')
        return dict(row)

    def _head(self):
        row=_control_row(self.s,"SELECT * FROM control_commands WHERE instance_ref=? AND source='maintenance-controller' AND kind='maintenance.exclusion_head' AND state='succeeded' ORDER BY generation DESC LIMIT 1",(self.s.instance_id,))
        if row is None:return None
        value=c.loads(row['payload'])
        if row['payload_hash']!=c.fingerprint(value):raise Conflict('current control exclusion head integrity differs')
        return value

    def verify_exclusion_index(self,entry,plan,directory,index,stage):
        binding=self._session(entry,plan);registration=self._registered_root()
        if binding['module']!='M12' or directory!=str(self.exclusion_root):raise Forbidden('not the registered current M12 exclusion root')
        if any(record['instance_id']!=self.s.instance_id for record in index['entries'].values()):raise Forbidden('this current-control root is not shared with another instance')
        head=self._head()
        if head is None:
            if stage=='restore_current_head':raise Forbidden('no current control exclusion head registration')
            if len(index['entries'])>1 or index['entries'] and (plan is None or set(index['entries'])!={plan['id']}):raise Forbidden('cannot initialize unknown prior exclusion history')
            return None
        if head['root_registration_id']!=registration['id']:raise Forbidden('exclusion head belongs to another current root')
        if head['index_digest']==c.fingerprint(index) and head['generation']==index['generation']:return None
        if stage!='restore_current_head' and plan is not None and index['generation']==head['generation']+1 and all(index['entries'].get(key)==value for key,value in head['entries'].items()) and set(index['entries'])==set(head['entries'])|{plan['id']}:
            return None # exact interrupted authenticated append, never rollback
        raise Forbidden('old/replaced exclusion anchor differs from current control head')

    def record_exclusion_index(self,entry,plan,directory,index):
        self.verify_exclusion_index(entry,plan,directory,index,'resume_append');registration=self._registered_root()
        from digital_life.application.lifecycle.control_plane import Control
        value={'contract':'TL-CURRENT-MAINTENANCE-HEAD-1','root_registration_id':registration['id'],'root':directory,'generation':index['generation'],'index_digest':c.fingerprint(index),'entries':deepcopy(index['entries'])}
        control=Control(self.s.root,self.s.instance_id)
        try:
            with control.tx():
                key,prior=control.command('maintenance.exclusion_head','maintenance-exclusion-head:'+str(index['generation']),value,authority='maintenance-controller')
                if not prior:control.db.execute("UPDATE control_commands SET generation=?,state='succeeded',finished_at=? WHERE id=?",(index['generation'],self.clock(),key))
                provenance=self._actual_f1_provenance(plan['barrier_id']);change=provenance['request']['payload']['change_id']
                control.db.execute("UPDATE control_commands SET state='succeeded',result_json=?,finished_at=? WHERE instance_ref=? AND source='maintenance-controller' AND kind='maintenance.protective_change_pending' AND command_key=? AND state='running'",(dumps({'barrier_id':plan['barrier_id'],'source_epoch':plan['source_epoch'],'exclusion_plan_id':plan['id'],'head_generation':index['generation']}),self.clock(),self.s.instance_id,'protective-change:'+change))
        finally:control.close()

    def prepare_acknowledgement(self,entry,obligation_id,original_work):
        """Produce an exact current F2 packet and real hold-observation evidence.

        Preparing is not acknowledgement. It consumes the same maintenance
        account, and the eventual F2 repeats all current owner/action checks.
        """
        from digital_life.application.learning.propagation import MaintenanceReadAccounting
        binding=self._session(entry);plan=binding['plan'];row=self.s.row('tl_propagation',obligation_id)
        if binding['module'] not in ('M12','M04'):raise Forbidden('actual domain verifier is not implemented')
        active,policy,control=self._current();work=self.s.row('tl_work',original_work)
        if work['learning_activity_id']!=plan['source_activity']:raise Forbidden('not the original source work')
        configuration=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
        budget={'account_ref':ref(self.s,row['budget_account_id'],'activity_budget_accounts'),'deadline':row['deadline'],'max_attempts':1,'max_input_tokens':0,'max_output_tokens':0,'max_tool_calls':0,'max_scan':plan['caps']['scan'],'max_items':plan['caps']['items'],'max_bytes':plan['caps']['bytes']}
        request={'contract':'TL-LOOP-0.1','schema_revision':1,'instance_id':self.s.instance_id,'command_id':identifier(),'idempotency_key':identifier(),'principal':self.principal(entry),'work_ref':slot(ref(self.s,original_work,'tl_work')),
            'expected':slot({'object':ref(self.s,row['id'],'tl_propagation'),'revision':row['row_revision'],'epoch':row['generation']}),
            'control':{'policy':{'object':ref(self.s,policy['id'],'policy_versions'),'revision':0,'epoch':active['epoch']},'configuration':{'object':ref(self.s,configuration['id'],'configuration_versions'),'revision':0,'epoch':0},'source_epochs':[],'runtime_epoch':control['runtime_epoch'],'input_epoch':self.s.row('activities',work['learning_activity_id'])['input_epoch'],'cancelled':False},'budget':budget,'payload':{'domain':row['domain']}}
        erasure=ManagedErasure(self.s,self,clock=self.clock);accounting=MaintenanceReadAccounting(erasure,plan['id'])
        with dispatch_gate(self.s.root),accounting.operation(entry,request,row):
            minimum=self.storage.read_artifact(row['targets_artifact_id']);targets=minimum['targets'];barrier=self.s.row('tl_barrier',row['barrier_id'])
            complete=binding['module']=='M12'
            coverage={'state':'complete' if complete else 'partial','domain':slot('M12 current protective qualification gate' if complete else 'M04 explicitly owned withdrawal actions'),'scanned':len(targets),'limit':plan['caps']['scan'],'truncated':False,'missing':[] if complete else [{'status':'unknown','value':None,'reason_code':'not_measured','reason':'other owned targets require explicit owner coverage verification','basis_refs':[]}]}
            facts={'contract':'TL-AUTHENTICATED-DOMAIN-HOLD-1','grant_id':binding['grant_id'],'barrier_id':row['barrier_id'],'source_epoch':barrier['source_epoch'],'domain':binding['module'],'state':barrier['state'],'targets':targets}
            with self.s.tx():
                event=self.s.event('maintenance.domain_hold_observed',payload=facts,source='tl.maintenance.domain',key=identifier(),lane='control');evidence=ref(self.s,event,'runtime_events')
                verification={'contract':'TL-PROPAGATION-VERIFICATION-1','barrier':ref(self.s,barrier['id'],'tl_barrier'),'generation':row['generation'],'domain':binding['module'],'source_epoch':barrier['source_epoch'],'minimum_plan':ref(self.s,row['targets_artifact_id'],'artifacts'),'targets':targets,'actions':[evidence],'coverage':coverage,'boundary':{'contract':'TL-AUTHENTICATED-LOCAL-DOMAIN-1','grant_id':binding['grant_id'],'domain':binding['module']},'watermark':{'source_epoch':barrier['source_epoch'],'policy_epoch':active['epoch']},'unresolved':[] if complete else ['remaining owner coverage'],'per_target':[{'target':target,'action':evidence,'verification':evidence} for target in targets]}
                artifact=self.s.artifact(verification)
            request['payload']={'barrier':verification['barrier'],'generation':row['generation'],'domain':binding['module'],'targets':targets,'coverage':coverage,'actions':[evidence],'verification':ref(self.s,artifact,'artifacts')}
            self.verify_propagation(entry,request,row,barrier,'prepare_return')
            c.validate_request('acknowledge_propagation',request)
        return request

    def _protective_current(self):
        active=self.s.db.execute('SELECT * FROM policy_epochs WHERE instance_id=?',(self.s.instance_id,)).fetchone()
        control=_control_row(self.s,'SELECT * FROM instance_control_state WHERE instance_ref=?',(self.s.instance_id,))
        if active is None or control is None:raise Forbidden('actual current protective control unavailable')
        if control['active_process_run_id'] is not None:
            process=_control_row(self.s,'SELECT * FROM process_runs WHERE id=? AND instance_ref=?',(control['active_process_run_id'],self.s.instance_id))
            if process is None or process['exited_at'] is not None or process['pid'] is None:raise Forbidden('current managed process record inconsistent')
        return dict(active),self.s.row('policy_versions',active['policy_version_id']),dict(control)

    def protective_request(self,bearer,work_id,source,affected_scope,*,change_id=None,idempotency_key=None,kind='erase'):
        """Prepare real finite M12 resources, preserving the historical work.

        No source change, inference, tool dispatch or unlock happens here.
        Repeating a change ID reuses its fixed request/account/deadline.
        """
        from datetime import datetime,timedelta,timezone
        actor=self._controller(bearer);c.validate('VersionToken',source);c.validate('Scope',affected_scope);t.enum(kind,('erase','revoke','unavailable'))
        change_id=change_id or identifier();key=idempotency_key or change_id
        logical={'work_id':work_id,'source':source,'scope':affected_scope,'kind':kind,'change_id':change_id,'idempotency_key':key}
        with dispatch_gate(self.s.root):
            active,policy,control=self._protective_current();work=self.s.row('tl_work',work_id)
            self._owned_source(source['object'],policy['id'],actor)
            limits=c.loads(policy['scope']).get('tool_learning_maintenance_limits')
            if type(limits) is not dict:raise Forbidden('current finite M12 protective policy is not configured')
            t.obj(limits,('scan','items','bytes','elapsed_ms','attempts'))
            for value in limits.values():t.integer(value,1,2**53-1)
            if limits['attempts']!=1:raise Forbidden('current finite M12 protective policy unavailable')
            prior=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.maintenance.F1.prepared' AND source_event_id=?",(self.s.instance_id,change_id)).fetchone()
            if prior:
                value=self.storage.read_artifact(prior['payload_artifact_id'])
                if prior['payload_hash']!=c.fingerprint(value) or value['logical']!=logical:raise Conflict('protective change ID cannot reset source/scope/command/caps')
                if value['request']['principal']['authorization']['id']!=policy['id']:raise Forbidden('old protective preparation needs explicit current continuation')
                return deepcopy(value['request'])
            from digital_life.application.learning.eligibility import ToolLearningEligibility
            if ToolLearningEligibility(self.s).current_epoch(source['object'],affected_scope)!=source['epoch']:raise Conflict('new protective request has stale source epoch')
            obj=source['object'];trigger=self.s.row('activities',work['source_activity_id'])['trigger_event_id']
            if obj['kind']!='perception_signals':raise Forbidden('SDK work/input evidence adapter unavailable for this source kind')
            signal=self.s.row('perception_signals',obj['id'])
            if trigger!=obj['id'] or signal['artifact_id']!=work['source_artifact_id']:raise Forbidden('protective source is not this actual work input/trigger')
            material=self.s.row('artifacts',work['source_artifact_id'])
            evidence={'source':deepcopy(obj),'source_kind':'user_statement' if signal['source_actor_id']==actor else 'system_event','original_result':slot(),'receipt':slot(),'artifact':ref(self.s,material['id'],'artifacts'),'source_revision':slot(),'digest':{'algorithm':'sha256','hex':material['hash']},'media_type':material['media_type'],'encoding':slot('UTF-8'),'view':slot(),'view_digest':slot(),'locator':{'kind':'whole_artifact','justification':'actual immutable work trigger/input artifact'},'origin_method':{'name':'controller-protective-source','version':'1','request_ref':slot(),'model_config_ref':slot()},'observed_at':slot(signal['received_at']),'reported_at':slot(),'coverage':{'state':'complete','domain':slot('actual local signal artifact'),'scanned':1,'limit':1,'truncated':False,'missing':[]},'derivation_refs':[],'access_dependencies':[]}
            configuration=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
            activity_id=identifier();account_id=identifier();now=self.clock();deadline=(datetime.fromisoformat(now.replace('Z','+00:00'))+timedelta(milliseconds=limits['elapsed_ms'])).astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
            budget={'account_ref':ref(self.s,account_id,'activity_budget_accounts'),'deadline':deadline,'max_attempts':1,'max_input_tokens':0,'max_output_tokens':0,'max_tool_calls':0,'max_scan':limits['scan'],'max_items':limits['items'],'max_bytes':limits['bytes']}
            principal={'actor':ref(self.s,actor,'social_actors'),'module':'M12','recipient':ref(self.s,actor,'social_actors'),'purpose':'erase' if kind=='erase' else 'propagate','authorization':ref(self.s,policy['id'],'policy_versions')}
            request={'contract':'TL-LOOP-0.1','schema_revision':1,'instance_id':self.s.instance_id,'command_id':identifier(),'idempotency_key':key,'principal':principal,'work_ref':slot(ref(self.s,work_id,'tl_work')),'expected':slot(deepcopy(source)),
                'control':{'policy':{'object':ref(self.s,policy['id'],'policy_versions'),'revision':0,'epoch':active['epoch']},'configuration':{'object':ref(self.s,configuration['id'],'configuration_versions'),'revision':0,'epoch':0},'source_epochs':[deepcopy(source)],'runtime_epoch':control['runtime_epoch'],'input_epoch':self.s.row('activities',work['learning_activity_id'])['input_epoch'],'cancelled':False},'budget':budget,
                'payload':{'change_id':change_id,'kind':kind,'source':deepcopy(source),'replacement':slot(),'affected_scope':deepcopy(affected_scope),'subjects':[],'purposes':[],'expected_epoch':source['epoch'],'evidence':[evidence],'erase_scope':slot(ref(self.s,policy['id'],'policy_versions')) if kind=='erase' else slot()}}
            c.validate_request('apply_invalidation',request)
            with self.s.tx():
                self.s.insert('activities',id=activity_id,trigger_event_id=signal['id'],state='pending',release_id=self.s.row('activities',work['learning_activity_id'])['release_id'],publication_state='ready',deadline=deadline,budget_json={})
                self.s.insert('activity_budget_accounts',id=account_id,activity_id=activity_id,token_limit=0,tool_call_limit=0,attempt_limit=1,time_limit_ms=limits['elapsed_ms'])
                value={'contract':'TL-PROTECTIVE-F1-PREPARATION-1','logical':logical,'request':request,'activity_id':activity_id,'account_id':account_id,'caps':deepcopy(limits)}
                event=self.s.event('maintenance.protective_resources_prepared',payload=value,source='tl.maintenance.F1.prepared',key=change_id,activity=activity_id,lane='control')
                self.s.db.execute('UPDATE activities SET budget_json=? WHERE instance_id=? AND id=?',(dumps({'contract':'TL-PROTECTIVE-F1-BUDGET-1','preparation_event_id':event,'used':{dimension:0 for dimension in ('scan','items','bytes','elapsed_ms','attempts')},'entered':False,'unknown':False}),self.s.instance_id,activity_id))
            return request

    def _prepared_f1(self,request):
        row=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.maintenance.F1.prepared' AND source_event_id=?",(self.s.instance_id,request['payload']['change_id'])).fetchone()
        if row is None:raise Forbidden('actual independent protective resources were not prepared')
        value=self.storage.read_artifact(row['payload_artifact_id'])
        if row['payload_hash']!=c.fingerprint(value) or value['contract']!='TL-PROTECTIVE-F1-PREPARATION-1' or value['request']!=request:raise Forbidden('protective request differs from exact independently prepared resources')
        activity=self.s.row('activities',value['activity_id']);account=self.s.row('activity_budget_accounts',value['account_id']);ledger=c.loads(activity['budget_json'])
        if ledger.get('contract')!='TL-PROTECTIVE-F1-BUDGET-1' or ledger.get('preparation_event_id')!=row['id'] or account['activity_id']!=activity['id'] or (account['token_limit'],account['tool_call_limit'],account['attempt_limit'],account['time_limit_ms'])!=(0,0,1,value['caps']['elapsed_ms']) or request['budget']['account_ref']['id']!=account['id'] or activity['deadline']!=request['budget']['deadline']:raise Forbidden('protective real account/ledger/caps binding changed')
        t.obj(ledger,('contract','preparation_event_id','used','entered','unknown'));t.boolean(ledger['entered']);t.boolean(ledger['unknown'])
        t.obj(ledger['used'],tuple(value['caps']))
        for amount in ledger['used'].values():t.integer(amount)
        return value,activity,account,ledger

    def authorize_invalidation(self,bearer,envelope):
        """Authenticate the exact F1 command, source/work/scope and controls.

        This is distinct from an existing-barrier maintenance grant. It never
        retroactively validates an untrusted earlier change or fabricates work.
        """
        actor=self._controller(bearer);c.validate_request('apply_invalidation',envelope);request=deepcopy(envelope)
        with dispatch_gate(self.s.root):
            active,policy,control=self._protective_current();p=request['payload']
            if p['kind'] not in ('erase','revoke','unavailable') or p['replacement']['status']=='known':raise Forbidden('M12 protective SDK cannot manufacture corrected scientific content')
            scope_id=p['erase_scope']['value']['id'] if p['erase_scope']['status']=='known' else policy['id']
            self._owned_source(p['source']['object'],scope_id,actor)
            expected={'actor':ref(self.s,actor,'social_actors'),'module':'M12','recipient':ref(self.s,actor,'social_actors'),'purpose':'erase' if p['kind']=='erase' else 'propagate','authorization':ref(self.s,policy['id'],'policy_versions')}
            if request['principal']!=expected or request['instance_id']!=self.s.instance_id:raise Forbidden('protective request is not the real current controller principal')
            work=self.s.row('tl_work',request['work_ref']['value']['id']);signal=self.s.row('perception_signals',p['source']['object']['id']) if p['source']['object']['kind']=='perception_signals' else None
            if signal is None or self.s.row('activities',work['source_activity_id'])['trigger_event_id']!=signal['id'] or work['source_artifact_id']!=signal['artifact_id']:raise Forbidden('actual source/work evidence binding unavailable')
            prepared,maintenance_activity,maintenance_account,ledger=self._prepared_f1(request)
            if request['budget']['deadline']<=self.clock():raise Forbidden('protective preparation deadline already expired')
            if maintenance_account['id']==work['budget_account_id']:raise Forbidden('protective preparation cannot borrow the old model account')
            configuration=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
            if request['control']['policy']!={'object':ref(self.s,policy['id'],'policy_versions'),'revision':0,'epoch':active['epoch']} or request['control']['configuration']!={'object':ref(self.s,configuration['id'],'configuration_versions'),'revision':0,'epoch':0} or request['control']['runtime_epoch']!=control['runtime_epoch'] or request['control']['cancelled']:raise Forbidden('protective current control binding differs')
            body={'contract':'TL-CONTROLLER-F1-AUTHORIZATION-1','command_id':request['command_id'],'idempotency_key':request['idempotency_key'],'request_digest':c.fingerprint(request),'controller_id':actor,'configuration_id':configuration['id'],'policy_id':policy['id'],'policy_epoch':active['epoch'],'control_revision':control['control_revision'],'runtime_epoch':control['runtime_epoch'],'active_process_run_id':control['active_process_run_id'],'deadline':request['budget']['deadline'],'work_id':work['id'],'account_id':maintenance_account['id'],'maintenance_activity_id':maintenance_activity['id'],'scope_semantics':'all subjects and purposes within the explicitly owned source and affected_scope'}
            with self.s.tx():key=self.s.event('maintenance.protective_change_authorized',payload=body,source='tl.maintenance.F1',key=request['idempotency_key'],activity=work['learning_activity_id'],lane='control')
            if not hasattr(self,'_f1_entries'):self._f1_entries={}
            entry=identifier();self._f1_entries[entry]={'event_id':key,'body':body,'request':request,'credential':hashlib.sha256(self.s.root.joinpath('controller.token').read_bytes()).hexdigest()}
            return entry

    def _f1_session(self,entry,request):
        binding=getattr(self,'_f1_entries',{}).get(entry)
        if binding is None:raise Forbidden('actual independent F1 controller authorization required')
        token=self.s.root/'controller.token'
        if token.is_symlink() or hashlib.sha256(token.read_bytes()).hexdigest()!=binding['credential']:raise Forbidden('protective credential generation changed')
        body=binding['body'];event=self.s.row('runtime_events',binding['event_id']);actual=self.storage.read_artifact(event['payload_artifact_id'])
        if actual!=body or event['source']!='tl.maintenance.F1' or event['event_type']!='maintenance.protective_change_authorized' or event['payload_hash']!=c.fingerprint(body) or c.fingerprint(request)!=body['request_digest']:raise Forbidden('F1 command/idempotency/source/work/scope changed after authorization')
        active,policy,control=self._protective_current()
        configuration=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
        if configuration is None or body['configuration_id']!=configuration['id'] or body['controller_id']!=self.s.config()['controller'] or self.s.row('identity_instances',self.s.instance_id)['controller_ref']!=body['controller_id']:raise Forbidden('F1 current configuration/controller identity changed')
        if self.clock()>=body['deadline'] or policy['id']!=body['policy_id'] or active['epoch']!=body['policy_epoch'] or control['control_revision']!=body['control_revision'] or control['runtime_epoch']!=body['runtime_epoch'] or control['active_process_run_id']!=body['active_process_run_id']:raise Forbidden('F1 authorization expired or current policy/control changed')
        scope=request['payload']['erase_scope']['value']['id'] if request['payload']['erase_scope']['status']=='known' else policy['id']
        self._owned_source(request['payload']['source']['object'],scope,body['controller_id'])
        return binding

    def _pending_protective_change(self,entry,request):
        self._f1_session(entry,request);registration=self._registered_root()
        from digital_life.application.lifecycle.control_plane import Control
        payload={'contract':'TL-CURRENT-PROTECTIVE-CHANGE-1','instance_id':self.s.instance_id,'change_id':request['payload']['change_id'],'kind':request['payload']['kind'],
            'root_registration_id':registration['id'],'source':request['payload']['source'],'scope_digest':c.fingerprint(request['payload']['affected_scope']),
            'result_epoch_floor':request['payload']['expected_epoch']+1,'work_id':request['work_ref']['value']['id'],'command_id':request['command_id']}
        control=Control(self.s.root,self.s.instance_id)
        try:
            with control.tx():
                key,prior=control.command('maintenance.protective_change_pending','protective-change:'+request['payload']['change_id'],payload,authority='maintenance-controller')
                if not prior:control.db.execute("UPDATE control_commands SET state='running' WHERE id=?",(key,))
        finally:control.close()

    def current_restore_exclusions(self,entry,instance_id,max_records,max_bytes):
        self.verify_restore(entry,instance_id,'current_control_exclusions')
        rows=self.s.control_reader().execute("SELECT payload,payload_hash,state,result_json FROM control_commands WHERE instance_ref=? AND source='maintenance-controller' AND kind='maintenance.protective_change_pending' ORDER BY received_at LIMIT ?",(instance_id,max_records+1))
        result=[];size=0
        for row in rows:
            if len(result)>=max_records:raise Forbidden('current protective control coverage bound exceeded')
            size+=len(row['payload'].encode())+len((row['result_json'] or '').encode())
            if size>max_bytes:raise Forbidden('current protective control byte coverage bound exceeded')
            value=c.loads(row['payload'])
            if row['payload_hash']!=c.fingerprint(value) or value.get('contract')!='TL-CURRENT-PROTECTIVE-CHANGE-1':raise Conflict('current protective control exclusion integrity differs')
            result.append({'directive':value,'state':row['state'],'result':c.loads(row['result_json']) if row['result_json'] else None})
        return result

    def reconcile_protective_commit(self,bearer,command_id):
        """Read durable F1 proof after lost acknowledgement; NEVER rerun F1."""
        actor=self._controller(bearer)
        from digital_life.infrastructure.persistence.tool_learning_store import command_fingerprint
        amounts={'input_tokens':0,'output_tokens':0,'tool_calls':0,'attempts':0,'scan':1024,'items':1024,'bytes':1048576,'elapsed_ms':1000}
        meter=PhysicalReadMeter(amounts,(datetime.fromisoformat(self.clock().replace('Z','+00:00'))+timedelta(seconds=1)).isoformat(timespec='milliseconds').replace('+00:00','Z'),clock=self.clock);result=None
        with dispatch_gate(self.s.root):
            self._current()
            try:
                with meter.installed(self.s):
                    command=self.s.row('tl_command',command_id)
                    if command['operation']!='apply_invalidation' or command['state']!='committed':raise Forbidden('protective outcome has no durable committed proof')
                    response=self.storage.read_artifact(command['result_artifact_id'])
                    barriers=[r for r in response['result_refs'] if r['kind']=='tl_barrier']
                    if len(barriers)!=1:raise Conflict('protective result does not bind one actual barrier')
                    provenance=self._actual_f1_provenance(barriers[0]['id']);request=provenance['request']
                    if request['command_id']!=command_id or command['fingerprint']!=command_fingerprint(request):raise Conflict('durable protective proof names a different original command')
                    erase=request['payload']['erase_scope'];scope_id=erase['value']['id'] if erase['status']=='known' else request['principal']['authorization']['id']
                    self._owned_source(request['payload']['source']['object'],scope_id,actor)
                    barrier=self.s.row('tl_barrier',barriers[0]['id'])
                    result={'command_id':command_id,'persistent_commit':'committed','barrier_id':barrier['id'],'source_epoch':barrier['source_epoch'],'reexecuted':False,'restore_exclusion_complete':False,'unknown_consumption_released':False}
                    meter.time();return result
            finally:
                with self.s.tx():self.s.event('recovery.protective_commit_reconciled',payload={'controller_id':actor,'command_id':command_id,'result':result,'usage':meter.usage(),'measured':dict(meter.actual),'unknown':meter.usage() is None,'automatic_replay':False},source='tl.recovery.protective',lane='control')

    def apply_protective(self,entry,request):
        return _apply_protective(self,entry,request)


from digital_life.application.learning.invalidation import InvalidationAuthority

class ControllerInvalidationAuthority(InvalidationAuthority):
    """Actual F1 adapter, separate authorization from existing-barrier F3."""
    def __init__(self,controller):
        if not isinstance(controller,ControllerMaintenanceAuthority):raise ContractError('actual controller M12 owner required')
        self.controller=controller
    def verify(self,entry,operation,request,instance_id,stage):
        self.controller._f1_session(entry,request)
        if operation!='apply_invalidation' or instance_id!=self.controller.s.instance_id:raise Forbidden('not the authorized F1 instance/operation')
        return StorageGrant('M12',frozenset(('tl_change','tl_source_epoch','tl_barrier','tl_propagation','tl_input_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):
        self.verify(entry,operation,request,instance_id,stage);return response
    def verify_protective_budget(self,entry,request,work,account,activity,stage):
        binding=self.controller._f1_session(entry,request);prepared,actual_activity,actual_account,ledger=self.controller._prepared_f1(request)
        if getattr(self.controller,'_active_protective',{}).get(entry)!=account['id'] or account!=actual_account or activity!=actual_activity or binding['body']['work_id']!=work['id'] or binding['body']['account_id']!=account['id'] or not ledger['entered'] or ledger['unknown']:raise Forbidden('actual current M12 protective budget opportunity is not entered')
    def verify_change(self,entry,request,stage):
        self.controller._f1_session(entry,request)
        if getattr(self.controller,'_active_protective',{}).get(entry)!=request['budget']['account_ref']['id']:raise Forbidden('actual protective read opportunity is not entered')
    def verify_version(self,entry,request,token,stage):
        self.controller._f1_session(entry,request);obj=token['object'];self.controller.storage.validate_ref(obj)
        if obj['kind']!='perception_signals' or token['revision']!=0:raise Forbidden('actual protective source version adapter unavailable')
        s=self.controller.s
        if has_registered_revision(s,obj['id']):raise Conflict('static signal conflicts with native registered version')
        signal=s.row('perception_signals',obj['id']);self.controller.storage.read_artifact(signal['artifact_id'])


def _apply_protective(controller,entry,request):
    """Real control opportunity; deliberately not an IM05 execution grant."""
    from digital_life.application.learning.invalidation import ToolLearningInvalidation
    from digital_life.infrastructure.persistence.tool_learning_store import CommitUnknown
    s=controller.s
    if s.db.in_transaction:raise Conflict('protective F1 needs independent instance transaction')
    with dispatch_gate(s.root):
        controller._f1_session(entry,request);prepared,activity,account,ledger=controller._prepared_f1(request)
        controller._pending_protective_change(entry,request)
        if ledger['entered'] or ledger['unknown']:raise Forbidden('protective F1 prior resource/commit outcome unknown; original grant remains held')
        caps=prepared['caps'];remaining={key:max(0,caps[key]-ledger['used'][key]) for key in caps}
        meter=PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'tool_calls':0,**remaining},request['budget']['deadline'],clock=controller.clock)
        ledger['entered']=True
        with s.tx():s.db.execute('UPDATE activities SET budget_json=? WHERE instance_id=? AND id=?',(dumps(ledger),s.instance_id,activity['id']))
        if not hasattr(controller,'_active_protective'):controller._active_protective={}
        controller._active_protective[entry]=prepared['account_id'];commit_unknown=False
        try:
            with meter.installed(s):
                return ToolLearningInvalidation(s,ControllerInvalidationAuthority(controller),clock=controller.clock).apply(entry,request)
        except CommitUnknown:commit_unknown=True;raise
        finally:
            controller._active_protective.pop(entry,None)
            usage=meter.usage();measured=meter.actual if usage is None else usage
            with s.tx():
                for key in caps:ledger['used'][key]+=measured[key]
                ledger['entered']=False;ledger['unknown']=usage is None or commit_unknown
                s.db.execute('UPDATE activities SET budget_json=? WHERE instance_id=? AND id=?',(dumps(ledger),s.instance_id,activity['id']))


