from pathlib import Path
import hashlib,json,re,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3]
adr=ROOT/sys.argv[1]; art=adr/'artifacts'; message=sys.argv[2]
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(art/'run-001/integrated/result.json');c=read(art/'check-003.json');ok=r['completed'] and not c['failed'] and not c['import_leaks'];decision='Accepted' if ok else 'Rejected'
result={'status':'complete','success_criteria_met':ok,'integrated':r,'contract_check':c,'interpretation':message,'main_changed':False,'decision_eligible':False}
put(art/'run-001/result.json',result);m=read(adr/'실험/manifest.json')
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['baseline','integrated'],'selection_rule':'Frozen known nine-response trace and prospective contracts; stop on protected mismatch','status':'complete','artifact_path':str((art/'run-001/result.json').relative_to(ROOT)),'sha256':sha(art/'run-001/result.json'),'success_criteria_met':ok}]
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','inherited_result':'ADR-1099/run-001/baseline'},'integrated':{'status':'complete','decision':decision,'success':ok,'contracts_passed':c['passed'],'calls':len(r['calls'])}},comparisons=[{'kind':'known-case replay','candidate_completed':r['completed'],'interpretation':message}],usage={'new_model_calls':0,'cost_usd':0},latency={'candidate_nonmodel_excluding_glossary':r.get('nonmodel_excluding_glossary_seconds'),'valid_full_request':r['completed']},error_taxonomy=[] if ok else [{'kind':'protected_replay_mismatch','description':message}],main_wiring='unchanged',quality_certified=False)
m['retrieval_accounting']=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1093-nonmodel-residual-profile/실험/manifest.json')['retrieval_accounting'];m['retrieval_accounting']['changed']=False;m['retrieval_accounting']['stage_ledger']['mode']='inherited';put(adr/'실험/manifest.json',m)
meta=(adr/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: '+decision,meta)
sections=[('결정 요약',decision+'. '+message),('문제와 변경 전 구조','준비 SQL·스키마 재사용·현재 페이지 상세화 후보. 정확한 변경·기준은 design/criteria.json과 동결 snapshot으로 결속한다.'),('가설과 사전 판정 기준',m['design']['hypothesis']),('실험 설계','신규 계약 검사 후 보관응답9개를 네트워크 없이 실제 서비스 진입점에서 재생한다. 첫 보호 입력 불일치 시 중단한다.'),('데이터·모델·재현성','완료1086rev004 fsc-hard-005의 원래 입력/출력. 기존 데이터·권한·예산 유지. 새 모델0회. 기준1099 측정 재사용.'),('결과',f"신규 검사{c['passed']} 통과. 후보 완료={r['completed']}. {message}"),('사례별 오류 분석',message+' 실제 expected/actual과 실패 상태를 보존한다.'),('비용·지연·회수 규모','새 모델0·비용0. 완료되지 않은 실행의 부분 시간은 개선률로 쓰지 않는다. 상세 SQL·자원은 result.json.'),('해석','합성 검사와 실제 서비스 재생은 별도다. 관측은 알려진 한 질문에 한정한다.'),('한계와 일반화 가능 범위','승격자격 없음. 1초 목표·새 질문 판단품질·Oracle/GENOS 효과 미인증. 입력/복구 통합은 후속 범위.'),('운영 결정·롤백 조건','MAIN106 유지. 실패 후보·원본·감사 자료 보존. 새로운 수정/평가는 새로운 ADR로 동결.'),('재현 명령',f"06_TOOLS/EXPERIMENTS/adr_{m['adr_id'].split('-')[1]}/check.py 및 replay.py optimized. 완료 산출물 덮어쓰기 금지. validate --final 및 graph 결과 보존.")]
(adr/'README.md').write_text('---'+meta+'---\n\n# 준비 성능 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(sections,1))+'\n')
(adr/'실험/README.md').write_text('# 결과\n\n[검증 결과](../artifacts/run-001/result.json). '+message+'\n')
files=[p for p in art.rglob('*') if p.is_file() and p!=art/'manifest.json' and 'runtime' not in p.parts]
put(art/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Protected preparation replay and preserved evidence','contains_raw_prompts_and_outputs':p.name in ('actual.json','expected.json')} for p in files]})
print(decision)
