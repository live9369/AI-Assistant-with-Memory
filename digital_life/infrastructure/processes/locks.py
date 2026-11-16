"""Process exclusion independent of either Runtime implementation."""
import contextlib
import fcntl
from pathlib import Path

@contextlib.contextmanager
def exclusive(root,name='runtime.lock'):
    root=Path(root).resolve()
    if not root.is_dir(): raise ValueError('实例目录不存在')
    with (root/name).open('a') as stream:
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('已有实例进程占用锁')
        try: yield
        finally: fcntl.flock(stream,fcntl.LOCK_UN)

