"""Resource-aware evidence reuse and conservative executable-plan admission.

Metadata guards do not read file contents or manufacture fresh observations.
They invalidate reuse on changes; receipts retain their original evidence IDs.
"""
import json
import re
from digital_life.domain.contracts import dumps,sha,ContractError
from digital_life.infrastructure.tools.workspace import safe_path,resource_signature

PATH=re.compile(r'(?<![\w./])((?:\.\.?/|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)')

class ExplorationEvidence:
    def __init__(self,exploration):self.x=exploration;self.s=exploration.s
    def plan(self,verification):
        paths=[m.group(1).rstrip('.') for m in PATH.finditer(verification)]
        if not paths and re.search(r'list_files|列举|列出|目录|\blist\b',verification,re.I) and re.search(r'\bnotes\b',verification):paths=['notes']
        plans=[]
        for relative in paths:
            try:
                path=safe_path(self.s.root/'workspace',relative)
                if path.is_file() and path.stat().st_size<=65536:action={'tool':'read_file','arguments':{'path':relative}}
                elif path.is_dir():action={'tool':'list_files','arguments':{'path':relative}}
                else:continue
            except (OSError,ContractError):continue
            if action not in plans:plans.append(action)
        return plans[:2]
    def signature(self,action):
        if action.get('tool') not in ('read_file','list_files'):return None
        try:
            path=safe_path(self.s.root/'workspace',action['arguments'].get('path') or 'notes');stat=path.stat()
            if action['tool']=='read_file' and (not path.is_file() or stat.st_size>65536):return None
            if action['tool']=='list_files' and not path.is_dir():return None
            return resource_signature(path)
        except (OSError,ContractError,KeyError,TypeError):return None
    def intent_action(self,intent):
        row=self.s.row('action_intents',intent);tool=self.s.row('tool_definitions',row['tool_id'])
        return {'tool':tool['name'],'arguments':json.loads(row['arguments_json'])}
    def key(self,action):return sha(dumps({'tool':action['tool'],'path':action['arguments'].get('path') or 'notes'}))
    def current(self):
        latest={}
        for event in self.x.payloads('exploration.resource_observed'):latest[event['resource_key']]=event
        result=[]
        for event in latest.values():
            if not self.x.readable_refs(event['source_refs']):continue
            if self.signature(event['action'])!=event['signature']:continue
            try:
                receipt=self.s.read_artifact(event['receipt'])
                if not isinstance(receipt,dict) or receipt.get('execution')!='succeeded' or receipt.get('verification')!='pass':continue
                self.s.row('evidence_items',event['evidence'])
            except (ContractError,OSError,ValueError):continue
            result.append(event)
        return result
    def cached(self,action):return next((r for r in reversed(self.current()) if r['resource_key']==self.key(action)),None)
    def publish(self,activity,outcome,before):
        if outcome['state']!='succeeded':return
        result=self.s.row('action_results',outcome['result']);attempt=self.s.row('action_attempts',result['attempt_id'])
        action=self.intent_action(attempt['intent_id']);after=self.signature(action)
        receipt=self.s.read_artifact(outcome['receipt']);evidence=receipt.get('evidence',{})
        if evidence.get('path')!=(action['arguments'].get('path') or 'notes'):return
        observed_signature=evidence.get('resource_signature')
        if after is None or observed_signature!=after:return
        q=self.x.questions().get(self.x.binding(activity)['question_id']);sources=q['evidence_refs'] if q else []
        self.s.event('exploration.resource_observed',payload={'version':1,'resource_key':self.key(action),'action':action,'signature':after,
          'source_refs':sources,'evidence':outcome['evidence'],'receipt':outcome['receipt'],'result':outcome['result'],'activity':activity},activity=activity,lane='result')
    def changed(self,question,plans):
        if question['state'] not in ('resolved','abandoned') or not self.x.readable_refs(question['evidence_refs']):return False
        latest={}
        for record in self.x.payloads('exploration.resource_observed'):latest[record['resource_key']]=record
        for action in plans:
            old=latest.get(self.key(action));current=self.signature(action)
            if old and current is not None and current!=old['signature']:return True
        return False
    def duplicate(self,candidate,plans,questions):
        if not plans:return None
        resources={self.key(a) for a in plans}
        def normalize(value):
            value=PATH.sub('',value.casefold())
            universal=bool(re.search(r'所有|全部|始终|是否都|\b(?:all|always|every)\b',value))
            value=value.replace('是否都','是否')
            value=re.sub(r'所有|全部|始终|\b(?:all|always|every)\b','',value)
            return universal,re.sub(r'[^a-z0-9\u4e00-\u9fff]','',value)
        wording=normalize(candidate['question'])
        for q in questions.values():
            old=q.get('verification_plan') or self.plan(q['verification'])
            if not resources&{self.key(a) for a in old}:continue
            if wording[1] and wording==normalize(q['question']):return q['id']
        return None
