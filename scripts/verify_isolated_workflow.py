#!/usr/bin/env python3
"""Verify the installed-wheel GUI workflow with offline dependency installation.

Output contract ``ternary-image-editor.isolated-workflow-verification/v1``:

* Normal execution writes exactly one JSON object to stdout.  The script itself
  writes no diagnostics to stderr; captured child diagnostics are bounded strings
  inside ``error.details``.
* Success has ``schema_version: str``, ``status: "ok"``, a boolean ``checks``
  object, wheel identity, lock-bound installation evidence, installed versions,
  package version, declared entry point, installed module-relative path, edit
  coordinate, interaction/restart modes, and acceptance boundary.
* Failure has ``schema_version: str``, ``status: "error"``, and ``error`` with
  stable ``stage``, ``code``, ``message``, structured ``details``, and a
  ``next_action`` remediation hint.
* Exit 0 means every representative workflow check passed; exit 1 means selection,
  dependency, installation, or workflow failure; exit 2 means invalid arguments.
  ``--help`` is the sole human-readable stdout exception and exits 0.

Acceptance evidence supplies ``--expected-wheel-sha256`` from the same build and
identifies the source snapshot separately.  Without it, success identifies only
the selected artifact.  Ordinary test collection does not perform installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path
from typing import Any, NoReturn

SCHEMA_VERSION = "ternary-image-editor.isolated-workflow-verification/v1"
EXPECTED_DISTRIBUTION = "ternary-image-editor"
EXPECTED_ENTRY_POINT = "ternary_image_editor.app:main"
WHEEL_GLOB = "ternary_image_editor-*.whl"
EXPECTED_RUNTIME_DISTRIBUTIONS = {
    "numpy",
    "pillow",
    "pyside6",
    "pyside6-addons",
    "pyside6-essentials",
    "scipy",
    "shiboken6",
    "ternary-image-editor",
}
ACCEPTANCE_BOUNDARY = (
    "local_offscreen_programmatic_workflow_same_process_"
    "not_launcher_windows_or_pyinstaller"
)
WORKFLOW_CHECKS = (
    "wheel_metadata",
    "installed_origin",
    "offscreen_main_window_constructed",
    "image_loaded",
    "programmatic_edit_applied",
    "saved",
    "same_process_new_window_session",
    "output_priority_resume",
)


@dataclass(frozen=True, slots=True)
class WheelIdentity:
    path: Path
    distribution: str
    version: str


class VerificationFailure(RuntimeError):
    """A stable, stage-labelled verification failure."""

    def __init__(
        self,
        stage: str,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.details = details or {}
        self.exit_code = exit_code


class _MachineReadableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise VerificationFailure(
            "arguments",
            "invalid_arguments",
            message,
            exit_code=2,
        )


def _normalize_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _read_project_version(project_root: Path) -> str:
    pyproject_path = project_root / "pyproject.toml"
    try:
        config = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        version = config["project"]["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise VerificationFailure(
            "wheel_selection",
            "project_version_unavailable",
            f"Cannot determine the current project version from {pyproject_path}",
            details={"exception": type(exc).__name__},
        ) from exc
    if not isinstance(version, str) or not version:
        raise VerificationFailure(
            "wheel_selection",
            "project_version_invalid",
            f"Project version is not a non-empty string in {pyproject_path}",
        )
    return version


def read_wheel_identity(path: Path) -> WheelIdentity:
    """Read the distribution name and version from one wheel's METADATA."""

    wheel_path = Path(path).expanduser().resolve()
    if not wheel_path.is_file() or wheel_path.suffix.casefold() != ".whl":
        raise VerificationFailure(
            "wheel_selection",
            "wheel_path_invalid",
            f"Wheel path is not a .whl file: {wheel_path}",
        )
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            metadata_members = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_members) != 1:
                raise VerificationFailure(
                    "wheel_selection",
                    "wheel_metadata_ambiguous",
                    "Wheel must contain exactly one .dist-info/METADATA member",
                    details={"wheel": str(wheel_path), "count": len(metadata_members)},
                )
            metadata = BytesParser(policy=compat32).parsebytes(
                archive.read(metadata_members[0])
            )
    except VerificationFailure:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise VerificationFailure(
            "wheel_selection",
            "wheel_unreadable",
            f"Cannot read wheel metadata: {wheel_path}",
            details={"exception": type(exc).__name__},
        ) from exc

    distribution = metadata.get("Name")
    version = metadata.get("Version")
    if not distribution or not version:
        raise VerificationFailure(
            "wheel_selection",
            "wheel_identity_missing",
            "Wheel METADATA must contain Name and Version",
            details={"wheel": str(wheel_path)},
        )
    return WheelIdentity(wheel_path, distribution, version)


def select_wheel(
    artifact: Path,
    *,
    project_root: Path,
    expected_version: str | None = None,
) -> WheelIdentity:
    """Select one explicit wheel or one current-version wheel from a dist directory."""

    artifact_path = Path(artifact).expanduser().resolve()
    if artifact_path.is_file():
        identity = read_wheel_identity(artifact_path)
        _require_expected_wheel(identity, expected_version=expected_version)
        return identity
    if not artifact_path.is_dir():
        raise VerificationFailure(
            "wheel_selection",
            "artifact_path_missing",
            f"Artifact path is neither a wheel nor a directory: {artifact_path}",
        )

    selected_version = expected_version or _read_project_version(project_root)
    matches: list[WheelIdentity] = []
    for candidate in sorted(artifact_path.glob(WHEEL_GLOB)):
        identity = read_wheel_identity(candidate)
        if (
            _normalize_distribution_name(identity.distribution)
            == _normalize_distribution_name(EXPECTED_DISTRIBUTION)
            and identity.version == selected_version
        ):
            matches.append(identity)
    if len(matches) != 1:
        raise VerificationFailure(
            "wheel_selection",
            "wheel_selection_not_unique",
            "Dist directory must contain exactly one matching project wheel",
            details={
                "dist": str(artifact_path),
                "expected_version": selected_version,
                "matches": [match.path.name for match in matches],
            },
        )
    return matches[0]


def _require_expected_wheel(
    identity: WheelIdentity,
    *,
    expected_version: str | None,
) -> None:
    if _normalize_distribution_name(identity.distribution) != _normalize_distribution_name(
        EXPECTED_DISTRIBUTION
    ):
        raise VerificationFailure(
            "wheel_selection",
            "wheel_distribution_mismatch",
            f"Expected {EXPECTED_DISTRIBUTION}, got {identity.distribution}",
        )
    if expected_version is not None and identity.version != expected_version:
        raise VerificationFailure(
            "wheel_selection",
            "wheel_version_mismatch",
            f"Expected version {expected_version}, got {identity.version}",
        )


def _require_expected_wheel_hash(actual: str, expected: str | None) -> None:
    if expected is None:
        return
    normalized = expected.casefold()
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise VerificationFailure(
            "arguments",
            "expected_wheel_hash_invalid",
            "Expected wheel SHA-256 must contain exactly 64 hexadecimal characters",
            exit_code=2,
        )
    if actual != normalized:
        raise VerificationFailure(
            "wheel_selection",
            "wheel_hash_mismatch",
            "Selected wheel does not match the expected SHA-256",
            details={"actual": actual, "expected": normalized},
        )


def build_venv_command(
    uv_executable: str,
    venv_path: Path,
    python_selector: str,
) -> list[str]:
    """Return the no-project, no-download temporary-venv command."""

    return [
        uv_executable,
        "venv",
        "--no-project",
        "--no-config",
        "--no-python-downloads",
        "--python",
        python_selector,
        str(venv_path),
    ]


def build_lock_export_command(
    uv_executable: str,
    project_root: Path,
    requirements_path: Path,
) -> list[str]:
    """Export exact hashed runtime requirements from the co-located lock."""

    return [
        uv_executable,
        "export",
        "--project",
        str(project_root),
        "--format",
        "requirements.txt",
        "--locked",
        "--offline",
        "--no-default-groups",
        "--no-dev",
        "--no-emit-project",
        "--no-annotate",
        "--no-header",
        "--no-sources",
        "--output-file",
        str(requirements_path),
    ]


def build_locked_dependency_install_command(
    uv_executable: str,
    environment_python: Path,
    requirements_path: Path,
) -> list[str]:
    """Install the lock-exported runtime dependencies with exact hashes."""

    return [
        uv_executable,
        "pip",
        "install",
        "--no-config",
        "--offline",
        "--no-sources",
        "--only-binary",
        ":all:",
        "--require-hashes",
        "--strict",
        "--python",
        str(environment_python),
        "--requirements",
        str(requirements_path),
    ]


def build_install_command(
    uv_executable: str,
    environment_python: Path,
    wheel_path: Path,
) -> list[str]:
    """Install only the selected wheel after locked dependencies are present."""

    return [
        uv_executable,
        "pip",
        "install",
        "--no-config",
        "--offline",
        "--no-sources",
        "--no-deps",
        "--only-binary",
        ":all:",
        "--strict",
        "--python",
        str(environment_python),
        str(wheel_path),
    ]


def build_environment_check_command(
    uv_executable: str,
    environment_python: Path,
) -> list[str]:
    return [
        uv_executable,
        "pip",
        "check",
        "--no-config",
        "--offline",
        "--python",
        str(environment_python),
    ]


def _installation_evidence(
    *,
    lock_sha256: str,
    requirements_sha256: str,
) -> dict[str, str | bool]:
    return {
        "dependencies": "installed_from_uv_lock_export",
        "dependency_resolution": "exact_versions_and_hashes_offline_uv_cache",
        "environment": "temporary_venv",
        "lock_sha256": lock_sha256,
        "os_network_sandboxed": False,
        "requirements_sha256": requirements_sha256,
    }


def _venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _tail(value: str | bytes | None, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    stripped = value.strip()
    return stripped if len(stripped) <= limit else stripped[-limit:]


def _run_command(
    stage: str,
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise VerificationFailure(
            stage,
            "command_timed_out",
            f"Command exceeded {timeout:g} seconds",
            details={
                "stdout_tail": _tail(exc.stdout or ""),
                "stderr_tail": _tail(exc.stderr or ""),
            },
        ) from exc
    except OSError as exc:
        raise VerificationFailure(
            stage,
            "command_not_started",
            f"Cannot start command: {command[0]}",
            details={"exception": type(exc).__name__, "message": str(exc)},
        ) from exc
    if result.returncode != 0:
        raise VerificationFailure(
            stage,
            "command_failed",
            f"Command exited with status {result.returncode}",
            details={
                "returncode": result.returncode,
                "stdout_tail": _tail(result.stdout),
                "stderr_tail": _tail(result.stderr),
            },
        )
    return result


def _parse_child_payload(stdout: str) -> dict[str, Any]:
    for line in reversed([candidate for candidate in stdout.splitlines() if candidate.strip()]):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION:
            return payload
    raise VerificationFailure(
        "workflow",
        "child_result_missing",
        "Installed-runtime verifier did not emit the expected JSON envelope",
        details={"stdout_tail": _tail(stdout)},
    )


def _validate_child_success_payload(
    payload: dict[str, Any],
    *,
    expected_version: str,
    wheel_sha256: str,
) -> None:
    checks = payload.get("checks")
    installed = payload.get("installed_distributions")
    edit = payload.get("edit")
    exact_values = {
        "acceptance_boundary": ACCEPTANCE_BOUNDARY,
        "declared_entry_point": EXPECTED_ENTRY_POINT,
        "display_mode": "qt_offscreen",
        "interaction_mode": "programmatic_no_physical_input",
        "launcher_executed": False,
        "package_version": expected_version,
        "schema_version": SCHEMA_VERSION,
        "session_restart_mode": "same_process_new_main_window_and_image_session",
        "status": "ok",
        "wheel_sha256": wheel_sha256,
    }
    invalid_exact = {
        name: {"actual": payload.get(name), "expected": expected}
        for name, expected in exact_values.items()
        if payload.get(name) != expected
    }
    _require(
        not invalid_exact,
        "workflow",
        "child_success_contract_mismatch",
        "Installed-runtime success payload has invalid fixed fields",
        details={"fields": invalid_exact},
    )
    _require(
        isinstance(checks, dict)
        and set(checks) == set(WORKFLOW_CHECKS)
        and all(value is True for value in checks.values()),
        "workflow",
        "child_checks_invalid",
        "Installed-runtime success payload must contain exactly eight true checks",
        details={"checks": checks},
    )
    _require(
        isinstance(installed, dict)
        and bool(installed)
        and all(
            isinstance(name, str)
            and bool(name)
            and isinstance(version, str)
            and bool(version)
            for name, version in installed.items()
        )
        and EXPECTED_RUNTIME_DISTRIBUTIONS <= set(installed)
        and installed.get(EXPECTED_DISTRIBUTION) == expected_version,
        "workflow",
        "installed_distributions_invalid",
        "Installed-runtime success payload must identify installed distribution versions",
        details={"installed_distributions": installed},
    )
    _require(
        isinstance(edit, dict)
        and set(edit) == {"label", "x", "y"}
        and all(type(value) is int for value in edit.values()),
        "workflow",
        "edit_evidence_invalid",
        "Installed-runtime success payload must identify one integer edit coordinate",
        details={"edit": edit},
    )
    _require(
        isinstance(payload.get("module_relative_path"), str)
        and bool(payload["module_relative_path"]),
        "workflow",
        "module_relative_path_invalid",
        "Installed-runtime success payload must identify the installed module path",
    )
    _require(
        isinstance(payload.get("python_version"), str)
        and re.fullmatch(r"3\.11\.\d+", payload["python_version"]) is not None,
        "workflow",
        "python_version_invalid",
        "Installed-runtime success payload must identify an exact Python 3.11 version",
        details={"python_version": payload.get("python_version")},
    )


def _orchestrate(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[1]
    identity = select_wheel(
        Path(args.artifact),
        project_root=project_root,
        expected_version=args.version,
    )
    wheel_digest = _sha256(identity.path)
    _require_expected_wheel_hash(wheel_digest, args.expected_wheel_sha256)
    lock_path = project_root / "uv.lock"
    if not lock_path.is_file():
        raise VerificationFailure(
            "lock_export",
            "lock_file_missing",
            f"Locked dependency source does not exist: {lock_path}",
        )
    lock_digest = _sha256(lock_path)
    uv_executable = args.uv or shutil.which("uv")
    if not uv_executable:
        raise VerificationFailure(
            "environment",
            "uv_not_found",
            "uv is required to create and populate the temporary environment",
        )

    base_environment = os.environ.copy()
    base_environment.update(
        {
            "NO_COLOR": "1",
            "UV_NO_PROGRESS": "1",
            "UV_OFFLINE": "1",
        }
    )

    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="tie-isolated-workflow-") as temporary:
        temporary_path = Path(temporary)
        venv_path = temporary_path / "venv"
        workflow_path = temporary_path / "workflow"
        requirements_path = temporary_path / "locked-runtime-requirements.txt"
        workflow_path.mkdir()
        _run_command(
            "lock_export",
            build_lock_export_command(uv_executable, project_root, requirements_path),
            cwd=project_root,
            environment=base_environment,
            timeout=120,
        )
        if not requirements_path.is_file() or requirements_path.stat().st_size == 0:
            raise VerificationFailure(
                "lock_export",
                "locked_requirements_missing",
                "uv lock export did not create a non-empty runtime requirements file",
            )
        requirements_digest = _sha256(requirements_path)
        _run_command(
            "environment_creation",
            build_venv_command(uv_executable, venv_path, args.python),
            cwd=temporary_path,
            environment=base_environment,
            timeout=120,
        )
        environment_python = _venv_python(venv_path)
        if not environment_python.is_file():
            raise VerificationFailure(
                "environment_creation",
                "environment_python_missing",
                "Temporary environment did not contain its expected Python executable",
            )
        _run_command(
            "locked_dependency_installation",
            build_locked_dependency_install_command(
                uv_executable,
                environment_python,
                requirements_path,
            ),
            cwd=temporary_path,
            environment=base_environment,
            timeout=300,
        )
        _run_command(
            "wheel_installation",
            build_install_command(uv_executable, environment_python, identity.path),
            cwd=temporary_path,
            environment=base_environment,
            timeout=300,
        )
        _run_command(
            "environment_validation",
            build_environment_check_command(uv_executable, environment_python),
            cwd=temporary_path,
            environment=base_environment,
            timeout=120,
        )
        _require(
            _sha256(identity.path) == wheel_digest,
            "wheel_installation",
            "wheel_changed_during_installation",
            "Selected wheel changed between hashing and installation",
        )
        _require(
            _sha256(lock_path) == lock_digest,
            "lock_export",
            "lock_changed_during_installation",
            "uv.lock changed between hashing and environment validation",
        )

        runtime_environment = base_environment.copy()
        for inherited_name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
            runtime_environment.pop(inherited_name, None)
        runtime_environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "QT_QPA_PLATFORM": "offscreen",
            }
        )
        runtime_command = [
            str(environment_python),
            str(script_path),
            "--_installed-runtime",
            "--_repo-root",
            str(project_root),
            "--_work-dir",
            str(workflow_path),
            "--_expected-version",
            identity.version,
            "--_wheel-sha256",
            wheel_digest,
        ]
        runtime_result = _run_command(
            "workflow",
            runtime_command,
            cwd=workflow_path,
            environment=runtime_environment,
            timeout=90,
        )
        payload = _parse_child_payload(runtime_result.stdout)
        _validate_child_success_payload(
            payload,
            expected_version=identity.version,
            wheel_sha256=wheel_digest,
        )
        payload["wheel"] = {
            "distribution": identity.distribution,
            "path": str(identity.path),
            "sha256": wheel_digest,
            "version": identity.version,
        }
        payload["installation"] = _installation_evidence(
            lock_sha256=lock_digest,
            requirements_sha256=requirements_digest,
        )

    assert temporary_path is not None
    payload["installation"]["temporary_environment_removed"] = not temporary_path.exists()
    return payload, 0


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _require(
    condition: bool,
    stage: str,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    if not condition:
        raise VerificationFailure(stage, code, message, details=details)


def _wait_for(
    application: Any,
    predicate: Any,
    *,
    stage: str,
    description: str,
    timeout: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        application.processEvents()
        if time.monotonic() >= deadline:
            raise VerificationFailure(
                stage,
                "qt_wait_timed_out",
                f"Timed out waiting for {description}",
            )
        time.sleep(0.01)
    application.processEvents()


def _window_is_idle(window: Any) -> bool:
    return (
        window._active_job is None
        and window._latest_component_token is None
        and not window._workers
    )


def _verify_loaded_module_origins(repo_root: Path) -> str:
    source_root = (repo_root / "src").resolve()
    environment_root = Path(sys.prefix).resolve()
    offending: dict[str, str] = {}
    package_file: Path | None = None
    for module_name, module in sorted(sys.modules.items()):
        if module_name != "ternary_image_editor" and not module_name.startswith(
            "ternary_image_editor."
        ):
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        resolved = Path(module_file).resolve()
        if module_name == "ternary_image_editor":
            package_file = resolved
        if _is_relative_to(resolved, source_root) or not _is_relative_to(
            resolved, environment_root
        ):
            offending[module_name] = str(resolved)
    _require(
        package_file is not None,
        "installed_origin",
        "package_origin_missing",
        "Installed package has no inspectable file origin",
    )
    _require(
        not offending,
        "installed_origin",
        "source_or_external_import_detected",
        "All ternary_image_editor modules must load from the temporary environment",
        details={"offending_modules": offending},
    )
    for sys_path_entry in sys.path:
        if sys_path_entry and Path(sys_path_entry).resolve() == source_root:
            raise VerificationFailure(
                "installed_origin",
                "repo_source_on_sys_path",
                "Repository src directory is present on sys.path",
            )
    assert package_file is not None
    return package_file.relative_to(environment_root).as_posix()


def _close_window(window: Any, application: Any) -> None:
    window._allow_close_once = True
    window.close()
    application.processEvents()


def _installed_workflow(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    from importlib import metadata

    import numpy as np
    from PIL import Image
    from PySide6.QtCore import QSettings

    import ternary_image_editor
    from ternary_image_editor.app import create_application
    from ternary_image_editor.constants import SAVE_RGB
    from ternary_image_editor.image_io import validate_output_png
    from ternary_image_editor.main_window import MainWindow
    from ternary_image_editor.models import EditSource, PairingMode

    repo_root = Path(args._repo_root).resolve()
    work_dir = Path(args._work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    distribution = metadata.distribution(EXPECTED_DISTRIBUTION)
    _require(
        distribution.version == args._expected_version,
        "wheel_metadata",
        "installed_version_mismatch",
        "Installed distribution version does not match the selected wheel",
        details={"expected": args._expected_version, "actual": distribution.version},
    )
    _require(
        ternary_image_editor.__version__ == args._expected_version,
        "wheel_metadata",
        "package_version_mismatch",
        "Package version does not match installed distribution metadata",
        details={
            "distribution": distribution.version,
            "package": ternary_image_editor.__version__,
        },
    )
    entry_points = [
        entry
        for entry in distribution.entry_points
        if entry.group == "gui_scripts" and entry.name == EXPECTED_DISTRIBUTION
    ]
    _require(
        len(entry_points) == 1 and entry_points[0].value == EXPECTED_ENTRY_POINT,
        "wheel_metadata",
        "gui_entry_point_mismatch",
        "Installed wheel does not expose the expected GUI entry point",
        details={"entries": [entry.value for entry in entry_points]},
    )
    module_relative_path = _verify_loaded_module_origins(repo_root)

    original_dir = work_dir / "original"
    ternary_dir = work_dir / "ternary"
    output_dir = work_dir / "output"
    for directory in (original_dir, ternary_dir, output_dir):
        directory.mkdir()

    height, width = 16, 24
    y_indices, x_indices = np.indices((height, width), dtype=np.uint8)
    original_rgb = np.stack(
        (
            x_indices * 7,
            y_indices * 11,
            (x_indices.astype(np.uint16) + y_indices.astype(np.uint16)).astype(np.uint8)
            * 5,
        ),
        axis=-1,
    ).astype(np.uint8)
    input_labels = np.zeros((height, width), dtype=np.uint8)
    input_labels[2:5, 2:6] = 1
    input_labels[7:9, 12:15] = 2
    Image.fromarray(original_rgb).save(original_dir / "original.png", format="PNG")
    input_rgb = np.asarray(SAVE_RGB, dtype=np.uint8)[input_labels]
    Image.fromarray(input_rgb).save(ternary_dir / "labels.png", format="PNG")

    application = create_application(["verify-isolated-workflow"])
    application.setQuitOnLastWindowClosed(False)
    first_settings = QSettings(
        str(work_dir / "first-settings.ini"),
        QSettings.Format.IniFormat,
    )
    first_settings.clear()
    first_window = MainWindow(settings=first_settings, expected_size=(width, height))
    first_window.show()
    application.processEvents()
    _require(
        first_window.isVisible(),
        "gui_started",
        "first_window_not_visible",
        "First MainWindow did not become visible under the offscreen platform",
    )
    first_result = first_window.configure_folders(
        original_dir,
        ternary_dir,
        output_dir,
        pairing_mode=PairingMode.NATURAL_ORDER,
        natural_order_confirmed=True,
    )
    _require(
        len(first_result.pairs) == 1 and first_result.blocking_reason is None,
        "image_loaded",
        "pairing_failed",
        "The generated real images did not form one usable pair",
        details={"blocking_reason": first_result.blocking_reason},
    )
    _require(
        first_window.open_pair(0),
        "image_loaded",
        "initial_open_failed",
        "MainWindow could not open the generated image pair",
    )
    _wait_for(
        application,
        lambda: _window_is_idle(first_window),
        stage="image_loaded",
        description="initial image analysis",
    )
    _require(
        first_window.session.edit_source is EditSource.INPUT,
        "image_loaded",
        "initial_source_not_input",
        "Initial open must use input when no output exists",
    )
    _require(
        first_window.canvas.has_image,
        "image_loaded",
        "canvas_image_missing",
        "MainWindow canvas did not receive the loaded images",
    )

    edit_y, edit_x, edit_label = 5, 9, 2
    _require(
        first_window.session.labels is not None,
        "edited",
        "session_labels_missing",
        "Loaded session does not expose labels",
    )
    edited_labels = first_window.session.labels.copy()
    edited_labels[edit_y, edit_x] = edit_label
    first_window._apply_generated_labels(edited_labels, "隔離配布経路検証")
    _wait_for(
        application,
        lambda: _window_is_idle(first_window),
        stage="edited",
        description="post-edit image analysis",
    )
    _require(
        first_window.session.is_dirty
        and first_window.session.labels is not None
        and int(first_window.session.labels[edit_y, edit_x]) == edit_label,
        "edited",
        "edit_not_applied",
        "MainWindow edit path did not commit the expected label",
    )

    first_session_id = first_window.session.session_id
    first_window.request_save()
    _wait_for(
        application,
        lambda: _window_is_idle(first_window),
        stage="saved",
        description="asynchronous save completion",
    )
    _require(
        first_window.session.pair is not None,
        "saved",
        "saved_pair_missing",
        "Saved session lost its image pair",
    )
    output_path = first_window.session.pair.output_path
    _require(
        output_path.is_file() and not first_window.session.is_dirty,
        "saved",
        "output_not_committed",
        "MainWindow save did not create a clean output file",
    )
    saved = validate_output_png(output_path, expected_size=(width, height))
    _require(
        np.array_equal(saved.labels, edited_labels),
        "saved",
        "saved_labels_mismatch",
        "Strict output reload did not preserve the complete edited label array",
    )
    _close_window(first_window, application)

    second_settings = QSettings(
        str(work_dir / "second-settings.ini"),
        QSettings.Format.IniFormat,
    )
    second_settings.clear()
    second_window = MainWindow(settings=second_settings, expected_size=(width, height))
    second_window.show()
    application.processEvents()
    _require(
        second_window.isVisible(),
        "new_session",
        "second_window_not_visible",
        "Second same-process MainWindow did not become visible",
    )
    second_result = second_window.configure_folders(
        original_dir,
        ternary_dir,
        output_dir,
        pairing_mode=PairingMode.NATURAL_ORDER,
        natural_order_confirmed=True,
    )
    _require(
        len(second_result.pairs) == 1 and second_window.open_pair(0),
        "output_priority_resume",
        "resume_open_failed",
        "Second same-process MainWindow could not reopen the pair",
    )
    _wait_for(
        application,
        lambda: _window_is_idle(second_window),
        stage="output_priority_resume",
        description="restart-equivalent image analysis",
    )
    _require(
        second_window.session.session_id is not None
        and second_window.session.session_id != first_session_id,
        "new_session",
        "session_not_recreated",
        "Second same-process window did not create a distinct ImageSession identity",
    )
    _require(
        second_window.session.edit_source is EditSource.OUTPUT,
        "output_priority_resume",
        "output_priority_not_selected",
        "Omitted-source reopen did not prefer the existing output",
    )
    _require(
        second_window.session.labels is not None
        and np.array_equal(second_window.session.labels, edited_labels),
        "output_priority_resume",
        "resumed_labels_mismatch",
        "Output-priority reopen did not restore the complete saved label array",
    )
    _close_window(second_window, application)
    module_relative_path = _verify_loaded_module_origins(repo_root)
    installed_distributions = {
        _normalize_distribution_name(name): distribution_item.version
        for distribution_item in metadata.distributions()
        if (name := distribution_item.metadata.get("Name"))
    }

    payload: dict[str, Any] = {
        "acceptance_boundary": ACCEPTANCE_BOUNDARY,
        "checks": dict.fromkeys(WORKFLOW_CHECKS, True),
        "declared_entry_point": EXPECTED_ENTRY_POINT,
        "display_mode": "qt_offscreen",
        "edit": {"label": edit_label, "x": edit_x, "y": edit_y},
        "installed_distributions": dict(sorted(installed_distributions.items())),
        "interaction_mode": "programmatic_no_physical_input",
        "launcher_executed": False,
        "module_relative_path": module_relative_path,
        "package_version": distribution.version,
        "python_version": sys.version.split()[0],
        "schema_version": SCHEMA_VERSION,
        "session_restart_mode": "same_process_new_main_window_and_image_session",
        "status": "ok",
        "wheel_sha256": args._wheel_sha256,
    }
    return payload, 0


def _build_parser() -> argparse.ArgumentParser:
    parser = _MachineReadableArgumentParser(
        description=(
            "Install one ternary-image-editor wheel into a disposable venv with offline "
            "dependency resolution and verify its offscreen load/edit/save/output-resume "
            "workflow."
        )
    )
    parser.add_argument(
        "artifact",
        nargs="?",
        default="dist",
        help="wheel file or dist directory (default: dist)",
    )
    parser.add_argument(
        "--version",
        help="exact expected version; dist defaults to the current pyproject version",
    )
    parser.add_argument(
        "--expected-wheel-sha256",
        help="fail unless the selected wheel matches this exact SHA-256",
    )
    parser.add_argument(
        "--python",
        default=str(Path(sys.executable).resolve()),
        help="Python selector passed to uv venv (default: current interpreter)",
    )
    parser.add_argument("--uv", help="uv executable path (default: PATH lookup)")
    parser.add_argument("--_installed-runtime", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_repo-root", help=argparse.SUPPRESS)
    parser.add_argument("--_work-dir", help=argparse.SUPPRESS)
    parser.add_argument("--_expected-version", help=argparse.SUPPRESS)
    parser.add_argument("--_wheel-sha256", help=argparse.SUPPRESS)
    return parser


def _error_payload(error: VerificationFailure) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "details": error.details,
            "message": str(error),
            "next_action": _next_action(error.stage),
            "stage": error.stage,
        },
        "schema_version": SCHEMA_VERSION,
        "status": "error",
    }


def _next_action(stage: str) -> str:
    if stage == "arguments":
        return "Correct the arguments and rerun."
    if stage == "wheel_selection":
        return "Provide one exact wheel or one matching current-version wheel in dist."
    if stage in {
        "environment",
        "environment_creation",
        "environment_validation",
        "lock_export",
        "locked_dependency_installation",
        "wheel_installation",
    }:
        return "Prime Python 3.11 and the locked uv cache locally, then rerun offline."
    if stage in {
        "wheel_metadata",
        "installed_origin",
        "gui_started",
        "image_loaded",
        "edited",
        "saved",
        "new_session",
        "output_priority_resume",
        "workflow",
    }:
        return "Inspect details, fix and rebuild the wheel workflow, then rerun."
    return "Inspect the exception details and rerun the verifier."


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        if args._installed_runtime:
            missing = [
                name
                for name in (
                    "_repo_root",
                    "_work_dir",
                    "_expected_version",
                    "_wheel_sha256",
                )
                if not getattr(args, name)
            ]
            if missing:
                raise VerificationFailure(
                    "arguments",
                    "installed_runtime_arguments_missing",
                    "Internal installed-runtime arguments are incomplete",
                    details={"missing": missing},
                    exit_code=2,
                )
            payload, exit_code = _installed_workflow(args)
        else:
            payload, exit_code = _orchestrate(args)
    except VerificationFailure as exc:
        payload, exit_code = _error_payload(exc), exc.exit_code
    except Exception as exc:  # noqa: BLE001 - top-level machine-readable boundary
        payload = _error_payload(
            VerificationFailure(
                "internal",
                "unexpected_exception",
                str(exc),
                details={"exception": type(exc).__name__},
            )
        )
        exit_code = 1
    _emit(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
