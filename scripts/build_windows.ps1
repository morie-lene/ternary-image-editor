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
$AddendumSource = Join-Path $ProjectRoot "docs/mouse-input-bindings-addendum.md"
$AddendumPath = Join-Path $SpecDirectory "mouse-input-bindings-addendum.md"
$ExpectedAddendumHash = "91D7FEC202E9C211DE29FCECAB5BA3DD78BE539B814FB1A58737B38C40964EBA"
$FlexibleInputAddendumSource = Join-Path $ProjectRoot "docs/flexible-input-pairing-addendum.md"
$FlexibleInputAddendumPath = Join-Path $SpecDirectory "flexible-input-pairing-addendum.md"
$ExpectedFlexibleInputAddendumHash = "CE148618E7CF049CBFE2FA13E00FC4F3CB17B4726C4BF8E878BD63EDCBB6255C"
$DisplayComparisonAddendumSource = Join-Path $ProjectRoot "docs/display-comparison-addendum.md"
$DisplayComparisonAddendumPath = Join-Path $SpecDirectory "display-comparison-addendum.md"
$ExpectedDisplayComparisonAddendumHash = "26F1FF442548D51F66BDB518A14D10D92E52E48C10DAEC877A8AB04AD27E3779"
$TransientMemoAddendumSource = Join-Path $ProjectRoot "docs/transient-memo-layer-addendum.md"
$TransientMemoAddendumPath = Join-Path $SpecDirectory "transient-memo-layer-addendum.md"
$ExpectedTransientMemoAddendumHash = "2EE72910899B8DAF9761BB41AD7312933444831E87DA5200B61B358594567FB0"
$IconDirectory = Join-Path $ProjectRoot "src/ternary_image_editor/assets"
$ExecutableIconSource = Join-Path $IconDirectory "app_icon.ico"
$RuntimeIconSource = Join-Path $IconDirectory "app_icon.png"
$BundledRuntimeIconPath = Join-Path $BundlePath "_internal\ternary_image_editor\assets\app_icon.png"
$TestDirectory = Join-Path $ProjectRoot "tests"
$PackagingTestPath = Join-Path $TestDirectory "test_packaging.py"
$FlexibleInputTestPath = Join-Path $TestDirectory "test_flexible_input_contract.py"
$DisplayComparisonTestPath = Join-Path $TestDirectory "test_display_comparison_contract.py"
$BrushResponsivenessTestPath = Join-Path $TestDirectory "test_brush_responsiveness_contract.py"
$TransientMemoTestPath = Join-Path $TestDirectory "test_transient_memo_layer_contract.py"
$MemoHistoryTestPath = Join-Path $TestDirectory "test_memo_history.py"
$RealSizeWorkflowTestPath = Join-Path $TestDirectory "test_real_size_workflow.py"
$ExternalProcessConflictsTestPath = Join-Path $TestDirectory "test_external_process_conflicts.py"
$IsolatedDistributionWorkflowTestPath = Join-Path $TestDirectory "test_isolated_distribution_workflow.py"

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit code $LASTEXITCODE)"
    }
}

foreach ($RequiredInput in @(
    $ExecutableIconSource,
    $RuntimeIconSource,
    $SpecSource,
    $AddendumSource,
    $FlexibleInputAddendumSource,
    $DisplayComparisonAddendumSource,
    $TransientMemoAddendumSource,
    $PackagingTestPath,
    $FlexibleInputTestPath,
    $DisplayComparisonTestPath,
    $BrushResponsivenessTestPath,
    $TransientMemoTestPath,
    $MemoHistoryTestPath,
    $RealSizeWorkflowTestPath,
    $ExternalProcessConflictsTestPath,
    $IsolatedDistributionWorkflowTestPath
)) {
    if (-not (Test-Path -LiteralPath $RequiredInput -PathType Leaf)) {
        throw "Required build input is missing: $RequiredInput"
    }
}

uv sync --locked --python 3.11
Assert-NativeSuccess "uv sync"
uv run pytest $TestDirectory
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
Copy-Item -LiteralPath $AddendumSource -Destination $AddendumPath -Force -ErrorAction Stop
$AddendumHash = (Get-FileHash -LiteralPath $AddendumPath -Algorithm SHA256).Hash
if ($AddendumHash -ne $ExpectedAddendumHash) {
    throw "Bundled mouse-input addendum hash mismatch: $AddendumPath"
}
Copy-Item `
    -LiteralPath $FlexibleInputAddendumSource `
    -Destination $FlexibleInputAddendumPath `
    -Force `
    -ErrorAction Stop
$FlexibleInputAddendumHash = (
    Get-FileHash -LiteralPath $FlexibleInputAddendumPath -Algorithm SHA256
).Hash
if ($FlexibleInputAddendumHash -ne $ExpectedFlexibleInputAddendumHash) {
    throw "Bundled flexible-input pairing addendum hash mismatch: $FlexibleInputAddendumPath"
}
Copy-Item `
    -LiteralPath $DisplayComparisonAddendumSource `
    -Destination $DisplayComparisonAddendumPath `
    -Force `
    -ErrorAction Stop
$DisplayComparisonAddendumHash = (
    Get-FileHash -LiteralPath $DisplayComparisonAddendumPath -Algorithm SHA256
).Hash
if ($DisplayComparisonAddendumHash -ne $ExpectedDisplayComparisonAddendumHash) {
    throw "Bundled display-comparison addendum hash mismatch: $DisplayComparisonAddendumPath"
}
Copy-Item `
    -LiteralPath $TransientMemoAddendumSource `
    -Destination $TransientMemoAddendumPath `
    -Force `
    -ErrorAction Stop
$TransientMemoAddendumHash = (
    Get-FileHash -LiteralPath $TransientMemoAddendumPath -Algorithm SHA256
).Hash
if ($TransientMemoAddendumHash -ne $ExpectedTransientMemoAddendumHash) {
    throw "Bundled transient-memo addendum hash mismatch: $TransientMemoAddendumPath"
}

$ArtifactHash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash
Write-Host "配布候補: $ArtifactPath"
Write-Host "大きさ: $($Artifact.Length) bytes"
Write-Host "SHA-256: $ArtifactHash"
Write-Host "アプリケーションアイコン: $BundledRuntimeIconPath"
Write-Host "アプリケーションアイコンSHA-256: $RuntimeIconHash"
Write-Host "要求正本: $SpecPath"
Write-Host "要求正本SHA-256: $SpecHash"
Write-Host "マウス入力割当追補: $AddendumPath"
Write-Host "マウス入力割当追補SHA-256: $AddendumHash"
Write-Host "可変入力・組合せ追補: $FlexibleInputAddendumPath"
Write-Host "可変入力・組合せ追補SHA-256: $FlexibleInputAddendumHash"
Write-Host "表示比較（暗）追補: $DisplayComparisonAddendumPath"
Write-Host "表示比較（暗）追補SHA-256: $DisplayComparisonAddendumHash"
Write-Host "一時メモ層追補: $TransientMemoAddendumPath"
Write-Host "一時メモ層追補SHA-256: $TransientMemoAddendumHash"
