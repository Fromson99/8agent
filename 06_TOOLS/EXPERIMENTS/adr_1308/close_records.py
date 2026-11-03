from common import *
# Clarify that ten follow-up tests include five loader checks and other smoke checks.
for p in (OUT/'수정과_검증_메인반영결과.txt',ADR/'README.md',ADR/'실험/001-query-contracts.md'):
 s=p.read_text().replace('음수·0을 포함한 모든 행 경계 재개10검사가 통과했다','음수·0을 포함한 모든 행 경계 재개 검사 등 후속10개 검사가 통과했다')
 p.write_text(s)
put(ART/'preparation-failures.json',{'failures':[
 {'stage':'contracts-r1','error':'pytest plugin hook argument r must be report','product_execution':False},
 {'stage':'regression-final-r1','error':'Legacy ontology collection imported a non-serving lawrag.platform.main_promotion module','product_execution':False},
 {'stage':'scope followup freeze','error':'Upstream changed after working integration; old provenance rejected. Partial revision retained; new scope-fixed candidate used.','product_execution':False},
 {'stage':'followup record creation','error':'Immutable summary/backup name collision rejected overwrite; separate design-final/final output/preflight-r2 paths used.','product_execution':False}],
 'scope_cache_failure':bind(ART/'scope-final/result.json'),'original_ontology_fixture_failures':bind(ART/'prior-fixtures/result.json'),
 'initial_oracle_fixture_failure':bind(ART/'oracle-select-r1/failure.json')})
put(ART/'support-files-final.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
paths=sorted({p for p in ART.rglob('*') if p.is_file() and not p.is_symlink() and p!=ART/'manifest.json'}|{p for p in OUT.rglob('*') if p.is_file() and not p.is_symlink()})
m=read(ART/'manifest.json');m['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Verified query implementation record; failed and successful stages preserved','contains_raw_prompts_and_outputs':p.name=='runtime.tar.gz'} for p in paths]
(ART/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
print('Indexed',len(paths),'artifacts including failed runs and runtime archives')
