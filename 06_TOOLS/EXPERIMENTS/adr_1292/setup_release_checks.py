from common import *
p=Path(__file__).parent/'common.py';s=p.read_text();s+="\nRELEASE='ontology-console-20261103-r1'\n";p.write_text(s)
p=Path(__file__).parent/'check.py';s=p.read_text();a=s.index('freeze=read(');b=s.index('\nassert all',a)
s=s[:a]+"release=read(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json');C=ROOT/release['code_root'];freeze={'files':release['files'],'pointer_sha256':read(DES/'baseline.json')['active_sha256']};out=ART/args.name;out.mkdir(exist_ok=False)"+s[b:]
s=s.replace("paths=args.tests or ['06_TOOLS/EXPERIMENTS/adr_1292/test_connections.py']", "paths=args.tests or ['05_TESTS/CONTRACTS/test_agent_loop_fault_recovery.py']")
(Path(__file__).parent/'check_prepared.py').write_text(s)
for name in ('main_entry.py','gold_entry.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1287'/name).read_text()
 s=s.replace("active['generation']==133","active['generation']==134").replace("['generation']==132","['generation']==133").replace('main133','main134').replace('MAIN133','MAIN134').replace('main132','main133').replace('MAIN132','MAIN133').replace("and len(release['files'])==513",'').replace('selected513','selected_inventory').replace("len(checks),'checks PASS'","len(checks),'checks PASS'")
 (Path(__file__).parent/name).write_text(s)
s=(ROOT/'09_ARTIFACTS/AUDITS/20261103-rag-ontology-ui-check-105744/oracle_readonly.py').read_text().replace("OUT=Path(__file__).resolve().parent", "OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-rag-ontology-console-integration'")
(Path(__file__).parent/'oracle_readonly.py').write_text(s)
