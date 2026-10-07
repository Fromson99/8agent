"""Freeze the already verified success scope into a fresh release run, without a base."""
import inspect
import json
from pathlib import Path
from semantic_runtime.contracts import sha
from lawrag.pipeline import document_release, reference_resolution, structure_selection


def freeze(data, *, expected_count=2121, new_run='financial-risk-success-20261001-r2', replace_corpus=False):
    data = Path(data).resolve(strict=True)
    parent = 'financial-risk-full-e2e-20260930-r3'
    old_run = 'financial-risk-success-20261001-r1'
    for run in (parent, old_run, new_run):
        from lawrag.pipeline.genos_status import validate_run_id
        validate_run_id(run)
    if new_run in (parent, old_run):
        raise ValueError('A separate follow-up run is required')
    # This handoff assumes the already applied R3 wiring, never silently replaces code.
    if ('reference_profile' not in inspect.signature(document_release.build).parameters
            or not callable(getattr(reference_resolution, 'advance', None))
            or '--reference-model-profile' not in inspect.getsource(document_release.main)):
        raise ValueError('R3 release wiring required; no code was patched by this script')
    if replace_corpus:
        from lawrag.pipeline import glossary_document_update
        if ('glossary_corpus_policy' not in inspect.signature(document_release.build).parameters
                or '--glossary-corpus-policy' not in inspect.getsource(document_release.main)
                or 'corpus_policy' not in inspect.signature(glossary_document_update.augment).parameters
                or not callable(getattr(glossary_document_update, 'replace_corpus', None))):
            raise ValueError('Field glossary corpus replacement contract missing; build refused')
        from lawrag.pipeline import term_generation
        from semantic_runtime import term_index
        audit_split = ('audit_output=' in inspect.getsource(term_generation.build_generation)
                       and 'separate_navigation' in inspect.getsource(term_index.compile_index))
        print('FIELD index build/audit separation wired=' + str(audit_split), flush=True)
        if not audit_split:
            print('WARNING: local index compaction wiring is not confirmed in this field code; no silent patch.', flush=True)
    profile = data / 'LOGS' / parent / 'reference-model-profile.json'
    if not profile.is_file():
        raise FileNotFoundError(profile)
    old_path = data / 'LOGS' / old_run / 'structure-selection.json'
    old = json.loads(old_path.read_text())
    if len(old['documents']) != expected_count:
        raise ValueError('Unexpected selection count; review scope before building')
    print('VERIFY frozen successful scope including adopted DOCX retries', flush=True)
    _, pins = document_release.selected_sources(data, old_run, [])
    current = json.loads((data / 'LOGS' / parent / 'structure-selection.json').read_text())
    if current['documents'] != old['documents']:
        raise ValueError('Parent successes changed since the 2121-document snapshot; review scope first')
    print('SELECT new run; no parsing or structure model calls', flush=True)
    result = structure_selection.select_completed(
        data, parent, new_run, allow_incomplete=True,
        reason='User approved existing successful structures including DOCX retries only; legacy NFS base excluded')
    new = json.loads((data / 'LOGS' / new_run / 'structure-selection.json').read_text())
    if new['documents'] != old['documents']:
        raise ValueError('Selected scope changed; build refused')
    for path, expected in pins.items():
        if sha(path) != expected:
            raise ValueError('Frozen source changed during selection: ' + path)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    print('BUILD scope=2121 selected structures; base_generations=[]; activation=false', flush=True)
    return result
