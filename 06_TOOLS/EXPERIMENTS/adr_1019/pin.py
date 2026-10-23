from common import *
meta=read(DES/'candidate.json');P=ROOT/meta['path'];S=P/'snapshot'/meta['selected_code_relative'];config=read(S/'00_SYSTEM/PIPELINE.json')
for entry in config['engines'].values():
 p=S/entry['manifest'];engine=read(p);engine['files']={n:sha(S/n) for n in engine['files']};put(p,engine);entry['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',config)
