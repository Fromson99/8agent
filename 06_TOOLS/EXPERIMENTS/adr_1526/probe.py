"""ADR-1526 step 3: for each internal article of 위험관리기준시행세칙,
  (a) vector candidates: the nearest external articles among all 432 Risk team external documents (no model),
  (b) one connection step from the top 5 candidates (the generation's reference index, both directions, no model),
  (c) --model: ONE Qwen3.8 call that reads the internal articles, the candidates and the external document list and
      picks, per internal article, the governing external documents and articles (or none), with search words.
Checked against design expected.json (written before any result).

usage: probe.py            vector + connections only
       probe.py --model    the same, then one model call"""
from common import *
import re,sqlite3
import numpy as np
MAIN=ROOT/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
TOP,SHOW,HOP_FROM=10,8,5
p=read(ART/'passages.json.gz');expected=read(ART/'expected.json')
E=np.load(ART/'vectors-external.npy');I=np.load(ART/'vectors-internal.npy')
ext=p['external'];internal=p['internal']
def display(path,name):
    """An annex is its own document; its name gets the rule it belongs to (the vectors were made without it)."""
    parts=[x.strip() for x in str(path).split('>')]
    if '별표서식' in parts:
        i=parts.index('별표서식');return (parts[i-1]+' '+name).strip()
    return name
for e in ext:
    e['vector_document']=e['document'];e['document']=display(p['documents'][e['document_id']]['path'],e['document'])
by_id={e['id']:e for e in ext}
nav=sqlite3.connect((MAIN/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
def label(sid):
    if sid in by_id:return by_id[sid]['document'],by_id[sid]['heading']
    row=nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
    if not row:return '?',sid
    v=json.loads(row[0]);return str(v.get('document_name','')).split('>')[-1].strip(),v.get('heading','')
def hops(sid):
    out=set();inn=set()
    for (j,) in nav.execute("SELECT json FROM reference WHERE json_extract(json,'$.source_id')=?",(sid,)):
        out.update(t['source_id'] for t in json.loads(j).get('targets',[]))
    for (rid,) in nav.execute('SELECT reference_id FROM reference_target WHERE source_id=?',(sid,)):
        row=nav.execute('SELECT json FROM reference WHERE id=?',(rid,)).fetchone()
        if row:inn.add(json.loads(row[0])['source_id'])
    return [{'id':s,'document':label(s)[0],'heading':label(s)[1]} for s in sorted(out-{sid})][:12],\
           [{'id':s,'document':label(s)[0],'heading':label(s)[1]} for s in sorted(inn-{sid})][:12]
def matches(item,want):
    doc,art=want['document'],want['article']
    if doc not in item['document']:return False
    return art is None or item['heading'].startswith(art+' ') or item['heading']==art or art in item['document']
rows=[]
for k,a in enumerate(internal):
    s=E@I[k];order=np.argsort(-s)[:300]
    top=[{'rank':r+1,'id':ext[i]['id'],'document':ext[i]['document'],'heading':ext[i]['heading'],'score':round(float(s[i]),4)} for r,i in enumerate(order[:TOP])]
    docs={}
    for i in order[:60]:docs.setdefault(ext[i]['document'],[]).append(float(s[i]))
    doc_rank=sorted(((d,round(sum(sorted(v,reverse=True)[:3]),3),len(v)) for d,v in docs.items()),key=lambda x:-x[1])[:8]
    connected=[]
    for c in top[:HOP_FROM]:
        o,n=hops(c['id']);connected.append({'from':c['heading'],'outgoing':o,'incoming':n})
    rows.append({'internal':a['heading'],'top':top,'documents':doc_rank,'connections':connected})
# expected pairs: vector top-10 and one step from the top 5
for pair in expected['pairs']:
    row=next(r for r in rows if r['internal']==pair['internal'])
    pair['found']=[{'want':w,'vector_rank':next((t['rank'] for t in row['top'] if matches(t,w)),None),
                    'one_step':any(matches(x,w) for c in row['connections'] for x in c['outgoing']+c['incoming'])} for w in pair['external']]
result={'rows':rows,'expected':expected['pairs']}
if '--model' in sys.argv:
    sys.path[:0]=[str(ROOT/'02_BACKEND'),str(ROOT)]
    from lawrag.research.experiment_client import ExperimentClient
    names=sorted({e['document'] for e in ext})
    doc_ids={n:'D%d'%(i+1) for i,n in enumerate(names)}
    cand={}
    for k,r in enumerate(rows):
        cand['A%d'%(k+1)]=[{'id':'A%dC%d'%(k+1,j+1),'document':t['document'],'heading':t['heading'],
                            'excerpt':by_id[t['id']]['passage'][len(by_id[t['id']]['vector_document']):].strip()[:200]} for j,t in enumerate(r['top'][:SHOW])]
    all_c=[c['id'] for v in cand.values() for c in v]
    data={'company_facts':['회사는 금융투자업자(증권회사)이다.','회사는 종합금융투자사업자로 지정되어 있다.'],
          'internal_document':'위험관리기준시행세칙',
          'internal_articles':[{'id':'A%d'%(k+1),'heading':a['heading'],'text':a['text']} for k,a in enumerate(internal)],
          'candidates':cand,'documents':[{'id':doc_ids[n],'name':n} for n in names]}
    schema={'type':'object','additionalProperties':False,'required':['articles'],'properties':{'articles':{'type':'array','minItems':len(internal),'maxItems':len(internal),
        'items':{'type':'object','additionalProperties':False,'required':['internal_id','basis','documents','candidates','search_words','reason'],
          'properties':{'internal_id':{'enum':['A%d'%(k+1) for k in range(len(internal))]},
                        'basis':{'enum':['DIRECT','NAMED','INFERRED','NONE']},
                        'documents':{'type':'array','maxItems':6,'items':{'enum':list(doc_ids.values())}},
                        'candidates':{'type':'array','maxItems':6,'items':{'enum':all_c}},
                        'search_words':{'type':'array','maxItems':4,'items':{'type':'string'}},
                        'reason':{'type':'string'}}}}}}
    system=('너는 증권회사 리스크관리부서의 규정 담당자다. 현업은 외규(법령·감독규정·시행세칙 등)를 조사해 그 요구를 바탕으로 '
            '"우리 회사는 이렇게 한다"는 내규를 만든다. 내규(internal_articles)의 각 조문이 근거로 삼는 외규를 찾는다. 각 조문마다: '
            '(1) documents: 근거가 되는 외규 문서를 documents 목록의 id로 고른다(여러 개 가능, 근거 외규가 없으면 빈 목록). '
            '(2) candidates: 그 조문의 후보(candidates[조문 id], 비슷한 외규 조문을 자동으로 찾은 것) 중 실제 근거로 보이는 것만 고른다. '
            '엉뚱한 후보는 고르지 않는다(다른 업권·다른 주제 등). '
            '(3) search_words: 후보에 근거 조문이 없거나 부족하면 외규에서 찾을 말을 외규 표현으로 쓴다(예: 건전성비율 → 재무건전성 순자본비율). '
            '(4) basis: DIRECT=내규가 외규 조문을 직접 적음, NAMED=외규 이름만 적음, INFERRED=내용으로 짐작, NONE=회사 자체 기준이라 외규 근거 없음. '
            '(5) reason: 판단 이유 한두 문장. 회사 정보(company_facts)에 맞지 않는 업권의 외규(예: 은행·보험)는 고르지 않는다.')
    client=ExperimentClient(ROOT,ART/'model',max_calls=4,fallback_policy=ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json')
    gz(ART/'model-input.json.gz',{'system':system,'data':data,'schema':schema})
    value=client.generate(system,data,schema,phase='pairing')
    gz(ART/'model-output.json.gz',value)
    back={v:n for n,v in doc_ids.items()};cmap={c['id']:c for v in cand.values() for c in v}
    picks=[]
    for x in value['articles']:
        k=int(x['internal_id'][1:])-1
        picks.append({'internal':internal[k]['heading'],'basis':x['basis'],'documents':[back[d] for d in x['documents']],
                      'candidates':[{'document':cmap[c]['document'],'heading':cmap[c]['heading'],'own':c.startswith(x['internal_id']+'C')} for c in x['candidates']],
                      'search_words':x['search_words'],'reason':x['reason']})
    result['model']={'picks':picks,'usage':client.usage}
    for pair in result['expected']:
        pick=next((q for q in picks if q['internal']==pair['internal']),None)
        for f in pair['found']:
            f['model_chose']=bool(pick) and any(matches(c,f['want']) for c in pick['candidates'])
            f['model_document']=bool(pick) and any(f['want']['document'] in d for d in pick['documents'])
put(ART/('result-model.json' if '--model' in sys.argv else 'result-vector.json'),result)
for r in rows:
    print('==',r['internal']);print('   문서:',[(d,s) for d,s,_ in r['documents'][:5]])
    for t in r['top'][:6]:print('   %2d %.3f %s | %s'%(t['rank'],t['score'],t['document'][:28],t['heading'][:40]))
for pair in result['expected']:print('expected',pair['internal'],[(f['want']['document'][:10],f['want']['article'],f['vector_rank'],f['one_step'],f.get('model_chose'),f.get('model_document')) for f in pair['found']])
if '--model' in sys.argv:
    for q in result['model']['picks']:print('MODEL',q['internal'],q['basis'],q['documents'],[(c['document'][:14],c['heading'][:30]) for c in q['candidates']],q['search_words'])
