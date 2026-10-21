"""Frozen synthetic initial-hint projection ledger; zero model calls.

Both arms call the same public navigation_context helper with the same supplied
matched metadata. This measures available locations -> initial hint locations,
not matcher recall, original acquisition, legal applicability or answer quality.
Run in separate processes against the frozen baseline/candidate code roots.
"""
from pathlib import Path
from types import SimpleNamespace as NS
import argparse
import hashlib
import json
import os
import sys


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fixture():
    did='synthetic-navigation-document'
    name='합성시험규정';term='합성기준'
    question=name+"에서 '"+term+"'의 정의 위치를 확인하라."
    units={};sources={};definitions={}
    for number in range(19):
        uid=str(number);sid='synthetic-source-'+uid
        units[(did,uid)]={'surface':'제'+str(number+1)+'조',
            'coordinate_key':'body:제'+str(number+1)+'조',
            'title':'합성 정의 '+str(number+1),'parent':None,
            'coordinate_scope':'body','coordinate_binding':{'mode':'stored'}}
        sources[sid]={'document_id':did,'unit_id':uid}
        definitions['synthetic-definition-'+uid]={
            'id':'synthetic-definition-'+uid,'key':term,'document_id':did,
            'unit_id':uid,'source_id':sid,'scope_status':'UNRESOLVED'}
    start=question.index(term)
    matches={'documents':[{'id':did,'name':name}],'structures':[],
        'terms':[{'id':'synthetic-term','question_spans':[
            {'start':start,'end':start+len(term),'text':term}]}]}
    matcher=NS(documents={did:name},units=units,sources=sources,
        tools=NS(terms={'synthetic-term':{'label':term}},definitions=definitions))
    available=[{'doc_id':did,'node':number} for number in range(19)]
    declaration={'question':question,'scope':[did],'matches':matches,
        'units':[{'document_id':d,'unit_id':u,**value} for (d,u),value in units.items()],
        'sources':sources,'definitions':definitions,'available':available}
    return question,matcher,[did],matches,available,declaration


def run(code_root,arm):
    repository=Path(__file__).resolve().parents[3]
    sys.dont_write_bytecode=True
    os.environ.update(SOURCE_PROVIDER_PROJECT_ROOT=str(repository),
        LAWRAG_WORKSPACE_ROOT=str(repository),LAWRAG_TOOL_WORKSPACE_ROOT=str(repository))
    sys.path[:0]=[str(code_root/'02_BACKEND'),str(code_root),str(repository/'02_BACKEND')]
    from semantic_runtime.legal_agent import structure_query as sq
    selected=Path(sq.__file__).resolve()
    if not selected.is_relative_to(code_root):raise RuntimeError('native helper is outside selected code root')
    question,matcher,scope,matches,available,declaration=fixture()
    hints=sq.navigation_context(question,matcher,scope,matches=matches)
    occurrences=[]
    for kind in ('structures','definitions'):
        for row in hints[kind]:
            did,uid=row['document_id'],str(row['unit_id'])
            if did not in scope or (did,uid) not in matcher.units:
                raise RuntimeError('returned location is outside the exact fixture scope/structure')
            occurrences.append({'kind':kind,'doc_id':did,'node':int(uid)})
    keys={(row['doc_id'],row['node']) for row in occurrences}
    presented=[{'doc_id':did,'node':node} for did,node in sorted(keys)]
    available_keys={(r['doc_id'],r['node']) for r in available}
    if not keys<=available_keys:raise RuntimeError('native output invented a location')
    discarded=[{**row,'reason':'NOT_PRESENT_IN_NATIVE_INITIAL_HINT_OUTPUT'}
               for row in available if (row['doc_id'],row['node']) not in keys]
    return {'case_id':'navigation-inventory','arm':arm,
        'measurement':'synthetic available_locations -> native initial_navigation projection',
        'model_calls':0,'legal_quality_evaluation':False,'original_acquisition_measured':False,
        'matcher_recall_measured':False,'available':available,'presented':presented,
        'discarded':discarded,'occurrences':occurrences,
        'counts':{'available_unique':len(available),'presented_unique':len(presented),
            'presented_occurrences':len(occurrences),
            'hints':{kind:len(hints[kind]) for kind in ('documents','structures','terms','definitions')}},
        'fixture_sha256':sha(encoded(declaration).encode()),
        'hints_sha256':sha(encoded(hints).encode()),
        'hints':hints,'code_root':str(code_root),
        'native_helper':{'path':str(selected),'sha256':sha(selected.read_bytes())},
        'runner':{'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__).read_bytes())}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--code-root',type=Path,required=True)
    parser.add_argument('--arm',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.code_root.resolve(),args.arm)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'counts':result['counts'],
                      'fixture_sha256':result['fixture_sha256']},ensure_ascii=False))


if __name__=='__main__':main()
