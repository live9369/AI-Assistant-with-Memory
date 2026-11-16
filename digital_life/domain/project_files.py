"""Small provider-independent project-file action contracts."""
import re
from digital_life.domain.contracts import ContractError,text
STRING={'type':'string'}
PROPERTIES={
 'project_version_status':{'paths':{'type':'array','items':STRING,'minItems':1,'maxItems':50}},
 'project_version_log':{'limit':{'type':'integer','minimum':1,'maximum':20}},
 'project_version_save':{'paths':{'type':'array','items':STRING,'minItems':1,'maxItems':50},'message':STRING,'expected_head':STRING},
 'project_version_diff':{'path':STRING,'version':STRING},
 'project_version_restore':{'path':STRING,'version':STRING,'expected_sha256':STRING,'expected_head':STRING,'message':STRING},
 'project_list':{'path':STRING},
 'project_check':{'path':STRING,'check':{'type':'string','enum':['python_syntax']}},
 'project_mkdir':{'path':STRING},
 'project_edit':{'path':STRING,'old_text':STRING,'new_text':STRING,'expected_sha256':STRING},
 'project_read':{'path':STRING,'start_line':{'type':'integer','minimum':1},'max_lines':{'type':'integer','minimum':1,'maximum':200}},
 'project_search':{'path':STRING,'query':STRING},
 'project_write':{'path':STRING,'text':STRING,'expected_sha256':STRING},
}
NAMES=tuple(PROPERTIES)
def validate(tool,args):
 if not isinstance(args,dict) or set(args)!=set(PROPERTIES[tool]):raise ContractError('invalid project tool arguments')
 if 'path' in args:text(args['path'],1000)
 if 'paths' in args:
  if not isinstance(args['paths'],list) or not 1<=len(args['paths'])<=50 or len(set(args['paths']))!=len(args['paths']):raise ContractError('1..50 unique file paths required')
  for path in args['paths']:text(path,1000)
 if 'message' in args:text(args['message'],1000)
 if 'version' in args and (not isinstance(args['version'],str) or not re.fullmatch('[a-f0-9]{40}',args['version'])):raise ContractError('complete version id required')
 if 'expected_head' in args and (not isinstance(args['expected_head'],str) or not re.fullmatch('(?:[a-f0-9]{40})?',args['expected_head'])):raise ContractError('expected_head required')
 if tool=='project_version_log' and (type(args['limit']) is not int or not 1<=args['limit']<=20):raise ContractError('history limit 1..20 required')
 if tool=='project_version_restore' and (not isinstance(args['expected_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',args['expected_sha256'])):raise ContractError('restore requires current file sha256')
 if tool=='project_read':
  if type(args['start_line']) is not int or args['start_line']<1 or type(args['max_lines']) is not int or not 1<=args['max_lines']<=200:raise ContractError('invalid line range')
 if tool=='project_search':text(args['query'],200)
 if tool=='project_check' and args['check']!='python_syntax':raise ContractError('unsupported named check')
 if tool in ('project_write','project_edit'):
  for field in (('text',) if tool=='project_write' else ('old_text','new_text')):
   if not isinstance(args[field],str) or len(args[field].encode())>20000:raise ContractError('project text argument exceeds 20000 bytes')
  if tool=='project_edit' and not args['old_text']:raise ContractError('old_text must not be empty')
  if not isinstance(args['expected_sha256'],str) or not re.fullmatch(r'(?:[a-f0-9]{64})?',args['expected_sha256']):raise ContractError('expected_sha256 required; empty only for new files')
