"""Bounded metadata and exact installed-package binding. No loader state writes."""
import hashlib
import json
from pathlib import Path
import re
import tempfile


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
    if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('METADATA_LIMIT_OR_CHANGED')
    return json.loads(raw)


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(canonical(value), encoding='utf-8')
    temp.replace(path)


def error(exc):
    return {'type': type(exc).__name__, 'codes': sorted(set(re.findall(r'(?:ORA|PLS)-\d{5}', str(exc))))[:12]}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError('IDENTIFIER')
    return value


def literal(value):
    if not isinstance(value, str) or len(value) > 512 or '\0' in value:
        raise ValueError('LITERAL')
    return "'"+value.replace("'", "''")+"'"


def default_job():
    return Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'


class ContextError(ValueError):
    def __init__(self, code, details):
        super().__init__(code)
        self.details = details


def prepared(old_job=''):
    """A valid saved plan remains reportable even when runtime binding fails."""
    job = Path(old_job or default_job()).resolve(strict=True)
    desc = read(job/'projection-descriptor-r7.json')
    body = {k:v for k,v in desc.items() if k != 'checksum'}
    if digest(body) != desc.get('checksum'):
        raise ValueError('DESCRIPTOR_CHECKSUM')
    return {'job':str(job), 'descriptor':body, 'descriptor_checksum':desc['checksum']}


def _unique_paths(values):
    return list(dict.fromkeys(Path(v).resolve() for v in values if v))


def _bounded_glob(root, pattern, limit=256):
    values = []
    for p in Path(root).glob(pattern):
        values.append(p)
        if len(values)>limit: raise ValueError('DISCOVERY_LIMIT_SET_EXPLICIT_PATH')
    return sorted(values)


def _verified_package(package, code):
    for relative, sha in code['files'].items():
        path = (package/relative).resolve(strict=True)
        if package not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise ValueError('INSTALLED_PACKAGE_HASH')
    contract = read(package/'contract.json')
    tables = contract['tables']
    if len(tables)!=17 or any(not t['name'].endswith('_1') or t['owner'] not in ('SIDDS','SIDDA') for t in tables.values()):
        raise ValueError('NOT_FRESH_1_TARGET')
    for t in tables.values():
        identifier(t['owner']); identifier(t['name'])
        for col in t['columns'].values(): identifier(col['name'])
    return contract


def context(old_job='', state_dir='', package_dir='', hints=None):
    hints = hints or {}
    plan = prepared(old_job); job = Path(plan['job']); body = plan['descriptor']
    details = {'job':str(job), 'states':[], 'packages':[], 'selected':None,
               'rule':'source+files+installed code+contract+fresh _1 targets; never select by mtime/status'}
    try:
        full = read(job/'full-state.json')
        full_root = Path(full['identity']['generation']).resolve(strict=True)
        matches = []
        hint_states = _unique_paths(hints.get('state_paths',[]))
        if hints.get('contract_hash'):
            h = hints['contract_hash']
            if isinstance(h,str) and re.fullmatch('[a-f0-9]{64}',h): hint_states.append(job.parent/('gold-shape-'+h[:12]))
        candidates = _unique_paths([state_dir]) if state_dir else _unique_paths([*hint_states,*_bounded_glob(job.parent,'gold-shape-*')])
        for directory in candidates:
            entry = {'path':str(directory), 'status':'UNREAD', 'reason':''}; details['states'].append(entry)
            try:
                state = read(directory/'state.json'); binding = state.get('binding',{})
                entry.update(status=state.get('status','UNKNOWN'), code_prefix=str(binding.get('code',''))[:12], contract_prefix=str(binding.get('contract',''))[:12])
                if binding.get('source_release')!=body['binding']['source']:
                    entry['reason']='SOURCE_RELEASE_MISMATCH'; continue
                if binding.get('files')!=body['binding']['files']:
                    entry['reason']='FILES_MISMATCH'; continue
                expected_query=full.get('deferred',{}).get('plan',{}).get('query_release_id')
                if expected_query and binding.get('query_release')!=expected_query:
                    entry['reason']='QUERY_RELEASE_MISMATCH'; continue
                if Path(binding['generation']).resolve(strict=True)!=full_root or job.parent not in full_root.parents:
                    entry['reason']='GENERATION_BINDING'; continue
                expected = job.parent/('gold-shape-'+binding['contract'][:12])
                if directory!=expected.resolve():
                    entry['reason']='STATE_DIRECTORY_CONTRACT_MISMATCH'; continue
                entry['reason']='SOURCE_MATCH_NEEDS_PACKAGE'
                matches.append((directory,state,entry))
            except (OSError,ValueError,KeyError,TypeError) as exc:
                entry['reason']='STATE_UNREADABLE_'+type(exc).__name__
        details['source_matching_states']=len(matches)
        if not matches:
            raise ContextError('STATE_NOT_FOUND_OR_BINDING_MISMATCH',details)
        hint_packages = _unique_paths(hints.get('package_paths',[]))
        roots = [Path(package_dir)] if package_dir else list(hint_packages)
        if not package_dir:
            for pattern in ('legal-gold-fresh-1-*','legal-gold-shape-*','legal-gold-flow-*'):
                roots.extend(_bounded_glob(tempfile.gettempdir(),pattern))
        packages = _unique_paths([p for root in roots for p in (root,root/'engine')])
        if len(packages)>512: raise ValueError('PACKAGE_DISCOVERY_LIMIT_SET_PACKAGE_DIR')
        codes = {s['binding']['code'] for _,s,_ in matches}
        verified = []; validation_errors=[]
        for package in packages:
            if not (package/'CODE_MANIFEST.json').is_file(): continue
            entry={'path':str(package),'reason':'UNREAD'}; details['packages'].append(entry)
            try:
                code=read(package/'CODE_MANIFEST.json'); code_hash=digest(code)
                entry['code_prefix']=code_hash[:12]
                if code_hash not in codes:
                    entry['reason']='CODE_BINDING_MISMATCH'; continue
                contract=_verified_package(package,code)
                verified.append((package,code_hash,contract))
                entry['reason']='FRESH_1_PACKAGE_VERIFIED'
            except (OSError,ValueError,KeyError,TypeError) as exc:
                reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                entry['reason']=reason[:120]; validation_errors.append(reason)
        pairs=[]
        for directory,state,entry in matches:
            options=[v for v in verified if v[1]==state['binding']['code'] and digest(v[2])==state['binding']['contract']]
            if not options:
                entry['reason']='NO_VERIFIED_FRESH_1_PACKAGE'; continue
            # Multiple byte-identical installations do not make the state ambiguous.
            options.sort(key=lambda v:(v[0] not in hint_packages,str(v[0])))
            entry['reason']='FRESH_1_STATE_VERIFIED'
            pairs.append((directory,state,*options[0]))
        details['fresh_matching_states']=len(pairs)
        if not pairs:
            reason='INSTALLED_PACKAGE_HASH' if 'INSTALLED_PACKAGE_HASH' in validation_errors else 'PACKAGE_OR_FRESH_CONTRACT_NOT_FOUND'
            raise ContextError(reason,details)
        if len(pairs)>1 and not state_dir:
            preferred=[v for v in pairs if v[0] in hint_states]
            if len(preferred)==1: pairs=preferred
            else:
                preferred=[v for v in pairs if v[2] in hint_packages]
                if len(preferred)==1: pairs=preferred
        if len(pairs)!=1: raise ContextError('MULTIPLE_VERIFIED_FRESH_STATES_SET_STATE_DIR',details)
        directory,state,package,code_hash,contract=pairs[0]
        root=Path(state['binding']['generation']).resolve(strict=True)
        manifest=read(root/'manifest.json')
        if hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()!=state['binding']['files']['manifest.json']:
            raise ValueError('SOURCE_MANIFEST_HASH')
        details['selected']={'state_dir':str(directory),'package':str(package),'status':state.get('status','UNKNOWN')}
        return {**plan,'state_dir':str(directory),'package':str(package),'root':str(root),'state':state,
                'manifest':manifest,'contract':contract,'discovery':details,
                'scope':'metadata binding verified; full SQLite file hashes not reread by snapshot'}
    except ContextError:
        raise
    except (OSError,ValueError,KeyError,TypeError) as exc:
        details['failure_type']=type(exc).__name__
        raise ContextError(str(exc) if isinstance(exc,ValueError) else type(exc).__name__,details) from exc

