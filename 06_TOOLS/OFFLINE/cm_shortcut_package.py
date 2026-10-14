"""Build a portable, source-only registration package from the reviewed CM corpus."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from semantic_runtime.storage import Store
from lawrag.pipeline.shortcut_package import SCHEMA, TARGET_BINDING, text_sha


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(root, generation, output, package_id, *, common=False, target_selected=False):
    corpus = root/'01_DATA/review/cm_core_e2e_v3.json'
    data = json.loads(corpus.read_text())
    # A complete historic run has a recorded non-answer for every CM case.
    # Later semantic failures are supplementary provenance, not a new regrade.
    failures = root/'04_EXPERIMENTS/ADR/ADR-0426-cm-glossary-network-validation/artifacts/grading/results.json'
    old = json.loads(failures.read_text())['results']
    records = {c['id']: [] for c in data['cases']}
    for i, row in enumerate(old):
        if row.get('correct') is False and not row.get('error') and row.get('rubric_consistent') is True:
            records[row['case_id']].append({'artifact': str(failures.relative_to(root)),
                'artifact_sha256': sha(failures), 'record': 'results/'+str(i),
                'kind': 'HISTORICAL_NON_ANSWER', 'product_sha256': row['product_sha256']})
    if any(not r for r in records.values()):
        raise ValueError('every selected CM case needs a real recorded failure')
    store = Store(generation)
    try:
        cases = []
        for case in data['cases']:
            entries = []
            for a in case['evidence_articles']:
                docs = list(store.db.execute('SELECT * FROM document WHERE name=?', (a['law'],)))
                units = [(d,u) for d in docs for u in store.db.execute('SELECT * FROM source_unit WHERE document_id=?', (d['document_id'],))
                         if json.loads(u['json']).get('coordinate_key') == a['coordinate_key']]
                if len(units) != 1:raise ValueError('ambiguous/missing article '+case['id']+' '+a['law']+' '+a['article'])
                doc,unit = units[0]
                section = store.section(doc['document_id'],unit['unit_id'])
                entries.append({'document_name': a['law'], 'coordinate_key': a['coordinate_key'],
                    'source_artifact_sha256': doc['source_artifact_sha256'],
                    'section_text_sha256': text_sha('\n'.join(b['text'] for b in section['blocks'])),
                    'evidence_role': a['evidence_role_v3'], 'gold_source_version': {
                        k:a.get(k) for k in ('document_revision','document_enforcement','authority_as_of','source_text_sha256')},
                    'selected_document_id': doc['document_id'], 'selected_unit_id': str(unit['unit_id'])})
            cases.append({'case_id': case['id'], 'question': case['question'], 'topic': case['topic'],
                'question_aliases': [case['source_question'], '벤처기업의 주식매수선택권은 언제부터 행사할 수 있나요?'] if case['id']=='cm-016' else [],
                'alias_provenance': 'CM-016 literal original question and ADR0684 photo-normalized reproduction; source entries only' if case['id']=='cm-016' else None,
                'entries': entries, 'reference_answer': case['reference_answer'],
                'reference_provenance': {'corpus_sha256':sha(corpus),'case_id':case['id'],
                    'reference_sha256':case['reference_sha256'],'status':'ACTUAL_WORK_REFERENCE; CURRENT_INTERPRETATION_UNVERIFIED'},
                'historical_failures':records[case['id']]})
        package = {'schema_version': SCHEMA, 'package_id': package_id,
            'registration_authority': 'USER_REQUEST_2026-10-07',
            'visibility':'COMMON_CATALOG' if common else 'PRIVATE_OWNER_TEAM',
            'question_export': 'NOT_AUTHORIZED_FOR_EXTERNAL_MODEL', 'legal_claim_reuse':False,
            'training_cases':True,'benchmark_warning':'Known CM seeds after registration are in-sample; do not count as unseen success.',
            'source':{'path':str(corpus.relative_to(root)),'sha256':sha(corpus),'schema':data['schema_version']},
            'built_against':{'generation':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256']},
            'counts':{'cases':len(cases),'source_entries':sum(len(c['entries']) for c in cases)},'cases':cases}
        if target_selected:
            layout = json.loads((root/'01_DATA/CATALOG/TEAM_LAYOUT.json').read_text())
            aliases = {}
            for path, item in layout['files'].items():
                if item.get('source') == 'external' and item.get('role') == 'body':
                    aliases.setdefault(item.get('scope_document') or item.get('name'), set()).update(
                        (Path(path).name, Path(path).stem))
            package.update(source_binding_policy=TARGET_BINDING,
                           target_source_interpretation='CURRENT_SOURCE_REQUIRES_ASSESSMENT',
                           reference_built_against=package.pop('built_against'),
                           reference_hash_policy='local hashes are provenance only; bind target source and article bytes at import')
            for case in cases:
                for entry in case['entries']:
                    entry['document_name_aliases'] = sorted(aliases.get(entry['document_name'], set()))
        store.check_unchanged()
    finally:store.close()
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('preserve completed package; use a new output path')
    output.write_text(json.dumps(package,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'path':str(output),'sha256':sha(output),**package['counts']},ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--generation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--package-id',required=True)
    parser.add_argument('--common',action='store_true')
    parser.add_argument('--target-selected-source',action='store_true',help='explicit onsite title/alias/article binding; preserve local hashes as reference provenance')
    args = parser.parse_args()
    build(args.root,args.generation,args.output,args.package_id,common=args.common,target_selected=args.target_selected_source)
