"""Source binding, publication, ACL and rollback of curated CM data; no LLM."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from collections import defaultdict
import sqlite3
import pytest
from lawrag.pipeline import shortcut_package as packages
from lawrag.pipeline.legal_wiki_compiler import rebuild
from semantic_runtime.storage import Store
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import MemoryError
from semantic_runtime.legal_agent import core_evidence_route as core

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def inputs():
    package = json.loads((ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_data_20261007_r2/CM51_SOURCE_PACKAGE.json').read_text())
    store = Store(ROOT/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation')
    principal = {'user_id': 'fixture', 'team_id': 'fixture', 'authenticated': True,
                 'document_ids': sorted(store.manifest['scope']['document_version_ids'])}
    yield package, store, principal
    store.close()


@pytest.fixture
def repo(tmp_path):
    repo = ShortcutRepository(tmp_path/'cases-v4.sqlite')
    yield repo
    repo.close()


def host(repo, binding, trust='internal'):
    return SimpleNamespace(shortcut=repo,binding=binding,
        model=SimpleNamespace(pipeline=SimpleNamespace(term_agent=SimpleNamespace(
            transport=SimpleNamespace(binding={'trust_zone':trust})))))


def state(package, principal):
    return {'task': package['cases'][0]['question'], 'facts': [], 'source_category': 'all',
            'document_ids': principal['document_ids']}


def test_real_51_cases_98_entries_and_shared_wiki(inputs,repo,tmp_path):
    package,store,p=inputs
    receipt=packages.import_package(repo,p,package,store)
    assert len(receipt['records'])==51 and sum(r['sources'] for r in receipt['records'])==98
    assert packages.verify_package(repo,p,receipt)['units']==51
    before=repo.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]
    assert packages.import_package(repo,p,package,store)['already_imported'] is True
    assert repo.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==before
    assert not repo.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal'").fetchone()
    built=rebuild(repo,p,tmp_path/'legal_wiki')
    assert built['pages']==51
    pages=repo.search(p,limit=100)['pages']
    assert all(v['claims']==v['procedures']==[] and v['completeness']=='OPEN' for v in pages)
    assert all(v['observations'][0]['kind']=='ACTUAL_WORK_REFERENCE_NOT_APPROVED_INTERPRETATION' for v in pages)
    assert core.lookup(host(repo,receipt['source_binding']),state(package,p),p)['contract']==packages.CONTRACT


@pytest.mark.parametrize('field',['source_artifact_sha256','section_text_sha256','coordinate_key'])
def test_bad_source_cannot_write_partial_import(inputs,repo,field):
    package,store,p=inputs;bad=deepcopy(package);bad['cases'][-1]['entries'][-1][field]='not-the-selected-original'
    with pytest.raises(MemoryError):packages.import_package(repo,p,bad,store)
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0


def test_acl_external_and_changed_conditions_cannot_reuse(inputs,repo):
    package,store,p=inputs;receipt=packages.import_package(repo,p,package,store)
    h=host(repo,receipt['source_binding']);s=state(package,p)
    assert core.lookup(h,s,{**p,'user_id':'other'}) is None
    assert core.lookup(host(repo,receipt['source_binding'],'external'),s,p) is None
    assert core.lookup(h,{**s,'facts':[{'name':'조건','value':'다름'}]},p) is None
    assert core.lookup(host(repo,{**receipt['source_binding'],'store_sha256':'different'}),s,p) is None
    with pytest.raises(MemoryError):packages.import_package(repo,{**p,'document_ids':[]},package,store)


def test_literal_cm_request_survives_model_paraphrase_and_preserves_current_facts(inputs,repo):
    package,store,p=inputs;receipt=packages.import_package(repo,p,package,store)
    h=host(repo,receipt['source_binding'])
    current={'task':'모델이 정리한 현재 행사 가능 시점', 'facts':[{'name':'근무기간','value':'3개월'}],
             'source_category':'all','document_ids':p['document_ids']}
    literal='벤처기업의 주식매수선택권은 언제부터 행사할 수 있나요?'
    path=core.lookup(h,current,p,question=literal)
    assert path['case_id']=='cm-016' and path['conditions']==core.conditions(current)
    assert len(path['targets'])==4 and path['legal_claim_reuse'] is False
    assert core.lookup(h,current,p,question='조세 감면의 금액은?') is None


def test_photo_question_discovers_real_venture_originals_with_fresh_handles(inputs,repo):
    from semantic_runtime.term_index import SourceMap
    from semantic_runtime.unit_fulltext import UnitFulltextIndex
    from semantic_runtime.navigation_match import ReverseMatcher
    from semantic_runtime.legal_agent.law_candidates import discover
    package,store,p=inputs;receipt=packages.import_package(repo,p,package,store)
    q='벤처기업의 주식매수선택권은 언제부터 행사할 수 있나요?'
    path=core.lookup(host(repo,receipt['source_binding']),{**state(package,p),'task':q},p,question=q)
    nav=json.loads((store.path/'navigation/manifest.json').read_text())
    index=UnitFulltextIndex(store.path/'fulltext',nav);db=index.connect()
    source_db=sqlite3.connect((store.path/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
    source_db.row_factory=sqlite3.Row
    tools=SimpleNamespace(sources=SourceMap(source_db));members=defaultdict(set)
    units={(r['document_id'],str(r['unit_id'])):{'parent':str(r['parent_id']) if r['parent_id'] is not None else None}
           for r in store.db.execute('SELECT document_id,unit_id,parent_id FROM source_unit')}
    for r in source_db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') AS unit_id FROM source"):
        current=str(r['unit_id']) if r['unit_id'] is not None else None
        while current is not None:
            members[(r['document_id'],current)].add(r['id'])
            current=units[(r['document_id'],current)]['parent']
    matcher=SimpleNamespace(members=members,units=units,unit_fulltext=index,unit_fulltext_db=db)
    matcher._unit_sources=lambda did,uid:ReverseMatcher._unit_sources(matcher,did,uid)
    events=[];s=SimpleNamespace(matcher=matcher,store=store,scope=set(p['document_ids']),tools=tools,
        core_evidence_route=path,repo=SimpleNamespace(event=lambda kind,value:events.append((kind,value))))
    try:
        selected,record=discover(SimpleNamespace(s=s))
        assert len(selected)==4 and record['discovery_mode']=='core-route'
        names={tools.sources[sid]['document_name'] for sid in selected}
        assert names=={'벤처기업육성에 관한 특별법','벤처기업육성에 관한 특별법 시행령'}
        assert all(sid.startswith('article:') for sid in selected)
        assert events[-1][0]=='CORE_EVIDENCE_ROUTE_USED' and events[-1][1]['legal_claim_reuse'] is False
    finally:source_db.close();db.close()


def test_rollback_preserves_records_and_is_not_undone_by_reimport(inputs,repo):
    package,store,p=inputs;receipt=packages.import_package(repo,p,package,store)
    before=repo.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]
    assert packages.retire_package(repo,p,receipt)['records_preserved'] is True
    assert packages.retire_package(repo,p,receipt)['retired']==51
    assert repo.search(p,limit=100)['pages']==[]
    assert repo.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==before
    with pytest.raises(MemoryError):packages.import_package(repo,p,package,store)


def test_forged_rollback_receipt_is_rejected(inputs,repo):
    package,store,p=inputs;receipt=packages.import_package(repo,p,package,store)
    bad=deepcopy(receipt);bad['records']=bad['records'][:-1]
    with pytest.raises(MemoryError):packages.retire_package(repo,p,bad)
    assert len(repo.search(p,limit=100)['pages'])==51


def test_source_change_at_commit_rolls_back_all_units(inputs,repo,monkeypatch):
    package,store,p=inputs;calls=[]
    def check():
        calls.append(1)
        if len(calls)>1:raise ValueError('changed during import')
    monkeypatch.setattr(store,'check_unchanged',check)
    with pytest.raises(ValueError):packages.import_package(repo,p,package,store)
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0
    assert repo.db.execute('SELECT count(*) FROM sw_import').fetchone()[0]==0
