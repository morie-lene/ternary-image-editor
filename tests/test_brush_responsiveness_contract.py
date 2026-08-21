"""筆追従局所更新の公開受入・性能回帰試験。"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QSettings, Qt
from PySide6.QtGui import QImage, QPaintEvent, QRegion
from PySide6.QtWidgets import QApplication

import ternary_image_editor.canvas as canvas_module
import ternary_image_editor.operations as operations_module
from ternary_image_editor.canvas import EditTool, ImageCanvas
from ternary_image_editor.constants import Label
from ternary_image_editor.main_window import MainWindow
from ternary_image_editor.operations import paint_brush, paint_brush_increment


def _rgb(image: QImage) -> np.ndarray:
    return np.asarray(
        [
            [image.pixelColor(x, y).getRgb()[:3] for x in range(image.width())]
            for y in range(image.height())
        ],
        dtype=np.int16,
    )


@pytest.mark.parametrize("brush_shape", ["circle", "square"])
def test_brush_increment_dirty_regions_preserve_reference_stroke(
    brush_shape: str,
) -> None:
    source = np.zeros((260, 180), dtype=np.uint8)
    points = [(12.5, 12.5), (190.0, 50.5), (-8.0, 90.5), (160.5, 145.5)]
    expected = paint_brush(source, points, Label.BOUNDARY, 4, brush_shape)
    actual = source.copy()

    increments = [(points[0], None), *zip(points[:-1], points[1:], strict=True)]
    for start, end in increments:
        before = actual.copy()
        dirty = paint_brush_increment(
            actual,
            start,
            end,
            Label.BOUNDARY,
            4,
            brush_shape,
        )
        changed_y, changed_x = np.nonzero(actual != before)
        if changed_x.size == 0:
            assert dirty is None
            continue
        assert dirty is not None
        left, top, right, bottom = dirty
        assert 0 <= left <= int(changed_x.min())
        assert int(changed_x.max()) < right <= actual.shape[1]
        assert 0 <= top <= int(changed_y.min())
        assert int(changed_y.max()) < bottom <= actual.shape[0]

    np.testing.assert_array_equal(actual, expected)


def test_brush_increment_skips_same_label_and_protected_rows() -> None:
    labels = np.full((240, 180), Label.PRESENT, dtype=np.uint8)

    assert (
        paint_brush_increment(
            labels,
            (40.5, 40.5),
            (48.5, 40.5),
            Label.PRESENT,
            9,
            "circle",
        )
        is None
    )
    before = labels.copy()
    assert (
        paint_brush_increment(
            labels,
            (40.5, 180.5),
            (80.5, 180.5),
            Label.BOUNDARY,
            9,
            "square",
        )
        is None
    )
    np.testing.assert_array_equal(labels, before)


def test_brush_increment_allocates_the_swept_region_instead_of_the_full_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = np.zeros((1536, 2048), dtype=np.uint8)
    allocated_shapes: list[tuple[int, ...]] = []
    original_zeros = operations_module.np.zeros

    def recording_zeros(
        shape: tuple[int, ...],
        *args: object,
        **kwargs: object,
    ) -> np.ndarray:
        allocated_shapes.append(shape)
        return original_zeros(shape, *args, **kwargs)

    monkeypatch.setattr(operations_module.np, "zeros", recording_zeros)

    dirty = paint_brush_increment(
        labels,
        (1000.5, 700.5),
        (1008.5, 704.5),
        Label.PRESENT,
        5,
        "circle",
    )

    assert dirty == (998, 698, 1011, 707)
    assert allocated_shapes == [(9, 13)]


@pytest.mark.parametrize(
    ("pseudo", "darken", "opacity"),
    [
        (False, False, 0.0),
        (False, False, 0.55),
        (False, True, 0.55),
        (True, False, 0.55),
        (True, True, 0.55),
    ],
)
def test_regional_label_refresh_matches_full_rebuild_in_every_comparison_mode(
    qtbot,
    pseudo: bool,
    darken: bool,
    opacity: float,
) -> None:
    generator = np.random.default_rng(20260820)
    original = generator.integers(0, 256, size=(12, 14, 3), dtype=np.uint8)
    labels = generator.integers(0, 3, size=(12, 14), dtype=np.uint8)
    regional = ImageCanvas()
    full = ImageCanvas()
    qtbot.addWidget(regional)
    qtbot.addWidget(full)
    pseudo_palette = ((230, 40, 90), (20, 210, 100), (80, 120, 245))

    for canvas in (regional, full):
        canvas.set_pseudo_palette(pseudo_palette)
        canvas.set_pseudo_enabled(pseudo)
        canvas.set_darken_comparison_enabled(darken)
        canvas.set_original_opacity(opacity)

    regional.set_images(original, labels)
    dirty = paint_brush_increment(
        labels,
        (3.5, 4.5),
        (10.5, 7.5),
        Label.BOUNDARY,
        3,
        "circle",
    )
    assert dirty is not None
    regional.refresh_label_region(labels, dirty)
    full.set_images(original, labels.copy())

    assert regional._label_image is not None
    assert full._label_image is not None
    np.testing.assert_array_equal(_rgb(regional._label_image), _rgb(full._label_image))
    regional_display = regional._native_display_image()
    full_display = full._native_display_image()
    assert regional_display is not None
    assert full_display is not None
    np.testing.assert_array_equal(_rgb(regional_display), _rgb(full_display))


def test_main_window_brush_preview_uses_region_and_skips_noop(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = QSettings(str(tmp_path / "brush.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    labels = np.zeros((240, 180), dtype=np.uint8)
    window.session._labels = labels
    window._stroke_before = labels.copy()
    window._stroke_label = int(Label.PRESENT)
    window._stroke_diameter = 5
    window._stroke_shape = "circle"
    regional_calls: list[tuple[int, int, int, int]] = []
    full_calls: list[np.ndarray] = []

    monkeypatch.setattr(
        window.canvas,
        "refresh_label_region",
        lambda target, bbox: regional_calls.append(bbox),
    )
    monkeypatch.setattr(
        window.canvas,
        "refresh_labels",
        lambda target=None: full_calls.append(target),
    )

    window.canvas.begin_label_memo_erase()
    window._render_brush_preview((20.5, 20.5), (28.5, 20.5))
    assert len(regional_calls) == 1
    window._render_brush_preview((20.5, 20.5), (28.5, 20.5))
    assert len(regional_calls) == 1
    assert full_calls == []
    window.canvas.cancel_label_memo_erase()
    window._stroke_before = None


def test_pointer_and_label_changes_request_bounded_widget_updates(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas = ImageCanvas()
    canvas.resize(640, 480)
    qtbot.addWidget(canvas)
    labels = np.zeros((240, 320), dtype=np.uint8)
    canvas.set_images(np.zeros((240, 320, 3), dtype=np.uint8), labels)
    updates: list[tuple[object, ...]] = []
    monkeypatch.setattr(canvas, "update", lambda *args: updates.append(args))

    canvas._update_pointer(QPointF(*canvas.transform.image_to_canvas(80.5, 60.5)))
    updates.clear()
    canvas._update_pointer(QPointF(*canvas.transform.image_to_canvas(250.5, 100.5)))
    pointer_updates = tuple(updates)
    assert len(pointer_updates) == 2
    dirty = paint_brush_increment(
        labels,
        (250.5, 100.5),
        (258.5, 104.5),
        Label.PRESENT,
        5,
        "circle",
    )
    assert dirty is not None
    canvas.refresh_label_region(labels, dirty)

    assert updates
    assert all(len(args) == 1 and isinstance(args[0], QRect) for args in updates)
    rects = [args[0] for args in updates]
    assert len(rects) >= 3
    assert all(not rect.isEmpty() for rect in rects)
    assert all(
        rect.width() * rect.height() < canvas.width() * canvas.height() // 4 for rect in rects
    )


@pytest.mark.parametrize(
    ("button", "temporary_pan"),
    (
        (Qt.MouseButton.MiddleButton, False),
        (Qt.MouseButton.LeftButton, True),
    ),
    ids=("middle", "space-left"),
)
@pytest.mark.parametrize("ternary_visible", [True, False])
def test_pan_repaints_the_full_canvas_during_each_drag_move(
    qtbot,
    button: Qt.MouseButton,
    temporary_pan: bool,
    ternary_visible: bool,
) -> None:
    class PaintProbeCanvas(ImageCanvas):
        def __init__(self) -> None:
            self.paint_regions: list[QRegion] = []
            super().__init__()

        def paintEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt override
            self.paint_regions.append(QRegion(event.region()))
            super().paintEvent(event)

    canvas = PaintProbeCanvas()
    canvas.resize(320, 240)
    qtbot.addWidget(canvas)
    canvas.set_images(
        np.zeros((512, 512, 3), dtype=np.uint8),
        np.zeros((512, 512), dtype=np.uint8),
        reset_view=True,
    )
    canvas.set_actual_size()
    canvas.ternary_visible = ternary_visible
    canvas.show()
    qtbot.waitExposed(canvas)
    canvas.set_space_pressed(temporary_pan)

    start = QPoint(150, 110)
    moves = (QPoint(175, 125), QPoint(210, 150))
    qtbot.mouseMove(canvas, start)
    qtbot.mousePress(canvas, button, pos=start)
    QApplication.processEvents()
    origin = (canvas.transform.origin_x, canvas.transform.origin_y)

    for point in moves:
        canvas.paint_regions.clear()
        qtbot.mouseMove(canvas, point)
        QApplication.processEvents()

        assert canvas.paint_regions
        assert any(region.contains(canvas.rect()) for region in canvas.paint_regions)

    assert canvas.transform.origin_x == pytest.approx(origin[0] + 60)
    assert canvas.transform.origin_y == pytest.approx(origin[1] + 40)

    qtbot.mouseRelease(canvas, button, pos=moves[-1])
    assert not canvas._panning
    assert canvas._last_pan_position is None
    canvas.set_space_pressed(False)


def test_native_cursor_is_hidden_only_while_the_custom_image_pointer_is_visible(qtbot) -> None:
    canvas = ImageCanvas()
    canvas.resize(640, 480)
    qtbot.addWidget(canvas)
    canvas.set_images(
        np.zeros((240, 320, 3), dtype=np.uint8),
        np.zeros((240, 320), dtype=np.uint8),
        reset_view=True,
    )
    canvas.set_actual_size()
    canvas.show()
    qtbot.waitExposed(canvas)
    inside = QPointF(*canvas.transform.image_to_canvas(80.5, 60.5))
    protected = QPointF(*canvas.transform.image_to_canvas(80.5, 200.5))

    canvas._update_pointer(inside)
    assert canvas._cursor_image is not None
    assert canvas.cursor().shape() is Qt.CursorShape.BlankCursor

    canvas.tool = EditTool.FILL
    canvas._refresh_cursor_shape()
    assert canvas.cursor().shape() is Qt.CursorShape.BlankCursor
    canvas._update_pointer(protected)
    assert canvas._cursor_protected
    assert canvas.cursor().shape() is Qt.CursorShape.BlankCursor

    canvas.set_space_pressed(True)
    assert canvas.cursor().shape() is Qt.CursorShape.OpenHandCursor
    canvas.set_space_pressed(False)
    assert canvas.cursor().shape() is Qt.CursorShape.BlankCursor

    pan_position = QPoint(round(inside.x()), round(inside.y()))
    qtbot.mousePress(canvas, Qt.MouseButton.MiddleButton, pos=pan_position)
    assert canvas.cursor().shape() is Qt.CursorShape.ClosedHandCursor
    qtbot.mouseRelease(canvas, Qt.MouseButton.MiddleButton, pos=pan_position)
    assert canvas.cursor().shape() is Qt.CursorShape.BlankCursor

    canvas.ternary_visible = False
    assert canvas.cursor().shape() is Qt.CursorShape.ArrowCursor
    canvas.ternary_visible = True
    assert canvas.cursor().shape() is Qt.CursorShape.BlankCursor

    canvas._update_pointer(QPointF(1.0, 1.0))
    assert canvas._cursor_image is None
    assert canvas.cursor().shape() is Qt.CursorShape.ArrowCursor


def test_grid_iteration_is_limited_to_the_paint_event_region(qtbot) -> None:
    class PainterProbe:
        def __init__(self) -> None:
            self.lines: list[tuple[QPointF, QPointF]] = []

        def setPen(self, _pen) -> None:  # noqa: N802, ANN001 - QPainter-compatible probe
            return

        def drawLine(self, start: QPointF, end: QPointF) -> None:  # noqa: N802
            self.lines.append((start, end))

    canvas = ImageCanvas()
    canvas.resize(640, 480)
    qtbot.addWidget(canvas)
    canvas.set_images(
        np.zeros((240, 320, 3), dtype=np.uint8),
        np.zeros((240, 320), dtype=np.uint8),
    )
    canvas.transform.zoom_at(320.0, 240.0, 8.0)
    probe = PainterProbe()

    canvas._paint_grid(probe, QRect(280, 200, 64, 64))  # type: ignore[arg-type]

    assert 0 < len(probe.lines) < 40


def test_paint_event_preserves_disjoint_update_regions(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas = ImageCanvas()
    canvas.resize(640, 480)
    qtbot.addWidget(canvas)
    canvas.set_images(
        np.zeros((240, 320, 3), dtype=np.uint8),
        np.zeros((240, 320), dtype=np.uint8),
    )
    background_rects: list[QRect] = []
    grid_rects: list[QRect] = []
    render_hint = canvas_module.QPainter.RenderHint

    class PainterProbe:
        RenderHint = render_hint

        def __init__(self, _widget) -> None:  # noqa: ANN001 - QPainter-compatible probe
            return

        def setRenderHint(self, _hint, _enabled=True) -> None:  # noqa: N802, ANN001
            return

        def end(self) -> None:
            return

    monkeypatch.setattr(canvas_module, "QPainter", PainterProbe)
    monkeypatch.setattr(
        canvas,
        "_paint_background",
        lambda _painter, rect: background_rects.append(rect),
    )
    monkeypatch.setattr(canvas, "_paint_grid", lambda _painter, rect: grid_rects.append(rect))
    for method_name in (
        "_paint_image_layers",
        "_paint_protected_region",
        "_paint_warning_boxes",
        "_paint_outer_border",
        "_paint_pointer",
    ):
        monkeypatch.setattr(canvas, method_name, lambda _painter: None)

    region = QRegion(QRect(12, 18, 20, 24)).united(QRegion(QRect(520, 390, 18, 22)))
    expected = tuple(region)
    assert len(expected) == 2

    canvas.paintEvent(QPaintEvent(region))

    assert tuple(background_rects) == expected
    assert tuple(grid_rects) == expected
    assert region.boundingRect().width() * region.boundingRect().height() > sum(
        rect.width() * rect.height() for rect in expected
    )


@pytest.mark.performance
def test_regional_brush_pipeline_is_materially_faster_than_full_refresh(qtbot) -> None:
    height, width = 1536, 2048
    original = np.zeros((height, width, 3), dtype=np.uint8)
    full_labels = np.zeros((height, width), dtype=np.uint8)
    regional_labels = np.zeros((height, width), dtype=np.uint8)
    full = ImageCanvas()
    regional = ImageCanvas()
    qtbot.addWidget(full)
    qtbot.addWidget(regional)
    full.set_images(original, full_labels)
    regional.set_images(original, regional_labels)

    def sample(canvas: ImageCanvas, labels: np.ndarray, *, use_region: bool) -> list[float]:
        samples: list[float] = []
        for index in range(10):
            replacement = Label.PRESENT if index % 2 == 0 else Label.BOUNDARY
            started = time.perf_counter()
            dirty = paint_brush_increment(
                labels,
                (1000.5, 700.5),
                (1008.5, 704.5),
                replacement,
                5,
                "circle",
            )
            assert dirty is not None
            if use_region:
                canvas.refresh_label_region(labels, dirty)
            else:
                canvas.refresh_labels(labels)
            assert canvas._native_display_image() is not None
            samples.append((time.perf_counter() - started) * 1000.0)
        return samples[2:]

    full_median = statistics.median(sample(full, full_labels, use_region=False))
    regional_median = statistics.median(sample(regional, regional_labels, use_region=True))

    assert regional_median < full_median * 0.5, (
        f"regional={regional_median:.3f} ms, full={full_median:.3f} ms"
    )
