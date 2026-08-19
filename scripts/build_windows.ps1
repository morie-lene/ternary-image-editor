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
$IconDirectory = Join-Path $ProjectRoot "src/ternary_image_editor/assets"
$ExecutableIconSource = Join-Path $IconDirectory "app_icon.ico"
$RuntimeIconSource = Join-Path $IconDirectory "app_icon.png"
$BundledRuntimeIconPath = Join-Path $BundlePath "_internal\ternary_image_editor\assets\app_icon.png"
$TestDirectory = Join-Path $ProjectRoot "tests"

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit code $LASTEXITCODE)"
    }
}

foreach ($RequiredAsset in @($ExecutableIconSource, $RuntimeIconSource)) {
    if (-not (Test-Path -LiteralPath $RequiredAsset -PathType Leaf)) {
        throw "Required application icon asset is missing: $RequiredAsset"
    }
}

uv sync --locked --python 3.11
Assert-NativeSuccess "uv sync"
if (Test-Path -LiteralPath $TestDirectory -PathType Container) {
    uv run pytest $TestDirectory
    Assert-NativeSuccess "pytest"
}
else {
    Write-Warning "tests/が公開取得物に含まれないためpytestを省略した。試験済みとは扱わないこと。"
}
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
    --icon $ExecutableIconSource `
    --contents-directory "_internal" `
    --distpath $DistPath `
    --paths "src" `
    --add-data "${RuntimeIconSource}:ternary_image_editor/assets" `
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

if (-not (Test-Path -LiteralPath $BundledRuntimeIconPath -PathType Leaf)) {
    throw "Bundled runtime icon is missing from the expected package path: $BundledRuntimeIconPath"
}
$RuntimeIconHash = (Get-FileHash -LiteralPath $RuntimeIconSource -Algorithm SHA256).Hash
$BundledRuntimeIconHash = (
    Get-FileHash -LiteralPath $BundledRuntimeIconPath -Algorithm SHA256
).Hash
if ($BundledRuntimeIconHash -ne $RuntimeIconHash) {
    throw "Bundled runtime icon hash mismatch: $BundledRuntimeIconPath"
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
Write-Host "アプリケーションアイコン: $BundledRuntimeIconPath"
Write-Host "アプリケーションアイコンSHA-256: $RuntimeIconHash"
Write-Host "要求正本: $SpecPath"
Write-Host "要求正本SHA-256: $SpecHash"
