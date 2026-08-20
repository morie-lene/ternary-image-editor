from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_isolated_workflow.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_verify_isolated_workflow_script",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_wheel(path: Path, *, version: str = "0.8.0") -> None:
    dist_info = f"ternary_image_editor-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            "\n".join(
                (
                    "Metadata-Version: 2.3",
                    "Name: ternary-image-editor",
                    f"Version: {version}",
                    "",
                )
            ),
        )


def test_dist_selection_uses_current_project_version(tmp_path: Path) -> None:
    script = _load_script()
    project_root = tmp_path / "project"
    dist = project_root / "dist"
    dist.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "ternary-image-editor"\nversion = "0.8.0"\n',
        encoding="utf-8",
    )
    _write_wheel(dist / "ternary_image_editor-0.7.1-py3-none-any.whl", version="0.7.1")
    expected = dist / "ternary_image_editor-0.8.0-py3-none-any.whl"
    _write_wheel(expected)

    selected = script.select_wheel(dist, project_root=project_root)

    assert selected.path == expected.resolve()
    assert selected.distribution == "ternary-image-editor"
    assert selected.version == "0.8.0"
    script._require_expected_wheel_hash("a" * 64, "A" * 64)
    with pytest.raises(script.VerificationFailure) as hash_failure:
        script._require_expected_wheel_hash("a" * 64, "b" * 64)
    assert hash_failure.value.stage == "wheel_selection"
    assert hash_failure.value.code == "wheel_hash_mismatch"


def test_dist_selection_fails_closed_when_target_is_not_unique(tmp_path: Path) -> None:
    script = _load_script()
    project_root = tmp_path / "project"
    dist = project_root / "dist"
    dist.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "ternary-image-editor"\nversion = "0.8.0"\n',
        encoding="utf-8",
    )
    _write_wheel(dist / "ternary_image_editor-0.8.0-py3-none-any.whl")
    _write_wheel(dist / "ternary_image_editor-0.8.0-1-py3-none-any.whl")

    with pytest.raises(script.VerificationFailure) as captured:
        script.select_wheel(dist, project_root=project_root)

    assert captured.value.stage == "wheel_selection"
    assert captured.value.code == "wheel_selection_not_unique"


def test_install_command_is_offline_and_targets_temporary_python(tmp_path: Path) -> None:
    script = _load_script()
    environment_python = tmp_path / "venv" / "bin" / "python"
    wheel_path = tmp_path / "ternary_image_editor-0.8.0-py3-none-any.whl"
    requirements_path = tmp_path / "locked-runtime-requirements.txt"

    export_command = script.build_lock_export_command(
        "uv",
        tmp_path,
        requirements_path,
    )
    dependency_command = script.build_locked_dependency_install_command(
        "uv",
        environment_python,
        requirements_path,
    )
    command = script.build_install_command("uv", environment_python, wheel_path)
    check_command = script.build_environment_check_command("uv", environment_python)

    assert export_command[:2] == ["uv", "export"]
    assert "--locked" in export_command
    assert "--offline" in export_command
    assert "--no-default-groups" in export_command
    assert "--no-emit-project" in export_command
    assert export_command[export_command.index("--output-file") + 1] == str(
        requirements_path
    )
    assert dependency_command[:3] == ["uv", "pip", "install"]
    assert "--require-hashes" in dependency_command
    assert "--offline" in dependency_command
    assert dependency_command[dependency_command.index("--python") + 1] == str(
        environment_python
    )
    assert dependency_command[-1] == str(requirements_path)
    assert command[:3] == ["uv", "pip", "install"]
    assert "--offline" in command
    assert "--no-sources" in command
    assert "--no-deps" in command
    assert command[command.index("--python") + 1] == str(environment_python)
    assert command[-1] == str(wheel_path)
    assert check_command[:3] == ["uv", "pip", "check"]
    assert check_command[check_command.index("--python") + 1] == str(
        environment_python
    )
    assert script._installation_evidence(
        lock_sha256="a" * 64,
        requirements_sha256="b" * 64,
    ) == {
        "dependencies": "installed_from_uv_lock_export",
        "dependency_resolution": "exact_versions_and_hashes_offline_uv_cache",
        "environment": "temporary_venv",
        "lock_sha256": "a" * 64,
        "os_network_sandboxed": False,
        "requirements_sha256": "b" * 64,
    }
    success_payload = {
        "acceptance_boundary": script.ACCEPTANCE_BOUNDARY,
        "checks": dict.fromkeys(script.WORKFLOW_CHECKS, True),
        "declared_entry_point": script.EXPECTED_ENTRY_POINT,
        "display_mode": "qt_offscreen",
        "edit": {"label": 2, "x": 9, "y": 5},
        "installed_distributions": {
            "numpy": "2.4.6",
            "pillow": "12.3.0",
            "pyside6": "6.11.1",
            "pyside6-addons": "6.11.1",
            "pyside6-essentials": "6.11.1",
            "scipy": "1.17.1",
            "shiboken6": "6.11.1",
            "ternary-image-editor": "0.8.0",
        },
        "interaction_mode": "programmatic_no_physical_input",
        "launcher_executed": False,
        "module_relative_path": "lib/python3.11/site-packages/ternary_image_editor/__init__.py",
        "package_version": "0.8.0",
        "python_version": "3.11.15",
        "schema_version": script.SCHEMA_VERSION,
        "session_restart_mode": "same_process_new_main_window_and_image_session",
        "status": "ok",
        "wheel_sha256": "c" * 64,
    }
    script._validate_child_success_payload(
        success_payload,
        expected_version="0.8.0",
        wheel_sha256="c" * 64,
    )
    success_payload["checks"] = {"wheel_metadata": True}
    with pytest.raises(script.VerificationFailure) as child_failure:
        script._validate_child_success_payload(
            success_payload,
            expected_version="0.8.0",
            wheel_sha256="c" * 64,
        )
    assert child_failure.value.code == "child_checks_invalid"


def test_selection_failure_emits_stable_json_without_installing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()

    exit_code = script.main([str(tmp_path), "--version", "0.8.0"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload == {
        "error": {
            "code": "wheel_selection_not_unique",
            "details": {
                "dist": str(tmp_path.resolve()),
                "expected_version": "0.8.0",
                "matches": [],
            },
            "message": "Dist directory must contain exactly one matching project wheel",
            "next_action": (
                "Provide one exact wheel or one matching current-version wheel in dist."
            ),
            "stage": "wheel_selection",
        },
        "schema_version": "ternary-image-editor.isolated-workflow-verification/v1",
        "status": "error",
    }
