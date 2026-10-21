"""Basis lifecycle hooks for existing document publication and Dataiku recipes."""
from contextlib import ExitStack,closing
import argparse
import json
from pathlib import Path


def prepare(repository,old_sources,new_sources,principal,changes,lineage,official=None):
    from semantic_runtime.basis_links.service import Service
    from semantic_runtime.basis_links.migration import migrate
    from semantic_runtime.basis_links.contracts import require
    require(principal.get('basis_migrate') is True,'BASIS_MIGRATION_DENIED','판본 이행 권한이 필요합니다.',403)
    with repository.transaction():
        for item in lineage:
            require(set(item)>={'version_id','family_id','source_artifact_hash','provenance'} and item['provenance'],
                    'BASIS_LINEAGE','계열·판본·원문 해시·계열 지정 근거가 필요합니다.')
            source=old_sources if old_sources.document_hash(item['version_id']) is not None else new_sources
            require(source.document_hash(item['version_id'])==item['source_artifact_hash'],'BASIS_LINEAGE_HASH','원문과 계열 기록의 해시가 다릅니다.',409)
            repository.register_lineage(item)
    return migrate(Service(repository,old_sources),new_sources,principal,changes,official=official)


def prepare_local(old_generation,new_generation,plan):
    """Explicit local plan; deployment supplies Oracle ports to prepare() instead."""
    from semantic_runtime.storage import Store
    from semantic_runtime.basis_links.repository import Repository
    from semantic_runtime.basis_links.sources import SourcePort
    from semantic_runtime.basis_links.contracts import require
    require(plan.get('backend')=='sqlite-local','BASIS_BACKEND','로컬 이행 계획의 backend를 명시해야 합니다.')
    with ExitStack() as stack:
        old=stack.enter_context(closing(Store(old_generation)))
        new=stack.enter_context(closing(Store(new_generation)))
        repo=stack.enter_context(closing(Repository(plan['authority_path'])))
        return prepare(repo,SourcePort(old),SourcePort(new),plan['principal'],plan['changes'],plan['lineage'],plan.get('official'))


def verify(repository,sources,principal,migration_id):
    from semantic_runtime.basis_links.contracts import require
    value=repository.migration(migration_id)
    require(value is not None and value['team_id']==principal['team_id'],'BASIS_NOT_FOUND','이행 기록을 찾을 수 없습니다.',404)
    require(value['new_generation']==sources.generation,'BASIS_GENERATION','검증 세대가 이행의 신판 세대와 다릅니다.',409)
    for row in value['items']:
        binding=repository.binding(row['link_id'],row['revision'],sources.generation)
        require(binding is not None and binding['binding_id']==row['binding_id'],'BASIS_BINDING','이행 위치 기록이 없습니다.',409)
        for end in binding['internal']+binding['external']:sources.verify(end,principal)
    return {'verified':True,'migration_id':migration_id,'relations':len(value['items']),'unresolved':value['unresolved'],'legal_quality_certified':False}


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["batch-artifacts"]:
        from .basis_batch_artifacts import main as artifacts_main
        return artifacts_main(argv[1:])
    if argv[:1] == ["seed-risk"]:
        from .risk_basis_seed_cli import main as seed_main
        return seed_main(argv[1:])
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['import','inspect','export','migrate','verify'])
    p.add_argument('--plan',type=Path,required=True,help='Explicit local backend/principal/authority configuration; never credentials')
    p.add_argument('--old-generation',type=Path);p.add_argument('--new-generation',type=Path)
    p.add_argument('--generation',type=Path);p.add_argument('--run-id');p.add_argument('--input',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args(argv);plan=json.loads(a.plan.read_text())
    if a.action=='migrate':
        if not a.old_generation or not a.new_generation:p.error('migrate requires old/new generation')
        result=prepare_local(a.old_generation,a.new_generation,plan)
    else:
        from semantic_runtime.basis_links.api import local_factory
        from semantic_runtime.basis_links.contracts import require
        require(plan.get('backend')=='sqlite-local','BASIS_BACKEND','명시적인 로컬 계획이 필요합니다.')
        from semantic_runtime.storage import Store
        from semantic_runtime.basis_links.repository import Repository
        from semantic_runtime.basis_links.sources import SourcePort
        from semantic_runtime.basis_links.service import Service
        if not a.generation:p.error('--generation required')
        with ExitStack() as stack:
            store=stack.enter_context(closing(Store(a.generation)));repo=stack.enter_context(closing(Repository(plan['authority_path'])))
            service=Service(repo,SourcePort(store));who=plan['principal']
            if a.action=='verify':result=verify(repo,service.sources,who,a.run_id)
            elif a.action=='import':
                if not a.input:p.error('--input required')
                rows=json.loads(a.input.read_text());result=[]
                for row in rows:
                    # Imported approval assertions remain provenance, never
                    # fabricated authenticated human review events.
                    body={k:row[k] for k in ('request_id','internal','external','kind','reason')}
                    body['provenance']={'type':'IMPORT','source_record':row.get('provenance',{}),'reported_approval':row.get('reported_approval')}
                    result.append(service.propose(who,body))
            else:result=service.list(who)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.output:
        with a.output.open('x') as out:out.write(text)
    else:print(text)
    return 0


class PublicationHook:
    """Reusable hook for the existing Dataiku/Oracle publication function.

    Factories provide approved source ports and one Oracle authority. A batch
    never infers credentials, owners, families or human approvals.
    """
    def __init__(self,authority,old_sources,new_sources,principal,changes,lineage,official=None):
        self.authority=authority;self.old_sources=old_sources;self.new_sources=new_sources
        self.principal=principal;self.changes=changes;self.lineage=lineage;self.official=official

    def prepare(self,source_manifest):
        from semantic_runtime.basis_links.contracts import require
        with self.authority() as service,self.old_sources() as old,self.new_sources() as new:
            require(new.generation==source_manifest['generation_id'],'BASIS_GENERATION','게시 대상과 이행 신판 세대가 다릅니다.',409)
            receipt=prepare(service.repo,old,new,self.principal,self.changes,self.lineage,self.official)
            checked=verify(service.repo,new,self.principal,receipt['migration_id'])
            return {'migration_id':receipt['migration_id'],'new_generation':new.generation,
                    'source_store_sha256':source_manifest['store_sha256'],'verification':checked}
