from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_windows.ps1"
ADDENDUM_PATH = PROJECT_ROOT / "docs" / "mouse-input-bindings-addendum.md"
FLEXIBLE_INPUT_ADDENDUM_PATH = (
    PROJECT_ROOT / "docs" / "flexible-input-pairing-addendum.md"
)
DISPLAY_COMPARISON_ADDENDUM_PATH = (
    PROJECT_ROOT / "docs" / "display-comparison-addendum.md"
)
TRANSIENT_MEMO_ADDENDUM_PATH = (
    PROJECT_ROOT / "docs" / "transient-memo-layer-addendum.md"
)


def _build_script() -> str:
    return BUILD_SCRIPT_PATH.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_public_pytest_configuration_collects_packaging_tests() -> None:
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = config["tool"]["pytest"]["ini_options"]
    package_init = (PROJECT_ROOT / "src" / "ternary_image_editor" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert pytest_options["testpaths"] == ["tests"]
    assert config["project"]["version"] == "0.8.0"
    assert f'__version__ = "{config["project"]["version"]}"' in package_init


def test_windows_build_requires_public_tests_and_checks_native_exit_codes() -> None:
    script = _build_script()
    required_inputs = script[
        script.index("foreach ($RequiredInput") : script.index("uv sync --locked")
    ]

    assert 'Assert-NativeSuccess "uv sync"' in script
    assert 'Assert-NativeSuccess "pytest"' in script
    assert 'Assert-NativeSuccess "ruff"' in script
    assert 'Assert-NativeSuccess "PyInstaller"' in script
    assert '$PackagingTestPath = Join-Path $TestDirectory "test_packaging.py"' in script
    assert (
        '$FlexibleInputTestPath = Join-Path $TestDirectory '
        '"test_flexible_input_contract.py"'
    ) in script
    assert (
        '$DisplayComparisonTestPath = Join-Path $TestDirectory '
        '"test_display_comparison_contract.py"'
    ) in script
    assert (
        '$BrushResponsivenessTestPath = Join-Path $TestDirectory '
        '"test_brush_responsiveness_contract.py"'
    ) in script
    assert (
        '$TransientMemoTestPath = Join-Path $TestDirectory '
        '"test_transient_memo_layer_contract.py"'
    ) in script
    assert '$MemoHistoryTestPath = Join-Path $TestDirectory "test_memo_history.py"' in script
    assert (
        '$RealSizeWorkflowTestPath = Join-Path $TestDirectory '
        '"test_real_size_workflow.py"'
    ) in script
    assert (
        '$ExternalProcessConflictsTestPath = Join-Path $TestDirectory '
        '"test_external_process_conflicts.py"'
    ) in script
    assert (
        '$IsolatedDistributionWorkflowTestPath = Join-Path $TestDirectory '
        '"test_isolated_distribution_workflow.py"'
    ) in script
    assert "$PackagingTestPath" in required_inputs
    assert "$FlexibleInputTestPath" in required_inputs
    assert "$DisplayComparisonTestPath" in required_inputs
    assert "$BrushResponsivenessTestPath" in required_inputs
    assert "$TransientMemoTestPath" in required_inputs
    assert "$MemoHistoryTestPath" in required_inputs
    assert "$RealSizeWorkflowTestPath" in required_inputs
    assert "$ExternalProcessConflictsTestPath" in required_inputs
    assert "$IsolatedDistributionWorkflowTestPath" in required_inputs
    assert "$AddendumSource" in required_inputs
    assert "$FlexibleInputAddendumSource" in required_inputs
    assert "$DisplayComparisonAddendumSource" in required_inputs
    assert "$TransientMemoAddendumSource" in required_inputs
    assert "uv run pytest $TestDirectory" in script
    assert "Write-Warning" not in script
    assert script.index('Assert-NativeSuccess "uv sync"') > script.index("uv sync --locked")
    assert script.index('Assert-NativeSuccess "pytest"') > script.index(
        "uv run pytest $TestDirectory"
    )
    assert script.index('Assert-NativeSuccess "ruff"') > script.index("uv run ruff check .")
    assert script.index('Assert-NativeSuccess "PyInstaller"') > script.index("uv run pyinstaller")


def test_windows_build_fails_closed_and_pins_the_normative_documents() -> None:
    script = _build_script()

    remove_index = script.index("Remove-Item -LiteralPath $BundlePath")
    build_index = script.index("uv run pyinstaller")
    success_index = script.index('Assert-NativeSuccess "PyInstaller"')
    existence_index = script.index("Test-Path -LiteralPath $ArtifactPath -PathType Leaf")
    length_index = script.index("$Artifact.Length -le 0")
    header_index = script.index("$FirstByte -ne 0x4d")
    uniqueness_index = script.index("$Candidates.Count -ne 1")
    spec_copy_index = script.index("Copy-Item -LiteralPath $SpecSource")
    spec_hash_index = script.index("Bundled v1.5 specification hash mismatch")
    addendum_copy_index = script.index("Copy-Item -LiteralPath $AddendumSource")
    addendum_hash_index = script.index("Bundled mouse-input addendum hash mismatch")
    flexible_addendum_copy_index = script.index(
        "-LiteralPath $FlexibleInputAddendumSource"
    )
    flexible_addendum_hash_index = script.index(
        "Bundled flexible-input pairing addendum hash mismatch"
    )
    display_addendum_copy_index = script.index(
        "-LiteralPath $DisplayComparisonAddendumSource"
    )
    display_addendum_hash_index = script.index(
        "Bundled display-comparison addendum hash mismatch"
    )
    transient_memo_addendum_copy_index = script.index(
        "-LiteralPath $TransientMemoAddendumSource"
    )
    transient_memo_addendum_hash_index = script.index(
        "Bundled transient-memo addendum hash mismatch"
    )
    hash_index = script.index("Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256")
    report_index = script.index('Write-Host "配布候補: $ArtifactPath"')

    assert "Set-StrictMode -Version Latest" in script
    assert "uv sync --locked --python 3.11" in script
    assert "--distpath $DistPath" in script
    assert remove_index < build_index < success_index
    assert success_index < existence_index < length_index < header_index
    assert header_index < uniqueness_index < spec_copy_index < spec_hash_index
    assert spec_hash_index < addendum_copy_index < addendum_hash_index
    assert addendum_hash_index < flexible_addendum_copy_index < flexible_addendum_hash_index
    assert (
        flexible_addendum_hash_index
        < display_addendum_copy_index
        < display_addendum_hash_index
    )
    assert (
        display_addendum_hash_index
        < transient_memo_addendum_copy_index
        < transient_memo_addendum_hash_index
    )
    assert transient_memo_addendum_hash_index < hash_index < report_index
    assert "ternary_image_editor_spec_v1_5.html" in script
    spec_path = PROJECT_ROOT / "docs" / "ternary_image_editor_spec_v1_5.html"
    assert f'$ExpectedSpecHash = "{_sha256(spec_path)}"' in script
    assert f'$ExpectedAddendumHash = "{_sha256(ADDENDUM_PATH)}"' in script
    assert (
        f'$ExpectedFlexibleInputAddendumHash = '
        f'"{_sha256(FLEXIBLE_INPUT_ADDENDUM_PATH)}"'
    ) in script
    assert (
        f'$ExpectedDisplayComparisonAddendumHash = '
        f'"{_sha256(DISPLAY_COMPARISON_ADDENDUM_PATH)}"'
    ) in script
    assert (
        f'$ExpectedTransientMemoAddendumHash = '
        f'"{_sha256(TRANSIENT_MEMO_ADDENDUM_PATH)}"'
    ) in script
    assert (
        'Write-Host "可変入力・組合せ追補: $FlexibleInputAddendumPath"'
        in script
    )
    assert (
        'Write-Host "可変入力・組合せ追補SHA-256: '
        '$FlexibleInputAddendumHash"'
    ) in script
    assert 'Write-Host "表示比較（暗）追補: $DisplayComparisonAddendumPath"' in script
    assert (
        'Write-Host "表示比較（暗）追補SHA-256: '
        '$DisplayComparisonAddendumHash"'
    ) in script
    assert 'Write-Host "一時メモ層追補: $TransientMemoAddendumPath"' in script
    assert (
        'Write-Host "一時メモ層追補SHA-256: '
        '$TransientMemoAddendumHash"'
    ) in script


def test_python_archives_contain_the_public_packaging_contract(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    source_archives = list(tmp_path.glob("ternary_image_editor-*.tar.gz"))
    wheels = list(tmp_path.glob("ternary_image_editor-*.whl"))
    assert len(source_archives) == 1
    assert len(wheels) == 1

    with tarfile.open(source_archives[0], "r:gz") as source_archive:
        source_names = source_archive.getnames()
        source_root = source_names[0].split("/", maxsplit=1)[0]
        benchmark_member = source_archive.extractfile(
            f"{source_root}/docs/brush-responsiveness-benchmark-2026-08-20.json"
        )
        assert benchmark_member is not None
        benchmark_evidence = json.loads(benchmark_member.read())
    required_source_paths = {
        "README.md",
        "packaging/windows_entry.py",
        "pyproject.toml",
        "scripts/benchmark_brush_responsiveness.py",
        "scripts/build_windows.ps1",
        "scripts/verify_isolated_workflow.py",
        "docs/brush-responsiveness-benchmark-2026-08-20.json",
        "docs/ternary_image_editor_spec_v1_5.html",
        "docs/mouse-input-bindings-addendum.md",
        "docs/flexible-input-pairing-addendum.md",
        "docs/display-comparison-addendum.md",
        "docs/transient-memo-layer-addendum.md",
        "docs/test-strategy.md",
        "docs/local-verification-2026-08-20-brush-responsiveness.md",
        "docs/local-verification-2026-08-20-local-acceptance.md",
        "docs/local-verification-2026-08-20-transient-memo.md",
        "docs/local-verification-2026-08-21-headed-macos.md",
        "tests/test_packaging.py",
        "tests/test_flexible_input_contract.py",
        "tests/test_display_comparison_contract.py",
        "tests/test_external_process_conflicts.py",
        "tests/test_isolated_distribution_workflow.py",
        "tests/test_brush_responsiveness_contract.py",
        "tests/test_real_size_workflow.py",
        "tests/test_transient_memo_layer_contract.py",
        "tests/test_memo_history.py",
        "uv.lock",
    }
    for relative_path in required_source_paths:
        assert f"{source_root}/{relative_path}" in source_names
    project_version = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    assert project_version == "0.8.0"
    assert benchmark_evidence["application_version"] == "0.7.1"
    assert benchmark_evidence["application_version"] != project_version
    assert benchmark_evidence["acceptance_boundary"].endswith(
        "not Windows input-to-photon acceptance"
    )
    assert {case["case"] for case in benchmark_evidence["cases"]} == {
        "actual-size-no-grid",
        "scale-8-auto-grid",
    }
    assert all(case["p50_speedup"] > 2.0 for case in benchmark_evidence["cases"])
    public_test_paths = {
        name.removeprefix(f"{source_root}/")
        for name in source_names
        if name.startswith(f"{source_root}/tests/")
    }
    assert public_test_paths == {
        "tests/test_brush_responsiveness_contract.py",
        "tests/test_display_comparison_contract.py",
        "tests/test_external_process_conflicts.py",
        "tests/test_flexible_input_contract.py",
        "tests/test_isolated_distribution_workflow.py",
        "tests/test_memo_history.py",
        "tests/test_packaging.py",
        "tests/test_real_size_workflow.py",
        "tests/test_transient_memo_layer_contract.py",
    }

    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_names = set(wheel.namelist())
        entry_points_path = next(
            name for name in wheel_names if name.endswith(".dist-info/entry_points.txt")
        )
        metadata_path = next(name for name in wheel_names if name.endswith(".dist-info/METADATA"))
        entry_points = wheel.read(entry_points_path).decode("utf-8")
        metadata = wheel.read(metadata_path).decode("utf-8")

    assert "ternary_image_editor/__init__.py" in wheel_names
    assert "ternary_image_editor/app.py" in wheel_names
    assert "ternary_image_editor/assets/app_icon.ico" in wheel_names
    assert "ternary_image_editor/assets/app_icon.png" in wheel_names
    assert "ternary_image_editor/assets/app_icon.svg" in wheel_names
    assert not any(name.startswith("tests/") for name in wheel_names)
    assert "ternary-image-editor = ternary_image_editor.app:main" in entry_points
    project_config = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = tomllib.loads(project_config)["project"]
    assert f"Version: {project['version']}\n" in metadata
