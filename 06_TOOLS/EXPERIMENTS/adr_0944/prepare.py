"""Freeze a fresh working1.18 vs candidate1.19 paired live comparison."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess
import sys

R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0944-research-decision-live-cost';D=A/'artifacts/design'
D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
P=R/'04_EXPERIMENTS/ADR/ADR-0943-research-decision-admission/artifacts/design'
parent=read(P/'fixed-binding.json')
names=parent['serving_files']
before=read(P/'working-before.json')['files']
assert all(sha(R/n)==h for n,h in before.items())
assert all(sha(R/parent['code_root']/n)==h for n,h in names.items())
put(D/'baseline.json',read(P/'baseline.json'));put(D/'working-before.json',before)
source=R/'04_EXPERIMENTS/ADR/ADR-0940-research-continuity-prompt-cost/artifacts/design'
put(D/'cases.json',read(source/'cases.json'))
criteria=read(source/'criteria.json')
criteria.update(
    hypothesis='Explicit need resolution and state-based review admission repair deterministic omissions, with bounded discovery-to-read selection and measured prompt overhead.',
    controls='Fresh working1.18 and frozen candidate1.19; same MAIN90 data/search/model/grant/profile. Qwen3.8 Parasail FP8, reasoning none, no fallback. Existing max40 calls/request and 1800sec deadline preserved.',
    primary_metric='Actual provider tokens/calls and identical-state schema/message increment from the explicit need_resolution field, with retained-original and consumer checks.',
    selection='Two known public topics, one request per arm/case. ModifiedRP, baselineRP, baselineLeverage, modifiedLeverage. No adaptive rerun.',
    success=[
        'No source/hash/ACL/state/budget violation; already read sources survive bounded or failed investigation.',
        'New transition metadata/schema fraction <=10% median and <=20% maximum of captured message+schema characters.',
        'Report actual input tokens and calls per case; >125% of baseline is a material cost increase and blocks an unqualified claim of no cost regression.',
        'Inspect exact acquired/returned/cited roots and parent re-review outcomes, without grading absence or model opinion as legal truth.',
    ],
    failure=['Any source/hash/ACL/state/budget regression','Resource guard stop','Transition metadata threshold breach'],
    limitations=[
        'Known-case probe, not holdout and not legal accuracy certification.',
        'Extra review of a changed attempt or reading newly discovered originals can legitimately cost more. No threshold is changed after observing results.',
        'Token total >125% requires a further decision before promotion; technical unit-test success alone does not waive cost regression.',
        'No risk_cm original/annotation/gold input; only existing approved workflow document grant.',
    ])
put(D/'criteria.json',criteria)
put(D/'schedule.json',[{'arm':a,'case_id':c} for a,c in
    [('modified','rp-bond-scope'),('baseline','rp-bond-scope'),('baseline','leverage'),('modified','leverage')]])
for name in ('live.py','audit.py','run_sequence.py','deadline.py','archive.py','report.py',
             'coverage_audit.py','navigation_audit.py','packet_audit.py','citation_audit.py','scope_audit.py'):
    s=(R/'06_TOOLS/EXPERIMENTS/adr_0940'/name).read_text()
    s=s.replace('ADR-0940-research-continuity-prompt-cost','ADR-0944-research-decision-live-cost').replace('adr0940-','adr0944-').replace("'ADR-0940'","'ADR-0944'")
    s=s.replace('Per-call normalized JSON character reduction by removing new continuity fields and reverting old task history shape. Same captured sources/decisions; excludes static instruction change. Per-call provider usage is the authoritative token count.',
                'Per-call same-payload schema/message character increment of need_resolution; static instruction delta separate. Actual provider usage is the authoritative token count.')
    (T/name).write_text(s)
m=read(A/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],
    success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[
    {'id':'baseline','role':'candidate','derived_from':[],'changes':'Frozen current working1.18 control snapshot; baseline in paired analysis','controls':criteria['controls']},
    {'id':'modified','role':'candidate','derived_from':['ADR-0943-experiment-v1/fixed'],'changes':'Unchanged completed candidate1.19','controls':criteria['controls']}]
m['runs'][0].update(arm_ids=['baseline','modified'],selection_rule=criteria['selection'],
    artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':160}]
m['dataset'].update(name='two-known-public-topics-decision-transitions',version='20261020-r1',
    frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},
        {'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},
        {'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','modified')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason='No approved legal gold; original-source transitions measured.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
    artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
candidates=[]
for arm in ('baseline','modified'):
    cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),
         '--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
    for n in names:cmd+=['--source',n]
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
    C=R/'02_BACKEND/lawrag/research/candidates/adr_0944'/arm
    if arm=='modified':
        for n,h in names.items():
            if sha(C/'snapshot'/n)!=h:shutil.copyfile(R/parent['code_root']/n,C/'snapshot'/n)
    for command in ('refresh','freeze','validate'):
        subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],check=True,stdout=subprocess.DEVNULL)
    rev=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
    files={n:sha(code/n) for n in names}
    assert files==(names if arm=='modified' else before)
    candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
        'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':arm,
        'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],
        'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
    candidates.append(candidate)
    put(D/(arm+'-binding.json'),{'code_root':str(code.relative_to(R)),'serving_files':files,
        'candidate':candidate,'release_id':'adr0944-'+arm,'generation':90})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=candidates)
m['questions']=[]
for i,case in enumerate(read(D/'cases.json'),1):
    p=A/'실험'/f'질문-{i:03d}-{case["id"]}.md'
    titles=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값',
            '제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
    texts=['run-001; baseline/modified 각1회; known-case probe.',case['question'],
           '승인된 법률 정답 없음. 원문 확보와 비용을 관찰한다.',
           '고정 데이터·코드·허용 문서 binding과 raw/wire 캡처.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/run-001/retrieval-ledger.json',
           '각 arm/case wire 및 raw의 실제 provider 요청/응답.', 'canonical, calls.json, generations.json.',
           '평가 모델0회. 기계 계측과 원문 확인.', '실행 후 기록.']
    p.write_text('# '+case['id']+'\n\n'+'\n\n'.join(f'## {j}. {title}\n\n{text}' for j,(title,text) in enumerate(zip(titles,texts),1))+'\n')
    m['questions'].append({'number':i,'case_id':case['id'],'file':p.name,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
files={}
for arm in ('baseline','modified'):
    b=read(D/(arm+'-binding.json'))
    files.update({str((Path(b['code_root'])/n)):h for n,h in b['serving_files'].items()})
base=read(D/'baseline.json')['manifest']
paths=[*T.glob('*.py'),*D.glob('*.json'),R/'06_TOOLS/EXPERIMENTS/resource_guard.py',
       R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
       R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
paths += [R/base['data_path']/n for n in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('Two immutable 389-file code roots and four-request sequence frozen.')
