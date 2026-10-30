from common import *
m=read(ADR/'실험/manifest.json');r=read(RUN/'result.json');f=read(DES/'freeze.json');calls=read(ART/'live/cm-007/calls.json');usage={'input_tokens':sum((x.get('usage') or {}).get('prompt_tokens',0) for x in calls),'output_tokens':sum((x.get('usage') or {}).get('completion_tokens',0) for x in calls),'cost_usd':sum((x.get('usage') or {}).get('cost',0) for x in calls)}
r['combined_usage']=r['usage'];r['usage']=usage;r['combined_unique_physical_calls']=19;r['physical_calls']=11;r['inherited_physical_calls']=8;r['technical_checks_inherited']=247;r['technical_checks_new_executions']=0;r['failed_revisions_preserved']=['ADR1176 original CM001 gate false on COMPLETED enum retained; this audit corrects only canonical COMPLETE','CM007 required KOSDAQ13 and KOSPI13 not acquired; failed completion preserved; CM009 not run'];r['remaining']=['Model treated other securities underwriting rules as sufficient and excluded the two market-specific13 originals','Full ancestor9 receipt incorrectly left child9(14) REQUIRED; observed and scheduled for offline ADR1178 fix','No working integration/MAIN/GENOS promotion']
for row in r['cases']:row['executed_here']=row['case_id']=='cm-007';row['inherited_from']= 'ADR1176 actual0018calls' if row['case_id']=='cm-001' else None
put(RUN/'result.json',r);m['runs'][0]['sha256']=sha(RUN/'result.json');m['results']['usage']={'physical_requests':11,'inherited_physical_requests':8,'unique_across1176_1177':19,'offline_evaluator_requests':0,**usage};m['results']['by_arm']['continued']['cases']=r['cases'];m['results']['error_taxonomy']=r['failed_revisions_preserved']+r['remaining'];put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
'제품464파일은1176rev004와 동일하다. 저장 완료 enum 검사만 COMPLETE로 바로잡아 기존001 기록의 조건 통과를 확인했다.001 재호출0. 이어서007 실제1회11호출·360.868초를 실행했으나 필요한 두 시장 제13조 미확보로 실패했다.009는 실행하지 않았다. MAIN112 유지.',
'1176 gate.py가 저장 성공값을 COMPLETED로 기대했으나 실제 case_repository.py110행과 저장DB는 COMPLETE를 사용했다.1176의 원래 gate와 원시 출력은 보존하고 새 ADR에서 검사기만 정정했다. [정정 영수증](artifacts/storage-enum-correction.json).',
'[사전 기준](artifacts/design/criteria.json).464제품 파일 동일, 기존247기술검사/211부모대조 회귀 결속,001의 storage_complete 한 조건만 수정, 나머지 원문/권한/완성/저장 조건 동일.001 재실행 금지,007 통과 때만009 1회. 사례 실패 시 후속 실행을 하지 않는다.',
'parent=완료1176/repaired, continued 후보의 제품 변경0.001의 작은 감사 JSON만 복사하고 raw/canonical/runtime은 원본을 공유했다. 각 원본 경로와 hash,001의8호출 상속과007의 새11호출을 분리했다. 기존247검사는 같은464파일을 확인해 상속했으며 새247회 실행으로 세지 않았다.',
'동일 MAIN112 선택 데이터, 허용65문서, Qwen3.8 Chutes FP8·출력상한없음·40/1024/1800 유지. 새11요청은 Chutes이며 실제 NearAI 전환0. 평가모델0, 기준답변은 제품 입력에 넣지 않았다. 법령/기준답변 버전 일치와 법률 품질 인증 없음. [freeze](artifacts/design/freeze.json).',
'상속001:8호출146.752초·ANSWER/COVERED·필수원문/저장 조건통과. 새007:11호출360.868초·HTTP200/READY·주장2·ANSWER/COVERED지만 코스닥13/유가증권13 모두 미확보라 완료gate실패.009:미실행.007 확보336/전달834구간 불일치0·권한위반0·물리11=차감11·반환/저장 일치. [결과](artifacts/run-001/result.json).',
'007에서 SOURCE_GOAL_SELECTION_REQUIRED2회, SOURCE_GOAL_INTERMEDIATE1회, FINISH의 REQUIRED_SOURCE_RECOVERY_CHOICE 보완1회가 실제 발생했다. 정확조회 뒤 바로 멈추던 경로는 재개했다. 그러나 모델이 다른 인수업무 규정을 공통 답으로 보고 두 시장13조를 조사하지 않았다. 추가 서버 결함:이미 읽은9조 전체가 하위9조14항을 포함해도 exact좌표불일치 때문에 미확보 처리. [관측](artifacts/ancestor-receipt-observation.json)은 인접block190까지 검사했으나 구조 span은 [186,190)의4블록이 정본이다. 이 결함은 별도1178에서 원문 포함 증명으로 수정한다.',
'새 제품 호출11, 상속8, 이번 작업 전체 고유19. 새007360.868초이며 속도개선 인증 없음. '+json.dumps(usage,ensure_ascii=False)+'\n\n[단계 회수 원장](artifacts/run-001/retrieval-ledger.json)은001상속/007실행/009미실행을 case_id+canonical article-root 좌표로 보존한다. 원장 coverage와 법률 정답률을 구분한다.',
'형식과 조사복구를 개선해도 필요 문서 선택·제외 판단이 자동 해결되지 않는다.007의 원문 누락은 답변완성 실패이며, 단지HTTP200/스키마 통과/저장 성공으로 완료라 할 수 없다. 상위 원문의 하위 포함 판정은 모델 의미와 분리해 서버에서 정확히 고칠 수 있다.',
'알려진 사례 in-sample probe, decision_eligible=false. 제품 동일성 확인은1176 기술검사를 상속하는 근거이며 모든 경로의 현장 실행 인증이 아니다. 더 좋은 모델·GENOS 대리 모델 비교·GENOS 현장·MAIN 서비스 확인 미수행.',
'Proposed/main_wiring=unchanged. 작업 제품 통합·MAIN승격 안함.009 자동실행과007 재실행 없음. 결정적 receipt 결함만1178에서 외부호출 없이 보완한다. 선택포인터가 바뀌지 않아 활성서비스 롤백은 불필요하다. 전체답변 완성과 법률품질 미인증.',
'```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1177/inherit_check.py\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1177-response-recovery-followup --final\n```\n\n원시 실행/검사 결과를 덮어쓰는 재실행은 새 ADR로 분기한다.001과007의 dispatch는 자동 재실행을 차단한다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];p.write_text('---'+front+'---\n\n# 동일 응답복구 코드의 후속 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
for q in m['questions']:
 p=ADR/'실험'/q['file'];s=p.read_text().replace('run-001 / guarded /','run-001 / continued /')
 if q['case_id']=='cm-001':s=s.replace('실제 실행1회','ADR1176의 실제1회 기록상속; 이ADR새호출0')
 p.write_text(s);q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 인덱스\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n\n001상속8호출·007신규11호출·009미실행. [단계 원장](../artifacts/run-001/retrieval-ledger.json), [집계](manifest.json).\n')
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=ART/'manifest.json'];paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path']];a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Same-code audit, canonical COMPLETE correction, inherited001 and new007 raw evidence','contains_raw_prompts_and_outputs':bool('raw' in p.parts or 'canonical' in p.parts or p.suffix in ('.log','.sqlite','.gz'))} for p in paths];put(ART/'manifest.json',a)
print('1177 recorded:11new8inherited;007gatefail;009notrun')
