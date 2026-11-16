#!/usr/bin/env python3
"""Install account tables only on a stopped native instance; never starts inference."""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.application.accounts.accounts import install,enabled,Accounts,public
from digital_life.application.lifecycle.control_plane import Control
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.domain.contracts import Conflict,Forbidden,dumps


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',required=True,type=Path)
    parser.add_argument('--install',action='store_true',help='备份后安装；默认只检查')
    args=parser.parse_args();root=args.data.resolve()
    with dispatch_gate(root):
        store=Store(root)
        try:
            control=Control(root,store.instance_id)
            try:state=control.state()
            finally:control.close()
            schema=store.db.execute('PRAGMA user_version').fetchone()[0]
            from digital_life.application.learning.runtime import qualified_plane_required
            if schema not in (2,3) or qualified_plane_required(store):raise Forbidden('only native schema2/3 is supported')
            installed=enabled(root)
            if installed:
                auth=Accounts(root,store.instance_id)
                try:print(dumps({'installed':True,'root_account':public(auth.row(auth.root_id())),'inference_started':False}))
                finally:auth.close()
                return
            if not args.install:
                print(dumps({'installed':False,'can_install':bool(state['user_stopped'] and not state['active_process_run_id']),'requires_stopped_instance':True,'inference_started':False}));return
            if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('先使用CLI停止当前实例，确认进程已退出后再安装。')
        finally:store.close()
        backup=root/'account-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True,mode=0o700);os.chmod(backup.parent,0o700)
        for name in ('runtime.sqlite','control.sqlite','accounts.sqlite'):
            source=root/name
            if source.exists():
                if source.is_symlink():raise Forbidden('database symlink refused')
                target=backup/name;fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
                src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(str(target))
                try:src.backup(dst)
                finally:dst.close();src.close()
        result=install(root);result['backup_directory']=str(backup);print(dumps(result))

if __name__=='__main__':main()
