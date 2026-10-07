/* 8-AGENT application shell.
 * Domain screens own their interactions; this file owns product navigation,
 * page identity, pending-work badges, theme and the Ctrl/⌘+K switcher.
 */
(function () {
  "use strict";

  const GROUPS = [
    { label: "업무", items: [
      { key:"home", href:"/home/", label:"문서 허브", short:"문서", icon:"library", desc:"자료 업로드와 처리 현황" },
      { key:"rag", href:"/rag/", label:"법률 질의", short:"질의", icon:"spark", desc:"LegalClosure 질의응답" },
      { key:"expc", href:"/expc/", label:"해석례 연구", short:"해석례", icon:"book", desc:"법령해석례와 위키" },
    ]},
    { label: "지식 구축", items: [
      { key:"structure", href:"/structure/", label:"구조 검수", short:"구조", icon:"layers", desc:"원문 구조와 계층 교정" },
      { key:"bindings", href:"/bindings/", label:"구조화 설계", short:"틀", icon:"blocks", desc:"문서·폴더와 틀 연결" },
      { key:"glossary", href:"/glossary/", label:"용어집", short:"용어", icon:"tag", desc:"용어와 개념 검수" },
      { key:"knowledge", href:"/knowledge/", label:"지식 그래프", short:"그래프", icon:"network", desc:"개념·규범·근거 연결 탐색" },
      { key:"links", href:"/links/", label:"법률 연결", short:"참조", icon:"link", desc:"조문 참조와 연결 그래프" },
    ]},
    { label: "품질 학습", items: [
      { key:"golden", href:"/golden/", label:"골든셋", short:"골든", icon:"check", desc:"정답 조문과 질의 태깅" },
      { key:"experiments", href:"/experiments/", label:"실험 카탈로그", short:"실험", icon:"experiment", desc:"격리 모듈과 평가 실행 결과" },
      { key:"rules", href:"/rules/", label:"규칙 실험실", short:"공리", icon:"flask", desc:"귀납 규칙의 승격과 부검" },
      { key:"evolution", href:"/evolution/", label:"진화 루프", short:"진화", icon:"cycle", desc:"승인 신호와 탐색 변이 후보" },
      { key:"agent6", href:"/agent6/", label:"준법 점검", short:"점검", icon:"shield", desc:"체크리스트와 근거 연결" },
    ]},
    { label: "운영", items: [
      { key:"lineage", href:"/lineage/", label:"데이터 계보", short:"원장", icon:"route", desc:"수집부터 연결까지 추적" },
      { key:"pipeline", href:"/pipeline/", label:"파이프라인", short:"실행", icon:"play", desc:"미처리 작업 실행과 이력" },
      { key:"logs", href:"/logs/", label:"시스템 로그", short:"로그", icon:"pulse", desc:"질의·앱·파일 로그" },
    ]},
  ];
  const PAGES = Object.fromEntries(GROUPS.flatMap((g) => g.items).map((x) => [x.key, x]));
  const ICONS = {
    library:'<path d="M4 5.5h16M5.5 3v18M10 3v18M15 3v18M20 5.5v15.5H3"/>',
    spark:'<path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3Z"/><path d="m18.5 15 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z"/>',
    book:'<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H11a3 3 0 0 1 3 3v17a3 3 0 0 0-3-3H4V4.5Z"/><path d="M20 4.5A2.5 2.5 0 0 0 17.5 2H14v20a3 3 0 0 1 3-3h3V4.5Z"/>',
    layers:'<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 17l9 5 9-5"/>',
    blocks:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="8.5" y="14" width="7" height="7" rx="1"/><path d="M6.5 10v2h11v-2M12 12v2"/>',
    tag:'<path d="M20.6 13.6 13.7 20.5a2 2 0 0 1-2.8 0L3.5 13.1A2 2 0 0 1 3 11.7V4a1 1 0 0 1 1-1h7.7a2 2 0 0 1 1.4.6l7.5 7.2a2 2 0 0 1 0 2.8Z"/><circle cx="8" cy="8" r="1.4"/>',
    network:'<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="m10.8 7.2-4.6 8.6M13.2 7.2l4.6 8.6M7.5 18h9"/>',
    link:'<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2"/>',
    check:'<path d="M9 11.5 11 14l4.5-5"/><path d="M20 12a8 8 0 1 1-4.8-7.3"/><path d="M16 3h5v5"/>',
    flask:'<path d="M9 3h6M10 3v6l-5.5 9.2A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.8L14 9V3"/><path d="M7 16h10"/>',
    experiment:'<path d="M6 3h12M8 3v5l-4 8a3 3 0 0 0 2.7 4h10.6a3 3 0 0 0 2.7-4l-4-8V3"/><path d="M7 14h10"/><circle cx="10" cy="17" r="1"/><circle cx="14.5" cy="16.5" r=".7"/>',
    cycle:'<path d="M20 7h-5V2"/><path d="M20 7a8 8 0 1 0 1 8"/><path d="M4 17h5v5"/><path d="M4 17a8 8 0 0 0 13-8"/>',
    shield:'<path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/>',
    route:'<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h3a3 3 0 0 0 3-3V9a3 3 0 0 1 3-3h-1M6 16V8a2 2 0 0 1 2-2h2"/>',
    play:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3V9Z"/>',
    pulse:'<path d="M3 12h4l2-7 4 14 2-7h6"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
    panel:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
    sun:'<circle cx="12" cy="12" r="3.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  };
  const icon = (name, cls="") => `<svg class="ui-icon ${cls}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;

  const QUEUES = [
    { key:"glossary", jump:"/glossary/#review", url:"/v1/glossary/review?limit=1", pick:(d)=>d.total||0, hint:"용어 검수 대기" },
    { key:"links", jump:"/links/#pending", url:"/v1/rag/links/summary", pick:(d)=>d.pending||0, hint:"보류 참조" },
    { key:"rag", jump:"/rag/#backlog", url:"/v1/rag/verdicts", pick:(d)=>(d.edges||[]).length+(d.fixes||[]).length+(d.struct||[]).length+(d.misses||[]).length+(d.memory_pending||0), hint:"판정 백로그" },
    { key:"rules", jump:"/rules/", url:"/v1/rag/rules", pick:(d)=>(d.rules||[]).filter((r)=>r.status==="잠정"||(r["보고서"]||{})["권고"]==="정착 후보").length, hint:"규칙 승격 대기" },
    { key:"expc", jump:"/expc/#wiki", url:"/v1/expc/summary", pick:(d)=>d.wiki_pending||0, hint:"위키 생애 대기" },
    { key:"logs", jump:"/logs/", tone:"err", url:"/v1/logs/app?level=ERROR&limit=50", pick:(d)=>d.count||0, hint:"최근 오류" },
  ];
  const CACHE_KEY = "ui.queue-counts.v2";

  function currentKey(host) { return host.getAttribute("data-nav") || (location.pathname.split("/")[1] || "home"); }
  function routeMeta(key) {
    return location.pathname.endsWith("debug.html")
      ? { ...PAGES.rag, label:"RAG 디버깅", desc:"질의 경로와 교정 백로그 분석" }
      : (PAGES[key] || PAGES.home);
  }
  async function counts() {
    try { const s=JSON.parse(sessionStorage.getItem(CACHE_KEY)||"null"); if(s&&Date.now()-s.t<60000)return s.n; } catch {}
    const n={};
    await Promise.all(QUEUES.map(async(q)=>{ try { const r=await fetch(q.url); if(r.ok)n[q.key]=q.pick(await r.json()); } catch {} }));
    try { sessionStorage.setItem(CACHE_KEY,JSON.stringify({t:Date.now(),n})); } catch {}
    return n;
  }
  async function mountBadges(shell) {
    const n=await counts();
    for(const q of QUEUES){ if(!n[q.key])continue; shell.querySelectorAll(`[data-key="${q.key}"]`).forEach((a)=>{
      if(a.querySelector(".qbadge"))return; const b=document.createElement("span"); b.className=`qbadge${q.tone?` ${q.tone}`:""}`;
      b.textContent=n[q.key]>999?"999+":String(n[q.key]); b.title=q.hint;
      b.addEventListener("click",(e)=>{e.preventDefault();e.stopPropagation();location.href=q.jump;}); a.appendChild(b);
    }); }
  }
  async function opsChip(host) {
    try { const r=await fetch("/v1/ops/status"); if(!r.ok)return; const s=await r.json(); if(!s.record)return;
      const chip=document.createElement("span"); chip.className="ops-chip"; chip.textContent=`기록 ${s.outbox}건`;
      chip.title="기록 모드 · 쓰기 조작이 아웃박스에 쌓입니다"; host.appendChild(chip); } catch {}
  }
  function navMarkup(cur) {
    return GROUPS.map((g)=>`<section class="ui-nav-group"><div class="ui-nav-label">${g.label}</div>${g.items.map((x)=>
      `<a href="${x.href}" data-key="${x.key}" class="ui-nav-item${x.key===cur?" on":""}" ${x.key===cur?'aria-current="page"':""} title="${x.desc}">
        ${icon(x.icon)}<span class="ui-nav-copy"><b>${x.label}</b><small>${x.desc}</small></span></a>`).join("")}</section>`).join("");
  }
  function applyTheme(value) {
    if(value==="system")delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme=value;
    localStorage.setItem("ui.theme",value); document.querySelectorAll("[data-theme-label]").forEach((x)=>x.textContent=value==="dark"?"어두운 화면":value==="light"?"밝은 화면":"시스템 화면");
  }
  function cycleTheme(){const now=localStorage.getItem("ui.theme")||"system";applyTheme(now==="system"?"light":now==="light"?"dark":"system");}

  function commandPalette(cur) {
    const modal=document.createElement("div"); modal.className="ui-command hidden";
    modal.innerHTML=`<div class="ui-command-card" role="dialog" aria-modal="true" aria-label="화면 이동">
      <div class="ui-command-search">${icon("search")}<input type="search" placeholder="화면이나 기능 찾기" autocomplete="off"><kbd>esc</kbd></div>
      <div class="ui-command-list"></div><footer><span>↑↓ 이동</span><span>enter 열기</span><span>⌘K 닫기</span></footer></div>`;
    document.body.appendChild(modal); const input=modal.querySelector("input"),list=modal.querySelector(".ui-command-list"); let selected=0;
    const rows=()=>{const q=input.value.trim().toLowerCase();return GROUPS.flatMap((g)=>g.items.map((x)=>({...x,group:g.label}))).filter((x)=>!q||`${x.label} ${x.short} ${x.desc} ${x.group}`.toLowerCase().includes(q));};
    function paint(){const data=rows();selected=Math.max(0,Math.min(selected,data.length-1));list.innerHTML=data.map((x,i)=>
      `<a href="${x.href}" class="${i===selected?"sel":""}" data-key="${x.key}">${icon(x.icon)}<span><b>${x.label}</b><small>${x.group} · ${x.desc}</small></span>${x.key===cur?"<em>현재</em>":""}</a>`).join("")||'<div class="ui-command-empty">일치하는 화면이 없습니다</div>';list.querySelector(".sel")?.scrollIntoView({block:"nearest"});}
    function open(){modal.classList.remove("hidden");input.value="";selected=0;paint();requestAnimationFrame(()=>input.focus());}
    function close(){modal.classList.add("hidden");}
    input.addEventListener("input",()=>{selected=0;paint();}); input.addEventListener("keydown",(e)=>{
      if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();selected+=e.key==="ArrowDown"?1:-1;paint();}
      else if(e.key==="Enter"){e.preventDefault();const a=list.querySelector(".sel");if(a)location.href=a.href;}
      else if(e.key==="Escape")close();});
    modal.addEventListener("mousedown",(e)=>{if(e.target===modal)close();}); document.addEventListener("keydown",(e)=>{
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){e.preventDefault();modal.classList.contains("hidden")?open():close();}
      else if(e.key==="Escape"&&!modal.classList.contains("hidden"))close();}); return {open,close};
  }

  function mount() {
    const oldNav=document.querySelector("[data-nav]"); if(!oldNav||document.querySelector(".ui-shell"))return;
    const cur=currentKey(oldNav),page=routeMeta(cur),bar=oldNav.closest(".ui-bar");
    document.body.dataset.uiPage=cur;
    if(!document.querySelector('link[data-ui-refresh]')){
      const refresh=document.createElement("link");refresh.rel="stylesheet";refresh.href="/ui/refresh.css";refresh.dataset.uiRefresh="";document.head.appendChild(refresh);
    }
    if(!document.querySelector('link[data-ui-enterprise]')){
      const enterprise=document.createElement("link");enterprise.rel="stylesheet";enterprise.href="/ui/enterprise.css";enterprise.dataset.uiEnterprise="";document.head.appendChild(enterprise);
    }
    applyTheme(localStorage.getItem("ui.theme")||"system"); document.body.classList.add("has-ui-shell");
    if(localStorage.getItem("ui.compact")==="1")document.body.classList.add("ui-collapsed");
    const shell=document.createElement("aside"); shell.className="ui-shell"; shell.innerHTML=`
      <div class="ui-brand"><a href="/home/" aria-label="8-AGENT 홈"><span class="ui-brand-mark">8</span><span class="ui-brand-copy"><b>8-AGENT</b><small>Legal Intelligence</small></span></a><button class="ui-collapse" type="button" title="메뉴 폭 줄이기">${icon("panel")}</button></div>
      <button class="ui-nav-search" type="button">${icon("search")}<span>빠른 이동</span><kbd>⌘K</kbd></button>
      <nav class="ui-nav" aria-label="주 메뉴">${navMarkup(cur)}</nav>
      <div class="ui-shell-foot"><button class="ui-theme" type="button">${icon("sun")}<span data-theme-label></span></button><div class="ui-ops"></div></div>`;
    document.body.insertBefore(shell,document.body.firstChild); oldNav.remove();
    const menu=document.createElement("button");menu.className="ui-mobile-menu";menu.type="button";menu.setAttribute("aria-label","메뉴 열기");menu.innerHTML=icon("menu");bar.insertBefore(menu,bar.firstChild);
    const heading=document.createElement("div");heading.className="ui-heading";heading.innerHTML=`<strong>${page.label}</strong><span>${page.desc}</span>`;bar.insertBefore(heading,bar.querySelector(".ui-meta")||bar.querySelector(".grow"));
    const skip=document.createElement("a");skip.className="ui-skip";skip.href="#ui-main";skip.textContent="본문으로 건너뛰기";document.body.insertBefore(skip,shell);
    const main=document.querySelector("main");if(main&&!main.id)main.id="ui-main";
    const backdrop=document.createElement("div");backdrop.className="ui-shell-backdrop";document.body.appendChild(backdrop);
    const palette=commandPalette(cur);shell.querySelector(".ui-nav-search").addEventListener("click",palette.open);shell.querySelector(".ui-theme").addEventListener("click",cycleTheme);
    shell.querySelector(".ui-collapse").addEventListener("click",()=>{document.body.classList.toggle("ui-collapsed");localStorage.setItem("ui.compact",document.body.classList.contains("ui-collapsed")?"1":"0");});
    const closeMobile=()=>document.body.classList.remove("ui-nav-open");menu.addEventListener("click",()=>document.body.classList.toggle("ui-nav-open"));backdrop.addEventListener("click",closeMobile);shell.querySelectorAll("a").forEach((a)=>a.addEventListener("click",closeMobile));
    mountBadges(shell);opsChip(shell.querySelector(".ui-ops"));
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mount);else mount();
})();
