"""Build two self-contained Windows launchers from the verified R1 workers."""
from __future__ import annotations

from pathlib import Path


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "zip_parts_20261007_r1"
HEADER = r'''@echo off
setlocal
set "ZIP_PARTS_LAUNCHER=%~f0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$raw=[IO.File]::ReadAllText($env:ZIP_PARTS_LAUNCHER,[Text.Encoding]::UTF8); $marker=[regex]::Match($raw,'(?m)^# ZIP_PARTS_POWERSHELL\r?$'); if(-not $marker.Success) { Write-Host 'Invalid launcher file.'; Read-Host 'Press Enter'; exit 1 }; & ([scriptblock]::Create($raw.Substring($marker.Index+$marker.Length)))"
exit /b %errorlevel%
# ZIP_PARTS_POWERSHELL
'''
PREAMBLE = '''$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$status = 0
try {
    if ($PSVersionTable.PSVersion -lt [version]'5.1') {
        throw 'Windows PowerShell 5.1 or later is required.'
    }
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    if ($env:ZIP_PARTS_DESKTOP) {
        $desktop = [IO.Path]::GetFullPath($env:ZIP_PARTS_DESKTOP)
    }
    if (-not [IO.Directory]::Exists($desktop)) {
        throw "바탕화면 폴더를 찾을 수 없습니다: $desktop"
    }
    Write-Host ''
    Write-Host '__TITLE__'
    Write-Host "바탕화면: $desktop"
    Write-Host '파일 이름만 입력하세요. 한글과 공백도 사용할 수 있습니다.'
    $name = (Read-Host 'ZIP 파일 이름 (예: 자료.zip)').Trim().Trim('"')
    if ($name.EndsWith('.parts', [StringComparison]::OrdinalIgnoreCase)) {
        $name = $name.Substring(0, $name.Length - 6)
    }
    if ([string]::IsNullOrWhiteSpace($name) -or $name -in @('.', '..') -or
        $name.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
        $name.Contains('/') -or $name.Contains('\\')) {
        throw '경로 대신 ZIP 파일 이름만 입력하세요.'
    }
    if (-not $name.EndsWith('.zip', [StringComparison]::OrdinalIgnoreCase)) {
        $name += '.zip'
    }
    $source = [IO.Path]::Combine($desktop, $name)
    $worker = {
__WORKER__
    }
__ACTION__
} catch {
    $status = 1
    Write-Host ''
    Write-Host ('실패: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host '파일 이름과 실제 저장 위치를 확인하세요. 원본은 보존합니다.'
} finally {
    if ($env:ZIP_PARTS_NO_PAUSE -ne '1') {
        Write-Host '창을 닫으려면 Enter를 누르세요'
        [void](Read-Host)
    }
}
exit $status
'''
SPLIT = '''    if (-not [IO.File]::Exists($source)) {
        throw "바탕화면에 ZIP 파일이 없습니다: $name"
    }
    Write-Host '49MB 이하 조각으로 나누는 중입니다. 잠시 기다려 주세요.'
    & $worker -InputFile $source
    Write-Host ''
    Write-Host '분할 완료. 조각 폴더 안의 모든 파일과 parts-manifest.json을 함께 옮기세요.' -ForegroundColor Green
'''
JOIN = '''    $parts = $source + '.parts'
    if (-not [IO.Directory]::Exists($parts)) {
        throw "바탕화면에 조각 폴더가 없습니다: $name.parts"
    }
    $stem = [IO.Path]::GetFileNameWithoutExtension($name)
    $output = [IO.Path]::Combine($desktop, $stem + '_restored.zip')
    if ([IO.File]::Exists($output) -or [IO.Directory]::Exists($output)) {
        $suffix = [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
        $output = [IO.Path]::Combine($desktop, $stem + '_restored_' + $suffix + '.zip')
    }
    Write-Host '조각을 합치고 원본 해시를 검사하는 중입니다. 잠시 기다려 주세요.'
    & $worker -PartsDirectory $parts -OutputFile $output
    Write-Host ''
    Write-Host "병합 완료: $output" -ForegroundColor Green
'''


def build() -> None:
    for filename, title, worker, action in (
        ("1_SPLIT_ZIP.cmd", "ZIP 나누기", "Split-ZipParts.ps1", SPLIT),
        ("2_JOIN_ZIP.cmd", "ZIP 합치기", "Join-ZipParts.ps1", JOIN),
    ):
        body = PREAMBLE.replace("__TITLE__", title).replace(
            "__WORKER__", (BASE / worker).read_text(encoding="ascii")
        ).replace("__ACTION__", action)
        # ASCII batch header; UTF-8 payload is explicitly decoded by PowerShell.
        raw = (HEADER + body).replace("\n", "\r\n").encode("utf-8")
        (HERE / filename).write_bytes(raw)
        (HERE / (filename + ".txt")).write_bytes(raw)


if __name__ == "__main__":
    build()
