from common import *
T=Path(__file__).parent
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1292/release_prepare.py').read_text()
s=s.replace("RELEASE='ontology-console-20261103-r1'",'')
s=s.replace("('contracts-final','oracle-create-r2','oracle-read','oracle-withdraw')", "('contracts-r1','regression-r2','native-final')")
s=s.replace("assert all(sha(ROOT/n)==h for n,h in before.items()),'concurrent upstream drift'", "assert all(sha(ROOT/n)==h for n,h in before.items()),'concurrent upstream drift'\nassert read(ART/'scaling/result.json')['status']=='PASS'")
s=s.replace("'.adr1292'", "'.adr1301'")
s=s.replace('Verified console/authoring connections and lossless scenario calculation/history display; no legal quality certification','Verified ordinary lossless input, shared review relations and host-derived acquired-source bookkeeping; existing semantic validators intact; no legal quality certification')
s=s.replace('Separately bound console/test/research dependency outside serving closure','Unchanged console/test/research dependency outside serving closure')
a=s.index("put(OUT/'authorization.json'");b=s.index("put(OUT/'validation.json'",a)
s=s[:a]+"""put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'정리해보고 메인에 반영해',
 'scope':'Ordinary ASSESS contract cleanup; local MAIN and Gold binding only',
 'quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,
 'known_limits':['ADR1297 actual scenario UNKNOWN and no full pass preserved','Independent semantic/scope review remains; incremental review not implemented','New effect on real Qwen quality and large-data latency unverified'], 'criteria':bind(DES/'criteria.json')})
"""+s[b:]
s=s.replace("'verification':{n:bind(ART/n/'result.json')", "'scaling':bind(ART/'scaling/result.json'),'verification':{n:bind(ART/n/'result.json')")
(T/'release_prepare.py').write_text(s)
s=(T/'check.py').read_text();a=s.index('freeze=read(');b=s.index('\nassert all',a)
s=s[:a]+"release=read(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json');C=ROOT/release['code_root'];freeze={'files':release['files'],'pointer_sha256':read(DES/'baseline.json')['active_sha256']};out=ART/args.name;out.mkdir(exist_ok=False)"+s[b:]
(T/'check_prepared.py').write_text(s)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1292/activate.py').read_text()
s=s.replace(";package=read(OUT/'ui-package-check.json')",'').replace("assert package['passed']\n",'')
s=s.replace("assert test['passed']==14", "assert test['passed']==13")
s=s.replace('main134','main135').replace('MAIN134_CONSOLE_INTEGRATION_REAL_QWEN_NOT_CERTIFIED','MAIN135_ORDINARY_ASSESSMENT_REAL_QWEN_NOT_CERTIFIED').replace('MAIN134','MAIN135').replace("active['generation']==134","active['generation']==135")
s=s.replace('rollback_main133','rollback_main134')
s=s.replace(", 'ui_package':bind(OUT/'ui-package.json')",'').replace(",'ui_package':bind(OUT/'ui-package.json')",'')
s=s.replace('; separate UI package verified','; original data/settings preserved')
(T/'activate.py').write_text(s)
for name in ('main_entry.py','gold_entry.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1292'/name).read_text().replace('main134','main135').replace('MAIN134','MAIN135').replace("['generation']==134","['generation']==135").replace("['generation']==133","['generation']==134").replace('rollback_main133','rollback_main134')
 (T/name).write_text(s)
print('Prepared local release scripts, no application yet')
