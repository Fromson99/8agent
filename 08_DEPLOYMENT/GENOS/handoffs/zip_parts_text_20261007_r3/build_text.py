"""Create standalone interactive PowerShell source as two plain-text attachments."""
from __future__ import annotations

from pathlib import Path


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "zip_parts_click_20261007_r2"


def launcher(filename: str) -> str:
    return "& ([scriptblock]::Create([IO.File]::ReadAllText(([Environment]::GetFolderPath('Desktop')+'\\" + filename + "'))))"


def build() -> None:
    for source, target in (
        ("1_SPLIT_ZIP.cmd", "ZIP_SPLIT_RUN.txt"),
        ("2_JOIN_ZIP.cmd", "ZIP_JOIN_RUN.txt"),
    ):
        text = (PREVIOUS / source).read_text(encoding="utf-8")
        marker = "\n# ZIP_PARTS_POWERSHELL\n"
        assert text.count(marker) == 1
        body = text.split(marker, 1)[1]
        assert body.endswith("exit $status\n")
        body = body.removesuffix("exit $status\n") + "if ($status -ne 0) { throw 'ZIP 작업에 실패했습니다. 위 오류 메시지를 확인하세요.' }\n"
        # UTF-8 BOM makes the source readable in older Windows Notepad as well.
        (HERE / target).write_text(body, encoding="utf-8-sig", newline="\r\n")


if __name__ == "__main__":
    build()
