"""Register the identical validated compiler bytes for the A1 experimental arm.

The two candidates have the same file map. A0/A1/A2 use one frozen code root;
only the explicit runtime ontology mode differs. No live model or data load.
"""
from common import *
import argparse
import shutil
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--origin', default='compiler-r4', choices=['compiler-r4', 'compiler-r5'])
    parser.add_argument('--candidate', default='compiler-a1', choices=['compiler-a1', 'compiler-a1-r5'])
    parser.add_argument('--receipt', default='compiler-a1-identical-code.json',
        choices=['compiler-a1-identical-code.json', 'compiler-a1-r5-identical-code.json'])
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
    import adr_candidate as candidates
    origin = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1041' / args.origin
    value = read(origin / 'candidate.json')
    assert not candidates.validate(origin)
    frozen = origin / 'revisions/rev-001/snapshot'
    present = [r['target_path'] for r in value['files'] if (ROOT / r['target_path']).is_file()]
    target = candidates.snapshot(ADR, args.candidate, present,
        experiment_id='ADR-1041-experiment-v1', arm_id='A1', run_ids=['run-001'])
    for row in value['files']:
        name = row['target_path']
        source = frozen / name
        assert sha(source) == row['snapshot_sha256']
        dest = target / 'snapshot' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        if name not in present:
            candidates.register_file(target, target=name, upstream_state='absent')
    candidates.refresh(target)
    candidates.freeze(target)
    assert not candidates.validate(target)
    other = read(target / 'candidate.json')
    assert {r['target_path']:r['snapshot_sha256'] for r in other['files']} == {
        r['target_path']:r['snapshot_sha256'] for r in value['files']}
    exact_write(ART / args.receipt, {
        'schema_version':'ontology-identical-arm-code-v1',
        'origin':str(origin.relative_to(ROOT)), 'origin_manifest_sha256':sha(origin/'candidate.json'),
        'registered_a1':str(target.relative_to(ROOT)), 'a1_manifest_sha256':sha(target/'candidate.json'),
        'identical_files':len(value['files']), 'same_code_root_for_execution':str(frozen.relative_to(ROOT)),
        'only_runtime_arm_difference':'candidate_navigation.ontology_context mode and presentation',
        'live_model_calls':0})
    print('Identical A1 registration:', len(value['files']), 'files')


if __name__ == '__main__':
    main()
