@echo off
setlocal
set "ZIP_PARTS_LAUNCHER=%~f0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$raw=[IO.File]::ReadAllText($env:ZIP_PARTS_LAUNCHER,[Text.Encoding]::UTF8); $marker=[regex]::Match($raw,'(?m)^# ZIP_PARTS_POWERSHELL\r?$'); if(-not $marker.Success) { Write-Host 'Invalid launcher file.'; Read-Host 'Press Enter'; exit 1 }; & ([scriptblock]::Create($raw.Substring($marker.Index+$marker.Length)))"
exit /b %errorlevel%
# ZIP_PARTS_POWERSHELL
$ErrorActionPreference = 'Stop'
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
    Write-Host 'ZIP 나누기'
    Write-Host "바탕화면: $desktop"
    Write-Host '파일 이름만 입력하세요. 한글과 공백도 사용할 수 있습니다.'
    $name = (Read-Host 'ZIP 파일 이름 (예: 자료.zip)').Trim().Trim('"')
    if ($name.EndsWith('.parts', [StringComparison]::OrdinalIgnoreCase)) {
        $name = $name.Substring(0, $name.Length - 6)
    }
    if ([string]::IsNullOrWhiteSpace($name) -or $name -in @('.', '..') -or
        $name.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
        $name.Contains('/') -or $name.Contains('\')) {
        throw '경로 대신 ZIP 파일 이름만 입력하세요.'
    }
    if (-not $name.EndsWith('.zip', [StringComparison]::OrdinalIgnoreCase)) {
        $name += '.zip'
    }
    $source = [IO.Path]::Combine($desktop, $name)
    $worker = {
#Requires -Version 5.1
<#
.SYNOPSIS
Split an existing file into <=50,000,000-byte pieces without extracting it.
.EXAMPLE
.\Split-ZipParts.ps1 -InputFile 'D:\Transfer\nfs-data.zip'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputFile,
    [string]$OutputDirectory,
    [ValidateRange(1, 50)][int]$ChunkSizeMB = 49
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Hex([byte[]]$Bytes) {
    return [BitConverter]::ToString($Bytes).Replace('-', '').ToLowerInvariant()
}

$source = Get-Item -LiteralPath $InputFile
if ($source -isnot [System.IO.FileInfo]) { throw 'InputFile must be a file.' }
if (-not $OutputDirectory) { $OutputDirectory = $source.FullName + '.parts' }
$destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
if ([IO.File]::Exists($destination) -or [IO.Directory]::Exists($destination)) {
    throw "Output already exists; choose a new directory: $destination"
}
$parent = [IO.Path]::GetDirectoryName($destination)
[void][IO.Directory]::CreateDirectory($parent)
$staging = $destination + '.partial-' + [Guid]::NewGuid().ToString('N')
[void][IO.Directory]::CreateDirectory($staging)
$reader = $null
$sourceHash = [Security.Cryptography.SHA256]::Create()
$copiedHash = [Security.Cryptography.SHA256]::Create()
$buffer = New-Object byte[] (1MB)
[long]$limit = [long]$ChunkSizeMB * 1000000
$parts = New-Object 'System.Collections.Generic.List[object]'

try {
    # FileShare.Read permits other readers but prevents writers on Windows.
    $reader = [IO.File]::Open($source.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    [long]$originalBytes = $reader.Length
    Write-Host 'Calculating original SHA-256...'
    $originalSha256 = Get-Hex ($sourceHash.ComputeHash($reader))
    [void]$reader.Seek(0, [IO.SeekOrigin]::Begin)
    [long]$copied = 0
    [int]$number = 1
    while ($copied -lt $originalBytes) {
        $name = '{0}.part{1:D4}' -f $source.Name, $number
        $partPath = [IO.Path]::Combine($staging, $name)
        $writer = $null
        $partHash = [Security.Cryptography.SHA256]::Create()
        [long]$partBytes = 0
        try {
            $writer = [IO.File]::Open($partPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            [long]$targetBytes = [Math]::Min($limit, $originalBytes - $copied)
            while ($partBytes -lt $targetBytes) {
                [int]$wanted = [Math]::Min([long]$buffer.Length, $targetBytes - $partBytes)
                $read = $reader.Read($buffer, 0, $wanted)
                if ($read -eq 0) { throw 'Input ended before its recorded length.' }
                $writer.Write($buffer, 0, $read)
                [void]$partHash.TransformBlock($buffer, 0, $read, $buffer, 0)
                [void]$copiedHash.TransformBlock($buffer, 0, $read, $buffer, 0)
                $partBytes += $read
                $copied += $read
                Write-Progress -Activity 'Splitting file' -Status $name -PercentComplete ([int](100.0 * $copied / $originalBytes))
            }
            [void]$partHash.TransformFinalBlock($buffer, 0, 0)
            $expectedPartHash = Get-Hex $partHash.Hash
            $writer.Flush($true)
        } finally {
            if ($null -ne $writer) { $writer.Dispose() }
            $partHash.Dispose()
        }
        # Re-read saved bytes to detect changes introduced while saving.
        $actual = Get-FileHash -LiteralPath $partPath -Algorithm SHA256
        if (([IO.FileInfo]$partPath).Length -ne $partBytes -or $actual.Hash -ne $expectedPartHash) {
            throw "Saved part differs from input bytes: $name"
        }
        $parts.Add([ordered]@{ name = $name; bytes = $partBytes; sha256 = $expectedPartHash })
        Write-Host ('Saved {0} ({1:N0} bytes)' -f $name, $partBytes)
        $number++
    }
    if ($reader.Length -ne $originalBytes -or $reader.ReadByte() -ne -1) {
        throw 'Input length changed during splitting.'
    }
    [void]$copiedHash.TransformFinalBlock($buffer, 0, 0)
    if ((Get-Hex $copiedHash.Hash) -ne $originalSha256) {
        throw 'Input content changed after its original SHA-256 was calculated.'
    }
    $manifest = [ordered]@{
        schema_version = 'split-archive-v1'
        archive = $source.Name
        archive_bytes = $originalBytes
        archive_sha256 = $originalSha256
        part_max_bytes = $limit
        parts = @($parts.ToArray())
    }
    $json = ($manifest | ConvertTo-Json -Depth 6) + [Environment]::NewLine
    $manifestPath = [IO.Path]::Combine($staging, 'parts-manifest.json')
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($manifestPath, $json, $utf8)
    if ([IO.File]::ReadAllText($manifestPath, $utf8) -cne $json) {
        throw 'Saved manifest differs from generated JSON.'
    }
    $reader.Dispose()
    $reader = $null
    [IO.Directory]::Move($staging, $destination)
    Write-Progress -Activity 'Splitting file' -Completed
    Write-Host "OK: $($parts.Count) part(s) plus parts-manifest.json"
    Write-Host "Directory: $destination"
    Write-Host "Original SHA-256: $originalSha256"
    Write-Host 'Transfer ALL parts AND parts-manifest.json together.'
} catch {
    Write-Warning "Incomplete files retained at: $staging"
    throw
} finally {
    if ($null -ne $reader) { $reader.Dispose() }
    $sourceHash.Dispose()
    $copiedHash.Dispose()
}

    }
    if (-not [IO.File]::Exists($source)) {
        throw "바탕화면에 ZIP 파일이 없습니다: $name"
    }
    Write-Host '49MB 이하 조각으로 나누는 중입니다. 잠시 기다려 주세요.'
    & $worker -InputFile $source
    Write-Host ''
    Write-Host '분할 완료. 조각 폴더 안의 모든 파일과 parts-manifest.json을 함께 옮기세요.' -ForegroundColor Green

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
