"""Explicit, session-owned synthetic fixture. Uses the real local workflow."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3


def fixture():
    from semantic_runtime.legal_agent.ontology_compiler import content_hash
    text = '예시 업무의 검토 대상과 기준일을 확인한다. 금액은 승인된 산정 기준에 따라 확인한다. 제외 대상은 별도 검토한다.'
    work = {'version': 'ontology-work-v1', 'concept': '업무 검토 · 범위와 산정 기준',
            'originals': [{'id': 'S1', 'text': text, 'anchor': {'document_id': 'DEMO-DOC-01',
                          'version': 'demo-v1', 'unit_id': 'demo-unit-1', 'label': '합성 검토지침 · 제1조',
                          'content_sha256': content_hash(text)}}],
            'judgments': [{'id': 'J1', 'source_ids': ['S1'], 'judgment': {'finding': '검토 대상과 기준일을 함께 확인', 'reason': '원문 첫 문장의 확인 항목'}, 'origin': {'run_id': 'DEMO-QUESTION-A'}},
                          {'id': 'J2', 'source_ids': ['S1'], 'judgment': {'finding': '산정 기준의 별도 원문은 미확보', 'reason': '현재 확보한 원문에 세부 산식이 없음'}, 'origin': {'run_id': 'DEMO-QUESTION-B'}}],
            'origin': {'run_id': 'DEMO-QUESTION-A', 'synthetic': True}}
    proposal = {'components': [
        {'id': '적용 범위', 'text': '예시 업무의 검토 대상과 기준일을 확인한다.', 'requires': [], 'basis': [{'source': 'S1', 'quote': '예시 업무의 검토 대상과 기준일을 확인한다.'}]},
        {'id': '산정 기준', 'text': '금액은 승인된 산정 기준에 따라 확인한다.', 'requires': ['적용 범위'], 'basis': [{'source': 'S1', 'quote': '금액은 승인된 산정 기준에 따라 확인한다.'}]},
        {'id': '제외 확인', 'text': '제외 대상은 별도로 검토한다.', 'requires': [], 'basis': [{'source': 'S1', 'quote': '제외 대상은 별도 검토한다.'}]},
        {'id': '추가 조사', 'text': '세부 산정 기준의 원문은 미확보이며 추가 확인이 필요하다.', 'requires': [], 'basis': [{'source': 'S1', 'quote': '승인된 산정 기준'}]}],
        'paths': [{'id': 'NORMAL', 'title': '일반 검토 경로', 'business_use': '검토 범위와 산정 기준을 함께 확인할 때', 'conditions': ['적용 범위'], 'calculations': ['산정 기준'], 'outcomes': ['산정 기준'], 'notes': ['추가 조사']},
                  {'id': 'EXCEPTION', 'title': '제외 확인 경로', 'business_use': '제외 여부를 추가 검토할 때', 'conditions': ['적용 범위'], 'calculations': [], 'outcomes': ['제외 확인'], 'notes': ['추가 조사']}],
        'unused_components': {}}
    return work, proposal


def create_demo():
    from semantic_runtime.ontology_work.repository import Repository
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.ontology_work.store import LocalFolderStore
    from ontology_dashboard_model import Dashboard
    owner = TemporaryDirectory(prefix='ontology-dashboard-demo-')
    root = Path(owner.name)
    repo = Repository(lambda: sqlite3.connect(root / 'demo.sqlite', timeout=5))
    repo.initialize()
    work, proposal = fixture()
    wf = Workflow(repo, LocalFolderStore(root / 'work'), actor='DEMO-REVIEWER',
                  source_reader=lambda anchor: work['originals'][0]['text'] if anchor == work['originals'][0]['anchor'] else None)
    first = wf.save(work, proposal, bundle_id='cb-demo-review')
    wf.review(first['bundle_id'], 1, first['work_hash'], True, '합성 예시의 이전 검토')
    wf.publish(first['bundle_id'], 1, first['work_hash'], 0)
    revised = deepcopy(proposal)
    revised['components'][1]['text'] = '승인된 산정 기준을 확인한다. 세부 산식은 현재 원문만으로 확정하지 않는다.'
    wf.save(work, revised, bundle_id=first['bundle_id'], expected_revision=1)
    approved = deepcopy(work); approved['concept'] = '기준일 확인 · 골드 이관 대기'
    saved = wf.save(approved, proposal, bundle_id='cb-demo-approved')
    wf.review(saved['bundle_id'], 1, saved['work_hash'], True, '합성 원문과 조립 경로 확인')
    waiting = deepcopy(work); waiting['concept'] = '제외 대상 · 생성 대기'
    wf.enqueue(waiting)
    rejected = deepcopy(work); rejected['concept'] = '적용 범위 · 보완 요청'
    saved = wf.save(rejected, proposal, bundle_id='cb-demo-rejected')
    wf.review(saved['bundle_id'], 1, saved['work_hash'], False, '범위 설명을 보완한 뒤 다시 검토')
    return Dashboard(wf, demo=True), owner
