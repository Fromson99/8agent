"""Offline generation discovery/selection; independent of code-serving settings."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys

SHARED_ROOT = Path('/nfs-root/diamo/8-agent/term-releases')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    value = json.loads(path.read_bytes())
    if not isinstance(value,dict):
        raise ValueError('metadata must be a JSON object: '+str(path))
    return value

def inside(root, relative):
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('unsafe generation asset path')
    path = root/value
    if path.is_symlink():
        raise ValueError('generation asset symlink is not supported')
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    return resolved

def inspect(path, config):
    supplied = Path(path).expanduser()
    if not supplied.is_absolute() or supplied.is_symlink():
        raise ValueError('generation must be an absolute directory, not a symlink')
    path = supplied.resolve(strict=True)
    raw = read(path/'manifest.json')
    if raw.get('schema_version')!='term-source-generation-v1':
        raise ValueError('not a source generation')
    if not (path/'store.sqlite').is_file():
        raise ValueError('source store is missing')
    nav = raw.get('navigation')
    ft = raw.get('fulltext') or config.get('fulltext')
    if not isinstance(nav,dict) or not isinstance(ft,dict):
        raise ValueError('generation has no navigation/fulltext binding')
    navigation = inside(path,nav['path'])
    fulltext = inside(path,ft['path'])
    nav_file = navigation/'manifest.json'
    ft_file = fulltext/'manifest.json'
    if sha(nav_file)!=nav['manifest_sha256'] or sha(ft_file)!=ft['manifest_sha256']:
        raise ValueError('navigation/fulltext metadata hash mismatch')
    nm,fm = read(nav_file),read(ft_file)
    source = {k:v for k,v in raw.items() if k not in {'navigation','fulltext','fulltext_derivation'}}
    source_digest = hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if nm.get('source_manifest_sha256')!=source_digest:
        raise ValueError('navigation source manifest mismatch')
    if fm.get('schema_version')!='semantic-fulltext-v2' or fm.get('tokenizer',{}).get('name')!='pecab':
        raise ValueError('unsupported fulltext/tokenizer for this search comparison')
    if nm['source_store_sha256']!=raw['store_sha256'] or nm['generation_id']!=raw['generation_id']:
        raise ValueError('navigation belongs to another source generation')
    if fm['navigation_index_sha256']!=nm['index_sha256'] or fm['source_store_sha256']!=raw['store_sha256'] or fm['generation_id']!=raw['generation_id']:
        raise ValueError('fulltext belongs to another navigation generation')
    if ft.get('navigation_index_sha256',nm['index_sha256'])!=nm['index_sha256']:
        raise ValueError('fulltext configuration navigation mismatch')
    if not (navigation/'navigation.sqlite').is_file() or not (fulltext/'fulltext.sqlite').is_file():
        raise ValueError('navigation/fulltext database is missing')
    proof = {str(path/'manifest.json'):sha(path/'manifest.json'),str(nav_file):sha(nav_file),str(ft_file):sha(ft_file)}
    return {'path':str(path),'generation_id':raw['generation_id'],'manifest_sha256':proof[str(path/'manifest.json')],
            'source_count':fm.get('counts',{}).get('source'), 'tokenizer':fm.get('tokenizer',{}),
            'data_status':raw.get('data_status'), 'proof':proof}

def settings(root, env):
    keys = ('GENOS_GENERATION','GENOS_DATA_ROOT')
    result = {key:env[key] for key in keys if env.get(key,'').strip()}
    path = root/'.env'
    if path.is_file() and not path.is_symlink():
        for line in path.read_text('utf-8').splitlines():
            match = re.match(r'^\s*(?:export\s+)?(GENOS_GENERATION|GENOS_DATA_ROOT)\s*=(.*)$',line)
            if match and match[1] not in env:
                values = shlex.split(match[2],comments=True)
                if len(values)>1 or (values and '$' in values[0]):
                    raise ValueError('GENOS data setting must be a literal path; no shell expansion')
                if values and values[0].strip():
                    result[match[1]]=values[0]
    return result

def roots(root, env):
    from lawrag.platform.workspace import load_layout
    # load_layout gives an inherited LAWRAG_WORKSPACE_ROOT priority over its
    # argument. This offline command explicitly selected this checkout.
    previous = os.environ.get('LAWRAG_WORKSPACE_ROOT')
    os.environ['LAWRAG_WORKSPACE_ROOT']=str(root)
    try:
        layout = load_layout(root)
        declared = root/layout.roots['data'].canonical_path
        data = layout.inspection_path('data',layout_version='v2') if declared.exists() else declared
    finally:
        if previous is None:os.environ.pop('LAWRAG_WORKSPACE_ROOT',None)
        else:os.environ['LAWRAG_WORKSPACE_ROOT']=previous
    values = settings(root,env)
    found = [data,root/'GENOS_DATA',data/'INBOX/AUTHORING',data/'TERM_RELEASES',SHARED_ROOT]
    if values.get('GENOS_DATA_ROOT'):
        found.insert(0,Path(values['GENOS_DATA_ROOT']).expanduser())
    # Optional extra existing data roots, for sites using a different mount.
    found.extend(Path(s).expanduser() for s in env.get('GENOS_BENCH_DATA_ROOTS','').split(os.pathsep) if s)
    result = []
    for path in found:
        if not path.is_absolute():
            raise ValueError('data root must be absolute')
        if path.is_dir():
            resolved = path.resolve(strict=True)
            if resolved not in result:result.append(resolved)
    return result

def pointer(path,config):
    value = read(path)
    if value.get('schema_version')!='genos-current-generation-v1':
        raise ValueError('unsupported CURRENT schema: '+str(path))
    chosen = inspect(Path(value['path']),config)
    if chosen['manifest_sha256']!=value['manifest_sha256']:
        raise ValueError('CURRENT generation manifest hash mismatch')
    chosen['proof'][str(path)]=sha(path)
    chosen['selection']='codespace-current'
    return chosen

PATTERNS = (
    'manifest.json', 'generation/manifest.json',
    'generations/*/manifest.json', 'generations/*/generation/manifest.json',
    '*/generation/manifest.json', '*/reviewed/generation/manifest.json', '*/unreviewed/generation/manifest.json',
    '*/serving/generation/manifest.json', '*/serving-unreviewed/generation/manifest.json',
    '*/unreviewed/serving/generation/manifest.json',
    'TERM_RELEASES/*/serving/generation/manifest.json',
    'TERM_RELEASES/*/unreviewed/serving/generation/manifest.json',
)

def discover(root, config, *, env=None):
    env = os.environ if env is None else env
    data_roots = roots(root,env)
    candidates, skipped = {}, []
    for base in data_roots:
        for pattern in PATTERNS:
            for manifest in base.glob(pattern):
                if any(p.startswith('.') for p in manifest.relative_to(base).parts):continue
                try:
                    value = inspect(manifest.parent,config)
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    skipped.append({'path':str(manifest.parent),'reason':str(exc)})
                    continue
                value['selection']='codespace-discovery'
                candidates[value['path']]=value
    return [candidates[k] for k in sorted(candidates)],data_roots,skipped

def select(root, config, *, explicit=None, index=None, env=None, interactive=None, choose=None):
    env = os.environ if env is None else env
    values = settings(root,env)
    if explicit is not None or values.get('GENOS_GENERATION'):
        chosen = inspect(Path(explicit or values['GENOS_GENERATION']).expanduser(),config)
        chosen['selection']='explicit-offline-generation'
        return chosen
    current = []
    for base in roots(root,env):
        path = base/'generations/CURRENT.json'
        if path.is_file():current.append(pointer(path,config))
    unique = {v['path']:v for v in current}
    if len(unique)==1:
        chosen = next(iter(unique.values()))
        for value in current:chosen['proof'].update(value['proof'])
        return chosen
    candidates,bases,skipped = discover(root,config,env=env)
    # Conflicting pointers can reference a valid generation outside the usual
    # publication folders. Keep both in the explicit selection menu.
    known = {v['path']:v for v in candidates}
    known.update(unique)
    candidates = [known[k] for k in sorted(known)]
    if not candidates:
        details='\n'.join('  '+str(p) for p in bases)
        rejected='\n'.join('  '+v['path']+' : '+v['reason'] for v in skipped[:5])
        raise ValueError('검색용 generation 후보가 없습니다. 확인한 기존 data roots:\n'+details+
                         ('\n제외 이유:\n'+rejected if rejected else '')+
                         '\nGENOS_BENCH_DATA_ROOTS=/실제/데이터루트 또는 GENOS_GENERATION=/실제/generation을 지정하세요. 배포 설정이나 새 데이터 생성은 필요하지 않습니다.')
    if len(candidates)==1 and len(unique)<=1:
        chosen=candidates[0];chosen['selection']='codespace-auto-single';return chosen
    print('검색용 데이터 세대 후보 (배포와 관계없는 이번 비교의 입력):',flush=True)
    for number,value in enumerate(candidates,1):
        print('%d) sources=%s tokenizer=%s id=%s\n   %s'%(number,value['source_count'],value['tokenizer'].get('name'),value['generation_id'],value['path']),flush=True)
    if index is None:
        tty = sys.stdin.isatty() if interactive is None else interactive
        if not tty:
            raise ValueError('후보가 여러 개입니다. 터미널에서 실행해 번호를 선택하거나 GENERATION_INDEX=번호를 지정하세요. 날짜순 자동 선택은 하지 않습니다.')
        answer=(choose or input)('비교할 데이터 세대 번호: ')
        try:index=int(answer)
        except (TypeError,ValueError):raise ValueError('generation 번호는 정수여야 합니다')
    if not 1<=index<=len(candidates):
        raise ValueError('generation 번호가 목록 범위를 벗어났습니다')
    chosen=candidates[index-1];chosen['selection']='codespace-user-selected';return chosen

def unchanged(selection):
    return all(Path(path).is_file() and sha(Path(path))==expected for path,expected in selection['proof'].items())
