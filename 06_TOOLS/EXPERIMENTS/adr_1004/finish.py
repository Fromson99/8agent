from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1004-saved-termination-response-replay';ART=ADR/'artifacts'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
f=read(ART/'freeze.json');assert all(sha(ROOT/n)==h for n,h in f['files'].items());m=read(ADR/'실험/manifest.json');assert m['design']==f['design']
rows={a:read(ART/(a+'.json')) for a in ['baseline','candidate']};result={'status':'COMPLETE','passed':all(r['passed'] for rs in rows.values() for r in rs),'by_arm':{a:{'correct':sum(r['passed'] for r in rs),'total':len(rs)} for a,rs in rows.items()},'new_model_calls':0,'known_saved_responses':True,'quality_certified':False,'main_changed':False,'original_failures_preserved':True};save(ART/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'));m['results'].update(status='complete',by_arm={a:{'status':'complete',**result['by_arm'][a],'accuracy':sum(r['passed'] for r in rs)/len(rs)} for a,rs in rows.items()},comparisons=[{'baseline':'baseline','candidate':'candidate','metric':'saved_response_action_correctness','delta':0,'interpretation':'Known synthetic replies; no evidence of improved native stopping.'}],judge_disagreements=0,usage={'physical_calls':0,'cost_usd':0},latency={'not_applicable_reason':'Offline replay only; original model times remain in ADR1002.'},error_taxonomy=[])
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted')
findings='보존한6개 모델 응답을 원래 입력·스키마와 동결 코드로 재검증했다. 기준3/3, 후보3/3이며 충분한 원문에서는FINISH, 필수 원문 누락·참조 경로 구체화에서는READ를 선택했다. 새 모델 호출0회다. ADR1002의 실행기 실패와 native 실패 판정은 바꾸지 않았다.'
values=[findings,'Original experiment returned transport envelopes, while its stage runner expected raw bodies.',m['design']['success_criteria'],m['design']['sampling'],'Exact ADR1002 snapshot and saved response hashes; no product edits.','[baseline](artifacts/baseline.json), [candidate](artifacts/candidate.json).',findings,json.dumps(result,ensure_ascii=False,indent=2),'Saved-response compatibility confirmed; no native quality certification.','Previously seen synthetic cases, no unseen evaluation; equal3/3 gives no improvement estimate.','MAIN/GENOS unchanged; no network or model client used.','reserve → freeze hashes/criteria → baseline3 → candidate3 → audit report → validate/graph.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 보존한 종료 응답 오프라인 검증\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,values)))
(ADR/'RESULT.txt').write_text(findings+'\n')
for q in m['questions']:
 vals=[q['case_id'],'Frozen synthetic rule question from ADR1002.','Pre-existing stage-gold.json action labels; no legal-answer claim.','Exact raw response and input hashes in freeze.json.','No retrieval executed.','Original schema and canonical projection revalidated.', 'New model calls0; original usage retained in ADR1002.','Deterministic schema/action checks, no model judge.',findings]
 p=ADR/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));q['sha256']=sha(p)
(ADR/'실험/README.md').write_text('# 사례\n\n'+''.join('- ['+q['case_id']+']('+q['file']+')\n' for q in m['questions']));save(ADR/'실험/manifest.json',m)
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1004','files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen exact saved-response replay'} for p in sorted(ART.glob('*.json')) if p.name!='manifest.json']})
p=ROOT/'04_EXPERIMENTS/ADR/README.md';s=p.read_text();p.write_text(s.replace('# ADR workspace\n','# ADR workspace\n- [ADR-1004 보존 응답 재검증](ADR-1004-saved-termination-response-replay/README.md) — 원본6응답 계약·행동 검증6/6, 모델0회, native 품질 인증 없음.\n'))
print(json.dumps(result,ensure_ascii=False))
