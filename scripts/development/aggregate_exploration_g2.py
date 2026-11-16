#!/usr/bin/env python3
"""Aggregate recorded G2 evidence with supplied review labels; never invent labels."""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from evaluation.exploration.g2.aggregate import aggregate
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_directory');p.add_argument('--review',action='append',default=[]);p.add_argument('--adjudication');args=p.parse_args()
    r=aggregate(args.run_directory,args.review,args.adjudication)
    print(json.dumps({'run_id':r['run_id'],'gates':r['gates'],'blockers':r['quality_blockers']},ensure_ascii=False,indent=2))
    raise SystemExit(0 if r['gates']['G2']=='pass' else 2)
