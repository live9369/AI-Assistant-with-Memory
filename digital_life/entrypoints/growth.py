"""Explicit CLI operations for T02-T04; no deployment or implicit wake."""
import json
from pathlib import Path
from digital_life.domain.contracts import ContractError,Forbidden,identifier

def parsers(sub):
 p=sub.add_parser('task-loop');p.add_argument('operation',choices=['start','status','resume']);p.add_argument('--text');p.add_argument('--activity');p.add_argument('--path');p.add_argument('--contains');p.add_argument('--key');p.add_argument('--max-rounds',type=int,default=3)
 p=sub.add_parser('cognition');p.add_argument('operation',choices=['status','enable','disable','confirm','method-feedback','retract-method-feedback']);p.add_argument('--revision');p.add_argument('--expected-current');p.add_argument('--source');p.add_argument('--outcome',choices=['success','failure','unknown']);p.add_argument('--reason');p.add_argument('--feedback')
 p=sub.add_parser('memory-feedback');p.add_argument('operation',choices=['propose','evaluate','commit','rollback']);p.add_argument('--memory');p.add_argument('--content');p.add_argument('--reason');p.add_argument('--proposal');p.add_argument('--evaluation');p.add_argument('--commit');p.add_argument('--cases');p.add_argument('--evidence',nargs='+')
 p=sub.add_parser('goal-regulation');p.add_argument('operation',choices=['status','enable','disable','prioritize']);p.add_argument('--activity');p.add_argument('--features');p.add_argument('--min-disk-bytes',type=int,default=67108864)
 p=sub.add_parser('behavior-policy');p.add_argument('operation',choices=['status','enable','disable']);p.add_argument('--temperature',type=float,default=.7);p.add_argument('--parameters')
 p=sub.add_parser('personality-growth');p.add_argument('operation',choices=['status','enable','disable','observe','invalidate','propose','evaluate','commit','rollback']);p.add_argument('--opportunity');p.add_argument('--trait');p.add_argument('--value',type=float);p.add_argument('--reliability',type=float,default=1);p.add_argument('--context');p.add_argument('--reason');p.add_argument('--key');p.add_argument('--observation');p.add_argument('--observations',nargs='+');p.add_argument('--heldout',nargs='+');p.add_argument('--proposal');p.add_argument('--evaluation');p.add_argument('--commit');p.add_argument('--evidence',nargs='+')
 p=sub.add_parser('habit-learning');p.add_argument('operation',choices=['status','enable','disable','enroll','feedback','inhibit','resume','rollback','collect-enable','collect-disable','candidates','confirm-candidate','reject-candidate']);p.add_argument('--candidate');p.add_argument('--definition');p.add_argument('--key');p.add_argument('--observation');p.add_argument('--outcome',type=int);p.add_argument('--reason');p.add_argument('--expected-revision');p.add_argument('--association');p.add_argument('--change');p.add_argument('--evidence',nargs='+')
 p=sub.add_parser('people-relations');p.add_argument('operation',choices=['status','enable','disable','register','alias','resolve','relate','trust','repair','invalidate']);p.add_argument('--person');p.add_argument('--name');p.add_argument('--alias');p.add_argument('--label');p.add_argument('--scope',default='global');p.add_argument('--domain');p.add_argument('--dimension',default='reliability');p.add_argument('--condition');p.add_argument('--outcome',type=int);p.add_argument('--evidence',nargs='+');p.add_argument('--reason');p.add_argument('--key');p.add_argument('--expected-revision');p.add_argument('--target')
 p=sub.add_parser('memory-quality');p.add_argument('operation',choices=['status','enable','disable','plan','preview','commit','conflict','retain','rebuild-index','evaluate','erase']);p.add_argument('--memory');p.add_argument('--spec');p.add_argument('--plan');p.add_argument('--left');p.add_argument('--right');p.add_argument('--evidence',nargs='+');p.add_argument('--key');p.add_argument('--reason');p.add_argument('--retention',choices=['demote','archive','retract','restore']);p.add_argument('--expected-revision');p.add_argument('--salience',type=float,default=.1);p.add_argument('--cases');p.add_argument('--k',type=int,default=5);p.add_argument('--include-registered-backups',action='store_true')
 p=sub.add_parser('autonomy-agenda');p.add_argument('operation',choices=['status','enable','disable','promise','release','question']);p.add_argument('--spec');p.add_argument('--key');p.add_argument('--commitment')
 p=sub.add_parser('maintenance');p.add_argument('operation',choices=['status','enable','disable','diagnose','plan','repair','propose','build','validate']);p.add_argument('--auto-repair',action='store_true');p.add_argument('--max-repairs',type=int,default=3);p.add_argument('--kind',choices=['restore_workspace','rebuild_index']);p.add_argument('--key');p.add_argument('--plan');p.add_argument('--proposal');p.add_argument('--spec');p.add_argument('--timeout',type=float,default=30)
 sub.add_parser('roadmap')

def required(value,name):
 if not value:raise ContractError('required argument: '+name)
 return value

def check_running_feature(store,module):
 from digital_life.application.lifecycle.release_inspection import release_status
 from digital_life.infrastructure.persistence.sqlite_store import PROJECT
 state=release_status(store.root,PROJECT)
 if state.get('process_run_id'):
  import sqlite3
  c=sqlite3.connect((store.root/'control.sqlite').as_uri()+'?mode=ro',uri=True)
  try:release=c.execute('SELECT release FROM deployments WHERE id=?',(state['deployment_id'],)).fetchone()[0]
  finally:c.close()
  if not (store.root/'releases'/release/'digital_life/application'/module).is_file():raise Forbidden('running release lacks this feature; stop and explicitly deploy first')

def handle(store,args):
 from digital_life.application.learning.runtime import legacy_protection_present
 if args.command!='maintenance' and legacy_protection_present(store):raise Forbidden('protected source state requires qualified module operations; legacy growth material is blocked')
 from digital_life.application.runtime.engine import Engine
 from digital_life.application.autonomy.task_loop import TaskLoop
 from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
 from digital_life.application.learning.learning_pipeline import LearningPipeline
 actor=store.config()['controller']
 if args.command=='maintenance':
  from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
  from digital_life.application.lifecycle.source_updates import SourceUpdates
  maintenance=SelfMaintenance(store);updates=SourceUpdates(store)
  if args.operation=='status':return dict(maintenance.status(),source_updates=updates.status())
  check_running_feature(store,'self_maintenance.py')
  if args.operation in ('enable','disable'):return maintenance.configure(args.operation=='enable',actor,args.auto_repair,args.max_repairs)
  if args.operation=='diagnose':return maintenance.diagnose()
  if args.operation=='plan':return maintenance.plan(required(args.kind,'--kind'),required(args.key,'--key'),actor)
  if args.operation=='repair':return maintenance.repair(required(args.plan,'--plan'),actor)
  if args.operation=='propose':
   spec=json.loads(Path(required(args.spec,'--spec')).read_text())
   if not isinstance(spec,dict) or set(spec)!={'base_deployment','changes','reason'}:raise ContractError('source spec requires base_deployment,changes,reason')
   return updates.propose(**spec,key=required(args.key,'--key'),actor=actor)
  if args.operation=='build':return updates.build(required(args.proposal,'--proposal'),actor)
  return updates.validate(required(args.proposal,'--proposal'),actor,args.timeout)
 if args.command=='autonomy-agenda':
  from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
  agenda=AutonomyAgenda(store)
  if args.operation=='status':return agenda.status()
  check_running_feature(store,'autonomy_agenda.py')
  if args.operation in ('enable','disable'):return agenda.configure(args.operation=='enable',actor)
  if args.operation=='release':return agenda.release(required(args.commitment,'--commitment'),actor)
  spec=json.loads(Path(required(args.spec,'--spec')).read_text())
  if not isinstance(spec,dict):raise ContractError('object spec required')
  return getattr(agenda,args.operation)(**spec,key=required(args.key,'--key'),actor=actor)
 if args.command=='memory-quality':
  from digital_life.application.memory.memory_quality import MemoryQuality
  quality=MemoryQuality(store)
  if args.operation=='status':return quality.status(args.memory)
  check_running_feature(store,'memory_quality.py')
  if args.operation in ('enable','disable'):return quality.configure(args.operation=='enable',actor)
  if args.operation=='plan':return quality.plan(json.loads(Path(required(args.spec,'--spec')).read_text()),required(args.key,'--key'),actor)
  if args.operation=='preview':return quality.preview(required(args.plan,'--plan'),actor)
  if args.operation=='commit':return quality.commit(required(args.plan,'--plan'),actor)
  if args.operation=='conflict':return quality.conflict(required(args.left,'--left'),required(args.right,'--right'),required(args.evidence,'--evidence'),required(args.reason,'--reason'),required(args.key,'--key'),actor)
  if args.operation=='retain':return quality.retain(required(args.memory,'--memory'),required(args.retention,'--retention'),required(args.expected_revision,'--expected-revision'),required(args.key,'--key'),required(args.reason,'--reason'),actor,args.salience)
  if args.operation=='rebuild-index':return quality.rebuild(actor)
  if args.operation=='evaluate':return quality.evaluate(json.loads(Path(required(args.cases,'--cases')).read_text()),actor,args.k)
  from digital_life.application.accounts.privacy import Privacy
  return Privacy(store).erase(required(args.memory,'--memory'),actor,args.include_registered_backups)
 if args.command=='people-relations':
  from digital_life.application.behavior.people_relations import PeopleRelations
  people=PeopleRelations(store)
  if args.operation=='status':return people.status()
  if args.operation=='resolve':return people.resolve(required(args.name,'--name'),args.scope)
  check_running_feature(store,'people_relations.py')
  if args.operation in ('enable','disable'):return people.configure(args.operation=='enable',actor)
  key=required(args.key,'--key')
  if args.operation=='register':return people.register(required(args.name,'--name'),required(args.evidence,'--evidence'),key,actor)
  if args.operation=='alias':return people.alias(required(args.person,'--person'),required(args.alias,'--alias'),args.scope,required(args.evidence,'--evidence'),key,actor)
  if args.operation=='relate':return people.relate(required(args.person,'--person'),required(args.label,'--label'),required(args.evidence,'--evidence'),key,actor)
  if args.operation=='invalidate':return people.invalidate(required(args.target,'--target'),required(args.reason,'--reason'),key,actor)
  revision=required(args.expected_revision,'--expected-revision');revision=None if revision=='none' else revision
  condition=json.loads(Path(args.condition).read_text()) if args.condition else {}
  if args.operation=='trust':
   if args.outcome is None:raise ContractError('required argument: --outcome')
   return people.trust(required(args.person,'--person'),required(args.domain,'--domain'),args.dimension,condition,args.outcome,required(args.evidence,'--evidence'),required(args.reason,'--reason'),key,revision,actor)
  return people.repair(required(args.person,'--person'),required(args.domain,'--domain'),args.dimension,condition,required(args.reason,'--reason'),key,revision,actor)
 if args.command=='habit-learning':
  from digital_life.application.behavior.habit_learning import HabitLearning
  habits=HabitLearning(store)
  if args.operation in ('collect-enable','collect-disable','candidates','confirm-candidate','reject-candidate'):
   from digital_life.application.behavior.habit_candidates import HabitCandidates
   candidates=HabitCandidates(store)
   if args.operation=='candidates':return candidates.status()
   check_running_feature(store,'habit_candidates.py')
   if args.operation in ('collect-enable','collect-disable'):return candidates.configure(args.operation=='collect-enable',actor)
   return candidates.decide(required(args.candidate,'--candidate'),required(args.expected_revision,'--expected-revision'),args.operation=='confirm-candidate',required(args.reason,'--reason'),required(args.key,'--key'),actor)
  if args.operation=='status':return habits.status()
  check_running_feature(store,'habit_learning.py')
  if args.operation in ('enable','disable'):return habits.configure(args.operation=='enable',actor)
  if args.operation=='enroll':
   definition=json.loads(Path(required(args.definition,'--definition')).read_text())
   if not isinstance(definition,dict) or set(definition)!={'action','cue'}:raise ContractError('action and cue definition required')
   return habits.enroll(definition['action'],definition['cue'],required(args.key,'--key'),actor)
  if args.operation=='feedback':
   if args.outcome is None:raise ContractError('required argument: --outcome')
   return habits.feedback(required(args.observation,'--observation'),args.outcome,required(args.reason,'--reason'),required(args.key,'--key'),required(args.expected_revision,'--expected-revision'),actor)
  if args.operation in ('inhibit','resume'):return habits.control(required(args.association,'--association'),args.operation,required(args.reason,'--reason'),required(args.expected_revision,'--expected-revision'),actor)
  return habits.rollback(required(args.change,'--change'),required(args.evidence,'--evidence'),actor)
 if args.command=='personality-growth':
  from digital_life.application.behavior.personality_growth import PersonalityGrowth
  growth=PersonalityGrowth(store)
  if args.operation=='status':return growth.status()
  check_running_feature(store,'personality_growth.py')
  if args.operation in ('enable','disable'):return growth.configure(args.operation=='enable',actor)
  if args.operation=='observe':
   if args.value is None:raise ContractError('required argument: --value')
   return {'observation':growth.observe(required(args.opportunity,'--opportunity'),required(args.trait,'--trait'),args.value,args.reliability,required(args.context,'--context'),required(args.reason,'--reason'),required(args.key,'--key'),actor)}
  if args.operation=='invalidate':return {'event':growth.invalidate(required(args.observation,'--observation'),required(args.reason,'--reason'),actor)}
  if args.operation=='propose':return growth.propose(required(args.trait,'--trait'),required(args.observations,'--observations'),actor)
  if args.operation=='evaluate':return growth.evaluate(required(args.proposal,'--proposal'),required(args.heldout,'--heldout'),actor)
  if args.operation=='commit':return growth.commit(required(args.proposal,'--proposal'),required(args.evaluation,'--evaluation'),actor)
  return growth.rollback(required(args.commit,'--commit'),required(args.evidence,'--evidence'),actor)
 if args.command=='behavior-policy':
  from digital_life.application.behavior.behavior_policy import BehaviorPolicy
  behavior=BehaviorPolicy(store)
  if args.operation=='status':return {'configuration':behavior.config(),'features':behavior.dimensions(),'inference_started':False}
  check_running_feature(store,'behavior_policy.py')
  return behavior.configure(args.operation=='enable',actor,args.temperature,json.loads(Path(args.parameters).read_text()) if args.parameters else None)
 if args.command=='goal-regulation':
  from digital_life.application.behavior.goal_regulation import GoalRegulation
  regulation=GoalRegulation(store)
  if args.operation=='status':return regulation.status()
  check_running_feature(store,'goal_regulation.py')
  if args.operation=='prioritize':return regulation.prioritize(required(args.activity,'--activity'),json.loads(Path(required(args.features,'--features')).read_text()),actor)
  return regulation.configure(args.operation=='enable',actor,args.min_disk_bytes)
 if args.command=='task-loop':
  loop=TaskLoop(store)
  if args.operation=='status':return loop.status(required(args.activity,'--activity'))
  check_running_feature(store,'task_loop.py')
  if args.operation=='start':
   with store.tx():
    a=Engine(store).submit(required(args.text,'--text'),args.key or identifier(),'task-loop')
    result=loop.configure(a,{'kind':'file_contains','path':required(args.path,'--path'),'text':required(args.contains,'--contains')},actor,args.max_rounds)
   return dict(result,activity=a,inference_started=False)
  return loop.resume(Engine(store),required(args.activity,'--activity'),required(args.text,'--text'),actor)
 if args.command=='cognition':
  c=CognitiveUpdates(store)
  if args.operation=='status':return {'enabled':c.enabled(),'generation':c.generation(),'beliefs':c.snapshot()}
  check_running_feature(store,'cognitive_updates.py')
  if args.operation=='confirm':return {'revision':c.confirm(required(args.revision,'--revision'),required(args.expected_current,'--expected-current'),actor)}
  if args.operation in ('method-feedback','retract-method-feedback'):
   from digital_life.application.cognition.method_experience import MethodExperience
   check_running_feature(store,'method_experience.py');methods=MethodExperience(store)
   if args.operation=='method-feedback':return methods.feedback(required(args.revision,'--revision'),required(args.outcome,'--outcome'),required(args.source,'--source'),required(args.reason,'--reason'),actor)
   return {'event':methods.retract(required(args.feedback,'--feedback'),required(args.reason,'--reason'),actor)}
  c.configure(args.operation=='enable',actor);return {'enabled':c.enabled(),'inference_started':False}
 if args.command=='memory-feedback':
  check_running_feature(store,'learning_pipeline.py');p=LearningPipeline(store)
  if args.operation=='propose':return p.feedback(required(args.memory,'--memory'),required(args.content,'--content'),required(args.reason,'--reason'),actor)
  if args.operation=='evaluate':return p.evaluate(required(args.proposal,'--proposal'),json.loads(Path(required(args.cases,'--cases')).read_text()),actor)
  if args.operation=='commit':return {'commit':p.commit(required(args.proposal,'--proposal'),required(args.evaluation,'--evaluation'),actor)}
  return {'reversal':p.rollback(required(args.commit,'--commit'),required(args.evidence,'--evidence'),actor)}
 raise ContractError('unknown growth operation')
