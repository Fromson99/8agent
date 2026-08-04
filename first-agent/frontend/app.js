/* 신탁 대사 뷰어 — React + htm (빌드 도구 없이 동작).
   데이터는 build_viewer.py 가 window.__BUNDLE__ 로 인라인해 넣는다. */
(function () {
  "use strict";
  const { useState, useMemo, useCallback } = React;
  const html = htm.bind(React.createElement);
  const B = window.__BUNDLE__;

  /* ---------- 유틸 ---------- */
  const pct = (n) => (n == null ? "—" : (Number(n) * 100).toFixed(0) + "%");
  const truncate = (s, n) => {
    const t = (s || "").replace(/\s+/g, " ").trim();
    return t.length > n ? t.slice(0, n) + "…" : t;
  };
  const VERDICT_KO = {
    match: "일치", mismatch: "불일치", uncertain: "불확실",
    missing_side: "한쪽 없음", unpaired: "짝 없음", missing: "누락",
    ok: "충족", not_applicable: "해당없음", suggestion: "제안",
  };

  const Verdict = ({ v }) =>
    html`<span class=${"verdict v-" + v}>${VERDICT_KO[v] || v}</span>`;

  const Meter = ({ value }) => html`
    <span class="meter">
      <span class="meter__bar"><span class="meter__fill" style=${{ width: Math.max(0, Math.min(1, value || 0)) * 100 + "%" }}></span></span>
      <span class="meter__val">${pct(value)}</span>
    </span>`;

  const Panel = ({ title, right, flush, children }) => html`
    <section class="panel">
      ${title && html`<header class="panel__head">
        <h3 class="panel__title">${title}</h3>${right}
      </header>`}
      <div class=${"panel__body" + (flush ? " panel__body--flush" : "")}>${children}</div>
    </section>`;

  const Empty = ({ children }) => html`<p class="empty">${children}</p>`;

  const Seg = ({ options, value, onChange }) => html`
    <div class="seg" role="group">
      ${options.map((o) => html`
        <button key=${o.value} aria-pressed=${String(value === o.value)}
                onClick=${() => onChange(o.value)}>${o.label}</button>`)}
    </div>`;

  /* ---------- 개요 ---------- */
  function Overview() {
    const r = B.report, s = r.summary;
    const acts = r.findings.filter((f) => f.type !== "suggestion");
    const sugg = r.findings.filter((f) => f.type === "suggestion");
    return html`
      <${Panel} title="파이프라인">
        <div class="flow">
          <span class="flow__node"><b>P1</b> 파싱<br/><small>${B.parsed.contract.parser}</small></span>
          <span class="flow__arrow">→</span>
          <span class="flow__node flow__node--llm"><b>P2</b> 태깅<br/><small>섹션 ${B.tagged.contract.sections.length} / ${B.tagged.statement.sections.length}</small></span>
          <span class="flow__arrow">→</span>
          <span class="flow__node flow__node--llm"><b>P3</b> 1단계 대응<br/><small>쌍 ${s.pairs}</small></span>
          <span class="flow__arrow">→</span>
          <span class="flow__node"><b>P4</b> 2단계 비교<br/><small>요소 ${s.elements_compared}</small></span>
          <span class="flow__arrow">→</span>
          <span class="flow__node"><b>P5</b> 완결성·리포트<br/><small>필수 ${s.required}</small></span>
        </div>
        <p class="foot">파란 테두리 = LLM 이 판단하는 단계. 나머지는 결정론적 코드다.</p>
      <//>

      ${r.warnings.length > 0 && html`
        <${Panel} title=${`경고 ${r.warnings.length}건`}>
          <div class="warnlist">
            ${r.warnings.map((w, i) => html`<div class="warnitem" key=${i}><span>${w}</span></div>`)}
          </div>
        <//>`}

      <${Panel} title=${`조치 필요 ${acts.length}건`} flush=${true}>
        ${acts.length === 0
          ? html`<${Empty}>이상 없음<//>`
          : html`<div class="tablewrap"><table>
              <thead><tr>
                <th>심각도</th><th>유형</th><th>항목</th>
                <th class="cell-wide">계약서</th><th class="cell-wide">설명서</th><th>판정 근거</th>
              </tr></thead>
              <tbody>${acts.map((f, i) => html`
                <tr key=${i}>
                  <td><span class=${"sev sev--" + f.severity}>${f.severity}</span></td>
                  <td><${Verdict} v=${f.type} /></td>
                  <td>${f.display || f.tag}<br/><span class="cell-code">${f.tag}</span></td>
                  <td class="cell-code">${truncate(f.detail.contract_value, 90) || "—"}</td>
                  <td class="cell-code">${truncate(f.detail.statement_value, 90) || "—"}</td>
                  <td>${truncate(f.detail.reason || f.detail.evidence || f.detail.why, 160)}
                    ${f.detail.method && html`<br/><span class="cell-code">${f.detail.method}</span>`}</td>
                </tr>`)}</tbody></table></div>`}
      <//>

      ${sugg.length > 0 && html`
        <${Panel} title=${`스키마 추가 제안 ${sugg.length}건`} flush=${true}>
          <div class="tablewrap"><table>
            <thead><tr><th>제안 id</th><th>내용</th><th>발견 문서</th><th>이유</th></tr></thead>
            <tbody>${sugg.map((f, i) => html`<tr key=${i}>
              <td class="cell-code">${f.tag || "—"}</td><td>${f.display}</td>
              <td>${f.detail.doc_role === "contract" ? "계약서" : "설명서"}</td>
              <td>${truncate(f.detail.why, 140)}</td></tr>`)}</tbody>
          </table></div>
          <p class="foot" style=${{ padding: "10px 16px" }}>
            선언(tag_schema.json)에 없지만 문서에 있던 사안이다. 버리지 않고 올려 두니 사람이 스키마에 추가할지 판단하면 된다.
          </p>
        <//>`}`;
  }

  /* ---------- P1 파싱 ---------- */
  function ParseView() {
    const [side, setSide] = useState("contract");
    const doc = B.parsed[side];
    const [kind, setKind] = useState("all");
    const kinds = useMemo(() => ["all", ...Array.from(new Set(doc.blocks.map((b) => b.kind)))], [doc]);
    const rows = doc.blocks.filter((b) => kind === "all" || b.kind === kind);
    return html`
      <${Panel} title="파싱 통계" right=${html`<${Seg} value=${side} onChange=${setSide}
        options=${[{ value: "contract", label: "계약서" }, { value: "statement", label: "설명서" }]} />`}>
        <dl class="kv">
          <dt>파서</dt><dd class="cell-code">${doc.parser}</dd>
          <dt>원본</dt><dd class="cell-code">${doc.source_path}</dd>
          <dt>형식</dt><dd>${doc.source_format}</dd>
          <dt>블록</dt><dd>${doc.blocks.length}개 (표 ${doc.stats.tables ?? 0}개)</dd>
          ${doc.stats.docling_texts != null && html`<dt>도클링</dt>
            <dd>texts ${doc.stats.docling_texts} · tables ${doc.stats.docling_tables} ·
                머리말/꼬리말 제거 ${doc.stats.dropped_header_footer}</dd>`}
          ${doc.stats.pdfplumber_tables != null && html`<dt>pdfplumber 보완</dt>
            <dd>표 ${doc.stats.pdfplumber_tables}개</dd>`}
          <dt>기준일</dt><dd>${doc.meta.version_date || "미확인"}</dd>
          <dt>발행사</dt><dd>${doc.meta.issuer || "미확인"}</dd>
          <dt>상품유형</dt><dd>${doc.meta.product_type || "—"}</dd>
        </dl>
        ${doc.warnings.length > 0 && html`<div class="warnlist" style=${{ marginTop: "12px" }}>
          ${doc.warnings.map((w, i) => html`<div class="warnitem" key=${i}><span>${w}</span></div>`)}
        </div>`}
      <//>

      <${Panel} title=${`블록 ${rows.length} / ${doc.blocks.length}`} flush=${true}
        right=${html`<${Seg} value=${kind} onChange=${setKind}
          options=${kinds.map((k) => ({ value: k, label: k === "all" ? "전체" : k }))} />`}>
        <div class="blocklist">
          ${rows.map((b) => html`
            <div class="blockrow" key=${b.block_id}>
              <span class=${"kind kind--" + b.kind}>${b.kind}</span>
              <span class="blockrow__page">p.${b.provenance.page ?? "—"}</span>
              <div class="blockrow__text">
                ${b.kind === "table" && b.table
                  ? html`<div class="tablewrap"><table><tbody>
                      ${b.table.map((row, ri) => html`<tr key=${ri}>
                        ${row.map((c, ci) => html`<td key=${ci}>${c}</td>`)}</tr>`)}
                    </tbody></table></div>`
                  : b.text}
              </div>
            </div>`)}
        </div>
      <//>`;
  }

  /* ---------- P2 태깅 ---------- */
  function TagView() {
    const [side, setSide] = useState("contract");
    const doc = B.tagged[side];
    const parsed = B.parsed[side];
    const blockById = useMemo(() => {
      const m = {}; parsed.blocks.forEach((b) => (m[b.block_id] = b)); return m;
    }, [parsed]);
    const tagDisplay = useMemo(() => {
      const m = {}; B.schema.sections.forEach((s) => (m[s.id] = s.display)); return m;
    }, []);
    return html`
      <${Panel} title=${`섹션 ${doc.sections.length}개`}
        right=${html`<${Seg} value=${side} onChange=${setSide}
          options=${[{ value: "contract", label: "계약서" }, { value: "statement", label: "설명서" }]} />`}>
        <p class="foot">섹션은 파서가 나눈 것이 아니라 <b>같은 메인 태그가 붙은 연속 블록</b>이다.
          제목이 없거나 서로 같아도 본문 내용으로 갈린다.</p>
      <//>
      <div class="cards">
        ${doc.sections.map((s) => html`
          <article class="card" key=${s.section_id}>
            <header class="card__head">
              <span class="card__tag">${s.tag}</span>
              <span class="card__title">${tagDisplay[s.tag] || s.tag}</span>
              ${s.title && html`<span class="cell-code">${s.title}</span>`}
              <span class="card__meta">블록 ${s.block_ids.length} · p.${s.provenance.page ?? "—"} · <${Meter} value=${s.tag_confidence} /></span>
            </header>
            <div class="card__body">
              ${s.rationale && html`<p style=${{ margin: "0 0 10px", color: "var(--muted)", fontSize: "12.5px" }}>${s.rationale}</p>`}
              ${s.terms.length > 0 && html`<p class="foot" style=${{ marginBottom: "10px" }}>
                용어: ${s.terms.map((t) => html`<span class="cell-code" key=${t}>${t} </span>`)}</p>`}
              ${s.elements.length === 0
                ? html`<p class="foot">추출된 세부 요소 없음</p>`
                : html`<div class="tablewrap"><table>
                    <thead><tr><th>세부 요소</th><th>유형</th><th>원문</th><th>구조화된 값</th><th class="num">확신도</th></tr></thead>
                    <tbody>${s.elements.map((e) => html`<tr key=${e.element_id}>
                      <td>${e.display}<br/><span class="cell-code">${e.element_id}</span></td>
                      <td><span class="kind">${e.value.value_type}</span></td>
                      <td class="cell-code">${truncate(e.value.raw, 110) || "—"}</td>
                      <td><code class="raw data-json">${JSON.stringify(e.value.data)}</code></td>
                      <td class="num">${pct(e.confidence)}</td></tr>`)}
                    </tbody></table></div>`}
              <details style=${{ marginTop: "10px" }}>
                <summary class="foot" style=${{ cursor: "pointer" }}>원본 블록 ${s.block_ids.length}개</summary>
                <div class="blocklist" style=${{ marginTop: "8px" }}>
                  ${s.block_ids.map((id) => {
                    const b = blockById[id];
                    return html`<div class="blockrow" key=${id} style=${{ padding: "6px 0" }}>
                      <span class=${"kind kind--" + (b ? b.kind : "")}>${b ? b.kind : "?"}</span>
                      <span class="blockrow__page">p.${b?.provenance.page ?? "—"}</span>
                      <span class="blockrow__text">${b ? truncate(b.text || (b.table || []).map((r) => r.join(" | ")).join(" / "), 220) : id}</span>
                    </div>`;
                  })}
                </div>
              </details>
            </div>
          </article>`)}
      </div>`;
  }

  /* ---------- 큰 요소 → 세부 요소 (핵심 화면) ---------- */
  const ROLE_KO = { value: "실제 값", provision: "관련 조항", explanation: "설명 서술" };
  const ROLE_CLASS = { value: "v-match", provision: "v-idle", explanation: "v-uncertain" };

  function ElementView() {
    const schemaById = useMemo(() => {
      const m = {}; B.schema.sections.forEach((s) => (m[s.id] = s)); return m;
    }, []);
    const byTag = useMemo(() => {
      const m = {};
      const touch = (t) => (m[t] = m[t] || { contract: [], statement: [], comps: [] });
      ["contract", "statement"].forEach((side) =>
        B.tagged[side].sections.forEach((s) => { if (s.tag) { touch(s.tag); m[s.tag][side].push(s); } }));
      B.report.comparisons.forEach((c) => { if (c.tag) { touch(c.tag); m[c.tag].comps.push(c); } });
      return m;
    }, []);
    const tags = Object.keys(byTag).sort((a, b) => {
      const bad = (t) => byTag[t].comps.some((c) => c.verdict === "mismatch") ? 0 : 1;
      return bad(a) - bad(b) || a.localeCompare(b);
    });
    const [tag, setTag] = useState(tags[0]);
    const g = byTag[tag] || { contract: [], statement: [], comps: [] };
    const spec = schemaById[tag] || {};

    const SideCol = ({ label, sections }) => html`
      <div>
        <div class="pair__role" style=${{ marginBottom: "8px" }}>${label}</div>
        ${sections.length === 0 ? html`<${Empty}>이 문서에는 없음<//>` : sections.map((s) => html`
          <div class="card" key=${s.section_id} style=${{ marginBottom: "8px" }}>
            <header class="card__head">
              <span class=${"verdict " + (ROLE_CLASS[s.role] || "v-idle")}>${ROLE_KO[s.role] || s.role}</span>
              <span class="card__title">${s.title || "(제목 없음)"}</span>
              <span class="card__meta">p.${s.provenance.page ?? "—"} · <${Meter} value=${s.tag_confidence} /></span>
            </header>
            <div class="card__body">
              ${s.elements.length === 0
                ? html`<p class="foot">세부 요소 없음 — 값이 아니라 규정만 담긴 섹션이다.</p>`
                : html`<dl class="kv">${s.elements.map((e) => html`<${React.Fragment} key=${e.element_id}>
                    <dt>${e.display}</dt>
                    <dd><code class="raw">${e.value.raw || "—"}</code>
                      <div class="foot">${JSON.stringify(e.value.data)}</div></dd>
                  <//>`)}</dl>`}
            </div>
          </div>`)}
      </div>`;

    return html`
      <${Panel} title=${`큰 요소 ${tags.length}개 — 하나를 고르면 세부 요소 비교가 열린다`}>
        <div style=${{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          ${tags.map((t) => {
            const bad = byTag[t].comps.filter((c) => c.verdict === "mismatch").length;
            const unc = byTag[t].comps.filter((c) => c.verdict === "uncertain" || c.verdict === "missing_side").length;
            return html`<button class="navitem" key=${t} aria-current=${String(t === tag)}
              onClick=${() => setTag(t)}
              style=${{ width: "auto", padding: "5px 11px", border: "1px solid var(--rule)",
                        borderRadius: "var(--r)", borderLeftWidth: "1px",
                        display: "inline-flex", gap: "7px" }}>
              <span>${schemaById[t]?.display || t}</span>
              ${bad > 0 && html`<span class="verdict v-mismatch">${bad}</span>`}
              ${bad === 0 && unc > 0 && html`<span class="verdict v-uncertain">${unc}</span>`}
              ${bad === 0 && unc === 0 && html`<span class="verdict v-match">✓</span>`}
            </button>`;
          })}
        </div>
      <//>

      <${Panel} title=${`${spec.display || tag} — 문서가 어떻게 쪼개졌나`}>
        <p class="foot" style=${{ marginBottom: "14px" }}>
          같은 큰 요소라도 계약서 안에서 <b>관련 조항</b>과 <b>실제 값</b>으로 갈린다.
          값 비교는 실제 값·설명 서술에서만 하고, 관련 조항은 근거로 붙는다.
        </p>
        <div class="grid2">
          <${SideCol} label="신탁계약서" sections=${g.contract} />
          <${SideCol} label="핵심상품설명서" sections=${g.statement} />
        </div>
      <//>

      <${Panel} title=${`세부 요소 비교 ${g.comps.length}건`} flush=${true}>
        ${g.comps.length === 0 ? html`<${Empty}>비교된 세부 요소가 없다<//>` : html`
          <div class="tablewrap"><table>
            <thead><tr><th>세부 요소</th><th>유형</th><th>판정</th>
              <th class="cell-wide">계약서 값</th><th class="cell-wide">설명서 값</th>
              <th>근거</th><th class="num">확신도</th></tr></thead>
            <tbody>${g.comps.map((c, i) => html`<tr key=${i}>
              <td>${c.display} ${c.is_key && html`<span class="key-star">★</span>`}
                <br/><span class="cell-code">${c.element_id}</span></td>
              <td><span class="kind">${c.value_type}</span></td>
              <td><${Verdict} v=${c.verdict} /></td>
              <td class="cell-code">${truncate(c.contract_raw, 110) || "—"}</td>
              <td class="cell-code">${truncate(c.statement_raw, 110) || "—"}</td>
              <td>${truncate(c.reason, 170)}
                <br/><span class="cell-code">${c.method}</span>
                ${c.evidence?.contract_provisions?.length > 0 &&
                  html`<div class="foot">관련 조항: ${c.evidence.contract_provisions.join(" · ")}</div>`}</td>
              <td class="num">${pct(c.confidence)}</td>
            </tr>`)}</tbody>
          </table></div>`}
      <//>`;
  }

  /* ---------- P3 1단계 ---------- */
  function PairView() {
    const pairs = B.report.pairs;
    const secById = useMemo(() => {
      const m = {};
      ["contract", "statement"].forEach((k) =>
        B.tagged[k].sections.forEach((s) => (m[s.section_id] = s)));
      return m;
    }, []);
    const tagDisplay = useMemo(() => {
      const m = {}; B.schema.sections.forEach((s) => (m[s.id] = s.display)); return m;
    }, []);
    const label = (ids) => ids.length === 0 ? "—"
      : ids.map((id) => secById[id]?.title || secById[id]?.tag || id).join(" + ");
    return html`
      <${Panel} title="후보 축소 방식">
        <p style=${{ margin: 0, color: "var(--muted)", fontSize: "12.5px" }}>
          섹션을 전수 조합하지 않는다. 같은 태그끼리 하나의 쌍으로 묶고, 태그가 다른 것만 공유 용어가 있을 때 LLM 이 본다.
          계약서 여러 조항 ↔ 설명서 한 문단은 자연스럽게 1:N 이 된다.
        </p>
      <//>
      <${Panel} title=${`대응 쌍 ${pairs.length}개`} flush=${true}>
        <div class="tablewrap"><table>
          <thead><tr>
            <th>태그</th><th class="cell-wide">계약서 섹션</th><th class="cell-wide">설명서 섹션</th>
            <th>방법</th><th class="num">확신도</th><th>상태</th><th>근거</th>
          </tr></thead>
          <tbody>${pairs.map((p) => html`<tr key=${p.pair_id}>
            <td>${tagDisplay[p.tag] || "—"}<br/><span class="cell-code">${p.tag || ""}</span></td>
            <td>${label(p.contract_sections)}</td>
            <td>${label(p.statement_sections)}</td>
            <td><span class="kind">${p.method}</span></td>
            <td class="num">${pct(p.confidence)}</td>
            <td><${Verdict} v=${p.flag === "ok" ? "match" : p.flag === "uncertain" ? "uncertain" : "unpaired"} /></td>
            <td>${truncate(p.evidence, 130)}
              ${p.shared_terms?.length > 0 && html`<br/><span class="foot">공유 용어 ${p.shared_terms.length}</span>`}</td>
          </tr>`)}</tbody>
        </table></div>
      <//>`;
  }

  /* ---------- P4 2단계 ---------- */
  function CompareView() {
    const [filter, setFilter] = useState("all");
    const all = B.report.comparisons;
    const rows = all.filter((c) => filter === "all" || c.verdict === filter);
    const counts = useMemo(() => {
      const c = {}; all.forEach((x) => (c[x.verdict] = (c[x.verdict] || 0) + 1)); return c;
    }, [all]);
    const opts = [{ value: "all", label: `전체 ${all.length}` }].concat(
      ["match", "mismatch", "uncertain", "missing_side"]
        .filter((v) => counts[v])
        .map((v) => ({ value: v, label: `${VERDICT_KO[v]} ${counts[v]}` })));
    return html`
      <${Panel} title=${`요소 비교 ${rows.length}건`} flush=${true}
        right=${html`<${Seg} value=${filter} onChange=${setFilter} options=${opts} />`}>
        <div class="tablewrap"><table>
          <thead><tr>
            <th>태그 · 요소</th><th>유형</th><th>판정</th>
            <th class="cell-wide">계약서 값</th><th class="cell-wide">설명서 값</th>
            <th>판정 근거</th><th class="num">확신도</th>
          </tr></thead>
          <tbody>${rows.map((c, i) => html`<tr key=${i}>
            <td>${c.display} ${c.is_key && html`<span class="key-star" title="핵심 요소">★</span>`}
              <br/><span class="cell-code">${c.tag}.${c.element_id}</span></td>
            <td><span class="kind">${c.value_type}</span></td>
            <td><${Verdict} v=${c.verdict} /></td>
            <td class="cell-code">${truncate(c.contract_raw, 120) || "—"}</td>
            <td class="cell-code">${truncate(c.statement_raw, 120) || "—"}</td>
            <td>${truncate(c.reason, 190)}<br/><span class="cell-code">${c.method}</span></td>
            <td class="num">${pct(c.confidence)}</td>
          </tr>`)}</tbody>
        </table></div>
      <//>
      <p class="foot">★ = 태그 스키마에서 <code>key: true</code> 로 선언한 핵심 요소. 불일치 시 심각도 high.
        <code>typed_compare</code> 는 코드가, <code>llm_semantic</code> 은 LLM 이 판정한 것이다.</p>`;
  }

  /* ---------- 완결성 ---------- */
  function CompletenessView() {
    const rows = B.report.completeness;
    return html`
      <${Panel} title="검증 (a) 완결성">
        <p style=${{ margin: 0, color: "var(--muted)", fontSize: "12.5px" }}>
          설명서를 <b>혼자</b> 놓고 필수 항목이 다 있는지 본다. 두 문서를 대조하는 정합성(P3·P4)과는 별개 검증이다.
          상품유형에 따라 필수 여부가 바뀌는 항목은 "해당없음"으로 빠져 오탐이 되지 않는다.
        </p>
      <//>
      <${Panel} title=${`필수 항목 ${rows.length}개`} flush=${true}>
        <div class="tablewrap"><table>
          <thead><tr><th>항목</th><th>필수 여부</th><th>존재</th><th>판정</th><th>위치 / 사유</th></tr></thead>
          <tbody>${rows.map((r) => html`<tr key=${r.tag}>
            <td>${r.display}<br/><span class="cell-code">${r.tag}</span></td>
            <td>${r.required ? "필수" : "해당없음"}</td>
            <td class="num">${r.present ? "O" : "X"}</td>
            <td><${Verdict} v=${r.verdict} /></td>
            <td>${r.verdict === "ok" ? r.location : truncate(r.reason, 150)}</td>
          </tr>`)}</tbody>
        </table></div>
      <//>`;
  }

  /* ---------- 선언 / 용어집 ---------- */
  function DeclareView() {
    const [tab, setTab] = useState("schema");
    return html`
      <${Panel} title="사용자가 선언하는 것"
        right=${html`<${Seg} value=${tab} onChange=${setTab} options=${[
          { value: "schema", label: "태그 스키마" },
          { value: "glossary", label: "용어집" },
          { value: "mapping", label: "표기 매핑" }]} />`}>
        <p style=${{ margin: 0, color: "var(--muted)", fontSize: "12.5px" }}>
          ${tab === "schema" && "무엇을 태깅할지 사용자가 선언한다. sections[] 가 메인 요소(1단계 대상), elements[] 가 세부 요소(2단계 대상)다."}
          ${tab === "glossary" && "같은 것을 다르게 부르는 표현을 묶는다. source=user 는 사람이 추가한 것이고 LLM 이 덮어쓰지 못한다. source=llm 은 태깅 중 발견된 제안이다."}
          ${tab === "mapping" && "표기 체계가 다른 분류값을 공통 코드로 통일한다. 위험등급 '2등급' 과 '높은위험' 이 같은 G2 가 된다."}
        </p>
      <//>
      ${tab === "schema" && html`<div class="cards">
        ${B.schema.sections.map((s) => html`
          <article class="card" key=${s.id}>
            <header class="card__head">
              <span class="card__tag">${s.id}</span>
              <span class="card__title">${s.display}</span>
              <span class="card__meta">${s.scope} · 필수 ${typeof s.required_in_statement === "string"
                ? s.required_in_statement : JSON.stringify(s.required_in_statement)}</span>
            </header>
            <div class="card__body">
              ${s.hints?.length > 0 && html`<p class="foot">힌트: ${s.hints.join(" · ")}</p>`}
              ${s.confusable_with?.length > 0 && html`<p class="foot">혼동 주의: ${s.confusable_with.join(" · ")}</p>`}
              <div class="tablewrap"><table>
                <thead><tr><th>세부 요소</th><th>id</th><th>값 유형</th><th>핵심</th></tr></thead>
                <tbody>${(s.elements || []).map((e) => html`<tr key=${e.id}>
                  <td>${e.display}</td><td class="cell-code">${e.id}</td>
                  <td><span class="kind">${e.value_type}</span></td>
                  <td class="num">${e.key ? "★" : ""}</td></tr>`)}</tbody>
              </table></div>
            </div>
          </article>`)}
      </div>`}
      ${tab === "glossary" && html`<${Panel} title=${`용어 ${B.glossary.terms.length}개`} flush=${true}>
        <div class="tablewrap"><table>
          <thead><tr><th>정규형</th><th>표시명</th><th>값 유형</th><th>출처</th><th>표면 표현</th><th>혼동 주의</th></tr></thead>
          <tbody>${B.glossary.terms.map((t) => html`<tr key=${t.canonical}>
            <td class="cell-code">${t.canonical}</td><td>${t.display}</td>
            <td><span class="kind">${t.value_type}</span></td>
            <td><span class=${"verdict " + (t.source === "user" ? "v-match" : t.source === "llm" ? "v-uncertain" : "v-idle")}>${t.source}</span></td>
            <td>${(t.surfaces || []).join(" · ")}</td>
            <td class="cell-code">${(t.confusable_with || []).join(" · ")}</td></tr>`)}</tbody>
        </table></div>
      <//>`}
      ${tab === "mapping" && html`<div class="cards">
        ${Object.keys(B.mapping_table).filter((k) => !k.startsWith("_")).map((k) => html`
          <article class="card" key=${k}>
            <header class="card__head"><span class="card__tag">${k}</span></header>
            <div class="card__body"><div class="tablewrap"><table>
              <thead><tr><th>문서 표기</th><th>공통 코드</th></tr></thead>
              <tbody>${Object.entries(B.mapping_table[k]).filter(([s]) => !s.startsWith("_"))
                .map(([s, c]) => html`<tr key=${s}><td>${s}</td><td class="cell-code">${c}</td></tr>`)}</tbody>
            </table></div></div>
          </article>`)}
      </div>`}`;
  }

  /* ---------- LLM 호출 ---------- */
  function CallsView() {
    const st = B.snapshot_stats || {};
    return html`
      <${Panel} title="LLM 호출과 재현성">
        <dl class="kv">
          <dt>백엔드</dt><dd class="cell-code">${B.report.backend}</dd>
          <dt>스냅샷 항목</dt><dd>${st.entries ?? "—"}건</dd>
          <dt>이번 실행</dt><dd>재생 ${st.hits ?? 0} · 신규 호출 ${st.misses ?? 0}</dd>
        </dl>
        <p class="foot" style=${{ marginTop: "12px" }}>
          모든 호출을 <b>입력 해시</b>로 기록한다. 같은 문서를 다시 돌리면 스냅샷을 재생하므로 결과가 고정되고,
          API 키 없이도 같은 리포트가 나온다. 프롬프트를 고치면 지문이 달라져 자동으로 재호출된다.
          사람이 스냅샷 JSON 을 고치면 그게 정답이 된다 — 감사 대응 경로다.
        </p>
      <//>
      <${Panel} title="호출 지점 5개">
        <div class="tablewrap"><table>
          <thead><tr><th>호출</th><th>언제</th><th>단계</th></tr></thead>
          <tbody>
            <tr><td class="cell-code">doc_meta</td><td>발행사·기준일·상품유형</td><td>P1 직후</td></tr>
            <tr><td class="cell-code">tag_blocks</td><td>블록에 메인 태그 부여 (= 섹션 형성)</td><td>P2</td></tr>
            <tr><td class="cell-code">extract_elements</td><td>섹션에서 세부 요소를 구조화 추출</td><td>P2</td></tr>
            <tr><td class="cell-code">pair_sections</td><td>태그가 다른 섹션의 대응 판정</td><td>P3</td></tr>
            <tr><td class="cell-code">compare_values</td><td>코드가 판정 못 한 값쌍만</td><td>P4</td></tr>
          </tbody>
        </table></div>
        <p class="foot" style=${{ marginTop: "10px" }}>
          문서 해석은 전부 이 5개를 거친다. 정규표현식은 쓰지 않는다 —
          dataset 9종 실측에서 금액 파서 오탐 80%, 기준일 추출 성공률 44% 로 오버피팅이 확인됐다.
        </p>
      <//>`;
  }

  /* ---------- 셸 ---------- */
  const STAGES = [
    { id: "overview", step: "—", label: "개요", group: "요약", C: Overview },
    { id: "elements", step: "—", label: "큰 요소 · 세부 요소", group: "요약", C: ElementView,
      count: () => B.schema.sections.length },
    { id: "parse", step: "P1", label: "파싱", group: "파이프라인", C: ParseView,
      count: () => B.parsed.contract.blocks.length + B.parsed.statement.blocks.length },
    { id: "tag", step: "P2", label: "태깅", group: "파이프라인", C: TagView,
      count: () => B.tagged.contract.sections.length + B.tagged.statement.sections.length },
    { id: "pair", step: "P3", label: "1단계 · 섹션 대응", group: "파이프라인", C: PairView,
      count: () => B.report.pairs.length },
    { id: "compare", step: "P4", label: "2단계 · 값 비교", group: "파이프라인", C: CompareView,
      count: () => B.report.comparisons.length },
    { id: "completeness", step: "P5", label: "완결성", group: "파이프라인", C: CompletenessView,
      count: () => B.report.completeness.length },
    { id: "declare", step: "", label: "선언 · 용어집", group: "설정", C: DeclareView,
      count: () => B.schema.sections.length },
    { id: "calls", step: "", label: "LLM 호출", group: "설정", C: CallsView },
  ];

  const STAGE_LEDE = {
    overview: "무엇이 어긋났는지부터. 상세는 단계별로 따라 들어가면 된다.",
    elements: "큰 요소를 고르면 두 문서가 그 요소를 어떻게 쪼갰는지 보이고, 그 안에서 세부 요소 값이 비교된다.",
    parse: "도클링이 문서를 블록으로 쪼갠 결과. 아직 의미는 붙지 않았다.",
    tag: "사용자가 선언한 태그를 블록에 붙이고, 섹션 안에서 세부 요소를 구조화한다.",
    pair: "계약서의 어느 섹션과 설명서의 어느 섹션이 같은 사안인가.",
    compare: "대응된 섹션 안에서 같은 요소끼리 값을 비교한다.",
    completeness: "설명서 혼자 놓고 필수 항목이 다 있는지 본다.",
    declare: "코드가 아니라 이 선언이 대사 대상을 정한다.",
    calls: "문서 해석은 전부 LLM 이 하고, 그 호출을 스냅샷으로 고정한다.",
  };

  function TopBar({ theme, onTheme }) {
    const d = B.report.documents, s = B.report.summary;
    const doc = (role, meta) => html`
      <div class="pair__doc">
        <div class="pair__role">${role}</div>
        <div class="pair__name">${meta.title || "—"}</div>
        <div class="pair__meta">${meta.issuer || "발행사 미상"} · 기준일 ${meta.version_date || "미상"} · ${meta.product_type || "—"}</div>
      </div>`;
    return html`
      <header class="topbar">
        <div class="pair">
          ${doc("신탁계약서 (정답 문서)", d.contract)}
          <span class="pair__vs">↔</span>
          ${doc("핵심상품설명서", d.statement)}
        </div>
        <div style=${{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          <div class="chips">
            <span class="chip chip--ok">일치 <b>${s.match}</b></span>
            <span class="chip chip--bad">불일치 <b>${s.mismatch}</b></span>
            <span class="chip chip--warn">불확실 <b>${s.uncertain}</b></span>
            <span class="chip chip--bad">누락 <b>${s.missing}</b></span>
            <span class="chip">쌍 <b>${s.pairs}</b></span>
          </div>
          <button class="iconbtn" onClick=${onTheme} aria-label="테마 전환">
            ${theme === "dark" ? "밝게" : "어둡게"}
          </button>
        </div>
      </header>`;
  }

  function App() {
    const [stage, setStage] = useState("overview");
    const [theme, setTheme] = useState(
      document.documentElement.getAttribute("data-theme") ||
      (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
    const toggle = useCallback(() => {
      const next = theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      setTheme(next);
    }, [theme]);

    const cur = STAGES.find((s) => s.id === stage) || STAGES[0];
    let lastGroup = null;
    return html`
      <div class="app">
        <nav class="rail" aria-label="파이프라인 단계">
          <div class="rail__brand">
            <div class="rail__title">신탁 대사 뷰어</div>
            <div class="rail__sub">계약서 ↔ 핵심상품설명서</div>
          </div>
          ${STAGES.map((s) => {
            const head = s.group !== lastGroup ? s.group : null;
            lastGroup = s.group;
            return html`<${React.Fragment} key=${s.id}>
              ${head && html`<div class="rail__group">${head}</div>`}
              <button class="navitem" aria-current=${String(stage === s.id)}
                      onClick=${() => setStage(s.id)}>
                <span class="navitem__step">${s.step}</span>
                <span>${s.label}</span>
                <span class="navitem__count">${s.count ? s.count() : ""}</span>
              </button>
            <//>`;
          })}
        </nav>
        <div class="main">
          <${TopBar} theme=${theme} onTheme=${toggle} />
          <main class="stage">
            <div class="stage__head">
              <div class="stage__eyebrow">${cur.step ? cur.step + " · " : ""}${cur.group}</div>
              <h1 class="stage__title">${cur.label}</h1>
              <p class="stage__lede">${STAGE_LEDE[cur.id]}</p>
            </div>
            <${cur.C} />
          </main>
        </div>
      </div>`;
  }

  ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
})();
