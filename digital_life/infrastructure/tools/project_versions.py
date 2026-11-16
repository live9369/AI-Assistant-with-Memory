"""Private Git object store for authorized text-file versions; no Git shell surface."""
import difflib,fcntl,json,os,re,shutil,subprocess,time
from contextlib import contextmanager
from pathlib import Path
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,ToolResult,sha,dumps
from digital_life.infrastructure.tools.project_files import parts,directory,read

class Versions:
 def __init__(self,scope,journal):
  self.scope=scope;self.journal=Path(journal);base=self.journal.parent/'project-versions'
  if base.is_symlink():raise Forbidden('version store symlink denied')
  base.mkdir(mode=0o700,parents=True,exist_ok=True)
  self.repo=base/(sha(scope['root'])+'.git')
  if self.repo.is_symlink():raise Forbidden('version repository symlink denied')
  self.git=shutil.which('git')
  if not self.git:raise ContractError('Git executable unavailable')
  self.env={'PATH':'/usr/bin:/bin','HOME':str(base),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','GIT_NO_REPLACE_OBJECTS':'1','GIT_AUTHOR_NAME':'primordial00','GIT_AUTHOR_EMAIL':'digital-life@localhost','GIT_COMMITTER_NAME':'primordial00','GIT_COMMITTER_EMAIL':'digital-life@localhost','LC_ALL':'C'}
  self.lock_path=base/(sha(scope['root'])+'.lock')
 @contextmanager
 def locked(self):
  fd=os.open(str(self.lock_path),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX)
   if not self.repo.exists():
    p=subprocess.run([self.git,'init','--bare','--template=',str(self.repo)],env=self.env,capture_output=True,timeout=10)
    if p.returncode:raise ContractError('version repository initialization failed')
   yield self
  finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 def run(self,*args,body=None,optional=False):
  command=[self.git,'--git-dir='+str(self.repo),'-c','core.hooksPath=/dev/null','-c','core.attributesFile=/dev/null','-c','gc.auto=0',*args]
  p=subprocess.run(command,input=body,env=self.env,capture_output=True,timeout=15)
  if len(p.stdout)>20971520:raise ContractError('version output exceeds bound')
  if p.returncode:
   if optional:return None
   raise ContractError('Git version operation failed: '+p.stderr.decode('utf-8',errors='replace')[:200])
  return p.stdout
 def head(self):
  value=self.run('rev-parse','--verify','refs/heads/main',optional=True)
  return value.decode().strip() if value else ''
 def revision(self,value):
  if not re.fullmatch('[a-f0-9]{40}',value):raise ContractError('complete Git version id required')
  head=self.head()
  if not head or self.run('merge-base','--is-ancestor',value,head,optional=True) is None:raise Forbidden('version is not in this project history')
  return value
 def tree(self,version):
  if not version:return {}
  rows=self.run('ls-tree','-rz','--full-tree',version);values={}
  for row in rows.split(b'\0'):
   if not row:continue
   metadata,path=row.split(b'\t',1);mode,kind,oid=metadata.decode().split()
   if kind!='blob' or mode not in ('100644','100755'):raise Forbidden('unsupported version object')
   values[path.decode('utf-8')]=(mode,oid)
  if len(values)>2000:raise ContractError('version file count exceeds bound')
  return values
 def content(self,tree,path):
  parts(self.scope,path)
  if path not in tree:raise ContractError('file does not exist in selected version; deletion restore is not supported')
  raw=self.run('cat-file','blob',tree[path][1])
  if len(raw)>524288:raise ContractError('version file too large')
  raw.decode('utf-8');return raw
 def current(self,path):
  ps=parts(self.scope,path)
  if not ps:raise Forbidden('file path required')
  with directory(self.scope,ps[:-1]) as fd:return read(fd,ps[-1])[0]
 def make_tree(self,flat):
  nested={}
  for path,value in flat.items():
   target=nested;ps=path.split('/')
   for part in ps[:-1]:
    target=target.setdefault(part,{})
    if not isinstance(target,dict):raise Conflict('file/directory version collision')
   if isinstance(target.get(ps[-1]),dict):raise Conflict('file/directory version collision')
   target[ps[-1]]=value
  def build(tree):
   rows=[]
   for name,value in sorted(tree.items()):
    mode,oid=('040000',build(value)) if isinstance(value,dict) else value
    kind='tree' if mode=='040000' else 'blob'
    rows.append(f'{mode} {kind} {oid}\t'.encode()+name.encode()+b'\0')
   return self.run('mktree','-z',body=b''.join(rows)).decode().strip()
  return build(nested)
 def save_release(self,files,message,operation):
  """Host-only verified release material; does not expand model file-read limits."""
  head=self.head();tree=self.tree(head);total=0
  for path,raw in files:
   name=str(path);parts(self.scope,name);total+=len(raw)
   if total>20000000:raise ContractError('release version exceeds 20MB')
   tree[name]=('100644',self.run('hash-object','-w','--stdin',body=raw).decode().strip())
  if len(tree)>2000:raise ContractError('release version exceeds file bound')
  root=self.make_tree(tree)
  if head and root==self.run('rev-parse',head+'^{tree}').decode().strip():return head
  args=['commit-tree',root]+(['-p',head] if head else [])
  commit=self.run(*args,body=(message+'\n\nOperation: '+operation+'\n').encode()).decode().strip()
  self.run('update-ref','refs/heads/main',commit,head or '0'*40);return commit
 def save(self,paths,message,expected_head,operation):
  head=self.head()
  # Exact retry witness survives a lost worker result; never execute twice.
  if head:
   log=self.run('show','-s','--format=%B',head).decode()
   if log.endswith('\nOperation: '+operation+'\n\n') or ('\nOperation: '+operation+'\n') in log:
    return {'version':head,'previous_version':expected_head,'reused':True}
  if head!=expected_head:raise Conflict('version head changed; inspect status before saving')
  tree=self.tree(head)
  for path in paths:
   raw=self.current(path);raw.decode('utf-8')
   blob=self.run('hash-object','-w','--stdin',body=raw).decode().strip();tree[path]=('100644',blob)
  root=self.make_tree(tree)
  if head and root==self.run('rev-parse',head+'^{tree}').decode().strip():return {'version':head,'previous_version':head,'unchanged':True}
  args=['commit-tree',root]
  if head:args+=['-p',head]
  commit=self.run(*args,body=(message+'\n\nOperation: '+operation+'\n').encode()).decode().strip()
  self.run('update-ref','refs/heads/main',commit,head or '0'*40)
  return {'version':commit,'previous_version':head,'paths':paths,'message':message}

def operate(action,scope,operation,journal):
 tool=action['tool'];args=action['arguments']
 if tool not in scope['tools']:raise Forbidden('version tool not authorized')
 repo=Versions(scope,journal)
 with repo.locked():
  head=repo.head();evidence={'operation':operation,'head':head}
  if tool=='project_version_log':
   history=[]
   if head:
    commits=repo.run('rev-list','--max-count='+str(args['limit']),head).decode().splitlines()
    for commit in commits:
     fields=repo.run('show','-s','--format=%ct%n%B',commit).decode().split('\n',1);history.append({'version':commit,'timestamp':int(fields[0]),'message':fields[1].strip()[:1000]})
   evidence['history']=history
  elif tool=='project_version_save':evidence.update(repo.save(args['paths'],args['message'],args['expected_head'],operation))
  elif tool=='project_version_status':
   tree=repo.tree(head);changes=[]
   for path in args['paths']:
    parts(scope,path)
    try:raw=repo.current(path);current=sha(raw)
    except FileNotFoundError:raw=None;current=None
    saved=repo.content(tree,path) if path in tree else None
    changes.append({'path':path,'current_sha256':current,'version_sha256':sha(saved) if saved is not None else None,'state':'untracked' if path not in tree else 'deleted' if raw is None else 'unchanged' if raw==saved else 'modified'})
   evidence['files']=changes
  elif tool=='project_version_diff':
   version=repo.revision(args['version']);saved=repo.content(repo.tree(version),args['path']);current=repo.current(args['path'])
   diff=''.join(difflib.unified_diff(saved.decode().splitlines(True),current.decode().splitlines(True),fromfile=version+':'+args['path'],tofile='working:'+args['path']))
   evidence.update(version=version,diff=diff[:18000],truncated=len(diff)>18000)
  elif tool=='project_version_restore':
   if 'project_write' not in scope['tools']:raise Forbidden('restore also requires project_write permission')
   if head!=args['expected_head']:raise Conflict('version head changed before restore')
   version=repo.revision(args['version']);raw=repo.content(repo.tree(version),args['path'])
   from digital_life.infrastructure.tools.project_files import operate as file_operate
   if len(raw)>20000:raise ContractError('restore currently supports text files <=20000 bytes')
   # Save the present file before replacing it; do not erase uncommitted work.
   before=repo.save([args['path']],'Before restore '+args['path'],head,operation+'before')
   result=file_operate({'tool':'project_write','arguments':{'path':args['path'],'text':raw.decode(),'expected_sha256':args['expected_sha256']}},scope,operation,journal)
   if result.execution_state!='succeeded':return result
   after=repo.save([args['path']],args['message'],before['version'],operation+'after')
   evidence.update(result.evidence,restored_from=version,**after)
  else:raise ContractError('unknown version tool')
  return ToolResult('received','succeeded','pass',evidence)
