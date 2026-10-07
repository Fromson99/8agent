"""Finish the measured, in-sample successor without creating MAIN eligibility."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0676-investigation-reinspection-repair';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'실험/manifest.json');v=read(A/'artifacts/run-001/result.json');assert m['in_sample'] and not m['decision_eligible'];ok=v['strict_success'];front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted' if ok else 'status: Rejected')
sections={
'1. 결정 요약':('Accepted. 관찰 실패 수정 probe를 통과했다.' if ok else 'Rejected. 사전 probe 조건을 충족하지 못했다.')+' in_sample=true, decision_eligible=false. 이 결과로 MAIN을 승격하지 않는다.\n\n'+json.dumps(v['checks'],ensure_ascii=False,indent=2),
'2. 문제와 변경 전 구조':'완료 ADR0675의 IC11~IC13에서 저장 원문 재열람과 보류가 충돌했고 sparse 보정이 행동과 근거를 따로 교체했다. IC15에서는 일반적인 기재사항 질문을 제1항만으로 제한했다. IC14는 Parasail upstream 응답 연결이 중단됐다. 실패 기록은 원래 ADR에 보존했다.',
'3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
'4. 실험 설계':'관찰된 IC11~IC15 5건에 한정한 in-sample probe다. generation42 baseline과 통합 후보를 동일 원문·공개145 문서 권한·모델·provider·예산으로 각각1회 계획했으며5건은 완료,2건은 응답 도중 중단,3건은 미실행으로 보존했다. 원문 재열람은 DEFER를 유지할 수 있고 새 범위 확보의 READ와는 구분한다. control-v2 보정은 행동·대상·검색어·근거가 연결된 전체 union 결정을 요구한다. ADR0665 legacy grouped READ+DEFER는 기존대로 유지한다.',
'5. 데이터·모델·재현성':'Qwen3.8 qwen/qwen3.8-27b, OpenRouter Parasail FP8 단독, reasoning none, fallback 없음. term-source-3b667f54bb11d9477888 공개 원문 판본. gold는 제품에 전달하지 않았으며 완성된 응답만 동일 독립 judge로 각1회 채점했다. 동결 code/schema/pipeline/runner/model/data와 평가 서빙265파일을 결속했다.',
'6. 결과':json.dumps({a:{k:r[k] for k in ('total','executed_count','not_executed_count','request_success_count','correct_count')} for a,r in v['by_arm'].items()},ensure_ascii=False,indent=2)+'\n\n'+json.dumps(v['paired_outcomes'],ensure_ascii=False,indent=2),
'7. 사례별 오류 분석':'질문별 원시 입출력·중간 선택과 보정·native 상태·실제 인용 및 독립 채점을 질문 문서와 diagnostic.json에 보존했다. 실패를 대체하거나 제품 답변을 수정해 채점하지 않았다.\n\n'+json.dumps({a:[{'case_id':c['case_id'],'http_status':c['http_status'],'correct':c['correct'],'reason':c['grading_reason']} for c in r['cases']] for a,r in v['by_arm'].items()},ensure_ascii=False,indent=2),
'8. 비용·지연·회수 규모':json.dumps({a:{k:r[k] for k in ('usage','latency')} for a,r in v['by_arm'].items()},ensure_ascii=False,indent=2)+'\n\nsource→recall→acquired→presented는 canonical 조문 그룹 단위 retrieval-ledger.json에 기록한다. 확보와 전달, 채택 범위는 독립 영수증이며 확보만으로 채택이나 전체 조문 확인을 선언하지 않는다.',
'9. 해석':'관찰된 실패 수정 여부만 판정한다. 쟁점별 COVERED는 모델의 판단이며 semantic_quality_certified=false를 유지한다. 정확 인용·권한·실행 계약은 별도 결정적 검증이다.',
'10. 한계와 일반화 가능 범위':'관찰된5사례는 독립 품질 분모가 아니다. 후속 분리평가를 통과해야 MAIN 후보가 된다. GENOS 내부 자료·모델·리비전·워크플로우는 실행하지 않았다. 이전 probe의 obsolete 테스트5개는 ADR0665가 의도적으로 바꾼 legacy DEFER 동작과 모순되어 제외하고 해당 원본과 실패 로그를 보존했다. ADR0665 현행 계약을 포함한146검사는 통과했다. 원시 입력·출력은 hash 고정 파일을 참조하여 중복 복사를 줄였고, 회수 원장은 무손실 gzip으로 보존했다. 사용자의 후속 지시로 세부 판단 오류는 승격의 절대 차단 기준으로 삼지 않지만, 이 probe의 동결 기준을 소급 변경하지 않았다. 후속 ADR에서 새 기준을 호출 전에 고정한다. legacy-test-topology.json에 근거를 남긴다.',
'11. 운영 결정·롤백 조건':'MAIN은 generation42로 유지한다. 후속 ADR의 Accepted·out-of-sample·decision-eligible·complete 결과와 hash 고정 승격 및 서비스 실행 binding 확인이 별도로 필요하다. 현재 후보 파일을 작업 코드나 선택 릴리스에 적용하지 않았다.',
'12. 재현 명령':'WSL /home/jin/8-AGENT에서 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0676/run_case.py --arm baseline 또는 integrated --case IC11…IC15. 기존 결과는 덮어쓰지 않는다. 후속 후보·재실행·재채점은 새 ADR이다. 완료 검사: .venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0676-investigation-reinspection-repair --final 및 graph.'}
(A/'README.md').write_text('---'+front+'---\n\n# ADR-0676 저장 원문 재열람·보정 및 요구 범위 유지\n\n'+'\n\n'.join('## '+k+'\n\n'+s for k,s in sections.items())+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and p.suffix in ('.json','.txt','.log','.py','.gz') and not any(x in ('prepared-generations','runtime','main-stage') for x in p.relative_to(A/'artifacts').parts)]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact probe design, frozen boundaries, native/provider/evaluator evidence'} for p in sorted(files)]})
print('Probe decision', 'Accepted' if ok else 'Rejected', 'never MAIN eligible')
