"""Existing pipeline CLI dispatch for the same knowledge application service."""
import argparse
import importlib
import json
from pathlib import Path
from lawrag.legal_knowledge.contracts import KnowledgeError, canonical, validate_definition, principal


def read_json(path):
    with Path(path).open('rb') as stream:
        data = stream.read(128001)
    if len(data) > 128000: raise ValueError('지식 명령 파일은 128KB 이하로 분리해 주세요.')
    return json.loads(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description='업무 검토 지식 검사·게시. 원문/숏컷 저장소를 복제하지 않습니다.')
    sub = parser.add_subparsers(dest='action', required=True)
    validate = sub.add_parser('validate'); validate.add_argument('--file', required=True)
    schema = sub.add_parser('oracle-ddl'); schema.add_argument('--table-map', required=True)
    for name in ('command', 'operation-status'):
        child = sub.add_parser(name)
        child.add_argument('--host', required=True, help='운영자가 설치한 module:function; (service_factory, authenticated_principal) 반환')
        child.add_argument('--file' if name == 'command' else '--operation-id', required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'validate':
            validate_definition(read_json(args.file))
            print(canonical({'status': 'VALID', 'published': False})); return 0
        if args.action == 'oracle-ddl':
            from lawrag.legal_knowledge.adapters.oracle import ddl
            print(ddl(read_json(args.table_map))); return 0
        module, separator, name = args.host.partition(':')
        if not separator or not all(part.isidentifier() for part in module.split('.')) or not name.isidentifier():
            parser.error('--host는 module:function 형식이어야 합니다.')
        factory, who = getattr(importlib.import_module(module), name)()
        principal(who)
        with factory() as service:
            result = (service.command(who, read_json(args.file)) if args.action == 'command'
                      else service.operation(args.operation_id, who))
        print(canonical(result)); return 0
    except KnowledgeError as exc:
        print(canonical({'status': 'FAILED', 'code': exc.code, 'message': str(exc), 'fields': exc.fields}))
        return 1


if __name__ == '__main__': raise SystemExit(main())
