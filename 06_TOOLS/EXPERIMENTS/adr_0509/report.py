"""Render exact paired records and the explicit post-run evidence audit."""
import json,hashlib,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0509-gemma-search-skill-harness-paired'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '\n```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```\n'
def main():
 m=read(A/'실험/manifest.json');data=read(A/'artifacts/trace-summary.json');res=read(A/'artifacts/run-001/results.json');ledger=read(A/'artifacts/retrieval-stage-ledger.json');audit=read(A/'artifacts/qualitative-findings.json')
 for q in m['questions']:
  cid=q['case_id'];rows=[x for x in data['by_case'] if x['case_id']==cid];raw=[];traces=[];stages=[]
  for arm in ('baseline','integrated'):
   base=A/'artifacts/run-001'/cid/arm
   raw.append('### '+arm+'\n'+'\n'.join('#### '+str(p.relative_to(A))+'\n'+block(read(p)) for p in sorted((base/'calls').rglob('*.json'))))
   traces.append('### '+arm+'\n'+block(read(base/'trace.json')))
   rec=next(a for a in ledger['runs'][0]['arms'] if a['arm_id']==arm)
   stages.append('### '+arm+'\n'+block(next(c for c in rec['cases'] if c['case_id']==cid)))
  sections=[('실행 메타',block(res['cases'][cid])),('사용자 질문 원문',rows[0]['question']),('기준답변 — 채점 전용, 제품 입력 비공개',rows[0]['reference_answer']),('제품 입력을 구성한 원값','\n'.join(traces)+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n'+'\n'.join(stages)),('제품 모델 호출 — run·arm별 실제 원문','\n'.join(raw)),('중간 LLM 호출 — router/compiler/verifier/repair','탐색·선택·작성·검토·형식 수정은 위 호출 기록에 포함. 별도 모델 없음.'),('채점 호출과 반복 판정','자동 judge 호출 없음. Codex가 저장 질문·기준답·원문·실제 최종 출력을 대조한 감사. 사람 확정 평가나 최신 법률 인증 아님.'),('사례 최종 판정',block(audit['cases'][cid]))]
  (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
 table='|문항|기준 최종 답변|보강 최종 답변|보강 원문 전달/필수|주요 관측|\n|---|---|---|---|---|\n'
 for cid,f in audit['cases'].items():
  rows={x['arm']:x for x in data['by_case'] if x['case_id']==cid}
  table+='|'+cid+'|'+str(bool(rows['baseline']['answer'].get('claims')))+'|'+str(bool(rows['integrated']['answer'].get('claims')))+'|'+str(rows['integrated']['gold_by_stage']['presented'])+'/'+str(rows['integrated']['gold_total'])+'|'+f['summary']+'|\n'
 front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed', 'status: Rejected')
 sections=[('결정 요약',audit['overall']+'\n\n'+table),('문제와 변경 전 구조','선택된 로컬 v5 release r3를 기준으로, 스킬 지침을 기존 ModelGateway 단계에 결속하고 원문 전달·선택·인용·커서 복구를 보강했다. 후보 4개 제품 모듈과 공유 실험 어댑터만 변경. 연구 snapshot이며 MAIN/GENOS unchanged.'),('가설과 사전 판정 기준','[PLAN](PLAN.md), [호출 전 동결 설계](artifacts/frozen-design.json). 검토된 비어 있지 않은 최종 답변4/6 이상 및 기준 대비 증가, 적합 답변 최소1 증가·회귀0, 문항별 필수 근거 전달 회귀0, 입력토큰2배/지연1.5배 이하. 형식 통과만으로 품질 성공 판정하지 않는다.'),('실험 설계','공개 CM6 단회 paired probe, 두 arm 같은 모델·데이터·14호출/56도구/300초/60000자/6400출력. 문항마다 arm 제출 순서를 번갈아 최대2프로세스로 실행. 여러 하네스 변경과 스킬을 합친 효과이며 개별 요소의 인과 효과는 분리하지 않았다.'),('데이터·모델·재현성','google/gemma-4-31b-it, DeepInfra FP8, thinking off, temperature0, fallback 없음. 기존 승인 공개145문서와 RAW hash 검증. 사용자 명시 Gemma 요청에 대한 실험 한정 policy, MAIN Qwen 기본값 불변. Gold는 제품 실행 후에만 결합. 기존 법률·기준답 판본의 최신성 재인증은 없음.'),('결과',table+'\n'+block(audit['counts'])+'\n'+block(data['criteria'])),('사례별 오류 분석','[CASE_REVIEW](CASE_REVIEW.md), [질문별 전체 입출력](실험/README.md). 미완료·원문 미전달·형식 오류·내용 오류를 분리한다.'),('비용·지연·회수 규모',block(data['by_arm'])+'\n[단계 원장](artifacts/retrieval-stage-ledger.json). 호출 usage 합계이며 미확인 청구는 추정하지 않는다. wall은 로딩 포함, controller 지연은 별도. n=6의 p95는 nearest-rank 최댓값이며 안정적인 서비스 지연 추정이 아니다. canonical 최종 present 단계는 최종 인용이며 모델 전달 recall은 presented 단계로 별도 표시.'),('해석',audit['overall']),('한계와 일반화 가능 범위','6문항은 지침 설계에 사용한 in-sample 사례다. 단회·모델 한 종류·외부 provider이며 소형 모델 일반화, 실제 내부 자료 또는 GENOS 현장 성능을 보장하지 않는다. 감사 판정은 독립 사람 확정이 아니다.'),('운영 결정·롤백 조건','Rejected, decision_eligible=false. 사전 성공 기준 미충족으로 이번 통합 후보 채택을 기각한다. [실제 보강 범위](IMPLEMENTATION.md), [후속 변경 후보](NEXT_STEPS.md). 활성 MAIN 포인터·운영 코드·모델 기본값·데이터 세대 불변. 후보를 적용하지 않아 운영 롤백 불필요. 새로운 수정·재실행은 새 ADR. 56개 관련 합성 계약 통과; 새 GENOS 자동 모델 결속 작업에 대한 2개 테스트는 선택 릴리스와 버전이 달라 제외.'),('재현 명령','```bash\n.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0509/integrated\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0509-gemma-search-skill-harness-paired --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n완료 run은 재실행/덮어쓰기하지 않는다. 검증 결과는 artifacts/completion.json 참조. 전체 graph의 기존 오류는 이번 ADR 오류와 분리한다.')]
 (A/'README.md').write_text('---'+front+'---\n\n# 검색 스킬·하네스 Gemma 비교\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
 (A/'CASE_REVIEW.md').write_text('# 문항별 감사\n\n'+audit['overall']+'\n\n'+table+'\n\n'+'\n\n'.join('## '+cid+'\n\n'+block(f) for cid,f in audit['cases'].items())+'\n')
 (A/'실험/README.md').write_text('# 기준·보강 Gemma 전체 기록\n\n'+table+'\n'+ '\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
 m['results']['comparisons']=[x for x in m['results']['comparisons'] if x!=audit['counts']]+[audit['counts']];m['gemma_binding']['live_calls']=sum(x['physical_calls'] for x in data['by_arm'].values());write(A/'실험/manifest.json',m)
 subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(A.relative_to(R))],check=True,stdout=subprocess.DEVNULL)
 files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ['manifest.json','completion.json','validation-final.txt','graph-check.txt'] and not p.name.endswith(('-wal','-shm'))]
 files+=list(Path(__file__).parent.glob('*.py'))+[A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',A/'CASE_REVIEW.md',A/'IMPLEMENTATION.md',A/'NEXT_STEPS.md']
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0509/integrated';files+=[C/'candidate.json']+[R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files']]
 write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0509','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact run, frozen candidate, input or evidence audit'} for p in sorted(set(files))]})
if __name__=='__main__':main()
