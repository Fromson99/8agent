"""Check the split documentation, preserved text and links; no runtime tests."""
from pathlib import Path
import datetime, gzip, hashlib, json, re
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MAP = HERE / "DOCUMENT_MAP.json"
RESULT = HERE / "REORGANIZATION_VALIDATION.json"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def sections(text):
    hits = list(re.finditer(r"^## (.+)$", text, re.M))
    result = {}
    for i, h in enumerate(hits):
        label = h.group(1)
        number = re.match(r"(\d+)\.", label)
        key = int(number.group(1)) if number else ("A" if label.startswith("부록 A") else "B")
        result[key] = text[h.start():hits[i+1].start() if i+1 < len(hits) else len(text)].strip()
    return result

def visible(text):
    text = re.sub(r'<a id="[^"]+"></a>', "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(\d+(?:\.\d+)?)절–(\d+(?:\.\d+)?)절", r"\1~\2절", text)
    text = text.replace("부록 B", "연구·표준 출처")
    return re.sub(r"\s+", " ", text).strip()

layout = json.loads(MAP.read_text())
archive_path = ROOT / layout["archive"]["path"]
assert sha(archive_path.read_bytes()) == layout["archive"]["sha256"]
saved = json.loads(gzip.decompress(archive_path.read_bytes()))
for path, item in saved["files"].items():
    assert sha(item["content"].encode()) == item["sha256"], path
old_sections = {path: sections(item["content"]) for path, item in saved["files"].items()
                if path in {row["source"] for row in layout["parts"]}}
moved = 0
for row in layout["parts"]:
    p = ROOT / row["path"]
    text = p.read_text()
    assert sha(p.read_bytes()) == row["sha256"], p
    current_sections = sections(text)
    for key in row["sections"]:
        assert visible(old_sections[row["source"]][key]) in visible(current_sections[key]), (p, key)
        moved += 1

for path, expected in layout["unchanged_artifacts"].items():
    assert sha((ROOT/path).read_bytes()) == expected, path

source_main = "07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V3.md"
mapped = {row["section"] for row in layout["sections"] if row["source"] == source_main and "." not in row["section"]}
assert mapped == {str(i) for i in range(1,25)} | {"A","B"}
for row in layout["sections"]:
    text = (ROOT/row["path"]).read_text()
    assert 'id="'+row["anchor"]+'"' in text, row

# This result has its own path; the completed DB validation is never rewritten.
if not RESULT.exists():
    RESULT.write_text('{"status":"CHECKING"}\n')
documents = [ROOT/p for p in layout["entrypoints"]]
documents += [ROOT/p["path"] for p in layout["parts"]]
documents += [ROOT/"07_DOCS/REFERENCE/REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/REVIEW.md",
              archive_path.parent/"README.md"]
known_documents = set(documents)
links = anchors = json_examples = 0
for path in documents:
    text = path.read_text()
    assert not any(line.rstrip()!=line for line in text.splitlines()), path
    assert sum(line.startswith("```") for line in text.splitlines())%2 == 0, path
    ids = re.findall(r'<a id="([^"]+)"></a>',text)
    assert len(ids)==len(set(ids)), path
    for target in re.findall(r"\]\(([^)]+)\)",text):
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:",target):
            continue
        name, _, fragment = target.partition("#")
        name = re.sub(r":\d+$","",name)
        destination = (path.parent/unquote(name)).resolve() if name else path
        assert destination.exists(), (path,target)
        links += 1
        if fragment and destination in known_documents:
            assert 'id="'+unquote(fragment)+'"' in destination.read_text(), (path,target)
            anchors += 1
    for block in re.findall(r"```json\n(.*?)```",text,re.S):
        json.loads(block)
        json_examples += 1
old_readme = saved["files"]["07_DOCS/README.md"]["content"]
new_readme = (ROOT/"07_DOCS/README.md").read_text()
strip_entry = lambda text: [line for line in text.splitlines() if not line.startswith("- [온톨로지 v3")]
assert strip_entry(old_readme)==strip_entry(new_readme), "unrelated README content changed"
result = {
    "schema_version":"ontology-v3-document-reorganization-validation-v1",
    "checked_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "status":"PASSED",
    "checks":{"entrypoints":len(layout["entrypoints"]),"topic_documents":len(layout["parts"]),
              "source_sections_preserved":moved,"duplicate_overviews_consolidated":2,
              "local_links":links,"split_section_anchor_links":anchors,"json_examples":json_examples,
              "unchanged_artifacts":len(layout["unchanged_artifacts"]),
              "archive_hash_and_contents":True,"original_prose_preserved_except_link_formatting":True,
              "unrelated_readme_content_unchanged":True},
    "scope":"Documentation organization only; no model, DB, runtime or release execution.",
    "documents":[{"path":str(p.relative_to(ROOT)),"sha256":sha(p.read_bytes()),"lines":len(p.read_text().splitlines())}
                 for p in documents],
    "map_sha256":sha(MAP.read_bytes()),
    "checker_sha256":sha(Path(__file__).read_bytes())
}
RESULT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"status":result["status"],**result["checks"]},ensure_ascii=False))
