"""Offline macOS candidate probe backend. No unsandboxed fallback."""
from dataclasses import dataclass
import math
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
from digital_life.domain.contracts import ContractError, sha

VERSION = 'candidate-seatbelt-v1'
OUTPUT_LIMIT = 131072
FILE_LIMIT = 64 * 1024 * 1024
FD_LIMIT = 256

# Deliberately smaller than an interactive developer-tool sandbox. No user
# directories, networking, shell, Mach service lookup or sandbox extensions.
POLICY = '''(version 1)
(deny default)
(allow process-fork)
(allow process-exec (literal (param "PYTHON")) (literal (param "PYTHON_HELPER")))
(allow process-info* signal (target same-sandbox))
(allow sysctl-read
 (sysctl-name-prefix "hw.") (sysctl-name "kern.osversion")
 (sysctl-name "kern.osrelease") (sysctl-name "kern.ostype")
 (sysctl-name "kern.osproductversion") (sysctl-name "kern.osvariant_status")
 (sysctl-name "kern.secure_kernel") (sysctl-name "kern.hostname")
 (sysctl-name "kern.maxfilesperproc") (sysctl-name "kern.argmax")
 (sysctl-name "kern.usrstack64") (sysctl-name "sysctl.proc_cputype"))
(allow system-mac-syscall (mac-policy-name "vnguard"))
(allow system-mac-syscall (require-all (mac-policy-name "Sandbox") (mac-syscall-number 67)))
(allow file-read* file-map-executable
 (subpath (param "CANDIDATE")) (subpath (param "RUNTIME"))
 (subpath "/System/Library") (subpath "/usr/lib")
 (subpath "/Library/Apple/System/Library") (subpath "/Library/Apple/usr/lib"))
(allow file-read* file-write* (subpath (param "PROBE")))
(allow file-read-metadata
 (literal "/var") (literal "/tmp") (literal "/etc")
 (path-ancestors (param "CANDIDATE")) (path-ancestors (param "PROBE"))
 (path-ancestors (param "RUNTIME")))
(allow file-read* (literal "/") (literal "/dev/urandom") (literal "/dev/random"))
(allow file-read* file-write-data (literal "/dev/null") (literal "/dev/zero"))
'''

# Set hard limits before importing any candidate module. These are inherited by
# ordinary Python workers; they are not aggregate VM memory/process quotas.
BOOTSTRAP = '''import sys,resource
cpu=int(sys.argv[1])
for kind,value in ((resource.RLIMIT_CPU,cpu),(resource.RLIMIT_FSIZE,67108864),(resource.RLIMIT_NOFILE,256),(resource.RLIMIT_CORE,0)):
 resource.setrlimit(kind,(value,value))
body=sys.argv[2]
sys.argv=['candidate-probe']+sys.argv[3:]
exec(compile(body,'<candidate-probe>','exec'),{'__name__':'__main__'})
'''


class SandboxError(ContractError):
    def __init__(self, message, isolation):
        super().__init__(message); self.isolation = isolation


@dataclass
class ProbeResult:
    returncode: int
    output: bytes
    isolation: dict


class CandidateSandbox:
    def __init__(self):
        self.executable = Path('/usr/bin/sandbox-exec')
        if sys.platform != 'darwin' or not self.executable.is_file():
            raise SandboxError('candidate isolation backend unavailable; execution refused',
                               {'backend': VERSION, 'required': True, 'state': 'unavailable'})
        self.python = Path(sys.executable).resolve()
        self.runtime = Path(sys.base_prefix).resolve()
        helper=self.runtime/'Resources/Python.app/Contents/MacOS/Python'
        self.helper=helper.resolve() if helper.is_file() else self.python
        if self.runtime in (Path('/'), Path.home().resolve()) or not self.python.is_relative_to(self.runtime) or not self.helper.is_relative_to(self.runtime):
            raise SandboxError('candidate Python runtime path cannot be safely scoped',
                               {'backend': VERSION, 'required': True, 'state': 'unsupported-runtime'})

    @staticmethod
    def _terminate(process):
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        if process.poll() is None: process.kill()
        process.wait(timeout=5)

    def run(self, candidate, probe, script, arguments, timeout):
        candidate = Path(candidate).resolve(); probe = Path(probe).resolve()
        if not candidate.is_dir() or not probe.is_dir() or candidate == probe or candidate in probe.parents or probe in candidate.parents:
            raise ContractError('disjoint candidate and probe directories required')
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 1 <= timeout <= 60:
            raise ContractError('candidate timeout must be 1..60 seconds')
        policy = probe.parent/'candidate-policy.sb'
        policy.write_text(POLICY); policy.chmod(0o600)
        params = {'PYTHON':str(self.python),'PYTHON_HELPER':str(self.helper),'RUNTIME':str(self.runtime),
                  'CANDIDATE':str(candidate),'PROBE':str(probe)}
        command = [str(self.executable), '-f', str(policy)]
        for key,value in params.items(): command += ['-D',key+'='+value]
        arguments=[str(value.resolve()) if isinstance(value,Path) else str(value) for value in arguments]
        command += [str(self.python),'-I','-S','-B','-c',BOOTSTRAP,str(math.ceil(timeout)),script,*arguments]
        home=probe/'home';temp=probe/'tmp';home.mkdir();temp.mkdir()
        env={'PATH':str(self.python.parent),'HOME':str(home),'TMPDIR':str(temp),
             'USER':'candidate','LOGNAME':'candidate','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'}
        evidence={'backend':VERSION,'required':True,'state':'started','policy_sha256':sha(POLICY),
                  'bootstrap_sha256':sha(BOOTSTRAP),'scope_sha256':sha(json.dumps(params,sort_keys=True)),
                  'network':'deny','candidate':'read-only-copy','writable':'synthetic-probe-only',
                  'limits':{'wall_seconds':timeout,'cpu_seconds_per_process':math.ceil(timeout),
                            'file_bytes':FILE_LIMIT,'open_files':FD_LIMIT,'output_bytes':OUTPUT_LIMIT},
                  'aggregate_memory_limit':False,'aggregate_process_limit':False}
        started=time.monotonic();output=bytearray()
        process=subprocess.Popen(command,cwd=str(probe),env=env,stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT,close_fds=True,start_new_session=True)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
        try:
            while selector.get_map():
                remaining=timeout-(time.monotonic()-started)
                if remaining<=0:
                    evidence['state']='timeout';raise SandboxError('candidate sandbox wall timeout',evidence)
                for key,_ in selector.select(min(.1,remaining)):
                    chunk=os.read(key.fileobj.fileno(),min(16384,OUTPUT_LIMIT-len(output)+1))
                    if not chunk:selector.unregister(key.fileobj);continue
                    output.extend(chunk)
                    if len(output)>OUTPUT_LIMIT:
                        evidence['state']='output-limit';raise SandboxError('candidate sandbox output limit',evidence)
            remaining=timeout-(time.monotonic()-started)
            if remaining<=0:raise SandboxError('candidate sandbox wall timeout',dict(evidence,state='timeout'))
            try:code=process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:raise SandboxError('candidate sandbox wall timeout',dict(evidence,state='timeout')) from None
            evidence.update(state='exited',returncode=code,elapsed_seconds=round(time.monotonic()-started,3))
            return ProbeResult(code,bytes(output),evidence)
        finally:
            selector.close();process.stdout.close()
            # Includes ordinary worker descendants still in this process group.
            self._terminate(process)
