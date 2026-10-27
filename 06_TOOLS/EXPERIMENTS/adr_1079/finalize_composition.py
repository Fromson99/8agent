"""Bind only completed merge parents and verified MAIN105 before live freeze."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
from common import ROOT, ADR, ART, read, save, sha, exact_write
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_structure as structure


def ref(path):return {'path':str(path.relative_to(ROOT)),'sha256':sha(path)}


def nodes(path):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body
            if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


def main():
    assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
    active_path=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(active_path)
    consumer_path=ROOT/'09_ARTIFACTS/AUDITS/20261027-navigation-validation-main/consumer-active.json'
    consumer=read(consumer_path)
    assert active['generation']==105 and consumer['passed'] is True and consumer['pointer']==active
    assert consumer['binding']['generation']==105 and all(consumer['checks'].values())
    release=read(ROOT/active['manifest_path']);assert sha(ROOT/active['manifest_path'])==active['release_manifest_sha256']
    main_code=ROOT/release['code_root'];composition=read(ART/'main105-alignment-rev2.json')
    code=ROOT/composition['code_root'];perf=ROOT/read(ART/'main105-alignment-plan.json')['performance_code_root']
    assert all(sha(code/p)==h for p,h in composition['files'].items())
    matches={p:sha(main_code/p)==h==sha(perf/p) for p,h in composition['performance_source_files'].items()}
    assert all(matches.values())
    for name in ('_UncacheablePreparation','_preparation_key','CatalogReadPreparation','acquired_blocks'):
        path='02_BACKEND/semantic_runtime/legal_agent/unit_relations.py'
        assert nodes(code/path)[name]==nodes(main_code/path)[name]
    sql='02_BACKEND/semantic_runtime/search_selection.py'
    assert sha(code/sql)==sha(main_code/sql)
    parent_paths=[(ROOT/'04_EXPERIMENTS/ADR/ADR-1077-ontology-task-departure-reference-closure/실험/manifest.json','B1'),
        (ROOT/'04_EXPERIMENTS/ADR/ADR-1081-reference-visibility-valid-fixtures/실험/manifest.json','optimized')]
    loaded=[structure._load_parent(p,arm,'merged_from') for p,arm in parent_paths]
    for data,info in loaded:
        assert data['reservation']['status']=='completed' and data['results']['status']=='complete'
        assert data['results']['by_arm'][info['record']['arm_id']]['status']=='complete'
    exact_write(ART/'main-performance-equivalence.json',{'schema_version':'adr1079-main105-performance-binding-v1',
        'active':ref(active_path),'consumer':ref(consumer_path),'release':ref(ROOT/active['manifest_path']),
        'main_code_root':str(main_code.relative_to(ROOT)),'candidate_code_root':composition['code_root'],
        'main_three_modules_exact_1081':matches,'candidate_search_selection_exact_main':True,
        'candidate_cache_helpers_ast_exact_main':True,'candidate_directory_forwarding':
        'offer_choices -> inspect_directory -> preview/catalog plus acquired-state flags; selected directory behavior preserved',
        'whole_product_equal_to_main':False,'whole_product_performance_equal_to_main':False,'model_calls':0})
    manifest=read(ADR/'실험/manifest.json');exact_write(ART/'manifest-before-final-composition.json',manifest)
    refs=[info['ref'] for _,info in loaded];parent_data=loaded[0][0]
    manifest['lineage'].update(parents=[info['record'] for _,info in loaded],
        root_ref=parent_data['lineage']['root_ref'],
        root_refs=list(dict.fromkeys(data['lineage']['root_ref'] for data,_ in loaded)),
        branch_path=['main105-aligned-ontology'],branch_id='main105-aligned-ontology',
        source_branch_paths={info['ref']:data['lineage']['branch_path'] for data,info in loaded},
        hypothesis_delta='Preserve1077 multi-original departure repair while adopting completed1081 pure preparation/visibility changes in the existing task-local directory path.')
    manifest['design']['arms'][0].update(derived_from=refs,
        changes='1077 B1 plus1081 three performance hunks; directory-specific call forwarding; no prompt/question/model changes.',
        controls='Single CM023 A2; preserved ontology and strict source/state contracts; MAIN105 performance-hunk equality separately bound.')
    manifest['integration']={'type':'multi_parent_merge','parent_refs':refs,'result_arm':'A2','rollback_ref':refs[0],
        'parent_contributions':[{'parent_ref':refs[0],'adopted':'All749file ontology/task-local base including judgment_refs closure','excluded':'None except the declared pure performance hunks and derived pins'},
            {'parent_ref':refs[1],'adopted':'Exact cache helpers/acquired block logic and4TEMP EXISTS; directory call forwarding','excluded':'Legacy MAIN directory behavior and all unrelated420file snapshot contents'}],
        'conflicts':[{'id':'directory-call-closure','between':refs,'resolution':'Keep1077 selected/durable directory behavior and pass one preparation through inspect_directory to preview and acquired state',
            'chosen_from':refs,'rationale':'Whole-file replacement would remove ontology/task-local behavior; only3performance hunk families are adopted.'}],
        'no_conflict_reason':None,'rollback_conditions':'Contract/integrity failure stops the one cell and preservesrev1; no activeMAIN modification.'}
    for number in (1078,1080):
        path=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number}-*'))
        manifest['relationships'].append(structure._load_related_adr(path,'informed_by',
            'Failed intermediate validation preserved; not a completed merge parent.'))
    plan=read(ART/'implementation-plan-rev1-unexecuted.json')
    plan.update(scope='Single CM023 A2 live transition after1077 repair and completed1081 performance-hunk alignment with actual MAIN105.',
        completed_parents=refs,product_changes=list(composition['performance_source_files']),
        composition_receipt=ref(ART/'main105-alignment-rev2.json'),main_performance_equivalence=ref(ART/'main-performance-equivalence.json'))
    plan.pop('completed_parent',None)
    plan['success_criteria'][0]='Exact declared rev-002 composition before and after execution: only3performance modules+31pins over preserved1077B1; prompts/model/ontology/task-departure repair unchanged.'
    save(ART/'implementation-plan.json',plan)
    manifest['design']['success_criteria']=deepcopy(plan['success_criteria'])
    manifest['design']['criteria_record']=ref(ART/'implementation-plan.json')
    directory=code.parent.parent.parent;candidate=read(directory/'candidate.json');revision=candidate['revisions'][-1]
    assert revision['revision_id']=='rev-002'
    binding={'candidate_id':candidate['candidate_id'],'experiment_id':manifest['experiment_id'],'arm_id':'A2','run_ids':['run-001'],
        'manifest_path':str((directory/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(directory/'candidate.json'),
        'revision_id':'rev-002','revision_sha256':revision['revision_sha256'],
        'runner_path':str((Path(__file__).parent/'run_matrix.py').relative_to(ROOT)),
        'runner_sha256':sha(Path(__file__).parent/'run_matrix.py')}
    save(ART/'candidate-bindings.json',{'schema_version':'adr1079-composed-candidate-binding-v1','arm_code_bindings':[binding],
        'parent_code_files':composition['old_files'],'composition_code_files':composition['files'],
        'product_changed_files':list(composition['performance_source_files']),'parent_exact':False,
        'main_performance_equivalence':ref(ART/'main-performance-equivalence.json'),'files':749,'model_calls':0,'corpus_loads':0})
    manifest['design']['code_isolation']['candidates']=[binding];save(ADR/'실험/manifest.json',manifest)
    print('Final composition parents and MAIN105 consumer bound; live design freeze still separate.')


if __name__=='__main__':main()
