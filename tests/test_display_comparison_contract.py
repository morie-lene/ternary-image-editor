"""表示比較（暗）追補の公開受入試験。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from ternary_image_editor.canvas import ImageCanvas
from ternary_image_editor.constants import SAVE_RGB
from ternary_image_editor.image_io import save_labels_atomic
from ternary_image_editor.main_window import MainWindow
from ternary_image_editor.operations import alpha_composite, gimp_lighten_composite
from ternary_image_editor.settings_model import AppSettings, SettingsRepository


def _rgb(image: QImage) -> np.ndarray:
    return np.asarray(
        [
            [image.pixelColor(x, y).getRgb()[:3] for x in range(image.width())]
            for y in range(image.height())
        ],
        dtype=np.int16,
    )


def _rgba(image: QImage) -> np.ndarray:
    return np.asarray(
        [
            [image.pixelColor(x, y).getRgb() for x in range(image.width())]
            for y in range(image.height())
        ],
        dtype=np.int16,
    )


def _darken_expected(
    ternary_rgb: np.ndarray,
    original_rgb: np.ndarray,
    opacity: float,
) -> np.ndarray:
    base = ternary_rgb.astype(np.float64)
    darker = np.minimum(base, original_rgb.astype(np.float64))
    return np.clip(np.rint((1.0 - opacity) * base + opacity * darker), 0, 255).astype(
        np.int16
    )


def test_disp_cmp_003_005_default_off_and_darken_cover_saved_and_pseudo_colors(qtbot) -> None:
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)
    labels = np.asarray([[0, 1, 2]], dtype=np.uint8)
    original = np.asarray(
        [[[32, 240, 20], [220, 40, 200], [80, 100, 255]]],
        dtype=np.uint8,
    )
    saved_rgb = np.asarray(SAVE_RGB, dtype=np.uint8)[labels]
    labels_before = labels.copy()
    canvas.set_images(original, labels)
    canvas.set_original_opacity(0.25)

    assert not canvas.darken_comparison_enabled
    legacy = canvas._native_display_image()
    assert legacy is not None
    assert np.max(np.abs(_rgb(legacy) - gimp_lighten_composite(saved_rgb, original, 0.25))) <= 1

    canvas.set_darken_comparison_enabled(True)
    dark_saved = canvas._native_display_image()
    assert dark_saved is not None
    assert np.max(np.abs(_rgb(dark_saved) - _darken_expected(saved_rgb, original, 0.25))) <= 2

    pseudo_palette = ((240, 16, 64), (12, 230, 90), (120, 80, 245))
    pseudo_rgb = np.asarray(pseudo_palette, dtype=np.uint8)[labels]
    canvas.set_pseudo_palette(pseudo_palette)
    canvas.set_pseudo_enabled(True)
    dark_pseudo = canvas._native_display_image()
    assert dark_pseudo is not None
    assert np.max(np.abs(_rgb(dark_pseudo) - _darken_expected(pseudo_rgb, original, 0.25))) <= 2

    canvas.set_darken_comparison_enabled(False)
    normal_pseudo = canvas._native_display_image()
    assert normal_pseudo is not None
    assert np.max(np.abs(_rgb(normal_pseudo) - alpha_composite(pseudo_rgb, original, 0.25))) <= 2
    np.testing.assert_array_equal(labels, labels_before)
    np.testing.assert_array_equal(canvas.labels, labels_before)


def test_disp_cmp_004_006_opacity_endpoints_and_single_layer_views_are_stable(qtbot) -> None:
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)
    labels = np.asarray([[0, 1, 2]], dtype=np.uint8)
    original = np.asarray(
        [[[10, 220, 64], [255, 8, 160], [70, 200, 1]]],
        dtype=np.uint8,
    )
    ternary = np.asarray(SAVE_RGB, dtype=np.uint8)[labels]
    canvas.set_images(original, labels)
    canvas.set_darken_comparison_enabled(True)

    canvas.set_original_opacity(0.0)
    zero = canvas._native_display_image()
    assert zero is not None
    np.testing.assert_array_equal(_rgb(zero), ternary)

    canvas.set_original_opacity(1.0)
    full = canvas._native_display_image()
    assert full is not None
    np.testing.assert_array_equal(_rgb(full), np.minimum(ternary, original))

    canvas.set_original_opacity(0.5)
    canvas.ternary_visible = False
    original_only_on = canvas._native_display_image()
    assert original_only_on is not None
    original_only_on_pixels = _rgba(original_only_on)
    canvas.set_darken_comparison_enabled(False)
    original_only_off = canvas._native_display_image()
    assert original_only_off is not None
    np.testing.assert_array_equal(_rgba(original_only_off), original_only_on_pixels)

    canvas.ternary_visible = True
    canvas.original_visible = False
    ternary_only_off = canvas._native_display_image()
    assert ternary_only_off is not None
    ternary_only_off_pixels = _rgba(ternary_only_off)
    canvas.set_darken_comparison_enabled(True)
    ternary_only_on = canvas._native_display_image()
    assert ternary_only_on is not None
    np.testing.assert_array_equal(_rgba(ternary_only_on), ternary_only_off_pixels)

    canvas.ternary_visible = False
    assert canvas._native_display_image() is None


def test_disp_cmp_002_007_action_sync_and_restart_do_not_touch_document_state(
    qtbot,
    tmp_path: Path,
) -> None:
    raw = QSettings(str(tmp_path / "comparison.ini"), QSettings.Format.IniFormat)
    raw.clear()
    first = MainWindow(settings=raw)
    qtbot.addWidget(first)
    first._request_components = lambda: None
    first.show()
    QApplication.processEvents()

    action = first._operation_actions["view.toggle-darken-comparison"]
    state_before = (
        first.session.labels,
        first.session.baseline_labels,
        first.session.is_dirty,
        first.session.history.operation_count,
        first.session.history.cursor,
        first.session.revision,
    )
    assert action.isCheckable()
    assert not action.isChecked()
    assert first.action_registry.operation_for_shortcut("D") is None

    action.trigger()

    assert first.controls.darken_comparison.isChecked()
    assert first.canvas.darken_comparison_enabled
    assert action.isChecked()
    assert raw.value("view/darkenComparison", type=bool) is True
    assert (
        first.session.labels,
        first.session.baseline_labels,
        first.session.is_dirty,
        first.session.history.operation_count,
        first.session.history.cursor,
        first.session.revision,
    ) == state_before

    raw.sync()
    second = MainWindow(settings=raw)
    qtbot.addWidget(second)
    second._request_components = lambda: None
    second.show()
    QApplication.processEvents()
    assert second.controls.darken_comparison.isChecked()
    assert second.canvas.darken_comparison_enabled
    assert second._operation_actions["view.toggle-darken-comparison"].isChecked()


def test_disp_cmp_008_settings_roundtrip_and_corrupt_value_fallback(tmp_path: Path) -> None:
    raw = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    raw.clear()
    repository = SettingsRepository(raw)
    assert not repository.load().darken_comparison_enabled

    enabled = AppSettings(darken_comparison_enabled=True)
    repository.save(enabled)
    assert SettingsRepository(raw).load().darken_comparison_enabled

    raw.setValue("view/darkenComparison", "invalid")
    raw.sync()
    corrupt_repository = SettingsRepository(raw)
    recovered = corrupt_repository.load()
    assert not recovered.darken_comparison_enabled
    assert "invalid setting view/darkenComparison; default used" in corrupt_repository.warnings


def test_disp_cmp_007_saved_png_is_identical_before_and_after_display_toggle(
    qtbot,
    tmp_path: Path,
) -> None:
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)
    labels = np.asarray([[0, 1, 2], [2, 1, 0]], dtype=np.uint8)
    original = np.asarray(
        [
            [[240, 10, 30], [20, 220, 40], [70, 90, 255]],
            [[8, 200, 180], [250, 30, 90], [60, 170, 12]],
        ],
        dtype=np.uint8,
    )
    canvas.set_images(original, labels)
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    save_labels_atomic(labels, before, expected_fingerprint=None)

    canvas.set_original_opacity(0.75)
    canvas.set_pseudo_enabled(True)
    canvas.set_darken_comparison_enabled(True)
    assert canvas.labels is not None
    save_labels_atomic(canvas.labels, after, expected_fingerprint=None)

    assert before.read_bytes() == after.read_bytes()
    np.testing.assert_array_equal(canvas.labels, labels)
