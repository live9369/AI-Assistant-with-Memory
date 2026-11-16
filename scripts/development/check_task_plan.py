"""Check development gates; never accesses or starts a life instance."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.application.monitoring.task_plan import inspect_plan
if __name__=='__main__':print(json.dumps(inspect_plan(Path(__file__).resolve().parents[2]),ensure_ascii=False,indent=2))
