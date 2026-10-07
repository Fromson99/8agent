"""Finalize descriptive report and append-only experiment artifacts after runs."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0673-investigation-chain-cm-six'
D=R/'09_ARTIFACTS/AUDITS/20261006-investigation-chain-cm-six'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');rows=read(A/'artifacts/offline-review.json')['cases']
sections=(A/'README.md').read_text().split('## ')
for i,s in enumerate(sections):
 if s.startswith('6. 결과'):
  table=['6. 결과','', '| 사례 | HTTP | 초 | 모델 호출 | 필수 조문 일부접촉 / 전체확보 / 채택 | 판단 이유 유지 |',
   '|---|---:|---:|---:|---:|---|']
  for x in rows:table.append(f"| {x['case_id']} | {x['http_status']} | {x['request_seconds']:.1f} | {x['model_calls']} | {x['same_law_article_required_acquired']}/{x['required_total']} · 전체{x['same_law_article_full_original_covered']}/{x['required_total']} · 채택{x['same_law_article_adopted']}/{x['required_total']} | {x['history_preserved']} |")
  table+=['','실행 성공률과 정답률을 분리한다. 독립 judge 정답 채점은 하지 않았고, 동결 기준답변과 실제 전체 답변은 각 질문 파일과 로컬 대조 보고서에 보존한다.','']
  sections[i]='\n'.join(table)
 if s.startswith('8. 비용·지연·회수 규모'):
  sections[i]='8. 비용·지연·회수 규모\n\n```json\n'+json.dumps({'usage':m['results']['usage'],'latency':m['results']['latency'],'retrieval_accounting':m['retrieval_accounting']},ensure_ascii=False,indent=2)+'\n```\n\n회수 단위는 정확한 document ID와 조 root coordinate다. 현재 실행과 골든 버전이 다른 경우 같은 법령·조문 확보와 정확한 골든 버전 확보를 별도로 기록한다. 정본 단계 원장은 artifacts/stage-ledger.json이다.\n\n'
 if s.startswith('12. 재현 명령'):
  sections[i]='12. 재현 명령\n\n```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0673/run_probe.py --case cm-003\n```\n\n고정 사례는 cm-003, cm-018, cm-038, cm-039, cm-043, cm-051이다. 이미 있는 결과 폴더의 덮어쓰기를 거부한다. 완료 후 반복·수정은 새 ADR로 선점한다.\n'
(A/'README.md').write_text('## '.join(sections))
v=read(D/'verification.json');v['source_coverage']=rows;v['legal_accuracy_scored']=False
v['unchanged_parent_product_code']=read(A/'artifacts/design/unchanged-parent-code.json');put(D/'verification.json',v)
tools={str(p.relative_to(R)):sha(p) for p in (R/'06_TOOLS/EXPERIMENTS/adr_0673').glob('*.py')}
put(A/'artifacts/report-tool-bindings.json',{'product_runner_unchanged':True,'tools':tools,'offline_model_calls':0})
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.suffix in ('.json','.txt','.log','.md') and '/generation-shadow/' not in str(p) and '/runtime/' not in str(p) and p!=A/'artifacts/manifest.json']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],
 'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact frozen design/run/provider or offline accounting receipt'} for p in files]})
index=R/'04_EXPERIMENTS/ADR/README.md';s=index.read_text();link='- [ADR-0673 탐색 행동 체인 CM 추가 6사례](ADR-0673-investigation-chain-cm-six/README.md) — 동결 ADR0672 제품 코드와 신규 CM 질문6건; MAIN 불변.'
if 'ADR-0673-investigation-chain-cm-six/README.md' not in s:index.write_text(s.rstrip()+'\n'+link+'\n')
print('Six-case descriptive report and artifact hashes saved; MAIN unchanged.')
