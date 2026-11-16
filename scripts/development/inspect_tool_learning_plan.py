"""Read-only IM readiness; no task, model, service or instance execution."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from digital_life.application.learning.plan import inspect

if __name__=='__main__':
    result=inspect(ROOT)
    print(json.dumps({'ready':result['ready'],'authorization_blocked':result['authorization_blocked'],
        'tasks':[{'id':t['id'],'status':t['status'],'title':t['title']} for t in result['tasks']],
        'historical_code_drift':result['historical_code_drift'],'execution_performed':False},ensure_ascii=False,indent=2))
