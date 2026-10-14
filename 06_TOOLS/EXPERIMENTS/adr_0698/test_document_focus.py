from semantic_runtime.legal_agent import structure_query as sq
from test_structure_first_search import matcher


def test_named_document_batch_restricts_bare_coordinate():
 out=sq.catalogue(matcher(),['law','decree'],queries=['자본시장법 제6조','제6조'])
 assert {x['document_id'] for x in out['items']}=={'law'}


def test_multiple_named_documents_survive_focus():
 out=sq.catalogue(matcher(),['law','decree'],queries=['자본시장법 제6조','자본시장법 시행령 제6조','제6조'])
 assert {x['document_id'] for x in out['items']}=={'law','decree'}


def test_unbound_coordinate_remains_broad_structure():
 out=sq.catalogue(matcher(),['law','decree'],queries=['제6조'])
 assert {x['document_id'] for x in out['items']}=={'law','decree'} and not out['citation_eligible']


def test_inaccessible_name_cannot_become_bare_coordinate_fallback():
 out=sq.catalogue(matcher(),['law'],queries=['자본시장법 시행령 제6조','제6조'])
 assert out['items']==[] and out['total']==0


def test_focused_page_cursor_preserves_named_document_set():
 m=matcher();q=['자본시장법','제6조','제6조의2'];first=sq.catalogue(m,['law','decree'],queries=q,limit=1)
 rows=first['items'];offset=first['next_offset']
 while offset is not None:
  page=sq.catalogue(m,['law','decree'],queries=q,limit=1,offset=offset);rows+=page['items'];offset=page['next_offset']
 assert len(rows)==first['total'] and {x['document_id'] for x in rows}=={'law'}
 assert len({(x['kind'],x['document_id'],x.get('unit_id')) for x in rows})==len(rows)
