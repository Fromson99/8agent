"""Only explicitly registered entrypoints execute; manifests pin every package file."""
from dataclasses import dataclass
import hashlib
import json
import importlib
import re
from pathlib import Path
from .contracts import WorkflowError


@dataclass(frozen=True)
class Definition:
    manifest: dict
    entrypoint: object
    reporter: object = None
    normalizer: object = None
    presenter: object = None
    finalizer: object = None


class Registry:
    def __init__(self):
        self._definitions = {}

    def register(self, manifest, entrypoint, reporter=None, normalizer=None, presenter=None, finalizer=None):
        key = (manifest['workflow_id'], manifest['version'])
        if key in self._definitions or not callable(entrypoint) or (reporter is not None and not callable(reporter)):
            raise WorkflowError('WORKFLOW_REGISTRY', '중복 또는 잘못된 워크플로우 등록입니다.')
        self._definitions[key] = Definition(manifest, entrypoint, reporter, normalizer, presenter, finalizer)

    def resolve(self, ident, version, team):
        if version is None:
            matches=[v for (name,_),v in self._definitions.items() if name==ident]
            if len(matches)>1:raise WorkflowError('WORKFLOW_VERSION_REQUIRED','여러 실행 버전이 등록되어 명시 버전이 필요합니다.',409)
            result=matches[0] if matches else None
        else:
            result = self._definitions.get((ident, version))
        if result is None:
            raise WorkflowError('WORKFLOW_NOT_REGISTERED', '등록되지 않은 워크플로우입니다.', 404)
        if team not in result.manifest['allowed_teams']:
            raise WorkflowError('WORKFLOW_TEAM_DENIED', '이 팀에서 허용되지 않은 워크플로우입니다.', 403)
        return result


def builtin(declarations=None, code_root=None):
    root=Path(__file__).resolve().parent
    code_root=Path(code_root or root.parents[1]).resolve()
    if declarations is None:
        path=root/'risk_team_compare_workflow/manifest.json'
        metadata=json.loads(path.read_text())
        declarations=[{'id':metadata['workflow_id'],'version':metadata['version'],
            'manifest':str(path.relative_to(code_root)),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
    registry=Registry()
    for declared in declarations:
        path=(code_root/declared['manifest']).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=declared['sha256']:
            raise WorkflowError('WORKFLOW_CODE_BINDING','등록된 워크플로우 manifest 결속이 다릅니다.',409)
        manifest=json.loads(path.read_text())
        if (manifest['workflow_id'],manifest['version'])!=(declared['id'],declared['version']):
            raise WorkflowError('WORKFLOW_CODE_BINDING','워크플로우 등록 정보가 다릅니다.',409)
        for relative,expected in manifest['files'].items():
            path=(root/relative).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise WorkflowError('WORKFLOW_CODE_BINDING','워크플로우 코드 결속이 변경되었습니다.',409)
        def load(name):
            if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}',name):
                raise WorkflowError('WORKFLOW_REGISTRY','유효한 패키지 진입점이 필요합니다.')
            module,attribute=name.rsplit('.',1)
            if module.replace('.','/')+'.py' not in manifest['files']:
                raise WorkflowError('WORKFLOW_REGISTRY','해시가 등록되지 않은 진입점입니다.')
            return getattr(importlib.import_module('.'+module,__package__),attribute)
        registry.register(manifest,load(manifest['entrypoint']),load(manifest['reporter']),
            load(manifest['normalizer']) if manifest.get('normalizer') else None,
            load(manifest['presenter']) if manifest.get('presenter') else None,
            load(manifest['finalizer']) if manifest.get('finalizer') else None)
    return registry
