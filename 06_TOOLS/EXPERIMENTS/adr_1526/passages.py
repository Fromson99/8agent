"""ADR-1526 step 1 (no model): the internal articles of 위험관리기준시행세칙 and every article-level original of the
Risk team's external documents, from each generation's navigation source table (heading, text, document name).

usage: passages.py   -> artifacts/passages.json.gz"""
from common import *
import sqlite3,re
LIQ=ROOT/'01_DATA/TERM_RELEASES/liquidity-compare-20261111-r1/generation'
MAIN=ROOT/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
INTERNAL='7a3907e193ec6c14'
PASSAGE_CHARS=250
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
def clean(name):
    """The document name a person would say: the last path part, without file number, extension and notice tail."""
    n=str(name).split('>')[-1].strip()
    n=re.sub(r'\.(hwpx?|pdf|docx?)$','',n);n=re.sub(r'^\d+\.\s*(\d{4}_)?','',n)
    return n.strip()
internal=[]
for sid,j in ro(LIQ/'navigation/navigation.sqlite').execute('SELECT id,json FROM source WHERE document_id=?',(INTERNAL,)):
    v=json.loads(j)
    internal.append({'id':sid,'heading':v.get('heading',''),'text':v.get('text',''),'unit_id':v.get('unit_id')})
internal.sort(key=lambda r:int(r['unit_id']) if str(r['unit_id']).isdigit() else 0)
docs={}
for d,j in ro(MAIN/'store.sqlite').execute('SELECT document_id,json FROM document'):
    v=json.loads(j);md=v.get('document_metadata') or {}
    teams={l.get('team') for l in [md,*md.get('aliases',[])] if isinstance(l,dict)}
    if 'risk_team' in teams and 'internal' not in v.get('doc',''):docs[d]={'path':v.get('doc',''),'name':clean(v.get('doc',''))}
external=[]
for sid,d,j in ro(MAIN/'navigation/navigation.sqlite').execute('SELECT id,document_id,json FROM source'):
    if d not in docs:continue
    v=json.loads(j);text=v.get('text','')
    if not text.strip():continue
    external.append({'id':sid,'document_id':d,'document':docs[d]['name'],'heading':v.get('heading',''),
                     'passage':(docs[d]['name']+' '+v.get('heading','')+'\n'+re.sub(r'\s+',' ',text))[:PASSAGE_CHARS]})
gz(ART/'passages.json.gz',{'internal':internal,'external':external,'documents':docs,'passage_chars':PASSAGE_CHARS,
    'sources':{'internal':str(LIQ.relative_to(ROOT)),'external':str(MAIN.relative_to(ROOT))}})
print('internal',len(internal),[r['heading'] for r in internal])
print('external passages',len(external),'documents',len({e['document_id'] for e in external}),'of',len(docs))
