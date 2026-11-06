from common import *
from copy import deepcopy
sys.path.insert(0,'/tmp/adr1355-grammar');import xgrammar
f=read(DES/'candidate-repaired.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.wire_schema import discriminator_first
p=ROOT/'04_EXPERIMENTS/ADR/ADR-1361-repaired-qwen-bf16-answers/artifacts/public-live/B03-03-deepinfra/raw/call-007/request.json.gz'
s=read(p)['response_format']['json_schema']['schema'];old=deepcopy(s['properties']['read_judgment_review']['properties']['judgments']['items']);old['$defs']=s['$defs'];new,count=discriminator_first(old)
assert old==new
compiler=xgrammar.GrammarCompiler(xgrammar.TokenizerInfo([bytes([i]) for i in range(256)],stop_token_ids=[]),max_threads=1)
rows=[]
for label,schema in [('old',old),('new',new)]:
 compiled=compiler.compile_json_schema(schema)
 for status in ['USE','CONDITIONAL','UNRESOLVED','NOT_USED']:
  matcher=xgrammar.GrammarMatcher(compiled);prefix='{"id":"J1","disposition":"'+status+'"'
  rows.append({'schema':label,'selected_status':status,'prefix_accepted':matcher.accept_string(prefix)})
put(ART/'local-grammar-prefix.json',{'rows':rows,'old_and_new_json_schema_equal':old==new,'discriminator_order_changes':count,'xgrammar_version':'0.2.8','tokenizer':'256 byte tokens; local mechanism probe only','remote_backend_or_version_not_identified':True,'model_calls':0})
print(json.dumps(rows))
