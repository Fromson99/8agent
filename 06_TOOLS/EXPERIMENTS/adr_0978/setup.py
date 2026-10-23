"""Prospective candidate; no production mutations or model calls."""
from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-0977-unified-scope-semantic-authority'
prev=read(parent/'artifacts/stage.json');PC=ROOT/prev['roots']['candidate']
record=read(ROOT/prev['candidate_dir']/'candidate.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='Unify title and scope intent, preserve lexical candidates and model semantic authority while integrating verified hierarchy and multiturn fixes.',
 primary_metric='Fresh request scope interpretation and source-bound retrieval; mandatory deterministic safety and native API contracts.',
 success_criteria='All frozen critical ACL/original/hash/state/budget/API checks pass. Candidate scope decision correct in at least 22 of 24 fresh cases, with semantic misses documented rather than silently widened. All declared retrieval fixture candidates and pagination remain reachable. Known original query is a separate diagnostic, not holdout accuracy.',
 failure_criteria='Any new source/ACL/hash/state violation, silent widening after unresolved named scope, or failed mandatory deterministic/native contract rejects promotion. Provider failures are preserved and not silently retried.',
 criteria_frozen_before_run=True,sampling='24 newly authored public or synthetic expressions, unseen in parent probe. Public metadata grant is unchanged; missing named documents are explicit negative resolver cases.',
 budget={'parallel_heavy_processes':1,'test_address_space_bytes':3*1024**3,'full_runtime_rss_bytes':10*1024**3,'minimum_available_ram_bytes':3*1024**3,'entry_model_calls':48,'known_diagnostic_max_model_calls':40,'transport_retries':0},
 recovery=read(parent/'실험/manifest.json')['design']['recovery'])
save(ADR/'실험/manifest.json',m)
paths=[r['target_path'] for r in record['files'] if (ROOT/r['target_path']).exists()]
Cdir=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0978/candidate'
if not Cdir.exists(): Cdir=ac.snapshot(ADR,'candidate',paths,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
assert not (ART/'stage.json').exists(), 'setup already completed'
C=Cdir/'snapshot'
for row in record['files']:
 target=row['target_path'];p=C/target
 register=not p.exists()
 p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PC/target,p)
 if register:ac.register_file(Cdir,target,upstream_state='absent')
save(ART/'stage.json',{'base_pointer':prev['base_pointer'],'base_release':prev['base_release'],
 'working_baseline':{r['target_path']:sha(ROOT/r['target_path']) if (ROOT/r['target_path']).exists() else None for r in record['files']},
 'roots':{'baseline':prev['roots']['baseline'],'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(Cdir.relative_to(ROOT)),
 'parent_probe':str(parent.relative_to(ROOT)),'preexisting_differences':prev['preexisting_differences']})
p=C/'02_BACKEND/semantic_runtime/legal_agent/request_entry.py';t=p.read_text();needle='법령을 검색 대상으로 준 질문은 NAMED_SCOPE다.'
assert needle in t;t=t.replace(needle,needle+' 검색 대상의 명시 여부와 실제 문서의 검색 가능 여부는 별개다. 법령명이 law_title_hints에 없거나 저장소에 없을 것 같아도 사용자가 그 법령에 따른 설명을 요청하면 NAMED_SCOPE와 그 이름을 보존한다. 문서 해석·검증 실패는 시스템이 미확인으로 처리하므로 허용 전체 범위로 바꾸지 않는다. 조문 번호가 없어도 특정 법령 전체를 요청한 것이다.')
p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/completion_execution.py';t=p.read_text()
t=t.replace("        from .law_candidates import answer_first\n        defer_to_user = False  # Materiality is the model's assessment; a claim is not completion.\n        if fresh and not defer_to_user and count < limit and can_investigate:","        # A supported claim does not settle the model's remaining material gaps.\n        if fresh and count < limit and can_investigate:")
start=t.index('        if fresh and defer_to_user:');end=t.index('        elif repeated',start)
t=t[:start]+"        if fresh:\n            stop_reason = 'ASSESSMENT_REENTRY_LIMIT' if count >= limit else 'INVESTIGATION_BUDGET'\n"+t[end:];p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/relation_read_policy.py';t=p.read_text().replace('relation-reading-policy-20261018-r3','relation-reading-policy-20261022-model-v1')
t=t.replace('DEFER는 UNDETERMINED와 미확인 사유다. 조건부 SKIP은 DOES_NOT_APPLY와\n실제 질문 범위에 연결한 제외 사유다. 단순 연결도 생략 사유를 기록한다.', 'DEFER는 UNDETERMINED와 미확인 사유다. SKIP은 현재 필요하지 않다는 판단과 사유를 기록하며 적용 여부를 거짓으로 확정하지 않는다. 단순 연결도 생략 사유를 기록한다.')
p.write_text(t)
print(C)
