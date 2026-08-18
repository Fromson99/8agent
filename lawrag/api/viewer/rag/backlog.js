/* 판정·교정 백로그 카드 — 질의응답·디버깅 화면 공용.
 *
 * 카드 머리를 누르면 토글로 펼쳐진다:
 *   · 무엇을 승인하는 건지 설명 한 줄 (억제 = 이 연결을 답변 검색에서 제외)
 *   · 간선 경로 — 출발/도착을 누르면 PDF 패널에 그 자리(앵커)가 뜬다
 *   · 이 판단을 만든 질의들 — 칩을 누르면 카드 안에서 Q/A 가 바로 스위칭:
 *     질문 → 주입 프롬프트(지식이 어떻게 들어갔나) → 답 전문 → 회수 구역
 *
 * 전역 $, esc, api 는 화면 스크립트가, ppTail·data-pp 패널은 pdfpane.js 가 준다. */
"use strict";

const bkClip = (s, n) => (String(s).length > n ? String(s).slice(0, n) + "…" : String(s));

function bkMount(els) {
  const BK = { data: null, tuples: new Map() };

  async function refresh(shared) {
    // shared(디버깅 화면의 /debug 응답)를 주면 그대로 쓰고, 없으면 직접 부른다.
    const d = shared || await api("/v1/rag/debug?limit=300");
    BK.data = d.backlog || {};
    BK.tuples = new Map((d.tuples || []).map((t) => [t.qid, t]));
    render();
  }

  /* ---------------------------------------------------------- Q/A 블록 */
  function qa(qid) {
    const t = BK.tuples.get(qid);
    if (!t) return `<div class="sub">질의 기록을 찾지 못했습니다 — 오래된 기록일 수 있습니다</div>`;
    const ctx = (t.context || []).map((c) => `
      <div class="ctxrow">
        <span class="n">[${c.n}]</span>
        <span class="badge ${c.kind === "벡터" ? "warn" : ""}">${esc(c.kind || "?")}</span>
        ${c.node != null ? `<a class="pplink q" data-pp data-doc="${esc(c.doc_id)}"
             data-node="${c.node}" data-label="${esc(ppTail(c.path || ""))}"
             title="${esc(c.doc || "")} ▸ ${esc(c.path || "")}">${esc(c.doc || "")} ▸ ${esc(c.path || "")}</a>`
          : `<span class="q">${esc(c.doc || "")} ▸ ${esc(c.path || "")}</span>`}
      </div>`).join("");
    return `
      <div class="bkq"><span class="plabel">질문</span> ${esc(t.질의)}</div>
      ${t.프롬프트 ? `
        <details class="bkprompt">
          <summary>주입 프롬프트 — 지식이 어떻게 들어갔나 (system + 질문/컨텍스트)</summary>
          <div class="plabel">system</div>
          <pre>${esc(t.프롬프트.system || "")}</pre>
          <div class="plabel">user — [질문] + [컨텍스트]</div>
          <pre>${esc(t.프롬프트.user || "")}</pre>
        </details>` : `<div class="sub">프롬프트 기록 없음 — 저장 이전의 질의</div>`}
      <div class="plabel" style="margin-top:6px">답 전문
        ${t.answerable === false ? '<span class="badge warn">답없음</span>' : ""}</div>
      <div class="bka">${esc(t.답 || "(답 기록 없음 — 저장 이전의 질의)")}</div>
      <div class="plabel" style="margin-top:6px">회수 구역 — 누르면 PDF 로</div>
      ${ctx || `<span class="sub">회수 기록 없음</span>`}`;
  }

  /* 질의 칩 줄 + 스위칭 영역. 질의들 = [{qid, 질의, ts}] — qid 코드가 아니라
   * 질문 글자가 라벨이다. */
  function qtabs(qlist) {
    const qs = (qlist || []).filter((x) => x && x.qid);
    if (!qs.length) return `<div class="sub">질의 기록 없음</div>`;
    return `
      <div class="plabel">이 판단이 나온 질의 ${qs.length}건 — 누르면 아래에서 Q/A 가 바뀝니다</div>
      <div class="bktabs">${qs.map((x, j) => `
        <span class="tchip bkq-tab${j === 0 ? " cur" : ""}" data-qid="${esc(x.qid)}"
              title="${esc(x.질의)} (${esc((x.ts || "").slice(5, 16).replace("T", " "))})">
          ${esc(bkClip(x.질의 || x.qid, 38))}</span>`).join("")}
      </div>
      <div class="bkqa">${qa(qs[0].qid)}</div>`;
  }

  function wireCard(card) {
    const head = card.querySelector(".bkhead");
    const body = card.querySelector(".bkbody");
    head.onclick = (ev) => {
      if (ev.target.closest("button") || ev.target.closest("[data-pp]")) return;
      body.classList.toggle("hidden");
    };
    card.querySelectorAll(".bkq-tab").forEach((ch) => {
      ch.onclick = () => {
        card.querySelectorAll(".bkq-tab").forEach((x) => x.classList.remove("cur"));
        ch.classList.add("cur");
        card.querySelector(".bkqa").innerHTML = qa(ch.dataset.qid);
      };
    });
  }

  /* tone: "bad" = 잘못된 연결의 끝(빨강), "ok" = 제안된 옳은 자리(초록),
   * "" = 평범한 좌표(파랑). 색이 곧 "무엇이 잘못됐나"의 답이다 — PDF 패널의
   * 앵커 상자도 같은 색으로 뜬다. */
  function pathLink(doc, node, path, tone, tip) {
    const cls = tone === "bad" ? "pplink bad" : tone === "ok" ? "pplink ok" : "pplink";
    return node != null
      ? `<a class="${cls}" data-pp data-doc="${esc(doc)}" data-node="${node}"
           data-tone="${esc(tone || "")}" data-label="${esc(ppTail(path || ""))}"
           title="${esc(tip || "누르면 PDF 로")}">${esc(path || doc)}</a>`
      : esc(path || doc || "");
  }

  async function act(url, body, btn) {
    btn.disabled = true;
    try {
      await api(url, { method: "POST",
                       headers: { "content-type": "application/json" },
                       body: JSON.stringify(body) });
      sessionStorage.removeItem("ui-queue-counts");   // 상단바 배지 즉시 갱신
    } catch (err) { alert("처리 실패: " + err.message); }
    refresh();
  }

  /* ---------------------------------------------------------- 카드들 */
  function edgeCard(g, i) {
    const e = g.edge || {};
    const kinds = Object.entries(g.판정 || {}).map(([k, n]) => `${k} ${n}`).join(" · ");
    return `<div class="bk sup" data-i="${i}">
      <div class="bkhead">
        <span class="badge ${g.판정 && g.판정["오참조"] ? "bad" : "warn"}">${esc(kinds)}</span>
        <span class="q">${esc(ppTail(e.src_path) || e.src_doc)} → ${esc(ppTail(e.dst_path) || e.dst_doc)}
          <i class="sub">(${esc(e.surface || "")})</i></span>
        <span class="sub">▾ 펼치기</span>
      </div>
      <div class="bkbody hidden">
        <div class="bkhint">LLM 판단: 아래 질의에서 이 <b>연결(간선)</b>을 타고 온 구역이
          잘못 끌려왔다. <b>억제 승인</b> = 앞으로 답변 검색이 이 연결을 타지 않게 하는
          규칙을 만든다(간선 자체는 남는다). <b>기각</b> = 연결 유지, 이 판단만 닫는다.</div>
        <div class="bkpath">
          <span class="plabel">참조가 쓰인 자리</span>
          ${pathLink(e.src_doc, e.src, e.src_path, "bad",
                     "잘못됐다고 판정된 연결의 출발 — 누르면 PDF 로")}
          <span class="arrow bad">─ ${esc(e.surface || "")} →</span>
          <span class="plabel">잘못 끌려온 구역</span>
          ${pathLink(e.dst_doc, e.dst, e.dst_path, "bad",
                     "이 구역이 잘못 끌려왔다는 판정 — 누르면 PDF 로")}
        </div>
        <div class="sub">LLM 사유: ${esc((g.사유 || [])[0] || "")}</div>
        <div class="acts">
          <button class="yes sup" data-act="승인">억제 승인 — 이 연결 안 쓰기</button>
          <button class="no" data-act="기각">기각 — 연결 유지</button>
        </div>
        ${qtabs(g.질의들)}
      </div>
    </div>`;
  }

  function fixCard(g, i) {
    const e = g.edge || {};
    return `<div class="bk fix" data-i="${i}">
      <div class="bkhead">
        <span class="badge">교정 ${g.n}회</span>
        <span class="q">${esc(ppTail(e.dst_path))} <span class="arrow">⤷</span>
          <b>${esc(ppTail(g.new_dst_path))}</b>
          <i class="sub">(${esc(e.surface || "")})</i></span>
        <span class="sub">▾ 펼치기</span>
      </div>
      <div class="bkbody hidden">
        <div class="bkhint">LLM 판단: "${esc(e.surface || "")}" 참조의 착지가 얕다 —
          아래 새 좌표가 맞다. <b>재지정 승인</b> = 간선의 도착을 새 좌표로 옮기는
          규칙을 만든다(다음 질의부터 적용). <b>기각</b> = 제안만 닫는다.</div>
        <div class="bkpath">
          <span class="plabel">참조가 쓰인 자리</span>
          ${pathLink(e.src_doc, e.src, e.src_path, "", "참조가 쓰인 구역")}
          <span class="arrow">─ ${esc(e.surface || "")} →</span>
          <span class="plabel">지금 착지(얕음)</span>
          ${pathLink(e.dst_doc, e.dst, e.dst_path, "bad", "얕게 멈춘 착지 — 누르면 PDF 로")}
          <span class="arrow">⤷</span>
          <span class="plabel">제안된 자리</span>
          ${pathLink(e.dst_doc, g.new_dst, g.new_dst_path, "ok", "LLM 이 제안한 옳은 자리")}
        </div>
        <div class="sub">LLM 사유: ${esc((g.사유 || [])[0] || "")}</div>
        <div class="acts">
          <button class="yes" data-act="승인">재지정 승인 — 새 좌표로 옮김</button>
          <button class="no" data-act="기각">기각 — 제안 닫기</button>
        </div>
        ${qtabs(g.질의들)}
      </div>
    </div>`;
  }

  /* 구조화오류 — 간선이 아니라 **문서의 계층**이 틀렸다는 판정. 억제·교정으로
   * 고칠 수 없고, 검수 화면에서 계층을 옮겨야 한다(그래서 버튼이 그리로 간다). */
  function structCard(g, i) {
    const s = g.구역 || {};
    const link = `/structure/?doc=${encodeURIComponent(s.doc_id || "")}`
      + (s.node != null ? `&node=${s.node}` : "");
    return `<div class="bk st" data-si="${i}">
      <div class="bkhead">
        <span class="badge bad">구조화오류</span>
        <span class="q">${esc(s.doc || "")} ▸ ${esc(ppTail(s.path || ""))}
          <i class="sub">${esc(bkClip(g.사유?.[0] || "", 44))}</i></span>
        <span class="sub">${g.n}회 · ▾ 펼치기</span>
      </div>
      <div class="bkbody hidden">
        <div class="bkhint">LLM 판단: 이 구역의 <b>계층이 원문과 어긋난다</b>.
          우리 구조 해석이 마디를 잘못 매단 것이라 연결(간선)로는 고칠 수 없다 —
          검수 화면에서 <b>계층 교정</b>(내어쓰기·들여쓰기)을 하거나, 같은 어긋남이
          문서군 전체에 있으면 <b>구조화 틀의 마커</b>를 고친다.</div>
        <div class="bkpath">
          <span class="plabel">계층이 이상한 구역</span>
          ${pathLink(s.doc_id, s.node, `${s.doc || ""} ▸ ${s.path || ""}`, "",
                     "누르면 PDF 로")}
        </div>
        ${(g.사유 || []).map((r) => `<div class="sub">LLM 사유: ${esc(r)}</div>`).join("")}
        <div class="acts">
          <a class="btnlink" href="${link}" target="_blank"
             title="검수 화면에서 그 마디를 열어 계층을 옮긴다">검수 화면에서 고치기 →</a>
          <button class="yes" data-sact="고침">고쳤음 — 닫기</button>
          <button class="no" data-sact="무시">무시 — 문제 아님</button>
        </div>
        ${qtabs((g.질의들 || []).slice(-5))}
      </div>
    </div>`;
  }

  /* 회수 결함(참조무관·검색무관) — **억제 버튼이 없다.** 좌표가 맞는데 이번
   * 질문에 안 맞았을 뿐이라 연결을 지우면 옳은 참조를 영영 잃는다. 대신 둘:
   *   후순위   그 간선을 확장 자리 경쟁에서 뒤로 민다 (참조무관)
   *   진입제외 그 좌표를 벡터·용어 진입에서만 뺀다 (검색무관 — 참조로는 온다) */
  function missCard(g, i) {
    const s = g.구역 || {};
    const e = g.간선;
    const isSearch = g.판정 === "검색무관" || !e;
    return `<div class="bk ms" data-mi="${i}">
      <div class="bkhead">
        <span class="badge warn">${esc(g.판정 || "무관")}</span>
        <span class="q">${esc(s.doc || "")} ▸ ${esc(ppTail(s.path || ""))}
          <i class="sub">${esc(bkClip(g.사유?.[0] || "", 40))}</i></span>
        <span class="sub">${g.n}회 · ▾ 펼치기</span>
      </div>
      <div class="bkbody hidden">
        <div class="bkhint">${isSearch
          ? `<b>진입 검색</b>(벡터·용어)이 이 구역을 데려왔는데 질문과 무관했다.
             <b>진입 제외</b> = 앞으로 이 좌표를 진입으로 데려오지 않는다
             (참조를 타고는 여전히 온다 — 연결 지식은 그대로다).`
          : `<b>참조 확장</b>이 데려왔고 <b>연결 자체는 옳다</b>. 그래서 억제(삭제)
             버튼이 없다. <b>후순위</b> = 자리 경쟁에서 뒤로 민다 — 자리가 남으면
             여전히 온다.`}</div>
        <div class="bkpath">
          ${e ? `<span class="plabel">참조가 쓰인 자리</span>
                 ${pathLink(e.src_doc, e.src, e.src_path, "", "연결은 옳다 — 누르면 PDF 로")}
                 <span class="arrow">─ ${esc(e.surface || "")} →</span>` : ""}
          <span class="plabel">이 질문엔 무관한 구역</span>
          ${pathLink(s.doc_id, s.node, `${s.doc || ""} ▸ ${s.path || ""}`, "", "누르면 PDF 로")}
        </div>
        ${(g.사유 || []).map((r) => `<div class="sub">LLM 사유: ${esc(r)}</div>`).join("")}
        <div class="acts">
          ${e ? `<button class="yes" data-mact="후순위">후순위 — 뒤로 밀기</button>` : ""}
          <button class="yes" data-mact="진입제외">진입 제외 — 검색으로 안 데려오기</button>
          <button class="no" data-mact="정상">정상 — 문제 아님</button>
        </div>
        ${qtabs((g.질의들 || []).slice(-5))}
      </div>
    </div>`;
  }

  /* ---------------------------------------------------------- 그리기 */
  function render() {
    const bl = BK.data;
    const edges = bl.edges || [], fixes = bl.fixes || [];
    const struct = bl.struct || [], misses = bl.misses || [], miss = bl.miss || {};

    if (els.stats) els.stats.textContent =
      `오참조 ${edges.length} · 구조화오류 ${struct.length} · 회수 결함 ${misses.length}`
      + (miss.검색무관 || miss.참조무관
         ? ` (검색 ${miss.검색무관 || 0} · 참조 ${miss.참조무관 || 0})` : "")
      + ` │ 규칙 — 억제 ${bl.suppressed ?? 0} · 재지정 ${bl.redirected ?? 0}`
      + ` · 후순위 ${bl.demoted ?? 0} · 진입제외 ${bl.entry_blocked ?? 0}`
      + ` · 처리 ${bl.resolved ?? 0}`;
    if (els.fixStats) els.fixStats.textContent =
      `대기 ${fixes.length}건 · 재지정 규칙 ${bl.redirected ?? 0}`;

    const edgesHtml =
      (edges.length
        ? `<div class="sub" style="margin:0 0 5px">오참조 — 참조 해소가 좌표를 틀렸다는
             판정. 승인하면 그 연결을 안 쓴다 — 억제된 간선은
             <a class="qlink" href="/links/">참조 화면</a>과 질의 확장에서 빠진다.</div>`
          + edges.map(edgeCard).join("")
        : `<span class="sub">억제 대기 중인 오참조 간선이 없습니다</span>`)
      + (struct.length ? `<div class="sub" style="margin:12px 0 5px">구조화오류 —
          실린 구역의 계층이 원문과 어긋난다는 판정 (${struct.length}곳) ·
          고칠 자리는 검수 화면의 계층 교정이다</div>`
          + struct.map(structCard).join("") : "")
      + (misses.length ? `<div class="sub" style="margin:12px 0 5px">회수 결함 —
          좌표는 맞는데 이번 질문에 안 맞은 것 (${misses.length}곳) · 연결은 지우지 않는다.
          <b>검색무관</b>은 진입 검색(벡터·용어)이, <b>참조무관</b>은 참조 확장이 빗나간 것이다</div>`
          + misses.map(missCard).join("") : "");
    const fixesHtml =
      fixes.map(fixCard).join("") || `<span class="sub">대기 중인 교정 제안이 없습니다</span>`;

    if (els.fixes) {
      els.edges.innerHTML = edgesHtml;
      els.fixes.innerHTML = fixesHtml;
    } else {
      els.edges.innerHTML =
        (fixes.length ? `<div class="sub" style="margin:0 0 5px">착지 교정 제안</div>` + fixesHtml : "")
        + edgesHtml;
    }

    [els.edges, els.fixes].filter(Boolean).forEach((box) => {
      box.querySelectorAll(".bk").forEach(wireCard);
      box.querySelectorAll(".bk.sup button[data-act]").forEach((b) => {
        b.onclick = () => {
          const g = edges[+b.closest(".bk").dataset.i];
          const e = g.edge || {};
          act("/v1/rag/verdicts/resolve",
              { src_doc: e.src_doc, src: e.src, dst_doc: e.dst_doc, dst: e.dst,
                src_path: e.src_path || "", dst_path: e.dst_path || "",
                action: b.dataset.act }, b);
        };
      });
      box.querySelectorAll(".bk.fix button[data-act]").forEach((b) => {
        b.onclick = () => {
          const g = fixes[+b.closest(".bk").dataset.i];
          const e = g.edge || {};
          act("/v1/rag/fixes/resolve",
              { src_doc: e.src_doc, src: e.src, dst_doc: e.dst_doc, dst: e.dst,
                new_dst: g.new_dst, src_path: e.src_path || "",
                dst_path: e.dst_path || "", new_dst_path: g.new_dst_path || "",
                surface: e.surface || "", action: b.dataset.act }, b);
        };
      });
      // 회수 결함 — 후순위/진입제외/정상 (억제 없음)
      box.querySelectorAll(".bk.ms button[data-mact]").forEach((b) => {
        b.onclick = () => {
          const g = misses[+b.closest(".bk").dataset.mi];
          act("/v1/rag/verdicts/miss",
              { 판정: g.판정, 구역: g.구역, 간선: g.간선,
                action: b.dataset.mact }, b);
        };
      });
      // 구조화오류 — 여기서는 닫기만 한다(고치는 자리는 검수 화면)
      box.querySelectorAll(".bk.st button[data-sact]").forEach((b) => {
        b.onclick = () => {
          const g = struct[+b.closest(".bk").dataset.si];
          act("/v1/rag/verdicts/struct",
              { 구역: g.구역, action: b.dataset.sact }, b);
        };
      });
    });
  }

  return { refresh };
}
