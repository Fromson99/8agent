"""Reserve-first, gold-separated audit of unchanged current v6."""
import json
import os
import sqlite3
import subprocess
from common import ROOT, ADR, DESIGN, RUN, ARMS, read, put, sha, candidate

def tool(*args):
    subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),*map(str,args)],cwd=ROOT,check=True)

def main():
    assert not (DESIGN/'freeze.json').exists()
    old = ROOT/'04_EXPERIMENTS/ADR/ADR-0618-unified-cm-guidance-two-failures/artifacts/design'
    hard = next(c for c in read(old/'inputs.json') if c['case_id']=='cm-003')
    cases = [
        {'case_id':'simple-public',
         'question':'코스닥시장 상장규정 제26조 제1항 제1호에 따라 일반기업(기술성장기업이나 신속이전기업 아님)의 최대주주등은 상장일부터 얼마 동안 의무보유해야 하나?',
         'guides':['정정할게. 상장신청인은 일반기업이 아니라 기술성장기업이야. 대상은 최대주주등 그대로야. 이 조건을 반영해서 의무보유 기간을 다시 판단해.',
                   '방금 정정한 기술성장기업과 최대주주등 조건을 유지해. 코스닥시장 상장규정 제26조 제1항 제1호 원문을 대조해서 기간과 기산점을 명확히 다시 답해. 다른 예외에 관한 새 사실은 추가하지 마.'],
         'reuse_question':'코스닥시장 상장규정 제26조 제1항 제1호에 따라 기술성장기업의 최대주주등은 상장일부터 얼마 동안 의무보유해야 하나?',
         'changed_question':'코스닥시장 상장규정 제26조 제1항 제1호에 따라 일반기업(기술성장기업이나 신속이전기업 아님)의 최대주주등은 상장일부터 얼마 동안 의무보유해야 하나? 이전에 저장한 기술성장기업 조건과는 다른 사건이야.'},
        {**hard,'reuse_question':hard['question'],
         'changed_question':'코스닥시장 상장규정 제26조 제1항 제3호와 제4호의 신규상장 의무보유를 검토해줘. 이번 투자자는 벤처금융이고 모집이나 매출이 아닌 제3자배정으로 취득했으며 상장예비심사 신청일 기준 투자기간이 3년이야. 취득은 상장예비심사 신청일 3년 전이야. 이 새로운 조건을 원문과 대조해줘. 이전 사건과 조건이 달라.'}
    ]
    for case in cases:
        case['confirmation']='이 답과 현재 조건을 최종 경험으로 확정해서 기억해줘.'
        case['explicit_reuse']='이전에 확정해서 저장한 경험을 활용해서 답해줘. '+case['reuse_question']
    put(DESIGN/'inputs.json',cases)
    gold = {'cm-003':read(old/'gold.json')['cm-003']}
    original=next(x for x in gold['cm-003']['source_originals'] if x['document_name']=='코스닥시장 상장규정')
    gold['simple-public']={'decisive_source_ids':[original['id']], 'source_originals':[original],
        'rubric':'최초 일반기업 최대주주등: 상장일부터 6개월. 정정 후 기술성장기업 최대주주등: 상장일부터 1년. 새 대화 기술성장기업도 1년이며 조건 변경 일반기업은 6개월. 제공되지 않은 특별한 면제·연장 사유를 단정하지 않는다.'}
    gold['cm-003']['rubric']=gold['cm-003']['source_supported_rubric']
    put(DESIGN/'gold.json',gold)
    b=read(old/'source-binding.json');generation=ROOT/b['generation']
    b.update(policy_sha256=sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),
        source_authorization_sha256=sha(ROOT/'08_DEPLOYMENT/CONFIG/legal-source-export.json'),
        source_manifest_sha256=sha(generation/'manifest.json'),
        basis='User requested current v6 multiturn/experience performance experiment; public synthetic scenario and historical public CM question only.')
    assert sha(generation/'store.sqlite') == b['source_store_sha256']
    grant=read(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
    assert set(b['scope_document_ids'])==set(grant['public_document_ids'])
    export=read(ROOT/'08_DEPLOYMENT/CONFIG/legal-source-export.json')
    assert export['enabled'] and any(set(grant['public_document_ids'])<=set(x['document_version_ids']) for x in export['bindings'])
    with sqlite3.connect('file:'+str(generation/'store.sqlite')+'?mode=ro',uri=True) as db:
        provenance=dict(db.execute('SELECT document_id,source_artifact_sha256 FROM document'))
    for row in b['document_provenance']:
        assert not row['raw_relative_path'].startswith('internal/')
        assert sha(ROOT/'01_DATA/RAW'/row['raw_relative_path'])==row['raw_sha256']
        assert provenance[row['document_id']]==row['source_artifact_sha256']
    put(DESIGN/'source-binding.json',b)
    coordinates=read(old/'source-coordinates.json')
    put(DESIGN/'source-coordinates.json',coordinates)
    m=read(ADR/'실험/manifest.json')
    m['lineage']['hypothesis_delta']='Fresh measurement of frozen current working v6, natural-language corrections and confirmed experience reuse; no product implementation changed.'
    m['design'].update(hypothesis='Natural-language user corrections produce current conditional answers; explicit confirmation persists a bound experience across process restart and reuses it on equivalent new questions faster without stale-condition reuse.',
        primary_metric='Per-case correction/state correctness, persistent experience/wiki identity, automatic and explicit new-session reuse, same-condition latency/call reduction versus fresh no-experience control.',
        success_criteria='Both cases: final guided response completes and matches stored-source rubric; confirmation STORED; both wikis agree on ID/revision/judgment refs; process restart preserves experience; automatic and explicit equivalent requests REUSED; changed-condition request investigates; reuse has >=20% lower latency and fewer physical model calls than fresh same-question control, with no quality regression.',
        failure_criteria='Any guided execution/grounding failure, wrong condition, missing persistence, ordinary repeated question fails to reuse, stale conditions reused, or no paired speed/call improvement.',
        criteria_frozen_before_run=True,repeats=1,
        budget={'native_model_attempts_per_request':40,'product_physical_calls_max_per_process':280,'offline_judge_calls_max':32,'fallback':False,'transport_retries':0},
        order='simple-public then cm-003; baseline original first, guided forks exact completed initial store; fresh control uses different identity/runtime without experience; restart before reuse; ordinary question then explicit request then changed-condition request.',
        confirmation_rule='Experiment-authored explicit confirmation for measurement only, never expert legal approval; attempted after final completed READY answer even if offline score later fails.',
        optional_failures='If final guided answer fails, confirmation/reuse are reported blocked with zero invented completions. Independent fresh same-question control still executes.',
        scope='Stored approved public corpus, explicit host-authenticated synthetic principal. No GENOS claim or active MAIN change.')
    for arm in m['design']['arms']:
        arm['role']='candidate'  # Both unchanged code copies use the isolation registry.
        arm['changes']='Unchanged frozen current v6 original question; independent final-condition fresh control' if arm['id']=='baseline' else 'Same initial store and code; two frozen natural-language corrections, confirmation and cross-session reuse probes'
        arm['controls']='Same current v6/source generation/Qwen3.8 Parasail FP8 none policy/native budget; no answer injection or resolver override.'
    stages=[{'stage_id':s,'kind':k,'parent_stage_ids':[] if i==0 else [prev]} for i,(s,k,prev) in enumerate([('source','source',None),('discovered','retrieve','source'),('read','filter','discovered'),('selected','select','read'),('present','present','selected')])]
    m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ARMS}
    m['runs'][0].update(selection_rule='One explicit simple numeric condition correction and one known difficult CM003 source/exception question; frozen before results; no sample replacement.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
    m['dataset'].update(name='current-v6-multiturn-two-public-cases',version='v1',frozen_source=str((DESIGN/'inputs.json').relative_to(ROOT)),sha256=sha(DESIGN/'inputs.json'),legal_version_checked=True,reference_version_checked=True,current_law_verified=False,caveat='Stored public originals; no present-law advice. CM003 historical reference agreement is not definitive legal correctness.')
    m['retrieval_accounting'].update(changed=True,corpus_total=len({(v['doc_id'],v['node']) for v in coordinates.values()}),not_applicable_reason=None)
    m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-stage-ledger.json').relative_to(ROOT)),not_applicable_reason=None)
    m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':b['model'],'repeats':1,'temperature':0},{'role':'source-supported-offline-judge','class':'offline_evaluator','model':b['model'],'repeats':2,'temperature':0}]
    put(ADR/'실험/manifest.json',m);put(DESIGN/'pre-snapshot-design.json',m)
    config=read(ROOT/'00_SYSTEM/PIPELINE.json');paths={'00_SYSTEM/PIPELINE.json','00_SYSTEM/WORKSPACE.json','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'}
    for node in config['profiles']['legal-agent-rag-v6']['nodes']:
        manifest=config['engines'][node['engine']]['manifest'];paths.add(manifest);paths.update(read(ROOT/manifest)['files'])
    for directory in ('00_SYSTEM/SCHEMAS','00_SYSTEM/MIGRATION','00_SYSTEM/LEGAL_AGENT'):
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT/directory).rglob('*.json'))
    for base in ('02_BACKEND/semantic_runtime','02_BACKEND/PIPELINE','02_BACKEND/lawrag'):
        for directory,dirs,files in os.walk(ROOT/base):
            dirs[:]=[d for d in dirs if d not in ('candidates','__pycache__','.git')]
            paths.update(str((Path(directory)/f).relative_to(ROOT)) for f in files if f.endswith(('.py','.sql')))
    for engine in config['engines'].values():paths.add(engine['manifest'])
    for key in ('origin_projections','alias_projections'):
        paths.update(x['path'] for x in config['profiles']['legal-agent-rag-v6']['nodes'][0]['parameters']['term_agent'][key])
    paths.add('06_TOOLS/ACTIVE_TOOLS.json')
    put(DESIGN/'snapshot-source-files.json',sorted(paths))
    for arm in ARMS:
        args=['adr_candidate.py','snapshot','--adr',ADR,'--candidate-id','v6-'+arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
        for path in sorted(paths):args+=['--source',path]
        tool(*args)
    print(json.dumps({'prepared':True,'cases':len(cases),'public_docs':len(b['scope_document_ids']),'files_per_snapshot':len(paths),'model_calls':0}))

from pathlib import Path
if __name__=='__main__':main()
