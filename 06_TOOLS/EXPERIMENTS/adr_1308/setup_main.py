from pathlib import Path
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;OLD=R/'06_TOOLS/EXPERIMENTS/adr_1301'
s=(OLD/'common.py').read_text().replace('ADR-1301-ordinary-assessment-contract-main','ADR-1308-gold-query-optimization').replace('20261103-ordinary-assessment-contract-main','20261103-gold-query-optimization').replace("RELEASE='ordinary-assessment-20261103-r1'","RELEASE='gold-query-optimized-20261103-r1'")
(T/'common.py').write_text(s)
s=(OLD/'release_prepare.py').read_text().replace("before=read(DES/'working-before.json')","before=b['working_files']").replace("('contracts-r1','regression-r2','native-final')","('contracts-final','regression-final')")
s=s.replace(" and r['active_unchanged']",'').replace("assert read(ART/'scaling/result.json')['status']=='PASS'", "assert read(ART/'oracle-select-final/result.json')['passed']==15")
s=s.replace("'.adr1301'","'.adr1308'")
s=s.replace('Verified ordinary lossless input, shared review relations and host-derived acquired-source bookkeeping; existing semantic validators intact; no legal quality certification','Verified query scope/key pushdown, bounded result reuse, page-only body/card reads, FTS tf and exact ranking, need-bound recovery; preexisting user answer-display changes preserved; real model quality untested')
s=s.replace("'authorization_text':'정리해보고 메인에 반영해'", "'authorization_text':'쿼리 최적화 할 부분 전부 다 찾아봐봐 → 싹다 고쳐봐'")
s=s.replace('Ordinary ASSESS contract cleanup; local MAIN and Gold binding only','User-directed query and stop-logic fixes; local MAIN and Gold binding; separate R7 loader artifact, no field deployment')
a=s.index(" 'known_limits':");b=s.index("put(OUT/'validation.json'",a)
s=s[:a]+" 'known_limits':['Field plan, latency and Dataiku R7 execution unverified','No new Qwen answer test or quality certification','Schema/index/statistics changes require field evidence; existing DDL unchanged'], 'criteria':bind(DES/'criteria.json')})\n"+s[b:]
s=s.replace("'scaling':bind(ART/'scaling/result.json'),", "'oracle_select':bind(ART/'oracle-select-final/result.json'),")
(T/'release_prepare.py').write_text(s)
s=(OLD/'activate.py').read_text().replace("b=read(DES/'baseline.json');", "b={**read(DES/'baseline.json'),**read(DES/'gold-before.json')};")
s=s.replace("assert test['passed']==13", "assert test['passed']>0").replace(" and test['active_unchanged']",'')
s=s.replace('main135','main136').replace('MAIN135','MAIN136').replace("['generation']==135","['generation']==136").replace('rollback_main134','rollback_main135')
s=s.replace('ORDINARY_ASSESSMENT_REAL_QWEN_NOT_CERTIFIED','QUERY_OPTIMIZATION_REAL_QWEN_NOT_CERTIFIED')
(T/'activate.py').write_text(s)
for name in ('main_entry.py','gold_entry.py'):
 s=(OLD/name).read_text().replace("b=read(DES/'baseline.json')", "b={**read(DES/'baseline.json'),**read(DES/'gold-before.json')}")
 s=s.replace('main135','main136').replace('MAIN135','MAIN136').replace("['generation']==135","['generation']==136").replace("['generation']==134","['generation']==135").replace('rollback_main134','rollback_main135')
 (T/name).write_text(s)
# Check only the prepared serving files while tests remain outside the release.
p=T/'check.py';s=p.read_text().replace("p.add_argument('--name',required=True);", "p.add_argument('--name',required=True);p.add_argument('--prepared',action='store_true');")
s=s.replace("f=json.loads((ADR/'artifacts/design/freeze.json').read_text());C=ROOT/f['code_root']", "f=json.loads((ADR/'artifacts/design/freeze.json').read_text())\nif args.prepared:f=json.loads((ROOT/'08_DEPLOYMENT/RELEASES/gold-query-optimized-20261103-r1/release.json').read_text())\nC=ROOT/f['code_root']")
p.write_text(s)
print('Main scripts ready')
