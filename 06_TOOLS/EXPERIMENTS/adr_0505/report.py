"""Preserve exact calls and link qualitative observations; no model requests."""
import json,hashlib,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0505-gemma-numbered-three-case-probe'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '\n```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```\n'
def main():
 m=read(A/'실험/manifest.json');data=read(A/'artifacts/trace-summary.json');res=read(A/'artifacts/run-001/results.json');ledger=read(A/'artifacts/retrieval-stage-ledger.json');findings=read(A/'artifacts/qualitative-findings.json')
 for q in m['questions']:
  cid=q['case_id'];x=next(c for c in data['by_case'] if c['case_id']==cid);base=A/'artifacts/run-001'/cid/'numbered'
  raw='\n'.join('### '+str(p.relative_to(A))+'\n'+block(read(p)) for p in sorted((base/'calls').rglob('*.json')))
  stage=next(c for c in ledger['runs'][0]['arms'][0]['cases'] if c['case_id']==cid)
  sections=[('실행 메타',block(res['cases'][cid]['numbered'])),('사용자 질문 원문',x['question']),('기준답변 — 채점 전용, 제품 입력 비공개',x['reference_answer']),('제품 입력을 구성한 원값',block(read(base/'trace.json'))+'\n### 회수·탈락 단계 원장 — run·arm별\n'+block(stage)),('제품 모델 호출 — run·arm별 실제 원문',raw),('중간 LLM 호출 — router/compiler/verifier/repair','탐색/선택/작성/검토 및 형식 수정은 위 호출 원문에 모두 기록했다. 별도 모델 호출 없음.'),('채점 호출과 반복 판정','자동 평가 모델 호출 없음. Codex가 저장 기준답·전달 원문·실제 응답을 대조했다. 사람이 확정한 평가가 아니며 현재 법률 정답 인증도 아니다.'),('사례 최종 판정',block(findings['cases'][cid]))]
  (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(sections,1)))
 totals=data['totals'];front=(A/'README.md').read_text().split('---',2)[1]
 table='|문항|실제 판단 관측|\n|---|---|\n'+'\n'.join('|'+c['case_id']+'|'+findings['cases'][c['case_id']]['summary']+'|' for c in data['by_case'])
 sections=[('결정 요약',findings['overall']+'\n\n'+table+'\n\n[답변·초안·판단 근거 대조](CASE_REVIEW.md). MAIN/GENOS unchanged.'),('문제와 변경 전 구조','ADR0504 numbered rev-004의 정수 참조를 실제 Gemma 탐색→선택→작성→검토 흐름에서 확인했다. 새 후보는 실험 경로 결속만 바꾸고 판단 프롬프트·스키마·검색 구현은 부모와 동일하다.'),('가설과 사전 판정 기준','[사전 PLAN](PLAN.md), [동결 설계](artifacts/frozen-design.json). 참조 오류 0, 의미 있는 요구 설명 3/3, 중대 조건·범위 오류 0을 확인한다. 원문 미전달·답변 미관측은 판단 오답으로 합산하지 않는다. 호출 한도 14회/문항, 출력 2800 tokens, controller 300초.'),('실험 설계','CM033·CM025·CM050 각 1회, 번호 후보 한 군. 세 문항을 병렬 실행했다. baseline은 계보 참조만이며 재실행하지 않아 전후 효과나 순위·정답률 일반화는 불가하다. 자동 judge 호출 없음.'),('데이터·모델·재현성','기존 공개 질문과 해시 확인한 공개 원문. google/gemma-4-31b-it, OpenRouter DeepInfra FP8, thinking off, temperature 0, fallback 없음. 실제 모델·provider·usage는 원시 response/receipt에 남겼다. Gold는 제품 프로세스가 읽지 않는 별도 파일. 최신 법률/기준답 버전 인증은 수행하지 않았다.'),('결과',table+'\n\n'+block(findings['counts'])+'\n번호 형식 성공과 올바른 판단을 분리하며 초안·검토·최종 답변을 섞지 않는다.'),('사례별 오류 분석','[CASE_REVIEW.md](CASE_REVIEW.md)에 실제 문장과 판단 근거를 남겼다. SQL/게시 오류는 품질 평가 대상에서 제외했다. 단일 사례에서 관측한 문제를 모델 고유 능력 전체로 귀속하지 않는다.'),('비용·지연·회수 규모',block(totals)+'\n소요시간은 자원 로딩 포함. 상세 controller 시간과 호출별 usage는 trace-summary에 있다. 수신 usage 합계는 확인된 비용이며 누락된 청구액을 추정하지 않는다. [회수 원장](artifacts/retrieval-stage-ledger.json)은 실제 관측 source identity와 제품 실행 후에만 결합한 gold를 보존한다.'),('해석',findings['overall']),('한계와 일반화 가능 범위','기존 관측 3문항의 in-sample 단회 확인. 반복 실행·새 holdout·독립 사람 평가 없음. 자동 점수 없음. 원문과 사실을 고정 제공한 순수 적용 판단 실험이 아니므로 검색과 입력의 영향을 분리해서 해석한다.'),('운영 결정·롤백 조건','Proposed, decision_eligible=false. MAIN·GENOS 미변경. 결과 확인 후 제품 코드를 수정하거나 같은 실행을 덮어쓰지 않는다. 후속 수정은 새 ADR로 분기한다.'),('재현 명령','```bash\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0505-gemma-numbered-three-case-probe --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n제품 runner는 run_probe.py --execute. 완료 run 재실행은 새 ADR에서 한다. summarize.py/report.py는 저장 결과 정리만 수행한다.')]
 (A/'README.md').write_text('---'+front+'---\n\n# Gemma 번호 선택 3문항 확인\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# Gemma 3문항 실제 실행 인덱스\n\n'+table+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n\n원시 system/user/schema/response/usage 전체 보존. Gold는 제품 입력 비공개. 자동 채점 호출 없음.\n')
 m['results']['by_arm']['numbered'].update(findings['counts']);m['results']['error_taxonomy']=findings['error_taxonomy'];write(A/'실험/manifest.json',m)
 for args in [['hash','--path',str(A.relative_to(R))]]:subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=R,check=True,stdout=subprocess.DEVNULL)
 files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ['manifest.json','completion.json','validation-final.txt','graph-check.txt'] and not p.name.endswith(('-wal','-shm'))]
 files+=list(Path(__file__).parent.glob('*.py'))+[A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',A/'CASE_REVIEW.md']
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0505/numbered';files+=[C/'candidate.json']+[R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files']]
 write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0505','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact run data, frozen code/input or report'} for p in sorted(set(files))]})
 index=R/'04_EXPERIMENTS/ADR/README.md';t=index.read_text()
 for line in ['- [ADR-0504 번호 참조 구현·기능 점검](ADR-0504-gemma-numbered-reference-wiring/README.md) — 모의 검사 83개 통과, 실제 호출 없음.','- [ADR-0505 Gemma 번호 선택 3문항](ADR-0505-gemma-numbered-three-case-probe/README.md) — CM033·CM025·CM050 실제 실행, 번호 형식과 판단 품질 분리 확인, MAIN 유지.']:
  if line.split('](')[1].split(')')[0] not in t:t+='\n'+line+'\n'
 index.write_text(t)
 checks=[]
 for args,name in [(['validate','--path',str(A.relative_to(R)),'--final'],'validation-final.txt'),(['graph','--adr-root','04_EXPERIMENTS/ADR'],'graph-check.txt')]:
  with (A/'artifacts'/name).open('w') as log:p=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=R,stdout=log,stderr=subprocess.STDOUT)
  checks.append({'command':args,'exit_code':p.returncode,'output':(A/'artifacts'/name).read_text()})
 write(A/'artifacts/completion.json',{'recorded':True,'checks':checks});print(json.dumps(checks,ensure_ascii=False))
if __name__=='__main__':main()
