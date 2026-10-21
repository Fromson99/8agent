from pathlib import Path
import json,hashlib,statistics,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0915-answer-first-followup-provenance'
read=lambda p:json.loads(p.read_text());put=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
subprocess.run([sys.executable,str(Path(__file__).parent/'report.py')],check=True)
mfile=A/'실험/manifest.json';m=read(mfile);m['lineage']['hypothesis_delta']=read(A/'artifacts/design/criteria.json')['hypothesis']
for arm in read(A/'artifacts/run-001/retrieval-ledger.json')['runs'][0]['arms']:
 xs=[len(c['stages'][-1]['after']) for c in arm['cases']];k=arm['arm_id']
 m['retrieval_accounting']['presented_p50'][k]=statistics.median(xs);m['retrieval_accounting']['presented_p95'][k]=sorted(xs)[round((len(xs)-1)*.95)]
p=A/'artifacts/run-001/result.json';v=read(p);v['followup_audit']=read(A/'artifacts/followup-audit.json');v['followup_continuity_passed']=v['followup_audit']['same_goal_and_prior_evidence']
v['strict_success']=all(v[k] for k in ('all_answers_completed','all_source_checks_passed','all_duplicates_identical_without_calls','candidate_initial_calls_reduced','followup_continuity_passed')) and not v['resource_stops']
v['limitations']=['Known CM requests, one observation per scenario; no legal accuracy or general speed certification.','Supported answer may retain unresolved delegated details. Model can still investigate when it judges no current-question claim support.','Historical ADR0913 unchanged-code baseline; not a simultaneous randomized comparison.','Parent ADR0914 follow-up failure preserved; current utterance and resolved goal now separated without relaxing quote validation.','Probe does not itself change active MAIN or GENOS. Working integration and qualification have separate receipts.']
put(p,v);m['runs'][0]['sha256']=sha(p);put(mfile,m)
p=A/'README.md';s=p.read_text().replace('확보한 원문을 기존 ASSESS에 먼저 전달하고 현재 질문의 근거 있는 답변을 우선 발행한다. 부족 사항은 유지하고 후속 질문으로 이어진다.','현재 발언과 이전 목표 문맥을 분리하고 원문 순서 변화의 재평가를 제거했다. 실제 첫 답변과 같은 목표의 후속 답변이 모두 완료되었으며, 근거가 있는 범위를 먼저 답하고 미확인 범위는 보존한다.');p.write_text(s)
(A/'RESULT.txt').write_text(json.dumps({k:v[k] for k in ('strict_success','comparisons','followup_continuity_passed','limitations')},ensure_ascii=False,indent=2)+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0915','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen candidate verification and observation','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and not p.name.endswith(('-wal','-shm'))]})
print('strict_success',v['strict_success'])
