from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0796/selected/snapshot'
def put(n,s):p=C/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
def edit(n,old,new):p=C/n;s=p.read_text();assert old in s,(n,old);p.write_text(s.replace(old,new))
source=(R/'06_TOOLS/OFFLINE/genos_filename_audit.py').read_text()
core=source[:source.index('def load_helper(')]+source[source.index('def inventory_generation('):source.index('def inventory_raw(')]
core=core.replace('Read-only filename/date inventory. Reports are NOT a RAG activation plan.','Common filename selection for RAW admission and immutable generation visibility.')
core=core.replace("'expected_locations'}", "'expected_locations', 'title_spacing'}")
core=core.replace("keys = {name_key(t) for t in rule['titles']}\n        if titles & keys: raise ValueError('conflicting exception titles')\n        titles.update(keys)","spacing = rule.get('title_spacing', 'any')\n        if spacing not in {'any', 'compact', 'spaced'}: raise ValueError('invalid title spacing rule')\n        keys = {(name_key(t), spacing) for t in rule['titles']}\n        if any(k == old and (s == os or 'any' in {s, os}) for k, s in keys for old, os in titles): raise ValueError('conflicting exception titles')\n        titles.update(keys)")
core=core.replace("if row['title_key'] in keys: return True", "spacing = 'spaced' if re.search(r'\\s', row['title']) else 'compact'\n    if rule.get('title_spacing', 'any') not in {'any', spacing}: return False\n    if name_key(row['title']) in keys: return True")
core=core.replace("rule_members[rule['id']] = members\n        if", "rule_members[rule['id']] = members\n        if rule.get('title_spacing', 'any') != 'any':\n            for r in members: r['title_key'] += '::spacing:' + rule['title_spacing']\n        if")
core += '''\nDEFAULT_EXCEPTIONS = Path(__file__).resolve().parents[2] / '00_SYSTEM/FILENAME_EXCEPTIONS.json'\n\ndef latest_marks(rows):\n    """Serving approval, not certification of a legal effective date."""\n    groups = defaultdict(list)\n    for row in rows: groups[row['document_id']].append(row)\n    return [{'document_id': did, 'source_artifact_sha256': items[0]['source_artifact_sha256'],\n             'is_latest': not all(r['physical_exclusion_candidate'] for r in items),\n             'selection_statuses': sorted({r['status'] for r in items}),\n             'date_verified': False,\n             'locations': [{'path': r['path'], 'title': r['title'], 'date': r['date'],\n                 'status': r['status'], 'reason': r['reason'], 'exception_ids': r.get('exception_ids', [])}\n                 for r in items]} for did, items in sorted(groups.items())]\n'''
put('02_BACKEND/semantic_runtime/filename_versions.py',core)
conf=json.loads((R/'08_DEPLOYMENT/GENOS/handoffs/filename_audit_20261015_r3/FILENAME_EXCEPTIONS.json').read_text())
conf.update(revision='user-20261015-r2',description='사용자 승인 검색용 최신 선택 예외. 날짜의 법적 효력 인증과 구분하며 이 파일에서만 관리한다.')
for rule in conf['rules']:
 if rule['id']=='index-book-20260529':rule.update(titles=['인덱스북','인덱스북운용준칙'],title_spacing='compact',reason='공백 없는 인덱스북운용준칙은 2026-05-29 판본 선택')
conf['rules'].append({'id':'index-book-spaced-preserve','titles':['인덱스북운용준칙'],'title_spacing':'spaced','action':'keep_all','reason':'사용자 정정: 띄어쓰기 있는 인덱스북 운용준칙은 그대로 유지'})
put('00_SYSTEM/FILENAME_EXCEPTIONS.json',json.dumps(conf,ensure_ascii=False,indent=2)+'\n')
# Preserve historical v1 plan API. New policy is explicit, generation/hash-bound.
p=C/'02_BACKEND/lawrag/pipeline/search_selection.py';s=p.read_text();s=s.replace('def plan(generation):','def legacy_plan(generation):',1)
pos=s.index('\ndef activate(')
s=s[:pos]+'''
def plan(generation, *, latest=False, exceptions=None):
    if not latest: return legacy_plan(generation)
    from semantic_runtime.filename_versions import inventory_generation, select, latest_marks, load_exceptions, DEFAULT_EXCEPTIONS
    generation = Path(generation).resolve(strict=True)
    path = Path(exceptions or DEFAULT_EXCEPTIONS).resolve(strict=True)
    config, config_hash = load_exceptions(path)
    rows, binding = inventory_generation(generation)
    events = []; selected = select(rows, config, events); marks = latest_marks(selected)
    if sha(path) != config_hash: raise ValueError('exceptions changed during planning')
    excluded = [dict(document_id=r['document_id'], source_artifact_sha256=r['source_artifact_sha256'],
                     reason='not_latest_selected', paths=[v['path'] for v in r['locations']]) for r in marks if not r['is_latest']]
    return {'schema_version': 'filename-search-selection-v2', 'generation_path': str(generation),
        'generation_id': binding['generation_id'], 'manifest_sha256': binding['manifest_sha256'],
        'store_sha256': binding['store_sha256_declared'], 'metadata_sha256': binding['metadata_sha256'],
        'policy': 'user-approved-retained-set-latest-v2', 'exceptions': {'path': str(path), 'sha256': config_hash, 'value': config},
        'excluded': excluded, 'latest_documents': marks, 'exception_results': events,
        'counts': {'physical_documents': binding['total_physical_documents'], 'internal_documents': len(marks),
            'excluded_documents': len(excluded), 'latest_internal_documents': len(marks)-len(excluded),
            'searchable_documents': binding['total_physical_documents']-len(excluded)},
        'source_database_modified': False, 'index_rebuilt': False, 'model_calls': 0}

''' + s[pos:]
s=s.replace("if plan(generation) != value:","if plan(generation, latest=value.get('schema_version') == 'filename-search-selection-v2',\n            exceptions=value.get('exceptions', {}).get('path')) != value:")
s=s.replace("p.add_argument('--receipt', type=Path)","p.add_argument('--receipt', type=Path)\n    p.add_argument('--latest', action='store_true', help='Apply approved R3 retained selection with latest marks')\n    p.add_argument('--exceptions', type=Path)")
s=s.replace('value = plan(a.generation)','value = plan(a.generation, latest=a.latest, exceptions=a.exceptions)')
p.write_text(s)
# Marked RAW admission before any representation pairing or parsing.
p=C/'02_BACKEND/lawrag/pipeline/document_representations.py';s=p.read_text();start=s.index('def select_latest_internal(');end=s.index('\ndef metadata(',start)
s=s[:start]+'''def select_latest_internal(rows, exceptions_path=None):
    from semantic_runtime.filename_versions import select as select_versions, load_exceptions, DEFAULT_EXCEPTIONS
    config, config_hash = load_exceptions(exceptions_path or DEFAULT_EXCEPTIONS)
    rows = copy.deepcopy(rows)
    inventory = [{'document_id': r['path'], 'filename': Path(r['path']).name, 'path': r['path'],
                  'filename_source': 'raw_filename', 'source_artifact_sha256': r['sha256']}
                 for r in rows if r['source'] == 'internal']
    selected = {r['path']: r for r in select_versions(inventory, config)}
    output, excluded = [], []
    for row in rows:
        row['input_version_policy'] = 'user-approved-retained-set-latest-v2'
        if row['source'] != 'internal': output.append(row); continue
        decision = selected[row['path']]
        latest = not decision['physical_exclusion_candidate']
        row['is_latest'] = latest
        row['filename_version'] = {'policy': row['input_version_policy'], 'is_latest': latest,
            'family_title': decision['title'], 'date': decision['date'], 'status': decision['status'],
            'basis': decision['reason'], 'exception_ids': decision.get('exception_ids', []),
            'exceptions_sha256': config_hash, 'effective_date_verified': False}
        if latest: output.append(row)
        else: excluded.append({'path': row['path'], 'document_id': row['document_id'], 'sha256': row['sha256'],
            'reason': 'superseded_filename_version', 'policy': row['input_version_policy'],
            'selection': row['filename_version'], 'original_preserved': True})
    return output, excluded

''' + s[end:];p.write_text(s)
edit('02_BACKEND/lawrag/pipeline/genos_build.py',"'pairing_content_verified', 'source_title', 'filename_version'):","'pairing_content_verified', 'source_title', 'filename_version', 'is_latest'):")
# New builds default to latest. External-only runs need no internal filter.
for n in ['06_TOOLS/COMMANDS/composed_build.py','06_TOOLS/COMMANDS/genos_data_stages.py']:
 p=C/n;s=p.read_text().replace("p.add_argument('--latest-internal-versions', action='store_true',", "p.add_argument('--latest-internal-versions', action='store_true', default=True,")
 if 'composed' in n:s=s.replace('if args.latest_internal_versions and (args.base_generation or args.exclude_internal):',"if args.exclude_internal: args.latest_internal_versions = False\n    if args.latest_internal_versions and args.base_generation:")
 else:s=s.replace('if args.latest_internal_versions and (scope_path or args.only_internal_pdf or args.limit or args.exclude_internal):',"if args.exclude_internal: args.latest_internal_versions = False\n    if args.latest_internal_versions and (scope_path or args.only_internal_pdf or args.limit):")
 p.write_text(s)
# Serving policy is mandatory for the new MAIN; legacy APIs remain usable for migration.
p=C/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text());v['document_build']['latest_internal_versions']=True;v['document_build']['require_latest_selection']=True;v['document_build']['raw_selection']='Common filename_versions policy before structure; only is_latest internal rows admitted';p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/SCHEMAS/pipeline-v1.schema.json';v=json.loads(p.read_text());v['properties']['document_build']['properties'].update(latest_internal_versions={'type':'boolean'},require_latest_selection={'type':'boolean'});p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
edit('02_BACKEND/semantic_runtime/app.py',"contracts=Contracts(contracts_root)","contracts=Contracts(contracts_root)\n        if contracts.pipeline.get('document_build', {}).get('require_latest_selection'):\n            store.selection.require_latest()")
