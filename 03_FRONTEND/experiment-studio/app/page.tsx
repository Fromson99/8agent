'use client';

import { useMemo, useState } from 'react';
import { evaluatorRegistry, experimentRuns, goldenSuites, workspaceDatasets, workspaceSummary } from './workspace-data';

type View = 'graph' | 'runs' | 'compare' | 'datasets' | 'goldens' | 'evaluators' | 'traces' | 'ontology' | 'products' | 'releases';
type Tone = 'base' | 'good' | 'warn' | 'live';
type FlowNode = { id:string; eyebrow:string; title:string; note:string; score:string; delta:string; tone:Tone; x:string; y:string };

const flowNodes: FlowNode[] = [
  { id:'baseline', eyebrow:'BASELINE · ADR-0040', title:'Frame-only legal answer', note:'formal-v3 · 113 cases', score:'78.3%', delta:'locked', tone:'base', x:'7%', y:'27%' },
  { id:'query-guide', eyebrow:'GROUND · ADR-0041', title:'Definition knowledge card', note:'retrieval 변화만 허용', score:'84.1%', delta:'+5.8', tone:'good', x:'37%', y:'31%' },
  { id:'hard-negative', eyebrow:'CHALLENGE · ADR-0041', title:'Hard distractor set', note:'16 failure cases', score:'71.9%', delta:'−6.4', tone:'warn', x:'51%', y:'61%' },
  { id:'candidate', eyebrow:'CANDIDATE · ADR-0042', title:'Gold-only executor', note:'paired A/B · repeat 3', score:'87.0%', delta:'+8.7', tone:'live', x:'auto', y:'42%' },
];

const navGroups: { label:string; items:{ id:View; label:string; icon:string; count?:string }[] }[] = [
  { label:'WORKSPACE', items:[{id:'graph',label:'Experiment Graph',icon:'⌘'},{id:'runs',label:'Runs',icon:'◫',count:'12'},{id:'compare',label:'Compare',icon:'◈'}] },
  { label:'EVIDENCE', items:[{id:'datasets',label:'Datasets',icon:'▤',count:'5'},{id:'goldens',label:'Goldens',icon:'◇',count:'4'},{id:'evaluators',label:'Evaluators',icon:'◎',count:'5'},{id:'traces',label:'Traces',icon:'⌁'}] },
  { label:'SYSTEM', items:[{id:'ontology',label:'Ontology',icon:'⬡'},{id:'products',label:'Data products',icon:'□'},{id:'releases',label:'Releases',icon:'⇧'}] },
];

const titles: Record<View,{kicker:string;title:string;copy:string}> = {
  graph:{kicker:'EXPERIMENT LINEAGE',title:'무엇을 시도했고, 왜 다음 실험으로 갔는가',copy:'가설, 데이터셋, 변경점과 판정을 하나의 증거 흐름으로 고정합니다.'},
  runs:{kicker:'RUN REGISTRY',title:'모든 실행을 같은 판에서 비교합니다',copy:'parameter, artifact, dataset과 최초 실패 layer를 실행 단위로 기록합니다.'},
  compare:{kicker:'PAIRED COMPARISON',title:'평균보다 어떤 case가 바뀌었는지 봅니다',copy:'기준선과 후보를 같은 입력에 맞추고 개선·회귀·불변 케이스를 분리합니다.'},
  datasets:{kicker:'WORKSPACE DATA',title:'우리 데이터를 실험 가능한 계약으로 바꿉니다',copy:'원본 경로는 유지하고 version, schema, split과 adapter만 Studio에 등록합니다.'},
  goldens:{kicker:'GOLDEN REGISTRY',title:'정답집이 아니라 제품 사양을 관리합니다',copy:'Dev, locked, challenge, rolling shadow를 분리하고 변경 이력을 보존합니다.'},
  evaluators:{kicker:'EVALUATOR REGISTRY',title:'각 실패를 측정 가능한 함수로 고정합니다',copy:'결정론 검사, LLM judge, policy와 composite scorer를 같은 계약으로 다룹니다.'},
  traces:{kicker:'CASE TRACE',title:'최초로 실패한 계층을 찾습니다',copy:'Prepare에서 Solve까지 input, output, latency와 artifact lineage를 한 trace로 엮습니다.'},
  ontology:{kicker:'ONTOLOGY KERNEL',title:'데이터와 실험을 기업 업무 타입에 연결합니다',copy:'Object, relation, metric, policy, function, action을 versioned bundle로 관리합니다.'},
  products:{kicker:'DATA PRODUCTS',title:'원천에서 Golden까지 재생 가능한 경로를 봅니다',copy:'파서와 index를 숨기지 않고 품질·시점·ACL·lineage를 함께 노출합니다.'},
  releases:{kicker:'RELEASE CONTROL',title:'실험 결과를 승인 가능한 bundle로 승격합니다',copy:'Golden gate, 보안, 비용, 지연과 rollback 증거가 갖춰져야 production으로 이동합니다.'},
};

export default function Home() {
  const [view,setView]=useState<View>('graph');
  const [selectedNode,setSelectedNode]=useState('candidate');
  const [selectedDataset,setSelectedDataset]=useState('golden-formal');
  const [modal,setModal]=useState(false);
  const [step,setStep]=useState(1);
  const [draftName,setDraftName]=useState('retrieval-selectivity-v2');
  const [toast,setToast]=useState('');
  const selected=flowNodes.find(n=>n.id===selectedNode)??flowNodes[0];
  const dataset=workspaceDatasets.find(d=>d.id===selectedDataset)??workspaceDatasets[0];
  const title=titles[view];

  const showToast=(message:string)=>{setToast(message);window.setTimeout(()=>setToast(''),2400)};
  const openExperiment=()=>{setStep(1);setModal(true)};

  return <main className="studio-shell">
    <aside className="nav-rail" aria-label="주요 메뉴">
      <div className="brand-mark">AX</div>
      <nav>
        {(['graph','datasets','goldens','ontology','releases'] as View[]).map((id,i)=><button key={id} className={`rail-button ${view===id?'active':''}`} aria-label={titles[id].kicker} onClick={()=>setView(id)}>{['⌘','D','G','O','R'][i]}</button>)}
      </nav>
      <div className="rail-spacer"/><button className="rail-button user" aria-label="사용자 계정">JF</button>
    </aside>

    <section className="workspace">
      <header className="topbar">
        <div className="breadcrumb"><span>8-AGENT</span><b>/</b><strong>Legal RAG Lab</strong><b>/</b><span>{title.kicker}</span></div>
        <div className="topbar-actions"><span className="environment"><i/> ON-PREM · DEV</span><button className="quiet-button" onClick={()=>showToast('실험 표준과 ADR 계약을 확인했습니다.')}>명세 보기</button><button className="primary-button" onClick={openExperiment}>＋ 새 실험</button></div>
      </header>

      <div className="workspace-grid">
        <aside className="project-sidebar">
          {navGroups.map(group=><div className="side-section" key={group.label}><p className="side-label">{group.label}</p>{group.items.map(item=><button key={item.id} className={`side-link ${view===item.id?'active':''}`} onClick={()=>setView(item.id)}><span>{item.icon}</span>{item.label}{item.count&&<em>{item.count}</em>}</button>)}</div>)}
          <div className="data-health"><div><span>Workspace data</span><strong>Connected</strong></div><div className="health-track"><i/></div><small>{workspaceSummary.activeFiles.toLocaleString()} active artifacts · snapshot {workspaceSummary.capturedAt}</small></div>
        </aside>

        <section className="main-stage">
          <div className="stage-heading"><div><p className="kicker">{title.kicker}</p><h1>{title.title}</h1><p className="stage-copy">{title.copy}</p></div>{view==='graph'&&<div className="stage-tools"><button>−</button><span>82%</span><button>＋</button><button>맞춤</button></div>}</div>
          {view==='graph'&&<GraphView selectedId={selectedNode} onSelect={setSelectedNode}/>} 
          {view==='runs'&&<RunsView onCompare={()=>setView('compare')}/>} 
          {view==='compare'&&<CompareView/>}
          {view==='datasets'&&<DatasetsView selectedId={selectedDataset} onSelect={setSelectedDataset}/>} 
          {view==='goldens'&&<GoldensView/>}
          {view==='evaluators'&&<EvaluatorsView/>}
          {view==='traces'&&<TracesView/>}
          {view==='ontology'&&<OntologyView/>}
          {view==='products'&&<ProductsView/>}
          {view==='releases'&&<ReleasesView onPromote={()=>showToast('승격 요청을 Release Owner 검토함에 보냈습니다.')}/>} 
        </section>

        <aside className="inspector">
          {view==='datasets'?<DatasetInspector dataset={dataset}/>:<RunInspector selected={selected} onCompare={()=>setView('compare')}/>} 
        </aside>
      </div>
    </section>

    {modal&&<ExperimentModal step={step} setStep={setStep} name={draftName} setName={setDraftName} onClose={()=>setModal(false)} onCreate={()=>{setModal(false);setView('graph');showToast(`${draftName} 초안을 만들었습니다. 실행 전 ADR 동결이 필요합니다.`)}}/>}
    {toast&&<div className="toast" role="status"><span>✓</span>{toast}</div>}
  </main>;
}

function GraphView({selectedId,onSelect}:{selectedId:string;onSelect:(id:string)=>void}) {
  return <><div className="flow-canvas" aria-label="실험 계보 그래프">
    <div className="lane-label lane-prepare"><span/> PREPARE</div><div className="lane-label lane-ground"><span/> GROUND</div><div className="lane-label lane-solve"><span/> SOLVE</div>
    <div className="flow-date">AUG 19</div><div className="flow-date mid">AUG 23</div><div className="flow-date end">AUG 26</div>
    <div className="flow-line main-line"/><div className="flow-line branch-line"/><div className="flow-line merge-line"/>
    {flowNodes.map(node=><button key={node.id} className={`flow-node ${node.id} ${selectedId===node.id?'selected':''}`} onClick={()=>onSelect(node.id)}><span className={`node-dot ${node.tone==='live'?'pulse':''}`}/><span className="node-eyebrow">{node.eyebrow}</span><strong>{node.title}</strong><small>{node.note}</small><span className="node-metric"><b>{node.score}</b><em className={node.delta.startsWith('+')?'positive':node.delta.startsWith('−')?'negative':''}>{node.delta}</em></span></button>)}
    <div className="flow-annotation">hard negatives에서 회귀 발견</div><div className="flow-annotation promote">release gate 대기</div><div className="demo-flag">DEMO METRICS</div>
  </div><footer className="stage-footer"><div><span className="legend-dot baseline-dot"/> 기준선</div><div><span className="legend-dot candidate-dot"/> 후보</div><div><span className="legend-dot failed-dot"/> 회귀</div><p>노드를 선택하면 해당 실행의 증거가 열립니다.</p></footer></>;
}

function RunsView({onCompare}:{onCompare:()=>void}) { const [query,setQuery]=useState(''); const rows=experimentRuns.filter(r=>(r.name+r.adr+r.dataset).toLowerCase().includes(query.toLowerCase())); return <div className="content-panel"><div className="table-toolbar"><label><span>⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="run, ADR, dataset 검색"/></label><button onClick={onCompare}>선택 비교</button></div><div className="table-wrap"><table className="data-table"><thead><tr><th>Run</th><th>Layer</th><th>Dataset</th><th>Status</th><th>Score</th><th>Δ baseline</th><th>Latency</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><strong>{r.name}</strong><small>{r.adr} · changed: {r.changed}</small></td><td><span className={`layer-tag ${r.layer.toLowerCase()}`}>{r.layer}</span></td><td><code>{r.dataset}</code></td><td><span className={`status-text ${r.status.toLowerCase().replace(' ','-')}`}>{r.status}</span></td><td className="metric-cell">{r.score.toFixed(1)}%</td><td className={r.delta<0?'metric-down':r.delta>0?'metric-up':''}>{r.delta>0?'+':''}{r.delta.toFixed(1)}</td><td>{r.latency}</td></tr>)}</tbody></table></div></div> }

function CompareView(){ const cases=[{id:'18-0124',type:'개선',before:'관련 조문 누락',after:'2/2 근거 회수',delta:'+1'},{id:'21-0131',type:'개선',before:'시행령 과잉 회수',after:'지배조문 고정',delta:'+1'},{id:'25-0554',type:'회귀',before:'부분 근거',after:'정의문 과우선',delta:'−1'},{id:'06-0131',type:'불변',before:'정답',after:'정답',delta:'0'}]; return <div className="compare-layout"><section className="compare-summary"><div className="compare-head"><div><span>BASELINE</span><strong>ADR-0040 / frame-only</strong></div><b>vs</b><div><span>CANDIDATE</span><strong>ADR-0042 / gold-only</strong></div></div><div className="metric-grid"><Metric label="Direction" base="78.3%" next="87.0%" delta="+8.7"/><Metric label="Basis recall" base="84.8%" next="91.3%" delta="+6.5"/><Metric label="Latency p95" base="4.6s" next="4.8s" delta="+0.2s" warn/><Metric label="High-risk fail" base="5" next="3" delta="−2"/></div></section><section className="case-diff"><div className="section-bar"><h2>Case-level diff</h2><div><button className="filter-active">전체 113</button><button>개선 17</button><button>회귀 3</button></div></div>{cases.map(c=><div className="case-row" key={c.id}><code>{c.id}</code><span className={`case-type ${c.type}`}>{c.type}</span><p>{c.before}<b>→</b>{c.after}</p><strong>{c.delta}</strong></div>)}</section></div> }
function Metric({label,base,next,delta,warn}:{label:string;base:string;next:string;delta:string;warn?:boolean}){return <div className="compare-metric"><span>{label}</span><div><small>{base}</small><i>→</i><strong>{next}</strong></div><em className={warn?'warn':''}>{delta}</em></div>}

function DatasetsView({selectedId,onSelect}:{selectedId:string;onSelect:(id:string)=>void}){ const [filter,setFilter]=useState('all'); const list=workspaceDatasets.filter(d=>filter==='all'||d.kind===filter); return <div className="dataset-layout"><div className="snapshot-strip"><div><span>ACTIVE FILES</span><strong>{workspaceSummary.activeFiles.toLocaleString()}</strong></div><div><span>CORPUS</span><strong>{workspaceSummary.corpusFiles.toLocaleString()}</strong></div><div><span>WIKI</span><strong>{workspaceSummary.wikiFiles.toLocaleString()}</strong></div><div><span>STRUCTURE</span><strong>{workspaceSummary.structureFiles.toLocaleString()}</strong></div></div><div className="dataset-filters">{['all','golden','corpus','trace','ontology'].map(id=><button key={id} className={filter===id?'active':''} onClick={()=>setFilter(id)}>{id}</button>)}</div><div className="dataset-list">{list.map(d=><button key={d.id} className={`dataset-row ${selectedId===d.id?'selected':''}`} onClick={()=>onSelect(d.id)}><span className={`dataset-icon ${d.kind}`}>{d.kind.slice(0,1).toUpperCase()}</span><span><strong>{d.name}</strong><small>{d.sourcePath}</small></span><code>{d.records.toLocaleString()}</code><span className={`dataset-status ${d.status}`}>{d.status}</span></button>)}</div></div> }

function GoldensView(){return <div className="card-grid">{goldenSuites.map((g,i)=><article className="registry-card" key={g.name}><header><span className={`suite-kind kind-${g.split}`}>{g.split}</span><button>•••</button></header><h2>{g.name}</h2><p>{g.coverage}</p><div className="big-number">{g.cases}<small> cases</small></div><dl><div><dt>Owner</dt><dd>{g.owner}</dd></div><div><dt>Updated</dt><dd>{g.updated}</dd></div><div><dt>Version</dt><dd>v{i+3} · immutable</dd></div></dl></article>)}</div>}
function EvaluatorsView(){return <div className="content-panel"><div className="registry-intro"><div><span>5 ACTIVE</span><strong>모든 scorer는 input mapping과 version을 고정합니다.</strong></div><button>＋ evaluator 등록</button></div><div className="evaluator-list">{evaluatorRegistry.map(e=><div className="evaluator-row" key={e.name}><span className={`eval-type ${e.type.toLowerCase().replace(' ','-')}`}>{e.type.slice(0,1)}</span><div><strong>{e.name}</strong><small>{e.input}</small></div><code>{e.target}</code><span>{e.type}</span><b>{e.state}</b></div>)}</div></div>}
function TracesView(){const spans=[['Intent compile','142ms','pass'],['Ontology bind','88ms','pass'],['Query translate','612ms','pass'],['Hybrid retrieval','1.42s','warn'],['Context build','203ms','pass'],['Legal review','2.11s','pass'],['Evaluator bundle','224ms','fail']];return <div className="trace-layout"><div className="trace-meta"><code>trace_18-0124_run-042-a</code><span>case 18-0124</span><span>total 4.79s</span><span className="trace-fail">first failure: evaluator</span></div><div className="waterfall">{spans.map((s,i)=><div className="span-row" key={s[0]}><span>{i+1}</span><strong>{s[0]}</strong><div><i className={s[2]} style={{width:`${22+i*8}%`,marginLeft:`${i*6}%`}}/></div><code>{s[1]}</code></div>)}</div><div className="trace-output"><div><span>INPUT</span><p>국세기본법 제84조가 개인정보 보호법상 다른 법률의 특별한 규정인가?</p></div><div><span>FIRST FAILURE</span><p>답변은 정답 방향이지만 evaluator가 부칙 근거의 시점 binding을 확인하지 못했습니다.</p></div></div></div>}
function OntologyView(){return <div className="ontology-board"><div className="ontology-toolbar"><span>enterprise-legal-ontology@0.3</span><button>변경 영향 보기</button></div><div className="ontology-canvas"><div className="onto-core"><span>TYPE SYSTEM</span><strong>Legal Matter</strong><small>semantic + kinetic</small></div>{[['Case','object','10%','18%'],['Statute','object','68%','14%'],['Governing norm','relation','8%','62%'],['Basis coverage','metric','66%','60%'],['Access scope','policy','35%','78%'],['Review answer','action','72%','80%']].map(n=><div key={n[0]} className={`onto-node ${n[1]}`} style={{left:n[2],top:n[3]}}><span>{n[1]}</span><strong>{n[0]}</strong></div>)}<div className="onto-ring ring-one"/><div className="onto-ring ring-two"/></div><footer className="ontology-footer"><div><span>18</span>Object types</div><div><span>27</span>Relations</div><div><span>9</span>Metrics</div><div><span>6</span>Policies</div><div><span>4</span>Actions</div></footer></div>}
function ProductsView(){const stages=[['Raw corpus','3,118 files','checksum · source ACL','healthy'],['Structure','708 artifacts','parser v14 · doc.json','healthy'],['Domain graph','1.26 GB','edge manifest · lineage','review'],['Hybrid index','18.6 MB','lexical + vector','healthy'],['Golden registry','4 suites','split · lock · owner','healthy']];return <div className="pipeline-board">{stages.map((s,i)=><div key={s[0]} className="pipeline-step"><div className="step-index">0{i+1}</div><article><header><span className={s[3]}/><b>{s[3]}</b></header><h2>{s[0]}</h2><strong>{s[1]}</strong><p>{s[2]}</p></article>{i<stages.length-1&&<span className="pipeline-arrow">→</span>}</div>)}</div>}
function ReleasesView({onPromote}:{onPromote:()=>void}){return <div className="release-layout"><section className="release-hero"><div><span>CANDIDATE BUNDLE</span><h2>release-2026.08.26.5</h2><p>ADR-0042 · ontology 0.3 · prompt 34 · index 84</p></div><div className="release-score"><strong>6/7</strong><span>gates passed</span></div></section><section className="release-gates">{[['Golden regression','Passed','locked suites 4'],['Ontology compatibility','Passed','0 breaking changes'],['ACL / policy','Passed','0 violations'],['Latency p95','Passed','4.8s < 6.0s'],['Hard distractor','Review','2 unresolved cases'],['Supply chain','Passed','SBOM + signature'],['Rollback rehearsal','Passed','41s recovery']].map(g=><div key={g[0]}><span className={g[1].toLowerCase()}/><strong>{g[0]}</strong><b>{g[1]}</b><small>{g[2]}</small></div>)}</section><div className="release-actions"><button>bundle manifest</button><button className="primary-button" onClick={onPromote}>승격 검토 요청</button></div></div>}

function DatasetInspector({dataset}:{dataset:typeof workspaceDatasets[number]}){return <><div className="inspector-head"><div><p>{dataset.kind.toUpperCase()} · {dataset.version}</p><h2>{dataset.name}</h2></div><button>×</button></div><div className={`decision-banner dataset-${dataset.status}`}><span>CONNECTION</span><strong>{dataset.status}</strong><small>{dataset.records.toLocaleString()} records</small></div><section className="inspect-section"><h3>데이터 계약</h3><dl><div><dt>경로</dt><dd><code>{dataset.sourcePath}</code></dd></div><div><dt>Adapter</dt><dd>{dataset.adapter}</dd></div><div><dt>크기</dt><dd>{dataset.size}</dd></div><div><dt>설명</dt><dd>{dataset.description}</dd></div></dl></section><section className="inspect-section"><h3>노출 필드</h3><div className="field-list">{dataset.fields.map(f=><code key={f}>{f}</code>)}</div></section><section className="inspect-section"><h3>실험 안전장치</h3><div className="gate-row"><span>Version pinned</span><b className="pass">Yes</b></div><div className="gate-row"><span>Split locked</span><b className="pass">{dataset.status==='locked'?'Yes':'N/A'}</b></div><div className="gate-row"><span>Write access</span><b>Read only</b></div></section><div className="inspector-actions"><button className="quiet-button">schema</button><button className="primary-button">실험에 사용</button></div></>}
function RunInspector({selected,onCompare}:{selected:FlowNode;onCompare:()=>void}){return <><div className="inspector-head"><div><p>{selected.eyebrow}</p><h2>{selected.title}</h2></div><button>×</button></div><div className="decision-banner"><span>DECISION</span><strong>{selected.tone==='warn'?'회귀 확인 필요':selected.tone==='base'?'기준선 고정':'승격 후보'}</strong><small>3/4 gates passed</small></div><section className="inspect-section"><h3>실험 계약</h3><dl><div><dt>가설</dt><dd>정답 법적 효과만 executor에 전달하면 방향 오류가 감소한다.</dd></div><div><dt>변경</dt><dd><code>legal_effect_mode: gold_only</code></dd></div><div><dt>데이터</dt><dd>formal-v3 · locked · 113 cases</dd></div><div><dt>반복</dt><dd>3 paired trials</dd></div></dl></section><section className="inspect-section"><div className="section-title"><h3>Golden gates</h3><span>3 / 4</span></div><div className="gate-row"><span>Direction accuracy</span><b className="pass">87.0%</b></div><div className="gate-row"><span>Basis recall</span><b className="pass">91.3%</b></div><div className="gate-row"><span>Hard distractor</span><b className="fail">−2 cases</b></div><div className="gate-row"><span>Latency p95</span><b className="pass">4.8s</b></div></section><section className="inspect-section compact"><h3>Lineage</h3><div className="lineage-stack"><span>ADR-0040</span><i>→</i><span>ADR-0041</span><i>→</i><strong>ADR-0042</strong></div></section><div className="inspector-actions"><button className="quiet-button">113 cases</button><button className="primary-button" onClick={onCompare}>비교 열기</button></div></>}

function ExperimentModal({step,setStep,name,setName,onClose,onCreate}:{step:number;setStep:(n:number)=>void;name:string;setName:(s:string)=>void;onClose:()=>void;onCreate:()=>void}){const [dataset,setDataset]=useState('formal-v3');const ready=useMemo(()=>name.trim().length>3&&dataset.length>0,[name,dataset]);return <div className="modal-backdrop" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="experiment-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header><div><p>NEW EXPERIMENT · STEP {step}/4</p><h2 id="modal-title">{['가설을 먼저 동결합니다','데이터셋과 split을 고정합니다','변경할 한 변수를 선언합니다','실행 전 계약을 검토합니다'][step-1]}</h2></div><button onClick={onClose}>×</button></header><div className="stepper">{[1,2,3,4].map(n=><button key={n} className={step===n?'active':step>n?'done':''} onClick={()=>setStep(n)}><span>{step>n?'✓':n}</span>{['Hypothesis','Dataset','Change','Freeze'][n-1]}</button>)}</div><div className="modal-body">{step===1&&<><label className="form-field"><span>실험 이름</span><input value={name} onChange={e=>setName(e.target.value)}/></label><label className="form-field"><span>반증 가능한 가설</span><textarea defaultValue="retrieval 후보의 정의문 비중을 제한하면 hard distractor 회귀를 줄이면서 basis recall은 유지된다."/></label><div className="form-grid"><label className="form-field"><span>Primary metric</span><select defaultValue="basis_recall"><option>basis_recall</option><option>direction_exact</option></select></label><label className="form-field"><span>실패 판정</span><input defaultValue="Δ recall ≤ 0 또는 high-risk regression"/></label></div></>}{step===2&&<><div className="dataset-choice">{goldenSuites.slice(0,3).map(g=><label key={g.name} className={dataset===g.name?'selected':''}><input type="radio" name="dataset" value={g.name} checked={dataset===g.name} onChange={()=>setDataset(g.name)}/><span><strong>{g.name}</strong><small>{g.cases} cases · {g.split}</small></span><b>{g.coverage}</b></label>)}</div><div className="warning-note">Locked set 결과를 본 뒤 튜닝하면 새 dataset version이 필요합니다.</div></>}{step===3&&<><div className="change-contract"><label className="form-field"><span>변경 layer</span><select defaultValue="Ground"><option>Prepare</option><option>Ontology</option><option>Ground</option><option>Solve</option></select></label><label className="form-field"><span>단일 변경 key</span><input defaultValue="retrieval.definition_weight"/></label><label className="form-field"><span>Baseline</span><input defaultValue="ADR-0041 / run-041-b" readOnly/></label><label className="form-field"><span>Candidate value</span><input defaultValue="0.35"/></label></div><div className="warning-note safe">다른 prompt, model, ontology version은 baseline과 동일하게 고정됩니다.</div></>}{step===4&&<div className="freeze-review"><div><span>ADR</span><strong>새 ADR 필요</strong><em>실행 전에 생성·동결</em></div><div><span>Dataset</span><strong>{dataset}</strong><em>version pinned</em></div><div><span>Arms</span><strong>baseline / candidate</strong><em>paired inputs</em></div><div><span>Run record</span><strong>immutable</strong><em>inputs · outputs · usage · latency</em></div><div className="freeze-alert"><b>실험 실행은 아직 시작되지 않습니다.</b><p>초안을 만든 뒤 ADR과 manifest가 validation을 통과해야 runner가 활성화됩니다.</p></div></div>}</div><footer><button className="quiet-button" onClick={step===1?onClose:()=>setStep(step-1)}>{step===1?'취소':'이전'}</button><button className="primary-button" disabled={!ready} onClick={step===4?onCreate:()=>setStep(step+1)}>{step===4?'초안 만들기':'다음'}</button></footer></section></div>}
