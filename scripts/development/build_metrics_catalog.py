"""Extract the named measurement baseline, preserving source and definition text."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
SECTIONS=[
 ('perception-and-cognition.md','### 建议验证指标','M01'),
 ('personality-quantification.md','### 7.3 最小验证指标','M05'),
 ('cognition-quantification.md','## 11 建议指标','M03'),
 ('behavior-probability-model.md','## 13 建议指标','M11'),
 ('memory-quantification.md','## 10','M04'),
 ('supplementary-components-quantification.md','### 2.6 动机验证','M06'),
 ('supplementary-components-quantification.md','### 3.6 内部状态验证','M10'),
 ('supplementary-components-quantification.md','### 4.6 反馈验证','M14'),
 ('supplementary-components-quantification.md','### 5.7 自我的五维验证框架','M15'),
 ('dynamic-goals-values-commitments.md','### 4.4 目标量化指标','M06'),
 ('dynamic-goals-values-commitments.md','### 5.3 价值指标','M06'),
 ('dynamic-goals-values-commitments.md','### 6.2 习惯指标','M07'),
 ('dynamic-goals-values-commitments.md','### 8.3 承诺指标','M09'),
 ('digital-life-health-and-self-maintenance.md','### 9.1 当前状态','M16'),
 ('digital-life-health-and-self-maintenance.md','### 9.2 稳健性','M16'),
 ('digital-life-health-and-self-maintenance.md','### 9.3 韧性','M16'),
 ('digital-life-health-and-self-maintenance.md','### 9.4 维护质量','M16'),
]

def section(path,heading):
    lines=(ROOT/'docs/research'/path).read_text().splitlines(); start=next(i for i,line in enumerate(lines) if line.startswith(heading))
    level=len(lines[start].split(' ')[0]); end=next((i for i in range(start+1,len(lines)) if lines[i].startswith('#') and len(lines[i].split(' ')[0])<=level),len(lines))
    return [(i+1,lines[i]) for i in range(start+1,end)]

def build():
    result=[]
    def add(module,label,description,source,line,reducer='mean'):
        key=module+'.'+hashlib.sha256((source+':'+label).encode()).hexdigest()[:12]
        if any(r['key']==key for r in result): return
        if '校准' in label: reducer='ece'
        elif label in ('Precision@k','Recall@k','MRR','NDCG'): reducer=label.lower().split('@')[0]
        result.append(dict(key=key,module=module,label=label,description=description,source=source,line=line,
            reducer=reducer,unit='score',formula_version='1',requires='independent-evaluation',missing_rule='null-with-reason; never-zero-imputation'))
    for source,heading,module in SECTIONS:
        for line,text in section(source,heading):
            if text.startswith('|'):
                cells=[c.strip() for c in text.strip('|').split('|')]
                if len(cells)<2 or cells[0] in ('指标','维度','阶段') or re.fullmatch(r'[-: ]+',cells[0]): continue
                if module=='M04':
                    for label in re.split('[、，]',cells[1]): add(module,label.strip(),cells[1],source,line)
                else: add(module,cells[0],cells[1],source,line)
            elif text.startswith('- '):
                content=text[2:].strip().rstrip('；。'); label=re.split('[：，]',content)[0]
                add(module,label,content,source,line)
    # Relationship and engineering probes supplement, rather than replace, baseline measurements.
    supplements={
        'M02':['activity_completion_rate','queue_depth','oldest_job_age_seconds'],
        'M04':['memory_revision_integrity','memory_source_coverage'],
        'M08':['relationship_object_accuracy','trust_calibration','relationship_evidence_coverage'],
        'M09':['commitment_fulfillment_rate','commitment_on_time_rate'],
        'M10':['state_freshness','disk_free_bytes','process_max_rss_bytes'],
        'M12':['authorization_coverage','revoked_grants','scope_violation_rate'],
        'M13':['tool_success_rate','tool_unknown_rate','tool_latency_ms'],
        'M14':['learning_gain','old_task_regression','feedback_reversal_recovery'],
        'M15':['identity_anchor_integrity','restore_reconciliation_required'],
        'M16':['storage_integrity','foreign_key_violations','workspace_available'],
        'M17':['model_latency_ms','model_input_tokens','model_output_tokens','artifact_integrity'],
    }
    runtime={'activity_completion_rate','queue_depth','oldest_job_age_seconds','memory_revision_integrity','memory_source_coverage','relationship_evidence_coverage',
      'commitment_fulfillment_rate','commitment_on_time_rate','state_freshness','disk_free_bytes','process_max_rss_bytes','authorization_coverage','revoked_grants',
      'tool_success_rate','tool_unknown_rate','tool_latency_ms','identity_anchor_integrity','restore_reconciliation_required','storage_integrity','foreign_key_violations',
      'workspace_available','model_latency_ms','model_input_tokens','model_output_tokens','artifact_integrity'}
    for module,labels in supplements.items():
        for label in labels:
            add(module,label,label,'engineering-v1',0)
            result[-1]['requires']='runtime' if label in runtime else 'independent-evaluation'
            if label.endswith('_bytes'): result[-1]['unit']='bytes'
            elif label.endswith('_ms'): result[-1]['unit']='milliseconds'
            elif label.endswith('_seconds'): result[-1]['unit']='seconds'
            elif label.endswith('_tokens'): result[-1]['unit']='tokens'
            elif label in ('queue_depth','foreign_key_violations','revoked_grants','restore_reconciliation_required'): result[-1]['unit']='count'
    return result

if __name__=='__main__':
    catalog=build(); target=ROOT/'digital_life/resources/metrics.json'
    target.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    lines=['# 自动采集指标与评测协议字典','',
      '版本 V0.3。目录保留第一阶段明确列出的指标及验证协议，补充工程探针；不把采集能力等同于科学效度。',
      '', '运行探针从数据库及系统观测自动计算；独立评测项由受权评测器提交带来源、案例和数据集版本的观测，随后自动聚合。缺少真值、样本或评测时 value=NULL 并注明原因，不能按零或通过处理。',
      '', 'mean：独立评分／案例比例的算术均值，或显式 before/after 的配对差；ece：十个等宽区间的加权绝对校准误差；precision/recall/mrr/ndcg：按去重后的排名和二元相关真值计算。评分量表、任务集与正负方向应由具体实验条件说明，均值本身不是人格效度或因果证明。',
      '', '| 标识 | 模块 | 指标／协议 | 方式 | 聚合器 | 来源 |', '| --- | --- | --- | --- | --- | --- |']
    for metric in catalog:
        lines.append('| '+ ' | '.join([metric['key'],metric['module'],metric['label'],'运行自动探针' if metric['requires']=='runtime' else '独立评测观测→自动聚合',metric['reducer'],metric['source']+(':'+str(metric['line']) if metric['line'] else '')])+' |')
    (ROOT/'docs/research/phase-3-metric-dictionary.md').write_text('\n'.join(lines)+'\n')
    print('Generated',len(catalog),'metric definitions; no instance accessed.')
