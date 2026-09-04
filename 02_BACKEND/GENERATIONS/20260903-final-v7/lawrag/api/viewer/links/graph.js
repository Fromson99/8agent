/* 참조 네트워크 — 구역이 마디, 참조가 간선인 force 그래프.
 *
 * 벤더: vendor/d3.v7.min.js (ISC, Mike Bostock). CDN 을 부르지 않는다 —
 * 이 뷰어들은 오프라인 컨테이너에서 그대로 떠야 한다.
 *
 * ## 글자가 겹치지 않게
 *
 *   마디 라벨   forceCollide 반경에 **라벨 폭을 포함**시킨다 — 레이아웃이
 *               라벨 자리를 미리 비워 둔다.
 *   간선 글자   화면에 상주하지 않는다. hover 툴팁과 오른쪽 원문 패널에만.
 *
 * ## 원문이 곧 내비게이션이다
 *
 * 마디를 클릭하면 오른쪽에 그 구역의 원문이 뜨고, 본문 속 "제4조" 같은
 * 표면형은 링크다 — 클릭하면 그 마디로 건너가 다시 원문이 뜬다(위키처럼).
 * 좌표는 서버(/v1/rag/section)가 준다 — 화면이 문자열로 다시 찾지 않는다. */

const LG = {
  sel: null, ready: false, nodes: [], links: [], byId: new Map(),
  W: 900, H: 700, svg: null, g: null, zoom: null,
  nodeSel: null, linkSel: null,
};

function lgLabel(path) {
  const parts = (path || "").split(" ▸ ").filter(Boolean);
  let t = parts[parts.length - 1] || "?";
  if (t.length <= 2 && parts.length > 1) t = `${parts[parts.length - 2]} ▸ ${t}`;
  return t;
}

/* ------------------------------------------------------------------ 모델 */
function buildLinkGraph() {
  const byId = new Map();
  const nodes = [], links = [];
  const touch = (doc, node, path) => {
    const id = `${doc}:${node}`;
    if (!byId.has(id)) {
      const n = { id, doc, node, path, label: lgLabel(path) };
      byId.set(id, n);
      nodes.push(n);
    }
    return id;
  };
  for (const [d, es] of Object.entries(S.data.in_doc)) {
    for (const e of es) {
      links.push({
        source: touch(d, e.src, e.src_path), target: touch(d, e.dst, e.dst_path),
        surface: e.surface, via: "", srcDoc: d, dstDoc: d,
        srcLink: goSrc(d, e), dstLink: goDst(d, e) });
    }
  }
  for (const e of S.data.cross) {
    links.push({
      source: touch(e.src_doc, e.src, e.src_path),
      target: touch(e.dst_doc, e.dst, e.dst_path),
      surface: e.surface, via: e.via || "저장", srcDoc: e.src_doc, dstDoc: e.dst_doc,
      srcLink: goSrc(e.src_doc, e), dstLink: goDst(e.dst_doc, e) });
  }

  // 문서별 느슨한 자리 목표 — 무리(cluster)가 색과 함께 문서를 보여준다
  const used = [...new Set(nodes.map((n) => n.doc))];
  const W = Math.max(680, Math.round(Math.sqrt(nodes.length) * 115));
  const H = Math.max(560, Math.round(W * 0.75));
  const xt = Object.fromEntries(used.map((d, i) => [d, W * (i + 1) / (used.length + 1)]));

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((d) => d.id).distance(72).strength(0.5))
    .force("charge", d3.forceManyBody().strength(-150))
    .force("collide", d3.forceCollide()
      .radius((d) => 13 + d.label.length * 3.3).strength(0.9))
    .force("x", d3.forceX((d) => xt[d.doc]).strength(0.08))
    .force("y", d3.forceY(H / 2).strength(0.06))
    .stop();
  for (let i = 0; i < 280; i++) sim.tick();   // 초기 배치는 소리 없이 — 화면은 정착된 모양으로 뜬다

  if (LG.sim) LG.sim.stop();                  // 이전 데이터의 시뮬레이션이 돌고 있으면 끊는다
  LG.sim = sim;
  LG.nodes = nodes; LG.links = links; LG.byId = byId;
  LG.W = W; LG.H = H; LG.ready = true;
  if (LG.sel && LG.sel.kind === "node" && !byId.has(LG.sel.id)) LG.sel = null;
}

/* ------------------------------------------------------------------ 렌더 */
function edgePath(l) {
  const a = l.source, b = l.target;
  const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;      // 진행방향의 왼쪽 — 왕복 간선은 서로 반대로 휜다
  const mx = (a.x + b.x) / 2 + nx * 14, my = (a.y + b.y) / 2 + ny * 14;
  const cl = Math.hypot(b.x - mx, b.y - my) || 1;
  const ex = b.x - (b.x - mx) / cl * 10, ey = b.y - (b.y - my) / cl * 10;
  return `M${a.x},${a.y} Q${mx},${my} ${ex},${ey}`;
}

function drawLinkGraph() {
  const box = d3.select("#gcanvas");
  box.selectAll("*").remove();
  if (!LG.links.length) {
    box.append("p").attr("class", "hint").style("padding", "14px")
      .text("아직 참조 간선이 없습니다.");
    return;
  }
  const svg = box.append("svg")
    .attr("viewBox", [0, 0, LG.W, LG.H]).attr("class", "gnet");
  const defs = svg.append("defs");
  defs.append("marker").attr("id", "garr").attr("markerWidth", 7)
    .attr("markerHeight", 7).attr("refX", 6).attr("refY", 3.5).attr("orient", "auto")
    .append("path").attr("d", "M0,0 L7,3.5 L0,7")
    .attr("fill", "none").attr("stroke", "context-stroke").attr("stroke-width", 1.2);
  const g = svg.append("g");
  LG.svg = svg; LG.g = g;

  LG.zoom = d3.zoom().scaleExtent([0.25, 3])
    .on("zoom", (ev) => g.attr("transform", ev.transform));
  svg.call(LG.zoom)
    .on("click", (ev) => {
      if (ev.target.closest(".gn") || ev.target.closest(".ge")) return;
      LG.sel = null; applyDim(); lgDetail();
    });

  const tip = document.getElementById("gtip");
  LG.linkSel = g.append("g").selectAll("path")
    .data(LG.links).join("path")
    .attr("class", (l) => "ge" + (l.srcDoc === l.dstDoc ? "" : " gx"))
    .attr("stroke", (l) => S.color[l.srcDoc])
    .attr("marker-end", "url(#garr)")
    .attr("d", edgePath)
    .on("click", (ev, l) => {
      ev.stopPropagation();
      LG.sel = { kind: "edge", l };
      applyDim(); lgDetail();
    })
    .on("mouseenter", (ev, l) => {
      tip.innerHTML = `${esc(l.source.label)} <span class="chip">${esc(l.surface)}</span> `
        + `${esc(l.target.label)}${l.via ? ` <span class="pill">${esc(l.via)}</span>` : ""}`;
      tip.classList.remove("hidden");
    })
    .on("mousemove", (ev) => {
      tip.style.left = `${ev.clientX + 14}px`;
      tip.style.top = `${ev.clientY + 10}px`;
    })
    .on("mouseleave", () => tip.classList.add("hidden"));

  LG.nodeSel = g.append("g").selectAll("g")
    .data(LG.nodes).join("g")
    .attr("class", "gn")
    .attr("transform", (d) => `translate(${d.x},${d.y})`)
    // 드래그는 좌표를 직접 옮기지 않는다 — 고정점(fx/fy)만 잡고 시뮬레이션을
    // 다시 데워, 이웃과 간선이 매 tick 함께 재배치되게 한다. (요소를
    // sourceEvent.target 으로 찾으면 빠른 드래그에서 엉뚱한 마디가 움직인다 —
    // 데이텀 d 가 진실이고, 그리기는 tick 핸들러 한 곳이 맡는다.)
    .call(d3.drag()
      .on("start", (ev, d) => {
        if (!ev.active) LG.sim.alphaTarget(0.25).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on("end", (ev, d) => {
        if (!ev.active) LG.sim.alphaTarget(0);
        d.fx = null; d.fy = null;
      }))
    .on("click", (ev, d) => {
      ev.stopPropagation();
      if (LG.sel && LG.sel.kind === "node" && LG.sel.id === d.id) {
        LG.sel = null; applyDim(); lgDetail(); return;
      }
      selectNode(d.id, false);
    });
  LG.nodeSel.append("title")
    .text((d) => `${S.name[d.doc]} ▸ ${d.path}`);
  LG.nodeSel.append("circle").attr("r", 5).attr("fill", (d) => S.color[d.doc]);
  LG.nodeSel.append("text").attr("class", "glb").attr("x", 9).attr("y", 4)
    .text((d) => clip(d.label, 16));

  // 그리기의 단일한 자리 — 드래그로 데워진 시뮬레이션이 여기로만 화면을 움직인다
  LG.sim.on("tick", () => {
    LG.nodeSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
    LG.linkSel.attr("d", edgePath);
  });
  applyDim();
}

/* 고른 것과 이어진 것만 남긴다 — 지우지 않고 흐리게(전체 속 위치가 보여야 한다). */
function applyDim() {
  if (!LG.nodeSel) return;
  let nearN = null, nearL = null;
  if (LG.sel && LG.sel.kind === "node") {
    nearN = new Set([LG.sel.id]); nearL = new Set();
    for (const l of LG.links) {
      if (l.source.id === LG.sel.id || l.target.id === LG.sel.id) {
        nearL.add(l); nearN.add(l.source.id); nearN.add(l.target.id);
      }
    }
  } else if (LG.sel && LG.sel.kind === "edge") {
    nearL = new Set([LG.sel.l]);
    nearN = new Set([LG.sel.l.source.id, LG.sel.l.target.id]);
  }
  const qmiss = (d) => S.q && !(d.label + d.path).replace(/\s/g, "").includes(S.q);
  LG.nodeSel.classed("dim", (d) => (nearN && !nearN.has(d.id)) || qmiss(d));
  LG.linkSel.classed("dim", (l) => nearL && !nearL.has(l));
  LG.linkSel.classed("hot", (l) => !!(nearL && nearL.has(l)));
}

function selectNode(id, center) {
  const n = LG.byId.get(id);
  if (!n) return;
  LG.sel = { kind: "node", id };
  trailPush({ tab: "graph", doc: n.doc, node: n.node, label: n.label,
              title: `${S.name[n.doc] || ""} ▸ ${n.path}` });
  applyDim();
  loadSection(n);
  if (center && LG.svg) {
    LG.svg.transition().duration(450).call(LG.zoom.translateTo, n.x, n.y);
  }
}

/* -------------------------------------------------------- 원문 패널 */
async function loadSection(n) {
  const el = document.getElementById("gside");
  el.innerHTML = "<p class='hint'>원문 불러오는 중…</p>";
  const r = await fetch(`/v1/rag/section?doc_id=${encodeURIComponent(n.doc)}&node=${n.node}`);
  if (!r.ok) { el.innerHTML = "<p class='hint'>원문을 불러오지 못했습니다.</p>"; return; }
  const d = await r.json();
  el.innerHTML = `
    <div class="docgroup"><span class="dot" style="background:${S.color[d.doc_id]}"></span>
      <span title="${esc(d.doc)}">${esc(short(d.doc))}</span>
      ${d.page ? `<span class="pill">p.${d.page}</span>` : ""}
      <span class="grow"></span>
      <a class="go" href="/structure/?doc=${encodeURIComponent(d.doc_id)}&node=${d.node}">구조 뷰어 →</a>
    </div>
    <div class="gpath">${esc(d.path)}</div>
    <div class="row" style="margin:6px 0">
      <span class="pill">참조 ${d.refs.length}</span>
      <span class="pill">피참조 ${d.cited_by.length}</span>
    </div>
    <div class="txt">${linkify(d.text, d.refs, d.doc_id)}</div>
    ${d.cited_by.length ? `<div class="sub" style="margin:10px 0 4px">이 구역을 가리키는 곳</div>`
      + d.cited_by.map((c) => `
        <div class="citer">
          <span class="dot" style="background:${S.color[c.src_doc]}"></span>
          <a class="refgo" data-doc="${esc(c.src_doc)}" data-node="${c.src}"
             title="${esc(c.src_path)}">${esc(lgLabel(c.src_path))}</a>
          <span class="chip">${esc(c.surface)}</span>
        </div>`).join("") : ""}`;
  el.querySelectorAll(".refgo").forEach((a) => {
    a.onclick = () => {
      const id = `${a.dataset.doc}:${a.dataset.node}`;
      if (LG.byId.has(id)) selectNode(id, true);
      else {
        trailPush({ tab: "graph", doc: a.dataset.doc, node: +a.dataset.node,
                    label: a.textContent.trim(), title: a.title || "" });
        loadSection({ doc: a.dataset.doc, node: +a.dataset.node });
      }
    };
  });
}

/* 본문 속 표면형 → 링크. 긴 표면형 먼저 토큰으로 바꿔 짧은 것이 그 안을
 * 다시 물지 않게 한다("제4조"가 "제4조의2" 링크를 깨지 않게).
 *
 * 문서-안 간선은 외부 힌트가 붙은 출현을 물지 않는다 — "법 제238조"의
 * 제238조는 다른 문서(법률) 이야기라, 같은 표면형의 안쪽 간선이 그 자리를
 * 링크하면 엉뚱한 데로 간다. 힌트 문법은 refs.py 의 _EXTERNAL 과 같은
 * 관례다(「…」·법형식 접미 낱말·잘린 「 닫힘·맨 영). */
const EXT_HINT = new RegExp(
  "(?:[가-힣A-Za-z0-9·]{0,20}(?:법|법률|령|규칙|세칙|규정|약관|조례|정관|지침|고시)"
  + "|」|(?<![가-힣])영)\\s*$");

function linkify(text, refs, docId) {
  let html = esc(text || "");
  const sorted = [...refs].sort((a, b) => b.surface.length - a.surface.length);
  sorted.forEach((r, i) => {
    const s = esc(r.surface);
    if (!s) return;
    const guard = r.dst_doc === docId && !r.via;   // 문서-안 간선만 힌트를 살핀다
    let out = "", p = 0;
    for (let j = html.indexOf(s); j >= 0; j = html.indexOf(s, p)) {
      const skip = guard && EXT_HINT.test(html.slice(Math.max(0, j - 48), j));
      out += html.slice(p, j) + (skip ? s : `\u0000${i}\u0000`);
      p = j + s.length;
    }
    html = out + html.slice(p);
  });
  return html.replace(/\u0000(\d+)\u0000/g, (_, i) => {
    const r = sorted[+i];
    return `<a class="refgo" data-doc="${esc(r.dst_doc)}" data-node="${r.dst}"
      title="${esc(r.dst_path)}">${esc(r.surface)}</a>`;
  });
}

function lgDetail() {
  if (LG.sel && LG.sel.kind === "node") return;      // 원문 패널이 이미 답이다
  const el = document.getElementById("gside");
  if (LG.sel && LG.sel.kind === "edge") {
    const l = LG.sel.l;
    el.innerHTML = `
      <div class="docgroup">참조 간선</div>
      <div class="citer"><span class="dot" style="background:${S.color[l.srcDoc]}"></span>
        <a class="refgo" data-doc="${esc(l.srcDoc)}" data-node="${l.source.node}"
           title="${esc(l.source.path)}">${esc(l.source.label)}</a>
        <span class="chip">${esc(l.surface)}</span>
        <a class="refgo" data-doc="${esc(l.dstDoc)}" data-node="${l.target.node}"
           title="${esc(l.target.path)}">${esc(l.target.label)}</a>
        ${l.via ? `<span class="pill ${VIA_CLS[l.via] || ""}">${esc(l.via)}</span>` : ""}</div>
      <div class="links" style="margin-top:8px">
        <a class="go" href="${l.srcLink}">참조가 쓰인 자리 →</a>
        <a class="go" href="${l.dstLink}">가리키는 구역 →</a>
      </div>`;
    el.querySelectorAll(".refgo").forEach((a) => {
      a.onclick = () => selectNode(`${a.dataset.doc}:${a.dataset.node}`, true);
    });
    return;
  }
  el.innerHTML = "<p class='hint'>마디를 클릭하면 그 구역의 원문이 여기 뜹니다. "
    + "원문 속 <u>제N조</u> 같은 참조를 클릭하면 그 구역으로 건너갑니다.</p>";
}

function initLinkGraph() { /* d3.zoom 이 조작을 맡는다 — 여기서 할 일이 없다 */ }
