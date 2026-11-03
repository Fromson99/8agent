"""Read-only follow-up bound to one existing comparison and installed loader."""
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read(path, limit=32*1024**2):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    after = path.stat()
    if len(raw)>limit or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('INPUT_TOO_LARGE_OR_CHANGED')
    return json.loads(raw)


def write(path, value):
    path = Path(path)
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(canonical(value), encoding='utf-8')
    tmp.replace(path)


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,127}',value):
        raise ValueError('INVALID_IDENTIFIER')
    return value


def literal(value):
    if not isinstance(value,str) or len(value)>256 or '\0' in value:
        raise ValueError('INVALID_LITERAL')
    return "'"+value.replace("'","''")+"'"


def error(exc):
    result = {'type':type(exc).__name__, 'codes':sorted(set(re.findall(r'(?:ORA|PLS)-\d{5}',str(exc))))}
    if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]{1,120}',str(exc)):
        result['reason'] = str(exc)
    return result


def locate(explicit='', hints=(), cwd=None):
    if explicit:
        path = Path(explicit).expanduser().resolve(strict=True)
        if path.name!='COMPARISON.json': raise ValueError('SELECT_COMPARISON_JSON')
        return path
    candidates = set()
    for item in hints:
        if item:
            path = Path(item).expanduser().resolve()
            if path.is_dir(): path = path/'COMPARISON.json'
            if path.name=='COMPARISON.json' and path.is_file(): candidates.add(path)
    if len(candidates)==1: return candidates.pop()
    if len(candidates)>1: raise ValueError('MULTIPLE_HINTS_SET_COMPARISON_PATH')
    root = Path(cwd or Path.cwd())/'gold-comparison-reports'
    for n,path in enumerate(root.glob('*/COMPARISON.json')):
        if n>=256: raise ValueError('REPORT_DISCOVERY_LIMIT')
        candidates.add(path.resolve())
    if len(candidates)!=1: raise ValueError('SET_EXACT_COMPARISON_PATH')
    return candidates.pop()


def bind(report_path):
    path = Path(report_path).resolve(strict=True)
    report = read(path)
    config = read(path.parent/'worker-config.json')
    if report.get('status') not in ('COMPLETE','PARTIAL'):
        raise ValueError('COMPARISON_NOT_COMPLETED')
    if report.get('original_state_unchanged') is not True:
        raise ValueError('COMPARISON_STATE_UNCONFIRMED')
    for key in ('run_id','plan_sha256'):
        if not report.get(key) or report[key]!=config.get(key): raise ValueError('REPORT_CONFIG_MISMATCH')
    ctx = config['context']
    state_path = Path(ctx['state_dir']).resolve(strict=True)/'state.json'
    state = read(state_path)
    original_sha = hashlib.sha256(state_path.read_bytes()).hexdigest()
    if state!=ctx['state'] or original_sha!=report.get('original_state_sha256_after'):
        raise ValueError('STATE_CHANGED_SINCE_COMPARISON')
    binding = state['binding']
    if report.get('binding')!=binding: raise ValueError('REPORT_BINDING_MISMATCH')
    package = Path(ctx['package']).resolve(strict=True)
    manifest = read(package/'CODE_MANIFEST.json')
    if digest(manifest)!=binding['code']: raise ValueError('CODE_MANIFEST_MISMATCH')
    for name,sha in manifest['files'].items():
        code = (package/name).resolve(strict=True)
        if package not in code.parents or hashlib.sha256(code.read_bytes()).hexdigest()!=sha:
            raise ValueError('INSTALLED_CODE_CHANGED')
    contract = read(package/'contract.json')
    if digest(contract)!=binding['contract'] or contract!=ctx['contract']:
        raise ValueError('CONTRACT_CHANGED')
    table = contract['tables']['SRCH_ROW']
    owner,name = identifier(table['owner']),identifier(table['name'])
    if owner not in ('SIDDS','SIDDA') or not name.endswith('_1'): raise ValueError('UNEXPECTED_TARGET')
    pk = [identifier(table['columns'][n]['name']) for n in table['primary_key']]
    identity = binding['database']
    if len(identity)!=1 or not identity[0].get('LOGIN_USER'): raise ValueError('DATABASE_BINDING_MISSING')
    obj = [r for r in binding['objects'] if r['OWNER']==owner and r['OBJECT_NAME']==name]
    if len(obj)!=1: raise ValueError('OBJECT_BINDING_MISSING')
    return {'comparison_path':str(path), 'comparison_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'comparison_run_id':report['run_id'], 'report':report, 'state_path':str(state_path),
            'original_state_sha256':original_sha, 'loader_status':state.get('status'),
            'owner':owner, 'table':name, 'pk_columns':pk, 'database':identity,
            'object':obj, 'package':str(package), 'code_sha256':binding['code'],
            'contract_sha256':binding['contract']}


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0


def timing(report):
    groups = {}
    for trial in report.get('trials',[]):
        if (trial.get('phase'),trial.get('arm'),trial.get('status'))!=('response','exception','ROLLED_BACK_VERIFIED'):
            continue
        batches = trial.get('batches',[])
        keys = ('request_s','payload_db_s','insert_db_s','verify_db_s','rollback_db_s')
        if not batches or any(not all(finite(b.get(k)) for k in keys) for b in batches): continue
        row = {k:sum(b[k] for b in batches) for k in keys}
        row.update(kind=trial['kind'],pair=trial['pair'],rows=trial['rows'])
        row['unseparated_s'] = row['request_s']-sum(row[k] for k in keys[1:])
        groups.setdefault(trial['kind'],[]).append(row)
    output = []
    for kind,rows in sorted(groups.items()):
        valid = len(rows)==3 and {r['pair'] for r in rows}=={0,1,2} and len({r['rows'] for r in rows})==1
        output.append({'kind':kind,'samples':rows,'status':'THREE_SAVED_SAMPLES' if valid else 'INCOMPLETE',
            'medians':{k:statistics.median(r[k] for r in rows) for k in (*keys,'unseparated_s')} if valid else {}})
    return output
