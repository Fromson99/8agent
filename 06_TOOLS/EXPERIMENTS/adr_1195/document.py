"""Report completed evidence only; does not alter a product or rerun a case."""
from common import *
import re
r=read(RUN/'result.json');f=read(DES/'freeze.json')
rows=[]
for case in r['cases']:
 cid=case['case_id'];P=ART/'live'/cid
 if not case['executed']:
  rows.append({'case_id':cid,'executed':False,'reason':case['reason']});continue
 d=read(P/'diagnosis.json');g=read(P/'gate.json');review=read(P/'content-review.json');prompt=read(P/'prompt-audit.json')
 rows.append({'case_id':cid,'executed':True,'seconds':d['elapsed_seconds'],'model_seconds':d['model_transport_seconds'],
  'other_seconds':d['elapsed_seconds']-d['model_transport_seconds'],'physical_calls':d['model_calls'],
  'providers':d['completed_response_providers'],'provider_switches':d['provider_switches'],
  'http_status':d['return_http_status'],'final_answer':d['final_answer_present'],'request_status':d['request_status'],
  'source_checks':d['source_checks'],'input_checks':d['model_view_span_checks'],'source_mismatches':d['source_mismatches'],
  'acl_violations':d['acl_violations'],'budget_matches':d['physical_budget_matches'],
  'prompt_audit':prompt,'content_review':review,'gate':g,'resource':d['resource'],
  'remaining_worker_pids':d['remaining_worker_pids']})
assert all(not x.get('remaining_worker_pids') for x in rows)
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-main116-live-test';O.mkdir(parents=True,exist_ok=True)
put(O/'observations.json',{'cases':rows,'usage':r['usage'],'active_main':116,'main_changed':False,'new_product_changes':False,
 'same_code_as':'Selected MAIN116 / ADR1194 integrated rev-001','global_quality_certified':False})
lines=['MAIN116 실제 서비스 최종 답변 시험 — ADR1195','',
 '실행 조건','사용자 “테스트한번해봐” 요청으로 선택 MAIN116과 동일466파일을 동결했다.',
 '실제 service.service application → RAG_ASK와 기존 LocalQwen38Transport로 MAIN116을 실행했다.',
 '1194의 최종 프롬프트와 일반 문구 제거가 포함된 MAIN116 전체를 그대로 사용했다. 데이터·65문서 권한·Qwen3.8·Parasail 우선/확정429 NearAI1회 유지.',
 '예산40모델/1024도구/1800초·개별180초·출력상한없음·자원 중단 기준을 유지했다.',
 '기준답변과 평가 좌표는 제품 입력에 넣지 않았다. 같은 질문 자동재시험은 하지 않았다.','']
for x in rows:
 lines += [x['case_id']]
 if not x['executed']:
  lines += ['미실행: '+x['reason'],''];continue
 lines += [f"전체{x['seconds']:.3f}초 / 모델{x['model_seconds']:.3f}초 / 기타{x['other_seconds']:.3f}초.",
  f"물리{x['physical_calls']}호출·공급자{x['providers']}·전환{x['provider_switches']}회·HTTP{x['http_status']}.",
  f"최종답변 존재={x['final_answer']}·요청저장={x['request_status']}·전체게이트={x['gate']['passed']}.",
  f"원문검사{x['source_checks']}·입력검사{x['input_checks']}·불일치{len(x['source_mismatches'])}·권한위반{len(x['acl_violations'])}·물리차감일치={x['budget_matches']}.",
  '최종 프롬프트 전달: '+json.dumps(x['prompt_audit'],ensure_ascii=False),
  '내용 검토: '+json.dumps(x['content_review'],ensure_ascii=False),
  '자원: '+json.dumps(x['resource'],ensure_ascii=False),
  '답변 원문: '+str((ART/'live'/x['case_id']/'answer.txt').relative_to(ROOT)),'']
lines += ['사용량',json.dumps(r['usage'],ensure_ascii=False),'',
 '한계와 적용 상태','원문·내용·저장 완료와 법률 품질 인증은 구분한다. 알려진 사례 한 번의 관찰이며 통제 A/B가 아니다.',
 '이전1191과 공급자·조사 경로·입력이 달라질 수 있으므로 품질/속도 차이를 프롬프트만의 효과로 단정하지 않는다.',
 'MAIN116의 일반 미확인 문구 제거가 실제 최종 답변에도 반영되는지 확인했다. 전송 UNKNOWN과 실제 material gap은 별도 검증하며 전체 기준을 완화하지 않는다.',
 '작업 제품·MAIN116·GENOS 변경 없음. Git·메일 미수행. 새 평가 모델0. 완료/실패 원본을 보존한다.',
 'ADR: '+str(ADR.relative_to(ROOT)),'원시 요청/응답: artifacts/live/<case>/raw/call-*/*.json.gz']
report=O/'실험결과.txt'
with report.open('x') as s:s.write('\n'.join(lines)+'\n')
passed=all(x['executed'] and x['gate']['passed'] for x in rows)
front=(ADR/'README.md').read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if passed else 'Rejected'),front)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
brief='; '.join(x['case_id']+(': 미실행' if not x['executed'] else f": {x['physical_calls']}호출/{x['seconds']:.3f}초, 전체게이트={x['gate']['passed']}") for x in rows)
texts=[brief+'。MAIN116 유지.',
 '1194에서 최종 프롬프트와 근거 없는 일반 미확인 문구 제거를MAIN116에 통합했다. 이번은 실제 선택서비스에서 최초로 누적 수정 전체를 검사하는 요청이다.1193 감독 UNKNOWN은 미해결인 채 시작했다.',
 '[사전 기준](artifacts/design/criteria.json). 원문·권한·예산·필수근거 확보/인용·요구별 검토·저장·내용 전부 통과 시에만009 실행. 조건 누락과 서버 제한 문구는 분리 관찰하고 전체기준을 완화하지 않는다.',
 '선택MAIN116의466파일과 같은 격리 snapshot을 감사 증거로 동결했다. 실행은 실제 service.service의 선택 릴리스 import이며 포인터·제품코드·기본설정을 바꾸지 않았다.',
 '같은 CM007/조건부009·65문서 권한·데이터·Qwen3.8·Parasail우선/확정429NearAI1회. 예산·자원 기준 유지. 평가 전용 기준답변은 제품에 비공개다.',
 '[결과](artifacts/run-001/result.json). '+brief,
 '\n\n'.join(x['case_id']+': '+json.dumps(x.get('content_review',{'reason':x.get('reason')}),ensure_ascii=False) for x in rows),
 '물리 호출'+str(r['physical_calls'])+'회. 공급자 보고 사용량: '+json.dumps(r['usage'],ensure_ascii=False)+'. [회수 원장](artifacts/run-001/retrieval-ledger.json). 표본 p95나 속도 개선율을 주장하지 않는다.',
 '최종 프롬프트의 실제 전달과 모델 응답을 관찰했다. 원문 전달, 주장 내용, 서버 표시 문구를 구분한다. 한 번의 실행으로 개선 효과를 일반화하지 않는다.',
 '인샘플·decision_eligible=false. 공급자와 이전 조사 입력이 같지 않은 실험이다. 저장 판본 기준이며 현행 법률 자문·GENOS 품질 검증이 아니다.',
 '활성 MAIN116와 작업 제품은 유지한다. 같은 사례 자동 재시도0. 이번 실행 후 제품 수정·승격은 하지 않았다. 롤백할 운영 변경 없음.',
 '06_TOOLS/EXPERIMENTS/adr_1195. 완료 사례를 재호출하지 않는다. `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1195-main116-live-cm007 --final`.']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN116 실제 서비스 최종 답변 시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 인덱스\n\n'+ '\n'.join('- ['+x['case_id']+'](질문-'+str(i).zfill(3)+'-'+x['case_id']+'.md): '+('실행, 전체게이트 '+str(x['gate']['passed']) if x['executed'] else '선행 게이트 미통과로 미실행') for i,x in enumerate(rows,1))+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '__pycache__' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[report]
(ART/'manifest.json').write_text(json.dumps({'schema_version':'adr-artifacts-v1','adr_id':'ADR-1195','created_at':read(ADR/'claim.json')['created_at'],
 'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen prompt candidate live evidence or read-only diagnosis',
 'contains_raw_prompts_and_outputs':('/raw/' in str(p) or '/canonical/' in str(p) or p.name.endswith('.sqlite'))} for p in paths]},ensure_ascii=False,indent=2)+'\n')
print(report)
