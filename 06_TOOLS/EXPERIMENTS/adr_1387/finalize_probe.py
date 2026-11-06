"""Write post-run results from the frozen photo case; never open a model client."""
import json
import re
import sys
from pathlib import Path

script_dir = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(script_dir))
from common import ADR, ART, DES, ROOT, RUN, put, read, sha, write_raw_json
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import (
    StageLedgerRecorder, identity_canonicalizer, grade_capture, build_run_artifact,
    build_experiment_artifact, deterministic_sha256,
)

m = read(ADR/'실험/manifest.json')
photo = read(DES/'live-cases.json')[0]
audit = read(ART/'source-wire-audit.json')['cells']
semantic = read(ART/'manual-review.json')
ptr = read(ART/'activation-at-request.json')
candidate = read(DES/'candidate-selected.json')
assert all(sha(ROOT/candidate['code_root']/n) == h for n,h in candidate['selected_files'].items())
assert read(ART/'runtime-archives.json')['all_restore_hashes_verified']
cells = []
cost = 0
prompt_tokens = 0
completion_tokens = 0
model_seconds = 0
unknown = 0
for cell in sorted((ART/'public-live').iterdir()):
    result = read(cell/'result.json')
    calls = read(cell/'calls.json')
    interrupted=read(cell/'stopped-turn.json') if (cell/'stopped-turn.json').exists() else None
    def outcome(row):
        if interrupted and row['number']==interrupted['physical_call']:
            assert row['status']=='started' and interrupted['outcome']=='UNKNOWN'
            return 'unknown'
        return row['status']
    cells.append({'stopped_turn':interrupted,'name':cell.name, 'result':result, 'stages':[
        {'number':c['number'], 'stage':c['stage'], 'status':outcome(c),
         'model':c.get('actual_model'), 'provider':c.get('actual_provider')} for c in calls]})
    for row in calls:
        usage = row.get('usage') or {}
        cost += usage.get('cost') or 0
        prompt_tokens += usage.get('prompt_tokens') or 0
        completion_tokens += usage.get('completion_tokens') or 0
        model_seconds += row.get('seconds', 0)
        unknown += int(outcome(row)=='unknown')

count = sum(len(c['stages']) for c in cells)
summary = {'activation':ptr,'frozen_files':len(candidate['selected_files']),'cells':cells,
           'physical_calls':count,'unknown':unknown,'reported_cost_usd':round(cost,9),
           'prompt_tokens':prompt_tokens,'completion_tokens':completion_tokens,
           'completed_model_seconds_only':model_seconds,'manual_review':semantic,
           'closed_runtime_archives':read(ART/'runtime-archives.json')['all_restore_hashes_verified'],
           'source_audit':'artifacts/source-wire-audit.json'}
put(RUN/'result.json', summary)
inventory = {(doc,int(node)) for doc,node in read(ART/'source-inventory.json')['article_roots']}
acquired = {(doc,int(node)) for a in audit for doc,node in a['acquired_articles']}
presented = {(doc,int(node)) for a in audit for doc,node in a['presented_articles']}
assert presented <= acquired <= inventory
rec = StageLedgerRecorder('recovery','selected',identity_canonicalizer)
rec.record_stage('source','source',sorted(inventory))
rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),
                 discard_reasons={x:'No acquired article observed for this case' for x in inventory-acquired})
rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),
                 discard_reasons={x:'No corresponding original span verified on wire' for x in acquired-presented})
ledger = build_experiment_artifact(m['adr_id'],m['experiment_id'],[build_run_artifact(
    'run-001',[grade_capture(rec.capture(),[])],{'selected':['source','acquired','present']})])
ledger['audit']={'meaning':'Conversation-wide union of same-version article roots. No retrieval change or claim of benchmark recall.'}
ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/'retrieval-stage-ledger.json.gz'
if not lp.exists(): put(ART/'retrieval-ledger-ref.json',write_raw_json(lp,ledger))
def metric(v):
    return {'baseline':None,'selected':v}
m['retrieval_accounting']={'changed':False,'corpus_total':len(inventory),'before_filter':metric(len(inventory)),
    'after_filter':metric(len(acquired)),'presented_total':metric(len(presented)),'presented_mean':metric(len(presented)),
    'presented_p50':metric(len(presented)),'presented_p95':metric(len(presented)),'golden_recall':metric(None),
    'selectivity':metric(len(presented)/len(inventory)),'not_applicable_reason':'Unchanged retrieval; observed session only.',
    'stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate',
                    'summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'selected':summary},comparisons=[],
                    judge_disagreements=0,usage={'physical_calls':count,'reported_cost_usd':cost,'prompt_tokens':prompt_tokens,'completion_tokens':completion_tokens},
                    latency={'completed_model_seconds_only':model_seconds,'request_seconds_per_completed_turn':[t['request_seconds'] for c in cells for t in c['result']['turns']],
                             'distribution':'Single dependent sequence; population percentiles unavailable'},
                    error_taxonomy=semantic['error_taxonomy'])
put(ADR/'실험/manifest.json',m)
env=f"로컬 활성 {ptr['generation']}세대 {ptr['release_id']}의 서빙 {len(candidate['selected_files'])}파일 해시 고정. 공개 상법 1문서, SQLite, 기본 검토 켬, 부모의 승인 온톨로지 켬. 실제 Qwen3.8-27B FP8, 추론 none, 동일한 실제 실패 대화의 해시 검증된 독립 복제본 각각 1회, GENOS 워크플로우 질문 구성과 서비스 정규화 경유. 현장 Oracle·내부 모델·현장 화면은 별도."
questions='부모 질문 '+read(ART/'action-seed/origin.json')['sent_question']+'\n구조화 행동 '+read(ART/'action-seed/action-request.json')['label']+'\n자유문장 '+ '\n'.join(f"{s['number']}. {s['question']}" for s in photo['steps'])
evidence=f"물리 {count}회, UNKNOWN {unknown}회, 보고 비용 ${cost:.8f}. 입력 {prompt_tokens}, 출력 {completion_tokens} 토큰. [검증 원장](artifacts/source-wire-audit.json), [실행 요약](artifacts/run-001/result.json)."
limitations='한 대화 시도이며 제품 수정, MAIN 승격, 현장 배포 없이 진행했다. 정답은 모델에 별도로 주입하지 않았다.'
front=(ADR/'README.md').read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: '+semantic['adr_status'],front)
report='---'+front+'---\n\n# 사진 속 질문과 재검토 요청의 Qwen 실험\n\n'
sections=[('결정 요약',semantic['conclusion']),('문제와 변경 전 구조',semantic['context']),
 ('가설과 사전 판정 기준',read(DES/'criteria.json')['hypothesis']+'\n\n'+'\n'.join(read(DES/'criteria.json')['success'])),
 ('실험 설계',questions+'\n\n1383의 검토 미통과 원장 복제본에서 명시 행동과 같은 문장을 각각 한 번 실행하도록 동결했다.'),
 ('데이터·모델·재현성',env),('결과',semantic['details']),('사례별 오류 분석',semantic['diagnosis']),
 ('비용·지연·회수 규모',evidence),('해석',semantic['interpretation']),('한계와 일반화 가능 범위',limitations),
 ('운영 결정·롤백 조건','기존 동작을 관찰한 단회 실험이다. 추가 제품 변경은 별도 검증이 필요하다.'),
 ('재현 명령',f"도구는 {script_dir.relative_to(ROOT)}. setup.py로 고정, live_public.py recovery selected --preflight, live_public.py recovery selected. 첫 실패에서 제공된 행동과 검증된 체크포인트가 있는 경우에만 --structured. 중복 외부 호출을 피하려면 기존 raw/canonical 또는 저장된 응답을 검토한다.")]
(ADR/'README.md').write_text(report+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
qs=[('실행 메타',env),('사용자 질문 원문',questions),('기준답변 — 채점 전용, 제품 입력 비공개','상법 제365조 1~3항 원문과 소집 시기를 오프라인 대조. 같은 실패 상태의 후속 요청은 동일 사건·근거에 결속되는지 확인.'),
    ('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz, artifacts/source-wire-audit.json 및 public-live/*/canonical.'),
    ('제품 모델 호출 — run·arm별 실제 원문','artifacts/public-live/*/raw/call-*/request.json.gz, response.json.gz, finished.json. 통신 실패 시 수신 범위와 진단은 partial.json.gz 또는 finished.json에 보존한다.'),
    ('중간 LLM 호출 — router/compiler/verifier/repair','동일 셀의 calls.json / generations.json / canonical/ 및 보관 runtime. 실행되지 않은 단계에는 원응답이 없다.'),
    ('채점 호출과 반복 판정','채점 모델 0. 원문·실제 입력·저장 결과를 직접 대조했다.'),('사례 최종 판정',semantic['details']+'\n\n'+semantic['diagnosis'])]
(ADR/'실험'/m['questions'][0]['file']).write_text('# 사진 두 턴\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(qs,1))+'\n')
(ADR/'실험/README.md').write_text('# 사진 질문 세션\n\n- [실제 질문과 판정](질문-001-recovery.md)\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]
paths += [*script_dir.glob('*.py'),Path(__file__).resolve()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[
    {'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Photo-case experiment artifacts',
     'contains_raw_prompts_and_outputs':'raw' in p.parts or 'canonical' in p.parts or p.name.endswith('.tar.gz')} for p in sorted(set(paths))]})
print(semantic['conclusion'],evidence)
