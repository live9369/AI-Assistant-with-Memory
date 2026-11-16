"""Reentrant thread/process gate for control commits and synchronous dispatch.

The gate is held through the callback, not merely a preflight check. This makes
callback entry precede any competing stop commit, or the stop commit precede the
final preflight and reject it. Callbacks may stop themselves reentrantly; already
entered calls remain in flight. No SQLite write transaction is held across I/O.
"""
from contextlib import contextmanager
from functools import wraps
import fcntl
import os
from pathlib import Path
import threading

_registry={}
_registry_lock=threading.Lock()

def _after_fork():
    global _registry,_registry_lock
    for entry in _registry.values():
        if entry.fd is not None: os.close(entry.fd)
    _registry={}; _registry_lock=threading.Lock()

os.register_at_fork(after_in_child=_after_fork)

class _Entry:
    def __init__(self):
        self.lock=threading.RLock(); self.depth=0; self.fd=None; self.owner=None

@contextmanager
def dispatch_gate(root):
    root=Path(root).resolve()
    if not root.is_dir(): raise ValueError('dispatch instance directory missing')
    key=str(root)
    with _registry_lock: entry=_registry.setdefault(key,_Entry())
    with entry.lock:
        if entry.depth==0:
            fd=os.open(str(root/'dispatch.lock'),os.O_CREAT|os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
            try: fcntl.flock(fd,fcntl.LOCK_EX)
            except BaseException: os.close(fd); raise
            entry.fd=fd; entry.owner=threading.get_ident()
        entry.depth+=1
        try: yield
        finally:
            entry.depth-=1
            if entry.depth==0:
                fd=entry.fd; entry.fd=None; entry.owner=None
                try: fcntl.flock(fd,fcntl.LOCK_UN)
                finally: os.close(fd)

def coordinated(method):
    """Acquire gate before any transaction in a state-changing control method."""
    @wraps(method)
    def wrapped(self,*args,**kwargs):
        root=self.root if hasattr(self,'root') else self.s.root
        store=getattr(self,'s',None)
        if store is not None and store.depth:
            with _registry_lock: entry=_registry.get(str(Path(root).resolve()))
            if entry is None or entry.owner!=threading.get_ident(): raise ValueError('dispatch gate must precede runtime transaction')
        with dispatch_gate(root): return method(self,*args,**kwargs)
    return wrapped
