/* AGENT6 근거 연결 — 캔버스 보기.
 *
 * 세 겹이다:
 *
 *     [문서]  ┄┄▸  [조문]  ───▸  [체크리스트 항목]
 *     한 장     빠져나온 것만      근거를 받는 쪽
 *
 * ## 문서는 한 장이다
 *
 * KSB 하나가 구역 555개다. 카드 안에 555줄을 그리면 캔버스가 아니라 목록이 된다.
 * 그래서 문서는 **접힌 카드 한 장**이고, 누르면 아래 서랍에 **구조 테이블**이 열린다.
 * 테이블은 트리 순서·제목·본문 미리보기·연결 수를 함께 보여 준다.
 *
 * ## 연결된 조문만 노드로 빠져나온다
 *
 * 조문이 항목에 이어지는 순간 그 조문은 **자기 노드**로 캔버스에 선다(점선 테두리).
 * 그래야 "이 조문 하나를 몇 개 항목이 쓰는가"가 눈에 보인다 — 실측에서 `KSB/제19조`
 * 하나를 12개 항목이 쓴다. 그 조문이 개정되면 12개가 함께 흔들리는데, 목록 보기의
 * 어디에도 그 사실이 안 나타난다.
 *
 * 문서→조문 선은 **점선**(구조: 이 조문은 이 문서의 것)이고, 조문→항목 선은
 * **실선**(근거: 이 항목이 이 조문을 근거로 삼는다)이다. 둘은 다른 종류의 관계다.
 *
 * ## 자리는 계산한다
 *
 * 자유 배치로 두면 카드를 옮기는 데 시간이 다 간다. 세 열로 세우고, 옮기고 싶으면
 * 카드 머리를 끌 수 있다 — 그때만 그 카드의 자리가 고정된다.
 */

const CV = {
  on: false,
  pan: { x: 60, y: 40 }, zoom: 0.9,
  moved: {},                 // 사람이 옮긴 카드만 여기 남는다
  pinned: new Set(),         // 연결은 아직 없지만 꺼내 둔 조문
  open: null,                // 구조 테이블이 열린 문서
  expand: new Set(),         // 구조 테이블에서 펼친 가지
  drag: null, wire: null,
};

const COL = [0, 430, 900];   // 문서 · 조문 · 항목
const cq = (s) => document.querySelector(s);

/* ------------------------------------------------------------------ 모델 */
function cvModel() {
  const links = S.links.filter((l) => l.doc === S.doc);
  const byId = {};
  for (const s of S.tree) byId[s.section_id] = s;

  const used = new Map();                      // section_id → 그 조문을 쓰는 링크들
  for (const l of links) {
    const sid = l.section_id || l.section;
    if (!sid) continue;
    (used.get(sid) || used.set(sid, []).get(sid)).push(l);
  }
  for (const p of CV.pinned) if (!used.has(p)) used.set(p, []);

  const secs = [...used.entries()]
    .filter(([sid]) => byId[sid])
    .map(([sid, ls]) => ({ id: sid, sec: byId[sid], links: ls }))
    .sort((a, b) => b.links.length - a.links.length || a.id.localeCompare(b.id));

  // 근거가 없는 항목도 캔버스에 둔다 — 비어 있다는 사실이 가장 중요한 정보다.
  const items = S.items.slice().sort((a, b) => {
    const na = links.filter((l) => l.item === a.id).length;
    const nb = links.filter((l) => l.item === b.id).length;
    return nb - na || a.id.localeCompare(b.id);
  });
  return { links, secs, items, byId };
}

function cvLayout(m) {
  const pos = {};
  const put = (id, x, y) => (pos[id] = CV.moved[id] || { x, y });
  put(`doc:${S.doc}`, COL[0], 0);
  let y = 0;
  for (const s of m.secs) { put(`sec:${s.id}`, COL[1], y); y += 62; }
  y = 0;
  for (const it of m.items) {
    const n = m.links.filter((l) => l.item === it.id).length;
    put(`item:${it.id}`, COL[2], y);
    y += 52 + n * 20;
  }
  return pos;
}

/* ------------------------------------------------------------------ 렌더 */
function cvRender() {
  if (!CV.on) return;
  const m = cvModel();
  const pos = cvLayout(m);
  const corpus = S.corpora.find((c) => c.id === S.doc) || {};

  const docCard = `<div class="cvcard doc" data-node="doc:${esc(S.doc)}"
      style="left:${pos[`doc:${S.doc}`].x}px; top:${pos[`doc:${S.doc}`].y}px">
    <div class="cvhead"><b>${esc(corpus.title || S.doc)}</b>
      <span class="cvsub">${esc(S.doc)} · 구역 ${S.tree.length}</span></div>
    <div class="cvrow out doc-out" data-node="doc:${esc(S.doc)}" data-row="__doc__">
      <span class="rt">조문 ${m.secs.length}개 꺼냄 · 연결 ${m.links.length}</span>
      <span class="port"></span></div>
    <button class="cvopen">${CV.open === S.doc ? "구조 닫기" : "구조 테이블 열기"}</button>
  </div>`;

  const secCards = m.secs.map((s) => {
    const st = s.links.some((l) => l.status === "AMBIGUOUS") ? " amb"
             : s.links.length === 0 ? " idle" : "";
    return `<div class="cvcard sec${st}" data-node="sec:${esc(s.id)}"
        style="left:${pos[`sec:${s.id}`].x}px; top:${pos[`sec:${s.id}`].y}px">
      <div class="cvhead"><b>${esc(s.sec.label)}</b>
        <span class="cvsub">${esc(s.sec.title || s.sec.preview.slice(0, 34))}</span></div>
      <div class="cvrow in" data-node="sec:${esc(s.id)}" data-row="in">
        <span class="port"></span></div>
      <div class="cvrow out" data-node="sec:${esc(s.id)}" data-row="${esc(s.id)}">
        <span class="rt">${s.links.length ? `${s.links.length}개 항목이 사용` : "아직 연결 없음"}</span>
        <span class="port"></span></div>
    </div>`;
  }).join("");

  const itemCards = m.items.map((it) => {
    const mine = m.links.filter((l) => l.item === it.id);
    const rows = mine.map((l) => {
      const st = l.status === "AMBIGUOUS" ? " amb" : l.status === "RESOLVED" ? "" : " miss";
      return `<div class="cvrow in${st}" data-node="item:${esc(it.id)}"
                   data-row="${esc(l.section_id || l.section || l.coord)}">
        <span class="port"></span>
        <span class="rt">${esc(l.citation || l.resolved || l.coord)}</span></div>`;
    }).join("") || `<div class="cvrow in empty" data-node="item:${esc(it.id)}" data-row="__none__">
        <span class="port"></span><span class="rt">근거 없음</span></div>`;
    return `<div class="cvcard item${S.blocked[it.id] ? " blocked" : ""}"
        data-node="item:${esc(it.id)}"
        style="left:${pos[`item:${it.id}`].x}px; top:${pos[`item:${it.id}`].y}px">
      <div class="cvhead"><b>${esc(it.id)} ${esc(it.name)}</b>
        <span class="cvsub">${esc(it.type)}</span></div>${rows}</div>`;
  }).join("");

  const root = cq("#canvas");
  root.innerHTML = `<svg id="cvwires"></svg>${docCard}${secCards}${itemCards}`;
  root.style.transform = `translate(${CV.pan.x}px, ${CV.pan.y}px) scale(${CV.zoom})`;
  cvWires(m);
  cvTable(m);
  cq("#cvhint").textContent =
    `조문 ${m.secs.length} · 항목 ${m.items.length} · 연결 ${m.links.length}`
    + " — 조문 포트를 끌어 항목에 놓으면 이어지고, 선을 누르면 끊깁니다";
}

function cvWires(m) {
  const svg = cq("#cvwires");
  const el = {};
  document.querySelectorAll(".cvrow").forEach((e) => {
    el[`${e.dataset.node}|${e.dataset.row}`] = e;
  });
  const root = cq("#canvas").getBoundingClientRect();
  const z = CV.zoom;
  const at = (e, side) => {
    const r = e.getBoundingClientRect();
    return { x: ((side === "r" ? r.right : r.left) - root.left) / z,
             y: (r.top + r.height / 2 - root.top) / z };
  };
  const curve = (p1, p2, cls, data = "") => {
    const dx = Math.max(50, (p2.x - p1.x) / 2);
    return `<path class="${cls}" ${data} d="M${p1.x},${p1.y} `
      + `C${p1.x + dx},${p1.y} ${p2.x - dx},${p2.y} ${p2.x},${p2.y}"/>`;
  };

  const out = [];
  const docOut = el[`doc:${S.doc}|__doc__`];
  for (const s of m.secs) {                      // 문서 ┄▸ 조문 (구조)
    const a = docOut, b = el[`sec:${s.id}|in`];
    if (a && b) out.push(curve(at(a, "r"), at(b, "l"), "struct"));
  }
  for (const l of m.links) {                     // 조문 ─▸ 항목 (근거)
    const sid = l.section_id || l.section;
    const a = el[`sec:${sid}|${sid}`], b = el[`item:${l.item}|${sid}`];
    if (!a || !b) continue;
    const cls = l.status === "AMBIGUOUS" ? "amb" : l.status === "RESOLVED" ? "" : "miss";
    out.push(curve(at(a, "r"), at(b, "l"), cls,
      `data-item="${esc(l.item)}" data-doc="${esc(l.doc)}" `
      + `data-section="${esc(l.section || "")}" data-term="${esc(l.term || "")}"`));
  }
  if (CV.wire) {
    out.push(curve({ x: CV.wire.x1, y: CV.wire.y1 },
                   { x: CV.wire.x2, y: CV.wire.y2 }, "ghost"));
  }
  const w = cq("#canvas").scrollWidth, h = cq("#canvas").scrollHeight;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.style.width = w + "px"; svg.style.height = h + "px";
  svg.innerHTML = out.join("");
}

/* ------------------------------------------------- 구조 테이블 (문서 클릭) */
/* 트리이면서 표다.
 *
 * 목록으로 555줄을 쭉 펴면 어느 조의 몇 호인지가 사라지고, 순수 트리로만 두면
 * 연결 수·본문 미리보기를 나란히 못 본다. 그래서 **행은 표, 첫 칸은 트리**다 —
 * 들여쓰기와 접기는 왼쪽 칸이 맡고 나머지 칸은 줄이 맞는다.
 *
 * 기본은 접힌 상태다. 555줄을 펼쳐 놓으면 스크롤만 남는다. */

function cvKids(sid) {
  return S.tree.filter((s) => s.parent === sid && s.kind !== "default");
}

/* 화면에 실제로 그릴 줄 — 펼쳐진 가지만 따라 내려간다. */
function cvVisible(q) {
  if (q) {
    // 찾을 때는 트리를 접지 않는다. 맞은 줄과 **그 조상**을 함께 보여야 어디의
    // 몇 호인지 알 수 있다.
    const byId = {};
    for (const s of S.tree) byId[s.section_id] = s;
    const keep = new Set();
    for (const s of S.tree) {
      if (s.kind === "default") continue;
      if (!(s.label + s.title + s.preview).replace(/\s/g, "").includes(q)) continue;
      let cur = s;
      while (cur && !keep.has(cur.section_id)) {
        keep.add(cur.section_id);
        cur = byId[cur.parent];
      }
    }
    return S.tree.filter((s) => keep.has(s.section_id));
  }
  const out = [];
  const walk = (parent) => {
    for (const s of S.tree.filter((x) => x.parent === parent && x.kind !== "default")) {
      out.push(s);
      if (CV.expand.has(s.section_id)) walk(s.section_id);
    }
  };
  walk(null);
  return out;
}

function cvTable(m) {
  const box = cq("#cvtable");
  if (CV.open !== S.doc) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const q = (cq("#cvq").value || "").trim().replace(/\s/g, "");
  const rows = cvVisible(q).slice(0, 600);
  const nLink = (sid) => m.links.filter((l) => (l.section_id || l.section) === sid).length;

  cq("#cvtbody").innerHTML = rows.map((s) => {
    const n = nLink(s.section_id);
    const on = CV.pinned.has(s.section_id) || n > 0;
    const kids = cvKids(s.section_id).length;
    const tw = kids
      ? `<span class="tw" data-tw="${esc(s.section_id)}">${CV.expand.has(s.section_id) ? "▾" : "▸"}</span>`
      : `<span class="tw leaf"></span>`;
    return `<tr class="${on ? "on" : ""}" data-sid="${esc(s.section_id)}">
      <td class="tree" style="padding-left:${6 + s.level * 15}px">${tw}
        <span class="lb">${esc(s.label)}</span>
        <span class="ti">${esc(s.title || "")}</span></td>
      <td class="pv">${esc(s.preview.slice(0, 110))}</td>
      <td class="kd">${kids ? `하위 ${kids}` : ""}</td>
      <td class="nn">${n || ""}</td>
      <td class="ac">
        ${s.parent ? `<button class="mini up" data-up="${esc(s.parent)}"
            title="상위 계층으로 — 조 전체를 근거로 삼을 때">↑상위</button>` : ""}
        ${kids ? `<button class="mini down" data-down="${esc(s.section_id)}"
            title="하위 계층 펼치기 — 특정 항·호만 근거로 삼을 때">↓하위</button>` : ""}
        <button class="mini pin" data-sid="${esc(s.section_id)}">${on ? "있음" : "이 계층으로"}</button>
      </td></tr>`;
  }).join("") || `<tr><td colspan="5" class="pv">일치하는 구역이 없습니다.</td></tr>`;

  cq("#cvcount").textContent =
    `${rows.length}${rows.length >= 600 ? "+" : ""} 줄 / 전체 ${S.tree.length}`
    + (q ? " (찾기 — 조상 포함)" : "");

  const body = cq("#cvtbody");
  body.querySelectorAll("[data-tw]").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const id = el.dataset.tw;
      CV.expand.has(id) ? CV.expand.delete(id) : CV.expand.add(id);
      cvTable(m);
    };
  });
  // 상위/하위로 **바로 옮겨 간다.** 조 전체를 근거로 삼을지 특정 호만 삼을지는
  // 항목마다 다르고, 그 판단을 여기서 한 번에 할 수 있어야 한다.
  body.querySelectorAll("[data-up]").forEach((el) => {
    el.onclick = (e) => { e.stopPropagation(); cvGoto(el.dataset.up, m); };
  });
  body.querySelectorAll("[data-down]").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      CV.expand.add(el.dataset.down);
      cvTable(m);
    };
  });
  body.querySelectorAll(".pin").forEach((el) => {
    el.onclick = (e) => { e.stopPropagation(); CV.pinned.add(el.dataset.sid); cvRender(); };
  });
  body.querySelectorAll("tr[data-sid]").forEach((tr) => {
    tr.onclick = () => { CV.pinned.add(tr.dataset.sid); cvRender(); };
  });
}

/* 그 구역이 보이도록 조상을 전부 펼치고 그 줄로 스크롤한다. */
function cvGoto(sid, m) {
  const byId = {};
  for (const s of S.tree) byId[s.section_id] = s;
  let cur = byId[sid];
  while (cur && cur.parent) { CV.expand.add(cur.parent); cur = byId[cur.parent]; }
  cq("#cvq").value = "";
  cvTable(m || cvModel());
  const row = cq(`#cvtbody tr[data-sid="${CSS.escape(sid)}"]`);
  if (row) {
    row.scrollIntoView({ block: "center", behavior: "smooth" });
    row.classList.add("flash");
    setTimeout(() => row.classList.remove("flash"), 900);
  }
}

/* ------------------------------------------------------------- 상호작용 */
function cvInit() {
  const wrap = cq("#cvwrap"), root = cq("#canvas");

  wrap.addEventListener("wheel", (e) => {
    if (e.target.closest("#cvtable")) return;
    e.preventDefault();
    CV.zoom = Math.min(2, Math.max(0.3, CV.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1)));
    cvRender();
  }, { passive: false });

  wrap.addEventListener("mousedown", (e) => {
    if (e.target.closest("#cvtable")) return;
    const rb = root.getBoundingClientRect();
    if (e.target.closest(".cvopen")) return;
    const port = e.target.closest(".cvrow.out");
    if (port && port.dataset.row !== "__doc__") {
      const r = port.getBoundingClientRect();
      CV.wire = { from: port.dataset.row,
                  x1: (r.right - rb.left) / CV.zoom,
                  y1: (r.top + r.height / 2 - rb.top) / CV.zoom, x2: 0, y2: 0 };
      e.preventDefault(); return;
    }
    const head = e.target.closest(".cvhead");
    if (head) {
      const card = head.closest(".cvcard");
      CV.drag = { id: card.dataset.node, sx: e.clientX, sy: e.clientY,
                  ox: parseFloat(card.style.left), oy: parseFloat(card.style.top) };
      e.preventDefault(); return;
    }
    CV.drag = { pan: true, sx: e.clientX, sy: e.clientY, ox: CV.pan.x, oy: CV.pan.y };
  });

  window.addEventListener("mousemove", (e) => {
    if (CV.wire) {
      const b = root.getBoundingClientRect();
      CV.wire.x2 = (e.clientX - b.left) / CV.zoom;
      CV.wire.y2 = (e.clientY - b.top) / CV.zoom;
      cvWires(cvModel());
      return;
    }
    if (!CV.drag) return;
    const dx = e.clientX - CV.drag.sx, dy = e.clientY - CV.drag.sy;
    if (CV.drag.pan) {
      CV.pan = { x: CV.drag.ox + dx, y: CV.drag.oy + dy };
      root.style.transform = `translate(${CV.pan.x}px, ${CV.pan.y}px) scale(${CV.zoom})`;
    } else {
      CV.moved[CV.drag.id] = { x: CV.drag.ox + dx / CV.zoom, y: CV.drag.oy + dy / CV.zoom };
      cvRender();
    }
  });

  window.addEventListener("mouseup", async (e) => {
    if (CV.wire) {
      const card = e.target.closest(".cvcard.item");
      const from = CV.wire.from;
      CV.wire = null;
      if (!card) return cvRender();
      const prev = S.item;
      S.item = card.dataset.node.slice("item:".length);
      await addLink(from);                       // 목록 보기와 같은 통로를 쓴다
      S.item = prev;
      cvRender();
      return;
    }
    CV.drag = null;
  });

  root.addEventListener("click", (e) => {
    if (e.target.closest(".cvopen")) {
      CV.open = CV.open === S.doc ? null : S.doc;
      return cvRender();
    }
    const p = e.target.closest("#cvwires path");
    if (p && !p.classList.contains("ghost") && !p.classList.contains("struct")) {
      cutLink({ item: p.dataset.item, doc: p.dataset.doc,
                section: p.dataset.section, term: p.dataset.term });
    }
  });

  cq("#cvq").addEventListener("input", () => cvTable(cvModel()));
  cq("#cvclose").onclick = () => { CV.open = null; cvRender(); };
}

function cvToggle(on) {
  CV.on = on;
  const rw = document.getElementById('runwrap');
  if (rw) rw.classList.add('hidden');   // 실행 화면과 겹치지 않게

  cq("#cvwrap").classList.toggle("hidden", !on);
  cq("main.cols").classList.toggle("hidden", on);
  cq("#tab-list").classList.toggle("on", !on);
  cq("#tab-canvas").classList.toggle("on", on);
  if (on) {
    if (!S.doc && S.corpora.length) return loadTree(S.corpora[0].id).then(cvRender);
    cvRender();
  }
}
