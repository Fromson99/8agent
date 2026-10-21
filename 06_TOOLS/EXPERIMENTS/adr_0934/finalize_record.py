"""Finalize only closed, audited attempts; no model calls or product edits."""
from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0934-host-source-links-priority';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert len((A/'artifacts/sequence.jsonl').read_text().splitlines())==4
manual=read(A/'artifacts/run-001/manual-review.json');assert len(manual['cases'])==4
for name in ('policy_audit.py','claim_audit.py','scope_audit.py','coverage_audit.py','report.py','archive.py'):
    subprocess.run([sys.executable,str(T/name)],check=True)
working=read(D/'working-before.json');assert all(sha(R/n)==h for n,h in working.items())
assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer']
put(A/'artifacts/final-binding-check.json',{'working_files_unchanged':len(working),'active_pointer_unchanged':True,'genos_executed':False})
p=A/'README.md';p.write_text(p.read_text().replace('status: Proposed','status: Rejected').replace('# 다른 risk_cm 공개 주제 회귀 비교','# 새 원문 갱신 후보의 실제 실행 검증'))
r=read(A/'artifacts/run-001/result.json')
(A/'RESULT.txt').write_text(manual['conclusion']+'\n\n실제 모델 호출: '+str(r['model_calls'])+'회. 신규 원문 일치 검사: '+str(r['new_span_checks'])+'건. 상세 사례는 artifacts/run-001/manual-review.json 및 각 case claim-audit/policy-audit 참조.\nMAIN89와 작업코드387파일은 그대로 보존, RP단독수정은 독립 보존. GENOS 실행 및 MAIN 승격 없음.\n')
paths=[A/'RESULT.txt',*T.glob('*.py'),R/'02_BACKEND/lawrag/research/candidates/adr_0934/fixed/candidate.json']
paths += [p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and 'baseline' not in p.relative_to(A/'artifacts').parts]
manifest=read(A/'artifacts/manifest.json')
manifest['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Actual four requests; raw records losslessly archived, exact-source and source-selection audits kept separately.','contains_raw_prompts_and_outputs':p.name.endswith('.gz')} for p in sorted(set(paths))]
put(A/'artifacts/manifest.json',manifest)
for args in (['hash','--path',str(A)],['status','--path',str(A),'--status','completed','--note','Four fixed requests audited; host link assembly and source-selection limitations recorded; MAIN89 unchanged.'],['validate','--path',str(A),'--final']):
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],check=True)
print('Finalized ADR0934; rejected for source-completeness, not promoted.')
