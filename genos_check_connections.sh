#!/usr/bin/env bash
# Run with: bash genos_check_connections.sh [--check-config]
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
code_root="${GENOS_CODE_ROOT:-}"
if [[ -z "$code_root" ]]; then
  for candidate in "$script_dir" "$script_dir/.." "$PWD" /home/genos/DEV /workspace; do
    if [[ -f "$candidate/service.py" && -d "$candidate/02_BACKEND/semantic_runtime" ]]; then
      code_root="$(cd -- "$candidate" && pwd)"
      break
    fi
  done
fi
if [[ -z "$code_root" || ! -x "$code_root/.venv/bin/python" ]]; then
  echo 'GENOS_CODE_ROOT를 .venv와 service.py가 있는 설치 폴더로 설정하세요.' >&2
  exit 2
fi
case "${1:-}" in
  ''|--check-config) ;;
  *) echo '사용법: bash genos_check_connections.sh [--check-config]' >&2; exit 2 ;;
esac

"$code_root/.venv/bin/python" - "$code_root" "${1:-}" <<'PY'
import json
import math
import os
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / '02_BACKEND'))
try:
    from dotenv import load_dotenv
    load_dotenv(root / '.env', override=False)
    from semantic_runtime import genos
except ImportError:
    raise SystemExit('의존성 누락: 설치 폴더에서 .venv/bin/pip install -r requirements-genos.txt 를 실행하세요.')

def present(name):
    return bool(os.environ.get(name, '').strip())

def failure(component, exc):
    # Do not print exception text: HTTP errors may contain credentials or URLs.
    return {'component': component, 'status': 'FAIL', 'error': type(exc).__name__}

config = []
for kind in ('llm', 'embed'):
    try:
        genos.from_env(kind)
        config.append({'component': kind, 'status': 'CONFIGURED'})
    except Exception as exc:
        row = failure(kind, exc)
        row['required'] = (['GENOS_LLM_URL or GENOS_BASE_URL + LLM serving ID',
                            'GENOS_LLM_KEY or selected profile KEY'] if kind == 'llm'
                           else ['GENOS_EMBED_URL or GENOS_BASE_URL + GENOS_EMBED_SERVING_ID',
                                 'GENOS_EMBED_KEY'])
        config.append(row)

missing = [name for name in ('GENOS_VDB_URL', 'GENOS_VDB_COLLECTION') if not present(name)]
config.append({'component': 'vdb', 'status': 'MISSING' if missing else 'CONFIGURED',
               'missing': missing})
print('설정 확인 (키 값은 출력하지 않습니다):', flush=True)
print(json.dumps(config, ensure_ascii=False, indent=2), flush=True)
if sys.argv[2] == '--check-config':
    print('설정 유무만 확인했습니다. 실제 접속은 실행하지 않았습니다.')
    raise SystemExit(0 if all(row['status'] == 'CONFIGURED' for row in config) else 2)

print('1/3 LLM 짧은 응답 생성 중...', flush=True)
llm = genos.check('llm', execute=True)
print(json.dumps(llm, ensure_ascii=False), flush=True)

print('2/3 임베딩 생성 중...', flush=True)
vector = None
try:
    target, configured = genos.from_env('embed')
    model = genos.advertised_model(target, configured)
    response = genos.request_json(target, '/embeddings', {
        'model': model, 'input': ['GENOS connectivity check'],
    })
    candidate = response['data'][0]['embedding']
    if not isinstance(candidate, list) or not candidate or any(
        type(x) not in (int, float) or not math.isfinite(x) for x in candidate
    ):
        raise ValueError('Invalid embedding')
    vector = candidate
    embed = {'component': 'embed', 'status': 'PASS', 'dimensions': len(vector)}
except Exception as exc:
    embed = failure('embed', exc)
print(json.dumps(embed, ensure_ascii=False), flush=True)

print('3/3 Weaviate 스키마 및 nearVector 검색 중...', flush=True)
try:
    if missing:
        vdb = {'component': 'vdb', 'status': 'NOT_RUN', 'missing': missing}
    else:
        url = os.environ['GENOS_VDB_URL'].strip()
        collection = os.environ['GENOS_VDB_COLLECTION'].strip()
        if '/api/gateway/' in url or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,127}', collection):
            raise ValueError('Direct Weaviate URL and valid collection required')
        target = genos.endpoint(url, token=os.environ.get('GENOS_VDB_TOKEN', ''),
                                label='GENOS vdb', api_prefix='/v1',
                                read_timeout=30, max_retries=2)
        schema = genos.request_json(target, '/schema/' + collection)
        if schema.get('class') != collection:
            raise ValueError('Collection schema mismatch')
        if vector is None:
            vdb = {'component': 'vdb', 'status': 'NOT_RUN', 'schema': 'PASS',
                   'reason': '임베딩 실패로 벡터 검색은 실행하지 못했습니다.'}
        else:
            literal = json.dumps(vector, allow_nan=False, separators=(',', ':'))
            query = '{Get{' + collection + '(nearVector:{vector:' + literal + '},limit:1){_additional{id distance}}}}'
            response = genos.request_json(target, '/graphql', {'query': query})
            if response.get('errors'):
                raise ValueError('Vector query rejected')
            rows = response['data']['Get'][collection]
            if not isinstance(rows, list):
                raise ValueError('Invalid query result')
            vdb = {'component': 'vdb', 'status': 'PASS', 'schema': 'PASS',
                   'vector_query': 'PASS', 'objects_returned': len(rows)}
            if not rows:
                vdb['note'] = '검색 요청은 성공했지만 결과가 없어 저장된 벡터와의 차원 호환성은 확인되지 않았습니다.'
except Exception as exc:
    vdb = failure('vdb', exc)
print(json.dumps(vdb, ensure_ascii=False), flush=True)

checks = [llm, embed, vdb]
ok = all(row.get('status') == 'PASS' for row in checks)
print(json.dumps({'ok': ok, 'checks': checks}, ensure_ascii=False, indent=2))
print('이 결과는 실행한 코드스페이스의 연결 확인입니다. 데이터 적재와 배포된 RAG 답변 연결은 별도입니다.')
raise SystemExit(0 if ok else 1)
PY
