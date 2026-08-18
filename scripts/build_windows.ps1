Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "Windows配布物はWindows上で作成すること"
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$DistPath = Join-Path $ProjectRoot "dist"
$BundlePath = Join-Path $DistPath "TernaryImageEditor"
$ArtifactPath = Join-Path $BundlePath "TernaryImageEditor.exe"
$SpecSource = Join-Path $ProjectRoot "docs/ternary_image_editor_spec_v1_5.html"
$SpecDirectory = Join-Path $BundlePath "docs"
$SpecPath = Join-Path $SpecDirectory "ternary_image_editor_spec_v1_5.html"
$ExpectedSpecHash = "ED267BDE1634072F1E3249D0C7D0670CDEC1DBD08E3130380844CFF492C0C497"

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit code $LASTEXITCODE)"
    }
}

uv sync --locked --python 3.11
Assert-NativeSuccess "uv sync"
uv run pytest
Assert-NativeSuccess "pytest"
uv run ruff check .
Assert-NativeSuccess "ruff"

if (Test-Path -LiteralPath $BundlePath) {
    Remove-Item -LiteralPath $BundlePath -Recurse -Force -ErrorAction Stop
}

uv run pyinstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "TernaryImageEditor" `
    --distpath $DistPath `
    --paths "src" `
    --collect-submodules "scipy" `
    "packaging/windows_entry.py"
Assert-NativeSuccess "PyInstaller"

if (-not (Test-Path -LiteralPath $ArtifactPath -PathType Leaf)) {
    throw "PyInstaller succeeded but the expected executable is missing: $ArtifactPath"
}

$Artifact = Get-Item -LiteralPath $ArtifactPath -ErrorAction Stop
if ($Artifact.Length -le 0) {
    throw "Generated executable is empty: $ArtifactPath"
}

$Stream = [System.IO.File]::Open(
    $ArtifactPath,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::Read
)
try {
    $FirstByte = $Stream.ReadByte()
    $SecondByte = $Stream.ReadByte()
}
finally {
    $Stream.Dispose()
}
if ($FirstByte -ne 0x4d -or $SecondByte -ne 0x5a) {
    throw "Generated executable does not have an MZ header: $ArtifactPath"
}

$Candidates = @(
    Get-ChildItem -LiteralPath $BundlePath -Filter "TernaryImageEditor.exe" -File -Recurse
)
if ($Candidates.Count -ne 1 -or $Candidates[0].FullName -ne $Artifact.FullName) {
    throw "Expected exactly one executable at the canonical path: $ArtifactPath"
}

$null = New-Item -ItemType Directory -Path $SpecDirectory -Force -ErrorAction Stop
Copy-Item -LiteralPath $SpecSource -Destination $SpecPath -Force -ErrorAction Stop
$SpecHash = (Get-FileHash -LiteralPath $SpecPath -Algorithm SHA256).Hash
if ($SpecHash -ne $ExpectedSpecHash) {
    throw "Bundled v1.5 specification hash mismatch: $SpecPath"
}

$ArtifactHash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash
Write-Host "配布候補: $ArtifactPath"
Write-Host "大きさ: $($Artifact.Length) bytes"
Write-Host "SHA-256: $ArtifactHash"
Write-Host "要求正本: $SpecPath"
Write-Host "要求正本SHA-256: $SpecHash"
