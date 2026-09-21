param(
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$ExpectedManifestSha256,
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$WorkspaceRoot,
    [Parameter(Mandatory)][string]$Destination
)
# Native preparation only. Never invoke the interpreter being verified.
$ErrorActionPreference = 'Stop'
function Assert-NoLink([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse path rejected' }
        }
        $parent = [IO.Directory]::GetParent($current)
        $current = if ($parent) { $parent.FullName } else { $null }
    }
}
function Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$source = [IO.Path]::GetFullPath($SourceRoot)
$target = [IO.Path]::GetFullPath($Destination)
$allowed = [IO.Path]::GetFullPath((Join-Path $WorkspaceRoot '.cache/m2-02b2/production_environment_candidate'))
if (-not $target.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Output must be a child of the bounded candidate cache'
}
Assert-NoLink $source
Assert-NoLink $target
Assert-NoLink $ManifestPath
foreach ($startupRoot in @($source, $target)) {
$startupAncestor = $startupRoot
while ($startupAncestor) {
    $controls = @(if (Test-Path -LiteralPath $startupAncestor) { Get-ChildItem -Force -LiteralPath $startupAncestor -File | Where-Object {
        $_.Name -ieq 'pyvenv.cfg' -or $_.Name -like '*._pth'
    } })
    if ($controls.Count) { throw 'Unlisted startup control rejected' }
    $parent = [IO.Directory]::GetParent($startupAncestor)
    $startupAncestor = if ($parent) { $parent.FullName } else { $null }
}
}
$nestedControls = @(Get-ChildItem -Force -Recurse -LiteralPath $source | Where-Object {
    ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    $_.Name -ieq 'pyvenv.cfg' -or $_.Name -like '*._pth'
})
if ($nestedControls.Count) { throw 'Unexpected startup control or reparse entry rejected' }
if (Test-Path -LiteralPath $target) { throw 'Existing candidate must not be overwritten' }
if ($ExpectedManifestSha256 -cnotmatch '^[0-9a-f]{64}$' -or (Hash $ManifestPath) -cne $ExpectedManifestSha256) {
    throw 'Independent manifest pin mismatch'
}
$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$pins = @($manifest.file_hashes.PSObject.Properties)
if ($pins.Count -eq 0) { throw 'Empty expected inventory' }
$names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($pin in $pins) {
    if ($pin.Name -match '(^|[/\\])\.\.?([/\\]|$)|:|^[/\\]' -or $pin.Value -cnotmatch '^[0-9a-f]{64}$') {
        throw 'Invalid inventory path or digest'
    }
    if (-not $names.Add($pin.Name.Replace('\', '/'))) { throw 'Duplicate case-folded path' }
    if ($pin.Name -match '(^|/)__pycache__(/|$)|\.py[co]$|\._pth$|(^|/)pyvenv\.cfg$') {
        throw 'Unreviewed startup or bytecode input'
    }
    $path = Join-Path $source $pin.Name
    Assert-NoLink $path
    if ((Hash $path) -cne $pin.Value) { throw "Source bytes mismatch: $($pin.Name)" }
}
# Copy verified bytes only; no caches or other unlisted source files are admitted.
New-Item -ItemType Directory -Path $target | Out-Null
foreach ($pin in $pins) {
    $path = Join-Path $target $pin.Name
    $parent = [IO.Path]::GetDirectoryName($path)
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    Copy-Item -LiteralPath (Join-Path $source $pin.Name) -Destination $path -ErrorAction Stop
    if ((Hash $path) -cne $pin.Value) { throw 'Copied bytes mismatch; partial candidate is unusable' }
}
$receipt = [ordered]@{
    kind = 'NATIVE_PREPYTHON_CANDIDATE_BYTE_VERIFICATION'
    expected_manifest_sha256 = $ExpectedManifestSha256
    files_verified = $pins.Count
    production_candidate_prepared = $true
    production_environment_approved = $false
    python_executed = $false
    trust_boundary = 'Expected pins require separate provenance; native OS, loader, kernel and hardware remain external.'
}
$receiptPath = Join-Path $target 'CANDIDATE_RECEIPT.json'
$stream = [IO.File]::Open($receiptPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($receipt | ConvertTo-Json -Depth 10))
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
} finally { $stream.Dispose() }
$receipt | ConvertTo-Json -Depth 10
