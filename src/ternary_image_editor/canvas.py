"""保存データ・表示像・操作overlayを分離した画像キャンバス。"""

from __future__ import annotations

from enum import StrEnum
from math import ceil, floor, isclose

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
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
    BOTTOM_PROTECTED_START_Y,
    DEFAULT_BRUSH_DIAMETER,
    DEFAULT_PSEUDO_RGB,
    SAVE_RGB,
)
from .operations import brush_shape_mask

UInt8Array = NDArray[np.uint8]
BoolArray = NDArray[np.bool_]
_PROTECTED_Y_START = BOTTOM_PROTECTED_START_Y


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

        self._ternary_visible = True
        self.original_visible = True
        self.original_opacity = 0.5
        self.pseudo_enabled = False
        self.pseudo_palette = DEFAULT_PSEUDO_RGB
        self.auto_grid_enabled = True
        self.warning_visible = False
        self.editing_enabled = True
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

    @property
    def has_image(self) -> bool:
        return self.labels is not None and self._label_image is not None

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
        if not same_dimensions:
            height, width = labels.shape
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

        if pressed and self._brushing:
            self.interaction_blocked.emit("筆操作中は一時パンへ切り替えられない")
            return
        self._space_pressed = bool(pressed)
        if self._panning:
            return
        self._refresh_cursor_shape()

    def cancel_navigation_input(self) -> None:
        """焦点・window活性喪失時に一時的なパン入力状態を破棄する。"""

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
        del event
        self._sync_device_pixel_ratio()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._paint_background(painter)
        if self.has_image:
            self._paint_image_layers(painter)
            self._paint_grid(painter)
            self._paint_protected_region(painter)
            self._paint_warning_boxes(painter)
            self._paint_outer_border(painter)
            self._paint_pointer(painter)
        painter.end()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        previous_scale = self.transform.scale
        if self._brushing:
            self.cancel_brush("ウィンドウ寸法変更により筆操作を取り消した")
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
        delta = event.angleDelta().y()
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
        if pixel[1] >= _PROTECTED_Y_START:
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
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
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
        elif event_type in {
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
        }:
            self.update()
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
                        QPainter.CompositionMode.CompositionMode_SourceOver
                        if self.pseudo_enabled
                        else QPainter.CompositionMode.CompositionMode_Lighten
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

    def _paint_background(self, painter: QPainter) -> None:
        tile = 20
        first = QColor(78, 82, 88)
        second = QColor(96, 100, 106)
        for y in range(0, self.height(), tile):
            for x in range(0, self.width(), tile):
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

    def _paint_grid(self, painter: QPainter) -> None:
        if not self.transform.grid_is_visible(auto_enabled=self.auto_grid_enabled):
            return
        top_left = self.transform.canvas_to_image(0, 0)
        bottom_right = self.transform.canvas_to_image(self.width(), self.height())
        start_x = max(0, floor(top_left[0]))
        end_x = min(self.transform.image_width, ceil(bottom_right[0]))
        start_y = max(0, floor(top_left[1]))
        end_y = min(self.transform.image_height, ceil(bottom_right[1]))
        pen = QPen(QColor(20, 20, 20, 105))
        pen.setWidthF(self.transform.grid_line_width_logical)
        painter.setPen(pen)
        for column in range(start_x, end_x + 1):
            x, _ = self.transform.image_to_canvas(column, 0)
            top = self.transform.image_to_canvas(0, start_y)[1]
            bottom = self.transform.image_to_canvas(0, end_y)[1]
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        for row in range(start_y, end_y + 1):
            _, y = self.transform.image_to_canvas(0, row)
            left = self.transform.image_to_canvas(start_x, 0)[0]
            right = self.transform.image_to_canvas(end_x, 0)[0]
            painter.drawLine(QPointF(left, y), QPointF(right, y))

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
        if self.transform.image_height <= _PROTECTED_Y_START:
            return
        left, top = self.transform.image_to_canvas(0, _PROTECTED_Y_START)
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

    def _paint_pointer(self, painter: QPainter) -> None:
        if self._cursor_canvas is None or self._cursor_image is None:
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
                min(self.transform.image_height, _PROTECTED_Y_START),
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
        self._cursor_canvas = position
        self._remap_pointer()
        self._finish_brush_if_uneditable()

    def _remap_pointer(self) -> None:
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
            self._set_cursor_protected(pixel[1] >= _PROTECTED_Y_START)
            self.cursor_position_changed.emit(pixel)
        self.update()

    def _clear_pointer(self) -> None:
        had_pointer = self._cursor_canvas is not None or self._cursor_image is not None
        self._cursor_canvas = None
        self._cursor_image = None
        self._set_cursor_protected(False)
        if had_pointer:
            self.cursor_position_changed.emit(None)
        self.update()

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
        elif self._cursor_protected:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        elif self._space_pressed:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def _sync_device_pixel_ratio(self) -> None:
        ratio = max(self.devicePixelRatioF(), 1.0)
        if isclose(ratio, self.transform.device_pixel_ratio, rel_tol=0.0, abs_tol=1e-9):
            return
        if self._brushing:
            self.cancel_brush("DPI変更により筆操作を取り消した")
        self.transform.set_viewport(self.width(), self.height(), dpr=ratio)
        self._remap_pointer()
        self._finish_brush_if_uneditable()

    def _view_change_is_blocked(self) -> bool:
        if not self._brushing:
            return False
        self.interaction_blocked.emit("筆を放して操作を確定してから倍率を変更せよ")
        return True

    def _finish_brush_if_uneditable(self) -> None:
        if not self._brushing or self.transform.brush_is_editable(self.brush_diameter):
            return
        self.cancel_brush("表示上の筆径が4実画面画素未満になったため筆操作を取り消した")
        self.interaction_blocked.emit("表示上の筆径が4実画面画素未満になったため筆操作を取り消した")

    @staticmethod
    def _validate_image_pair(original_rgb: UInt8Array, labels: UInt8Array) -> None:
        if labels.ndim != 2 or labels.dtype != np.uint8:
            raise ValueError("ラベルはuint8二次元配列でなければならない")
        if original_rgb.dtype != np.uint8 or original_rgb.shape != (*labels.shape, 3):
            raise ValueError("原画像はラベルと同寸法のuint8 RGBでなければならない")
        if np.any(labels > 2):
            raise ValueError("ラベル値は0/1/2だけでなければならない")
