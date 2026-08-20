from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ternary_image_editor.constants import SAVE_RGB
from ternary_image_editor.errors import (
    ExternalOutputModificationError,
    OutputSaveLockError,
)
from ternary_image_editor.image_io import validate_output_png
from ternary_image_editor.models import EditSource, ImagePair
from ternary_image_editor.session import ImageSession


def _save_original(path: Path, *, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (32, 96, 160))
    try:
        image.save(path, format="PNG")
    finally:
        image.close()


def _save_labels(path: Path, labels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(SAVE_RGB, dtype=np.uint8)[labels]
    image = Image.fromarray(rgb, mode="RGB")
    try:
        image.save(path, format="PNG")
    finally:
        image.close()


def _make_pair(tmp_path: Path, *, with_output: bool) -> ImagePair:
    labels = np.zeros((4, 6), dtype=np.uint8)
    original_path = tmp_path / "original" / "①-conflict.png"
    ternary_path = tmp_path / "ternary" / "001-conflict.png"
    output_path = tmp_path / "output" / "001-conflict.png"
    _save_original(original_path, size=(6, 4))
    _save_labels(ternary_path, labels)
    if with_output:
        _save_labels(output_path, labels)
    return ImagePair(
        key=None,
        original_path=original_path,
        ternary_path=ternary_path,
        output_path=output_path,
        ternary_stem=ternary_path.stem,
    )


def _child_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    previous = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root if not previous else os.pathsep.join((source_root, previous))
    )
    return environment


def _run_external_png_writer(path: Path, *, value: int) -> None:
    script = """
from pathlib import Path
import sys
from PIL import Image

path = Path(sys.argv[1])
value = int(sys.argv[2])
image = Image.new("RGB", (6, 4), (value, value, value))
try:
    image.save(path, format="PNG")
finally:
    image.close()
"""
    subprocess.run(
        [sys.executable, "-c", script, str(path), str(value)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=_child_environment(),
        capture_output=True,
        text=True,
        timeout=10,
    )


@contextmanager
def _external_process_holding_save_lock(output_path: Path) -> Iterator[None]:
    ready_path = output_path.with_name(f".{output_path.name}.lock-ready")
    script = """
from pathlib import Path
import sys
from ternary_image_editor.save_lock import acquire_output_save_lock

with acquire_output_save_lock(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text("locked", encoding="utf-8")
    if sys.stdin.readline() != "release\\n":
        raise SystemExit(3)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(output_path), str(ready_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[1],
        env=_child_environment(),
        text=True,
    )
    assert process.stdin is not None
    assert process.stderr is not None
    deadline = time.monotonic() + 10.0
    try:
        while not ready_path.is_file():
            if process.poll() is not None:
                _stdout, stderr = process.communicate(timeout=5)
                pytest.fail(
                    "child process did not acquire the save lock: "
                    f"exit={process.returncode} {stderr!r}"
                )
            if time.monotonic() >= deadline:
                pytest.fail("child process did not acquire the save lock within 10 seconds")
            time.sleep(0.01)
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        ready_path.unlink(missing_ok=True)
        raise
    try:
        yield
    finally:
        if process.poll() is None:
            process.stdin.write("release\n")
            process.stdin.flush()
        _stdout, stderr = process.communicate(timeout=10)
        ready_path.unlink(missing_ok=True)
        assert process.returncode == 0, stderr


def test_separate_process_save_lock_preserves_dirty_document_then_releases(
    tmp_path: Path,
) -> None:
    pair = _make_pair(tmp_path, with_output=True)
    session = ImageSession()
    session.open_pair(pair, EditSource.OUTPUT, expected_size=(6, 4))
    changed = session.labels.copy()
    changed[1, 2] = 2
    session.apply_labels(changed, "別過程lock試験")
    output_before = hashlib.sha256(pair.output_path.read_bytes()).hexdigest()

    with _external_process_holding_save_lock(pair.output_path):
        with pytest.raises(OutputSaveLockError, match="別プロセスが保存中"):
            session.save(expected_size=(6, 4))

    assert session.is_dirty
    assert hashlib.sha256(pair.output_path.read_bytes()).hexdigest() == output_before

    session.save(expected_size=(6, 4))

    assert not session.is_dirty
    assert np.array_equal(
        validate_output_png(pair.output_path, expected_size=(6, 4)).labels,
        changed,
    )


def test_separate_process_output_replacement_is_detected_and_preserved(
    tmp_path: Path,
) -> None:
    pair = _make_pair(tmp_path, with_output=True)
    session = ImageSession()
    session.open_pair(pair, EditSource.OUTPUT, expected_size=(6, 4))
    intended = session.labels.copy()
    intended[0, 0] = 2
    session.apply_labels(intended, "外部置換試験")

    _run_external_png_writer(pair.output_path, value=128)
    external_hash = hashlib.sha256(pair.output_path.read_bytes()).hexdigest()

    with pytest.raises(ExternalOutputModificationError):
        session.save(expected_size=(6, 4))

    assert session.is_dirty
    assert np.array_equal(session.labels, intended)
    assert hashlib.sha256(pair.output_path.read_bytes()).hexdigest() == external_hash
    assert np.all(validate_output_png(pair.output_path, expected_size=(6, 4)).labels == 1)
