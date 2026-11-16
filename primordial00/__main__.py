import argparse
import json
import sys
import sqlite3
import time
from .core import Life
from .supervisor import exclusive, once, watch, set_stopped, control

def main():
    parser=argparse.ArgumentParser(description='原初00唤醒：实验性最小生命活动系统')
    parser.add_argument('--data',default='work/primordial00')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('init'); commands.add_parser('status'); commands.add_parser('health')
    commands.add_parser('model-check')
    event=commands.add_parser('event'); event.add_argument('text'); event.add_argument('--key')
    approve=commands.add_parser('approve'); approve.add_argument('activity_id')
    cancel=commands.add_parser('cancel'); cancel.add_argument('activity_id')
    commitment=commands.add_parser('commit'); commitment.add_argument('text'); commitment.add_argument('--after',type=float,default=0)
    commands.add_parser('wake'); commands.add_parser('stop'); commands.add_parser('resume'); commands.add_parser('_tick')
    watcher=commands.add_parser('watch'); watcher.add_argument('--cycles',type=int,default=10); watcher.add_argument('--interval',type=float,default=1)
    args=parser.parse_args()
    try:
        if args.command=='model-check':
            from .models import inspect
            value=inspect(args.data)
        elif args.command=='init':
            life=Life.initialize(args.data); value=life.status(); life.close(); db=control(args.data); db.close()
        elif args.command=='wake': value=once(args.data)
        elif args.command=='watch': value=watch(args.data,args.cycles,args.interval)
        elif args.command in ('stop','resume'):
            set_stopped(args.data,args.command=='stop'); value={'user_stopped':args.command=='stop'}
        else:
            with exclusive(args.data):
                life=Life(args.data)
                try:
                    if args.command=='event': value={'activity_id':life.emit(args.text,args.key)}
                    elif args.command=='approve': life.approve(args.activity_id); value={'approved':args.activity_id}
                    elif args.command=='cancel': life.cancel(args.activity_id); value={'cancelled':args.activity_id}
                    elif args.command=='commit': value={'commitment_id':life.commit(args.text,time.time()+args.after)}
                    elif args.command=='status': value=life.status()
                    elif args.command=='health': value=life.health()
                    elif args.command=='_tick':
                        db=control(args.data); stopped=db.execute('SELECT user_stopped FROM settings WHERE id=1').fetchone()[0]; db.close()
                        from .models import inspect
                        value={'processed':0 if stopped else life.tick(),'health':life.health(),'model':inspect(args.data)}
                finally: life.close()
        print(json.dumps(value,ensure_ascii=False,indent=2)); return 0
    except (ValueError,OSError,RuntimeError,sqlite3.Error) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr); return 1

if __name__=='__main__': sys.exit(main())
