"""One bounded tool invocation, JSON stdin/stdout, no LLM and no database."""
from dataclasses import asdict
import json
import sys
from digital_life.infrastructure.tools.workspace import registry

def main():
    raw=sys.stdin.read(65537)
    if len(raw)>65536: raise ValueError('request too large')
    request=json.loads(raw)
    if 'project_scope' in request:
        from digital_life.infrastructure.tools.project_files import invoke
        result=invoke(request['action'],request['project_scope'],request['operation'],request['journal'])
    else:result=registry().invoke(request['action'],request['root'],request['operation'])
    print(json.dumps(asdict(result),ensure_ascii=False)); return 0

if __name__=='__main__': sys.exit(main())
