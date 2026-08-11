/* 구조화 연결 — 폴더·문서를 구조화 틀에 손으로 잇는 화면.
 *
 * 왜 캔버스인가: "무엇이 무슨 틀로 잘리는가" 는 **관계**다. 표로 보면 폴더마다 한 줄이
 * 되고, 한 틀을 여러 폴더가 쓰는 것도 예외로 뺀 문서 하나도 줄 사이에 숨는다.
 * 선으로 그리면 그 둘이 한눈에 보인다.
 *
 * ## 정본은 어디에 있나
 *
 *   연결   서버의 bindings (폴더 표 / 문서 표) — 화면은 그것을 그린다
 *   자리   서버의 canvas.pos — 화면의 기억일 뿐, 없으면 자동 배치한다
 *   초안   서버의 canvas.drafts — **아직 만들지 않은 틀**과 거기 이어 둔 것
 *
 * 초안을 서버에 두는 이유: 이어 놓고 새로고침하면 다 날아가는 화면은 쓸 수 없다.
 *
 * ## 네 종류의 선
 *
 *   실선(파랑)  이 폴더는 이 틀로 잘린다 (bindings.folders)
 *   실선(주황)  이 문서만 따로 — 폴더 연결을 이기는 예외 (bindings.docs)
 *   파선        초안에 이어 둔 것. 아직 아무 일도 일어나지 않았다 — 실행해야 틀이 생긴다.
 *   점선(회색)  소속 — "이 문서는 이 폴더에서 나왔다". 연결이 아니라 출신이다.
 *
 * 소속 선을 그리는 이유: 문서 하나를 따로 빼서 다른 틀에 이으면, 그 문서가 **어느
 * 폴더에서 나온 예외인지**가 화면에서 사라진다. 폴더를 함께 세워 점선으로 이어 두면
 * "폴더는 A 틀인데 이 문서만 B 틀" 이 한눈에 보인다.
 *
 * ## 내장 구조화 — 손으로 잇지 않았는데 이미 이어져 있는 것
 *
 * 법령 본문 XML 로 들어온 문서는 태그 계층을 그대로 옮긴다(추론 0, fitness 1.0).
 * 그건 **파일 형식이 정한 길**이라 사람이 바꿀 수 없다. 그래도 "이 문서는 무엇으로
 * 잘렸나" 의 답이므로 읽기 전용 노드로 그린다 — 안 그리면 이 문서들만 캔버스에서
 * 사라져 "아직 아무것도 안 이어졌다" 로 잘못 읽힌다.
 */
const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* 원본 형식 — 흐름이 여기서 갈린다. 배지로 늘 보이게 한다.
 * (설명 문구는 서버의 KIND_SIGNALS 로 덮어써 두 곳이 갈리지 않게 한다.) */
const KIND = {
  pdf: { label: "PDF", note: "제목 표시 · 타이포그래피 · 지면 좌표" },
  docx: { label: "DOCX", note: "제목 계층(Word 스타일) · 좌표 없음" },
  hwp: { label: "HWP", note: "마커만 (제목 신호·좌표 없음)" },
  hwpx: { label: "HWPX", note: "마커만 (제목 신호·좌표 없음)" },
  lawxml: { label: "XML", note: "태그 계층 — 구조화 틀을 쓰지 않는다" },
};
const HEADING_KINDS = ["pdf", "docx"];       // 제목 신호가 오는 형식

const S = {
  docs: [], folders: [], formats: [],
  bind: { folders: {}, docs: {} },
  pos: {}, drafts: [],
  q: "",
  drag: null,            // 노드 옮기기
  wire: null,            // 선 긋는 중 {from, x, y}
  busy: new Set(),       // 실행 중인 틀 (버튼 잠금)
};

/* 노드 id 규약 — 한 문자열로 종류와 키를 함께 나른다(DOM·좌표·초안이 같은 키를 쓴다) */
const FOLDER = (n) => `folder:${n}`;
const DOC = (id) => `doc:${id}`;
const FMT = (t) => `fmt:${t}`;
const kind = (id) => id.split(":")[0];
const key = (id) => id.slice(id.indexOf(":") + 1);

/* 내장 구조화 — 파일 형식이 정하는 길이라 사람이 잇거나 끊을 수 없다. */
const BUILTIN = {
  lawxml: { id: "builtin:lawxml", name: "법령 XML 태그",
            note: "추론 없이 태그 계층 그대로 · 적합도 1.0",
            match: (d) => d.source_kind === "lawxml" },
};

/* 세 열 — 폴더 ┄▸ 문서 ━▸ 틀. 소속 선이 왼쪽에서 오른쪽으로 흐르게 하는 배치다. */
const NODE_W = 210, GAP_Y = 74, COL_FOLDER = 40, COL_DOC = 285, COL_FMT = 560;

/* 문서 하나의 원본 형식 배지. 형식이 흐름을 가르므로 문서가 보이는 곳마다 붙인다. */
const kindOf = (docId) => S.docs.find((d) => d.doc_id === docId)?.source_kind || "";

function kindBadge(k) {
  const info = KIND[k];
  if (!info) return "";
  return `<span class="pill kind ${k}" title="${esc(info.note)}">${info.label}</span>`;
}

/* 문서 묶음의 형식 분포 — "PDF 2 · HWP 1" */
function kindMix(ids) {
  const n = {};
  for (const id of ids) {
    const k = kindOf(id);
    if (k) n[k] = (n[k] || 0) + 1;
  }
  return Object.entries(n).map(([k, c]) => `${KIND[k]?.label || k} ${c}`).join(" · ");
}

async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

async function errText(r) {
  const j = await r.json().catch(() => ({}));
  const d = j.detail;
  if (typeof d === "string") {
    try { const p = JSON.parse(d); return `${p.error} — ` +
      (p.failed || []).map((f) => `${f.name} ${Math.round(f.score * 100)}%`).join(", "); }
    catch { return d; }
  }
  return (d && d.message) || `실패 (${r.status})`;
}

function banner(msg, kindName = "") {
  const b = $("banner");
  b.textContent = msg;
  b.className = "banner " + kindName;
  clearTimeout(banner.t);
  banner.t = setTimeout(() => b.classList.add("hidden"), 7000);
}

/* ------------------------------------------------------------------ 적재 */
async function load() {
  const [docs, folders, fmts, canvas] = await Promise.allSettled([
    jget("/v1/structure/documents"),
    jget("/v1/structure/folders"),
    jget("/v1/formats"),
    jget("/v1/formats/canvas"),
  ]);
  S.docs = docs.status === "fulfilled" ? docs.value.documents : [];
  S.folders = folders.status === "fulfilled" ? folders.value.folders
    : [...new Set(S.docs.map((d) => d.folder).filter(Boolean))]
        .map((n) => ({ name: n, docs: 0 }));
  if (fmts.status === "fulfilled") {
    S.formats = fmts.value.routes || [];
    S.bind = fmts.value.bindings || { folders: {}, docs: {} };
    for (const [k, note] of Object.entries(fmts.value.kind_signals || {}))
      if (KIND[k]) KIND[k].note = note;     // 설명의 정본은 서버다
  }
  if (canvas.status === "fulfilled") {
    S.pos = canvas.value.pos || {};
    S.drafts = canvas.value.drafts || [];
  }
  render();
}

async function saveCanvas() {
  await fetch("/v1/formats/canvas", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pos: S.pos, drafts: S.drafts }) });
}

/* --------------------------------------------------------------- 모델 계산 */
/* 캔버스에 서는 노드 = 연결이 있는 것 + 사람이 끌어다 놓은 것(자리가 있는 것). */
function model() {
  const nodes = new Map();
  const add = (id, extra) => {
    if (!nodes.has(id)) nodes.set(id, { id, ...extra });
    return nodes.get(id);
  };

  for (const f of S.formats) if (f.ready) {
    // 틀은 연결이 있거나 자리를 잡아 준 것만 캔버스에 세운다 — 등록만 하고 안 쓰는
    // 틀까지 그리면 화면이 등록부 목록이 된다(그건 문서·데이터 화면의 일이다).
    const used = Object.values(S.bind.folders).includes(f.doc_type)
      || Object.values(S.bind.docs).includes(f.doc_type);
    if (used || S.pos[FMT(f.doc_type)]) add(FMT(f.doc_type), { fmt: f });
  }
  for (const d of S.drafts) add(`draft:${d.id}`, { draft: d });

  for (const [name, dt] of Object.entries(S.bind.folders)) {
    if (S.formats.some((f) => f.doc_type === dt)) add(FOLDER(name), {});
  }
  for (const [id, dt] of Object.entries(S.bind.docs)) {
    if (S.formats.some((f) => f.doc_type === dt)) add(DOC(id), {});
  }
  for (const d of S.drafts) {
    (d.folders || []).forEach((n) => add(FOLDER(n), {}));
    (d.docs || []).forEach((i) => add(DOC(i), {}));
  }
  for (const id of Object.keys(S.pos)) {
    if (kind(id) === "folder" && S.folders.some((f) => f.name === key(id))) add(id, {});
    if (kind(id) === "doc" && S.docs.some((d) => d.doc_id === key(id))) add(id, {});
  }

  // 선 — 실선(확정) / 파선(초안)
  const edges = [];
  for (const [name, dt] of Object.entries(S.bind.folders))
    if (nodes.has(FMT(dt))) edges.push({ from: FOLDER(name), to: FMT(dt), firm: true });
  for (const [id, dt] of Object.entries(S.bind.docs))
    if (nodes.has(FMT(dt))) edges.push({ from: DOC(id), to: FMT(dt), firm: true,
                                         exception: true });
  for (const d of S.drafts) {
    (d.folders || []).forEach((n) =>
      edges.push({ from: FOLDER(n), to: `draft:${d.id}`, firm: false }));
    (d.docs || []).forEach((i) =>
      edges.push({ from: DOC(i), to: `draft:${d.id}`, firm: false }));
  }

  // 내장 구조화 — 사람이 잇지 않았지만 이미 그 길로 잘린 문서들
  for (const b of Object.values(BUILTIN)) {
    const mine = S.docs.filter(b.match);
    if (!mine.length) continue;
    add(b.id, { builtin: b, docs: mine });
    for (const d of mine) {
      add(DOC(d.doc_id), {});
      edges.push({ from: DOC(d.doc_id), to: b.id, firm: true, builtin: true });
    }
  }

  // 소속 — 캔버스에 선 문서의 폴더도 함께 세운다("이 문서는 여기서 나왔다")
  for (const id of [...nodes.keys()]) {
    if (kind(id) !== "doc") continue;
    const folder = S.docs.find((d) => d.doc_id === key(id))?.folder;
    if (!folder) continue;
    add(FOLDER(folder), {});
    edges.push({ from: FOLDER(folder), to: id, own: true });
  }
  return { nodes, edges };
}

/* 자리 — 사람이 옮긴 것이 우선, 없으면 폴더·문서·틀 세 열로 세운다. */
const COL_OF = { folder: COL_FOLDER, doc: COL_DOC, fmt: COL_FMT, draft: COL_FMT,
                 builtin: COL_FMT };

function layout(nodes) {
  const seq = { folder: 0, doc: 0, fmt: 0 };
  for (const n of nodes.values()) {
    const k = kind(n.id);
    const col = k === "folder" ? "folder" : k === "doc" ? "doc" : "fmt";
    const p = S.pos[n.id];
    n.x = p ? p[0] : (COL_OF[k] ?? COL_FOLDER);
    n.y = p ? p[1] : 30 + seq[col]++ * GAP_Y;
  }
}

/* ------------------------------------------------------------------ 그리기 */
function render() {
  renderSources();
  const { nodes, edges } = model();
  layout(nodes);

  $("empty").hidden = nodes.size > 0;
  const box = $("nodes");
  box.innerHTML = "";
  for (const n of nodes.values()) box.appendChild(nodeEl(n));
  drawWires(nodes, edges);

  const nf = Object.keys(S.bind.folders).length, nd = Object.keys(S.bind.docs).length;
  $("summary").textContent =
    `틀 ${S.formats.filter((f) => f.ready).length} · 연결 폴더 ${nf} · 예외 문서 ${nd}`
    + (S.drafts.length ? ` · 초안 ${S.drafts.length}` : "");
}

function renderSources() {
  const q = S.q.replace(/\s/g, "").toLowerCase();
  const hit = (s) => !q || (s || "").replace(/\s/g, "").toLowerCase().includes(q);
  const box = $("srcList");
  box.innerHTML = "";

  // 이미 있는 틀 — 끌어다 놓아야 캔버스에 선다. 아무것도 안 이어진 틀은 스스로
  // 나타날 수 없으므로(연결이 노드를 부른다) 이 목록이 유일한 통로다.
  const ready = S.formats.filter((f) => f.ready && hit(f.doc_type));
  if (ready.length) {
    const g = document.createElement("div");
    g.className = "sfolder";
    g.innerHTML = `<div class="srow plain"><span class="ic">🧩</span><b>구조화 틀</b>
      <span class="sub">${ready.length}</span></div>`;
    for (const f of ready) {
      const el = document.createElement("div");
      el.className = "srow doc inf";
      el.draggable = true;
      el.dataset.node = FMT(f.doc_type);
      el.innerHTML = `<span class="ic">🧩</span>
        <span class="nm">${esc(f.doc_type)}</span>
        ${f.owner && f.owner !== "ui" ? `<span class="pill">${esc(f.owner)}</span>` : ""}`;
      g.appendChild(el);
    }
    box.appendChild(g);
  }

  for (const f of S.folders) {
    const docs = S.docs.filter((d) => d.folder === f.name);
    if (!hit(f.name) && !docs.some((d) => hit(d.name))) continue;
    const bound = S.bind.folders[f.name];
    const mix = kindMix(docs.map((d) => d.doc_id));
    const el = document.createElement("div");
    el.className = "sfolder";
    el.innerHTML = `<div class="srow" draggable="true" data-node="${esc(FOLDER(f.name))}">
        <span class="ic">📁</span><b>${esc(f.name)}</b>
        <span class="sub" title="${esc(mix)}">${docs.length}</span>
        ${bound ? `<span class="pill">🧩 ${esc(bound)}</span>` : ""}
      </div>`;
    for (const d of docs) {
      if (!hit(d.name) && !hit(f.name)) continue;
      el.appendChild(docRow(d, true));
    }
    box.appendChild(el);
  }
  const unfiled = S.docs.filter((d) => !d.folder && hit(d.name));
  if (unfiled.length) {
    const el = document.createElement("div");
    el.className = "sfolder";
    el.innerHTML = `<div class="srow plain"><span class="ic">·</span><b>미분류</b>
      <span class="sub">${unfiled.length}</span></div>`;
    unfiled.forEach((d) => el.appendChild(docRow(d, false)));
    box.appendChild(el);
  }

  box.querySelectorAll("[data-node]").forEach((el) => {
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", el.dataset.node);
      e.dataTransfer.effectAllowed = "copy";
    });
    el.ondblclick = () => dropNode(el.dataset.node);      // 두 번 눌러도 놓인다
  });
}

function docRow(d, inFolder) {
  const el = document.createElement("div");
  const own = S.bind.docs[d.doc_id];
  el.className = "srow doc" + (inFolder ? " inf" : "");
  el.draggable = true;
  el.dataset.node = DOC(d.doc_id);
  el.innerHTML = `<span class="ic">📄</span><span class="nm">${esc(d.name || d.doc_id)}</span>
    ${kindBadge(d.source_kind)}
    ${own ? `<span class="pill warn" title="폴더 연결을 무시하는 예외">🧩 ${esc(own)}</span>` : ""}`;
  return el;
}

function nodeEl(n) {
  const el = document.createElement("div");
  el.className = "node " + kind(n.id);
  el.style.left = `${n.x}px`;
  el.style.top = `${n.y}px`;
  el.dataset.node = n.id;

  if (kind(n.id) === "builtin") {
    // 읽기 전용 — 파일 형식이 정하는 길이라 잇거나 끊을 손잡이를 주지 않는다
    el.innerHTML = `<div class="head"><span class="ic">🏛</span>
        <b>${esc(n.builtin.name)}</b></div>
      <div class="meta">문서 ${n.docs.length} · ${esc(n.builtin.note)}</div>
      <div class="meta dim">파일 형식이 정하는 길 — 손으로 바꿀 수 없습니다</div>`;
    bindNode(el, n);
    return el;
  }
  if (kind(n.id) === "fmt") {
    const uses = Object.entries(S.bind.folders).filter(([, t]) => t === n.fmt.doc_type).length;
    const ex = Object.entries(S.bind.docs).filter(([, t]) => t === n.fmt.doc_type).length;
    // 이 틀이 실제로 어떤 형식의 문서를 자르고 있나 — 섞였으면 그 자체가 신호다
    const mix = kindMix(docsOf(n.fmt.doc_type));
    el.innerHTML = `<div class="head"><span class="ic">🧩</span>
        <b>${esc(n.fmt.doc_type)}</b></div>
      <div class="meta">폴더 ${uses} · 예외 ${ex}
        ${n.fmt.owner === "ui" ? "" : `<span class="pill">${esc(n.fmt.owner || "")}</span>`}</div>
      ${mix ? `<div class="meta dim" title="원본 형식마다 파서가 싣는 신호가 다릅니다">${
        esc(mix)}</div>` : ""}
      <div class="acts">
        <button data-act="apply" ${uses + ex ? "" : "disabled"}
          title="${uses + ex ? "이 틀에 이어진 문서를 이 틀로 다시 해석한다"
                             : "먼저 폴더나 문서를 이어 주세요"}">이 틀로 해석</button>
        ${uses + ex ? "" : `<button data-act="off" class="ghost"
          title="캔버스에서만 치운다 — 틀은 등록부에 남는다">치우기</button>`}
      </div>`;
  } else if (kind(n.id) === "draft") {
    const cnt = (n.draft.folders || []).length + (n.draft.docs || []).length;
    const ids = draftDocs(n.draft);
    const mix = kindMix(ids);
    const mixed = new Set(ids.map(kindOf).filter(Boolean)).size > 1;
    el.innerHTML = `<div class="head"><span class="ic">🧩</span>
        <b contenteditable="true" data-act="rename">${esc(n.draft.name)}</b></div>
      <div class="meta">초안 — 이어 놓은 것 ${cnt}${ids.length ? ` · 문서 ${ids.length}` : ""}</div>
      ${mix ? `<div class="meta ${mixed ? "warn" : "dim"}"
        title="${mixed ? "형식마다 파서가 싣는 신호가 다릅니다 — 실행 결과의 문서별 점수를 보세요"
                       : ""}">${esc(mix)}${mixed ? " · 형식 섞임" : ""}</div>` : ""}
      <div class="acts">
        <button data-act="run" ${cnt ? "" : "disabled"}
          title="${cnt ? "이어진 문서로 마커 체계를 유도해 틀을 만들고, 결과 화면으로 갑니다"
                       : "먼저 폴더나 문서를 이어 주세요"}">구조화 실행하기</button>
        <button data-act="del" class="ghost">버리기</button>
      </div>`;
  } else {
    const isF = kind(n.id) === "folder";
    const k = key(n.id);
    const name = isF ? k : (S.docs.find((d) => d.doc_id === k)?.name || k);
    const sub = isF ? `${S.docs.filter((d) => d.folder === k).length}개 문서`
                    : (S.docs.find((d) => d.doc_id === k)?.folder || "미분류");
    // 연결이 있으면 그 연결이 이 노드를 캔버스에 세운 것이다 — "치우기" 로는 사라지지
    // 않는다. 끊는 손짓만 준다(끊으면 자리도 함께 지운다).
    const builtin = !isF && Object.values(BUILTIN).find(
      (b) => b.match(S.docs.find((d) => d.doc_id === k) || {}));
    const bound = isF ? S.bind.folders[k] : (builtin ? null : S.bind.docs[k]);
    const badge = isF ? "" : kindBadge(kindOf(k));
    const mix = isF ? kindMix(S.docs.filter((d) => d.folder === k).map((d) => d.doc_id)) : "";
    el.innerHTML = `<div class="head"><span class="ic">${isF ? "📁" : "📄"}</span>
        <b>${esc(name)}</b>${badge}</div>
      <div class="meta">${esc(sub)}${mix ? ` · ${esc(mix)}` : ""}${!isF && S.bind.docs[k]
        ? ' · <span class="pill warn">예외</span>' : ""}</div>
      <div class="acts">
        ${bound
          ? `<button data-act="unbind" class="ghost"
               title="'${esc(bound)}' 연결을 끊는다 — 다시 구조를 유도한다">연결 끊기</button>`
          : builtin ? `<span class="sub">🏛 ${esc(builtin.name)}</span>`
          : `<button data-act="off" class="ghost">치우기</button>`}
      </div>
      ${builtin ? "" : `<div class="port" title="여기서 끌어 틀에 놓으면 이어집니다"></div>`}`;
  }
  bindNode(el, n);
  return el;
}

/* ------------------------------------------------------------------ 선 그리기 */
function drawWires(nodes, edges) {
  const svg = $("wires");
  const H = (el) => el?.offsetHeight || 56;
  const els = new Map([...$("nodes").children].map((e) => [e.dataset.node, e]));
  let d = "";
  for (const e of edges) {
    const a = nodes.get(e.from), b = nodes.get(e.to);
    if (!a || !b) continue;
    const x1 = a.x + NODE_W, y1 = a.y + H(els.get(a.id)) / 2;
    const x2 = b.x, y2 = b.y + H(els.get(b.id)) / 2;
    const c = Math.max(40, (x2 - x1) / 2);
    const cls = e.own ? "own" : e.builtin ? "builtin"
      : e.exception ? "exc" : e.firm ? "" : "draftw";
    d += `<path d="M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}"
      class="wire ${cls}"/>`;
  }
  if (S.wire) {
    const a = nodes.get(S.wire.from);
    if (a) {
      const els2 = els.get(a.id);
      const x1 = a.x + NODE_W, y1 = a.y + H(els2) / 2;
      d += `<path d="M${x1},${y1} L${S.wire.x},${S.wire.y}" class="wire live"/>`;
    }
  }
  svg.innerHTML = d;
}

/* ------------------------------------------------------------ 노드 손짓 */
function bindNode(el, n) {
  // 머리를 끌면 자리를 옮긴다 (자리는 서버에 남는다)
  el.querySelector(".head").addEventListener("pointerdown", (e) => {
    if (e.target.isContentEditable) return;
    e.preventDefault();
    const r = $("canvas").getBoundingClientRect();
    S.drag = { id: n.id, dx: e.clientX - r.left - n.x, dy: e.clientY - r.top - n.y };
    el.setPointerCapture(e.pointerId);
  });

  // 고리에서 끌면 선을 긋는다 (출처 노드에만 있다 — 방향은 출처→틀 하나뿐이다)
  el.querySelector(".port")?.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    S.wire = { from: n.id, x: n.x + NODE_W, y: n.y + 28 };
    el.setPointerCapture(e.pointerId);
  });

  el.querySelectorAll("[data-act]").forEach((b) => {
    const act = b.dataset.act;
    if (act === "rename") {
      b.addEventListener("blur", () => {
        const name = b.textContent.trim();
        if (name && name !== n.draft.name) { n.draft.name = name; saveCanvas(); }
        else b.textContent = n.draft.name;
      });
      b.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); b.blur(); } });
      return;
    }
    b.onclick = (e) => { e.stopPropagation(); nodeAction(act, n); };
  });
}

async function nodeAction(act, n) {
  if (act === "off") {                       // 캔버스에서만 치운다 (연결은 건드리지 않는다)
    delete S.pos[n.id];
    // 초안에 이어 둔 것도 함께 뗀다 — 선이 남으면 치운 게 아니다
    for (const d of S.drafts) {
      d.folders = (d.folders || []).filter((x) => FOLDER(x) !== n.id);
      d.docs = (d.docs || []).filter((x) => DOC(x) !== n.id);
    }
    await saveCanvas();
    render();
    return;
  }
  if (act === "unbind") return unbindNode(n.id);
  if (act === "del") {
    S.drafts = S.drafts.filter((d) => `draft:${d.id}` !== n.id);
    delete S.pos[n.id];
    await saveCanvas();
    render();
    return;
  }
  if (act === "run") return runDraft(n.draft);
  if (act === "apply") return applyFormat(n.fmt.doc_type);
}

async function unbindNode(id) {
  const scope = kind(id) === "folder" ? "folder" : "doc";
  const r = await fetch("/v1/formats/bindings", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, key: key(id), doc_type: null }) });
  if (!r.ok) { banner(await errText(r), "err"); return; }
  // 초안에 이어 둔 것도 함께 끊고 자리도 지운다 — 끊었는데 노드가 남아 있으면
  // "아직 이어져 있나" 로 읽힌다
  for (const d of S.drafts) {
    d.folders = (d.folders || []).filter((x) => FOLDER(x) !== id);
    d.docs = (d.docs || []).filter((x) => DOC(x) !== id);
  }
  delete S.pos[id];
  await saveCanvas();
  await load();
  banner("연결을 끊었습니다 — 다시 해석하면 문서에서 구조를 유도합니다");
}

/* 이었다 = "이 폴더(문서)는 이 틀을 쓴다" */
async function connect(fromId, toId) {
  if (!["folder", "doc"].includes(kind(fromId))) return;            // 방향은 하나뿐
  if (kind(toId) === "builtin") {
    banner("법령 XML 태그는 파일 형식이 정하는 길이라 손으로 이을 수 없습니다", "err");
    return;
  }
  if (kind(toId) === "draft") {
    const d = S.drafts.find((x) => `draft:${x.id}` === toId);
    if (!d) return;
    const list = kind(fromId) === "folder" ? (d.folders ||= []) : (d.docs ||= []);
    if (!list.includes(key(fromId))) list.push(key(fromId));
    await saveCanvas();
    render();
    return;
  }
  if (kind(toId) !== "fmt") return;
  const scope = kind(fromId) === "folder" ? "folder" : "doc";
  const r = await fetch("/v1/formats/bindings", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, key: key(fromId), doc_type: key(toId) }) });
  if (!r.ok) { banner(await errText(r), "err"); return; }
  await load();
  banner(scope === "folder"
    ? `'${key(fromId)}' 폴더를 '${key(toId)}' 틀에 이었습니다 — 이 틀로 해석을 눌러 적용하세요`
    : `문서 하나를 '${key(toId)}' 틀에 예외로 이었습니다 (폴더 연결보다 우선)`);
}

/* -------------------------------------------------------------- 실행·적용 */
async function runDraft(draft) {
  const name = (draft.name || "").trim();
  if (!name) { banner("틀 이름을 먼저 적어 주세요 (노드 제목을 눌러 고칩니다)", "err"); return; }
  if (S.busy.has(name)) return;
  S.busy.add(name);
  banner(`'${name}' — 이어진 문서로 마커 체계를 유도하는 중…`);

  const r = await fetch("/v1/formats/compile", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doc_type: name, folders: draft.folders || [], doc_ids: draft.docs || [],
      use_llm: $("useLlm").checked, overwrite: false, bind: true }) });
  S.busy.delete(name);
  if (!r.ok) { banner(await errText(r), "err"); return; }
  const j = await r.json();

  // 초안은 진짜 틀이 됐다 — 자리를 물려주고 초안을 지운다
  S.pos[FMT(name)] = S.pos[`draft:${draft.id}`] || [COL_FMT, 30];
  delete S.pos[`draft:${draft.id}`];
  S.drafts = S.drafts.filter((d) => d.id !== draft.id);
  await saveCanvas();
  await load();

  // 문서마다 **원본 형식과 함께** 점수를 보여준다 — "hwp 만 낮다" 가 여기서 읽힌다
  const rows = j.applied.map((a) =>
    `${a.name}(${KIND[a.kind]?.label || a.kind}) ${Math.round(a.score * 100)}%`).join(" · ");
  const skipped = (j.skipped || []).length
    ? ` · 제외 ${j.skipped.length}건(${j.skipped[0].reason})` : "";
  banner(`'${name}' 틀을 만들었습니다 — 마커 ${j.markers.length}개 · ${rows}`
    + (j.holdout ? " (홀드아웃 검증)" : " (샘플이 적어 신뢰도 낮음)") + skipped
    + (j.warnings?.length ? `\n! ${j.warnings[0]}` : ""));
  // 만든 즉시 그 틀로 다시 해석하고 결과 화면으로 넘긴다 — 만든 사람이 보고 싶은 것은
  // 형식 파일이 아니라 **잘린 결과**다.
  await applyFormat(name, j.doc_ids);
}

async function applyFormat(docType, ids) {
  const targets = ids || docsOf(docType);
  if (!targets.length) { banner("이 틀에 이어진 문서가 없습니다", "err"); return; }
  banner(`'${docType}' 틀로 ${targets.length}개 문서를 다시 해석하는 중…`);
  const done = [];
  for (const id of targets) {
    const r = await fetch(`/v1/structure/${encodeURIComponent(id)}/reinterpret`,
                          { method: "POST" });
    if (r.ok) done.push({ id, ...(await r.json()) });
    else banner(await errText(r), "err");
  }
  await load();
  if (!done.length) return;
  const avg = done.reduce((a, d) => a + (d.score || 0), 0) / done.length;
  banner(`'${docType}' 로 ${done.length}개를 다시 해석했습니다 — 평균 부합 `
    + `${Math.round(avg * 100)}% · 결과 화면으로 넘어갑니다`);
  setTimeout(() => {
    location.href = `/structure/?doc=${encodeURIComponent(done[0].id)}`;
  }, 900);
}

/* 초안에 이어 둔 것이 실제로 가리키는 문서들 (폴더는 안의 문서로 펼친다).
 * 법령 XML 은 태그가 곧 구조라 샘플이 될 수 없다 — 서버도 같은 이유로 건너뛴다. */
function draftDocs(draft) {
  const ids = S.docs.filter((d) => (draft.folders || []).includes(d.folder))
    .map((d) => d.doc_id);
  for (const i of draft.docs || []) if (!ids.includes(i)) ids.push(i);
  return ids.filter((i) => kindOf(i) !== "lawxml");
}

/* 이 틀에 걸린 문서 전부 — 폴더로 걸린 것 + 예외로 걸린 것 */
function docsOf(docType) {
  const folders = Object.entries(S.bind.folders)
    .filter(([, t]) => t === docType).map(([n]) => n);
  const ids = S.docs.filter((d) => folders.includes(d.folder)).map((d) => d.doc_id);
  for (const [id, t] of Object.entries(S.bind.docs))
    if (t === docType && !ids.includes(id)) ids.push(id);
  return ids;
}

/* --------------------------------------------------------------- 캔버스 손짓 */
function dropNode(nodeId, x, y) {
  if (!S.pos[nodeId]) {
    const n = model().nodes.size;
    S.pos[nodeId] = [x ?? COL_SRC, y ?? 30 + (n % 8) * GAP_Y];
  } else if (x != null) {
    S.pos[nodeId] = [x, y];
  }
  saveCanvas();
  render();
}

const cv = $("canvas");
cv.addEventListener("dragover", (e) => { e.preventDefault(); cv.classList.add("over"); });
cv.addEventListener("dragleave", () => cv.classList.remove("over"));
cv.addEventListener("drop", (e) => {
  e.preventDefault();
  cv.classList.remove("over");
  const id = e.dataTransfer.getData("text/plain");
  if (!id) return;
  const r = cv.getBoundingClientRect();
  dropNode(id, Math.round(e.clientX - r.left - NODE_W / 2),
           Math.round(e.clientY - r.top - 24));
});

cv.addEventListener("pointermove", (e) => {
  const r = cv.getBoundingClientRect();
  if (S.drag) {
    const x = Math.max(0, Math.round(e.clientX - r.left - S.drag.dx));
    const y = Math.max(0, Math.round(e.clientY - r.top - S.drag.dy));
    S.pos[S.drag.id] = [x, y];
    const el = cv.querySelector(`[data-node="${CSS.escape(S.drag.id)}"]`);
    if (el) { el.style.left = `${x}px`; el.style.top = `${y}px`; }
    const { nodes, edges } = model();
    layout(nodes);
    drawWires(nodes, edges);
  } else if (S.wire) {
    S.wire.x = e.clientX - r.left;
    S.wire.y = e.clientY - r.top;
    const { nodes, edges } = model();
    layout(nodes);
    drawWires(nodes, edges);
    const over = document.elementFromPoint(e.clientX, e.clientY)?.closest(".node");
    cv.querySelectorAll(".node").forEach((n) => n.classList.toggle(
      "target", n === over && ["fmt", "draft"].includes(kind(n.dataset.node))));
  }
});

cv.addEventListener("pointerup", async (e) => {
  if (S.drag) { S.drag = null; saveCanvas(); return; }
  if (!S.wire) return;
  const from = S.wire.from;
  S.wire = null;
  const target = document.elementFromPoint(e.clientX, e.clientY)?.closest(".node");
  cv.querySelectorAll(".node").forEach((n) => n.classList.remove("target"));
  if (target && target.dataset.node !== from) await connect(from, target.dataset.node);
  else render();
});

/* ------------------------------------------------------------------ 도구 */
$("newFormat").onclick = async () => {
  const id = `d${Date.now().toString(36)}`;
  const n = S.drafts.length;
  S.drafts.push({ id, name: `새 구조화 ${n + 1}`, folders: [], docs: [] });
  S.pos[`draft:${id}`] = [COL_FMT, 30 + n * GAP_Y * 1.6];
  await saveCanvas();
  render();
  banner("초안을 놓았습니다 — 왼쪽에서 폴더·문서를 끌어다 잇고 '구조화 실행하기' 를 누르세요");
};

$("tidy").onclick = async () => {
  S.pos = {};
  await saveCanvas();
  render();
};

/* 폴더 만들기 — 연결의 기본 단위라서 이 화면에서도 만들 수 있어야 한다.
 * (문서·데이터 화면으로 갔다 오면 이어 놓던 흐름이 끊긴다.) */
$("newFolder").onclick = async () => {
  const nv = prompt("새 폴더 이름 (예: 법령문서)\n"
    + "만들면 캔버스에 놓입니다 — 틀에 이으면 이 폴더의 문서가 그 틀로 잘립니다");
  if (nv === null) return;
  const name = nv.trim();
  if (!name) return;
  const r = await fetch("/v1/structure/folders", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }) });
  if (!r.ok) { banner(await errText(r), "err"); return; }
  S.pos[FOLDER(name)] = [COL_FOLDER, 30 + S.folders.length * GAP_Y];
  await saveCanvas();
  await load();
  banner(`'${name}' 폴더를 만들었습니다 — 문서·데이터 화면에서 문서를 넣거나, `
    + "여기서 틀에 이어 두면 앞으로 들어올 문서에 그 틀이 적용됩니다");
};

$("q").oninput = (e) => { S.q = e.target.value.trim(); renderSources(); };

load();
