/* 구조 해석 검수 화면.
 *
 * 서버가 주는 것
 *   nodes[]   평평한 트리 (parent 로 이어진다)
 *   blocks[]  블록마다 { rect(0~1 비율), node(속한 마디), opens(연 마디들), markers[] }
 *   pages[]   페이지 크기
 *
 * 화면이 하는 것
 *   페이지 PNG 위에 rect 를 절대배치로 얹는다. 비율이라 배율이 바뀌어도 그대로 곱하면 된다.
 *   색은 계층 깊이에만 쓴다 — 이 화면에서 의미를 가진 유일한 축이다.
 */
const API = "/v1/structure";
const LV = 7;                          // L0~L6 까지 색을 준다
const $ = (id) => document.getElementById(id);

const S = {
  docId: null, data: null, docs: [], zoom: 1,
  sel: null,                            // 선택한 마디 id
  pinned: false, pinBlock: null,        // 검사기 고정
  open: new Set(),                      // 펼친 마디
  byId: new Map(), children: new Map(), path: new Map(),
  blockAt: new Map(),                   // 블록 idx → 블록 (트리 잎용)
  openBlk: new Set(),                   // 세부(자기 블록)를 편 마디
  selBlock: null,                       // 낱개로 고른 블록 — 그것만 하이라이트
};

const lv = (n) => `var(--l${Math.min(Math.max(n | 0, 0), LV - 1)})`;

/* ---------------------------------------------------------------- 상태 표시 */
function say(msg, kind = "") {
  const el = $("status");
  el.textContent = msg || "";
  el.className = "status " + kind;
}

/* ------------------------------------------------------------------ 업로드 */
$("file").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  const g = (id) => ($(id).value || "").trim();
  if (g("hRoot")) fd.append("root", g("hRoot"));
  if (g("hFamilies")) fd.append("families", g("hFamilies").replace(/\s/g, ""));
  if (g("hLadder")) fd.append("ladder", g("hLadder").replace(/\s/g, ""));
  if (g("hOrder")) fd.append("order", g("hOrder").replace(/\s/g, ""));
  if ($("useLlm").checked) fd.append("use_llm", "true");

  say(`해석 중 — ${f.name} (첫 문서는 docling 모델 적재로 오래 걸립니다)`, "busy");
  try {
    const r = await fetch(`${API}/documents`, { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail?.message || j.detail || "실패");
    await refreshDocs();
    await load(j.doc_id);
  } catch (err) {
    say(String(err.message || err), "err");
  } finally {
    e.target.value = "";
  }
});

/* 문서 목록 — 이 시스템이 처리한 PDF 전부. 골라서 다시 볼 수 있다. */
async function refreshDocs() {
  const r = await fetch(`${API}/documents`);
  const { documents } = await r.json();
  S.docs = documents;
  $("docCount").textContent = documents.length;

  const box = $("docs");
  box.innerHTML = documents.length ? ""
    : "<div class='empty'><p class='dim'>아직 올린 문서가 없습니다.</p></div>";

  for (const d of documents) {
    const el = document.createElement("div");
    el.className = "doc" + (d.doc_id === S.docId ? " on" : "");
    el.onclick = (e) => { if (e.target.tagName !== "BUTTON") load(d.doc_id); };

    const top = document.createElement("div");
    top.className = "top";
    top.innerHTML = `<span class="name">${esc(d.name)}</span>
      <span class="pill ${d.passed ? "ok" : "no"}">${(d.score * 100).toFixed(0)}%</span>`;

    const del = document.createElement("button");
    del.className = "del";
    del.textContent = "삭제";
    del.onclick = async () => {
      if (!confirm(`${d.name} 을(를) 삭제합니다`)) return;
      await fetch(`${API}/${d.doc_id}`, { method: "DELETE" });
      if (S.docId === d.doc_id) { S.docId = null; S.data = null; }
      refreshDocs();
    };
    top.appendChild(del);

    const bot = document.createElement("div");
    bot.className = "bot";
    bot.innerHTML = `<span>${d.pages}쪽</span><span>${esc(d.tier)}</span>
      ${d.used_llm ? "<span>LLM</span>" : ""}
      <span style="margin-left:auto">${esc((d.at || "").replace("T", " ").slice(0, 16))}</span>`;

    el.append(top, bot);
    box.appendChild(el);
  }
}

/* 왼쪽 패널 탭 */
function tab(which) {
  for (const [id, name] of [["tabTree", "tree"], ["tabDocs", "docs"], ["tabFlow", "flow"]]) {
    $(id).classList.toggle("on", which === name);
    $(name).hidden = which !== name;
  }
  $("treeFilter").hidden = which === "docs";
  $("treeTools").style.visibility = which === "tree" ? "" : "hidden";
}
$("tabTree").onclick = () => tab("tree");
$("tabDocs").onclick = () => { tab("docs"); refreshDocs(); };
$("tabFlow").onclick = () => { tab("flow"); renderFlow(); };

/* 읽기 순서 — **구조가 안 잡힌 블록까지 전부** 읽기 순서대로 세운다.
 *
 * 구조 트리는 활성된 마디만 보여 준다. 그래서 마커가 없어 후보조차 서지 못한 줄
 * (`삼성증권 디폴트옵션 …`)은 화면 어디에도 안 나타난다 — 놓친 것이 안 보이면
 * 놓쳤다는 사실도 모른다. 여기서는 소속 레벨이 없으면 `None` 으로 뜬다. */
function renderFlow() {
  const d = S.data;
  if (!d) return;
  const q = ($("treeFilter").value || "").trim().toLowerCase();
  const byId = new Map(d.nodes.map((n) => [n.id, n]));
  const box = $("flow");
  box.innerHTML = "";

  let nNone = 0;
  for (const b of d.blocks) {
    const n = b.node == null ? null : byId.get(b.node);
    if (n == null) nNone++;
    const hay = (b.text || "").toLowerCase();
    if (q && !hay.includes(q)) continue;

    const row = document.createElement("div");
    row.className = "node flowrow" + (n == null ? " orphan" : "");
    row.dataset.block = b.idx;

    const chip = document.createElement("span");
    chip.className = "chip";
    if (n == null) { chip.textContent = "None"; chip.classList.add("none"); }
    else { chip.textContent = "L" + n.level; chip.style.background = lv(n.level); }

    const kind = document.createElement("span");
    kind.className = "kindtag";
    kind.textContent = b.kind === "table" ? "표" : b.kind === "figure" ? "그림" : "";

    const txt = document.createElement("span");
    txt.className = "surface";
    txt.textContent = b.text ? b.text.slice(0, 90) : (b.kind === "figure" ? "(그림)" : "(표)");

    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `#${b.idx} p${b.page}`
      + (b.opens && b.opens.length ? " · 구역 엶" : "");

    row.append(chip, kind, txt, meta);
    row.onclick = () => pick(b, true);
    box.appendChild(row);
  }
  const head = document.createElement("div");
  head.className = "sub";
  head.style.padding = "6px 8px";
  head.textContent = `블록 ${d.blocks.length}개 · 소속 없음 ${nNone}개`
    + " — 소속이 없으면 구조가 그 자리를 설명하지 못한 것입니다";
  box.prepend(head);
}

/* 딥링크 — `?doc=…&block=…` 으로 들어오면 그 문서를 열고 그 블록을 짚는다.
 *
 * 용어집에서 "이 말이 여기 있다" 를 눌렀을 때 문서를 손으로 다시 찾게 하면 안 된다.
 * 좌표는 이미 payload 에 있으므로 URL 로 넘겨 받아 그대로 고른다. */
function deepLink() {
  const u = new URLSearchParams(location.search);
  return { doc: u.get("doc"), block: u.get("block"), node: u.get("node") };
}

/* -------------------------------------------------------------------- 적재 */
async function load(docId) {
  say("불러오는 중", "busy");
  const r = await fetch(`${API}/${docId}`);
  if (!r.ok) return say("문서를 찾을 수 없습니다", "err");
  S.docId = docId;
  S.data = await r.json();
  index();
  $("docName").textContent = S.data.doc;
  S.pinned = false; renderInspector(null);
  // 한 화면이 터져도 나머지는 뜨게 한다. 트리에서 난 오류로 PDF 를 통째로 잃는
  // 일이 실제로 있었다 — 화면끼리 서로를 세우면 안 된다.
  for (const [name, fn] of [["트리", renderTree], ["페이지", renderPages],
                            ["요약", renderSummary], ["순서", renderOrderQuick],
                            ["힌트", renderApplied], ["유도순서", renderDerivedOrder]]) {
    try { fn(); } catch (err) {
      console.error(name, err);
      say(`${name} 화면 오류: ${err.message}`, "err");
    }
  }
  refreshDocs();
  tab("tree");
  $("reinterpret").disabled = false;

  // 딥링크로 들어왔으면 그 자리를 짚는다. 한 번만 쓰고 URL 에서 지운다 —
  // 남겨 두면 다른 문서를 열어도 계속 그리로 끌려간다.
  const dl = deepLink();
  if (dl.doc === docId) {
    if (dl.node != null) select(+dl.node, true);
    if (dl.block != null) {
      const b = S.blockAt.get(+dl.block);
      if (b) {
        // 그 블록을 품은 마디를 펼쳐야 트리에서도 보인다.
        for (const n of S.data.nodes)
          if (n.span[0] <= b.idx && b.idx < n.span[1]) { S.open.add(n.id); S.openBlk.add(n.id); }
        renderTree();
        pickBlock(b);
      }
    }
    history.replaceState(null, "", location.pathname);
  }
  say("");
}

/* 규칙을 고친 뒤 같은 문서를 다시 해석한다.
 *
 * 다시 올리게 하지 않는 이유: 비싼 것은 docling 파싱(모델 추론)이고 해석(S0~S5)은
 * 싸다. 서버가 `parse.json` 을 들고 있어서 이 버튼은 해석만 다시 돌린다. 등록한
 * 표면 패턴이나 힌트를 바꿨을 때 그 효과를 곧바로 볼 수 있어야 한다. */
$("reinterpret").onclick = async () => {
  if (!S.docId) return;
  const fd = new FormData();
  const g = (id) => ($(id).value || "").trim();
  if (g("hRoot")) fd.append("root", g("hRoot"));
  if (g("hFamilies")) fd.append("families", g("hFamilies").replace(/\s/g, ""));
  if (g("hLadder")) fd.append("ladder", g("hLadder").replace(/\s/g, ""));
  if (g("hOrder")) fd.append("order", g("hOrder").replace(/\s/g, ""));
  if ($("useLlm").checked) fd.append("use_llm", "true");

  $("reinterpret").disabled = true;
  // 몇 초 걸리는지 실시간으로 보여 준다. 파싱 캐시가 없는 문서는 docling 을 다시
  // 돌아 **몇 분**이 걸리는데, 아무 표시가 없으면 멈춘 것과 구별되지 않는다.
  const t0 = Date.now();
  const tick = setInterval(() => {
    const s = Math.round((Date.now() - t0) / 1000);
    say(`다시 해석 중… ${s}초`
      + ($("useLlm").checked ? " · LLM 해소를 켜면 페이지마다 VLM 을 불러 수십 초씩 걸립니다"
                             : " (첫 재해석은 파싱 캐시가 없어 몇 분 걸릴 수 있습니다)"), "busy");
  }, 1000);
  say("다시 해석 중… 0초", "busy");
  try {
    const r = await fetch(`${API}/${S.docId}/reinterpret`, { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail?.message || j.detail || "실패");
    await load(S.docId);
    const d = j.delta || {};
    const dz = d.score > 0 ? `+${d.score}` : `${d.score}`;
    say(`${j.took_sec}초 · 적합도 ${(j.score * 100).toFixed(0)}% (${j.tier}) `
      + `${d.score === 0 ? "변화 없음" : `이전 대비 ${dz}`}`
      + ` · 활성 ${d.activated}/${d.candidates} · 커버 ${d.coverage}`
      + (d.unlocked?.length ? ` · 층해제 ${d.unlocked.join(",")}` : "")
      + (d.thin_suspects ? ` · 놓친제목 의심 ${d.thin_suspects}` : "")
      + (d.vlm_sec ? ` · VLM ${d.vlm_sec}초/${d.vlm_pages}쪽 `
          + `(물음 ${d.vlm_asked}, 중복생략 ${d.vlm_deduped}, 제목 ${d.vlm_headings || 0})` : "")
      + ` · ${j.parse_note}`);
  } catch (err) {
    say(String(err.message || err), "err");
  } finally {
    clearInterval(tick);
    $("reinterpret").disabled = false;
  }
};

function index() {
  S.byId.clear(); S.children.clear(); S.path.clear(); S.open.clear(); S.sel = null;
  S.blockAt.clear(); S.openBlk.clear(); S.selBlock = null;
  for (const b of S.data.blocks) S.blockAt.set(b.idx, b);
  for (const n of S.data.nodes) {
    S.byId.set(n.id, n);
    if (!S.children.has(n.parent)) S.children.set(n.parent, []);
    S.children.get(n.parent).push(n);
  }
  for (const n of S.data.nodes) {
    const p = n.parent == null ? [] : S.path.get(n.parent);
    S.path.set(n.id, [...p, n.surface]);
    if (n.level <= 1) S.open.add(n.id);      // 처음엔 두 단계만 펼친다
  }
}

/* 이 마디가 **자기 것으로** 가진 블록 — span 에서 자식 마디의 몫과 제목 줄을 뺀 나머지. */
function ownBlocks(n) {
  const taken = new Set();
  for (const k of S.children.get(n.id) || [])
    for (let i = k.span[0]; i < k.span[1]; i++) taken.add(i);
  const out = [];
  for (let i = n.span[0]; i < n.span[1]; i++) {
    if (taken.has(i) || i === n.block) continue;
    const b = S.blockAt.get(i);
    if (b) out.push(b);
  }
  return out;
}

/* 낱개 블록을 고른다 — **그 상자 하나만** 하이라이트하고 그 자리로 스크롤한다.
 * 마디를 고르면 구간 전체가 칠해지는데, 세부를 볼 때는 그것이 오히려 방해다. */
function pickBlock(b) {
  S.selBlock = (S.selBlock === b.idx) ? null : b.idx;
  pick(b, true);
  paintSelection();
  renderTree();
  const el = document.querySelector(`.box[data-block="${b.idx}"]`);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
}

/* -------------------------------------------------------------------- 트리 */
function renderTree() {
  const box = $("tree");
  box.innerHTML = "";
  const q = ($("treeFilter").value || "").trim().toLowerCase();

  const walk = (parent, depth) => {
    for (const n of S.children.get(parent) || []) {
      const kids = S.children.get(n.id) || [];
      const row = document.createElement("div");
      row.className = "node" + (S.sel === n.id ? " sel" : "");
      row.style.paddingLeft = `${8 + depth * 14}px`;
      row.dataset.id = n.id;

      const tw = document.createElement("span");
      tw.className = "twist" + (kids.length ? "" : " leaf");
      tw.textContent = S.open.has(n.id) ? "▾" : "▸";
      tw.onclick = (e) => {
        e.stopPropagation();
        S.open.has(n.id) ? S.open.delete(n.id) : S.open.add(n.id);
        renderTree();
      };

      const chip = document.createElement("span");
      chip.className = "chip";
      chip.style.background = lv(n.level);
      chip.textContent = "L" + n.level;

      const su = document.createElement("span");
      su.className = "surface";
      su.textContent = n.surface;

      const ti = document.createElement("span");
      ti.className = "title";
      ti.textContent = n.title || "";

      const meta = document.createElement("span");
      meta.className = "meta";
      const att = n.attachments || [];
      const nt = att.filter((a) => a.kind === "table").length;
      const nf = att.filter((a) => a.kind === "figure").length;
      meta.textContent = `p${n.page} · ${n.span[1] - n.span[0]}블록`
        + (nt ? ` · 표${nt}` : "") + (nf ? ` · 그림${nf}` : "");

      // 세부(자기 블록)는 **따로** 접는다. 자식 마디 펼침과 같이 묶으면 조 하나를
      // 펼칠 때마다 본문 수십 줄이 함께 쏟아져 트리를 못 읽는다.
      const own = ownBlocks(n);
      let det = null;
      if (own.length) {
        det = document.createElement("span");
        det.className = "det" + (S.openBlk.has(n.id) ? " on" : "");
        det.textContent = `${S.openBlk.has(n.id) ? "▾" : "▸"} 세부 ${own.length}`;
        det.onclick = (e) => {
          e.stopPropagation();
          S.openBlk.has(n.id) ? S.openBlk.delete(n.id) : S.openBlk.add(n.id);
          renderTree();
        };
      }

      row.append(tw, chip, su, ti, meta);
      if (det) row.append(det);
      row.onclick = () => select(n.id, true);
      const hay = `${n.surface} ${n.title || ""} ${n.family}`.toLowerCase();
      if (q && !hay.includes(q))
        row.classList.add("hidden");
      box.appendChild(row);

      if (S.openBlk.has(n.id)) {
        for (const b of own) {
          const leaf = document.createElement("div");
          leaf.className = "node leaf-blk"
            + (S.selBlock === b.idx ? " sel" : "");
          leaf.style.paddingLeft = 8 + (depth + 1) * 14 + "px";
          const tag = b.kind === "table" ? "표" : b.kind === "figure" ? "그림" : "";
          leaf.innerHTML =
            `<span class="twist leaf"></span>` +
            `<span class="chip blk">${esc(tag || "본문")}</span>` +
            `<span class="surface">${esc((b.text || "(빈 블록)").slice(0, 70))}</span>` +
            `<span class="meta">#${b.idx} p${b.page}</span>`;
          leaf.onclick = (e) => { e.stopPropagation(); pickBlock(b); };
          if (q && !(b.text || "").toLowerCase().includes(q))
            leaf.classList.add("hidden");
          box.appendChild(leaf);
        }
      }

      // 표·그림은 마디의 **잎**이다. 구역을 열지 않으므로 자식 마디가 아니지만,
      // 트리에 안 보이면 "표가 어느 구역 것인지" 를 화면에서 확인할 길이 없다.
      for (const a of att) {
        const leaf = document.createElement("div");
        leaf.className = "node leaf-att";
        leaf.style.paddingLeft = 8 + (depth + 1) * 14 + "px";
        const far = !a.same_page || a.distance > 40;
        leaf.innerHTML =
          `<span class="twist leaf"></span>` +
          `<span class="chip att">${a.kind === "table" ? "표" : "그림"}</span>` +
          `<span class="surface">블록 ${a.block}</span>` +
          `<span class="meta${far ? " warn" : ""}">p${a.page}` +
          `${far ? ` · 마디에서 ${a.distance}블록 떨어짐` : ""}</span>`;
        leaf.onclick = (e) => {
          e.stopPropagation();
          const b = S.data.blocks.find((x) => x.idx === a.block);
          if (b) pick(b, true);
        };
        if (q && !`${a.kind} 표 그림`.includes(q)) leaf.classList.add("hidden");
        box.appendChild(leaf);
      }

      if (S.open.has(n.id)) walk(n.id, depth + 1);
    }
  };
  walk(null, 0);
}
$("treeFilter").addEventListener("input", renderTree);
$("expandAll").onclick = () => { S.data.nodes.forEach((n) => S.open.add(n.id)); renderTree(); };
$("collapseAll").onclick = () => { S.open.clear(); renderTree(); };

function select(id, scroll) {
  S.sel = id;
  // 선택한 마디가 보이도록 조상을 전부 펼친다
  let cur = S.byId.get(id);
  while (cur && cur.parent != null) { S.open.add(cur.parent); cur = S.byId.get(cur.parent); }
  renderTree();
  paintSelection();
  if (scroll) {
    const n = S.byId.get(id);
    const el = document.querySelector(`.page[data-page="${n.page}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function paintSelection() {
  const inSel = new Set();
  if (S.sel != null) {
    const stack = [S.sel];
    while (stack.length) {
      const id = stack.pop();
      const n = S.byId.get(id);
      for (let b = n.span[0]; b < Math.max(n.span[1], n.span[0] + 1); b++) inSel.add(b);
      for (const k of S.children.get(id) || []) stack.push(k.id);
    }
  }
  document.querySelectorAll(".box").forEach((el) => {
    const idx = +el.dataset.block;
    el.classList.toggle("sel", inSel.has(idx));
    // 낱개로 고른 블록은 **그것만** 도드라지게. 마디 선택(구간 전체)과 겹쳐도
    // 어느 상자를 고른 것인지 눈으로 갈려야 한다.
    el.classList.toggle("blksel", S.selBlock === idx);
  });
}

/* ------------------------------------------------------------ 페이지 오버레이 */
function renderPages() {
  const box = $("pages");
  box.innerHTML = "";
  const scale = 2;                                  // 서버 렌더 배율
  const width = (w) => Math.round(w * S.zoom * 1.34);   // 화면 기준 폭(pt→px 보정)

  const byPage = new Map();
  for (const b of S.data.blocks) {
    if (!b.rect) continue;
    if (!byPage.has(b.page)) byPage.set(b.page, []);
    byPage.get(b.page).push(b);
  }

  for (const p of S.data.pages) {
    const wrap = document.createElement("div");
    wrap.className = "page";
    wrap.dataset.page = p.n;
    wrap.style.width = width(p.w) + "px";

    const num = document.createElement("div");
    num.className = "pagenum";
    num.textContent = `p${p.n}`;

    const img = document.createElement("img");
    img.loading = "lazy";
    img.src = `${API}/${S.docId}/page/${p.n}?scale=${scale}`;
    img.alt = `${p.n}쪽`;

    wrap.append(num, img);
    for (const b of byPage.get(p.n) || []) for (const el of boxEls(b)) wrap.appendChild(el);
    box.appendChild(wrap);
  }
  paintSelection();
  applyToggles();
}

/* 한 블록이 구역을 여러 개 열 수 있다 — `제4장 … 제1절 …` 처럼 원문이 한 줄일 때다.
 * bbox 는 하나뿐이라 박스를 그대로 겹치면 안쪽 마디가 안 보인다.
 * 레벨이 깊을수록 안쪽으로 들여 그리고, 라벨은 세로로 쌓는다. */
function boxEls(b) {
  const out = [];
  const opens = (b.opens || []).slice().sort(
    (x, y) => S.byId.get(x).level - S.byId.get(y).level);
  const residual = b.markers.some((m) => S.data.residual_ids.includes(m.id));

  const mk = (cls, color, inset) => {
    const el = document.createElement("div");
    el.className = "box " + cls + (residual ? " residual" : "")
      + (b.kind && b.kind !== "text" ? " " + b.kind : "");
    el.dataset.block = b.idx;
    el.style.color = color;
    el.style.left = `calc(${b.rect.x * 100}% + ${inset}px)`;
    el.style.top = `calc(${b.rect.y * 100}% + ${inset}px)`;
    el.style.width = `calc(${b.rect.w * 100}% - ${inset * 2}px)`;
    el.style.height = `calc(${b.rect.h * 100}% - ${inset * 2}px)`;
    el.onclick = (e) => { e.stopPropagation(); pick(b, true); };
    el.onmouseenter = () => pick(b, false);
    out.push(el);
    return el;
  };

  if (!opens.length) {
    mk(b.node == null ? "chunk dead" : "chunk",
       b.level == null ? "var(--dim)" : lv(b.level), 0);
    return out;
  }

  opens.forEach((id, i) => {
    const n = S.byId.get(id);
    const el = mk("opener", lv(n.level), i * 3);
    el.dataset.node = id;
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.style.background = lv(n.level);
    tag.style.left = "0";
    tag.style.bottom = `calc(100% + ${(opens.length - 1 - i) * 12}px)`;
    tag.textContent = `L${n.level} ${n.surface}${n.title ? " " + n.title : ""}`;
    el.appendChild(tag);
    el.onclick = (e) => { e.stopPropagation(); select(id, false); pick(b, true); };
  });
  return out;
}

/* ------------------------------------------------- 검사기 (오른쪽 바 위쪽) */

/* 마우스를 올리면 바로 보여 주고, 클릭하면 고정한다 — 마우스를 떼도 읽을 수 있게. */
function pick(b, pin) {
  if (S.pinned && !pin) return;
  if (pin) S.pinned = (S.pinBlock === b.idx) ? !S.pinned : true;
  S.pinBlock = b.idx;
  renderInspector(b);
}

function renderInspector(b) {
  const box = $("inspect");
  if (!b) { box.innerHTML = "<div class='sub'>영역에 마우스를 올리면 판정 근거가 뜹니다</div>"; return; }
  const path = b.node == null ? "(구역 없음)" : S.path.get(b.node).join(" / ");
  const opened = (b.opens || []).map((i) => S.byId.get(i));

  const names = opened.length ? `<div class="names">` + opened.map((n) =>
    `<div><span class="chip" style="background:${lv(n.level)}">L${n.level}</span>
      <b>${esc(n.surface)}</b>
      ${n.title ? `<span class="nm">${esc(n.title)}</span>` : "<span class='sub'>이름 없음</span>"}
      <div class="sub">${esc(n.title_reason || "")}</div></div>`).join("") + `</div>` : "";

  const marks = b.markers.map((m) => {
    const res = S.data.residual_ids.includes(m.id);
    const state = !m.survives ? ["기각", "bad"]
      : m.activated ? [`활성 L${m.level}`, "good"] : ["미활성", "warn"];
    return `<div class="mk">
      <div class="mkhead">
        <b>${esc(m.surface)}</b>
        <span class="pill ${state[1] === "good" ? "ok" : "no"}">${state[0]}</span>
        <span class="sub mono">${esc(m.family)}</span>
        <span class="sub mono" style="margin-left:auto">s=${m.s > 0 ? "+" : ""}${m.s}</span>
      </div>
      ${m.llm ? `<div class="sub">LLM 판정: <b>${esc(m.llm)}</b></div>` : ""}
      ${res ? `<div class="warn">잔여 — 결정론이 못 가름</div>` : ""}
      <div class="sub reason">${esc(m.note || "")}</div>
    </div>`;
  }).join("") || "<div class='sub'>이 블록에는 마커가 없습니다</div>";

  box.innerHTML = `
    <div class="ihead">
      <span class="sub mono">블록 ${b.idx} · p${b.page}</span>
      ${b.kind && b.kind !== "text" ? `<span class="pill">${b.kind === "table" ? "표" : "그림"}</span>` : ""}
      ${S.pinned ? "<span class='pill'>고정</span>" : ""}
    </div>
    <div class="sub">${esc(path)}</div>
    ${bodyHtml(b)}
    ${names}
    ${b.opens && b.opens.length > 1
      ? `<div class="warn">이 블록이 구역 ${b.opens.length}개를 엽니다 —
         원문이 한 줄이라 좌표가 같습니다</div>` : ""}
    ${marks}`;
}
/* 표·그림은 평문으로 보이면 검수가 안 된다 — 표는 격자로, 그림은 자리만 알린다.
 * 병합 셀은 span 을 되살려 원본 모양대로 그린다. 머리글은 <th> 로 갈라, 값 셀의
 * 의미가 어느 축에서 오는지 눈으로 확인할 수 있게 한다. */
function bodyHtml(b) {
  if (b.kind === "table" && b.table) {
    const rows = b.table.rows.map((row) => "<tr>" + row.map((c) => {
      const tag = c.col_header || c.row_header ? "th" : "td";
      const sp = (c.row_span > 1 ? ` rowspan="${c.row_span}"` : "")
               + (c.col_span > 1 ? ` colspan="${c.col_span}"` : "");
      return `<${tag}${sp}>${esc(c.text)}</${tag}>`;
    }).join("") + "</tr>").join("");
    const src = b.table.header_source === "convention"
      ? `<div class="sub">머리글은 파서가 표시하지 않아 <b>관습</b>(첫 행·첫 열)으로 잡았습니다</div>`
      : "";
    return `<div class="tablewrap"><table class="rt">${rows}</table></div>
            <div class="sub mono">${b.table.n_rows}행 × ${b.table.n_cols}열</div>${src}`;
  }
  if (b.kind === "figure") {
    const f = b.figure || {};
    const size = f.size ? `<div class="sub mono">${f.size[0]}×${f.size[1]}px</div>` : "";
    // 픽셀이 있으면 그것을 보여 준다 — 캡션 없는 도장·서명이 대부분이라
    // "그림이 있었다" 만으로는 검수가 되지 않는다.
    const img = f.image
      ? `<img class="figimg" src="${f.image}" alt="${esc(f.caption || "그림")}">`
      : `<div class="warn">${f.omitted
          ? "그림이 커서 이 화면에는 싣지 않았습니다"
          : "픽셀을 받지 못했습니다 — 자리와 좌표만 있습니다"}</div>`;
    return `${img}${size}${f.caption ? `<div class="quote">${esc(f.caption)}</div>` : ""}`;
  }
  return `<div class="quote">${esc((b.text || "").slice(0, 400))}</div>`;
}

$("unpin").onclick = () => { S.pinned = false; renderInspector(null); };

const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------------------------------------------- 요약 */
function renderSummary() {
  const d = S.data, f = d.fitness, l = d.ladder;
  const pct = (x) => (x == null ? "–" : (x * 100).toFixed(0) + "%");
  const rungs = l.rungs.map((r) =>
    `<div class="rung"><span class="chip" style="background:${lv(r.level)}">L${r.level}</span>
     <span>${esc(r.families.join(", "))}</span>
     <span class="sub" style="margin-left:auto">reg ${r.reg_score.toFixed(2)}</span></div>`).join("");

  const problems = [];
  if (l.cycle_broken?.length)
    problems.push(`<div class="bad">순환 절단: ${esc(l.cycle_broken.join(", "))} — 층이 증거가 아니라 이름 순으로 정해졌습니다</div>`);
  if (l.unordered_pairs?.length)
    problems.push(`<div class="warn">순서 미정 ${l.unordered_pairs.length}/${l.n_pairs} 쌍</div>`);
  if (l.unregistered?.length)
    problems.push(`<div class="warn">미등재 계열: ${esc(l.unregistered.join(", "))}</div>`);

  const ap = d.applied || {};
  const hintRows = [
    ["부분 순서", (ap.partial_order || []).join(", ")],
    ["좌표 최상위", ap.root],
    ["어휘 제한", (ap.families || []).join(", ")],
    ["층 지정", (ap.ladder_hint || []).map((g) => g.join(",")).join(" ; ")],
    ["LLM 해소", ap.llm ? "켬" : ""],
  ].filter((x) => x[1]);
  const hints = `<div class="sec"><h4>이 문서에 준 힌트</h4>` +
    (hintRows.length
      ? `<div class="kv">${hintRows.map(([k, v]) =>
          `<div><span>${esc(k)}</span><b>${esc(String(v))}</b></div>`).join("")}</div>`
      : `<div class="sub">없음 — 관측만으로 유도했습니다</div>`) + `</div>`;

  const llm = d.llm ? `<div class="sec"><h4>LLM 배치 1콜</h4>
      <div class="sub">물음 ${d.llm.asked} → 구조 ${d.llm.structure.length},
      인용 ${d.llm.mention.length}, 보류 ${d.llm.unsure.length} · 실제 변경 ${d.llm.changed}</div></div>` : "";

  const res = d.residual.length
    ? `<div class="sec"><h4>잔여 ${d.residual.length}건</h4><div class="list">` +
      d.residual.map((r) => `<div class="mono" data-res="${esc(r.split(" ")[1])}">${esc(r)}</div>`).join("") +
      `</div></div>`
    : `<div class="sec"><h4>잔여</h4><div class="sub">없음 — 결정론이 전부 갈랐습니다</div></div>`;

  // 문서군(fingerprint) — 같은 모양의 문서가 몇 번 관측됐고 frame 이 동결됐는지.
  // 관측이 쌓여야 tier 가 hot 이 된다 (원장: structure_ledger.json).
  const fpc = d.stats.fingerprint_count;
  const fp = d.fingerprint ? `
    <div class="sub" title="${esc(d.fingerprint.key)}">문서군 관측 ${fpc ?? "–"}회
      ${d.stats.may_freeze ? `<span class="pill ok">frame 동결</span>`
                           : `<span class="pill">동결 전</span>`}</div>` : "";

  // 이 문서가 어떻게 잘렸는가 — 구조화 틀(형식)이 붙었으면 유도가 아니라 그 틀이다.
  // 붙은 틀에서는 사다리·문서군이 "유도의 산물"이 아니므로 먼저 말해 준다.
  const bound = d.bound_doc_type
    ? `<div class="metric"><span>구조화 틀</span>
         <span><b>🧩 ${esc(d.bound_doc_type)}</b></span></div>
       <div class="sub">이 문서는 유도가 아니라 형식 파일의 마커로 잘렸습니다 —
         적합도는 <b>그 틀에 얼마나 맞는가</b>입니다 (구조화 연결 화면에서 바꿉니다)</div>`
    : "";

  // 원본 형식 — 여기서부터 흐름이 갈린다. 파서가 무엇을 실었는지가 판정의 전제라
  // 결과 화면에 함께 둔다("hwp 라 제목 신호가 없었다" 를 여기서 알 수 있게).
  const KINDS = {
    pdf: ["PDF", "제목 표시 · 타이포그래피 · 지면 좌표"],
    docx: ["DOCX", "제목 계층(Word 스타일) · 좌표 없음 — 합성 지면에 올림"],
    hwp: ["HWP", "md 변환 · 마커만 (제목 신호·좌표 없음) — 합성 지면에 올림"],
    hwpx: ["HWPX", "md 변환 · 마커만 (제목 신호·좌표 없음) — 합성 지면에 올림"],
    lawxml: ["법령 XML", "태그 계층 그대로 — 추론 없음"],
  };
  const ki = KINDS[d.source_kind];
  const src = ki ? `<div class="metric"><span>원본 형식</span>
        <span><b>${ki[0]}</b></span></div>
      <div class="sub">${esc(ki[1])}</div>
      ${d.parser ? `<div class="sub mono">${esc(d.parser)}</div>` : ""}` : "";

  $("summary").innerHTML = `
    ${src}
    ${bound}
    <div class="metric"><span>적합도</span>
      <span><b>${pct(f.score)}</b>
      <span class="pill ${f.passed ? "ok" : "no"}">${f.passed ? "통과" : "미달"}</span>
      <span class="pill">${esc(f.tier)}</span></span></div>
    <div class="sub">커버 ${pct(f.coverage)} × 정합 ${pct(f.consistency)} × 사다리 ${pct(f.ladder_quality)}</div>
    ${fp}
    <div class="sec"><h4>사다리</h4>${rungs}</div>
    ${problems.length ? `<div class="sec"><h4>사다리 결함</h4>${problems.join("")}</div>` : ""}
    ${hints}
    ${llm}
    ${res}
    <div class="sec"><h4>통계</h4><div class="sub mono">
      블록 ${d.stats.blocks} · 후보 ${d.stats.candidates} · 생존 ${d.stats.survivors}
      · 활성 ${d.stats.activated} · 이름 찾은 마디 ${d.stats.titled ?? "–"}
    </div></div>
    <div class="sec"><h4>fingerprint</h4><div class="sub mono">${esc(d.fingerprint.key)}</div></div>`;

  $("summary").querySelectorAll("[data-res]").forEach((el) => {
    el.onclick = () => {
      const b = d.blocks.find((x) => x.markers.some((m) => m.id === el.dataset.res));
      if (!b) return;
      const p = document.querySelector(`.page[data-page="${b.page}"]`);
      if (p) p.scrollIntoView({ behavior: "smooth", block: "start" });
      const box = document.querySelector(`.box[data-block="${b.idx}"]`);
      if (box) { box.classList.add("sel"); setTimeout(() => box.classList.remove("sel"), 2500); }
    };
  });
}

/* ------------------------------------------------------------------ 토글 */
function applyToggles() {
  const chunks = $("showBoxes").checked, marks = $("showMarkers").checked,
        resid = $("showResidual").checked;
  document.querySelectorAll(".box").forEach((el) => {
    const opener = el.classList.contains("opener");
    const isRes = el.classList.contains("residual");
    el.style.display = ((opener ? marks : chunks) || (isRes && resid)) ? "" : "none";
    if (isRes && !resid) el.classList.add("nores"); else el.classList.remove("nores");
  });
  document.querySelectorAll(".tag").forEach((t) => (t.style.display = marks ? "" : "none"));
}
["showBoxes", "showMarkers", "showResidual"].forEach((id) =>
  $(id).addEventListener("change", applyToggles));

$("zoomIn").onclick = () => setZoom(S.zoom + 0.15);
$("zoomOut").onclick = () => setZoom(S.zoom - 0.15);
function setZoom(z) {
  S.zoom = Math.min(2.5, Math.max(0.4, z));
  $("zoomLabel").textContent = Math.round(S.zoom * 100) + "%";
  if (S.data) renderPages();
}

refreshDocs().then(() => {
  if (S.docs.length) load(S.docs[0].doc_id);
});
refreshRules();

/* ==========================================================================
 * 규칙 편집기 — 처음 보는 표기를 어휘에 더한다 (SPEC §6)
 *
 * 표면 패턴만 담는다. 레벨은 서버가 거부한다 — 계층은 문서가 유도한다.
 * ========================================================================== */

async function refreshRules() {
  const r = await fetch(`${API}/rules/custom`);
  if (!r.ok) return;
  const { rules } = await r.json();
  const box = $("rList");
  box.innerHTML = rules.length ? "" : "<div class='sub'>등록된 규칙이 없습니다</div>";
  for (const x of rules) {
    const row = document.createElement("div");
    row.className = "rule";
    row.innerHTML = `<b>${esc(x.id)}</b><code>${esc(x.pattern)}</code>`;
    const del = document.createElement("button");
    del.textContent = "삭제";
    del.onclick = async () => {
      await fetch(`${API}/rules/custom/${x.id}`, { method: "DELETE" });
      refreshRules();
      $("rMsg").textContent = `${x.id} 삭제 — 다시 올리면 반영됩니다`;
    };
    row.appendChild(del);
    box.appendChild(row);
  }
}

$("rSave").onclick = async () => {
  const v = (id) => ($(id).value || "").trim();
  const split = (id) => v(id).split(",").map((s) => s.trim()).filter(Boolean);
  const body = {
    id: v("rId"), family: v("rFamily") || undefined, pattern: v("rPattern"),
    groups: split("rGroups"), ordinal_from: split("rOrdinal"), note: v("rNote"),
  };
  const msg = $("rMsg");
  msg.className = "sub";
  try {
    const r = await fetch(`${API}/rules/custom`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail?.message || j.detail || "실패");
    msg.textContent = j.matched_in_note?.length
      ? `${j.saved} 등록 · 메모에서 적중: ${j.matched_in_note.join(" / ")}`
      : `${j.saved} 등록 — 문서를 다시 올리면 반영됩니다`;
    refreshRules();
  } catch (err) {
    msg.className = "sub bad";
    msg.textContent = String(err.message || err);
  }
};

/* 지금 문서에 적용된 힌트 */
function renderApplied() {
  const box = $("appliedNow");
  if (!box) return;
  if (!S.data) { box.innerHTML = "<div class='sub'>문서를 먼저 열어 주세요</div>"; return; }
  const ap = S.data.applied || {};
  const rows = [
    ["부분 순서", (ap.partial_order || []).join(", ")],
    ["좌표 최상위", ap.root],
    ["어휘 제한", (ap.families || []).join(", ")],
    ["층 지정", (ap.ladder_hint || []).map((g) => g.join(",")).join(" ; ")],
    ["LLM 해소", ap.llm ? "켬" : ""],
  ].filter((x) => x[1]);
  box.innerHTML = `<h3>${esc(S.data.doc)} 에 적용된 힌트</h3>` + (rows.length
    ? `<div class="kv">${rows.map(([k, v]) =>
        `<div><span>${esc(k)}</span><b>${esc(String(v))}</b></div>`).join("")}</div>`
    : `<div class="sub">없음 — 관측만으로 유도했습니다</div>`);
  // 다시 열었을 때 지난 값을 그대로 보여 준다
  if (!$("hOrder").value) $("hOrder").value = (ap.partial_order || []).join(", ");
  if (!$("hRoot").value) $("hRoot").value = ap.root || "";
}

/* 시스템이 **유도한** 순서 — 사람이 준 힌트와 나란히 봐야 뜻이 통한다. */
function renderDerivedOrder() {
  const box = $("derivedOrder");
  if (!box) return;
  if (!S.data) { box.innerHTML = ""; return; }
  const note = (S.data.ladder.notes || []).find((n) => n.startsWith("근거: "));
  const items = note ? note.slice(4).split("; ") : [];
  const pairs = items.map((x) => {
    const m = x.match(/^(\S+)→(\S+)\s*\((.+)\)$/);
    return m ? { a: m[1], b: m[2], why: m[3] } : null;
  }).filter(Boolean);
  box.innerHTML = `<h3>시스템이 유도한 순서 <span class="sub">${pairs.length}쌍</span></h3>` +
    (pairs.length
      ? `<div class="derived">${pairs.map((p) =>
          `<div class="row2"><b>${esc(p.a)}&gt;${esc(p.b)}</b>
            <span class="why">${esc(p.why)}</span></div>`).join("")}</div>`
      : `<div class="sub">없음</div>`);
}

/* 순서 지정 빠른 입력 — 지금 문서의 사다리에서 인접한 쌍을 버튼으로 준다.
   증거가 얇아 순서 미정으로 남은 쌍이 여기 뜬다. */
function renderOrderQuick() {
  const box = $("orderQuick");
  if (!box) return;
  box.innerHTML = "";
  if (!S.data) return;
  const pairs = S.data.ladder.unordered_pairs || [];
  if (!pairs.length) {
    box.innerHTML = "<span class='sub'>순서 미정 쌍 없음</span>";
    return;
  }
  for (const p of pairs) {
    const [a, b] = p.split("/");
    for (const [x, y] of [[a, b], [b, a]]) {
      const btn = document.createElement("button");
      btn.textContent = `${x}>${y}`;
      btn.onclick = () => {
        const cur = ($("hOrder").value || "").trim();
        $("hOrder").value = cur ? `${cur}, ${x}>${y}` : `${x}>${y}`;
      };
      box.appendChild(btn);
    }
  }
}


/* ==========================================================================
 * 규칙 전체 보기 — 이 시스템이 무엇으로 판단하는가
 * ========================================================================== */

/* 설정 모달 — 탭 셋. 힌트(이 문서)·시스템 규칙·내가 등록한 패턴이 한 자리에 있다.
 * 힌트와 규칙을 갈라 두면 "이 시스템이 무엇으로 판단하는가"가 두 군데로 흩어진다. */
function mtab(which) {
  for (const [btn, pane] of [["mtHint", "paneHint"], ["mtSys", "paneSys"],
                             ["mtCust", "paneCust"]]) {
    const on = btn === which;
    $(btn).classList.toggle("on", on);
    $(pane).hidden = !on;
  }
  if (which === "mtSys" && !$("paneSys").dataset.loaded) loadSystemRules();
  if (which === "mtCust") refreshRules();
}
$("mtHint").onclick = () => mtab("mtHint");
$("mtSys").onclick = () => mtab("mtSys");
$("mtCust").onclick = () => mtab("mtCust");

async function loadSystemRules() {
  const box = $("paneSys");
  box.innerHTML = "<div class='sub'>불러오는 중…</div>";
  try {
    const r = await fetch(`${API}/rules/all`);
    box.innerHTML = renderAllRules(await r.json());
    box.dataset.loaded = "1";
  } catch (err) {
    box.innerHTML = `<div class='bad'>${esc(String(err))}</div>`;
  }
}

$("showAll").onclick = () => {
  $("modal").hidden = false;
  renderApplied();
  renderOrderQuick();
  renderDerivedOrder();
  mtab("mtHint");
};
$("modalClose").onclick = () => ($("modal").hidden = true);
$("rSave") && ($("paneCust").dataset.ready = "1");
$("modal").onclick = (e) => { if (e.target.id === "modal") $("modal").hidden = true; };
addEventListener("keydown", (e) => { if (e.key === "Escape") $("modal").hidden = true; });

function renderAllRules(d) {
  const rows = (items, cols) =>
    `<table class="rt"><tr>${cols.map((c) => `<th>${c[0]}</th>`).join("")}</tr>` +
    items.map((it) => `<tr>${cols.map((c) => `<td>${c[1](it)}</td>`).join("")}</tr>`).join("") +
    `</table>`;

  const pat = (it) => (it.patterns || [])
    .map((p) => `<code>${esc(p.pattern)}</code>`).join("<br>") || "—";

  const kv = (obj) => `<div class="kv">` + Object.entries(obj)
    .map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(String(v))}</b></div>`)
    .join("") + `</div>`;

  const chips = (arr) => `<div class="chips">` +
    arr.map((x) => `<span>${esc(String(x))}</span>`).join("") + `</div>`;

  return `
  <section>
    <h3>S0 · 제안자 <span class="sub">표면 패턴을 찾아 후보를 낸다. 레벨 지식 0</span></h3>
    ${rows(d.proposers, [
      ["id", (x) => `<b>${esc(x.id)}</b>`],
      ["계열", (x) => esc(x.family)],
      ["언어", (x) => esc(x.lang)],
      ["표면", (x) => esc(x.surface)],
      ["정규표현식", pat],
    ])}
  </section>

  <section>
    <h3>S1 · 국소 가드 <span class="sub">후보 하나를 주변만 보고 채점</span></h3>
    ${rows(d.guards, [
      ["id", (x) => `<b>${esc(x.id)}</b>`],
      ["언어", (x) => esc(x.lang)],
      ["보는 것", (x) => esc(x.surface)],
    ])}
    ${kv(d.scoring["국소 가드 (S1)"])}
  </section>

  <section>
    <h3>S2 · 계열 정합 <span class="sub">사다리 없이 계열 안에서 구조/인용을 가른다</span></h3>
    ${rows(d.family_coherence, [
      ["id", (x) => `<b>${esc(x.id)}</b>`],
      ["보는 것", (x) => esc(x.surface)],
    ])}
    ${kv(d.scoring["계열 정합 (S2)"])}
  </section>

  <section>
    <h3>S3·S4 · 전역 정합성 <span class="sub">사다리를 세우고 후보를 앉힌다</span></h3>
    ${rows(d.global, [
      ["단계", (x) => esc(x.stage)],
      ["id", (x) => `<b>${esc(x.id)}</b>`],
      ["보는 것", (x) => esc(x.surface)],
      ["임계", (x) => Object.entries(x.params)
        .map(([k, v]) => `<code>${esc(k)}=${esc(String(v))}</code>`).join(" ") || "—"],
    ])}
    ${kv(d.scoring["DP 전이 벌점 (S4)"])}
  </section>

  <section>
    <h3>S5 · 게이트와 잔여</h3>
    ${kv(d.scoring["게이트 (S5)"])}
    ${kv(d.scoring["잔여 (S5)"])}
  </section>

  <section>
    <h3>어휘 <span class="sub">게이트가 쓰는 언어 자원</span></h3>
    <p class="sub">조사 (${d.lexicon["조사"].length})</p>${chips(d.lexicon["조사"])}
    <p class="sub">참조 서술어 (${d.lexicon["참조 서술어"].length})</p>${chips(d.lexicon["참조 서술어"])}
    <p class="sub">연쇄 참조</p>${chips(d.lexicon["연쇄 참조"])}
    <p class="sub">서수 체계</p>${chips(d.lexicon["서수 체계"])}
  </section>

  <section>
    <h3>제목 추출 <span class="sub">구역의 이름을 찾는 규칙</span></h3>
    <table class="rt">
      <tr><th>순서</th><th>규칙</th><th>예</th></tr>
      <tr><td>1</td><td>마커 직후 괄호</td><td><code>제7조(금융소비자의 기본적 권리)</code></td></tr>
      <tr><td>2</td><td>같은 블록의 다음 마커 앞까지</td><td><code>제4장 준수사항 제1절 일반원칙</code></td></tr>
      <tr><td>3</td><td>꼬리 전부 (짧고 종결부호 없음)</td><td><code>제1장 총칙</code></td></tr>
      <tr><td>4</td><td>마커만 있는 줄 → 다음 블록</td><td><code>제1절 ⏎ 영업행위 일반원칙</code></td></tr>
      <tr><td>—</td><td><b>내용이 따로 없으면 이름 없음</b> (규칙 1 제외)</td>
          <td><code>가. 「은행법」에 따른 예금 및 대출</code></td></tr>
    </table>
  </section>`;
}
