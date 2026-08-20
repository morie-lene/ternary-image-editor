from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ternary_image_editor import image_io, pairing
from ternary_image_editor import main_window as main_window_module
from ternary_image_editor import session as session_module
from ternary_image_editor.constants import SAVE_RGB, protected_start_y
from ternary_image_editor.errors import (
    ExternalOutputModificationError,
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


def _make_natural_folders(
    root: Path,
    input_labels: list[np.ndarray],
    *,
    outputs: dict[int, np.ndarray] | None = None,
) -> tuple[Path, Path, Path]:
    original_dir = root / "original"
    ternary_dir = root / "ternary"
    output_dir = root / "output"
    outputs = outputs or {}
    for index, labels in enumerate(input_labels):
        name = f"{chr(ord('a') + index)}.png"
        height, width = labels.shape
        _save_image(
            original_dir / name,
            np.full((height, width, 3), 70 + index, dtype=np.uint8),
            image_format="PNG",
        )
        _save_label_png(ternary_dir / name, labels)
        if index in outputs:
            _save_label_png(output_dir / name, outputs[index], rgb=True)
    return original_dir, ternary_dir, output_dir


def _make_contract_window(qtbot, tmp_path: Path) -> MainWindow:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    window._request_components = lambda: None
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    return window


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
    assert "出力名の衝突" in result.blocking_reason
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


def test_original_reference_normalizes_decodable_encodings_without_writing(
    tmp_path: Path,
) -> None:
    paths: list[Path] = []

    rgba_path = tmp_path / "rgba.png"
    _save_image(
        rgba_path,
        np.full((3, 4, 4), (20, 40, 60, 80), dtype=np.uint8),
        image_format="PNG",
    )
    paths.append(rgba_path)

    indexed_path = tmp_path / "indexed.png"
    indexed = Image.new("P", (4, 3), 1)
    indexed.putpalette([0, 0, 0, 30, 60, 90] + [0, 0, 0] * 254)
    try:
        indexed.save(indexed_path, format="PNG")
    finally:
        indexed.close()
    paths.append(indexed_path)

    sixteen_path = tmp_path / "sixteen.png"
    _save_image(
        sixteen_path,
        np.full((3, 4), 4096, dtype=np.uint16),
        image_format="PNG",
    )
    paths.append(sixteen_path)

    cmyk_path = tmp_path / "cmyk.jpg"
    cmyk = Image.new("CMYK", (4, 3), (0, 64, 128, 10))
    try:
        cmyk.save(cmyk_path, format="JPEG")
    finally:
        cmyk.close()
    paths.append(cmyk_path)

    bad_icc_path = tmp_path / "bad-icc.png"
    bad_icc = Image.new("RGB", (4, 3), (10, 20, 30))
    try:
        bad_icc.save(
            bad_icc_path,
            format="PNG",
            icc_profile=b"not-an-icc-profile",
        )
    finally:
        bad_icc.close()
    paths.append(bad_icc_path)

    source_hashes = {path: _sha256(path) for path in paths}

    for path in paths:
        loaded = image_io.load_original_image(path, expected_size=(4, 3))
        assert loaded.rgb.shape == (3, 4, 3)
        assert loaded.rgb.dtype == np.uint8

    assert {path: _sha256(path) for path in paths} == source_hashes


def test_original_reference_uses_exif_transposed_dimensions_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "oriented.jpg"
    exif = Image.Exif()
    exif[274] = 6
    _save_image(
        path,
        np.full((3, 4, 3), 70, dtype=np.uint8),
        image_format="JPEG",
        exif=exif,
    )
    before_hash = _sha256(path)

    loaded = image_io.load_original_image(path, expected_size=(3, 4))

    assert loaded.rgb.shape == (4, 3, 3)
    assert _sha256(path) == before_hash

    with pytest.raises(ImageValidationError, match="寸法不一致"):
        image_io.load_original_image(path, expected_size=(4, 3))

    assert _sha256(path) == before_hash


def test_original_reference_still_rejects_undecodable_data_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    before_hash = _sha256(path)

    with pytest.raises(ImageValidationError, match="復号に失敗"):
        image_io.load_original_image(path, expected_size=(4, 3))

    assert _sha256(path) == before_hash


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

    with pytest.raises(PairDimensionError, match="画像対の寸法が一致しません"):
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


def test_existing_output_is_automatically_preferred_without_source_confirmation(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    input_labels = np.zeros((3, 4), dtype=np.uint8)
    output_labels = np.full((3, 4), 2, dtype=np.uint8)
    for name, value in (("a.png", 70), ("b.png", 90)):
        _save_image(
            original_dir / name,
            np.full((3, 4, 3), value, dtype=np.uint8),
            image_format="PNG",
        )
        _save_label_png(ternary_dir / name, input_labels)
    _save_label_png(output_dir / "b.png", output_labels, rgb=True)

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
        assert window._choose_edit_source(result.pairs[0]) is EditSource.INPUT
        assert window.open_pair(0)
        monkeypatch.setattr(
            QMessageBox,
            "exec",
            lambda *_args: pytest.fail("既存出力の編集元確認は不要"),
        )

        window.request_open_index(1)

        assert window.current_index == 1
        assert window.session.edit_source is EditSource.OUTPUT
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, output_labels)
    finally:
        window._allow_close_once = True
        window.close()


def test_direct_open_pair_without_source_uses_output_priority(
    qtbot,
    tmp_path: Path,
) -> None:
    input_labels = np.zeros((3, 4), dtype=np.uint8)
    output_labels = np.full((3, 4), 2, dtype=np.uint8)
    folders = _make_natural_folders(
        tmp_path / "direct-auto-source",
        [input_labels, input_labels],
        outputs={0: output_labels},
    )
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )

        assert window.open_pair(0)
        assert window.session.edit_source is EditSource.OUTPUT
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, output_labels)

        assert window.open_pair(0, EditSource.INPUT)
        assert window.session.edit_source is EditSource.INPUT
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, input_labels)

        assert window.open_pair(1)
        assert window.session.edit_source is EditSource.INPUT
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, input_labels)
    finally:
        window._allow_close_once = True
        window.close()


def test_cold_start_auto_opens_first_strict_pair_from_existing_output(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_dir = tmp_path / "cold-start" / "original"
    ternary_dir = tmp_path / "cold-start" / "ternary"
    output_dir = tmp_path / "cold-start" / "output"
    suffix = "cold-start-output-priorityx"
    assert len(suffix) == 27
    original_name = f"①{suffix}.png"
    ternary_name = f"001{suffix}.jpg"
    output_name = f"001{suffix}.png"
    output_labels = np.full((3, 4), 2, dtype=np.uint8)
    _save_image(
        original_dir / original_name,
        np.full((3, 4, 3), 80, dtype=np.uint8),
        image_format="PNG",
    )
    _save_image(
        ternary_dir / ternary_name,
        np.full((3, 4, 3), 127, dtype=np.uint8),
        image_format="JPEG",
    )
    _save_label_png(output_dir / output_name, output_labels, rgb=True)
    settings = QSettings(str(tmp_path / "cold-start.ini"), QSettings.Format.IniFormat)
    settings.setValue("folders/original", str(original_dir))
    settings.setValue("folders/ternary", str(ternary_dir))
    settings.setValue("folders/output", str(output_dir))
    settings.setValue("pairing/mode", PairingMode.STRICT_KEY.value)

    monkeypatch.setattr(
        main_window_module,
        "confirm_ternary_jpeg_import",
        lambda *_args: pytest.fail("正常な既存出力の再開時はJPEG確認を出してはならない"),
    )
    window = MainWindow(settings=settings)
    window._request_components = lambda: None
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    try:
        assert window.current_index == 0
        assert window.session.edit_source is EditSource.OUTPUT
        assert window.session.has_saved_current
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, output_labels)
    finally:
        window._allow_close_once = True
        window.close()


def test_existing_output_bypasses_jpeg_confirmation_and_quantization(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_dir = tmp_path / "original"
    ternary_dir = tmp_path / "ternary"
    output_dir = tmp_path / "output"
    input_labels = np.zeros((3, 4), dtype=np.uint8)
    output_labels = np.full((3, 4), 2, dtype=np.uint8)
    for name, value in (("a.png", 70), ("b.png", 90)):
        _save_image(
            original_dir / name,
            np.full((3, 4, 3), value, dtype=np.uint8),
            image_format="PNG",
        )
    _save_label_png(ternary_dir / "a.png", input_labels)
    jpeg_path = ternary_dir / "b.jpg"
    _save_image(
        jpeg_path,
        np.full((3, 4, 3), 127, dtype=np.uint8),
        image_format="JPEG",
    )
    _save_label_png(output_dir / "b.png", output_labels, rgb=True)
    jpeg_hash = _sha256(jpeg_path)

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
        confirmation_calls: list[Path] = []
        monkeypatch.setattr(
            main_window_module,
            "confirm_ternary_jpeg_import",
            lambda _parent, path: confirmation_calls.append(path) or False,
        )
        monkeypatch.setattr(
            session_module,
            "load_ternary_image",
            lambda *_args, **_kwargs: pytest.fail("既存出力の読込時は三値化しない"),
        )

        window.request_open_index(1)

        assert confirmation_calls == []
        assert window.current_index == 1
        assert window.session.edit_source is EditSource.OUTPUT
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, output_labels)
        assert not window.session.import_report.quantized
        assert not window.session.import_requires_save
        assert not window.session.is_dirty
        assert _sha256(jpeg_path) == jpeg_hash
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
        assert shown and "ファイル名の先頭が規則外" in shown[0]
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


@pytest.mark.parametrize("unused_input_change", ["replace", "delete"])
def test_output_resume_ignores_invalid_input_for_open_and_later_save(
    tmp_path: Path,
    unused_input_change: str,
) -> None:
    pair = _make_png_pair(tmp_path / "resume", original_size=(4, 3))
    invalid_input = np.full((3, 4, 3), 17, dtype=np.uint8)
    _save_image(pair.ternary_path, invalid_input, image_format="PNG")
    output_labels = np.array(
        [
            [0, 1, 2, 0],
            [1, 2, 0, 1],
            [2, 0, 1, 2],
        ],
        dtype=np.uint8,
    )
    _save_label_png(pair.output_path, output_labels, rgb=True)
    current = ImageSession()

    current.open_pair(pair, EditSource.OUTPUT, expected_size=(4, 3))

    assert current.edit_source is EditSource.OUTPUT
    assert current.has_saved_current
    assert not current.is_dirty
    assert current.ternary_fingerprint is None
    assert current.labels is not None
    assert np.array_equal(current.labels, output_labels)

    if unused_input_change == "replace":
        replacement = np.full((2, 6, 3), 23, dtype=np.uint8)
        _save_image(pair.ternary_path, replacement, image_format="PNG")
        expected_input_hash = _sha256(pair.ternary_path)
    else:
        pair.ternary_path.unlink()
        expected_input_hash = None

    edited = output_labels.copy()
    edited[0, 0] = 2
    current.apply_labels(edited, "再開後編集")
    current.save(expected_size=(4, 3))

    saved = image_io.validate_output_png(pair.output_path, expected_size=(4, 3))
    assert np.array_equal(saved.labels, edited)
    assert current.has_saved_current
    if expected_input_hash is None:
        assert not pair.ternary_path.exists()
    else:
        assert _sha256(pair.ternary_path) == expected_input_hash


def test_output_resume_compares_output_with_display_oriented_original_only(
    tmp_path: Path,
) -> None:
    root = tmp_path / "display-size"
    original_path = root / "original.jpg"
    ternary_path = root / "unused-input.png"
    output_path = root / "output" / "unused-input.png"
    exif = Image.Exif()
    exif[274] = 6
    _save_image(
        original_path,
        np.full((3, 4, 3), 80, dtype=np.uint8),
        image_format="JPEG",
        exif=exif,
    )
    _save_label_png(ternary_path, np.zeros((2, 2), dtype=np.uint8))
    output_labels = np.array(
        [
            [0, 1, 2],
            [1, 2, 0],
            [2, 0, 1],
            [0, 1, 2],
        ],
        dtype=np.uint8,
    )
    _save_label_png(output_path, output_labels, rgb=True)
    pair = ImagePair(
        key=None,
        original_path=original_path,
        ternary_path=ternary_path,
        output_path=output_path,
        ternary_stem=ternary_path.stem,
        pairing_mode=PairingMode.NATURAL_ORDER,
    )
    current = ImageSession()

    current.open_pair(pair, EditSource.OUTPUT)

    assert current.original_rgb is not None
    assert current.original_rgb.shape == (4, 3, 3)
    assert current.labels is not None
    assert current.labels.shape == (4, 3)
    assert np.array_equal(current.labels, output_labels)
    assert current.ternary_fingerprint is None


def test_output_resume_requires_exact_width_and_height(tmp_path: Path) -> None:
    pair = _make_png_pair(tmp_path / "transposed", original_size=(4, 3))
    _save_label_png(pair.output_path, np.zeros((4, 3), dtype=np.uint8), rgb=True)
    current = ImageSession()

    with pytest.raises((ImageValidationError, PairDimensionError), match="寸法"):
        current.open_pair(pair, EditSource.OUTPUT)

    assert not current.is_loaded


def test_input_open_keeps_strict_validation_when_valid_output_exists(
    tmp_path: Path,
) -> None:
    pair = _make_png_pair(tmp_path / "strict-input", original_size=(4, 3))
    _save_image(
        pair.ternary_path,
        np.full((3, 4, 3), 17, dtype=np.uint8),
        image_format="PNG",
    )
    _save_label_png(pair.output_path, np.zeros((3, 4), dtype=np.uint8), rgb=True)
    current = ImageSession()

    with pytest.raises(ImageValidationError, match="三値"):
        current.open_pair(pair, EditSource.INPUT, expected_size=(4, 3))

    assert not current.is_loaded


@pytest.mark.parametrize("loader_name", ["input", "output"])
@pytest.mark.parametrize("orientation", range(2, 9))
def test_label_png_with_orientation_is_rejected_without_auto_rotation(
    tmp_path: Path,
    loader_name: str,
    orientation: int,
) -> None:
    path = tmp_path / f"oriented-{loader_name}-{orientation}.png"
    labels = np.array(
        [
            [0, 1, 2, 0],
            [1, 2, 0, 1],
            [2, 0, 1, 2],
        ],
        dtype=np.uint8,
    )
    exif = Image.Exif()
    exif[274] = orientation
    _save_image(
        path,
        np.asarray(SAVE_RGB, dtype=np.uint8)[labels],
        image_format="PNG",
        exif=exif,
    )
    before_hash = _sha256(path)

    with pytest.raises(ImageValidationError, match="Orientation"):
        if loader_name == "input":
            image_io.load_ternary_image(path, expected_size=(4, 3))
        else:
            image_io.load_output_image(path, expected_size=(4, 3))

    assert _sha256(path) == before_hash


@pytest.mark.parametrize("input_defect", ["invalid-colors", "different-size"])
def test_gui_auto_prefers_valid_output_when_unused_input_is_invalid(
    input_defect: str,
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_labels = np.array(
        [
            [0, 1, 2, 0],
            [1, 2, 0, 1],
            [2, 0, 1, 2],
        ],
        dtype=np.uint8,
    )
    folders = _make_natural_folders(
        tmp_path / input_defect,
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(2)],
        outputs={1: output_labels},
    )
    second_input = folders[1] / "b.png"
    if input_defect == "invalid-colors":
        _save_image(
            second_input,
            np.full((3, 4, 3), 17, dtype=np.uint8),
            image_format="PNG",
        )
    else:
        _save_label_png(second_input, np.zeros((2, 2), dtype=np.uint8))
    input_hash = _sha256(second_input)
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert window.open_pair(0)
        monkeypatch.setattr(
            session_module,
            "load_ternary_image",
            lambda *_args, **_kwargs: pytest.fail(
                "既存正常出力の自動再開では入力三値画像を復号しない"
            ),
        )
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda *_args: pytest.fail("正常出力の自動再開でerror modalを出さない"),
        )

        window.request_open_index(1)

        assert window.current_index == 1
        assert window.session.edit_source is EditSource.OUTPUT
        assert window.session.has_saved_current
        assert not window.session.is_dirty
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, output_labels)
        assert _sha256(second_input) == input_hash
    finally:
        window._allow_close_once = True
        window.close()


def test_folder_preflight_skips_invalid_pair_without_modal_error(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / "preflight-skip",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(2)],
    )
    first_input = sorted(folders[1].glob("*.png"))[0]
    _save_image(
        first_input,
        np.full((3, 4, 3), 17, dtype=np.uint8),
        image_format="PNG",
    )
    result = pairing.plan_pairing(*folders, mode=PairingMode.NATURAL_ORDER)
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module,
        "show_error",
        lambda _parent, title, message: shown.append((title, message)),
    )
    window = _make_contract_window(qtbot, tmp_path)
    try:
        prepared = window._preflight_first_usable_pair(result)

        assert prepared is not None
        assert prepared.index == 1
        assert 0 in prepared.pair_errors
        assert shown == []
    finally:
        window._allow_close_once = True
        window.close()


def test_preflight_reports_every_failure_in_status_when_no_pair_is_usable(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / "preflight-all-invalid",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(2)],
    )
    for input_path in folders[1].glob("*.png"):
        _save_image(
            input_path,
            np.full((3, 4, 3), 17, dtype=np.uint8),
            image_format="PNG",
        )
    result = pairing.plan_pairing(*folders, mode=PairingMode.NATURAL_ORDER)
    shown: list[tuple[str, str]] = []
    messages: list[str] = []
    monkeypatch.setattr(
        main_window_module,
        "show_error",
        lambda _parent, title, message: shown.append((title, message)),
    )
    window = _make_contract_window(qtbot, tmp_path)
    monkeypatch.setattr(window, "_message", messages.append)
    try:
        prepared = window._preflight_first_usable_pair(result)

        assert prepared is None
        assert shown == []
        assert len(messages) == 1
        assert "読込可能な画像対なし" in messages[0]
        assert "a（画像対）" in messages[0]
        assert "b（画像対）" in messages[0]
        assert messages[0].count("異常画素数=12") == 2
    finally:
        window._allow_close_once = True
        window.close()


def test_directional_navigation_skips_invalid_pair_without_modal_error(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / "directional-skip",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(3)],
    )
    second_input = sorted(folders[1].glob("*.png"))[1]
    _save_image(
        second_input,
        np.full((3, 4, 3), 17, dtype=np.uint8),
        image_format="PNG",
    )
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert window.open_pair(0)
        shown: list[tuple[str, str]] = []
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda _parent, title, message: shown.append((title, message)),
        )

        window._go_next()

        assert window.current_index == 2
        assert 1 in window._pair_errors
        assert shown == []
    finally:
        window._allow_close_once = True
        window.close()


@pytest.mark.parametrize("failure_kind", ["output", "unknown"])
def test_preflight_skips_output_and_unknown_failures_without_modal(
    failure_kind: str,
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / f"preflight-{failure_kind}",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(2)],
        outputs={0: np.zeros((3, 4), dtype=np.uint8)},
    )
    first_output = folders[2] / "a.png"
    if failure_kind == "output":
        _save_image(
            first_output,
            np.full((3, 4, 3), 17, dtype=np.uint8),
            image_format="PNG",
        )
    result = pairing.plan_pairing(*folders, mode=PairingMode.NATURAL_ORDER)
    original_open = ImageSession.open_pair
    if failure_kind == "unknown":

        def fail_first(
            session: ImageSession,
            pair: ImagePair,
            source: EditSource,
            *args,
            **kwargs,
        ) -> None:
            if pair == result.pairs[0]:
                raise RuntimeError("故障注入")
            original_open(session, pair, source, *args, **kwargs)

        monkeypatch.setattr(ImageSession, "open_pair", fail_first)
    window = _make_contract_window(qtbot, tmp_path)
    monkeypatch.setattr(
        window,
        "_ask_input_fallback",
        lambda *_args: pytest.fail("preflightでfallback modalを出してはならない"),
    )
    monkeypatch.setattr(
        main_window_module,
        "show_error",
        lambda *_args: pytest.fail("preflightでerror modalを出してはならない"),
    )
    try:
        prepared = window._preflight_first_usable_pair(result)

        assert prepared is not None
        assert prepared.index == 1
        assert 0 not in prepared.pair_errors
        if failure_kind == "output":
            assert 0 in prepared.output_errors
            assert 0 not in prepared.transient_errors
        else:
            assert 0 not in prepared.output_errors
            assert 0 in prepared.transient_errors
    finally:
        window._allow_close_once = True
        window.close()


@pytest.mark.parametrize("failure_kind", ["output", "unknown"])
def test_directional_navigation_skips_output_and_unknown_failures_without_modal(
    failure_kind: str,
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / f"directional-{failure_kind}",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(3)],
        outputs={1: np.zeros((3, 4), dtype=np.uint8)},
    )
    second_output = folders[2] / "b.png"
    if failure_kind == "output":
        _save_image(
            second_output,
            np.full((3, 4, 3), 17, dtype=np.uint8),
            image_format="PNG",
        )
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert window.open_pair(0)
        if failure_kind == "unknown":
            original_open = window.session.open_pair

            def fail_middle(
                pair: ImagePair,
                source: EditSource,
                *args,
                **kwargs,
            ) -> None:
                if pair == window.pairs[1]:
                    raise RuntimeError("故障注入")
                original_open(pair, source, *args, **kwargs)

            monkeypatch.setattr(window.session, "open_pair", fail_middle)
        monkeypatch.setattr(
            window,
            "_ask_input_fallback",
            lambda *_args: pytest.fail("前後移動でfallback modalを出してはならない"),
        )
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda *_args: pytest.fail("前後移動でerror modalを出してはならない"),
        )

        window._go_next()

        assert window.current_index == 2
        assert 1 not in window._pair_errors
        if failure_kind == "output":
            assert 1 in window._output_errors
            assert 1 not in window._transient_open_errors
        else:
            assert 1 not in window._output_errors
            assert 1 in window._transient_open_errors
    finally:
        window._allow_close_once = True
        window.close()


def test_direct_invalid_pair_reports_target_once(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / "direct-failure",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(2)],
    )
    second_input = sorted(folders[1].glob("*.png"))[1]
    _save_image(
        second_input,
        np.full((3, 4, 3), 17, dtype=np.uint8),
        image_format="PNG",
    )
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        assert window.open_pair(0)
        shown: list[tuple[str, str]] = []
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda _parent, title, message: shown.append((title, message)),
        )

        window.request_open_index(1)

        assert window.current_index == 0
        assert 1 in window._pair_errors
        assert len(shown) == 1
        assert str(window.pairs[1].ternary_path) in shown[0][1]
    finally:
        window._allow_close_once = True
        window.close()


def test_accepted_output_fallback_is_not_reconfirmed_for_same_snapshot(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / "fallback-cache",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(2)],
        outputs={0: np.zeros((3, 4), dtype=np.uint8)},
    )
    invalid_output = folders[2] / "a.png"
    _save_image(
        invalid_output,
        np.full((3, 4, 3), 17, dtype=np.uint8),
        image_format="PNG",
    )
    output_hash = _sha256(invalid_output)
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        fallback_calls: list[Path] = []
        monkeypatch.setattr(
            window,
            "_ask_input_fallback",
            lambda error: fallback_calls.append(error.path) or True,
        )
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda *_args: pytest.fail("受理済みfallbackで追加modalを出してはならない"),
        )

        assert window.open_pair(0)
        assert window.session.edit_source is EditSource.INPUT
        window.request_open_index(1)
        assert window.current_index == 1
        window.request_open_index(0)

        assert window.current_index == 0
        assert window.session.edit_source is EditSource.INPUT
        assert fallback_calls == [invalid_output]
        assert _sha256(invalid_output) == output_hash
    finally:
        window._allow_close_once = True
        window.close()


def test_accepted_output_fallback_is_invalidated_after_output_replacement(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / "fallback-snapshot-change",
        [np.zeros((3, 4), dtype=np.uint8) for _ in range(2)],
        outputs={0: np.zeros((3, 4), dtype=np.uint8)},
    )
    replaced_output = folders[2] / "a.png"
    _save_image(
        replaced_output,
        np.full((3, 4, 3), 17, dtype=np.uint8),
        image_format="PNG",
    )
    replacement_labels = np.full((3, 4), 2, dtype=np.uint8)
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        fallback_calls: list[Path] = []
        monkeypatch.setattr(
            window,
            "_ask_input_fallback",
            lambda error: fallback_calls.append(error.path) or True,
        )
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda *_args: pytest.fail("置換後の正常出力を開く際にerror modalは不要"),
        )

        assert window.open_pair(0, EditSource.OUTPUT)
        assert window.session.edit_source is EditSource.INPUT
        window.request_open_index(1)
        assert window.current_index == 1
        _save_label_png(replaced_output, replacement_labels, rgb=True)

        window.request_open_index(0)

        assert window.current_index == 0
        assert window.session.edit_source is EditSource.OUTPUT
        assert window.session.has_saved_current
        assert window.session.labels is not None
        assert np.array_equal(window.session.labels, replacement_labels)
        assert fallback_calls == [replaced_output]
        assert 0 not in window._output_errors
    finally:
        window._allow_close_once = True
        window.close()


@pytest.mark.parametrize("failure_kind", ["external-output", "unknown"])
def test_transient_open_failure_is_reported_but_not_cached_as_pair_error(
    failure_kind: str,
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / failure_kind,
        [np.zeros((3, 4), dtype=np.uint8)],
        outputs={0: np.zeros((3, 4), dtype=np.uint8)},
    )
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        pair = window.pairs[0]
        if failure_kind == "external-output":
            failure: Exception = ExternalOutputModificationError(
                path=pair.output_path,
                expected_sha256="old",
                actual_sha256="new",
            )
        else:
            failure = RuntimeError("故障注入")

        def fail_open(*_args, **_kwargs) -> None:
            raise failure

        monkeypatch.setattr(window.session, "open_pair", fail_open)
        fallback_shown: list[str] = []
        error_shown: list[tuple[str, str]] = []
        if failure_kind == "external-output":
            monkeypatch.setattr(
                window,
                "_ask_input_fallback",
                lambda error: fallback_shown.append(str(error)) or False,
            )
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda _parent, title, message: error_shown.append((title, message)),
        )

        assert not window.open_pair(0)

        assert 0 not in window._pair_errors
        assert window.image_list.count() == 1
        assert window.error_list.count() == 0
        if failure_kind == "external-output":
            assert len(fallback_shown) == 1
            assert error_shown == []
            message = fallback_shown[0]
        else:
            assert fallback_shown == []
            assert len(error_shown) == 1
            message = error_shown[0][1]
        assert any(
            str(path) in message
            for path in (pair.original_path, pair.ternary_path, pair.output_path)
        )
    finally:
        window._allow_close_once = True
        window.close()


def test_cancelled_output_fallback_has_exactly_one_error_notification(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folders = _make_natural_folders(
        tmp_path / "fallback-cancel",
        [np.zeros((3, 4), dtype=np.uint8)],
        outputs={0: np.zeros((3, 4), dtype=np.uint8)},
    )
    invalid_output = folders[2] / "a.png"
    _save_image(
        invalid_output,
        np.full((3, 4, 3), 17, dtype=np.uint8),
        image_format="PNG",
    )
    window = _make_contract_window(qtbot, tmp_path)
    try:
        window.configure_folders(
            *folders,
            pairing_mode=PairingMode.NATURAL_ORDER,
            natural_order_confirmed=True,
        )
        notifications: list[tuple[str, str]] = []
        monkeypatch.setattr(
            window,
            "_ask_input_fallback",
            lambda error: notifications.append(("fallback", str(error))) or False,
        )
        monkeypatch.setattr(
            main_window_module,
            "show_error",
            lambda _parent, title, message: notifications.append((title, message)),
        )

        assert not window.open_pair(0)

        assert 0 not in window._pair_errors
        assert len(notifications) == 1
        assert str(invalid_output) in notifications[0][1]
    finally:
        window._allow_close_once = True
        window.close()
