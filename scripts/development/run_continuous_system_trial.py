"""Explicit native-system acceptance. Never starts a runtime or changes open-mode policy."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.autonomy.continuous_exploration import ContinuousExploration
from digital_life.application.services.memory import Memory
from digital_life.application.monitoring.management import Management
from digital_life.domain.contracts import utc,sha

parser=argparse.ArgumentParser()
parser.add_argument('operation',choices=['prepare','watch'])
parser.add_argument('--data',default='work/primordial00-first-wake')
parser.add_argument('--manifest',default='outputs/inquiry-system-trial/manifest.json')
args=parser.parse_args();manifest=Path(args.manifest).resolve();manifest.parent.mkdir(parents=True,exist_ok=True)
if args.operation=='prepare':
    if manifest.exists():raise RuntimeError('manifest already exists; select a new trial path')
    s=Store(args.data)
    try:
        x=Exploration(s);x.configure(s.config()['controller'],True,6,3,60,900,mode='continuous')
        folder='inquiry-trial-'+uuid.uuid4().hex[:8];root=s.root/'workspace'/folder
        root.mkdir(exist_ok=False)
        contents={'tasks.csv':'id,status,due,muted\nD1,open,2026-11-14T18:00:00+08:00,true\nD2,open,2026-11-14T20:00:00+08:00,false\nD3,done,2026-11-14T17:00:00+08:00,false\nD4,open,,false\nD5,open,2026-11-14T17:30:00+08:00,false\n',
          'rules.txt':'这是合成验收数据，不代表真实承诺。固定判断时间为2026-11-14T18:30:00+08:00。仅当任务未完成、到期时间早于判断时间、且未静音时需要提醒。静音和已完成任务不提醒；缺少到期时间不能确定是否逾期。不要实际发送提醒，只报告判断和依据。\n'}
        files={}
        for name,text in contents.items():(root/name).write_text(text);files[folder+'/'+name]=sha(text)
        description='系统工程验收场景，非真实生活记忆：判断一组任务应否提醒。工作目录中有 '+folder+'/tasks.csv 和 '+folder+'/rules.txt。先记录预期，再观察实际资料；根据两份资料的内容修订判断。不要发送提醒、不要写文件、不要假定规则或任务内容。步骤回答完成不等于这个方向结束，最终应有基于实际来源的判断及无法判断项。'
        with s.tx():
            event=s.event('acceptance.inquiry_case',payload={'description':description,'files':list(files),'synthetic':True},source='system-acceptance',key=folder,lane='control')
            evidence=s.evidence(object_id=event,method='explicit-synthetic-system-trial')
            memory=Memory(s).encode(description,evidence,labels=[('content','synthetic-acceptance-case')],encoding_method='system-acceptance-v1')
            key=sha(folder);direction={'id':key,'title':'从实际任务记录与规则学习怎样做有依据的提醒判断','kind':'explore','next_step':'先明确预期和未知之处，读取 '+folder+'/tasks.csv；下一步根据实际观察选择，不猜测文件内容。','expected_gain':.9,'cost':.2,'evidence_refs':[memory['revision_id']],'parent_id':None,'state':'ready','understanding':'尚未读取任何资料，规则与任务状态未知。','no_progress':0,'steps':0,'due_at':utc(),'created_by':event,'reopen_condition':'','acceptance_case':folder}
            ContinuousExploration(x).emit('direction',direction)
        value={'data':str(s.root),'direction_id':key,'generation':x.config()['generation'],'started_at':utc(),'expires_at':x.config()['expires_at'],'files':files,'synthetic':True,'expected_reminders':['D5'],'expected_unknown':['D4']}
        manifest.write_text(json.dumps(value,ensure_ascii=False,indent=2));print(json.dumps({'manifest':str(manifest),'direction_id':key,'expires_at':value['expires_at']}))
    finally:s.close()
else:
    case=json.loads(manifest.read_text());summary={};seen=set()
    try:
        for _ in range(900):
            s=Store(case['data'])
            try:
                x=Exploration(s);c=ContinuousExploration(x);d=c.directions()[case['direction_id']];m=Management(s)
                bound=x.payloads('exploration.bound');activities={b['activity'] for b in bound if b['generation']==case['generation']}
                for row in m.approvals({'status':'pending','limit':100})['items']:
                    if row['activity_id'] not in activities:continue
                    detail=m.approval(row['id']);path=detail['arguments'].get('path')
                    if detail['tool']!='read_file' or path not in case['files']:
                        summary={'state':'blocked-unapproved-action','activity':row['activity_id'],'tool':detail['tool']};break
                    if sha((s.root/'workspace'/path).read_text())!=case['files'][path]:raise RuntimeError('trial source changed')
                    m.decide(row['id'],{'decision':'approved','expected_revision':detail['revision'],'expected_arguments_hash':detail['arguments_hash'],'reason':'user-authorized system acceptance: read only these two synthetic files'})
                    print(json.dumps({'approved_read':path}),flush=True)
                if summary:break
                inquiries=[v for v in c.values('inquiry') if v['direction_id']==d['id']]
                observations=[v for v in c.values('tool_result') if v['direction_id']==d['id']]
                for v in inquiries:
                    if v['request'] not in seen:seen.add(v['request']);print(json.dumps(v,ensure_ascii=False),flush=True)
                snapshot={'direction':d,'inquiries':inquiries,'tool_results':observations,'observations':[dict(v,receipt_snapshot=s.read_artifact(v['receipt'])) for v in observations if v.get('receipt')],'configuration':x.config()}
                (manifest.parent/'latest.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
                if d['state'] in ('finished','paused'):
                    summary={'state':d['state'],'steps':d['steps'],'real_tool_results':len(observations),'inquiry_records':len(inquiries),'direction':d};break
                if not x.config()['enabled']:summary={'state':'test-window-ended','direction':d};break
            finally:s.close()
            time.sleep(1)
    finally:
        s=Store(case['data'])
        try:Exploration(s).configure(s.config()['controller'],False)
        finally:s.close()
        (manifest.parent/'result.json').write_text(json.dumps(summary or {'state':'observer-ended'},ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
