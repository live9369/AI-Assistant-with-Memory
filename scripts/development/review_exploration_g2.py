#!/usr/bin/env python3
"""Export anonymized review packets. Does not invent labels or judge identities."""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from evaluation.exploration.g2.review import export_packets
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_directory');args=p.parse_args();print(json.dumps(export_packets(args.run_directory),ensure_ascii=False,indent=2))
