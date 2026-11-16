"""Test-only locked panel server. Refuses roots outside the OS temporary folder."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from panel_fixtures import seed_panel
from digital_life.entrypoints.http import create_server

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--ready',required=True);args=parser.parse_args()
    root=Path(args.root).resolve();refs=seed_panel(root);server=create_server(root,0)
    report={'url':'http://127.0.0.1:'+str(server.server_port),'token':(root/'controller.token').read_text().strip(),'refs':refs}
    Path(args.ready).write_text(json.dumps(report))
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
