(function () {
  "use strict";

  const $ = (q, root=document) => root.querySelector(q);
  const $$ = (q, root=document) => [...root.querySelectorAll(q)];
  const fmt = (n) => new Intl.NumberFormat("ko-KR").format(Number(n || 0));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const short = (s, n=34) => String(s || "").length > n ? String(s).slice(0, n) + "…" : String(s || "");
  const endpoint = (v) => typeof v === "object" ? v.id : v;
  const state = { nodes:new Map(), edges:new Map(), viewNodes:new Map(), viewEdges:new Map(), selected:null, center:null, simulation:null, initial:null, layout:"connect", traceTimer:null, traceStage:-1, traceRestore:null };

  const layers = {
    Concept:"meaning", Lexeme:"meaning",
    Assertion:"rule", Frame:"rule", FrameClass:"rule",
    Document:"source", Section:"source", TextBlock:"source", PendingReference:"source",
    Mention:"evidence", Quantity:"evidence", Tag:"evidence",
  };
  const normative = new Set(["ACTOR","PREDICATE","OBJECT","TARGET","METHOD","MODALITY","CONDITION","EFFECT","SUBJECT","FUNCTION","EXCEPTION"]);
  const semantic = new Set(["NORMALIZES_TO","DENOTES","IS_A","EQUIVALENT_TO","REALIZES","SATISFIES","OPPOSITE_OF","ALIAS_OF"]);
  const sourceEdges = new Set(["SUPPORTED_BY","REFERENCES","DEFINES","DEEMS","EXCLUDES","INCORPORATES","IN_ARTICLE","HAS_SECTION","PARENT_OF"]);

  const svg = d3.select("#kgGraph"), zoomLayer = svg.select(".kg-zoom-layer");
  const zoom = d3.zoom().scaleExtent([.15, 4]).on("zoom", (ev) => zoomLayer.attr("transform", ev.transform));
  svg.call(zoom).on("dblclick.zoom", null);

  function setLoading(on) { $("#kgLoading").classList.toggle("hidden", !on); }
  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status} ${r.statusText}`);
    return r.json();
  }
  function notify(message, bad=false) {
    const el = $("#graphStatus"); el.textContent = message; el.classList.toggle("bad", bad);
  }
  function nodeLayer(n) { return layers[n.kind] || "evidence"; }
  function edgeClass(e) {
    if (normative.has(e.kind)) return "normative";
    if (semantic.has(e.kind)) return "semantic";
    if (sourceEdges.has(e.kind)) return "source";
    return "evidence";
  }
  function symbolPath(n) {
    const size = n.kind === "Bundle" ? 420 : n.kind === "Concept" ? 260 : n.kind === "Assertion" ? 220 : n.kind === "Document" ? 210 : 120;
    if (n.kind === "Bundle") return d3.symbol().type(d3.symbolSquare).size(size)();
    if (n.kind === "Assertion") return d3.symbol().type(d3.symbolDiamond).size(size)();
    if (["Document","Section","TextBlock","PendingReference"].includes(n.kind)) return d3.symbol().type(d3.symbolSquare).size(size)();
    if (["Frame","FrameClass"].includes(n.kind)) return d3.symbol().type(d3.symbolHexagon || d3.symbolDiamond).size(size)();
    return d3.symbol().type(d3.symbolCircle).size(size)();
  }
  function flowStage(n) {
    if (n?.virtual) return n.stage;
    if (["Lexeme","Mention"].includes(n.kind)) return 0;
    if (n.kind === "Concept") return 1;
    if (["Assertion","Frame","FrameClass"].includes(n.kind)) return 2;
    if (["Document","Section"].includes(n.kind)) return 3;
    return 4;
  }
  const roleUsage={
    ACTOR:"행위 주체로 사용",PREDICATE:"행위·요건으로 사용",OBJECT:"적용 대상으로 사용",
    TARGET:"행위 상대방으로 사용",METHOD:"수단·방법으로 사용",MODALITY:"의무·금지·허용 판단에 사용",
    CONDITION:"적용 조건으로 사용",EFFECT:"법적 효과로 사용",SUBJECT:"규율 대상으로 사용",
    FUNCTION:"규범 기능으로 사용",EXCEPTION:"예외 판단에 사용",IS_A:"상위·하위 개념 연결에 사용",
  };
  function relationshipGraph(nodes,edges) {
    const byId=new Map(nodes.map((n)=>[n.id,n])),center=byId.get(state.center)||byId.get(state.selected);
    if(!center)return {nodes:[],edges:[]};
    const outNodes=[center],outEdges=[],bundles=new Map();
    const addBundle=(key,label,stage,relation,usage,members)=>{
      const unique=[...new Map(members.map((n)=>[n.id,n])).values()];
      if(!unique.length)return null;
      const node={id:`bundle:${key}`,kind:"Bundle",label,stage,virtual:true,degree:unique.length,
        props:{relation,count:unique.length,usage,examples:unique.slice(0,4).map((n)=>short(n.label,72)),member_ids:unique.map((n)=>n.id)}};
      bundles.set(key,node);outNodes.push(node);return node;
    };
    const addEdge=(key,src,dst,kind,count,usage)=>outEdges.push({id:`bundle-edge:${key}`,kind,src,dst,source:src,target:dst,virtual:true,weight:count,props:{count,usage}});
    const direct=edges.filter((e)=>e.src===center.id||e.dst===center.id),surfaces=[];
    for(const e of direct){const other=byId.get(e.src===center.id?e.dst:e.src);if(other&&flowStage(other)===0)surfaces.push(other);}
    const surface=addBundle("surface","표면형 묶음",0,"NORMALIZES_TO","검색어를 정규 Concept로 연결",surfaces);
    if(surface)addEdge("surface",surface.id,center.id,"NORMALIZES_TO",surfaces.length,"표면형 정규화");
    const roleGroups=new Map();
    for(const e of direct){
      const other=byId.get(e.src===center.id?e.dst:e.src);
      if(!other||other.kind!=="Assertion")continue;
      if(!roleGroups.has(e.kind))roleGroups.set(e.kind,[]);roleGroups.get(e.kind).push(other);
    }
    const assertionIds=new Set();
    for(const [role,members] of [...roleGroups].sort((a,b)=>b[1].length-a[1].length)){
      members.forEach((n)=>assertionIds.add(n.id));
      const usage=roleUsage[role]||`${role} 관계로 사용`;
      const bundle=addBundle(`role:${role}`,usage,2,role,usage,members);
      if(bundle)addEdge(`role:${role}`,center.id,bundle.id,role,members.length,usage);
    }
    const sources=[];
    for(const e of edges){
      if(e.kind!=="SUPPORTED_BY")continue;
      const assertion=assertionIds.has(e.src)?e.src:assertionIds.has(e.dst)?e.dst:null;
      if(!assertion)continue;const other=byId.get(e.src===assertion?e.dst:e.src);if(other)sources.push(other);
    }
    const source=addBundle("sources","근거 조문 묶음",3,"SUPPORTED_BY","답변의 법적 근거로 사용",sources);
    if(source){for(const [role,members] of roleGroups){const bundle=bundles.get(`role:${role}`);if(bundle)addEdge(`support:${role}`,bundle.id,source.id,"SUPPORTED_BY",Math.min(members.length,sources.length),"규범을 조문 원문으로 검증");}}
    const sourceIds=new Set(sources.map((n)=>n.id)),evidence=[];
    for(const e of edges){if(!sourceIds.has(e.src)&&!sourceIds.has(e.dst))continue;const other=byId.get(sourceIds.has(e.src)?e.dst:e.src);if(other&&flowStage(other)===4)evidence.push(other);}
    const proof=addBundle("evidence","원문 근거 묶음",4,"EVIDENCE","근거 span 검증에 사용",evidence);
    if(source&&proof)addEdge("evidence",source.id,proof.id,"EVIDENCE",evidence.length,"원문 grounding");
    return {nodes:outNodes,edges:outEdges};
  }
  function assignFlowTargets(nodes) {
    const groups=d3.group(nodes,flowStage);
    for (const [stage,items] of groups) {
      items.sort((a,b)=>String(a.label).localeCompare(String(b.label),"ko"));
      const step=items.length < 2 ? 0 : Math.min(34,760/(items.length-1));
      items.forEach((n,i)=>{ n.flowX=(stage-2)*230; n.flowY=(i-(items.length-1)/2)*step; });
    }
  }
  function assignConnectTargets(nodes){
    const groups=d3.group(nodes,flowStage);
    for(let stage=0;stage<5;stage++){
      const items=groups.get(stage)||[];items.sort((a,b)=>String(a.label).localeCompare(String(b.label),"ko"));
      const step=items.length<2?0:Math.min(86,320/(items.length-1));
      items.forEach((n,i)=>{n.flowX=(stage-2)*150;n.flowY=(i-(items.length-1)/2)*step;});
    }
  }
  const depthX=[-520,-235,10,275,520],depthScale=[.52,.78,1,.78,.52];
  const stageNames=["SURFACE","CONCEPT","NORM","SOURCE","EVIDENCE"];
  const stageLabels=["표면 용어","정규 Concept","규범 명제","법적 출처","원문 근거"];
  function assignDepthTargets(nodes) {
    const groups=d3.group(nodes,flowStage);
    for (let stage=0;stage<5;stage++) {
      const items=groups.get(stage)||[];
      items.sort((a,b)=>String(a.label).localeCompare(String(b.label),"ko"));
      const span=stage===2?780:stage===1?720:560;
      const step=items.length<2?0:Math.min(stage===2?34:30,span/(items.length-1));
      items.forEach((n,i)=>{
        n.flowX=depthX[stage]; n.flowY=(i-(items.length-1)/2)*step;
        n.depthScale=depthScale[stage]; n.depthStage=stage;
      });
    }
  }
  function renderDepthGuides(nodes) {
    const host=svg.select(".kg-depth-guides");
    if(state.layout==="connect"){
      host.selectAll("*").remove();
      host.selectAll("line").data(d3.range(5)).join("line").attr("class","kg-connect-guide")
        .attr("x1",(d)=>(d-2)*150).attr("x2",(d)=>(d-2)*150).attr("y1",-220).attr("y2",220);
      return;
    }
    if (state.layout!=="depth") { host.selectAll("*").remove(); return; }
    const counts=d3.rollup(nodes,(items)=>items.length,flowStage);
    const stages=d3.range(5).map((stage)=>({stage,x:depthX[stage],scale:depthScale[stage],count:counts.get(stage)||0}));
    const g=host.selectAll("g").data(stages,(d)=>d.stage).join("g").attr("class",(d)=>`kg-depth-plane stage-${d.stage}`);
    g.selectAll("rect").data((d)=>[d]).join("rect")
      .attr("x",(d)=>d.x-13).attr("y",(d)=>-430*d.scale)
      .attr("width",26).attr("height",(d)=>860*d.scale);
    g.selectAll("line.axis").data((d)=>[d]).join("line").attr("class","axis")
      .attr("x1",(d)=>d.x).attr("x2",(d)=>d.x)
      .attr("y1",(d)=>-455*d.scale).attr("y2",(d)=>455*d.scale);
    g.selectAll("line.cap-top").data((d)=>[d]).join("line").attr("class","cap cap-top")
      .attr("x1",(d)=>d.x-24*d.scale).attr("x2",(d)=>d.x+24*d.scale)
      .attr("y1",(d)=>-430*d.scale).attr("y2",(d)=>-430*d.scale);
    g.selectAll("line.cap-bottom").data((d)=>[d]).join("line").attr("class","cap cap-bottom")
      .attr("x1",(d)=>d.x-24*d.scale).attr("x2",(d)=>d.x+24*d.scale)
      .attr("y1",(d)=>430*d.scale).attr("y2",(d)=>430*d.scale);
    g.selectAll("text").data((d)=>[d]).join("text")
      .attr("x",(d)=>d.x).attr("y",(d)=>-445*d.scale).text((d)=>`0${d.stage+1} · ${stageNames[d.stage]} · ${d.count}`);
    host.selectAll("path.kg-depth-ray").data(stages.filter((d)=>d.stage!==2),(d)=>d.stage).join("path")
      .attr("class","kg-depth-ray").attr("d",(d)=>`M${d.x},${430*d.scale}L${depthX[2]},455 M${d.x},${-430*d.scale}L${depthX[2]},-455`);
  }
  function linkPath(d) {
    const sx=d.source.x||0,sy=d.source.y||0,tx=d.target.x||0,ty=d.target.y||0;
    if (state.layout === "map") return `M${sx},${sy}L${tx},${ty}`;
    if (state.layout === "depth") {
      const dx=tx-sx,bend=Math.max(38,Math.abs(dx)*.38);
      return dx>=0
        ? `M${sx},${sy}C${sx+bend},${sy} ${tx-bend},${ty} ${tx},${ty}`
        : `M${sx},${sy}C${sx+52},${sy-26} ${tx-52},${ty-26} ${tx},${ty}`;
    }
    const dx=tx-sx;
    if (Math.abs(dx) < 50) {
      const bend=38+Math.min(80,Math.abs(ty-sy)*.18);
      return `M${sx},${sy}C${sx+bend},${sy} ${tx+bend},${ty} ${tx},${ty}`;
    }
    const bend=Math.max(55,Math.abs(dx)*.46);
    return dx>0
      ? `M${sx},${sy}C${sx+bend},${sy} ${tx-bend},${ty} ${tx},${ty}`
      : `M${sx},${sy}C${sx+55},${sy-34} ${tx-55},${ty-34} ${tx},${ty}`;
  }
  function visibleGraph() {
    const enabled = new Set($$(".kg-layer-box input:checked").map((x) => x.value));
    const nodes = [...state.nodes.values()].filter((n) => enabled.has(nodeLayer(n)));
    const ids = new Set(nodes.map((n) => n.id));
    const edges = [...state.edges.values()].filter((e) => ids.has(endpoint(e.src)) && ids.has(endpoint(e.dst)));
    return {nodes, edges};
  }
  function mergeGraph(data, replace=false) {
    if (replace) { state.nodes.clear(); state.edges.clear(); }
    data.nodes.forEach((n) => {
      const old = state.nodes.get(n.id);
      state.nodes.set(n.id, old ? {...n, x:old.x, y:old.y, vx:old.vx, vy:old.vy} : n);
    });
    data.edges.forEach((e) => state.edges.set(e.id, {...e, source:e.src, target:e.dst}));
    state.center = data.center || state.center;
    render();
  }
  function render() {
    const base=visibleGraph(),view=state.layout==="connect"?relationshipGraph(base.nodes,base.edges):base;
    const {nodes,edges}=view;
    state.viewNodes=new Map(nodes.map((n)=>[n.id,n]));state.viewEdges=new Map(edges.map((e)=>[e.id,e]));
    if(state.layout==="connect")assignConnectTargets(nodes);else if(state.layout==="depth")assignDepthTargets(nodes);else assignFlowTargets(nodes);
    renderDepthGuides(nodes);
    $("#kgEmpty").classList.toggle("hidden", nodes.length > 0);
    $("#viewSize").textContent = `${fmt(nodes.length)} / ${fmt(edges.length)}`;
    const link = svg.select(".kg-edges").selectAll("path").data(edges, (d) => d.id).join("path")
      .attr("class", (d) => `kg-edge ${edgeClass(d)}`);
    const node = svg.select(".kg-nodes").selectAll("g").data(nodes, (d) => d.id).join(
      (enter) => {
        const g = enter.append("g").attr("class", (d) => `kg-node ${d.kind}`).call(d3.drag()
          .on("start", dragStart).on("drag", dragged).on("end", dragEnd));
        g.append("path").attr("class", "shape").attr("d", symbolPath);
        g.append("text").attr("class", "label").attr("x", 13).attr("y", 1).text((d) => short(d.label, 22));
        g.append("text").attr("class", "kind").attr("x", 13).attr("y", 11).text((d) => d.virtual?`${d.props.count} CONNECTIONS`:d.kind.toUpperCase());
        return g;
      },
      (update) => update.attr("class", (d) => `kg-node ${d.kind}${d.id === state.selected ? " selected" : ""}`),
      (exit) => exit.remove()
    );
    node.attr("class",(d)=>`kg-node ${d.kind}${d.id===state.selected?" selected":""}`);
    node.select(".shape").attr("d",symbolPath);
    node.select(".label").text((d)=>short(d.label,22));
    node.select(".kind").text((d)=>d.virtual?`${d.props.count} CONNECTIONS`:d.kind.toUpperCase());
    node.on("click", (ev, d) => { ev.stopPropagation(); selectGraphNode(d); })
      .on("dblclick", (ev, d) => { ev.stopPropagation(); if(!d.virtual)expandNode(d.id); });
    svg.on("click", () => clearSelection());
    if (state.simulation) state.simulation.stop();
    const simulation=d3.forceSimulation(nodes)
      .force("link", d3.forceLink(edges).id((d) => d.id).distance((d) => normative.has(d.kind) ? 62 : 82).strength(.28))
      .force("collision", d3.forceCollide().radius((d) => d.kind === "Concept" ? 31 : 23))
      .on("tick", () => {
        link.attr("d",linkPath);
        node.attr("transform", (d) => `translate(${d.x},${d.y}) scale(${state.layout==="depth"?(d.depthScale||1):1})`);
        updateEdgeLabels();
      });
    if (state.layout === "connect") {
      simulation.force("charge",d3.forceManyBody().strength(-110))
        .force("x",d3.forceX((d)=>d.flowX).strength(.92))
        .force("y",d3.forceY((d)=>d.flowY).strength(.52))
        .force("collision",d3.forceCollide().radius((d)=>d.virtual?48:34));
    } else if (state.layout === "depth") {
      simulation.force("charge",d3.forceManyBody().strength(-42))
        .force("x",d3.forceX((d)=>d.flowX).strength(.9))
        .force("y",d3.forceY((d)=>d.flowY).strength(.35));
    } else if (state.layout === "flow") {
      simulation.force("charge",d3.forceManyBody().strength(-75))
        .force("x",d3.forceX((d)=>d.flowX).strength(.78))
        .force("y",d3.forceY((d)=>d.flowY).strength(.24));
    } else {
      simulation.force("charge",d3.forceManyBody().strength((d)=>d.kind==="Concept"?-300:-190))
        .force("x",d3.forceX(0).strength(.035)).force("y",d3.forceY(0).strength(.05));
    }
    state.simulation=simulation;
    applySelection();
  }
  function dragStart(ev, d) { if (!ev.active) state.simulation.alphaTarget(.18).restart(); d.fx=d.x; d.fy=d.y; }
  function dragged(ev, d) { d.fx=ev.x; d.fy=ev.y; }
  function dragEnd(ev, d) { if (!ev.active) state.simulation.alphaTarget(0); d.fx=null; d.fy=null; }

  function clearSelection() { if(state.traceTimer)stopTrace(false); state.selected=null; applySelection(); inspect(null); }
  function selectGraphNode(node){if(!node)return;if(state.traceTimer)stopTrace(false);state.selected=node.id;applySelection();inspect(node);}
  function selectNode(id) { selectGraphNode(state.viewNodes.get(id)||state.nodes.get(id)); }
  function adjacent(id) {
    return [...state.viewEdges.values()].filter((e) => endpoint(e.src) === id || endpoint(e.dst) === id);
  }
  function applySelection() {
    const id=state.selected, connected=new Set(id ? [id] : []);
    if (id) adjacent(id).forEach((e) => { connected.add(endpoint(e.src)); connected.add(endpoint(e.dst)); });
    const overview=state.layout==="connect"&&id===state.center;
    svg.selectAll(".kg-node").classed("selected", (d) => d.id===id).classed("dim", (d) => !!id&&!overview&&!connected.has(d.id));
    svg.selectAll(".kg-edge").classed("focus", (d) => !!id&&!overview&&(endpoint(d.src)===id || endpoint(d.dst)===id)).classed("muted", (d) => !!id&&!overview&&endpoint(d.src)!==id&&endpoint(d.dst)!==id);
    updateEdgeLabels();
  }
  function updateEdgeLabels() {
    const edges=state.layout==="connect"&&state.selected===state.center?[...state.viewEdges.values()]:state.selected?adjacent(state.selected).slice(0,18):[];
    svg.select(".kg-edge-labels").selectAll("text").data(edges, (d) => d.id).join("text")
      .attr("class","kg-edge-label").attr("x",(d)=>(d.source.x+d.target.x)/2).attr("y",(d)=>(d.source.y+d.target.y)/2-3).text((d)=>d.virtual?`${d.kind} · ${d.weight}`:d.kind);
  }
  function inspect(n) {
    const host=$("#kgInspector"), panel=$(`.kg-inspector`);
    if (!n) { panel.classList.remove("open"); host.innerHTML='<div class="kg-inspector-empty"><span class="crosshair"></span><b>노드를 선택하세요</b><p>Concept가 의미의 허브이고 Assertion이 법적 명제를, 출처 노드가 검증 가능한 근거를 담당합니다.</p></div>'; return; }
    panel.classList.add("open");
    if(state.layout==="connect"&&n.id===state.center){
      const groups=[...state.viewNodes.values()].filter((x)=>x.virtual).sort((a,b)=>a.stage-b.stage);
      host.innerHTML=`<div class="kg-node-head"><div class="kg-type-line"><span>CONNECTION OVERVIEW</span><span class="kg-grade">${groups.length}개 묶음</span></div><h3>${esc(n.label)} 연결 구조</h3><span class="kg-node-id">개별 값보다 단계별 사용 관계를 요약합니다</span></div>
        <section class="kg-inspector-section"><h4>단계별 활용</h4><div class="kg-usage-list">${groups.map((g)=>`<button class="kg-usage-card" data-node="${esc(g.id)}"><em>0${g.stage+1} · ${esc(stageNames[g.stage])}</em><b>${esc(g.label)}</b><span>${esc(g.props.usage)} · ${fmt(g.props.count)}건</span></button>`).join("")}</div></section>
        <section class="kg-inspector-section"><h4>읽는 방법</h4><p class="kg-usage-note">선을 따라가면 이 Concept가 규범에서 어떤 역할로 사용되고, 몇 개 조문이 그 판단을 뒷받침하는지 확인할 수 있습니다. 실제 값은 관계 묶음을 선택할 때만 표시합니다.</p></section>`;
      $$('[data-node]',host).forEach((b)=>b.addEventListener("click",()=>selectNode(b.dataset.node)));return;
    }
    const props=n.props || {}, grade=n.virtual?`${props.count}건`:props.knowledge_grade == null ? "미평가" : `G${props.knowledge_grade}`;
    const facts=Object.entries(props).filter(([k,v]) => k!=="member_ids"&&v != null && v !== "" && (!Array.isArray(v) || v.length)).slice(0,14);
    const links=adjacent(n.id).slice(0,30).map((e) => {
      const otherId=endpoint(e.src)===n.id?endpoint(e.dst):endpoint(e.src);
      const other=state.viewNodes.get(otherId)||state.nodes.get(otherId);
      return other ? `<button class="kg-connection" data-node="${esc(other.id)}"><em>${esc(e.kind)}</em><span>${esc(short(other.label,28))}</span></button>` : "";
    }).join("");
    host.innerHTML=`<div class="kg-node-head"><div class="kg-type-line"><span>${esc(n.virtual?"RELATION GROUP":n.kind.toUpperCase())}</span><span class="kg-grade">${esc(grade)}</span></div><h3>${esc(n.label)}</h3><span class="kg-node-id" title="${esc(n.id)}">${esc(n.id)}</span></div>
      <section class="kg-inspector-section"><h4>속성</h4><dl class="kg-facts">${facts.length ? facts.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(Array.isArray(v)?v.join(", "):typeof v==="object"?JSON.stringify(v):v)}</dd>`).join("") : '<dt>상태</dt><dd>추가 속성 없음</dd>'}</dl></section>
      <section class="kg-inspector-section"><h4>직접 연결 · ${adjacent(n.id).length}</h4><div class="kg-connections">${links || '<span class="kg-no-results">현재 뷰에 직접 연결이 없습니다</span>'}</div>${n.virtual?"":`<button class="kg-expand" data-expand="${esc(n.id)}">이 노드에서 연결 더 불러오기</button>`}</section>`;
    $$("[data-node]",host).forEach((b)=>b.addEventListener("click",()=>selectNode(b.dataset.node)));
    $("[data-expand]",host)?.addEventListener("click",()=>expandNode(n.id));
  }

  async function search(query, autoload=false) {
    const q=String(query||"").trim(); setLoading(true);
    try {
      const data=await getJSON(`/v1/knowledge/search?q=${encodeURIComponent(q)}&limit=24`);
      const host=$("#kgResults"); $("#resultCount").textContent=`${data.results.length}건`;
      host.innerHTML=data.results.length ? data.results.map((n)=>`<button class="kg-result" data-id="${esc(n.id)}" data-kind="${esc(n.kind)}"><i></i><span><b>${esc(n.label)}</b><small>${esc(n.kind)}</small></span><em>${fmt(n.degree)}</em></button>`).join("") : '<div class="kg-no-results">일치하는 컴파일 노드가 없습니다</div>';
      $$(".kg-result",host).forEach((b)=>b.addEventListener("click",()=>loadRoot(b.dataset.id)));
      if (autoload && data.results[0]) await loadRoot(data.results[0].id);
      notify(`검색 ${data.results.length}건 · 컴파일 그래프`);
      return data.results;
    } catch(e) { notify(`그래프 검색 실패 · ${e.message}`,true); return []; }
    finally { setLoading(false); }
  }
  async function loadRoot(id) {
    setLoading(true);
    try {
      const data=await getJSON(`/v1/knowledge/neighborhood?id=${encodeURIComponent(id)}&depth=2&limit=180`);
      state.initial=id; mergeGraph(data,true);
      if (matchMedia("(max-width:900px)").matches) clearSelection(); else selectNode(id);
      $$(".kg-result").forEach((b)=>b.classList.toggle("on",b.dataset.id===id));
      notify(`${fmt(data.nodes.length)}개 노드 · ${fmt(data.edges.length)}개 연결${data.truncated?" · 상한 적용":""}`);
      requestAnimationFrame(()=>setTimeout(fitGraph,350));
    } catch(e) { notify(`연결을 불러오지 못했습니다 · ${e.message}`,true); }
    finally { setLoading(false); }
  }
  async function expandNode(id) {
    setLoading(true);
    try { const data=await getJSON(`/v1/knowledge/neighborhood?id=${encodeURIComponent(id)}&depth=1&limit=100`); mergeGraph(data,false); selectNode(id); notify(`${fmt(state.nodes.size)}개 노드로 확장됨`); }
    catch(e) { notify(`확장 실패 · ${e.message}`,true); }
    finally { setLoading(false); }
  }
  function fitGraph() {
    const box=zoomLayer.node().getBBox(), root=$("#kgGraph"); if (!box.width || !box.height) return;
    const w=root.clientWidth,h=root.clientHeight,pad=70,scale=Math.max(.16,Math.min(1.7,(w-pad)/box.width,(h-pad)/box.height));
    const x=w/2-scale*(box.x+box.width/2),y=h/2-scale*(box.y+box.height/2);
    svg.transition().duration(450).call(zoom.transform,d3.zoomIdentity.translate(x,y).scale(scale));
  }
  function paintTrace(stage) {
    state.traceStage=stage;
    const count=[...state.viewNodes.values()].filter((n)=>flowStage(n)===stage).reduce((sum,n)=>sum+(n.virtual?n.props.count:1),0);
    $("#traceStep").textContent=`0${stage+1} / 05`;
    $("#traceName").textContent=stageLabels[stage];
    $("#traceCount").textContent=count?`${fmt(count)} nodes`:"미컴파일";
    $$("#kgTraceStatus li").forEach((li,i)=>{li.classList.toggle("on",i===stage);li.classList.toggle("passed",i<stage);});
    svg.selectAll(".kg-node").classed("trace-active",(d)=>flowStage(d)===stage)
      .classed("trace-passed",(d)=>flowStage(d)<stage).classed("trace-future",(d)=>flowStage(d)>stage);
    svg.selectAll(".kg-edge").classed("trace-active",(d)=>Math.max(flowStage(d.source),flowStage(d.target))===stage)
      .classed("trace-passed",(d)=>Math.max(flowStage(d.source),flowStage(d.target))<stage)
      .classed("trace-future",(d)=>Math.max(flowStage(d.source),flowStage(d.target))>stage);
    svg.selectAll(".kg-depth-plane").classed("trace-active",(d)=>d.stage===stage)
      .classed("trace-passed",(d)=>d.stage<stage);
  }
  function stopTrace(restore=true) {
    if(state.traceTimer)clearInterval(state.traceTimer);
    state.traceTimer=null;state.traceStage=-1;
    $("#kgCanvas").classList.remove("trace-running");$("#traceFlow").classList.remove("on");
    $("#kgTraceStatus").classList.add("hidden");
    svg.selectAll(".trace-active,.trace-passed,.trace-future").classed("trace-active",false).classed("trace-passed",false).classed("trace-future",false);
    const restoreId=state.traceRestore;state.traceRestore=null;
    const restoreNode=state.viewNodes.get(restoreId)||state.nodes.get(restoreId);
    if(restore&&restoreNode){state.selected=restoreId;applySelection();inspect(restoreNode);}
  }
  function startTrace() {
    if(state.traceTimer){stopTrace(true);return;}
    if(state.layout==="map")setLayout("connect");
    state.traceRestore=state.selected;state.selected=null;applySelection();inspect(null);
    $("#kgCanvas").classList.add("trace-running");$("#traceFlow").classList.add("on");
    $("#kgTraceStatus").classList.remove("hidden");
    let stage=0;paintTrace(stage);
    state.traceTimer=setInterval(()=>{stage=(stage+1)%5;paintTrace(stage);},1150);
  }
  function setLayout(mode) {
    if(state.traceTimer)stopTrace(true);
    state.layout=["connect","depth","flow","map"].includes(mode)?mode:"connect";
    if(state.layout==="connect"||String(state.selected||"").startsWith("bundle:"))state.selected=state.center;
    $("#kgCanvas").classList.toggle("connect-mode",state.layout==="connect");
    $("#kgCanvas").classList.toggle("depth-mode",state.layout==="depth");
    $("#kgCanvas").classList.toggle("flow-mode",state.layout==="flow");
    $("#layoutConnect").classList.toggle("on",state.layout==="connect");
    $("#layoutDepth").classList.toggle("on",state.layout==="depth");
    $("#layoutFlow").classList.toggle("on",state.layout==="flow");
    $("#layoutMap").classList.toggle("on",state.layout==="map");
    render();
    const selectedNode=state.viewNodes.get(state.selected)||state.nodes.get(state.selected);if(selectedNode)inspect(selectedNode);
    requestAnimationFrame(()=>setTimeout(fitGraph,700));
  }
  async function init() {
    $("#kgSearch").addEventListener("submit",(e)=>{e.preventDefault();search($("#kgQuery").value,true);});
    $$("#kgPresets button").forEach((b)=>b.addEventListener("click",()=>{ $$("#kgPresets button").forEach((x)=>x.classList.toggle("on",x===b)); $("#kgQuery").value=b.dataset.query; search(b.dataset.query,true); }));
    $$(".kg-layer-box input").forEach((x)=>x.addEventListener("change",render));
    $("#layoutConnect").addEventListener("click",()=>setLayout("connect"));
    $("#layoutDepth").addEventListener("click",()=>setLayout("depth"));
    $("#layoutFlow").addEventListener("click",()=>setLayout("flow"));
    $("#layoutMap").addEventListener("click",()=>setLayout("map"));
    $("#zoomIn").addEventListener("click",()=>svg.transition().call(zoom.scaleBy,1.35));
    $("#zoomOut").addEventListener("click",()=>svg.transition().call(zoom.scaleBy,.74));
    $("#fitGraph").addEventListener("click",fitGraph);
    $("#resetGraph").addEventListener("click",()=>state.initial&&loadRoot(state.initial));
    $("#traceFlow").addEventListener("click",startTrace);
    try {
      const s=await getJSON("/v1/knowledge/summary"); $("#totalNodes").textContent=fmt(s.total_nodes); $("#totalEdges").textContent=fmt(s.total_edges);
      notify(`${fmt(s.nodes.Concept)} Concepts · ${fmt(s.nodes.Assertion)} Assertions`);
      $("#kgQuery").value="자기주식"; $("#kgPresets button").classList.add("on"); await search("자기주식",true);
    } catch(e) { notify(`컴파일 그래프 연결 실패 · ${e.message}`,true); }
  }
  init();
})();
