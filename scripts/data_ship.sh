#!/usr/bin/env bash
# data_ship.sh — 데이터를 이메일 크기(기본 45MB)로 쪼개 zip 으로 떨구고, 받는 쪽에서
# 그 zip 들을 풀어 저장소 뿌리에 제자리 배치한다.
#
#   보내는 쪽   scripts/data_ship.sh pack   [--out DIR] [--size MB] [--name NAME]
#                                          [--vectors] [--pdf] [--pages] [--corpus]
#   받는 쪽     scripts/data_ship.sh unpack <zip 들이 있는 폴더> [--root REPO] [--replace] [--dry-run]
#   확인        scripts/data_ship.sh list   [같은 스위치]                 # 무엇이 실리나 (크기)
#
#   기본으로 싣는 것 — 구조 정본(result.json·meta.json·source.xml)·용어·간선·관측.
#   기본으로 빼는 것 (2026-08-18 사용자 결정):
#     data/embeddings/          벡터는 그쪽 모델로 다시 만든다 (--vectors 로 포함).
#                               재생성: python -m lawrag.core.terms embed-sections
#                               (로컬 EMBED_MODEL 또는 GENOS_EMBED_URL — lawrag/core/embedding.py)
#     source.pdf · parse.json   lawxml 문서의 pdf 는 검수용 합성 지면이라 뷰어 재해석·
#                               페이지 그림에만 쓴다 (--pdf 로 포함). source.xml 은 싣는다.
#     pages/*.png · data/corpus/     --pages · --corpus
#     *.bak                     항상
#               scripts/data_ship.sh verify <폴더>                    # 부품 무결성만
#
# 함수로 쓰려면:  source scripts/data_ship.sh && data_pack …  /  data_unpack …
#
# 구조 — 목록(scripts/data_ship.list) → tar.gz 한 덩이 → N MB 조각 → 조각마다
# **독립 zip** (조각 + MANIFEST.json). 이렇게 하는 이유:
#   · 벡터(vectors.npz 123M)처럼 한 파일이 조각보다 큰 게 있어 파일 단위 zip 으론 못 나눈다
#   · zip 분할 볼륨(.z01…)은 메일 필터가 막거나 받는 쪽에 zip 이 없어 못 합친다
#   · 조각을 zip 으로 싸면 첨부마다 온전한 .zip 이고, 어느 한 통에도 매니페스트가 들어 있다
# 받는 쪽은 zip 을 풀어 조각을 순서대로 이어 붙이고 sha256 을 맞춘 뒤 tar 로 편다.
# 메일 클라이언트가 첨부 이름을 바꿔도(" (1)" 등) 안의 조각 이름으로 찾으니 상관없다.
#
# 도구: bash · tar · gzip · split · sha256sum · python3 (zip 만들기/풀기 — zip 바이너리 불필요)

set -euo pipefail

_DS_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_DS_ROOT="$(cd "$_DS_HERE/.." && pwd)"
_DS_LIST="$_DS_HERE/data_ship.list"
_DS_SIZE_MB=45          # 첨부 한도 50MB 아래. 서버가 base64 부풀림(×1.37)까지 세면 --size 35
_DS_EXCLUDE_PAGES='data/structure/*/pages'
_DS_EXCLUDE_PDF=('data/structure/*/source.pdf' 'data/structure/*/parse.json')
_DS_EXCLUDE_ALWAYS=('*.bak')

_ds_say()  { printf '%s\n' "$*" >&2; }
_ds_die()  { _ds_say "오류: $*"; return 1; }
_ds_mb()   { awk -v b="$1" 'BEGIN{printf "%.1f", b/1048576}'; }

# 목록 파일 → 경로들 (주석·빈 줄 제거, 없는 경로는 경고)
_ds_paths() {            # $1: with_corpus(0/1)
  local p
  while IFS= read -r line; do
    p="${line%%#*}"; p="${p## }"; p="${p%% }"; p="$(printf '%s' "$p" | sed 's/[[:space:]]*$//')"
    [[ -z "$p" ]] && continue
    [[ "${_DS_NO_VECTORS:-0}" == 1 && "${p%/}" == data/embeddings ]] && continue
    if [[ -e "$_DS_ROOT/$p" ]]; then printf '%s\n' "${p%/}"; else _ds_say "  (없음, 건너뜀) $p"; fi
  done < "$_DS_LIST"
  if [[ "${1:-0}" == 1 ]]; then
    [[ -e "$_DS_ROOT/data/corpus" ]] && printf 'data/corpus\n' || _ds_say "  (없음, 건너뜀) data/corpus/"
  fi
}

# ── list ─────────────────────────────────────────────────────────────────
data_list() {
  local corpus=0 pages=0 pdf=0 vec=0
  while [[ $# -gt 0 ]]; do case "$1" in
    --corpus) corpus=1;; --pages) pages=1;; --pdf) pdf=1;; --vectors) vec=1;;
    *) _ds_die "모르는 옵션 $1";; esac; shift; done
  cd "$_DS_ROOT"
  local total=0 p b
  local f=(-type f ! -name '*.bak')
  printf '%10s  %s\n' "MB" "경로"
  while IFS= read -r p; do
    if [[ "$p" == data/structure ]]; then
      local x=(); [[ $pages == 0 ]] && x+=(! -path "*/pages/*")
      [[ $pdf == 0 ]] && x+=(! -name source.pdf ! -name parse.json)
      b=$(find "$p" "${f[@]}" "${x[@]}" -printf '%s\n' | awk '{s+=$1}END{print s+0}')
    else
      b=$(find "$p" "${f[@]}" -printf '%s\n' | awk '{s+=$1}END{print s+0}')
    fi
    total=$((total + b)); printf '%10s  %s\n' "$(_ds_mb "$b")" "$p"
  done < <(_DS_NO_VECTORS=$((1-vec)) _ds_paths "$corpus")
  printf '%10s  합계 (원본 크기, 압축 전)\n' "$(_ds_mb "$total")"
  [[ $vec == 0 ]] && _ds_say "  * data/embeddings 제외 — 그쪽 모델로 재생성 (넣으려면 --vectors)"
  [[ $pdf == 0 ]] && _ds_say "  * source.pdf·parse.json 제외 (합성 지면·파싱 캐시 — 넣으려면 --pdf). source.xml 은 포함"
  [[ $pages == 0 ]] && _ds_say "  * data/structure/*/pages (PNG 렌더) 제외 — 넣으려면 --pages"
  [[ $corpus == 0 ]] && _ds_say "  * data/corpus/ 제외 — 넣으려면 --corpus"
  return 0
}

# ── pack ─────────────────────────────────────────────────────────────────
data_pack() {
  local out="" size="$_DS_SIZE_MB" corpus=0 pages=0 pdf=0 vec=0 name=""
  while [[ $# -gt 0 ]]; do case "$1" in
    --out)  out="$2"; shift;; --size) size="$2"; shift;; --name) name="$2"; shift;;
    --corpus) corpus=1;; --pages) pages=1;; --pdf) pdf=1;; --vectors) vec=1;;
    *) _ds_die "모르는 옵션 $1";; esac; shift; done
  cd "$_DS_ROOT"
  local stamp; stamp="$(date +%Y%m%d-%H%M)"
  name="${name:-8agent-data-$stamp}"
  out="${out:-$_DS_ROOT/var/var/out/ship/$name}"
  local rev; rev="$(git -C "$_DS_ROOT" rev-parse --short HEAD 2>/dev/null || echo '-')"
  local tmp; tmp="$(mktemp -d)"; trap "rm -rf '$tmp'; trap - RETURN" RETURN

  _ds_say "▶ 목록 확인 ($_DS_LIST)"
  local paths=(); local p
  while IFS= read -r p; do paths+=("$p"); done < <(_DS_NO_VECTORS=$((1-vec)) _ds_paths "$corpus")
  [[ ${#paths[@]} -gt 0 ]] || _ds_die "실을 경로가 없다"
  local excl=() e; for e in "${_DS_EXCLUDE_ALWAYS[@]}"; do excl+=(--exclude="$e"); done
  [[ $pages == 0 ]] && excl+=(--exclude="$_DS_EXCLUDE_PAGES")
  [[ $pdf == 0 ]] && for e in "${_DS_EXCLUDE_PDF[@]}"; do excl+=(--exclude="$e"); done

  _ds_say "▶ tar.gz 만드는 중 (${#paths[@]}개 경로$([[ $pages == 1 ]] && echo ', PNG 렌더 포함'))…"
  local tarball="$tmp/$name.tar.gz"
  tar -czf "$tarball" "${excl[@]}" -- "${paths[@]}"
  local tbytes tsha; tbytes=$(stat -c%s "$tarball"); tsha=$(sha256sum "$tarball" | cut -d' ' -f1)
  _ds_say "  tar.gz $(_ds_mb "$tbytes") MB  sha256 ${tsha:0:16}…"

  _ds_say "▶ ${size}MB 로 쪼개는 중…"
  ( cd "$tmp" && split -b "${size}m" -d -a 3 "$name.tar.gz" "$name.part." )
  local parts=(); while IFS= read -r p; do parts+=("$p"); done < <(ls "$tmp"/"$name".part.* | sort)
  local n=${#parts[@]}

  # 조각 이름을 사람이 읽는 꼴로 — NAME.p01-of-04.bin
  local i=0 renamed=()
  for p in "${parts[@]}"; do
    i=$((i+1)); local nn; nn="$(printf '%s.p%02d-of-%02d.bin' "$name" "$i" "$n")"
    mv "$p" "$tmp/$nn"; renamed+=("$nn")
  done

  _ds_say "▶ 매니페스트·zip (python3 zipfile, 저장만 — 이미 압축돼 있다)…"
  mkdir -p "$out"
  DS_NAME="$name" DS_OUT="$out" DS_TMP="$tmp" DS_REV="$rev" DS_TBYTES="$tbytes" DS_TSHA="$tsha" \
  DS_SIZE="$size" DS_PAGES="$pages" DS_CORPUS="$corpus" DS_PDF="$pdf" DS_VEC="$vec" \
  DS_PATHS="$(printf '%s\n' "${paths[@]}")" DS_PARTS="$(printf '%s\n' "${renamed[@]}")" \
  python3 - <<'PY'
import hashlib, json, os, platform, zipfile
from datetime import datetime, timezone
name, out, tmp = os.environ["DS_NAME"], os.environ["DS_OUT"], os.environ["DS_TMP"]
parts = os.environ["DS_PARTS"].split("\n")
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
rows = []
for i, fn in enumerate(parts, 1):
    fp = os.path.join(tmp, fn)
    rows.append({"n": i, "file": fn, "bytes": os.path.getsize(fp), "sha256": sha(fp)})
manifest = {
    "name": name, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "git_rev": os.environ["DS_REV"], "host": platform.node(),
    "part_mb": int(os.environ["DS_SIZE"]), "parts_total": len(parts), "parts": rows,
    "tar": {"file": name + ".tar.gz", "bytes": int(os.environ["DS_TBYTES"]), "sha256": os.environ["DS_TSHA"]},
    "paths": os.environ["DS_PATHS"].split("\n"),
    "excluded": (["*.bak"]
                 + ([] if os.environ["DS_PAGES"] == "1" else ["data/structure/*/pages (PNG 렌더 — 원본 PDF 에서 재생성)"])
                 + ([] if os.environ["DS_PDF"] == "1" else ["data/structure/*/{source.pdf,parse.json} (합성 지면·파싱 캐시 — 뷰어 재해석·페이지 그림만 쓴다)"])
                 + ([] if os.environ["DS_VEC"] == "1" else ["data/embeddings (벡터 — 그쪽 모델로 재생성: python -m lawrag.core.terms embed-sections)"])),
    "corpus_included": os.environ["DS_CORPUS"] == "1",
    "unpack": "scripts/data_ship.sh unpack <이 zip 들이 있는 폴더>   (저장소 뿌리에 펼쳐진다)",
}
mtxt = json.dumps(manifest, ensure_ascii=False, indent=1)
open(os.path.join(out, name + ".manifest.json"), "w", encoding="utf-8").write(mtxt)
for r in rows:
    zp = os.path.join(out, r["file"][:-4] + ".zip")
    with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_STORED) as z:
        z.write(os.path.join(tmp, r["file"]), r["file"])
        z.writestr("MANIFEST.json", mtxt)
    print(f"  {os.path.basename(zp):48s} {os.path.getsize(zp)/1048576:6.1f} MB")
PY

  _ds_say ""
  _ds_say "완료 → $out"
  _ds_say "  조각 $n 개 × ≤${size}MB, 원본 tar.gz $(_ds_mb "$tbytes") MB, git $rev"
  _ds_say "  받는 쪽: 첨부 zip 을 한 폴더에 모아 두고"
  _ds_say "           scripts/data_ship.sh unpack <그 폴더>        # 저장소 뿌리에 배치"
  _ds_say "           scripts/data_ship.sh unpack <그 폴더> --replace   # 기존 데이터를 백업 후 교체"
}

# ── verify / unpack 공통: zip 들을 풀어 조각과 매니페스트를 모은다 ───────
_ds_collect() {          # $1: 폴더, $2: 작업 폴더  → stdout 에 매니페스트 경로
  local src="$1" work="$2" z
  local zips=(); while IFS= read -r z; do zips+=("$z"); done < <(find "$src" -maxdepth 1 -name '*.zip' | sort)
  [[ ${#zips[@]} -gt 0 ]] || _ds_die "$src 에 zip 이 없다"
  for z in "${zips[@]}"; do
    if command -v unzip >/dev/null; then unzip -oq "$z" -d "$work"
    else python3 -m zipfile -e "$z" "$work"; fi
  done
  [[ -f "$work/MANIFEST.json" ]] || _ds_die "MANIFEST.json 이 없다 — data_ship.sh pack 으로 만든 zip 인가?"
  printf '%s\n' "$work/MANIFEST.json"
}

_ds_check_parts() {      # $1: 매니페스트, $2: 작업 폴더 → 이어 붙인 tar.gz 경로 (stdout)
  local mf="$1" work="$2"
  local name total; name=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['name'])" "$mf")
  total=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['parts_total'])" "$mf")
  local missing=0 bad=0 i fn want have
  : > "$work/$name.tar.gz"
  while IFS=$'\t' read -r i fn want; do
    if [[ ! -f "$work/$fn" ]]; then _ds_say "  ✗ 조각 $i/$total 없음: $fn"; missing=$((missing+1)); continue; fi
    have=$(sha256sum "$work/$fn" | cut -d' ' -f1)
    if [[ "$have" != "$want" ]]; then _ds_say "  ✗ 조각 $i/$total sha256 불일치: $fn"; bad=$((bad+1)); continue; fi
    _ds_say "  ✓ 조각 $i/$total $fn ($(_ds_mb "$(stat -c%s "$work/$fn")") MB)"
    cat "$work/$fn" >> "$work/$name.tar.gz"
  done < <(python3 -c "
import json,sys
for r in json.load(open(sys.argv[1]))['parts']: print(r['n'], r['file'], r['sha256'], sep='\t')" "$mf")
  [[ $missing == 0 && $bad == 0 ]] || _ds_die "조각 없음 $missing · 손상 $bad — 그 통을 다시 받아라"
  local want_t have_t; want_t=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['tar']['sha256'])" "$mf")
  have_t=$(sha256sum "$work/$name.tar.gz" | cut -d' ' -f1)
  [[ "$have_t" == "$want_t" ]] || _ds_die "이어 붙인 tar.gz sha256 불일치 — 조각 순서/누락 확인"
  _ds_say "  ✓ tar.gz 무결 ($(_ds_mb "$(stat -c%s "$work/$name.tar.gz")") MB)"
  printf '%s\n' "$work/$name.tar.gz"
}

data_verify() {
  local src="${1:-}"; [[ -n "$src" && -d "$src" ]] || _ds_die "verify <zip 폴더>"
  local work; work="$(mktemp -d)"; trap "rm -rf '$work'; trap - RETURN" RETURN
  local mf; mf=$(_ds_collect "$src" "$work")
  _ds_check_parts "$mf" "$work" >/dev/null
  _ds_say "무결 — unpack 해도 된다"
}

# ── unpack ───────────────────────────────────────────────────────────────
data_unpack() {
  local src="" root="$_DS_ROOT" replace=0 dry=0
  while [[ $# -gt 0 ]]; do case "$1" in
    --root) root="$2"; shift;; --replace) replace=1;; --dry-run) dry=1;;
    -*) _ds_die "모르는 옵션 $1";; *) src="$1";; esac; shift; done
  [[ -n "$src" && -d "$src" ]] || _ds_die "unpack <zip 들이 있는 폴더> [--root REPO] [--replace] [--dry-run]"
  [[ -d "$root" ]] || _ds_die "root 가 폴더가 아니다: $root"
  local work; work="$(mktemp -d)"; trap "rm -rf '$work'; trap - RETURN" RETURN

  _ds_say "▶ zip 풀어 조각 모으는 중 ($src)…"
  local mf; mf=$(_ds_collect "$src" "$work")
  python3 - "$mf" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"  이름 {m['name']} · 만든 때 {m['created']} · git {m['git_rev']} · 조각 {m['parts_total']}개", file=sys.stderr)
print("  실린 경로:", ", ".join(m["paths"]), file=sys.stderr)
if m.get("excluded"): print("  제외:", "; ".join(m["excluded"]), file=sys.stderr)
PY
  _ds_say "▶ 조각 검증·이어 붙이기…"
  local tarball; tarball=$(_ds_check_parts "$mf" "$work")

  if [[ $dry == 1 ]]; then
    _ds_say "▶ --dry-run — 펼치지 않는다. 안에 든 것(상위 30줄):"
    tar -tzf "$tarball" | head -30 >&2
    _ds_say "  … 총 $(tar -tzf "$tarball" | wc -l) 항목 → $root 에 펼쳐질 예정"
    return 0
  fi

  local paths=(); local p
  while IFS= read -r p; do paths+=("$p"); done < <(python3 -c "
import json,sys
for p in json.load(open(sys.argv[1]))['paths']: print(p)" "$mf")

  if [[ $replace == 1 ]]; then
    local bak="$root/.data_ship_backup/$(date +%Y%m%d-%H%M%S)"
    _ds_say "▶ --replace — 기존 것을 $bak 로 옮긴다"
    for p in "${paths[@]}"; do
      if [[ -e "$root/$p" ]]; then mkdir -p "$bak/$(dirname "$p")"; mv "$root/$p" "$bak/$p"; _ds_say "  ↪ $p"; fi
    done
  else
    _ds_say "▶ 덮어쓰기 배치 (기존 파일은 같은 이름만 교체, 남는 파일은 그대로 — 깨끗이 하려면 --replace)"
  fi

  _ds_say "▶ $root 에 펼치는 중…"
  tar -xzf "$tarball" -C "$root"
  _ds_say ""
  _ds_say "배치 완료 → $root"
  for p in "${paths[@]}"; do
    [[ -e "$root/$p" ]] && printf '  %8s  %s\n' "$(du -sh "$root/$p" 2>/dev/null | cut -f1)" "$p" >&2
  done
  _ds_say ""
  _ds_say "다음: 저장소 뿌리에서 scripts/serve.sh (기본 경로 STRUCTURE_STORE=data/structure 등이 그대로 맞는다)."
  if [[ ! -e "$root/data/embeddings/sections/vectors.npz" ]]; then
    _ds_say "      벡터가 없다 — 이쪽 모델로 만들어라:  python -m lawrag.core.terms embed-sections"
    _ds_say "        · 로컬 모델:  EMBED_MODEL=<sentence-transformers 이름>  (기본 BAAI/bge-m3)"
    _ds_say "        · GenOS 서빙: GENOS_EMBED_URL=<…/v1/embeddings 앞까지>  GENOS_EMBED_KEY=<키>"
    _ds_say "        만들기 전까지 벡터 채널만 빠지고 렉시컬·간선·용어·쟁점 채널은 다 돈다."
  fi
  _ds_say "      PNG 렌더·source.pdf 가 빠져 있으면 검수 화면의 페이지 그림·재해석만 없고 검색·질의는 전부 돈다."
}

# ── 진입 ─────────────────────────────────────────────────────────────────
_ds_main() {
  local cmd="${1:-}"; shift || true
  case "$cmd" in
    pack)   data_pack "$@";;
    unpack) data_unpack "$@";;
    list)   data_list "$@";;
    verify) data_verify "$@";;
    *) sed -n '2,12p' "${BASH_SOURCE[0]}" >&2; return 1;;
  esac
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then _ds_main "$@"; fi
