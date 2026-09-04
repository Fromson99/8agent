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
  docs: [], folders: [], formats: [], orphans: [],
  bind: { folders: {}, docs: {} },
  pos: {}, drafts: [], rev: 0,
  q: "",
  drag: null,            // 노드 옮기기
  wire: null,            // 선 긋는 중 {from, x, y}
  busy: new Set(),       // 실행 중인 틀 (버튼 잠금)
  cancel: false,         // 긴 작업 중단 요청
  sel: null,             // 고른 노드 — 오른쪽 상세가 이것을 그린다
  open: new Set(),       // 펼친 폴더 (안의 문서를 캔버스에 세운다)
  rules: new Map(),      // doc_type → 규칙 (한 번 받아 두고 다시 안 받는다)
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
const docOf = (docId) => S.docs.find((d) => d.doc_id === docId);
const kindOf = (docId) => docOf(docId)?.source_kind || "";

/* 문서 상태 배지 — 낡음(다시 해석 필요) · 격리(틀에 미달) · 파싱 캐시 없음(느림) */
function stateBadges(d) {
  if (!d) return "";
  const out = [];
  if (d.stale)
    out.push(`<span class="pill warn" title="${esc(d.stale_reason || "")}">↻ 다시 해석</span>`);
  if (d.passed === false)
    out.push(`<span class="pill bad" title="적합도 ${Math.round((d.score || 0) * 100)}% — 임계 미만">⚠ 격리</span>`);
  if (d.parse_cached === false)
    out.push(`<span class="pill" title="파싱 캐시가 없어 다시 해석이 분 단위입니다 — 미리 만들어 두면 빨라집니다">파싱 캐시 없음</span>`);
  return out.join("");
}

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
    S.orphans = fmts.value.orphans || [];
    for (const [k, note] of Object.entries(fmts.value.kind_signals || {}))
      if (KIND[k]) KIND[k].note = note;     // 설명의 정본은 서버다
  }
  if (canvas.status === "fulfilled") {
    S.pos = canvas.value.pos || {};
    S.drafts = canvas.value.drafts || [];
    S.rev = canvas.value.rev || 0;
    if (canvas.value.open) S.open = new Set(canvas.value.open);
  }
  render();
  if (S.orphans.length)
    banner("가리키던 틀이 사라진 연결이 있습니다: "
      + S.orphans.map((o) => `${o.key} → ${o.doc_type}`).join(", ")
      + " — 그 문서는 지금 구조를 유도합니다", "err");
}

/* 캔버스 저장 — rev 로 남의 저장을 덮어쓰지 않는다(409 면 새로 읽어 온다). */
async function saveCanvas() {
  const r = await fetch("/v1/formats/canvas", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pos: S.pos, drafts: S.drafts, rev: S.rev,
                           open: [...S.open] }) });
  if (r.status === 409) {
    banner("다른 화면이 먼저 저장했습니다 — 최신 상태를 다시 불러옵니다", "err");
    await load();
    return false;
  }
  if (r.ok) S.rev = (await r.json()).rev;
  return r.ok;
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
  // 펼친 폴더 — 안의 문서를 캔버스에 세운다. 기본은 접힘이다: 폴더가 연결 단위라
  // 문서를 늘 펼치면 캔버스가 문서 목록이 되고 "폴더 → 틀" 이 안 보인다.
  for (const name of S.open) {
    if (!S.folders.some((f) => f.name === name)) continue;
    add(FOLDER(name), {});
    for (const d of S.docs.filter((x) => x.folder === name)) add(DOC(d.doc_id), {});
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
    // 슬롯은 **자리 유무와 무관하게** 센다. 예전에는 자리 없는 노드만 셌는데,
    // 드래그를 시작하면 그 노드가 자리를 갖게 되어 슬롯 하나가 사라지고 같은 열의
    // 나머지 노드가 통째로 한 칸씩 튀어 올랐다(순간이동의 정체).
    const slot = seq[col]++;
    const p = S.pos[n.id];
    n.x = p ? p[0] : (COL_OF[k] ?? COL_FOLDER);
    n.y = p ? p[1] : 30 + slot * GAP_Y;
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
    // 목록에서도 접힌다. 찾는 중일 때는 맞은 문서를 감추면 안 되므로 강제로 편다.
    const open = S.open.has(f.name) || !!q;
    const el = document.createElement("div");
    el.className = "sfolder";
    el.innerHTML = `<div class="srow" draggable="true" data-node="${esc(FOLDER(f.name))}">
        <button class="caret" data-fold="${esc(f.name)}"
          title="${open ? "접기" : "펼치기"}">${docs.length ? (open ? "▾" : "▸") : "·"}</button>
        <span class="ic">📁</span><b>${esc(f.name)}</b>
        <span class="sub" title="${esc(mix)}">${docs.length}</span>
        ${bound ? `<span class="pill">🧩 ${esc(bound)}</span>` : ""}
      </div>`;
    if (open) {
      for (const d of docs) {
        if (!hit(d.name) && !hit(f.name)) continue;
        el.appendChild(docRow(d, true));
      }
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
    el.onclick = (e) => {                                 // 한 번 누르면 상세만 본다
      if (e.target.closest("[data-fold]")) return;
      if (model().nodes.has(el.dataset.node)) select(el.dataset.node);
    };
  });
  box.querySelectorAll("[data-fold]").forEach((b) => {
    b.onclick = async (e) => {
      e.stopPropagation();
      const name = b.dataset.fold;
      S.open.has(name) ? S.open.delete(name) : S.open.add(name);
      await saveCanvas();
      render();
    };
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
    const ids = docsOf(n.fmt.doc_type);
    const mix = kindMix(ids);
    // 이 틀이 실제로 어떤 상태인가 — 낡음(다시 해석 필요)과 격리(미달)는 연결이
    // 맞는지 판단할 유일한 근거다. 폴더 노드 하나로 뭉뚱그리면 이게 안 보인다.
    const stale = ids.filter((i) => docOf(i)?.stale).length;
    const failed = ids.filter((i) => docOf(i) && docOf(i).passed === false).length;
    el.innerHTML = `<div class="head"><span class="ic">🧩</span>
        <b>${esc(n.fmt.doc_type)}</b></div>
      <div class="meta">폴더 ${uses} · 예외 ${ex} · 문서 ${ids.length}
        ${n.fmt.owner === "ui" ? "" : `<span class="pill">${esc(n.fmt.owner || "")}</span>`}</div>
      ${mix ? `<div class="meta dim" title="원본 형식마다 파서가 싣는 신호가 다릅니다">${
        esc(mix)}</div>` : ""}
      ${stale ? `<div class="meta warn" title="연결이나 틀이 바뀌었습니다 — 다시 해석해야 반영됩니다">
        ↻ 다시 해석 필요 ${stale}</div>` : ""}
      ${failed ? `<div class="meta bad" title="이 틀과 부합이 임계 미만입니다 — 다른 양식이거나 틀이 안 맞습니다">
        ⚠ 격리 ${failed}</div>` : ""}
      <div class="acts">
        <button data-act="apply" ${uses + ex ? "" : "disabled"}
          title="${uses + ex ? "이 틀에 이어진 문서를 이 틀로 다시 해석한다"
                             : "먼저 폴더나 문서를 이어 주세요"}">이 틀로 해석</button>
        ${n.fmt.owner === "ui" ? `<button data-act="drop" class="ghost"
          title="이 틀을 등록부에서 지운다 — 이어진 문서는 다시 구조를 유도한다">틀 삭제</button>` : ""}
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
    const state = isF
      ? (() => {                            // 폴더는 안의 문서 상태를 합쳐 보여준다
          const inner = S.docs.filter((d) => d.folder === k);
          const st = inner.filter((d) => d.stale).length;
          const fa = inner.filter((d) => d.passed === false).length;
          const wp = inner.filter((d) => d.parse_cached === false).length;
          return (st ? `<span class="pill warn">↻ ${st}</span>` : "")
            + (fa ? `<span class="pill bad">⚠ ${fa}</span>` : "")
            + (wp ? `<span class="pill">캐시없음 ${wp}</span>` : "");
        })()
      : stateBadges(docOf(k));
    // 폴더는 접힘이 기본 — 펼치면 안의 문서가 캔버스에 서고 소속 선으로 이어진다
    const caret = isF && S.docs.some((d) => d.folder === k)
      ? `<button class="caret" data-act="fold"
           title="${S.open.has(k) ? "접기 — 안의 문서를 감춘다" : "펼치기 — 안의 문서를 세운다"}"
         >${S.open.has(k) ? "▾" : "▸"}</button>` : "";
    el.innerHTML = `<div class="head">${caret}<span class="ic">${isF ? "📁" : "📄"}</span>
        <b>${esc(name)}</b>${badge}</div>
      <div class="meta">${esc(sub)}${mix ? ` · ${esc(mix)}` : ""}${!isF && S.bind.docs[k]
        ? ' · <span class="pill warn">예외</span>' : ""}</div>
      ${state ? `<div class="meta">${state}</div>` : ""}
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
  if (S.sel === n.id) el.classList.add("sel");
  // 머리를 끌면 자리를 옮기고, 움직이지 않고 떼면 **고른 것**이다(상세가 뜬다).
  el.querySelector(".head").addEventListener("pointerdown", (e) => {
    if (e.target.isContentEditable || e.target.closest("[data-act]")) return;
    e.preventDefault();
    const r = $("canvas").getBoundingClientRect();
    S.drag = { id: n.id, dx: e.clientX - r.left - n.x, dy: e.clientY - r.top - n.y,
               moved: false };
    el.setPointerCapture(e.pointerId);
  });
  // 몸통 아무 데나 눌러도 고를 수 있다 — 머리만 눌러야 하면 손이 아프다
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-act]") || e.target.isContentEditable) return;
    select(n.id);
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
  if (act === "fold") {
    const name = key(n.id);
    S.open.has(name) ? S.open.delete(name) : S.open.add(name);
    await saveCanvas();
    render();
    if (S.sel === n.id) renderDetail();
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
  if (act === "drop") return dropFormat(n.fmt.doc_type);
}

async function dropFormat(docType) {
  const ids = docsOf(docType);
  if (!confirm(`틀 '${docType}' 을 지웁니다.\n`
    + (ids.length ? `이어진 문서 ${ids.length}건의 연결이 함께 풀리고, 다시 해석하면 `
                    + "문서에서 구조를 유도합니다.\n" : "")
    + "형식 파일과 등록부 항목이 지워집니다 (되돌릴 수 없습니다).")) return;
  const r = await fetch(`/v1/formats/${encodeURIComponent(docType)}?force=true`,
                        { method: "DELETE" });
  if (!r.ok) { banner(await errText(r), "err"); return; }
  const j = await r.json();
  await load();
  banner(`틀 '${docType}' 을 지웠습니다`
    + (j.unbound?.length ? ` — 연결 ${j.unbound.length}건도 함께 풀었습니다 `
        + "(그 문서는 '다시 해석' 해야 유도 결과로 돌아갑니다)" : ""));
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
  S.cancel = false;
  // 컴파일 자체는 싸다 — 비싼 것은 샘플 파싱이다. 캐시를 먼저 만들어 두면 컴파일 요청이
  // 몇 초로 끝나고, 오래 걸리는 구간에서 진행률과 취소가 보인다.
  if (!await warmUp(draftDocs(draft))) {
    S.busy.delete(name); progressDone();
    banner("파싱을 멈췄습니다 — 아무 틀도 만들지 않았습니다", "err");
    return;
  }
  progress(`'${name}' — 이어진 문서로 마커 체계를 유도하는 중…`);

  const r = await fetch("/v1/formats/compile", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doc_type: name, folders: draft.folders || [], doc_ids: draft.docs || [],
      use_llm: $("useLlm").checked, overwrite: false, bind: true }) });
  S.busy.delete(name);
  progressDone();
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

/* 긴 작업은 **한 건씩** 돌리고 진행률을 보인다 — 서버를 한 요청에 몇 분씩 묶어 두면
 * 프록시 시한에 걸려 통째로 날아가고, 어디까지 됐는지도 알 수 없다. 취소도 받는다. */
function progress(text) {
  let el = $("progress");
  if (!el) {
    el = document.createElement("div");
    el.id = "progress";
    el.className = "progress";
    document.body.appendChild(el);
  }
  el.innerHTML = `<span class="spin"></span><span>${esc(text)}</span>
    <button id="cancelJob">취소</button>`;
  $("cancelJob").onclick = () => { S.cancel = true; progress("취소하는 중…"); };
  return el;
}
const progressDone = () => $("progress")?.remove();

/* 파싱 캐시 만들기 — 캐시가 없는 문서만. 여기가 유일하게 분 단위인 구간이다(docling). */
async function warmUp(ids) {
  const cold = ids.filter((i) => docOf(i)?.parse_cached === false);
  if (!cold.length) return true;
  for (const [i, id] of cold.entries()) {
    if (S.cancel) return false;
    progress(`파싱 캐시 ${i + 1}/${cold.length} — ${docOf(id)?.name || id}`
      + " (첫 문서는 docling 모델 적재로 오래 걸립니다)");
    const r = await fetch(`/v1/structure/${encodeURIComponent(id)}/parse`,
                          { method: "POST" });
    if (!r.ok) { banner(await errText(r), "err"); return false; }
  }
  return true;
}

async function applyFormat(docType, ids) {
  const targets = ids || docsOf(docType);
  if (!targets.length) { banner("이 틀에 이어진 문서가 없습니다", "err"); return; }
  S.cancel = false;
  const done = [];
  try {
    if (!await warmUp(targets)) { banner("파싱을 멈췄습니다", "err"); return; }
    for (const [i, id] of targets.entries()) {
      if (S.cancel) break;
      progress(`'${docType}' 로 다시 해석 ${i + 1}/${targets.length} — ${docOf(id)?.name || id}`);
      const r = await fetch(`/v1/structure/${encodeURIComponent(id)}/reinterpret`,
                            { method: "POST" });
      if (r.ok) done.push({ id, ...(await r.json()) });
      else banner(await errText(r), "err");
    }
  } finally {
    progressDone();
    await load();
  }
  if (!done.length) return;
  const avg = done.reduce((a, d) => a + (d.score || 0), 0) / done.length;
  const failed = done.filter((d) => d.passed === false);
  banner(`'${docType}' 로 ${done.length}개를 다시 해석했습니다 — 평균 부합 `
    + `${Math.round(avg * 100)}%`
    + (failed.length ? ` · ⚠ 격리 ${failed.length}건(${failed.map((f) => f.name).join(", ")})`
                     : "")
    + (S.cancel ? " (취소로 일부만 처리)" : " · 결과 화면으로 넘어갑니다"));
  if (S.cancel) return;
  setTimeout(() => {
    location.href = `/structure/?doc=${encodeURIComponent(done[0].id)}`;
  }, 1200);
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

/* ------------------------------------------------------------------ 상세 패널
 *
 * 노드를 눌렀을 때 "이건 무엇이고 무엇으로 잘리나" 의 답이 없으면 캔버스는 그림일
 * 뿐이다. 특히 틀과 내장 경로는 **규칙 자체**(마커 정규식 / 태그 계층)를 보여 준다 —
 * 규칙을 볼 수 없으면 결과가 이상할 때 원인을 짚을 데가 없다.
 */
async function select(id) {
  // 같은 노드를 다시 고르면 아무 일도 하지 않는다 — 머리를 누르면 pointerup 과
  // click 이 둘 다 오는데, 그때마다 다시 그리면 화면이 한 번 깜빡인다.
  if (S.sel === id) return;
  S.sel = id;
  render();
  await renderDetail();
}

async function rulesOf(docType) {
  if (S.rules.has(docType)) return S.rules.get(docType);
  const r = await fetch(`/v1/formats/${encodeURIComponent(docType)}/rules`);
  const j = r.ok ? await r.json() : { error: await errText(r) };
  S.rules.set(docType, j);
  return j;
}

const kv = (rows) => `<div class="kv">` + rows.filter((x) => x[1] != null && x[1] !== "")
  .map(([k, v]) => `<span>${esc(k)}</span><b>${v}</b>`).join("") + `</div>`;

function docLine(id) {
  const d = docOf(id);
  if (!d) return `<div class="dim">${esc(id)} (없음)</div>`;
  return `<a href="/structure/?doc=${encodeURIComponent(id)}" title="검수 화면에서 열기">
    ${esc(d.name || id)}</a> ${kindBadge(d.source_kind)}${stateBadges(d)}`;
}

async function renderDetail() {
  const box = $("detail");
  const id = S.sel;
  if (!id) {
    $("detailKind").textContent = "";
    box.innerHTML = `<div class="empty"><p class="dim">노드를 누르면 여기에 뜹니다.</p></div>`;
    return;
  }
  const k = kind(id), key0 = key(id);
  $("detailKind").textContent =
    { folder: "폴더", doc: "문서", fmt: "구조화 틀", draft: "초안", builtin: "내장" }[k] || "";

  if (k === "folder") {
    const inner = S.docs.filter((d) => d.folder === key0);
    const bound = S.bind.folders[key0];
    box.innerHTML = `<h4>📁 ${esc(key0)}</h4>`
      + kv([["문서", inner.length], ["형식 분포", esc(kindMix(inner.map((d) => d.doc_id)))],
            ["구조화 틀", bound ? `🧩 ${esc(bound)}` : "<span class='dim'>연결 없음 — 문서마다 유도</span>"],
            ["다시 해석 필요", inner.filter((d) => d.stale).length || null],
            ["격리", inner.filter((d) => d.passed === false).length || null],
            ["파싱 캐시 없음", inner.filter((d) => d.parse_cached === false).length || null]])
      + `<h4>든 문서</h4><div class="dlist">`
      + (inner.map((d) => `<div>${docLine(d.doc_id)}</div>`).join("")
         || `<div class="dim">비어 있습니다</div>`) + `</div>`
      + `<div class="dacts">
           <button data-d="toggle">${S.open.has(key0) ? "캔버스에서 접기" : "캔버스에 펼치기"}</button>
           ${bound ? `<button data-d="apply">이 틀로 해석</button>
                      <button data-d="unbind" class="ghost">연결 끊기</button>` : ""}
         </div>`;
  } else if (k === "doc") {
    const d = docOf(key0);
    if (!d) { box.innerHTML = `<div class="dim">문서가 없습니다</div>`; return; }
    const own = S.bind.docs[key0];
    const via = own ? `🧩 ${esc(own)} <span class="pill warn">예외</span>`
      : (d.folder && S.bind.folders[d.folder])
        ? `🧩 ${esc(S.bind.folders[d.folder])} <span class="dim">(폴더 ${esc(d.folder)} 를 따라)</span>`
        : `<span class="dim">연결 없음 — 문서에서 구조를 유도</span>`;
    box.innerHTML = `<h4>📄 ${esc(d.name || key0)}</h4>`
      + kv([["원본 형식", `${kindBadge(d.source_kind)} <span class="dim">${
              esc(KIND[d.source_kind]?.note || "")}</span>`],
            ["폴더", esc(d.folder || "미분류")],
            ["구조화", via],
            ["잘린 방식", esc(d.structured_by || "")],
            ["적합도", d.score == null ? null
              : `${Math.round(d.score * 100)}% <span class="pill ${d.passed ? "ok" : "bad"}">${
                  d.passed ? "통과" : "격리"}</span>`],
            ["쪽", d.pages], ["파싱 캐시", d.parse_cached ? "있음" : "없음 — 다시 해석이 느립니다"],
            ["갱신", esc((d.at || "").replace("T", " ").slice(0, 16))],
            ["doc_id", `<span class="dim">${esc(key0)}</span>`]])
      + (d.stale ? `<h4>다시 해석 필요</h4><div class="rule"><div class="why">${
          esc(d.stale_reason || "")}</div></div>` : "")
      + `<div class="dacts">
           <a class="navlink" href="/structure/?doc=${encodeURIComponent(key0)}">검수 화면 →</a>
           <button data-d="warm">파싱 캐시 만들기</button>
           <button data-d="reinterpret">다시 해석</button>
           ${own ? `<button data-d="unbind" class="ghost">예외 연결 끊기</button>` : ""}
         </div>`;
  } else if (k === "builtin") {
    box.innerHTML = `<h4>🏛 불러오는 중…</h4>`;
    const r = await fetch(`/v1/formats/builtin/${encodeURIComponent(key0)}`);
    if (!r.ok) { box.innerHTML = `<div class="dim">${esc(await errText(r))}</div>`; return; }
    const j = await r.json();
    const mine = S.docs.filter((d) => d.source_kind === "lawxml");
    box.innerHTML = `<h4>🏛 ${esc(j.name)}</h4>`
      + kv([["문서", mine.length], ["판정", j.deterministic ? "결정론 (추론 0)" : "추론"],
            ["적합도", j.fitness]])
      + `<div class="why" style="color:var(--dim);margin-top:6px">${esc(j.note)}</div>`
      + `<h4>규칙 — 태그가 곧 구역</h4>`
      + `<div class="rule"><div class="top"><b>계층 순서</b></div>
           <code>${j.order.join(" › ")}</code>
           <div class="why">문서에 없는 종류는 건너뛰고, 있는 것끼리 이 순서로 레벨을 받습니다</div></div>`
      + j.rules.map((x) => `<div class="rule"><div class="top">
            <span class="lv">태그</span><b>${esc(x.tag)}</b>
            <span class="dim" style="margin-left:auto">${esc(x.family)}</span></div></div>`).join("")
      + `<h4>알아둘 것</h4>` + j.notes.map((n) =>
          `<div class="rule"><div class="why">${esc(n)}</div></div>`).join("")
      + `<h4>이 경로로 잘린 문서</h4><div class="dlist">`
      + mine.map((d) => `<div>${docLine(d.doc_id)}</div>`).join("") + `</div>`;
  } else if (k === "draft") {
    const d = S.drafts.find((x) => `draft:${x.id}` === id);
    if (!d) { box.innerHTML = `<div class="dim">초안이 없습니다</div>`; return; }
    const ids = draftDocs(d);
    box.innerHTML = `<h4>🧩 ${esc(d.name)} <span class="dim">(초안)</span></h4>`
      + kv([["이어 둔 폴더", (d.folders || []).map(esc).join(", ")],
            ["이어 둔 문서", (d.docs || []).length || null],
            ["샘플 문서", ids.length], ["형식 분포", esc(kindMix(ids))]])
      + `<div class="why" style="color:var(--dim);margin-top:6px">
           아직 아무 일도 일어나지 않았습니다 — 실행해야 마커 체계를 유도해 틀이 만들어집니다.</div>`
      + `<h4>샘플</h4><div class="dlist">`
      + (ids.map((i) => `<div>${docLine(i)}</div>`).join("") || `<div class="dim">없음</div>`)
      + `</div><div class="dacts"><button data-d="run" ${ids.length ? "" : "disabled"}>구조화 실행하기</button></div>`;
  } else if (k === "fmt") {
    box.innerHTML = `<h4>🧩 ${esc(key0)}</h4><div class="dim">규칙을 불러오는 중…</div>`;
    const j = await rulesOf(key0);
    if (j.error) { box.innerHTML = `<div class="dim">${esc(j.error)}</div>`; return; }
    const ids = docsOf(key0);
    box.innerHTML = `<h4>🧩 ${esc(j.doc_type)}</h4>`
      + kv([["만든 이", esc(j.owner || "")], ["버전", `v${j.format_version}`],
            ["신뢰도", esc(j.confidence || "")],
            ["게이트 임계", `${Math.round(j.threshold * 100)}%`],
            ["파서", esc(j.parser || "")],
            ["형식 파일", `<span class="dim">${esc(j.format)}</span>`],
            ["용어집", j.glossary ? `<span class="dim">${esc(j.glossary)}</span>`
                                  : "<span class='dim'>전역 용어집</span>"],
            ["유도에 쓴 샘플", (j.compiled_from || []).map(esc).join(", ")],
            ["문서", ids.length], ["형식 분포", esc(kindMix(ids))]])
      + (j.hierarchy?.length ? `<h4>계층</h4><div class="rule"><code>${
          j.hierarchy.map(esc).join(" › ")}</code></div>` : "")
      + `<h4>규칙 — 마커 ${j.regex_markers.length}개 <button class="mini" data-d="addmk"
             title="새 마커를 더한다">＋</button></h4>`
      + j.regex_markers.map((m) => `<div class="rule" data-mk="${esc(m.id)}">
          <div class="top"><span class="lv">L${m.level}</span><b>${esc(m.id)}</b>
            ${m.require_heading ? `<span class="pill warn"
              title="제목 위치에서만 인정 — 제목 신호가 없는 HWP 에서는 발화하지 않습니다">제목 필요</span>` : ""}
            ${m.parent ? `<span class="dim">아래: ${esc(m.parent)}</span>` : ""}
            <button class="mini" data-d="editmk" data-id="${esc(m.id)}"
              style="margin-left:auto" title="이 마커의 정규식·층을 고친다">고치기</button>
            <button class="mini" data-d="delmk" data-id="${esc(m.id)}"
              title="이 마커를 지운다">✕</button>
          </div><code>${esc(m.pattern)}</code>
          ${m.label ? `<div class="why">이름표 ${esc(m.label)}${
            m.groups?.length ? ` · 캡처 ${m.groups.map(esc).join(", ")}` : ""}</div>` : ""}
        </div>`).join("")
      + (j.term_markers.length ? `<h4>용어형 마커 ${j.term_markers.length}개</h4>`
          + j.term_markers.map((t) => `<div class="rule"><div class="top">
              <span class="lv">L${t.level}</span><b>${esc(t.term)}</b>
              ${t.under ? `<span class="dim" style="margin-left:auto">${esc(t.under)} 아래</span>` : ""}
            </div><div class="why">제목 위치에 이 용어가 오면 구역을 엽니다(정규식 없음)</div></div>`).join("")
          : "")
      + kv([["기본 구역", esc(j.default_section || "")]])
      + `<h4>이 틀에 걸린 것</h4><div class="dlist">`
      + j.bound_folders.map((f) => `<div>📁 ${esc(f)}</div>`).join("")
      + ids.map((i) => `<div>${docLine(i)}</div>`).join("")
      + (ids.length || j.bound_folders.length ? "" : `<div class="dim">아직 없음</div>`)
      + `</div>
         <div class="dacts">
           <button data-d="apply" ${ids.length ? "" : "disabled"}>이 틀로 해석</button>
           ${j.owner === "ui" ? `<button data-d="drop" class="ghost">틀 삭제</button>` : ""}
         </div>`;
  }

  box.querySelectorAll("[data-d]").forEach((b) => {
    b.onclick = () => detailAction(b.dataset.d, k, key0, b.dataset.id);
  });
}

/* 마커 고치기 — 다시 컴파일하지 않고 규칙 한 줄만 바로잡는 길.
 * 고치면 버전이 올라 이 틀로 잘린 문서가 전부 '다시 해석 필요' 가 된다. */
async function editMarker(docType, id) {
  const j = S.rules.get(docType);
  const m = (j.regex_markers || []).find((x) => x.id === id) || {};
  const pattern = prompt(
    `'${id}' 의 정규식 — 반드시 ^ 로 시작합니다 (구역은 줄 머리에서 열립니다)`,
    m.pattern || "^");
  if (pattern === null) return;
  const lv = prompt(`'${id}' 의 층(level) — 작을수록 바깥`, String(m.level ?? 0));
  if (lv === null) return;
  await patchRules(docType, [{ id, pattern: pattern.trim(), level: Number(lv) }]);
}

async function addMarker(docType) {
  const id = prompt("새 마커의 id (예: 별표)");
  if (!id?.trim()) return;
  const pattern = prompt("정규식 — ^ 로 시작", "^\\[별표\\s*(\\d+)\\]");
  if (pattern === null) return;
  const lv = prompt("층(level) — 작을수록 바깥", "0");
  if (lv === null) return;
  const groups = (prompt("캡처 이름 — 쉼표 (없으면 비움)", "no") || "")
    .split(",").map((s) => s.trim()).filter(Boolean);
  await patchRules(docType, [{ id: id.trim(), pattern: pattern.trim(),
                               level: Number(lv), groups }]);
}

async function patchRules(docType, markers, extra = {}) {
  const r = await fetch(`/v1/formats/${encodeURIComponent(docType)}/rules`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markers, ...extra }) });
  if (!r.ok) { banner(await errText(r), "err"); return false; }
  const j = await r.json();
  S.rules.delete(docType);                 // 캐시를 버리고 새 규칙을 다시 받는다
  await load();
  await renderDetail();
  banner(`'${docType}' 규칙을 고쳤습니다 (v${j.format_version}) — ${j.changed.join(", ")}`
    + (j.affected.length ? ` · ${j.affected.length}곳이 '다시 해석 필요' 가 됐습니다` : ""));
  return true;
}

async function detailAction(act, k, key0, id) {
  if (act === "editmk") return editMarker(key0, id);
  if (act === "addmk") return addMarker(key0);
  if (act === "delmk") {
    if (!confirm(`마커 '${id}' 를 지웁니다 — 이 틀로 자르던 구역이 사라집니다.`)) return;
    return patchRules(key0, [{ id, delete: true }]);
  }
  if (act === "toggle") {
    S.open.has(key0) ? S.open.delete(key0) : S.open.add(key0);
    await saveCanvas();
    render();
    return renderDetail();
  }
  if (act === "unbind") return unbindNode(k === "folder" ? FOLDER(key0) : DOC(key0));
  if (act === "apply") {
    return applyFormat(k === "folder" ? S.bind.folders[key0] : key0,
                       k === "folder" ? S.docs.filter((d) => d.folder === key0)
                         .map((d) => d.doc_id) : undefined);
  }
  if (act === "drop") return dropFormat(key0);
  if (act === "run") {
    const d = S.drafts.find((x) => `draft:${x.id}` === S.sel);
    if (d) return runDraft(d);
  }
  if (act === "warm") {
    progress("파싱 캐시 만드는 중…");
    const r = await fetch(`/v1/structure/${encodeURIComponent(key0)}/parse`,
                          { method: "POST" });
    progressDone();
    if (!r.ok) { banner(await errText(r), "err"); return; }
    const j = await r.json();
    banner(j.cached ? "이미 파싱 캐시가 있습니다" : `파싱 캐시를 만들었습니다 — ${j.took_sec}초`);
    await load();
    return renderDetail();
  }
  if (act === "reinterpret") {
    progress("다시 해석 중…");
    const r = await fetch(`/v1/structure/${encodeURIComponent(key0)}/reinterpret`,
                          { method: "POST" });
    progressDone();
    if (!r.ok) { banner(await errText(r), "err"); return; }
    const j = await r.json();
    banner(`다시 해석했습니다 — 부합 ${Math.round((j.score || 0) * 100)}%`
      + (j.parse_cached === false ? " (파싱을 새로 했습니다)" : ""));
    await load();
    return renderDetail();
  }
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
/* 빈 바탕을 누르면 고르기를 푼다 */
cv.addEventListener("click", (e) => {
  if (e.target.closest(".node")) return;
  S.sel = null;
  render();
  renderDetail();
});

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
    S.drag.moved = true;
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
  if (S.drag) {
    const { id, moved } = S.drag;
    S.drag = null;
    if (moved) saveCanvas();
    else select(id);                       // 누르기만 했다 = 고른 것
    return;
  }
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
