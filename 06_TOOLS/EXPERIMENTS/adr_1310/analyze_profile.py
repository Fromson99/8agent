from common import *
import collections
area=sys.argv[1] if len(sys.argv)>1 else 'profile';P=ART/area/'ontology-369-profile'
functions=read(P/'function-timings.json');samples=read(P/'sample-stacks.json.gz');sql=read(P/'sql-observation.json');result=read(P/'result.json')
leaf=collections.Counter();inclusive=collections.Counter();modules=collections.Counter()
for r in samples['stacks']:
 chain=[tuple(x) for x in r['stack']];sec=r['seconds']
 if chain:leaf[chain[0]]+=sec;modules[chain[0][0]]+=sec
 for x in set(chain):inclusive[x]+=sec
fmt=lambda rows:[{'file':k[0],'line':k[1],'function':k[2],'sample_seconds':v} for k,v in rows]
queries=[]
for r in sql['query_stats']:
 if r['phase']!='request':continue
 queries.append({**r,**sql['sql_shapes'].get(r['query_id'],{})})
report={'area':area,'result':result,'sampled_seconds':samples['sampled_seconds'],'sampler_thread_cpu_seconds':samples['sampler_thread_cpu_seconds'],'top_sample_leaf':fmt(leaf.most_common(60)),'top_sample_inclusive':fmt(inclusive.most_common(80)),'top_leaf_modules':[{'file':k,'seconds':v} for k,v in modules.most_common(40)],'functions_by_inclusive':[{'name':k,**v} for k,v in sorted(functions['functions'].items(),key=lambda kv:kv[1]['inclusive_seconds'],reverse=True)],'functions_by_exclusive':[{'name':k,**v} for k,v in sorted(functions['functions'].items(),key=lambda kv:kv[1]['exclusive_seconds'],reverse=True)],'queries_by_time':sorted(queries,key=lambda r:r['exclusive_seconds'],reverse=True),'queries_by_calls':sorted(queries,key=lambda r:r['calls'],reverse=True),'trace_seconds':sql['trace_callback_seconds']}
put(ART/(area+'-analysis.json'),report)
print('RESULT',result)
print('FUNCTION EXCLUSIVE',[(r['name'],r['calls'],round(r['exclusive_seconds'],3),round(r['inclusive_seconds'],3)) for r in report['functions_by_exclusive'][:16]])
print('SAMPLE LEAF',[(r['file'],r['function'],round(r['sample_seconds'],3)) for r in report['top_sample_leaf'][:15]])
print('SQL TIME',[(r['database'],r['calls'],round(r['exclusive_seconds'],3),r['rows'],r.get('shape','')[:140]) for r in report['queries_by_time'][:12]])
print('SQL COUNT',[(r['database'],r['calls'],round(r['exclusive_seconds'],3),r.get('shape','')[:130]) for r in report['queries_by_calls'][:8]])
