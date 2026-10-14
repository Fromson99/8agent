from pathlib import Path
import json,sqlite3,collections,hashlib,gzip
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display';S=R/'02_BACKEND/lawrag/research/candidates/adr_0772/provider-display/snapshot'
p=S/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py';s=p.read_text().replace("'law': '법제처', 'moleg': '법제처'", "'law': '법제처', 'moleg': '법제처', 'fsc': '금융위원회',\n                     'expc': '법제처 (법령해석례)', 'prec': '판례'")
s=s.replace('parts = [p.strip() for p in re.split(r"\\s*>\\s*" if ">" in row else r"/", row)]', 'prefix = re.match(r"^(external|internal)\\s*([>/])", row, re.I)\n        if not prefix:\n            return None, row\n        parts = [p.strip() for p in row.split(prefix.group(2))]')
s=s.replace("return '내부규정', parts[-1] or '문서명 미확인'", "return '내부 규정', ' / '.join(parts[3:] if len(parts) >= 4 and parts[2].lower() in {'forms', 'rules', 'regulations'} else parts[2:] if len(parts) >= 3 else parts[1:]) or '문서명 미확인'")
p.write_text(s)
p=S/'05_TESTS/CONTRACTS/test_workflow_source_cards.py';s=p.read_text().replace("'내부규정'", "'내부 규정'")
s+='''\n\n@pytest.mark.parametrize('code,label', [('fsc','금융위원회'),('expc','법제처 (법령해석례)'),('prec','판례'),('moleg','법제처')])
def test_registered_additional_source_labels(view, code, label):
    text=view._ChatProgress({})._card_rationale('검색',[f'external > team > {code} > 자료명'])
    assert '외부법률 / '+label in text and '1. 자료명' in text
    assert code not in text


def test_nested_annex_keeps_parent_law_and_internal_category(view):
    text=view._ChatProgress({})._card_rationale('검색',[
        'external > risk_team > law > 전자금융감독규정 > 별표서식 > [별지 1] 삭제',
        'internal > financial_team > forms > 상장주선인의 기업실사점검표(2024.12.31)'])
    assert '전자금융감독규정 / 별표서식 / ' in text
    assert '내부 규정' in text and '1. 상장주선인의' in text
    assert 'forms' not in text and 'team' not in text
''';p.write_text(s)
base=Path('01_DATA/TERM_RELEASES/native-cm-serving-20261008-r2-index/serving/baseline/generation');db=sqlite3.connect(f'file:{base}/store.sqlite?mode=ro',uri=True);counts=collections.Counter()
for name,raw in db.execute('select name,json from document'):
 folders=json.loads(raw).get('document_metadata',{}).get('folder_names',[])
 key='/'.join(folders[:3]) if folders and folders[0]=='external' else '/'.join(folders[:2]) if folders else 'unprefixed'
 counts[key]+=1
p=A/'artifacts/design/provider-label-evidence.json';v=json.loads(p.read_text());v['selected_local_db_source_counts']=dict(counts);v['actual_GENOS_database']='Unavailable; no field DB lookup claimed';v['additional_registry']='semantic_runtime.folder_navigation.PUBLIC_PROVIDERS; lawrag.pipeline collect_expc/fsc/prec module descriptions'
v['mapping'].update(fsc='금융위원회',expc='법제처 (법령해석례)',prec='판례',internal='내부 규정')
db=sqlite3.connect('file:01_DATA/LEXICON/glossary-v1/boundary-20260914-v3/dictionary.sqlite?mode=ro',uri=True);db.row_factory=sqlite3.Row
for label in ['금융위원회','법령해석','판례']:v['entries'].append(dict(db.execute('select id,source,label,english from entry where label=? limit 1',(label,)).fetchone()))
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
D=R/'08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2'
for p in D.iterdir():
 (A/'artifacts'/('development-r2-rev001-'+p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
