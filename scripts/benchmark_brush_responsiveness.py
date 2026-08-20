"""筆の全画像更新相当と局所更新を同一processで比較する局所probe。"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import PySide6
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from ternary_image_editor import __version__
from ternary_image_editor.canvas import ImageCanvas
from ternary_image_editor.operations import paint_brush_increment

IMAGE_HEIGHT = 1536
IMAGE_WIDTH = 2048
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 800
BRUSH_DIAMETER = 5
WARMUP_SAMPLES = 4


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, int(len(ordered) * percentile + 0.999999999))
    return ordered[min(rank, len(ordered)) - 1]


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(_nearest_rank(values, 0.95), 3),
        "max_ms": round(max(values), 3),
    }


def _make_canvas(
    application: QApplication,
    original: np.ndarray,
    configure_view: Callable[[ImageCanvas], None],
) -> tuple[ImageCanvas, np.ndarray]:
    labels = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8)
    canvas = ImageCanvas()
    canvas.resize(CANVAS_WIDTH, CANVAS_HEIGHT)
    canvas.set_images(original, labels)
    configure_view(canvas)
    canvas.show()
    canvas.update()
    application.processEvents()
    return canvas, labels


def _sample(
    application: QApplication,
    canvas: ImageCanvas,
    labels: np.ndarray,
    *,
    regional: bool,
    iterations: int,
    shift_modulus: int,
) -> list[float]:
    values: list[float] = []
    for index in range(iterations):
        shift = index % shift_modulus
        start = (1000.5 + shift, 700.5 + shift)
        end = (1008.5 + shift, 704.5 + shift)
        replacement = 1 if index % 2 == 0 else 2
        canvas_point = canvas.transform.image_to_canvas(*end)

        started = time.perf_counter_ns()
        canvas._update_pointer(QPointF(*canvas_point))
        dirty = paint_brush_increment(
            labels,
            start,
            end,
            replacement,
            BRUSH_DIAMETER,
            "circle",
        )
        if dirty is not None:
            if regional:
                canvas.refresh_label_region(labels, dirty)
            else:
                canvas.refresh_labels(labels)
        application.processEvents()
        values.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return values[WARMUP_SAMPLES:]


def _run_case(
    application: QApplication,
    original: np.ndarray,
    *,
    name: str,
    iterations: int,
    shift_modulus: int,
    configure_view: Callable[[ImageCanvas], None],
) -> dict[str, Any]:
    full_canvas, full_labels = _make_canvas(application, original, configure_view)
    regional_canvas, regional_labels = _make_canvas(application, original, configure_view)
    try:
        full = _sample(
            application,
            full_canvas,
            full_labels,
            regional=False,
            iterations=iterations,
            shift_modulus=shift_modulus,
        )
        regional = _sample(
            application,
            regional_canvas,
            regional_labels,
            regional=True,
            iterations=iterations,
            shift_modulus=shift_modulus,
        )
    finally:
        full_canvas.close()
        regional_canvas.close()
        application.processEvents()

    full_p50 = statistics.median(full)
    regional_p50 = statistics.median(regional)
    return {
        "case": name,
        "iterations": iterations,
        "warmup_samples_excluded": WARMUP_SAMPLES,
        "measured_samples": iterations - WARMUP_SAMPLES,
        "legacy_full_refresh_surrogate": _summary(full),
        "regional_refresh": _summary(regional),
        "p50_speedup": round(full_p50 / regional_p50, 2),
        "p50_reduction_percent": round((1.0 - regional_p50 / full_p50) * 100.0, 1),
    }


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication(["brush-responsiveness-benchmark"])
    original = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)

    def actual_size(canvas: ImageCanvas) -> None:
        canvas.set_actual_size()

    def scale_eight_grid(canvas: ImageCanvas) -> None:
        canvas.transform.zoom_at(canvas.width() / 2, canvas.height() / 2, 8.0)
        canvas.transform.center_on_image(1004.5, 702.5)

    result = {
        "benchmark": "brush-responsiveness-local-ab-v1",
        "application_version": __version__,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "pyside6": PySide6.__version__,
            "numpy": np.__version__,
            "qt_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        },
        "parameters": {
            "image": [IMAGE_WIDTH, IMAGE_HEIGHT],
            "canvas": [CANVAS_WIDTH, CANVAS_HEIGHT],
            "brush_diameter": BRUSH_DIAMETER,
            "segment_start": [1000.5, 700.5],
            "segment_end": [1008.5, 704.5],
            "percentile_method": "nearest-rank",
            "scope": "pointer update, brush operation, label refresh, display rebuild, Qt events",
        },
        "cases": [
            _run_case(
                application,
                original,
                name="actual-size-no-grid",
                iterations=64,
                shift_modulus=6,
                configure_view=actual_size,
            ),
            _run_case(
                application,
                original,
                name="scale-8-auto-grid",
                iterations=44,
                shift_modulus=4,
                configure_view=scale_eight_grid,
            ),
        ],
        "acceptance_boundary": (
            "same-process offscreen comparison; not Windows input-to-photon acceptance"
        ),
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
