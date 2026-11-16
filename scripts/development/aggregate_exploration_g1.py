#!/usr/bin/env python3
"""Rebuild an AE G1 report from sealed manifests and captured evidence."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from evaluation.exploration.aggregate import aggregate
if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('run_directory'); args=parser.parse_args()
    report=aggregate(args.run_directory)
    print(json.dumps({'run_id':report['run_id'],'gates':report['gates'],'invariants':report['invariants'],'evidence_missing':report['evidence_missing']},ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['gates']['G1']=='pass' else 1)
