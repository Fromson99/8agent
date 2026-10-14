#Requires -Version 5.1
<#
.SYNOPSIS
Restore a split file and verify every part and the complete SHA-256.
.EXAMPLE
.\Join-ZipParts.ps1 -PartsDirectory 'D:\Transfer\nfs-data.zip.parts' -OutputFile 'D:\Restored\nfs-data.zip'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PartsDirectory,
    [string]$OutputFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-LeafName([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name) -or $Name -in @('.', '..') -or
        $Name.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
        $Name.Contains('/') -or $Name.Contains('\')) {
        throw "Invalid file name in manifest: $Name"
    }
}
function Get-Hex([byte[]]$Bytes) {
    return [BitConverter]::ToString($Bytes).Replace('-', '').ToLowerInvariant()
}

$directory = Get-Item -LiteralPath $PartsDirectory
if ($directory -isnot [IO.DirectoryInfo]) { throw 'PartsDirectory must be a directory.' }
$manifestPath = [IO.Path]::Combine($directory.FullName, 'parts-manifest.json')
$manifest = [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
if ($manifest.schema_version -cne 'split-archive-v1') { throw 'Unsupported manifest schema.' }
Assert-LeafName $manifest.archive
if ($manifest.archive_sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid original SHA-256.' }
[long]$originalBytes = $manifest.archive_bytes
[long]$limit = $manifest.part_max_bytes
if ($originalBytes -lt 0 -or $limit -lt 1 -or $limit -gt 50000000) { throw 'Invalid manifest sizes.' }
$parts = @($manifest.parts)
$seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
[long]$sum = 0
foreach ($part in $parts) {
    Assert-LeafName $part.name
    if (-not $seen.Add($part.name)) { throw "Duplicate part name: $($part.name)" }
    if ($part.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid part SHA-256: $($part.name)" }
    [long]$size = $part.bytes
    if ($size -lt 1 -or $size -gt $limit -or $size -gt ($originalBytes - $sum)) {
        throw "Invalid part size: $($part.name)"
    }
    $path = [IO.Path]::Combine($directory.FullName, $part.name)
    if (-not [IO.File]::Exists($path)) { throw "Missing part: $($part.name)" }
    if (([IO.FileInfo]$path).Length -ne $size) { throw "Part size mismatch: $($part.name)" }
    $sum += $size
}
if ($sum -ne $originalBytes) { throw 'Part sizes do not equal the original size.' }
if (-not $OutputFile) { $OutputFile = [IO.Path]::Combine($directory.Parent.FullName, $manifest.archive) }
$destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputFile)
if ([IO.File]::Exists($destination) -or [IO.Directory]::Exists($destination)) {
    throw "Output already exists; choose a new output file: $destination"
}
[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
$temporary = $destination + '.partial-' + [Guid]::NewGuid().ToString('N')
$writer = $null
$wholeHash = [Security.Cryptography.SHA256]::Create()
$buffer = New-Object byte[] (1MB)
[long]$copied = 0

try {
    $writer = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    # The manifest array defines order, regardless of file listing order.
    foreach ($part in $parts) {
        $reader = $null
        $partHash = [Security.Cryptography.SHA256]::Create()
        try {
            $path = [IO.Path]::Combine($directory.FullName, $part.name)
            $reader = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
            [long]$partBytes = 0
            while (($read = $reader.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $partBytes += $read
                if ($partBytes -gt [long]$part.bytes) { throw "Part grew while reading: $($part.name)" }
                $writer.Write($buffer, 0, $read)
                [void]$partHash.TransformBlock($buffer, 0, $read, $buffer, 0)
                [void]$wholeHash.TransformBlock($buffer, 0, $read, $buffer, 0)
                $copied += $read
                Write-Progress -Activity 'Joining file' -Status $part.name -PercentComplete ([int](100.0 * $copied / $originalBytes))
            }
            [void]$partHash.TransformFinalBlock($buffer, 0, 0)
            if ($partBytes -ne [long]$part.bytes -or (Get-Hex $partHash.Hash) -ne $part.sha256) {
                throw "Part hash/size mismatch: $($part.name)"
            }
        } finally {
            if ($null -ne $reader) { $reader.Dispose() }
            $partHash.Dispose()
        }
        Write-Host "Verified $($part.name)"
    }
    [void]$wholeHash.TransformFinalBlock($buffer, 0, 0)
    if ($copied -ne $originalBytes -or (Get-Hex $wholeHash.Hash) -ne $manifest.archive_sha256) {
        throw 'Restored file does not match the original SHA-256/size.'
    }
    $writer.Flush($true)
    $writer.Dispose()
    $writer = $null
    $saved = Get-FileHash -LiteralPath $temporary -Algorithm SHA256
    if (([IO.FileInfo]$temporary).Length -ne $originalBytes -or $saved.Hash -ne $manifest.archive_sha256) {
        throw 'Saved restored file differs from original bytes.'
    }
    [IO.File]::Move($temporary, $destination)
    # Verify the final name as well; filesystem protection may depend on extension.
    $published = Get-FileHash -LiteralPath $destination -Algorithm SHA256
    if (([IO.FileInfo]$destination).Length -ne $originalBytes -or $published.Hash -ne $manifest.archive_sha256) {
        throw "Final file changed after rename; do not use it: $destination"
    }
    Write-Progress -Activity 'Joining file' -Completed
    Write-Host "OK: $destination"
    Write-Host "Verified original SHA-256: $($manifest.archive_sha256)"
} catch {
    if ([IO.File]::Exists($temporary)) { Write-Warning "Incomplete output retained at: $temporary" }
    throw
} finally {
    if ($null -ne $writer) { $writer.Dispose() }
    $wholeHash.Dispose()
}
