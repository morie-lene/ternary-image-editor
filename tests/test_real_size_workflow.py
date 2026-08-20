"""代表寸法で筆・表示・統一履歴をつなぐ用途寄り回帰試験。

2048x1536 は代表的な作業寸法であり、入力上限や絶対性能の契約ではない。
時間閾値ではなく、局所矩形、疎差分、状態の可逆性を検査する。
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

from ternary_image_editor.canvas import ImageCanvas
from ternary_image_editor.constants import SAVE_RGB, Label
from ternary_image_editor.history import HistoryManager, make_pixel_delta
from ternary_image_editor.operations import (
    brush_segment_footprint,
    paint_brush,
    paint_brush_footprint,
    paint_brush_increment,
)

IMAGE_SHAPE = (1536, 2048)
BRUSH_DIAMETER = 13


def _long_path() -> tuple[tuple[float, float], ...]:
    phase = np.linspace(0.0, 4.0 * np.pi, 81)
    columns = np.linspace(96.5, 1950.5, phase.size)
    rows = 680.5 + 180.0 * np.sin(phase)
    return tuple((float(x), float(y)) for x, y in zip(columns, rows, strict=True))


def _rgb888_view(image: QImage) -> np.ndarray:
    assert image.format() == QImage.Format.Format_RGB888
    rows = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(
        image.height(), image.bytesPerLine()
    )
    return rows[:, : image.width() * 3].reshape(image.height(), image.width(), 3)


def _memo_rgba_copy(canvas: ImageCanvas) -> np.ndarray:
    if canvas._memo_image is None:
        assert not canvas.has_memo
        return np.zeros((*IMAGE_SHAPE, 4), dtype=np.uint8)
    return canvas._memo_rgba_view().copy()


def test_real_size_long_stroke_keeps_updates_local_and_display_exact(qtbot) -> None:
    original = np.zeros((*IMAGE_SHAPE, 3), dtype=np.uint8)
    labels = np.zeros(IMAGE_SHAPE, dtype=np.uint8)
    baseline = labels.copy()
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)
    canvas.set_images(original, labels)
    canvas.set_original_opacity(0.0)
    points = _long_path()
    dirty_boxes: list[tuple[int, int, int, int]] = []

    increments = [(points[0], None), *zip(points[:-1], points[1:], strict=True)]
    for start, end in increments:
        dirty = paint_brush_increment(
            labels,
            start,
            end,
            Label.PRESENT,
            BRUSH_DIAMETER,
            "circle",
        )
        if dirty is None:
            continue
        dirty_boxes.append(dirty)
        canvas.refresh_label_region(labels, dirty)

    expected = paint_brush(
        baseline,
        points,
        Label.PRESENT,
        BRUSH_DIAMETER,
        "circle",
    )
    np.testing.assert_array_equal(labels, expected)

    dirty_areas = [(right - left) * (bottom - top) for left, top, right, bottom in dirty_boxes]
    assert len(dirty_boxes) == len(increments)
    assert min(left for left, _top, _right, _bottom in dirty_boxes) < IMAGE_SHAPE[1] // 10
    assert max(right for _left, _top, right, _bottom in dirty_boxes) > IMAGE_SHAPE[1] * 9 // 10
    assert max(dirty_areas) < labels.size // 100
    assert sum(dirty_areas) < labels.size // 10
    assert not labels[-100:].any()

    display = canvas._native_display_image()
    assert display is not None
    assert (display.height(), display.width()) == IMAGE_SHAPE
    expected_rgb = np.asarray(SAVE_RGB, dtype=np.uint8)[expected]
    np.testing.assert_array_equal(_rgb888_view(display), expected_rgb)


def test_real_size_overlapping_memo_erase_and_history_remain_reversible(qtbot) -> None:
    original = np.zeros((*IMAGE_SHAPE, 3), dtype=np.uint8)
    labels = np.zeros(IMAGE_SHAPE, dtype=np.uint8)
    baseline = labels.copy()
    canvas = ImageCanvas()
    qtbot.addWidget(canvas)
    canvas.set_images(original, labels)
    canvas.set_actual_size()
    canvas.set_original_opacity(0.0)
    outward = _long_path()

    canvas._begin_memo_stroke(outward[0])
    for start, end in zip(outward[:-1], outward[1:], strict=True):
        canvas._draw_memo_segment(start, end)
    created_memo = canvas.finish_memo_stroke()
    assert created_memo is not None
    memo_before = _memo_rgba_copy(canvas)
    opaque_before = int(np.count_nonzero(memo_before[..., 3]))
    assert opaque_before == created_memo.changed_pixels

    round_trip = (*outward, *reversed(outward[:-1]))
    canvas.begin_label_memo_erase()
    changed_regions: list[tuple[int, int, int, int]] = []
    footprints = []
    for start, end in [(round_trip[0], None), *zip(round_trip[:-1], round_trip[1:], strict=True)]:
        footprint = brush_segment_footprint(
            labels.shape,
            start,
            end,
            BRUSH_DIAMETER,
            "circle",
        )
        assert footprint is not None
        footprints.append(footprint)
        dirty = paint_brush_footprint(labels, footprint, Label.BOUNDARY)
        canvas.stage_label_memo_erase(footprint)
        if dirty is not None:
            changed_regions.append(dirty)
            canvas.refresh_label_region(labels, dirty)

    erased_memo = canvas.finish_label_memo_erase("長い筆によるメモ消去")
    assert erased_memo is not None
    assert len(changed_regions) < len(footprints)
    erased_indices = np.concatenate([patch.indices for patch in erased_memo.patches])
    assert erased_indices.size == np.unique(erased_indices).size
    memo_after = _memo_rgba_copy(canvas)
    assert erased_memo.changed_pixels == opaque_before - int(
        np.count_nonzero(memo_after[..., 3])
    )

    expected = paint_brush(
        baseline,
        round_trip,
        Label.BOUNDARY,
        BRUSH_DIAMETER,
        "circle",
    )
    np.testing.assert_array_equal(labels, expected)
    label_delta = make_pixel_delta(baseline, labels, "長い筆")
    assert label_delta is not None
    assert label_delta.changed_pixels == int(np.count_nonzero(labels != baseline))
    history = HistoryManager()
    history.record(label_delta, memo_delta=erased_memo)
    entry = history.current_entry
    assert entry is not None
    assert entry.memory_bytes < labels.nbytes

    undone = history.undo(labels)
    assert undone is not None and undone.memo_delta is erased_memo
    canvas.apply_memo_delta(undone.memo_delta, forward=False)
    canvas.refresh_labels(labels)
    np.testing.assert_array_equal(labels, baseline)
    np.testing.assert_array_equal(_memo_rgba_copy(canvas), memo_before)

    redone = history.redo(labels)
    assert redone is not None and redone.memo_delta is erased_memo
    canvas.apply_memo_delta(redone.memo_delta, forward=True)
    canvas.refresh_labels(labels)
    np.testing.assert_array_equal(labels, expected)
    np.testing.assert_array_equal(_memo_rgba_copy(canvas), memo_after)

    history.discard_memo()
    assert history.cursor == 1
    assert history.operation_count == 1
    assert history.total_bytes == label_delta.memory_bytes
    assert history.current_entry is not None
    assert history.current_entry.memo_delta is None
    assert history.undo(labels) is not None
    np.testing.assert_array_equal(labels, baseline)
    assert history.redo(labels) is not None
    np.testing.assert_array_equal(labels, expected)


def test_real_size_two_hundred_sparse_edits_undo_and_redo_without_snapshots() -> None:
    labels = np.zeros(IMAGE_SHAPE, dtype=np.uint8)
    baseline = labels.copy()
    history = HistoryManager()
    editable_pixels = (IMAGE_SHAPE[0] - 100) * IMAGE_SHAPE[1]
    edit_indices = np.linspace(
        0,
        editable_pixels - 1,
        history.max_operations,
        dtype=np.uint32,
    )

    for flat_index in edit_indices:
        before = labels.copy()
        row, column = divmod(int(flat_index), IMAGE_SHAPE[1])
        labels[row, column] = Label.PRESENT
        delta = make_pixel_delta(before, labels, f"疎編集{history.operation_count + 1}")
        assert delta is not None and delta.changed_pixels == 1
        report = history.record(delta)
        assert not report.trimmed

    final = labels.copy()
    snapshot_series_bytes = labels.nbytes * history.operation_count
    assert history.operation_count == history.max_operations == 200
    assert history.total_bytes < snapshot_series_bytes // 1000

    for _ in range(history.operation_count):
        assert history.undo(labels) is not None
    assert not history.can_undo
    assert history.can_redo
    np.testing.assert_array_equal(labels, baseline)

    for _ in range(history.operation_count):
        assert history.redo(labels) is not None
    assert history.can_undo
    assert not history.can_redo
    np.testing.assert_array_equal(labels, final)
