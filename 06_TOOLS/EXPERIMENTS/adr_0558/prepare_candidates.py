"""Create only ADR0558 research snapshots; never edit product files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0558'
REL = Path('02_BACKEND/semantic_runtime/legal_agent')

MODULE = '''"""Pure request-local data presentation. Source journals remain canonical."""
from copy import deepcopy
import hashlib
import json

VERSION = 'model-presentation-v1'
INSTRUCTIONS = (' Shared documents and bodies are defined once in this request. '
    'Read exact_evidence.body_refs through bodies, and document_ref through documents. '
    'Cite only exact_evidence.evidence numbers; body/document names are not citations. '
    'Coordinate labels are stored source structure. Unknown version/structure remains unknown. '
    'Grouped route occurrences are correlated observations, not independent legal proof.')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def unique(rows):
    seen = set(); result = []
    for row in rows:
        key = encoded(row)
        if key not in seen:
            result.append(deepcopy(row)); seen.add(key)
    return result


def document_identity(e):
    # If provenance is absent, never deduplicate distinct evidence by text/name.
    if e.get('document_id') and e.get('source_artifact_hash'):
        return (e['document_id'], e['source_artifact_hash'], e.get('generation_id'))
    return ('unverified', e.get('evidence'), e.get('source_id'))


def span_identity(span):
    return tuple(span.get(k) for k in ('block_id','start_cp','end_cp','block_hash','span_hash'))


def project(original, phase):
    view = deepcopy(original)
    # Source selection cards share a law table. Titles and verbatim excerpts stay.
    laws = {}; law_keys = {}
    for section in ('originals', 'selected_original_excerpts'):
        for card in view.get(section, []):
            law = card.pop('law', None)
            if law is not None:
                ref = law_keys.setdefault(law, 'D'+str(len(law_keys)+1))
                laws[ref] = law; card['law_ref'] = ref
            links = card.get('via_references', [])
            card['via_references'] = unique(links)
    if laws:
        view['source_laws'] = laws
    plan = view.get('question_plan') or {}
    demands = {d['id']:d for d in plan.get('demands', []) if isinstance(d,dict) and 'id' in d}
    for status in view.get('answer_obligations', []):
        demand = demands.get(status.get('id'))
        if demand:
            for key,value in demand.items():
                if key != 'id' and status.get(key) == value:
                    status.pop(key, None)
    if phase != 'compose':
        return view
    documents = {}; doc_refs = {}; bodies = {}; body_refs = {}; evidence = []
    for e in view.get('exact_evidence', []):
        identity = document_identity(e)
        dref = doc_refs.setdefault(identity, 'D'+str(len(doc_refs)+1))
        documents[dref] = {'name':e.get('document_name') or '문서명 미확인',
            'version':e.get('document_version_label') or '선택된 원문 판본; 시행일 미확인'}
        text = e.get('text')
        if not isinstance(text,str):
            raise ValueError('Exact evidence body must be text')
        spans = e.get('spans', [])
        fingerprint = (identity, tuple(span_identity(p) for p in spans), text)
        # Same identity/range only; Unicode source bytes are never normalized.
        bkey = encoded(fingerprint)
        bref = body_refs.setdefault(bkey, 'B'+str(len(body_refs)+1))
        bodies[bref] = {'document_ref':dref, 'text':text}
        refs = [bref]
        for span in spans:
            # Never silently remove an extra context span absent from the body.
            if isinstance(span.get('text'),str) and span['text'] not in text:
                extra_key = encoded((identity,span_identity(span),span['text']))
                extra = body_refs.setdefault(extra_key,'B'+str(len(body_refs)+1))
                bodies[extra] = {'document_ref':dref,'text':span['text']}
                if extra not in refs: refs.append(extra)
        row = {k:deepcopy(e[k]) for k in ('evidence','role','temporal_status','coverage') if k in e}
        row.update(document_ref=dref, body_refs=refs,
            coordinate_label=e.get('coordinate_label') or e.get('heading') or '구조 위치 미확인')
        evidence.append(row)
    view['exact_evidence'] = evidence
    view['documents'] = documents; view['bodies'] = bodies
    view['presentation_version'] = VERSION
    return view


def mapping(original, projected):
    rows = projected.get('exact_evidence', [])
    original_rows = original.get('exact_evidence', [])
    if len(rows) != len(original_rows):
        raise ValueError('Presentation must retain all evidence choices')
    result = []
    for e,row in zip(original_rows,rows):
        if row['evidence'] != e['evidence']:
            raise ValueError('Evidence choice changed')
        body = projected['bodies'][row['body_refs'][0]]
        if body['text'] != e['text']:
            raise ValueError('Exact original cannot be reconstructed')
        for ref in row['body_refs']:
            if ref not in projected['bodies']:
                raise ValueError('Body reference unresolved')
        if row['document_ref'] not in projected['documents']:
            raise ValueError('Document reference unresolved')
        result.append({'evidence':e['evidence'],'document_ref':row['document_ref'],
            'body_refs':row['body_refs'],'canonical_identity':document_identity(e),
            'spans':[span_identity(p) for p in e.get('spans',[])],
            'text_sha256':hashlib.sha256(e['text'].encode()).hexdigest()})
    return result
'''


def replace(path, old, new):
    text = path.read_text()
    assert old in text, (path,old[:120])
    path.write_text(text.replace(old,new))


def main():
    for arm in ('presentation','selected-only'):
        folder = BASE/arm/'snapshot'/REL
        (folder/'model_presentation.py').write_text(MODULE)
        gateway = folder/'gateway.py'
        replace(gateway,"        schema = self.protocol", "        original_view = view\n        schema = self.protocol")
        replace(gateway,"references or NumberedReferences(view)","references or NumberedReferences(original_view)")
        replace(gateway, "WIRE_PROJECTION = 'compact-v5-v1'", "WIRE_PROJECTION = 'compact-v5-v2'\nfrom .model_presentation import project, mapping, INSTRUCTIONS as DATA_INSTRUCTIONS")
        replace(gateway, "    result = deepcopy(view)\n", "    result = project(view, phase)\n")
        # Projection precedes numbered ID removal, preserving canonical identity.
        replace(gateway, "        numbered_instructions = ''\n", "        numbered_instructions = ''\n        if self.compact:\n            view = compact_wire_view(view, phase)\n")
        replace(gateway, "        if self.compact:\n            view = compact_wire_view(view, phase)\n        user = {'view': view}", "        if self.compact and phase == 'compose':\n            view.pop('navigation_choices', None)\n            for kind in ('targets','blocks','cursors'):\n                view.get('reference_numbers', {}).pop(kind, None)\n            prompt += DATA_INSTRUCTIONS\n        user = {'view': view}")
        repo = folder/'relations_repository.py'
        replace(repo, "        expected = stored\n", "        expected = stored\n        if wire_projection is not None:\n            from .gateway import WIRE_PROJECTION, compact_wire_view\n            if self.VERSION != 5 or wire_projection != WIRE_PROJECTION:\n                raise ContractError('unsupported wire projection')\n            expected = compact_wire_view(stored, stored['phase'])\n            if stored['phase'] == 'compose':\n                from .model_presentation import mapping\n                presentation_mapping = mapping(stored, expected)\n            else:\n                presentation_mapping = []\n")
        replace(repo, "            expected = verified.view(stored)", "            expected = verified.view(expected)")
        old = "        if wire_projection is not None:\n            from .gateway import WIRE_PROJECTION, compact_wire_view\n            if self.VERSION != 5 or wire_projection != WIRE_PROJECTION:\n                raise ContractError('unsupported wire projection')\n            expected = compact_wire_view(expected, stored['phase'])"
        replace(repo,old,"        if wire_projection is not None and stored['phase'] == 'compose':\n            expected.pop('navigation_choices', None)\n            for kind in ('targets','blocks','cursors'):\n                expected.get('reference_numbers', {}).pop(kind, None)")
        replace(repo, "'stored_view_hash': digest(stored), 'wire_view_hash': digest(wire)})", "'stored_view_hash': digest(stored), 'wire_view_hash': digest(wire),\n                    'evidence_body_mapping': presentation_mapping})")
        sources = folder/'exploration_tools.py'
        insertion = '''    def presentation_location(self, evidence):
        e = self.repo.evidence(evidence)
        chain = [self.matcher.units[(e['document_id'],uid)]
                 for uid in self.ancestors(e['document_id'],e['unit_id'])]
        labels = [' '.join(str(u[k]) for k in ('surface','title') if u.get(k)) for u in chain]
        return {'coordinate_label':' > '.join(x for x in labels if x) or
                    e['metadata'].get('heading') or '구조 위치 미확인',
                'document_id':e['document_id'],'unit_id':e['unit_id'],
                'source_artifact_hash':e['source_artifact_hash'],'generation_id':e['generation_id']}

'''
        replace(sources,"    def location(self, target):",insertion+"    def location(self, target):")
        views = folder/'relation_views.py'
        replace(views, "**s.sources.location(ident)})", "**s.sources.location(ident), **s.sources.presentation_location(ident)})")
        tiers = folder/'workflow_tiers_views.py'
        replace(tiers,"**s.sources.location(e['evidence_id'])} for e in evidence]", "**s.sources.location(e['evidence_id']), **s.sources.presentation_location(e['evidence_id'])} for e in evidence]")
        if arm == 'selected-only':
            replace(views,"    required=list(dict.fromkeys(required))", "    required=list(dict.fromkeys(required))\n    selected_required = list(required)\n    connection_reasons = {}")
            replace(views,"                required=list(dict.fromkeys(required+a['source_evidence']+a['target_evidence']))", "                for ident in a['source_evidence']+a['target_evidence']:\n                    if ident not in selected_required:\n                        connection_reasons.setdefault(ident, []).append(h['entity_id'])\n                required=list(dict.fromkeys(required+a['source_evidence']+a['target_evidence']))")
            replace(views,"    preferred=list(dict.fromkeys(required+[e for o in observations for e in o.get('evidence_ids',[])]))", "    preferred=(required if phase == 'compose' else list(dict.fromkeys(required+[e for o in observations for e in o.get('evidence_ids',[])])))")
            replace(views,"        'budgets':s.work.budget(),", "        'compose_delivery':{'selected_evidence':selected_required,'required_connections':connection_reasons} if phase == 'compose' else None,\n        'budgets':s.work.budget(),")
        selector = folder/'source_selection.py'
        replace(selector,"import time\n", "import time\nfrom .model_presentation import unique\n")
        replace(selector,"for x in p['links'][:3]]", "for x in p['links']]\n        links = unique(links)")
        replace(selector,"'via_queries': p['direct'][:3], 'via_references': links,", "'via_queries': p['direct'][:3], 'via_references': links[:3],")
        replace(selector,"len(p['links'])-3", "len(links)-3")
        replace(selector,"        for x in c['via_references'][:2]:", "        for x in c['via_references']:")
        replace(selector,"        n=c['rediscovery']", "        edges=unique(edges)[:2]\n        n=c['rediscovery']")
        print('Prepared',arm)


if __name__ == '__main__': main()
