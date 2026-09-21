#requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$ExpectedManifestSha256,
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$WorkspaceRoot,
    [Parameter(Mandatory)][string]$Destination,
    [string]$StageName = 'synthetic'
)
# Windows native preparation only. No candidate interpreter is invoked.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Native retained-handle preparation requires Windows' }
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class CandidateDirectory {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern SafeFileHandle CreateFileW(string p, uint access, uint share,
        IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool CreateDirectoryW(string p, IntPtr security);
    public static SafeFileHandle Hold(string p) {
        var h = CreateFileW(p, 0, 3, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
        if (h.IsInvalid) { h.Dispose(); throw new System.ComponentModel.Win32Exception(); }
        return h; // No FILE_SHARE_DELETE: directory identity cannot be replaced while held.
    }
    public static void CreateNew(string p) {
        if (!CreateDirectoryW(p, IntPtr.Zero)) throw new System.ComponentModel.Win32Exception();
    }
}
'@
$held = [Collections.Generic.List[IDisposable]]::new()
$directories = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
function Hold-Directory([string]$Path, [bool]$Create = $false) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($directories.Contains($full)) { return }
    $parent = [IO.Directory]::GetParent($full)
    if ($parent) { Hold-Directory $parent.FullName $Create }
    if (-not [IO.Directory]::Exists($full)) {
        if (-not $Create) { throw 'Required directory absent' }
        [CandidateDirectory]::CreateNew($full)
    }
    $handle = [CandidateDirectory]::Hold($full)
    $held.Add($handle)
    if ([IO.File]::GetAttributes($full) -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse directory rejected' }
    [void]$directories.Add($full)
}
function Open-Source([string]$Path) {
    Hold-Directory ([IO.Path]::GetDirectoryName($Path))
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $held.Add($stream)
    if ([IO.File]::GetAttributes($Path) -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse file rejected' }
    return $stream
}
function Sha([byte[]]$Bytes) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}
function Stream-Sha([IO.Stream]$Stream) {
    $Stream.Position = 0
    $result = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Stream)).ToLowerInvariant()
    $Stream.Position = 0
    return $result
}
function Check-Json([System.Text.Json.JsonElement]$Element) {
    if ($Element.ValueKind -eq [System.Text.Json.JsonValueKind]::Object) {
        $keys = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($property in $Element.EnumerateObject()) {
            if (-not $keys.Add($property.Name)) { throw 'Duplicate or case-colliding JSON key' }
            Check-Json $property.Value
        }
    } elseif ($Element.ValueKind -eq [System.Text.Json.JsonValueKind]::Array) {
        foreach ($value in $Element.EnumerateArray()) { Check-Json $value }
    }
}
function Check-Startup([string]$Root) {
    $current = $Root
    while ($current) {
        if ([IO.Directory]::Exists($current)) {
            foreach ($file in Get-ChildItem -LiteralPath $current -Force -File) {
                if ($file.Name -ieq 'pyvenv.cfg' -or $file.Name -like '*._pth') { throw 'Startup control rejected' }
            }
        }
        $parent = [IO.Directory]::GetParent($current)
        $current = if ($parent) { $parent.FullName } else { $null }
    }
}
$source = [IO.Path]::GetFullPath($SourceRoot)
$target = [IO.Path]::GetFullPath($Destination)
$allowedRoots = @('.cache/m2-02b2/production_environment_candidate', '.cache/m2-02b2b/production_environment_candidate')
$confined = $false
foreach ($relative in $allowedRoots) {
    $allowed = [IO.Path]::GetFullPath((Join-Path $WorkspaceRoot $relative))
    if ($target.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { $confined = $true }
}
if (-not $confined) { throw 'Output must be a child of the bounded candidate cache' }
try {
    Hold-Directory $source
    # Hold only existing target ancestors until all input validation succeeds.
    $ancestor = [IO.Path]::GetDirectoryName($target)
    while (-not [IO.Directory]::Exists($ancestor)) { $ancestor = [IO.Path]::GetDirectoryName($ancestor) }
    Hold-Directory $ancestor
    Check-Startup $source
    Check-Startup $target
    foreach ($entry in Get-ChildItem -LiteralPath $source -Force -Recurse) {
        if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            $entry.Name -ieq 'pyvenv.cfg' -or $entry.Name -like '*._pth' -or
            $entry.Name -ieq '__pycache__' -or $entry.Name -match '\.py[co]$') { throw 'Excluded source entry' }
    }
    $manifestStream = Open-Source ([IO.Path]::GetFullPath($ManifestPath))
    # Bound allocation before authenticating untrusted input (reviewed manifests < 1 MiB).
    if ($manifestStream.Length -gt 8MB) { throw 'Manifest exceeds 8 MiB input limit' }
    $buffer = [IO.MemoryStream]::new()
    try { $manifestStream.CopyTo($buffer); $manifestBytes = $buffer.ToArray() } finally { $buffer.Dispose() }
    if ($ExpectedManifestSha256 -cnotmatch '^[a-f0-9]{64}$' -or (Sha $manifestBytes) -cne $ExpectedManifestSha256) { throw 'Manifest pin mismatch' }
    # Authentication, strict decoding and parsing all use the same retained bytes.
    $jsonText = [Text.UTF8Encoding]::new($false, $true).GetString($manifestBytes)
    $parsed = [System.Text.Json.JsonDocument]::Parse($jsonText)
    try { Check-Json $parsed.RootElement } finally { $parsed.Dispose() }
    $manifest = $jsonText | ConvertFrom-Json -AsHashtable
    if ($manifest -isnot [Collections.IDictionary] -or $manifest.file_hashes -isnot [Collections.IDictionary] -or $manifest.file_hashes.Count -eq 0) { throw 'Inventory required' }
    $pins = $manifest.file_hashes
    $names = [string[]]@($pins.Keys)
    [Array]::Sort($names, [StringComparer]::Ordinal)
    $ordered = [ordered]@{}
    $sources = @{}
    foreach ($name in $names) {
        if ($name -match '(^/|\\|:|(^|/)\.\.?(/|$)|//|/$|[ .](/|$))' -or
            $name -match '(^|/)__pycache__(/|$)|\.py[co]$|\._pth$|(^|/)pyvenv\.cfg$' -or
            $name -ieq 'CANDIDATE_RECEIPT.json' -or $pins[$name] -isnot [string] -or
            $pins[$name] -cnotmatch '^[a-f0-9]{64}$') { throw 'Invalid or excluded inventory entry' }
        $stream = Open-Source (Join-Path $source $name)
        if ((Stream-Sha $stream) -cne $pins[$name]) { throw 'Source bytes mismatch' }
        $sources[$name] = $stream
        $ordered[$name] = $pins[$name]
    }
    # COPY_BOUNDARY
    Hold-Directory ([IO.Path]::GetDirectoryName($target)) $true
    [CandidateDirectory]::CreateNew($target)
    Hold-Directory $target
    $outputs = @{}
    foreach ($name in $names) {
        $path = Join-Path $target $name
        Hold-Directory ([IO.Path]::GetDirectoryName($path)) $true
        $output = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::Read)
        $held.Add($output)
        $sources[$name].CopyTo($output)
        $output.Flush($true)
        if ((Stream-Sha $output) -cne $pins[$name]) { throw 'Copy mismatch; partial candidate unusable' }
        $outputs[$name] = $output
    }
    # PUBLICATION_BOUNDARY: exact snapshot check, not a promise of future filesystem immutability.
    $actual = @(Get-ChildItem -LiteralPath $target -Force -Recurse -File)
    if ($actual.Count -ne $names.Count) { throw 'Unexpected candidate files; partial candidate unusable' }
    foreach ($entry in Get-ChildItem -LiteralPath $target -Force -Recurse) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Candidate reparse entry' }
        if (-not $entry.PSIsContainer) {
            $relative = [IO.Path]::GetRelativePath($target, $entry.FullName).Replace('\', '/')
            if (-not $outputs.ContainsKey($relative)) { throw 'Unexpected candidate file' }
            if ((Stream-Sha $outputs[$relative]) -cne $pins[$relative]) { throw 'Final candidate mismatch' }
        }
    }
    $procedure = Open-Source $PSCommandPath
    $receipt = [ordered]@{
        kind = 'NATIVE_PREPYTHON_CANDIDATE_BYTE_VERIFICATION_V2'
        stage = $StageName
        expected_manifest_sha256 = $ExpectedManifestSha256
        inventory_sha256 = Sha ([Text.Encoding]::UTF8.GetBytes(($ordered | ConvertTo-Json -Compress -Depth 20)))
        verifier_sha256 = Stream-Sha $procedure
        files_verified = $names.Count
        production_candidate_prepared = $true
        production_environment_approved = $false
        python_executed = $false
    }
    $receiptStream = [IO.File]::Open((Join-Path $target 'CANDIDATE_RECEIPT.json'), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $held.Add($receiptStream)
    $bytes = [Text.Encoding]::UTF8.GetBytes(($receipt | ConvertTo-Json -Depth 10))
    $receiptStream.Write($bytes, 0, $bytes.Length)
    $receiptStream.Flush($true)
    $receipt | ConvertTo-Json -Depth 10
} finally {
    for ($i = $held.Count - 1; $i -ge 0; $i--) { $held[$i].Dispose() }
}
