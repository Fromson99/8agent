from common import *
import re
r=read(ART/'contracts/result.json')
summary={'passed':r['passed'],'failed':r['failed'],'model_calls':0,'candidate_integrated':False,'main_unchanged':True,'quality_certified':False,'failures':[{'test':x['test'],'error':x['error']} for x in r['rows'] if x['outcome']=='failed']}
put(RUN/'result.json',summary)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'integrated':summary},comparisons=[],judge_disagreements=0,usage={'physical_calls':0},latency={'contracts':r['seconds']},error_taxonomy=['integration-stopped-unrelated-concurrent-working-change']);put(ADR/'실험/manifest.json',m)
notes=['후보106검사 통과. 앞서 확인한 화면 관련 병행2파일은 정확히 보존했다. 작업 반영 쓰기0.',
'통합 허용목록 검사에서1331 동결 전 Oracle 관련 병행4수정(source_tools/oracle_development_mapping/oracle_dp/oracle_query_service)과 신설 oracle_gold_mapping/oracle_gold_ontology2파일이 추가로 확인됐다. 검증 후보로 덮어쓰면 이 변경을 잃으므로 중단했다.',
'통합 허용목록을 무작정 완화하지 않고, 전체 작업 변화를 정확히 보존한 새527파일 후보로 검사한다. 선택MAIN140/원문DB/모델 불변.',
'후보1327 실패 대응 핵심7수정은 이 후보에서106통과 상태이며 다음 통합에 그대로 계승한다. 실제모델0.']

heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'완료1327 기반 격리 후보, 신규39과 기존67 검사','고정525 파일, 합성/API/원래1327 실패 기록, 실제모델0',notes[0],notes[1]+'\n'+notes[2],str(r['seconds'])+'초; 실제모델0; corpus retrieval 없음',notes[0],notes[3],'후보 미통합, 작업코드1326 유지; 다음 수정은 후속ADR','setup → candidate edits → freeze → check → archive_contracts → finish → hash/status/validate --final/graph']
f=(ADR/'README.md').read_text().split('---',2)[1];f=re.sub(r'(?m)^status:.*$','status: Proposed',f)
(ADR/'README.md').write_text('---'+f+'---\n\n# 반복과 범위 연결 계약 검사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 vals=['run-001/integrated/rev001',q['case_id'],'합성 계약·저장 실제 실패 대조, 기준답변 없음','### 회수·탈락 단계 원장 — run·arm별\n\ncorpus 회수 없음, 단계 원장 not_applicable; 전체 fixture와 failures 보존','새 제품모델0, scripted API runtime SHA archive','새 중간모델0','채점모델0; contracts/result.json', '\n'.join(notes)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,vals),1))+'\n')
(ADR/'실험/README.md').write_text('# 범위\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions']))
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1331','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen failed candidate, complete checks and archived runtime'} for p in paths]})
