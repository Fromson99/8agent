"""DOM renderer: untrusted source/relevance text is always assigned with textContent."""
SCRIPT = r'''
function renderSourceTiers(bundle) {
  const root=document.getElementById('sources');root.replaceChildren();
  if(!bundle)return;
  if(bundle.schema_version==='workflow-source-v1'){
    root.dataset.bundleHash=bundle.bundle_hash;
    for(const c of bundle.sources){
      const node=document.createElement('article');root.append(node);
      for(const [tag,text] of [['h4',c.document_name+' · '+c.coordinate_label],
                             ['p',c.side==='internal'?'내규':'외규'],['blockquote',c.excerpt]]){
        const n=document.createElement(tag);n.textContent=text;node.append(n);
      }
    }
    return;
  }
  if(bundle.schema_version!=='source-tiers-v4')return;
  root.dataset.bundleHash=bundle.bundle_hash;
  const add=(parent,tag,text)=>{const n=document.createElement(tag);n.textContent=text;parent.append(n);return n;};
  for(const [tier,label] of [['CORE','핵심 원문'],['SUPPLEMENTAL','보완 원문']]){
    const cards=bundle.sources.filter(c=>c.tier===tier);if(!cards.length)continue;
    add(root,'h3',label);
    for(const c of cards){
      const node=add(root,'article','');node.dataset.selectionId=c.selection_id;
      add(node,'h4',c.document_name+' · '+c.coordinate_label);
      add(node,'p','판본: '+c.generation_id+' · '+c.source_artifact_hash.slice(0,12));
      const area=tier==='SUPPLEMENTAL'?add(node,'details',''):node;
      if(tier==='SUPPLEMENTAL')add(area,'summary','발췌 보기');
      add(area,'blockquote',c.excerpt);add(node,'p','선택 이유: '+c.relevance_reason);
      add(node,'p','해석: '+(c.interpretation_status==='REVIEWED'?'독립 검토됨':'미확정')+' · 선택 범위 '+c.coverage);
      if(c.open_url && c.open_url.startsWith('/v1/rag/source?')){const a=add(node,'a','원문 열기');a.href=c.open_url;a.target='_blank';a.rel='noopener';}
    }
  }
  if(bundle.status==='NO_SELECTION')add(root,'p','관련 원문 채택 없음 · NO_SELECTION');
  const more=add(root,'details','');add(more,'summary','추가 확인 후보 '+bundle.candidate_counts.unselected+'건');
  add(more,'p','아직 채택하지 않은 후보입니다. 인용 출처에 포함하지 않습니다.');
  if(bundle.candidates_url){const a=add(more,'a','후보 목록 / 이어보기');a.href=bundle.candidates_url;a.target='_blank';a.rel='noopener';}
}
'''
