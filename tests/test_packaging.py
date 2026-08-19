from __future__ import annotations

import hashlib
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_windows.ps1"


def _build_script() -> str:
    return BUILD_SCRIPT_PATH.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_public_pytest_configuration_collects_packaging_tests() -> None:
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = config["tool"]["pytest"]["ini_options"]

    assert pytest_options["testpaths"] == ["tests"]


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
    assert "$PackagingTestPath" in required_inputs
    assert "uv run pytest $TestDirectory" in script
    assert "Write-Warning" not in script
    assert script.index('Assert-NativeSuccess "uv sync"') > script.index("uv sync --locked")
    assert script.index('Assert-NativeSuccess "pytest"') > script.index(
        "uv run pytest $TestDirectory"
    )
    assert script.index('Assert-NativeSuccess "ruff"') > script.index("uv run ruff check .")
    assert script.index('Assert-NativeSuccess "PyInstaller"') > script.index("uv run pyinstaller")


def test_windows_build_fails_closed_and_pins_the_normative_specification() -> None:
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
    hash_index = script.index("Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256")
    report_index = script.index('Write-Host "配布候補: $ArtifactPath"')

    assert "Set-StrictMode -Version Latest" in script
    assert "uv sync --locked --python 3.11" in script
    assert "--distpath $DistPath" in script
    assert remove_index < build_index < success_index
    assert success_index < existence_index < length_index < header_index
    assert header_index < uniqueness_index < spec_copy_index < spec_hash_index
    assert spec_hash_index < hash_index < report_index
    assert "ternary_image_editor_spec_v1_5.html" in script
    spec_path = PROJECT_ROOT / "docs" / "ternary_image_editor_spec_v1_5.html"
    assert f'$ExpectedSpecHash = "{_sha256(spec_path)}"' in script


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
    required_source_paths = {
        "README.md",
        "packaging/windows_entry.py",
        "pyproject.toml",
        "scripts/build_windows.ps1",
        "docs/ternary_image_editor_spec_v1_5.html",
        "tests/test_packaging.py",
        "uv.lock",
    }
    for relative_path in required_source_paths:
        assert f"{source_root}/{relative_path}" in source_names
    public_test_paths = {
        name.removeprefix(f"{source_root}/")
        for name in source_names
        if name.startswith(f"{source_root}/tests/")
    }
    assert public_test_paths == {"tests/test_packaging.py"}

    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_names = set(wheel.namelist())
        entry_points_path = next(
            name for name in wheel_names if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = wheel.read(entry_points_path).decode("utf-8")

    assert "ternary_image_editor/__init__.py" in wheel_names
    assert "ternary_image_editor/app.py" in wheel_names
    assert "ternary_image_editor/assets/app_icon.ico" in wheel_names
    assert "ternary_image_editor/assets/app_icon.png" in wheel_names
    assert "ternary_image_editor/assets/app_icon.svg" in wheel_names
    assert not any(name.startswith("tests/") for name in wheel_names)
    assert "ternary-image-editor = ternary_image_editor.app:main" in entry_points
