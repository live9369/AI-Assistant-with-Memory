"""Bounded directory-fd file operations. No shell and no database access."""
from contextlib import contextmanager
import ast,difflib,json,os,stat,uuid
from pathlib import Path
from digital_life.domain.contracts import ToolResult,Forbidden,Conflict,ContractError,sha,dumps
from digital_life.domain.project_files import validate,NAMES
LIMIT=524288

def parts(scope,path):
 if not isinstance(path,str) or Path(path).is_absolute() or '..' in Path(path).parts:raise Forbidden('relative project path required')
 ps=tuple(p for p in Path(path).parts if p!='.')
 if any(p.startswith('.') for p in ps):raise Forbidden('hidden paths denied')
 value='/'.join(ps)
 if any(value==x or value.startswith(x+'/') for x in scope['exclude']):raise Forbidden('excluded project path')
 if ps and (ps[-1].endswith(('.sqlite','.sqlite-wal','.sqlite-shm','.pem','.key')) or ps[-1] in ('controller.token','auth.json','credentials.json')):raise Forbidden('private runtime file denied')
 return ps

@contextmanager
def directory(scope,ps):
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
 try:
  for part in Path(scope['root']).parts[1:]:
   nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
  st=os.fstat(fd)
  if [st.st_dev,st.st_ino]!=scope['root_identity']:raise Forbidden('project directory replaced')
  for part in ps:
   nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
  yield fd
 finally:os.close(fd)

def read(fd,name):
 f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
 try:
  st=os.fstat(f)
  if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_size>LIMIT:raise Forbidden('regular single-link file <=512KiB required')
  with os.fdopen(f,'rb',closefd=False) as stream:raw=stream.read(LIMIT+1)
  if len(raw)>LIMIT:raise ContractError('file grew beyond read bound')
  return raw,st
 finally:os.close(f)

def operate(action,scope,operation,journal):
 tool=action['tool'];args=action['arguments'];validate(tool,args)
 if tool not in scope['tools'] or tool not in NAMES:raise Forbidden('project tool not authorized')
 ps=parts(scope,args['path']);evidence={'path':args['path'],'operation':operation}
 if tool=='project_list':
  with directory(scope,ps) as fd:
   entries=[]
   for name in sorted(os.listdir(fd)):
    try:
     parts(scope,'/'.join(ps+(name,)));st=os.stat(name,dir_fd=fd,follow_symlinks=False)
     if not stat.S_ISREG(st.st_mode) and not stat.S_ISDIR(st.st_mode):continue
     entries.append({'name':name,'kind':'directory' if stat.S_ISDIR(st.st_mode) else 'file'})
    except (Forbidden,OSError):continue
    if len(entries)>=200:break
   evidence.update(entries=entries,limit=200)
 elif tool=='project_check':
  if not ps or not ps[-1].endswith('.py'):raise ContractError('python_syntax requires a .py file')
  with directory(scope,ps[:-1]) as fd:raw,_=read(fd,ps[-1])
  try:ast.parse(raw,filename=args['path'])
  except SyntaxError as error:
   evidence.update(check='python_syntax',passed=False,line=error.lineno,message=error.msg,sha256=sha(raw))
   return ToolResult('received','failed','fail',evidence,'Python syntax check failed')
  evidence.update(check='python_syntax',passed=True,sha256=sha(raw),scope='syntax only; no code execution or test suite run')
 elif tool=='project_mkdir':
  if not ps:raise Forbidden('subdirectory path required')
  with directory(scope,ps[:-1]) as fd:
   try:os.mkdir(ps[-1],0o755,dir_fd=fd)
   except FileExistsError:pass
  with directory(scope,ps):pass
  evidence['directory_created_or_present']=True
 elif tool=='project_search':
  matches=[];scanned=0;used=0;visited=0;truncated=False
  def walk(ps):
   nonlocal scanned,used,visited,truncated
   with directory(scope,ps) as fd:
    for name in sorted(os.listdir(fd)):
     visited+=1
     if visited>=2000 or scanned>=500 or used>=4194304 or len(matches)>=60:truncated=True;return
     child=ps+(name,)
     try:
      parts(scope,'/'.join(child));st=os.stat(name,dir_fd=fd,follow_symlinks=False)
      if stat.S_ISDIR(st.st_mode):
       if len(child)<12:walk(child)
      elif stat.S_ISREG(st.st_mode):
       scanned+=1;raw,_=read(fd,name);used+=len(raw)
       for n,line in enumerate(raw.decode('utf-8').splitlines(),1):
        if args['query'] in line:matches.append({'path':'/'.join(child),'line':n,'text':line[:300]})
        if len(matches)>=60:break
     except (Forbidden,OSError,UnicodeError,ContractError):continue
  walk(ps);evidence.update(matches=matches,scanned_files=scanned,truncated=truncated,matching='literal text')
 else:
  if not ps:raise Forbidden('file path required')
  with directory(scope,ps[:-1]) as fd:
   name=ps[-1]
   if tool=='project_read':
    raw,_=read(fd,name);lines=raw.decode('utf-8').splitlines();start=args['start_line']-1
    excerpt='\n'.join(lines[start:start+args['max_lines']]);evidence.update(text=excerpt[:24000],sha256=sha(raw),start_line=start+1,total_lines=len(lines),truncated=len(excerpt)>24000)
   else:
    # The host supplies this private journal directory, never model input.
    folder=Path(journal);folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not operation.isalnum():raise Forbidden('invalid operation identifier')
    receipt=folder/(operation+'.json');key=sha(dumps({'action':action,'scope':scope}))
    if receipt.exists():
     saved=json.loads(receipt.read_text())
     if saved['key']!=key:raise Conflict('operation parameters changed')
     current,_=read(fd,name)
     if saved.get('completed') and sha(current)==saved['after_sha256']:return ToolResult('received','succeeded','pass',saved['evidence'])
    try:before,st=read(fd,name)
    except FileNotFoundError:before=None;st=None
    expected=args['expected_sha256']
    if (before is None and expected) or (before is not None and sha(before)!=expected):raise Conflict('file version changed; read again before writing')
    if tool=='project_edit':
     if before is None:raise Conflict('edit requires an existing file')
     original=before.decode('utf-8')
     if original.count(args['old_text'])!=1:raise Conflict('old_text must match exactly once')
     content=original.replace(args['old_text'],args['new_text'],1)
    else:content=args['text']
    raw=content.encode()
    if len(raw)>LIMIT:raise ContractError('updated file exceeds 512KiB')
    afterhash=sha(raw)
    diff=''.join(difflib.unified_diff((before or b'').decode('utf-8').splitlines(True),content.splitlines(True),fromfile=args['path'],tofile=args['path']))
    evidence.update(before_sha256=sha(before) if before is not None else None,sha256=afterhash,diff=diff[:16000],diff_truncated=len(diff)>16000)
    saved={'key':key,'completed':False,'before_text':before.decode('utf-8') if before is not None else None,'after_sha256':afterhash,'evidence':evidence}
    def save():
     temp=receipt.with_suffix('.tmp');f=os.open(str(temp),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
     with os.fdopen(f,'w') as stream:stream.write(dumps(saved));stream.flush();os.fsync(stream.fileno())
     os.replace(temp,receipt)
    save()
    temp='.life-edit-'+uuid.uuid4().hex
    try:
     f=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,stat.S_IMODE(st.st_mode) if st else 0o644,dir_fd=fd)
     with os.fdopen(f,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
     if before is None:
      os.link(temp,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False);os.unlink(temp,dir_fd=fd)
     else:
      current,now=read(fd,name)
      if sha(current)!=expected or now.st_ino!=st.st_ino:raise Conflict('file changed before replacement')
      os.replace(temp,name,src_dir_fd=fd,dst_dir_fd=fd)
     os.fsync(fd);current,_=read(fd,name)
     if sha(current)!=afterhash:raise Conflict('written file verification failed')
     saved['completed']=True;save()
    finally:
     try:os.unlink(temp,dir_fd=fd)
     except FileNotFoundError:pass
 return ToolResult('received','succeeded','pass',evidence)

def invoke(action,scope,operation,journal):
 try:
  if action['tool'].startswith('project_version_'):
   from digital_life.infrastructure.tools.project_versions import operate as version_operate
   return version_operate(action,scope,operation,journal)
  if action['tool'] in ('project_write','project_edit') and 'project_version_save' in scope['tools']:
   from digital_life.infrastructure.tools.project_versions import Versions
   from dataclasses import replace
   repo=Versions(scope,journal)
   with repo.locked():
    previous=repo.head();cached=Path(journal)/(operation+'.json')
    completed=cached.exists() and json.loads(cached.read_text()).get('completed')
    if not completed:
     try:before=repo.current(action['arguments']['path'])
     except FileNotFoundError:before=None
     expected=action['arguments']['expected_sha256']
     if (before is None and expected) or (before is not None and sha(before)!=expected):raise Conflict('file version changed before checkpoint')
     if before is not None:previous=repo.save([action['arguments']['path']],'Before edit '+action['arguments']['path'],previous,operation+'before')['version']
    result=operate(action,scope,operation,journal)
    if result.execution_state!='succeeded':return result
    after=repo.save([action['arguments']['path']],'Edit '+action['arguments']['path'],previous,operation+'after')
    return replace(result,evidence=dict(result.evidence,version_before=previous,version=after['version']))
  return operate(action,scope,operation,journal)
 except (OSError,ValueError,UnicodeError) as error:
  # Version conflicts and rejected paths are definite failures, not hidden success.
  uncertain=action['tool'] in ('project_version_save','project_version_restore') or action['tool'] in ('project_write','project_edit','project_mkdir') and (action['tool']=='project_mkdir' or (Path(journal)/(operation+'.json')).exists())
  return ToolResult('received','unknown' if uncertain else 'failed','fail',{'operation':operation},type(error).__name__+': '+str(error)[:500])
