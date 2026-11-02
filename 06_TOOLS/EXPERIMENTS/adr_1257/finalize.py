from pathlib import Path
import json,hashlib,datetime
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1257-wiki-oracle-space-recovery';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
v=read(O/'result.json');m=read(A/'실험/manifest.json');c=read(D/'criteria.json')
m['lineage']['hypothesis_delta']='Return already empty BODY heap allocation while preserving every current row and metadata.'
m['design'].update(hypothesis=c['action'],primary_metric='Freed bytes with full exact values preserved',success_criteria=c['success'],failure_criteria=['Any row, PK, metadata difference','Cannot restore original rowmovement','No actual reclaim or final over270MiB'],criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='not_applicable',reason='DB maintenance only; no product code/model/retrieval candidate. Runner and pre-run criteria hashes are preserved in artifacts/design.')
m['design']['arms'][0].update(changes='Read-only before maintenance',controls='Same four complete tables and original current allocation')
m['design']['arms'][1].update(changes='Previously proposed heap-only shrink after this thread user selected SIDDA cleanup; retain270MiB cap',controls='No DELETE, LOB/CASCADE/index DDL; every value and metadata compared')
m['dataset'].update(name='All current SIDDA Agent records before maintenance',version='20261030-1257',frozen_source=str((O/'before.json').relative_to(R)),sha256=sha(O/'before.json'),legal_version_checked=False,reference_version_checked=False)
m['runs'][0].update(arm_ids=['recovery'],selection_rule='Existing SIDDA BODY heap only, complete four table row preservation; target chosen before maintenance',status='complete',artifact_path=str((O/'result.json').relative_to(R)),sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','historical_only':True,'capacity':v['before_capacity']},'recovery':{**v,'status':'complete'}},usage={'new_model_calls':0},latency={'not_measured':True},error_taxonomy=[])
m['llm_policy']['llm_calls']=[]
reason='Oracle physical storage maintenance; no retrieval/model/question selection'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['사용자 “기존 SIDDA 공간 정리 후 진행” 선택으로 빈 BODY heap 할당만 반환. 204,734,464바이트(195.25MiB) 회수. 제품/MAIN 반영 아님.',
 '다른 완료시험 후 SIDDA 290,258,944바이트/기존300MiB의92.2708%. 이전1256 자동승인 거절과 미실행 제안은 보존. 현재 사용자 선택과 정확 작업 설명으로 새 자동승인 검토를 거쳐 실행했다.',
 '[사전 기준](artifacts/design/criteria.json), [사용자 범위](artifacts/design/authorization.json). 시작 시 이미90% 초과였으므로 전체기간 준수라고 하지 않는다. 전체4표값/PK/메타 동일과 종료270MiB이하를 요구했다.',
 '읽기전용 전체 압축백업→압축/비압축 해시 확인→270MiB할당상한→BODY ROW MOVEMENT ENABLE/SHRINK/DISABLE→전체값/메타 대조. 추가DELETE/컬럼/LOB/CASCADE/인덱스 DDL 없음.',
 '[전 상태/백업](artifacts/run-001/before.json), [실행기 지문](artifacts/design/runner.json). 실제 로컬FREEPDB1/SIDDA. 모델0; 법률 내용 평가 아님. 원문/Gold/기존완료ADR는 수정하지 않음.',
 '[실제 결과](artifacts/run-001/result.json). 290,258,944→85,524,480바이트. 기존300MiB 기준92.2708→27.1875%. 4표전체 stream hash/행수·PK/컬럼·제약·인덱스 동일. ROW MOVEMENT DISABLED 복원. quota270MiB 유지.',
 '1257 예약시 부모 arm명cleanup은 존재하지 않아 도구가 생성 전 거절; 실제완료archived로 정정. DB실행 자체 추가실패0. 이전1256 거절/준비실패 기록 불변.',
 '실제 모델0·질의 검색효과 없음. 회수195.25MiB는 SIDDA할당량이며 DB파일/호스트디스크의 동일비율 감소 주장이 아니다.',
 '이미 삭제된 과거실험으로 남은 빈 heap할당이 원인이었던 공간을 회수했다. 실제 모델/전체RAG통과와 별개이며 해당시험은1255에서 진행한다.',
 '전체백업 JSONL값의 복원 가능 표현과 압축복원/해시는 검증. 별도DB 재삽입 복원은 미실행. 물리ROWID는 바뀔 수 있으며 전후값동일만 인증. 현장19c/ORDS/NFS미시험.',
 '270MiB상한을 유지해 기존300MiB90%이상 추가할당 차단. 물리할당 되돌림을 자동으로 하지 않는다. 논리값보존실패 시 쓰기중단/보존백업과 관리자복구; 새기록삭제 금지. 기존1256 대기제안은 실행하지 않는다.',
 '06_TOOLS/EXPERIMENTS/adr_1257/reclaim.py 실행영수증을 조회한다. 이미완료된 유지보수 재실행금지. 이후검증은별도1255 동결후보를 사용한다.']
p=A/'README.md';s=p.read_text();front=s.split('---',2)[1].replace('status: Proposed','status: Accepted');p.write_text('---'+front+'---\n\n# SIDDA 빈 공간 반환과 기록 보존\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
q=A/'실험/질문-001-space-recovery.md';q.write_text('# 공간 회수\n\n현재4표값을보존하고BODY빈heap공간을회수할수있는가?\n\n[실제결과](../artifacts/run-001/result.json). 모델0·검색해당없음.\n')
(A/'실험/README.md').write_text('# 유지보수 결과\n\n[질문/판정](질문-001-space-recovery.md), [실제결과](../artifacts/run-001/result.json).\n')
files=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Pre-run criteria, complete row backup or actual maintenance receipt','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1257','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files})
