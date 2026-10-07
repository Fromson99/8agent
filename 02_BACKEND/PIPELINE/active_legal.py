"""Run the selected local legal RAG release through the same service request path."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


async def _call(data):
    import service
    return await service.service({}, data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'plan', 'run'))
    parser.add_argument('--profile', default='legal-rag', choices=('legal-rag',))
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)

    health = asyncio.run(_call({'op': 'call', 'method': 'GET', 'path': '/health'}))
    if health.get('status') != 200:
        raise RuntimeError('active legal RAG health check failed')
    body = health['body']
    binding = body.get('release') or {}
    if binding.get('mode') != 'local-release':
        raise RuntimeError('local CLI requires an active local release')

    if args.action == 'check':
        result = {'ok': True, 'profile': 'legal-rag', 'release': binding,
                  'llm_model': body.get('llm_model'), 'rag_mode': body.get('rag_mode'),
                  'generation_id': body.get('generation_id')}
    elif args.action == 'plan':
        import service
        code_root, _, _ = service._resolve_binding()
        config = json.loads((code_root/'00_SYSTEM/PIPELINE.json').read_text())
        profile = config['profiles']['legal-rag']
        result = {'schema_version': 'active-legal-rag-plan-v1', 'profile': 'legal-rag',
                  'release': binding, 'nodes': [
                      {'id': node['id'], 'engine': node['engine']} for node in profile['nodes']],
                  'llm_model': body.get('llm_model')}
    else:
        if args.inputs is None or args.output is None:
            parser.error('run requires --inputs and --output')
        inputs = json.loads(args.inputs.read_text())
        if set(inputs) != {'request'} or set(inputs['request']) != {'path', 'sha256'}:
            raise ValueError('inputs must bind one hash-pinned request artifact')
        request_path = Path(inputs['request']['path']).resolve()
        if _sha(request_path) != inputs['request']['sha256']:
            raise ValueError('request artifact hash mismatch')
        request = json.loads(request_path.read_text())
        if not isinstance(request, dict):
            raise ValueError('request artifact must contain an object')
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        result = asyncio.run(_call({'API_TYPE': 'RAG_ASK', 'json': request}))
        _write(output/'response.json', result)
        receipt = {'schema_version': 'active-legal-rag-run-v1',
                   'status': 'COMPLETE' if result.get('status') == 200 else 'FAILED',
                   'completed_at': datetime.now(timezone.utc).isoformat(),
                   'profile': 'legal-rag', 'release': binding,
                   'request_path': str(request_path),
                   'request_sha256': inputs['request']['sha256'],
                   'response_sha256': _sha(output/'response.json'),
                   'http_status': result.get('status'),
                   'run_id': (result.get('body') or {}).get('run_id')}
        _write(output/'receipt.json', receipt)
        if receipt['status'] != 'COMPLETE':
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        return print(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
