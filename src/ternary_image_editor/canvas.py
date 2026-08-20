"""保存データ・表示像・操作overlayを分離した画像キャンバス。"""

from __future__ import annotations

from enum import StrEnum
from math import ceil, floor, isclose

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from .canvas_transform import CanvasTransform
from .constants import (
    DEFAULT_BRUSH_DIAMETER,
    DEFAULT_PSEUDO_RGB,
    SAVE_RGB,
    protected_start_y,
)
from .memo_history import MemoDelta, MemoPixelPatch
from .operations import BoundingBox, BrushSegmentFootprint, brush_shape_mask

UInt8Array = NDArray[np.uint8]
BoolArray = NDArray[np.bool_]


class EditTool(StrEnum):
    BRUSH = "brush"
    FILL = "fill"


class BrushShape(StrEnum):
    CIRCLE = "circle"
    SQUARE = "square"


def qimage_from_rgb(rgb: UInt8Array) -> QImage:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("QImage変換元はuint8のH×W×3配列でなければならない")
    contiguous = np.ascontiguousarray(rgb)
    height, width, _ = contiguous.shape
    image = QImage(
        contiguous.data,
        width,
        height,
        contiguous.strides[0],
        QImage.Format.Format_RGB888,
    )
    return image.copy()


def qimage_from_warning_mask(mask: BoolArray) -> QImage:
    if mask.ndim != 2 or mask.dtype != np.bool_:
        raise ValueError("警告maskはbool二次元配列でなければならない")
    height, width = mask.shape
    rows = np.arange(height, dtype=np.uint32)[:, None]
    columns = np.arange(width, dtype=np.uint32)[None, :]
    stripe = ((columns + rows) // 2) % 2 == 0
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., :3] = np.where(stripe[..., None], 255, 0)
    rgba[..., 3] = np.where(mask, 150, 0).astype(np.uint8)
    image = QImage(
        rgba.data,
        width,
        height,
        rgba.strides[0],
        QImage.Format.Format_RGBA8888,
    )
    return image.copy()


def qimage_from_brush_mask(
    mask: BoolArray,
    *,
    color: tuple[int, int, int] = (255, 255, 255),
    blocked: bool = False,
) -> QImage:
    """離散筆maskを、内部半透明・輪郭不透明の表示像へ変換する。"""

    if mask.ndim != 2 or mask.dtype != np.bool_:
        raise ValueError("筆maskはbool二次元配列でなければならない")
    height, width = mask.shape
    padded = np.pad(mask, 1, constant_values=False)
    interior = mask & padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    edge = mask & ~interior
    if len(color) != 3 or any(channel < 0 or channel > 255 for channel in color):
        raise ValueError("筆ポインタ色は0から255のRGB三成分でなければならない")
    fill_color = (255, 70, 70) if blocked else color
    luminance = 0.2126 * fill_color[0] + 0.7152 * fill_color[1] + 0.0722 * fill_color[2]
    edge_color = (20, 20, 20) if luminance >= 150 else (245, 245, 245)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., :3] = fill_color
    rgba[edge, :3] = edge_color
    rgba[..., 3] = np.where(edge, 245, np.where(mask, 105, 0)).astype(np.uint8)
    image = QImage(
        rgba.data,
        width,
        height,
        rgba.strides[0],
        QImage.Format.Format_RGBA8888,
    )
    return image.copy()


class ImageCanvas(QWidget):
    brush_started = Signal(float, float)
    brush_moved = Signal(float, float)
    brush_finished = Signal()
    brush_cancelled = Signal(str)
    fill_requested = Signal(int, int)
    cursor_position_changed = Signal(object)
    view_changed = Signal(float)
    interaction_blocked = Signal(str)
    protected_cursor_changed = Signal(bool)
    memo_stroke_committed = Signal(object)
    memo_stroke_active_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.transform = CanvasTransform(
            viewport_width=self.width(),
            viewport_height=self.height(),
            device_pixel_ratio=max(self.devicePixelRatioF(), 1.0),
        )

        self.labels: UInt8Array | None = None
        self._label_image: QImage | None = None
        self._original_image: QImage | None = None
        self._display_image: QImage | None = None
        self._display_image_key: tuple[object, ...] | None = None
        self._warning_image: QImage | None = None
        self._warning_mask: BoolArray | None = None
        self._warning_boxes: tuple[tuple[int, int, int, int], ...] = ()
        self._memo_image: QImage | None = None
        self._memo_nontransparent_pixels = 0

        self._ternary_visible = True
        self.original_visible = True
        self.original_opacity = 0.5
        self.pseudo_enabled = False
        self.darken_comparison_enabled = False
        self.pseudo_palette = DEFAULT_PSEUDO_RGB
        self.auto_grid_enabled = True
        self.warning_visible = False
        self.editing_enabled = True
        self.memo_enabled = True
        self.tool = EditTool.BRUSH
        self.brush_shape = BrushShape.CIRCLE
        self.brush_diameter = DEFAULT_BRUSH_DIAMETER
        self.selected_label = 1

        self._cursor_canvas: QPointF | None = None
        self._cursor_image: tuple[float, float] | None = None
        self._cursor_protected = False
        self._brush_pointer_key: tuple[int, str, int, bool] | None = None
        self._brush_pointer_image: QImage | None = None
        self._space_pressed = False
        self._panning = False
        self._brushing = False
        self._last_pan_position: QPointF | None = None
        self._memo_drawing = False
        self._memo_last_image_position: tuple[float, float] | None = None
        self._memo_stroke_touched: set[int] | None = None
        self._memo_stroke_before: list[tuple[NDArray[np.uint32], UInt8Array]] = []
        self._pending_label_memo_patches: list[MemoPixelPatch] | None = None

    @property
    def has_image(self) -> bool:
        return self.labels is not None and self._label_image is not None

    @property
    def has_memo(self) -> bool:
        return self._memo_image is not None and self._memo_nontransparent_pixels > 0

    @property
    def memo_stroke_active(self) -> bool:
        return self._memo_drawing

    @property
    def temporary_pan_active(self) -> bool:
        """Return whether a held key or GUI toggle currently requests left-drag pan."""

        return self._space_pressed

    @property
    def ternary_visible(self) -> bool:
        return self._ternary_visible

    @ternary_visible.setter
    def ternary_visible(self, visible: bool) -> None:
        requested = bool(visible)
        if not requested and getattr(self, "_brushing", False):
            self.interaction_blocked.emit("筆操作中は三値画像を隠せない")
            return
        if requested == getattr(self, "_ternary_visible", True):
            return
        self._ternary_visible = requested
        self._invalidate_display_image()
        self._refresh_cursor_shape()
        self.update()

    def set_images(
        self,
        original_rgb: UInt8Array,
        labels: UInt8Array,
        *,
        reset_view: bool = False,
    ) -> None:
        self._validate_image_pair(original_rgb, labels)
        same_dimensions = (
            self.labels is not None
            and self.labels.shape == labels.shape
            and self.transform.image_width == labels.shape[1]
            and self.transform.image_height == labels.shape[0]
        )
        old_state = self.transform.capture_state() if same_dimensions else None
        self.labels = labels
        self._original_image = qimage_from_rgb(original_rgb)
        self._invalidate_display_image()
        self._refresh_label_image()
        height, width = labels.shape
        self._reset_memo_layer(width, height)
        if not same_dimensions:
            self.transform = CanvasTransform(
                image_width=width,
                image_height=height,
                viewport_width=self.width(),
                viewport_height=self.height(),
                device_pixel_ratio=max(self.devicePixelRatioF(), 1.0),
            )
        if reset_view or old_state is None:
            self.transform.fit_to_view()
        else:
            self.transform.restore_state(old_state)
        self.clear_warning_overlay()
        self._remap_pointer()
        self.update()
        self.view_changed.emit(self.transform.scale)

    def clear_images(self) -> None:
        self._reset_memo_layer(None, None)
        self.labels = None
        self._label_image = None
        self._original_image = None
        self._invalidate_display_image()
        self.clear_warning_overlay()
        self._clear_pointer()
        self.update()

    def refresh_labels(self, labels: UInt8Array | None = None) -> None:
        if labels is not None:
            if self.labels is not None and labels.shape != self.labels.shape:
                raise ValueError("更新ラベルの寸法が現在画像と一致しない")
            self.labels = labels
        self._refresh_label_image()
        self.update()

    def refresh_label_region(
        self,
        labels: UInt8Array,
        dirty_bbox: BoundingBox,
    ) -> None:
        """変更済みラベルの半開矩形だけを表示用QImageへ反映する。"""

        if labels.ndim != 2 or labels.dtype != np.uint8:
            raise ValueError("更新ラベルはuint8二次元配列でなければならない")
        if self.labels is not None and labels.shape != self.labels.shape:
            raise ValueError("更新ラベルの寸法が現在画像と一致しない")
        left, top, right, bottom = dirty_bbox
        height, width = labels.shape
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("更新矩形は現在画像内の非空半開矩形でなければならない")

        self.labels = labels
        if (
            self._label_image is None
            or self._label_image.width() != width
            or self._label_image.height() != height
        ):
            self._refresh_label_image()
            self.update()
            return

        region = labels[top:bottom, left:right]
        if np.any(region > 2):
            raise ValueError("ラベル値は0/1/2だけでなければならない")
        palette = self.pseudo_palette if self.pseudo_enabled else SAVE_RGB
        rgb = np.asarray(palette, dtype=np.uint8)[region]
        patch = qimage_from_rgb(rgb)
        painter = QPainter(self._label_image)
        if not painter.isActive():
            raise RuntimeError("ラベル表示像の局所更新を開始できない")
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.drawImage(left, top, patch)
        finally:
            painter.end()
        self._invalidate_display_image()
        dirty_rect = self._canvas_rect_for_image_bbox(dirty_bbox)
        if not dirty_rect.isEmpty():
            self.update(dirty_rect)

    def begin_label_memo_erase(self) -> None:
        """進行中のラベル筆へ束ねるメモ消去取引を開始する。"""

        if self._pending_label_memo_patches is not None:
            raise RuntimeError("メモ消去取引が既に開始されている")
        self._pending_label_memo_patches = []

    def stage_label_memo_erase(self, footprint: BrushSegmentFootprint) -> None:
        """筆跡maskと重なる不透明メモだけを即時消去して退避する。"""

        if self._pending_label_memo_patches is None:
            raise RuntimeError("メモ消去取引が開始されていない")
        patch = self._erase_memo_mask(footprint.bbox, footprint.mask)
        if patch is not None:
            self._pending_label_memo_patches.append(patch)

    def finish_label_memo_erase(self, description: str) -> MemoDelta | None:
        """進行中のメモ消去を一つの可逆差分として確定する。"""

        patches = self._pending_label_memo_patches
        if patches is None:
            return None
        self._pending_label_memo_patches = None
        if not patches:
            return None
        assert self.labels is not None
        return MemoDelta(self.labels.shape, tuple(patches), description)

    def cancel_label_memo_erase(self) -> bool:
        """取消されたラベル筆が消したメモを元へ戻す。"""

        patches = self._pending_label_memo_patches
        self._pending_label_memo_patches = None
        if not patches or self.labels is None:
            return False
        delta = MemoDelta(self.labels.shape, tuple(patches), "取消された筆のメモ消去")
        self.apply_memo_delta(delta, forward=False)
        return True

    def erase_memo_indices(
        self,
        indices: NDArray[np.uint32],
        description: str,
    ) -> MemoDelta | None:
        """ラベル差分索引と重なるメモを消し、同じ履歴項目用の差分を返す。"""

        if (
            self._memo_image is None
            or self.labels is None
            or self._memo_nontransparent_pixels == 0
            or indices.size == 0
        ):
            return None
        if indices.dtype != np.uint32 or indices.ndim != 1:
            raise ValueError("メモ消去索引はuint32一次元配列でなければならない")
        if indices.size > 1 and np.unique(indices).size != indices.size:
            raise ValueError("メモ消去索引に重複がある")
        rgba = self._memo_rgba_view()
        flat = rgba.reshape(-1, 4)
        opaque = flat[indices, 3] != 0
        if not opaque.any():
            return None
        removed_indices = indices[opaque].astype(np.uint32, copy=True)
        before = flat[removed_indices].astype(np.uint8, copy=True)
        after = np.zeros((removed_indices.size, 4), dtype=np.uint8)
        flat[removed_indices] = after
        self._memo_nontransparent_pixels -= int(removed_indices.size)
        patch = MemoPixelPatch(removed_indices, before, after)
        delta = MemoDelta(self.labels.shape, (patch,), description)
        self._update_memo_bbox(delta.bounding_box)
        self._release_empty_memo_image()
        return delta

    def apply_memo_delta(self, delta: MemoDelta, *, forward: bool) -> None:
        """Undo/Redoからメモ差分だけを原解像度像へ適用する。"""

        if self.labels is None:
            raise RuntimeError("メモ差分の適用先画像がない")
        if delta.shape != self.labels.shape:
            raise ValueError(
                f"メモ差分の適用先が一致しない: {delta.shape} != {self.labels.shape}"
            )
        self._ensure_memo_image()
        rgba = self._memo_rgba_view()
        flat = rgba.reshape(-1, 4)
        before_opaque = sum(
            int(np.count_nonzero(flat[patch.indices, 3])) for patch in delta.patches
        )
        if forward:
            delta.apply_forward(rgba)
        else:
            delta.apply_backward(rgba)
        after_opaque = sum(
            int(np.count_nonzero(flat[patch.indices, 3])) for patch in delta.patches
        )
        self._memo_nontransparent_pixels += after_opaque - before_opaque
        self._update_memo_bbox(delta.bounding_box)
        self._release_empty_memo_image()

    def clear_memo(self) -> None:
        """表示中メモと未確定メモ取引を破棄する。履歴破棄は所有者が行う。"""

        had_memo = self.has_memo
        self._abandon_memo_stroke()
        self._pending_label_memo_patches = None
        self._memo_image = None
        self._memo_nontransparent_pixels = 0
        if had_memo and self.labels is not None:
            self._update_memo_bbox((0, 0, self.labels.shape[1], self.labels.shape[0]))

    def cancel_memo_stroke(self, reason: str = "メモ入力を取り消した") -> bool:
        """右押下中の一筆全体を押下前へ戻し、履歴を作らない。"""

        if not self._memo_drawing:
            return False
        if self._memo_image is not None and self._memo_stroke_before:
            rgba = self._memo_rgba_view()
            flat = rgba.reshape(-1, 4)
            changed_indices: list[NDArray[np.uint32]] = []
            for indices, before in self._memo_stroke_before:
                self._memo_nontransparent_pixels += int(
                    np.count_nonzero(before[:, 3])
                    - np.count_nonzero(flat[indices, 3])
                )
                flat[indices] = before
                changed_indices.append(indices)
            self._update_memo_indices(changed_indices)
        self._abandon_memo_stroke()
        self._release_empty_memo_image()
        if reason:
            self.interaction_blocked.emit(reason)
        return True

    def finish_memo_stroke(self) -> MemoDelta | None:
        """右押下から解放までを一つのメモ履歴差分へ確定する。"""

        if not self._memo_drawing or self._memo_image is None or self.labels is None:
            return None
        rgba = self._memo_rgba_view()
        flat = rgba.reshape(-1, 4)
        patches: list[MemoPixelPatch] = []
        for indices, before in self._memo_stroke_before:
            after = flat[indices].astype(np.uint8, copy=True)
            changed = np.any(before != after, axis=1)
            if not changed.any():
                continue
            selected = indices[changed].astype(np.uint32, copy=True)
            patches.append(
                MemoPixelPatch(
                    selected,
                    before[changed].astype(np.uint8, copy=True),
                    after[changed].astype(np.uint8, copy=True),
                )
            )
        self._abandon_memo_stroke()
        self._release_empty_memo_image()
        if not patches:
            return None
        delta = MemoDelta(self.labels.shape, tuple(patches), "メモ一筆")
        self.memo_stroke_committed.emit(delta)
        return delta

    def set_warning_overlay(
        self,
        mask: BoolArray,
        boxes: tuple[tuple[int, int, int, int], ...] | list[tuple[int, int, int, int]],
    ) -> None:
        if self.labels is None or mask.shape != self.labels.shape:
            raise ValueError("警告maskの寸法が現在画像と一致しない")
        self._warning_mask = mask
        self._warning_image = qimage_from_warning_mask(mask)
        self._warning_boxes = tuple(boxes)
        self.update()

    def clear_warning_overlay(self) -> None:
        self._warning_mask = None
        self._warning_image = None
        self._warning_boxes = ()
        self.update()

    def set_pseudo_enabled(self, enabled: bool) -> None:
        self.pseudo_enabled = enabled
        self._refresh_label_image()
        self.update()

    def set_darken_comparison_enabled(self, enabled: bool) -> None:
        """表示合成だけを比較（暗）へ切り替え、画像データには作用させない。"""

        requested = bool(enabled)
        if requested == self.darken_comparison_enabled:
            return
        self.darken_comparison_enabled = requested
        self._invalidate_display_image()
        self.update()

    def set_pseudo_palette(self, palette: tuple[tuple[int, int, int], ...]) -> None:
        if len(palette) != 3 or any(len(color) != 3 for color in palette):
            raise ValueError("疑似色はRGB三色で指定する")
        if any(channel < 0 or channel > 255 for color in palette for channel in color):
            raise ValueError("疑似色成分は0から255で指定する")
        self.pseudo_palette = palette
        if self.pseudo_enabled:
            self._refresh_label_image()
            self.update()

    def set_original_opacity(self, opacity: float) -> None:
        self.original_opacity = min(max(float(opacity), 0.0), 1.0)
        self._invalidate_display_image()
        self.update()

    def set_selected_label(self, label: int) -> None:
        """筆ポインタへ、疑似色ではなく保存色の選択状態を反映する。"""

        normalized = int(label)
        if normalized not in {0, 1, 2}:
            raise ValueError("選択ラベルは0、1、2のいずれかでなければならない")
        if normalized == self.selected_label:
            return
        self.selected_label = normalized
        self._brush_pointer_key = None
        self._brush_pointer_image = None
        self.update()

    def set_space_pressed(self, pressed: bool) -> None:
        """Space押下状態を焦点widgetによらず表示範囲移動へ渡す。"""

        if pressed and (self._brushing or self._memo_drawing):
            operation = "メモ" if self._memo_drawing else "筆"
            self.interaction_blocked.emit(f"{operation}操作中は一時パンへ切り替えられない")
            return
        self._space_pressed = bool(pressed)
        if self._panning:
            return
        self._refresh_cursor_shape()

    def cancel_navigation_input(self) -> None:
        """焦点・window活性喪失時に一時的なパン入力状態を破棄する。"""

        self.cancel_memo_stroke("焦点の喪失によりメモ入力を取り消した")
        self._space_pressed = False
        self._panning = False
        self._last_pan_position = None
        self._refresh_cursor_shape()
        self.update()

    def cancel_brush(self, reason: str = "筆操作を取り消した") -> bool:
        """進行中の筆を正常確定と分離して取り消す。

        ラベル配列の復元は ``brush_cancelled`` を受ける所有者が行う。
        """

        if not self._brushing:
            return False
        self._brushing = False
        self.brush_cancelled.emit(reason)
        self._refresh_cursor_shape()
        self.update()
        return True

    def fit_to_view(self) -> None:
        if self._view_change_is_blocked():
            return
        self.transform.fit_to_view()
        self._remap_pointer()
        self.update()
        self.view_changed.emit(self.transform.scale)

    def set_actual_size(self) -> None:
        if self._view_change_is_blocked():
            return
        self.transform.set_actual_size()
        self._remap_pointer()
        self.update()
        self.view_changed.emit(self.transform.scale)

    def set_zoom_percent(self, percent: float) -> None:
        if self._view_change_is_blocked():
            return
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        self.transform.zoom_at(center.x(), center.y(), percent / 100.0)
        self._remap_pointer()
        self.update()
        self.view_changed.emit(self.transform.scale)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        self._sync_device_pixel_ratio()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        dirty_rects = tuple(event.region())
        for dirty_rect in dirty_rects:
            self._paint_background(painter, dirty_rect)
        if self.has_image:
            self._paint_image_layers(painter)
            for dirty_rect in dirty_rects:
                self._paint_grid(painter, dirty_rect)
            self._paint_protected_region(painter)
            self._paint_warning_boxes(painter)
            self._paint_outer_border(painter)
            self._paint_memo(painter)
            self._paint_pointer(painter)
        painter.end()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        previous_scale = self.transform.scale
        if self._brushing:
            self.cancel_brush("ウィンドウ寸法変更により筆操作を取り消した")
        if self._memo_drawing:
            self.cancel_memo_stroke("ウィンドウ寸法変更によりメモ入力を取り消した")
        self.transform.set_viewport(
            event.size().width(),
            event.size().height(),
            dpr=max(self.devicePixelRatioF(), 1.0),
        )
        self._remap_pointer()
        self._finish_brush_if_uneditable()
        if not isclose(previous_scale, self.transform.scale, rel_tol=0.0, abs_tol=1e-12):
            self.view_changed.emit(self.transform.scale)
        self.update()
        super().resizeEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        if not self.has_image:
            event.ignore()
            return
        if self._view_change_is_blocked():
            event.accept()
            return
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = 1.25 if delta > 0 else 1.0 / 1.25
        position = event.position()
        self.transform.zoom_at(
            position.x(),
            position.y(),
            self.transform.scale * factor,
        )
        self._update_pointer(position)
        self.update()
        self.view_changed.emit(self.transform.scale)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        position = event.position()
        self._update_pointer(position)
        if self._memo_drawing:
            self.interaction_blocked.emit("メモを放して一筆を確定してから別の操作を行え")
            event.accept()
            return
        wants_pan = event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_pressed
        )
        if wants_pan and self._brushing:
            self.interaction_blocked.emit("筆を放して操作を確定してから表示位置を動かせ")
            event.accept()
            return
        if wants_pan:
            self._panning = True
            self._last_pan_position = position
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            if not self.has_image:
                super().mousePressEvent(event)
                return
            if not self.memo_enabled:
                self.interaction_blocked.emit("処理中はメモを描画できない")
                event.accept()
                return
            if self._brushing:
                self.interaction_blocked.emit("筆を放して操作を確定してからメモを描画せよ")
                event.accept()
                return
            pixel = self.transform.canvas_to_pixel(position.x(), position.y())
            if pixel is None:
                event.accept()
                return
            image_position = self.transform.canvas_to_image(position.x(), position.y())
            self._begin_memo_stroke(image_position)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton or not self.has_image:
            super().mousePressEvent(event)
            return
        if not self.editing_enabled:
            self.interaction_blocked.emit("処理中は編集できない")
            event.accept()
            return
        if not self.ternary_visible:
            self.interaction_blocked.emit("三値画像が非表示のため編集できない")
            event.accept()
            return
        pixel = self.transform.canvas_to_pixel(position.x(), position.y())
        if pixel is None:
            event.accept()
            return
        if pixel[1] >= protected_start_y(self.transform.image_height):
            self.interaction_blocked.emit("下端100画素・強制無領域")
            event.accept()
            return
        if self.tool == EditTool.FILL:
            self.fill_requested.emit(*pixel)
            event.accept()
            return
        if not self.transform.brush_is_editable(self.brush_diameter):
            self.interaction_blocked.emit("表示上の筆径が4実画面画素未満のため描画できない")
            event.accept()
            return
        image_position = self.transform.canvas_to_image(position.x(), position.y())
        self._brushing = True
        try:
            self.brush_started.emit(*image_position)
        except Exception:
            self.cancel_brush("筆開始中の例外により取り消した")
            raise
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        """未割当右double-clickの二度目も独立した押下として扱う。"""

        if event.button() == Qt.MouseButton.RightButton:
            self.mousePressEvent(event)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        position = event.position()
        if self._panning and self._last_pan_position is not None:
            delta = position - self._last_pan_position
            self.transform.pan_by(delta.x(), delta.y())
            self._last_pan_position = position
            self._update_pointer(position)
            event.accept()
            return
        self._update_pointer(position)
        if self._memo_drawing:
            image_position = self.transform.canvas_to_image(position.x(), position.y())
            assert self._memo_last_image_position is not None
            try:
                self._draw_memo_segment(self._memo_last_image_position, image_position)
            except Exception:
                self.cancel_memo_stroke("メモ描画中の例外により一筆を取り消した")
                raise
            self._memo_last_image_position = image_position
            event.accept()
            return
        if self._brushing:
            try:
                self.brush_moved.emit(*self.transform.canvas_to_image(position.x(), position.y()))
            except Exception:
                self.cancel_brush("筆描画中の例外により取り消した")
                raise
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        ):
            position = event.position()
            if self._last_pan_position is not None:
                delta = position - self._last_pan_position
                self.transform.pan_by(delta.x(), delta.y())
                self._update_pointer(position)
            self._panning = False
            self._last_pan_position = None
            self._refresh_cursor_shape()
            self.update()
            event.accept()
            return
        if self._brushing and event.button() == Qt.MouseButton.LeftButton:
            position = event.position()
            self._update_pointer(position)
            if not self._brushing:
                event.accept()
                return
            try:
                self.brush_moved.emit(*self.transform.canvas_to_image(position.x(), position.y()))
            except Exception:
                self.cancel_brush("筆解放中の例外により取り消した")
                raise
            self._brushing = False
            self.brush_finished.emit()
            event.accept()
            return
        if self._memo_drawing and event.button() == Qt.MouseButton.RightButton:
            position = event.position()
            self._update_pointer(position)
            if not self._memo_drawing:
                event.accept()
                return
            image_position = self.transform.canvas_to_image(position.x(), position.y())
            last_image_position = self._memo_last_image_position
            if last_image_position is None:
                self.cancel_memo_stroke("メモ確定状態が失われたため一筆を取り消した")
                event.accept()
                return
            try:
                self._draw_memo_segment(last_image_position, image_position)
                self._memo_last_image_position = image_position
                self.finish_memo_stroke()
            except Exception:
                self.cancel_memo_stroke("メモ確定中の例外により一筆を取り消した")
                raise
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape and self._memo_drawing:
            self.cancel_memo_stroke("Escによりメモ入力を取り消した")
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self._brushing:
            self.cancel_brush("Escにより筆操作を取り消した")
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        super().keyReleaseEvent(event)

    def event(self, event: QEvent) -> bool:  # noqa: A003 - Qt API
        event_type = event.type()
        if event_type in {
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.WindowDeactivate,
            QEvent.Type.UngrabMouse,
        }:
            if getattr(self, "_brushing", False):
                reason = (
                    "ポインタ捕捉喪失により筆操作を取り消した"
                    if event_type == QEvent.Type.UngrabMouse
                    else "ウィンドウ非アクティブ化により筆操作を取り消した"
                )
                self.cancel_brush(reason)
            if getattr(self, "_memo_drawing", False):
                reason = (
                    "ポインタ捕捉喪失によりメモ入力を取り消した"
                    if event_type == QEvent.Type.UngrabMouse
                    else "ウィンドウ非アクティブ化によりメモ入力を取り消した"
                )
                self.cancel_memo_stroke(reason)
        elif event_type in {
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
        }:
            handled = super().event(event)
            if hasattr(self, "transform") and hasattr(self, "_brushing"):
                self._sync_device_pixel_ratio()
            self.update()
            return handled
        return super().event(event)

    def leaveEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        if not self._brushing:
            self._clear_pointer()
        super().leaveEvent(event)

    def _refresh_label_image(self) -> None:
        if self.labels is None:
            self._label_image = None
            self._invalidate_display_image()
            return
        if self.labels.ndim != 2 or self.labels.dtype != np.uint8:
            raise ValueError("ラベルはuint8二次元配列でなければならない")
        if np.any(self.labels > 2):
            raise ValueError("ラベル値は0/1/2だけでなければならない")
        palette = self.pseudo_palette if self.pseudo_enabled else SAVE_RGB
        rgb = np.asarray(palette, dtype=np.uint8)[self.labels]
        self._label_image = qimage_from_rgb(rgb)
        self._invalidate_display_image()

    def _invalidate_display_image(self) -> None:
        self._display_image = None
        self._display_image_key = None

    def _native_display_image(self) -> QImage | None:
        """原解像度で完成像を作り、倍率変更前の単一QImageとして返す。"""

        if not self.has_image:
            return None
        assert self._label_image is not None
        original_key = None if self._original_image is None else self._original_image.cacheKey()
        key = (
            self._label_image.cacheKey(),
            original_key,
            self.ternary_visible,
            self.original_visible,
            round(self.original_opacity, 12),
            self.pseudo_enabled,
            self.darken_comparison_enabled,
        )
        if self._display_image_key == key:
            return self._display_image

        native: QImage | None
        if self.ternary_visible:
            native = self._label_image.copy()
            if (
                self.original_visible
                and self._original_image is not None
                and self.original_opacity > 0.0
            ):
                painter = QPainter(native)
                try:
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                    painter.setOpacity(self.original_opacity)
                    painter.setCompositionMode(
                        QPainter.CompositionMode.CompositionMode_Darken
                        if self.darken_comparison_enabled
                        else (
                            QPainter.CompositionMode.CompositionMode_SourceOver
                            if self.pseudo_enabled
                            else QPainter.CompositionMode.CompositionMode_Lighten
                        )
                    )
                    painter.drawImage(0, 0, self._original_image)
                finally:
                    painter.end()
        elif (
            self.original_visible
            and self._original_image is not None
            and self.original_opacity > 0.0
        ):
            native = QImage(
                self._original_image.width(),
                self._original_image.height(),
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            native.fill(Qt.GlobalColor.transparent)
            painter = QPainter(native)
            try:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                painter.setOpacity(self.original_opacity)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                painter.drawImage(0, 0, self._original_image)
            finally:
                painter.end()
        else:
            native = None

        self._display_image = native
        self._display_image_key = key
        return native

    def _paint_background(self, painter: QPainter, dirty_rect: QRect) -> None:
        tile = 20
        first = QColor(78, 82, 88)
        second = QColor(96, 100, 106)
        left = max(0, (dirty_rect.left() // tile) * tile)
        top = max(0, (dirty_rect.top() // tile) * tile)
        right = min(self.width(), dirty_rect.right() + 1)
        bottom = min(self.height(), dirty_rect.bottom() + 1)
        for y in range(top, bottom, tile):
            for x in range(left, right, tile):
                painter.fillRect(x, y, tile, tile, first if (x // tile + y // tile) % 2 else second)

    def _paint_image_layers(self, painter: QPainter) -> None:
        assert self.labels is not None
        native = self._native_display_image()
        if native is None:
            return
        painter.save()
        painter.translate(self.transform.origin_x, self.transform.origin_y)
        painter.scale(self.transform.scale, self.transform.scale)
        painter.setClipRect(QRectF(0, 0, self.transform.image_width, self.transform.image_height))
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            self.transform.scale < 1.0,
        )
        painter.setOpacity(1.0)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(0, 0, native)
        if self.ternary_visible and self.warning_visible and self._warning_image is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.setOpacity(1.0)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawImage(0, 0, self._warning_image)
        painter.restore()

    def _paint_grid(self, painter: QPainter, dirty_rect: QRect) -> None:
        if not self.transform.grid_is_visible(auto_enabled=self.auto_grid_enabled):
            return
        margin = 2.0
        top_left = self.transform.canvas_to_image(
            dirty_rect.left() - margin,
            dirty_rect.top() - margin,
        )
        bottom_right = self.transform.canvas_to_image(
            dirty_rect.right() + 1 + margin,
            dirty_rect.bottom() + 1 + margin,
        )
        start_x = max(0, floor(min(top_left[0], bottom_right[0])) - 1)
        end_x = min(
            self.transform.image_width,
            ceil(max(top_left[0], bottom_right[0])) + 1,
        )
        start_y = max(0, floor(min(top_left[1], bottom_right[1])) - 1)
        end_y = min(
            self.transform.image_height,
            ceil(max(top_left[1], bottom_right[1])) + 1,
        )
        image_left, image_top = self.transform.image_to_canvas(0, 0)
        image_right, image_bottom = self.transform.image_to_canvas(
            self.transform.image_width,
            self.transform.image_height,
        )
        paint_left = max(float(dirty_rect.left()) - margin, image_left)
        paint_right = min(float(dirty_rect.right() + 1) + margin, image_right)
        paint_top = max(float(dirty_rect.top()) - margin, image_top)
        paint_bottom = min(float(dirty_rect.bottom() + 1) + margin, image_bottom)
        if paint_left >= paint_right or paint_top >= paint_bottom:
            return
        pen = QPen(QColor(20, 20, 20, 105))
        pen.setWidthF(self.transform.grid_line_width_logical)
        painter.setPen(pen)
        for column in range(start_x, end_x + 1):
            x, _ = self.transform.image_to_canvas(column, 0)
            painter.drawLine(QPointF(x, paint_top), QPointF(x, paint_bottom))
        for row in range(start_y, end_y + 1):
            _, y = self.transform.image_to_canvas(0, row)
            painter.drawLine(QPointF(paint_left, y), QPointF(paint_right, y))

    def _paint_warning_boxes(self, painter: QPainter) -> None:
        if not self.ternary_visible or not self.warning_visible or not self._warning_boxes:
            return
        pen = QPen(QColor(255, 70, 20, 235))
        pen.setWidthF(self.transform.warning_line_width_logical)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for left, top, right, bottom in self._warning_boxes:
            x1, y1 = self.transform.image_to_canvas(left, top)
            x2, y2 = self.transform.image_to_canvas(right, bottom)
            painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

    def _paint_protected_region(self, painter: QPainter) -> None:
        protected_start = protected_start_y(self.transform.image_height)
        if protected_start >= self.transform.image_height:
            return
        left, top = self.transform.image_to_canvas(0, protected_start)
        right, bottom = self.transform.image_to_canvas(
            self.transform.image_width,
            self.transform.image_height,
        )
        painter.fillRect(QRectF(left, top, right - left, bottom - top), QColor(255, 60, 40, 34))
        pen = QPen(QColor(255, 100, 70, 235))
        pen.setWidthF(2.0 / self.transform.device_pixel_ratio)
        painter.setPen(pen)
        painter.drawLine(QPointF(left, top), QPointF(right, top))

    def _paint_outer_border(self, painter: QPainter) -> None:
        x1, y1 = self.transform.image_to_canvas(0, 0)
        x2, y2 = self.transform.image_to_canvas(
            self.transform.image_width,
            self.transform.image_height,
        )
        pen = QPen(QColor(245, 245, 245, 230))
        pen.setWidthF(2.0 / self.transform.device_pixel_ratio)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

    def _paint_memo(self, painter: QPainter) -> None:
        """表示層・警告・外枠より上へ、保存対象外メモを独立合成する。"""

        if self._memo_image is None or not self.has_memo:
            return
        painter.save()
        painter.translate(self.transform.origin_x, self.transform.origin_y)
        painter.scale(self.transform.scale, self.transform.scale)
        painter.setClipRect(
            QRectF(0, 0, self.transform.image_width, self.transform.image_height)
        )
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            self.transform.scale < 1.0,
        )
        painter.setOpacity(1.0)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(0, 0, self._memo_image)
        painter.restore()

    def _paint_pointer(self, painter: QPainter) -> None:
        if self._cursor_canvas is None or self._cursor_image is None:
            return
        if self._memo_drawing:
            center = self._cursor_canvas
            painter.setBrush(QColor(255, 214, 64, 235))
            pen = QPen(QColor(25, 25, 25, 245))
            pen.setWidthF(2.0 / self.transform.device_pixel_ratio)
            painter.setPen(pen)
            painter.drawEllipse(center, 4.0, 4.0)
            return
        if not self.ternary_visible:
            return
        if self._cursor_protected:
            pen = QPen(QColor(255, 70, 70, 245))
            pen.setWidthF(2.0 / self.transform.device_pixel_ratio)
            painter.setPen(pen)
            center = self._cursor_canvas
            painter.drawLine(center + QPointF(-7, -7), center + QPointF(7, 7))
            painter.drawLine(center + QPointF(-7, 7), center + QPointF(7, -7))
            return
        if self.tool == EditTool.FILL:
            pen = QPen(QColor(255, 255, 255, 230))
            pen.setWidthF(1.0 / self.transform.device_pixel_ratio)
            painter.setPen(pen)
            center = self._cursor_canvas
            painter.drawLine(center + QPointF(-6, 0), center + QPointF(6, 0))
            painter.drawLine(center + QPointF(0, -6), center + QPointF(0, 6))
            return
        editable = self.editing_enabled and self.transform.brush_is_editable(self.brush_diameter)
        pointer_key = (
            self.brush_diameter,
            self.brush_shape.value,
            self.selected_label,
            not editable,
        )
        if self._brush_pointer_key != pointer_key or self._brush_pointer_image is None:
            mask = brush_shape_mask(self.brush_diameter, self.brush_shape.value)
            self._brush_pointer_image = qimage_from_brush_mask(
                mask,
                color=SAVE_RGB[self.selected_label],
                blocked=not editable,
            )
            self._brush_pointer_key = pointer_key
        assert self._brush_pointer_image is not None
        anchor_x = floor(self._cursor_image[0])
        anchor_y = floor(self._cursor_image[1])
        offset = -((self.brush_diameter - 1) // 2)
        painter.save()
        painter.translate(self.transform.origin_x, self.transform.origin_y)
        painter.scale(self.transform.scale, self.transform.scale)
        painter.setClipRect(
            QRectF(
                0,
                0,
                self.transform.image_width,
                protected_start_y(self.transform.image_height),
            )
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setOpacity(1.0)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(anchor_x + offset, anchor_y + offset, self._brush_pointer_image)
        painter.restore()

    def _update_pointer(self, position: QPointF) -> None:
        self._sync_device_pixel_ratio()
        if not self.has_image:
            self._clear_pointer()
            return
        old_pointer_rect = self._pointer_repaint_rect()
        self._cursor_canvas = position
        self._remap_pointer(old_pointer_rect=old_pointer_rect)
        self._finish_brush_if_uneditable()

    def _remap_pointer(self, *, old_pointer_rect: QRect | None = None) -> None:
        """現在の表示変換に対して静止中の指示位置を写像し直す。"""

        if not self.has_image or self._cursor_canvas is None:
            if not self.has_image:
                self._clear_pointer()
            return
        position = self._cursor_canvas
        image_position = self.transform.canvas_to_image(position.x(), position.y())
        pixel = self.transform.canvas_to_pixel(position.x(), position.y())
        if pixel is None:
            self._cursor_image = None
            self._set_cursor_protected(False)
            self.cursor_position_changed.emit(None)
        else:
            self._cursor_image = image_position
            self._set_cursor_protected(pixel[1] >= protected_start_y(self.transform.image_height))
            self.cursor_position_changed.emit(pixel)
        previous = self._pointer_repaint_rect() if old_pointer_rect is None else old_pointer_rect
        current = self._pointer_repaint_rect()
        if not previous.isEmpty():
            self.update(previous)
        if not current.isEmpty() and current != previous:
            self.update(current)

    def _clear_pointer(self) -> None:
        dirty = self._pointer_repaint_rect()
        had_pointer = self._cursor_canvas is not None or self._cursor_image is not None
        self._cursor_canvas = None
        self._cursor_image = None
        self._set_cursor_protected(False)
        if had_pointer:
            self.cursor_position_changed.emit(None)
        if not dirty.isEmpty():
            self.update(dirty)

    def _canvas_rect_for_image_bbox(self, bbox: BoundingBox) -> QRect:
        left, top, right, bottom = bbox
        x1, y1 = self.transform.image_to_canvas(left, top)
        x2, y2 = self.transform.image_to_canvas(right, bottom)
        rect = QRectF(
            min(x1, x2),
            min(y1, y2),
            abs(x2 - x1),
            abs(y2 - y1),
        ).toAlignedRect()
        return rect.adjusted(-2, -2, 2, 2).intersected(self.rect())

    def _pointer_repaint_rect(self) -> QRect:
        if self._cursor_canvas is None or self._cursor_image is None:
            return QRect()
        if self._memo_drawing:
            center = self._cursor_canvas
            return (
                QRectF(center.x() - 7.0, center.y() - 7.0, 14.0, 14.0)
                .toAlignedRect()
                .intersected(self.rect())
            )
        if not self.ternary_visible:
            return QRect()
        if self._cursor_protected or self.tool == EditTool.FILL:
            center = self._cursor_canvas
            return (
                QRectF(center.x() - 9.0, center.y() - 9.0, 18.0, 18.0)
                .toAlignedRect()
                .intersected(self.rect())
            )

        anchor_x = floor(self._cursor_image[0])
        anchor_y = floor(self._cursor_image[1])
        offset = -((self.brush_diameter - 1) // 2)
        bbox = (
            anchor_x + offset,
            anchor_y + offset,
            anchor_x + offset + self.brush_diameter,
            anchor_y + offset + self.brush_diameter,
        )
        return self._canvas_rect_for_image_bbox(bbox)

    def _set_cursor_protected(self, protected: bool) -> None:
        state = bool(protected)
        if state == self._cursor_protected:
            self._refresh_cursor_shape()
            return
        self._cursor_protected = state
        self.protected_cursor_changed.emit(state)
        self._refresh_cursor_shape()

    def _refresh_cursor_shape(self) -> None:
        if self._panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._memo_drawing:
            self.setCursor(Qt.CursorShape.BlankCursor)
        elif self._space_pressed:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif (
            self._cursor_canvas is not None
            and self._cursor_image is not None
            and (self.ternary_visible or self._memo_drawing)
        ):
            # 画像内では筆・塗り潰し・保護の独自表示が指示位置を担う。
            self.setCursor(Qt.CursorShape.BlankCursor)
        else:
            self.unsetCursor()

    def _sync_device_pixel_ratio(self) -> None:
        ratio = max(self.devicePixelRatioF(), 1.0)
        if isclose(ratio, self.transform.device_pixel_ratio, rel_tol=0.0, abs_tol=1e-9):
            return
        if self._brushing:
            self.cancel_brush("DPI変更により筆操作を取り消した")
        if self._memo_drawing:
            self.cancel_memo_stroke("DPI変更によりメモ入力を取り消した")
        self.transform.set_viewport(self.width(), self.height(), dpr=ratio)
        self._remap_pointer()
        self._finish_brush_if_uneditable()

    def _view_change_is_blocked(self) -> bool:
        if not self._brushing and not self._memo_drawing:
            return False
        operation = "メモ" if self._memo_drawing else "筆"
        self.interaction_blocked.emit(f"{operation}を放して操作を確定してから倍率を変更せよ")
        return True

    def _finish_brush_if_uneditable(self) -> None:
        if not self._brushing or self.transform.brush_is_editable(self.brush_diameter):
            return
        self.cancel_brush("表示上の筆径が4実画面画素未満になったため筆操作を取り消した")
        self.interaction_blocked.emit("表示上の筆径が4実画面画素未満になったため筆操作を取り消した")

    def _reset_memo_layer(self, width: int | None, height: int | None) -> None:
        self._abandon_memo_stroke()
        self._pending_label_memo_patches = None
        self._memo_nontransparent_pixels = 0
        self._memo_image = None

    def _ensure_memo_image(self) -> QImage:
        """必要になるまで原解像度RGBAメモ像を確保しない。"""

        if self.labels is None:
            raise RuntimeError("メモ画像の確保先がない")
        height, width = self.labels.shape
        image = self._memo_image
        if image is not None:
            if image.width() != width or image.height() != height:
                raise RuntimeError("メモ画像の寸法が現在画像と一致しない")
            return image
        image = QImage(width, height, QImage.Format.Format_RGBA8888)
        if image.isNull():
            raise RuntimeError("メモ画像を確保できない")
        image.fill(Qt.GlobalColor.transparent)
        self._memo_image = image
        return image

    def _release_empty_memo_image(self) -> None:
        """不透明画素を持たない遅延像を解放する。"""

        if self._memo_nontransparent_pixels == 0 and not self._memo_drawing:
            self._memo_image = None

    def _memo_rgba_view(self) -> UInt8Array:
        image = self._memo_image
        if image is None:
            raise RuntimeError("メモ画像がない")
        expected_stride = image.width() * 4
        if image.bytesPerLine() != expected_stride:
            raise RuntimeError("メモ画像の行幅がRGBA8888連続配置ではない")
        return np.frombuffer(image.bits(), dtype=np.uint8).reshape(
            image.height(),
            image.width(),
            4,
        )

    def _begin_memo_stroke(self, image_position: tuple[float, float]) -> None:
        if self.labels is None:
            return
        try:
            self._ensure_memo_image()
        except (MemoryError, RuntimeError):
            self.interaction_blocked.emit("メモ画像の作業領域を確保できない")
            return
        old_pointer_rect = self._pointer_repaint_rect()
        self._memo_drawing = True
        self._memo_last_image_position = image_position
        self._memo_stroke_touched = set()
        self._memo_stroke_before = []
        self.memo_stroke_active_changed.emit(True)
        self._refresh_cursor_shape()
        current_pointer_rect = self._pointer_repaint_rect()
        if not old_pointer_rect.isEmpty():
            self.update(old_pointer_rect)
        if not current_pointer_rect.isEmpty():
            self.update(current_pointer_rect)
        try:
            self._draw_memo_segment(image_position, image_position)
        except Exception:
            self.cancel_memo_stroke("メモ開始中の例外により一筆を取り消した")
            raise

    def _draw_memo_segment(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> None:
        image = self._memo_image
        touched = self._memo_stroke_touched
        if image is None or touched is None:
            raise RuntimeError("メモ一筆が開始されていない")
        scale = max(self.transform.scale, 1e-9)
        outline_width = max(1.0, 7.0 / scale)
        inner_width = max(1.0, 3.0 / scale)
        margin = int(ceil(outline_width / 2.0)) + 2
        left = max(0, floor(min(start[0], end[0])) - margin)
        top = max(0, floor(min(start[1], end[1])) - margin)
        right = min(image.width(), ceil(max(start[0], end[0])) + margin + 1)
        bottom = min(image.height(), ceil(max(start[1], end[1])) + margin + 1)
        if left >= right or top >= bottom:
            return

        before = self._memo_rgba_view()[top:bottom, left:right].copy()
        is_point = start == end
        point = QPointF(*start)
        painter = QPainter(image)
        if not painter.isActive():
            raise RuntimeError("メモ描画を開始できない")
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            outline = QPen(QColor(25, 25, 25, 245))
            outline.setWidthF(outline_width)
            outline.setCapStyle(Qt.PenCapStyle.RoundCap)
            outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(outline)
            if is_point:
                painter.drawPoint(point)
            else:
                painter.drawLine(QPointF(*start), QPointF(*end))
            inner = QPen(QColor(255, 214, 64, 245))
            inner.setWidthF(inner_width)
            inner.setCapStyle(Qt.PenCapStyle.RoundCap)
            inner.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(inner)
            if is_point:
                painter.drawPoint(point)
            else:
                painter.drawLine(QPointF(*start), QPointF(*end))
        finally:
            painter.end()

        after = self._memo_rgba_view()[top:bottom, left:right]
        self._memo_nontransparent_pixels += int(
            np.count_nonzero(after[..., 3]) - np.count_nonzero(before[..., 3])
        )
        changed = np.any(before != after, axis=2)
        if not changed.any():
            return
        rows, columns = np.nonzero(changed)
        width = image.width()
        indices = (
            (rows.astype(np.uint64) + top) * width
            + columns.astype(np.uint64)
            + left
        ).astype(np.uint32)
        first_change = np.fromiter(
            (int(index) not in touched for index in indices),
            dtype=np.bool_,
            count=indices.size,
        )
        if first_change.any():
            first_rows = rows[first_change]
            first_columns = columns[first_change]
            first_indices = indices[first_change].astype(np.uint32, copy=True)
            self._memo_stroke_before.append(
                (
                    first_indices,
                    before[first_rows, first_columns].astype(np.uint8, copy=True),
                )
            )
            touched.update(map(int, first_indices))
        self._update_memo_bbox(
            (
                left + int(columns.min()),
                top + int(rows.min()),
                left + int(columns.max()) + 1,
                top + int(rows.max()) + 1,
            )
        )

    def _abandon_memo_stroke(self) -> None:
        was_active = self._memo_drawing
        old_pointer_rect = self._pointer_repaint_rect()
        self._memo_drawing = False
        self._memo_last_image_position = None
        self._memo_stroke_touched = None
        self._memo_stroke_before = []
        if was_active:
            self.memo_stroke_active_changed.emit(False)
        self._refresh_cursor_shape()
        current_pointer_rect = self._pointer_repaint_rect()
        if not old_pointer_rect.isEmpty():
            self.update(old_pointer_rect)
        if not current_pointer_rect.isEmpty() and current_pointer_rect != old_pointer_rect:
            self.update(current_pointer_rect)

    def _erase_memo_mask(
        self,
        bbox: BoundingBox,
        mask: BoolArray,
    ) -> MemoPixelPatch | None:
        image = self._memo_image
        if image is None or self._memo_nontransparent_pixels == 0:
            return None
        left, top, right, bottom = bbox
        if mask.dtype != np.bool_ or mask.shape != (bottom - top, right - left):
            raise ValueError("メモ消去maskが対象矩形と一致しない")
        rgba = self._memo_rgba_view()
        region = rgba[top:bottom, left:right]
        affected = mask & (region[..., 3] != 0)
        if not affected.any():
            return None
        rows, columns = np.nonzero(affected)
        indices = (
            (rows.astype(np.uint64) + top) * image.width()
            + columns.astype(np.uint64)
            + left
        ).astype(np.uint32)
        flat = rgba.reshape(-1, 4)
        before = flat[indices].astype(np.uint8, copy=True)
        after = np.zeros((indices.size, 4), dtype=np.uint8)
        flat[indices] = after
        self._memo_nontransparent_pixels -= int(indices.size)
        self._update_memo_bbox(
            (
                left + int(columns.min()),
                top + int(rows.min()),
                left + int(columns.max()) + 1,
                top + int(rows.max()) + 1,
            )
        )
        patch = MemoPixelPatch(indices, before, after)
        self._release_empty_memo_image()
        return patch

    def _update_memo_indices(self, groups: list[NDArray[np.uint32]]) -> None:
        if self._memo_image is None:
            return
        width = self._memo_image.width()
        left = width
        top = self._memo_image.height()
        right = 0
        bottom = 0
        for group in groups:
            if group.size == 0:
                continue
            values = group.astype(np.int64, copy=False)
            columns = values % width
            rows = values // width
            left = min(left, int(columns.min()))
            top = min(top, int(rows.min()))
            right = max(right, int(columns.max()) + 1)
            bottom = max(bottom, int(rows.max()) + 1)
        if left < right and top < bottom:
            self._update_memo_bbox((left, top, right, bottom))

    def _update_memo_bbox(self, bbox: BoundingBox) -> None:
        dirty_rect = self._canvas_rect_for_image_bbox(bbox)
        if not dirty_rect.isEmpty():
            self.update(dirty_rect)

    @staticmethod
    def _validate_image_pair(original_rgb: UInt8Array, labels: UInt8Array) -> None:
        if labels.ndim != 2 or labels.dtype != np.uint8:
            raise ValueError("ラベルはuint8二次元配列でなければならない")
        if original_rgb.dtype != np.uint8 or original_rgb.shape != (*labels.shape, 3):
            raise ValueError("原画像はラベルと同寸法のuint8 RGBでなければならない")
        if np.any(labels > 2):
            raise ValueError("ラベル値は0/1/2だけでなければならない")
