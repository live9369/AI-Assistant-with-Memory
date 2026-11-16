"""Explicit local GGUF service owner. No downloads, auto-installs or home writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from digital_life.domain.contracts import ContractError,Forbidden
from digital_life.infrastructure.llm.inference import probe

def file_hash(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): value.update(block)
    return value.hexdigest()

class ModelService:
    def __init__(self,assets,log_directory,port=18081):
        self.assets=Path(assets).resolve(); self.logs=Path(log_directory).resolve(); self.port=port; self.process=None
        if type(port) is not int or not 1<=port<=65535: raise ContractError('invalid model service port')
    def start(self,timeout=45):
        if self.process: raise ContractError('service already owned')
        manifest=json.loads(self.assets.read_text()); root=self.assets.parent
        for name,digest in manifest['files'].items():
            path=root/name
            if root not in path.resolve().parents or file_hash(path)!=digest: raise ContractError('local model asset integrity failed: '+name)
            if path.is_symlink() and manifest.get('links',{}).get(name)!=os.readlink(path): raise ContractError('unverified local model asset link: '+name)
        binary=root/manifest['binary']; model=root/manifest['model']
        if manifest['binary'] not in manifest['files'] or manifest['model'] not in manifest['files']: raise ContractError('unverified model executable or weights')
        self.logs.mkdir(parents=True,exist_ok=True)
        self.config={'backend':'llamacpp','model':manifest['alias'],'base_url':'http://127.0.0.1:'+str(self.port),'timeout':120,'max_output_tokens':512,'context_window':8192}
        log=(self.logs/'local-model.log').open('ab')
        try:
            self.process=subprocess.Popen([str(binary),'--model',str(model),'--alias',manifest['alias'],'--host','127.0.0.1','--port',str(self.port),
              '--gpu-layers','0','--threads','2','--ctx-size','8192','--parallel','1','--offline','--no-webui','--chat-template-kwargs','{"enable_thinking":false}'],
              cwd=str(self.logs),stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        finally: log.close()
        deadline=time.monotonic()+timeout
        try:
            while time.monotonic()<deadline:
                if self.process.poll() is not None: raise ContractError('local model process exited; inspect local-model.log')
                try: probe(self.config); return dict(self.config)
                except (OSError,ValueError,ContractError): time.sleep(0.1)
            raise ContractError('local model readiness timed out')
        except BaseException: self.stop(); raise
    def stop(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=5)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
            self.process=None
