from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog

from ternary_image_editor import image_io, pairing
from ternary_image_editor import main_window as main_window_module
from ternary_image_editor.constants import SAVE_RGB, protected_start_y
from ternary_image_editor.errors import (
    ImageValidationError,
    JpegImportConfirmationRequired,
    PairDimensionError,
)
from ternary_image_editor.main_window import MainWindow
from ternary_image_editor.models import EditSource, ImagePair, PairingMode
from ternary_image_editor.operations import flood_fill4
from ternary_image_editor.session import ImageSession


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save_image(
    path: Path,
    pixels: np.ndarray,
    *,
    image_format: str,
    exif: Image.Exif | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(pixels)
    try:
        options = {} if exif is None else {"exif": exif}
        image.save(path, format=image_format, **options)
    finally:
        image.close()


def _save_label_png(path: Path, labels: np.ndarray, *, rgb: bool = False) -> None:
    values = np.asarray(SAVE_RGB, dtype=np.uint8)[labels]
    _save_image(path, values if rgb else values[:, :, 0], image_format="PNG")


def _make_png_pair(
    root: Path,
    *,
    original_size: tuple[int, int],
    ternary_size: tuple[int, int] | None = None,
) -> ImagePair:
    width, height = original_size
    ternary_width, ternary_height = ternary_size or original_size
    original_path = root / "original.png"
    ternary_path = root / "ternary.png"
    output_path = root / "output" / "ternary.png"
    _save_image(
        original_path,
        np.full((height, width, 3), 72, dtype=np.uint8),
        image_format="PNG",
    )
    _save_label_png(
        ternary_path,
        np.zeros((ternary_height, ternary_width), dtype=np.uint8),
    )
    return ImagePair(
        key=None,
        original_path=original_path,
        ternary_path=ternary_path,
        output_path=output_path,
        ternary_stem=ternary_path.stem,
        pairing_mode=PairingMode.NATURAL_ORDER,
    )


@pytest.mark.parametrize("mode", list(PairingMode))
def test_candidate_count_mismatch_blocks_every_mode_and_ignores_unsupported_files(
    tmp_path: Path,
    mode: PairingMode,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    original_dir.mkdir()
    ternary_dir.mkdir()
    (original_dir / "one.png").touch()
    (original_dir / "two.jpg").touch()
    (original_dir / "not-a-candidate.gif").touch()
    (ternary_dir / "one.png").touch()

    result = pairing.plan_pairing(
        original_dir,
        ternary_dir,
        output_dir,
        mode=mode,
    )

    assert result.pairs == []
    assert result.original_candidate_count == 2
    assert result.ternary_candidate_count == 1
    assert not result.counts_match
    assert result.blocking_reason is not None
    assert "件数不一致" in result.blocking_reason
    assert {item.reason_code for item in result.excluded} == {
        "candidate_count_mismatch",
        "unsupported_extension",
    }
    assert not output_dir.exists()


@pytest.mark.parametrize("mode", list(PairingMode))
def test_empty_candidate_group_reports_both_zero_counts_without_touching_output(
    tmp_path: Path,
    mode: PairingMode,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    original_dir.mkdir()
    ternary_dir.mkdir()
    (original_dir / "unsupported.gif").touch()

    result = pairing.pair_directories(
        original_dir,
        ternary_dir,
        output_dir,
        mode=mode,
    )

    assert result.pairs == []
    assert result.original_candidate_count == 0
    assert result.ternary_candidate_count == 0
    assert "原画像=0件" in (result.blocking_reason or "")
    assert "三値画像=0件" in (result.blocking_reason or "")
    assert {item.reason_code for item in result.excluded} == {
        "empty_candidate_group",
        "unsupported_extension",
    }
    diagnostic = MainWindow._pairing_failure_message(result)
    assert "原画像=0件" in diagnostic
    assert "三値画像=0件" in diagnostic
    assert "unsupported.gif" in diagnostic
    assert not result.output_checked
    assert not output_dir.exists()


def test_natural_order_pairs_independently_using_nfkc_and_numeric_runs(
    tmp_path: Path,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    original_dir.mkdir()
    ternary_dir.mkdir()
    for name in ("原10.png", "原⑤.png", "原2.png"):
        (original_dir / name).touch()
    for name in ("三値１０.png", "三値5.png", "三値②.png"):
        (ternary_dir / name).touch()

    result = pairing.plan_pairing(
        original_dir,
        ternary_dir,
        output_dir,
        mode=PairingMode.NATURAL_ORDER,
    )

    assert [pair.original_path.name for pair in result.pairs] == [
        "原2.png",
        "原⑤.png",
        "原10.png",
    ]
    assert [pair.ternary_path.name for pair in result.pairs] == [
        "三値②.png",
        "三値5.png",
        "三値１０.png",
    ]
    assert all(pair.key is None for pair in result.pairs)
    assert all(pair.pairing_mode is PairingMode.NATURAL_ORDER for pair in result.pairs)
    assert result.confirmation_required

    strict = pairing.plan_pairing(
        original_dir,
        ternary_dir,
        output_dir,
        mode=PairingMode.STRICT_KEY,
    )
    assert strict.pairing_mode is PairingMode.STRICT_KEY
    assert strict.pairs == []
    assert not strict.confirmation_required
    assert {item.reason_code for item in strict.excluded} == {"stem_too_short"}


def test_natural_order_output_collision_blocks_the_entire_plan(tmp_path: Path) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    original_dir.mkdir()
    ternary_dir.mkdir()
    for name in ("original1.png", "original2.png"):
        (original_dir / name).touch()
    (ternary_dir / "Mask1.png").touch()
    (ternary_dir / "mask1.jpg").touch()

    result = pairing.plan_pairing(
        original_dir,
        ternary_dir,
        output_dir,
        mode=PairingMode.NATURAL_ORDER,
    )

    assert result.pairs == []
    assert result.blocking_reason is not None
    assert "出力名衝突" in result.blocking_reason
    collisions = [
        item for item in result.excluded if item.reason_code == "output_name_collision"
    ]
    assert len(collisions) == 1
    assert len(collisions[0].paths) == 4
    assert not result.confirmation_required
    assert not output_dir.exists()


def test_pairing_plan_has_no_output_side_effect_until_finalize(tmp_path: Path) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "new-output"
    original_dir.mkdir()
    ternary_dir.mkdir()
    (original_dir / "original1.png").touch()
    (ternary_dir / "ternary1.png").touch()

    plan = pairing.plan_pairing(
        original_dir,
        ternary_dir,
        output_dir,
        mode=PairingMode.NATURAL_ORDER,
    )

    assert len(plan.pairs) == 1
    assert plan.confirmation_required
    assert not plan.output_checked
    assert not output_dir.exists()

    finalized = pairing.finalize_pairing(plan, output_dir)

    assert finalized is plan
    assert finalized.output_checked
    assert finalized.output_writable
    assert output_dir.is_dir()
    assert list(output_dir.iterdir()) == []


def test_quantize_l_all_values_matches_squared_srgb_distance_and_lower_tie() -> None:
    source = np.arange(256, dtype=np.uint8)[None, :]
    before = source.copy()
    source_rgb = np.repeat(source[:, :, None], 3, axis=2).astype(np.int32)
    palette = np.asarray(SAVE_RGB, dtype=np.int32)
    distances = np.sum(
        (source_rgb[:, :, None, :] - palette[None, None, :, :]) ** 2,
        axis=3,
        dtype=np.int64,
    )
    expected = np.argmin(distances, axis=2).astype(np.uint8)

    actual = image_io.quantize_srgb_to_labels(source)

    assert np.array_equal(actual, expected)
    assert actual[0, 64] == 0
    assert actual[0, 65] == 1
    assert np.array_equal(source, before)


def test_quantize_rgb_uses_lower_label_for_an_exact_tie_without_mutating_input() -> None:
    source = np.array([[[0, 64, 128], [64, 64, 64], [65, 64, 64]]], dtype=np.uint8)
    before = source.copy()

    actual = image_io.quantize_srgb_to_labels(source)

    assert actual.tolist() == [[0, 0, 1]]
    assert np.array_equal(source, before)

    samples = np.random.default_rng(0).integers(
        0,
        256,
        size=(32, 64, 3),
        dtype=np.uint8,
    )
    samples32 = samples.astype(np.int32)
    palette = np.asarray(SAVE_RGB, dtype=np.int32)
    expected = np.argmin(
        np.sum(
            (samples32[:, :, None, :] - palette[None, None, :, :]) ** 2,
            axis=3,
            dtype=np.int64,
        ),
        axis=2,
    ).astype(np.uint8)
    assert np.array_equal(image_io.quantize_srgb_to_labels(samples), expected)


@pytest.mark.parametrize("mode", ["L", "RGB"])
def test_load_ternary_accepts_l_and_rgb_jpeg_without_writing_source(
    tmp_path: Path,
    mode: str,
) -> None:
    path = tmp_path / f"labels-{mode}.jpg"
    if mode == "L":
        pixels = np.tile(np.array([20, 140, 240], dtype=np.uint8), (4, 1))
    else:
        row = np.array([[20, 30, 40], [140, 145, 150], [240, 230, 220]], dtype=np.uint8)
        pixels = np.tile(row[None, :, :], (4, 1, 1))
    _save_image(path, pixels, image_format="JPEG")
    before_hash = _sha256(path)

    loaded = image_io.load_ternary_image(path)

    assert loaded.labels.shape == (4, 3)
    assert loaded.labels.dtype == np.uint8
    assert loaded.import_report.source_format == "JPEG"
    assert loaded.import_report.quantized
    assert loaded.import_report.total_pixels == 12
    assert loaded.requires_save
    assert _sha256(path) == before_hash


def test_load_ternary_rejects_oriented_cmyk_and_fake_jpeg_without_writing(
    tmp_path: Path,
) -> None:
    oriented_path = tmp_path / "oriented.jpg"
    exif = Image.Exif()
    exif[274] = 2
    _save_image(
        oriented_path,
        np.full((3, 4, 3), 100, dtype=np.uint8),
        image_format="JPEG",
        exif=exif,
    )

    cmyk_path = tmp_path / "cmyk.jpg"
    cmyk = Image.new("CMYK", (4, 3), (0, 64, 128, 10))
    try:
        cmyk.save(cmyk_path, format="JPEG")
    finally:
        cmyk.close()

    fake_path = tmp_path / "fake.jpg"
    _save_image(
        fake_path,
        np.full((3, 4, 3), 100, dtype=np.uint8),
        image_format="PNG",
    )
    before_hashes = {path: _sha256(path) for path in (oriented_path, cmyk_path, fake_path)}

    with pytest.raises(ImageValidationError, match="Orientation"):
        image_io.load_ternary_image(oriented_path)
    with pytest.raises(ImageValidationError, match="RGBまたは8-bitグレースケール"):
        image_io.load_ternary_image(cmyk_path)
    with pytest.raises(ImageValidationError, match="実形式"):
        image_io.load_ternary_image(fake_path)

    assert {_path: _sha256(_path) for _path in before_hashes} == before_hashes


def test_png_ternary_branch_remains_exact_and_non_quantizing(tmp_path: Path) -> None:
    exact_path = tmp_path / "exact.png"
    invalid_path = tmp_path / "invalid.png"
    expected = np.array([[0, 1, 2], [2, 1, 0]], dtype=np.uint8)
    _save_label_png(exact_path, expected, rgb=True)
    invalid_pixels = np.asarray(SAVE_RGB, dtype=np.uint8)[expected].copy()
    invalid_pixels[0, 0] = (1, 1, 1)
    _save_image(invalid_path, invalid_pixels, image_format="PNG")
    hashes = {path: _sha256(path) for path in (exact_path, invalid_path)}

    loaded = image_io.load_ternary_image(exact_path)

    assert np.array_equal(loaded.labels, expected)
    assert loaded.import_report.source_format == "PNG"
    assert not loaded.import_report.quantized
    assert not loaded.requires_save
    with pytest.raises(ImageValidationError, match="三値以外"):
        image_io.load_ternary_image(invalid_path)
    assert {path: _sha256(path) for path in hashes} == hashes


def test_session_accepts_arbitrary_matching_dimensions(tmp_path: Path) -> None:
    pair = _make_png_pair(tmp_path / "matching", original_size=(19, 7))
    current = ImageSession()

    current.open_pair(pair, EditSource.INPUT)

    assert current.is_loaded
    assert current.original_rgb is not None
    assert current.original_rgb.shape == (7, 19, 3)
    assert current.labels is not None
    assert current.labels.shape == (7, 19)


def test_pair_dimension_failure_is_transactional_and_preserves_old_session(
    tmp_path: Path,
) -> None:
    valid_pair = _make_png_pair(tmp_path / "valid", original_size=(19, 7))
    invalid_pair = _make_png_pair(
        tmp_path / "invalid",
        original_size=(11, 6),
        ternary_size=(10, 6),
    )
    current = ImageSession()
    current.open_pair(valid_pair, EditSource.INPUT)
    old_session_id = current.session_id
    old_labels = current.labels.copy() if current.labels is not None else None

    with pytest.raises(PairDimensionError, match="画像対の寸法が一致しない"):
        current.open_pair(invalid_pair, EditSource.INPUT)

    assert current.pair == valid_pair
    assert current.session_id == old_session_id
    assert old_labels is not None
    assert current.labels is not None
    assert np.array_equal(current.labels, old_labels)
    assert current.edit_source is EditSource.INPUT


def test_jpeg_session_requires_opt_in_then_saves_rgb_png_without_mutating_sources(
    tmp_path: Path,
) -> None:
    root = tmp_path / "jpeg-session"
    original_path = root / "original.png"
    ternary_path = root / "ternary.jpg"
    output_path = root / "output" / "ternary.png"
    _save_image(
        original_path,
        np.full((6, 8, 3), 90, dtype=np.uint8),
        image_format="PNG",
    )
    _save_image(
        ternary_path,
        np.full((6, 8, 3), (150, 150, 150), dtype=np.uint8),
        image_format="JPEG",
    )
    pair = ImagePair(
        key=None,
        original_path=original_path,
        ternary_path=ternary_path,
        output_path=output_path,
        ternary_stem=ternary_path.stem,
        pairing_mode=PairingMode.NATURAL_ORDER,
    )
    source_hashes = {path: _sha256(path) for path in (original_path, ternary_path)}
    current = ImageSession()

    with pytest.raises(JpegImportConfirmationRequired):
        current.open_pair(pair, EditSource.INPUT)
    assert not current.is_loaded

    current.open_pair(pair, EditSource.INPUT, allow_jpeg_import=True)
    assert current.is_dirty
    assert current.import_requires_save
    assert current.import_report.quantized

    current.save()

    assert not current.is_dirty
    assert not current.import_requires_save
    assert output_path.is_file()
    assert image_io.inspect_png(output_path).color_type == 2
    assert image_io.validate_output_png(output_path).labels.shape == (6, 8)
    assert {path: _sha256(path) for path in source_hashes} == source_hashes


def test_dynamic_protected_start_normalization_and_operations() -> None:
    assert protected_start_y(1536) == 1436
    assert protected_start_y(101) == 1
    assert protected_start_y(100) == 100
    assert protected_start_y(80) == 80

    tall = np.ones((101, 2), dtype=np.uint8)
    normalized, changed_pixels = image_io.normalized_protected_labels_copy(tall)
    assert changed_pixels == 200
    assert np.all(normalized[0] == 1)
    assert not np.any(normalized[1:])
    assert np.all(tall == 1)

    short = np.ones((100, 2), dtype=np.uint8)
    short_normalized, short_changed = image_io.normalized_protected_labels_copy(short)
    assert short_changed == 0
    assert np.array_equal(short_normalized, short)

    tall_fill = flood_fill4(np.zeros((101, 3), dtype=np.uint8), (0, 0), 1)
    assert np.all(tall_fill[0] == 1)
    assert not np.any(tall_fill[1:])
    assert not np.any(flood_fill4(np.zeros((101, 3), dtype=np.uint8), (0, 1), 1))

    short_fill = flood_fill4(np.zeros((100, 3), dtype=np.uint8), (0, 0), 1)
    assert np.all(short_fill == 1)


def test_natural_confirmation_cancel_has_no_output_or_window_state_side_effect(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    original_dir.mkdir()
    ternary_dir.mkdir()
    (original_dir / "original1.png").touch()
    (ternary_dir / "ternary1.png").touch()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    try:
        monkeypatch.setattr(main_window_module, "confirm_natural_pairing", lambda *_args: False)

        result = window._prepare_pairing(
            (original_dir, ternary_dir, output_dir),
            PairingMode.NATURAL_ORDER,
        )

        assert result is None
        assert window.pairs == ()
        assert not output_dir.exists()
        assert not window.session.is_loaded
    finally:
        window._allow_close_once = True
        window.close()


def test_jpeg_cancel_precedes_unsaved_resolution_and_preserves_current_edit(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    labels = np.zeros((3, 4), dtype=np.uint8)
    for name, value in (("a.png", 70), ("b.png", 90)):
        _save_image(
            original_dir / name,
            np.full((3, 4, 3), value, dtype=np.uint8),
            image_format="PNG",
        )
    _save_label_png(ternary_dir / "a.png", labels)
    _save_image(
        ternary_dir / "b.jpg",
        np.full((3, 4, 3), 140, dtype=np.uint8),
        image_format="JPEG",
    )
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    window._request_components = lambda: None
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    try:
        result = window.configure_folders(
            original_dir,
            ternary_dir,
            output_dir,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert len(result.pairs) == 2
        assert window.open_pair(0)
        assert window.session.labels is not None
        edited = window.session.labels.copy()
        edited[0, 0] = 1
        window.session.apply_labels(edited, "試験編集")
        old_session_id = window.session.session_id
        old_labels = window.session.labels.copy()
        unsaved_calls: list[str] = []
        monkeypatch.setattr(
            main_window_module,
            "confirm_ternary_jpeg_import",
            lambda *_args: False,
        )
        monkeypatch.setattr(
            main_window_module,
            "ask_unsaved",
            lambda _parent, action: unsaved_calls.append(action),
        )

        window.request_open_index(1)

        assert unsaved_calls == []
        assert window.current_index == 0
        assert window.session.session_id == old_session_id
        assert window.session.is_dirty
        assert np.array_equal(window.session.labels, old_labels)
    finally:
        window._allow_close_once = True
        window.close()


def test_folder_selection_jpeg_cancel_precedes_output_probe(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "not-created"
    original_dir.mkdir()
    ternary_dir.mkdir()
    suffix = "x" * 27
    (original_dir / f"①-source-{suffix}.png").touch()
    ternary_path = ternary_dir / f"001-label-{suffix}.jpg"
    ternary_path.touch()

    class AcceptedFolderDialog:
        pairing_mode = PairingMode.STRICT_KEY
        folders = (original_dir, ternary_dir, output_dir)

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    try:
        monkeypatch.setattr(
            main_window_module,
            "FolderSelectionDialog",
            AcceptedFolderDialog,
        )
        monkeypatch.setattr(
            main_window_module,
            "confirm_ternary_jpeg_import",
            lambda _parent, path: path != ternary_path,
        )

        window._choose_folders()

        assert window.pairs == ()
        assert not window.session.is_loaded
        assert not output_dir.exists()
    finally:
        window._allow_close_once = True
        window.close()


def test_folder_preflight_rolls_back_when_invalid_png_skips_to_cancelled_jpeg(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_original = tmp_path / "old-original"
    old_ternary = tmp_path / "old-ternary"
    old_output = tmp_path / "old-output"
    labels = np.zeros((3, 4), dtype=np.uint8)
    _save_image(
        old_original / "old.png",
        np.full((3, 4, 3), 70, dtype=np.uint8),
        image_format="PNG",
    )
    _save_label_png(old_ternary / "old.png", labels)

    new_original = tmp_path / "new-original"
    new_ternary = tmp_path / "new-ternary"
    new_output = tmp_path / "new-output"
    for name, value in (("a.png", 90), ("b.png", 110)):
        _save_image(
            new_original / name,
            np.full((3, 4, 3), value, dtype=np.uint8),
            image_format="PNG",
        )
    _save_label_png(new_ternary / "a.png", np.zeros((3, 3), dtype=np.uint8))
    jpeg_path = new_ternary / "b.jpg"
    _save_image(
        jpeg_path,
        np.full((3, 4, 3), 140, dtype=np.uint8),
        image_format="JPEG",
    )

    class AcceptedFolderDialog:
        pairing_mode = PairingMode.NATURAL_ORDER
        folders = (new_original, new_ternary, new_output)

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    window._request_components = lambda: None
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    try:
        window.configure_folders(
            old_original,
            old_ternary,
            old_output,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert window.open_pair(0)
        assert window.session.labels is not None
        edited = window.session.labels.copy()
        edited[0, 0] = 1
        window.session.apply_labels(edited, "試験編集")
        old_session_id = window.session.session_id
        old_labels = window.session.labels.copy()
        old_pairs = window.pairs
        old_folders = window._folders
        source_hashes = {
            path: _sha256(path)
            for path in (*new_original.iterdir(), *new_ternary.iterdir())
        }
        unsaved_calls: list[str] = []
        jpeg_calls: list[Path] = []
        monkeypatch.setattr(
            main_window_module,
            "FolderSelectionDialog",
            AcceptedFolderDialog,
        )
        monkeypatch.setattr(main_window_module, "confirm_natural_pairing", lambda *_: True)
        monkeypatch.setattr(
            main_window_module,
            "confirm_ternary_jpeg_import",
            lambda _parent, path: jpeg_calls.append(path) or False,
        )
        monkeypatch.setattr(
            main_window_module,
            "ask_unsaved",
            lambda _parent, action: unsaved_calls.append(action),
        )
        monkeypatch.setattr(main_window_module, "show_error", lambda *_args: None)

        window._choose_folders()

        assert jpeg_calls == [jpeg_path]
        assert unsaved_calls == []
        assert window.session.session_id == old_session_id
        assert window.session.is_dirty
        assert np.array_equal(window.session.labels, old_labels)
        assert window.pairs == old_pairs
        assert window._folders == old_folders
        assert not new_output.exists()
        assert {path: _sha256(path) for path in source_hashes} == source_hashes
    finally:
        window._allow_close_once = True
        window.close()


def test_strict_scan_with_all_names_excluded_preserves_old_state_and_output(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_original = tmp_path / "old-original"
    old_ternary = tmp_path / "old-ternary"
    old_output = tmp_path / "old-output"
    labels = np.zeros((3, 4), dtype=np.uint8)
    _save_image(
        old_original / "old.png",
        np.full((3, 4, 3), 70, dtype=np.uint8),
        image_format="PNG",
    )
    _save_label_png(old_ternary / "old.png", labels)

    new_original = tmp_path / "new-original"
    new_ternary = tmp_path / "new-ternary"
    new_output = tmp_path / "new-output"
    suffix = "z" * 27
    _save_image(
        new_original / f"005-source-{suffix}.png",
        np.full((3, 4, 3), 90, dtype=np.uint8),
        image_format="PNG",
    )
    _save_label_png(new_ternary / f"007-label-{suffix}.png", labels)

    class AcceptedFolderDialog:
        pairing_mode = PairingMode.STRICT_KEY
        folders = (new_original, new_ternary, new_output)

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    window._request_components = lambda: None
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    try:
        window.configure_folders(
            old_original,
            old_ternary,
            old_output,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert window.open_pair(0)
        assert window.session.labels is not None
        edited = window.session.labels.copy()
        edited[0, 0] = 1
        window.session.apply_labels(edited, "試験編集")
        old_session_id = window.session.session_id
        old_labels = window.session.labels.copy()
        old_pairs = window.pairs
        old_folders = window._folders
        unsaved_calls: list[str] = []
        shown: list[str] = []
        monkeypatch.setattr(
            main_window_module,
            "FolderSelectionDialog",
            AcceptedFolderDialog,
        )
        monkeypatch.setattr(
            main_window_module,
            "ask_unsaved",
            lambda _parent, action: unsaved_calls.append(action),
        )
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda _parent, _title, message: shown.append(message),
        )

        window._choose_folders()

        assert unsaved_calls == []
        assert shown and "想定外の先頭文字列" in shown[0]
        assert window.session.session_id == old_session_id
        assert window.session.is_dirty
        assert np.array_equal(window.session.labels, old_labels)
        assert window.pairs == old_pairs
        assert window._folders == old_folders
        assert not new_output.exists()
    finally:
        window._allow_close_once = True
        window.close()


def test_discarded_navigation_commits_only_after_a_later_jpeg_is_accepted(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    labels = np.zeros((3, 4), dtype=np.uint8)
    for name, value in (("a.png", 70), ("b.png", 90), ("c.png", 110)):
        _save_image(
            original_dir / name,
            np.full((3, 4, 3), value, dtype=np.uint8),
            image_format="PNG",
        )
    _save_label_png(ternary_dir / "a.png", labels)
    _save_label_png(ternary_dir / "b.png", np.zeros((3, 3), dtype=np.uint8))
    jpeg_path = ternary_dir / "c.jpg"
    _save_image(
        jpeg_path,
        np.full((3, 4, 3), 140, dtype=np.uint8),
        image_format="JPEG",
    )

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    window._request_components = lambda: None
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    try:
        result = window.configure_folders(
            original_dir,
            ternary_dir,
            output_dir,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert len(result.pairs) == 3
        assert window.open_pair(0)
        assert window.session.labels is not None
        edited = window.session.labels.copy()
        edited[0, 0] = 1
        window.session.apply_labels(edited, "試験編集")
        old_session_id = window.session.session_id
        old_labels = window.session.labels.copy()
        unsaved_calls: list[str] = []
        jpeg_calls: list[Path] = []
        monkeypatch.setattr(
            main_window_module,
            "ask_unsaved",
            lambda _parent, action: (
                unsaved_calls.append(action) or main_window_module.UnsavedChoice.DISCARD
            ),
        )
        monkeypatch.setattr(
            main_window_module,
            "confirm_ternary_jpeg_import",
            lambda _parent, path: jpeg_calls.append(path) or False,
        )
        monkeypatch.setattr(main_window_module, "show_error", lambda *_args: None)

        window._request_directional_move(1)

        assert unsaved_calls == ["画像移動"]
        assert jpeg_calls == [jpeg_path]
        assert window.current_index == 0
        assert window.session.session_id == old_session_id
        assert window.session.is_dirty
        assert np.array_equal(window.session.labels, old_labels)
        assert list(output_dir.iterdir()) == []
    finally:
        window._allow_close_once = True
        window.close()
