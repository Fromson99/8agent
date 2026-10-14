from pathlib import Path
import subprocess
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication';S=C/'snapshot';T=S/'05_TESTS/CONTRACTS'
p=S/'02_BACKEND/semantic_runtime/legal_agent/successful_answer.py';p.write_text(p.read_text().replace("h=c.pop('hash')","h=c.pop('payload_hash')"))
p=T/'test_successful_core_routes.py';p.write_text(p.read_text().replace('with cases.transaction():record','with cases.shortcut.transaction():record'))
p=T/'test_ad_language.py';s=(R/'05_TESTS/CONTRACTS/test_ad_language.py').read_text();s=s.replace('    repo.close()\n    count=[0]', '''    repo.close()
    from test_successful_core_routes import seed_ad_case
    for i,ident in enumerate(ids):seed_ad_case(path,ident,principal,f'case-{i}')
    count=[0]''');p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target','05_TESTS/CONTRACTS/test_ad_language.py','--upstream-state','present'],check=True,stdout=subprocess.DEVNULL)
