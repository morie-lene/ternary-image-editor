"""Qt描画から分離した拡大・移動・座標変換。"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

from .constants import (
    BRUSH_THRESHOLD_DEVICE_PX,
    FIT_MARGIN_LOGICAL_PX,
    GRID_THRESHOLD_DEVICE_PX,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    MAX_ZOOM,
    MIN_ZOOM,
)


@dataclass(frozen=True, slots=True)
class FitResult:
    scale: float
    margin_preserved: bool
    fully_visible: bool


@dataclass(frozen=True, slots=True)
class ViewState:
    scale: float
    image_center_x: float
    image_center_y: float
    fit_mode: bool


class CanvasTransform:
    """論理座標だけで画像変換を保持する。

    `device_pixel_ratio` は格子・筆径等の実画面画素閾値にだけ使う。
    画像座標変換へ混ぜない。
    """

    def __init__(
        self,
        *,
        image_width: int = IMAGE_WIDTH,
        image_height: int = IMAGE_HEIGHT,
        viewport_width: float = 640.0,
        viewport_height: float = 480.0,
        scale: float = 1.0,
        device_pixel_ratio: float = 1.0,
    ) -> None:
        if image_width < 1 or image_height < 1:
            raise ValueError("画像寸法は正でなければならない")
        if viewport_width < 0 or viewport_height < 0:
            raise ValueError("表示領域寸法は負にできない")
        if device_pixel_ratio <= 0:
            raise ValueError("機器画素比は正でなければならない")
        self.image_width = image_width
        self.image_height = image_height
        self.viewport_width = float(viewport_width)
        self.viewport_height = float(viewport_height)
        self.scale = self._bounded_scale(scale)
        self.device_pixel_ratio = float(device_pixel_ratio)
        self.origin_x = (self.viewport_width - self.display_width) / 2.0
        self.origin_y = (self.viewport_height - self.display_height) / 2.0
        self.fit_mode = False
        self.clamp_origin()

    @property
    def display_width(self) -> float:
        return self.image_width * self.scale

    @property
    def display_height(self) -> float:
        return self.image_height * self.scale

    @property
    def physical_pixels_per_image_pixel(self) -> float:
        return self.scale * self.device_pixel_ratio

    @property
    def grid_line_width_logical(self) -> float:
        return 1.0 / self.device_pixel_ratio

    @property
    def warning_line_width_logical(self) -> float:
        return 2.0 / self.device_pixel_ratio

    def pan_bounds(self) -> tuple[float, float, float, float]:
        half_width = self.viewport_width / 2.0
        half_height = self.viewport_height / 2.0
        return (
            half_width - self.display_width,
            half_width,
            half_height - self.display_height,
            half_height,
        )

    def clamp_origin(self) -> None:
        min_x, max_x, min_y, max_y = self.pan_bounds()
        self.origin_x = min(max(self.origin_x, min_x), max_x)
        self.origin_y = min(max(self.origin_y, min_y), max_y)

    def set_viewport(self, width: float, height: float, *, dpr: float | None = None) -> None:
        if width < 0 or height < 0:
            raise ValueError("表示領域寸法は負にできない")
        if dpr is not None and dpr <= 0:
            raise ValueError("機器画素比は正でなければならない")
        center = self.center_image_coordinate()
        self.viewport_width = float(width)
        self.viewport_height = float(height)
        if dpr is not None:
            self.device_pixel_ratio = float(dpr)
        if self.fit_mode:
            self.fit_to_view()
            return
        self.center_on_image(*center)

    def fit_to_view(self) -> FitResult:
        available_width = self.viewport_width - 2.0 * FIT_MARGIN_LOGICAL_PX
        available_height = self.viewport_height - 2.0 * FIT_MARGIN_LOGICAL_PX
        margin_scale = min(
            available_width / self.image_width,
            available_height / self.image_height,
        )
        full_scale = min(
            self.viewport_width / self.image_width,
            self.viewport_height / self.image_height,
        )
        margin_preserved = margin_scale >= MIN_ZOOM
        candidate = margin_scale if margin_preserved else full_scale
        fully_visible = candidate >= MIN_ZOOM
        self.scale = MIN_ZOOM if candidate <= 0 else self._bounded_scale(candidate)
        self.origin_x = (self.viewport_width - self.display_width) / 2.0
        self.origin_y = (self.viewport_height - self.display_height) / 2.0
        self.fit_mode = True
        self.clamp_origin()
        return FitResult(
            scale=self.scale,
            margin_preserved=margin_preserved,
            fully_visible=fully_visible,
        )

    def set_actual_size(self) -> None:
        """100%を1画像画素=1論理画素として中央表示する。"""

        self.scale = 1.0
        self.fit_mode = False
        self.origin_x = (self.viewport_width - self.display_width) / 2.0
        self.origin_y = (self.viewport_height - self.display_height) / 2.0
        self.clamp_origin()

    def zoom_at(self, canvas_x: float, canvas_y: float, new_scale: float) -> float:
        image_x, image_y = self.canvas_to_image(canvas_x, canvas_y)
        self.scale = self._bounded_scale(new_scale)
        self.origin_x = canvas_x - image_x * self.scale
        self.origin_y = canvas_y - image_y * self.scale
        self.fit_mode = False
        self.clamp_origin()
        return self.scale

    def pan_by(self, delta_x: float, delta_y: float) -> None:
        self.origin_x += delta_x
        self.origin_y += delta_y
        self.fit_mode = False
        self.clamp_origin()

    def center_image_coordinate(self) -> tuple[float, float]:
        return self.canvas_to_image(
            self.viewport_width / 2.0,
            self.viewport_height / 2.0,
        )

    def center_on_image(self, image_x: float, image_y: float) -> None:
        self.origin_x = self.viewport_width / 2.0 - image_x * self.scale
        self.origin_y = self.viewport_height / 2.0 - image_y * self.scale
        self.clamp_origin()

    def capture_state(self) -> ViewState:
        center_x, center_y = self.center_image_coordinate()
        return ViewState(
            scale=self.scale,
            image_center_x=center_x,
            image_center_y=center_y,
            fit_mode=self.fit_mode,
        )

    def restore_state(self, state: ViewState) -> None:
        if state.fit_mode:
            self.fit_to_view()
            return
        self.scale = self._bounded_scale(state.scale)
        self.fit_mode = False
        self.center_on_image(state.image_center_x, state.image_center_y)

    def canvas_to_image(self, canvas_x: float, canvas_y: float) -> tuple[float, float]:
        return (
            (canvas_x - self.origin_x) / self.scale,
            (canvas_y - self.origin_y) / self.scale,
        )

    def canvas_to_pixel(self, canvas_x: float, canvas_y: float) -> tuple[int, int] | None:
        image_x, image_y = self.canvas_to_image(canvas_x, canvas_y)
        if not (0.0 <= image_x < self.image_width and 0.0 <= image_y < self.image_height):
            return None
        return floor(image_x), floor(image_y)

    def image_to_canvas(self, image_x: float, image_y: float) -> tuple[float, float]:
        return (
            self.origin_x + image_x * self.scale,
            self.origin_y + image_y * self.scale,
        )

    def grid_is_visible(self, *, auto_enabled: bool = True) -> bool:
        return auto_enabled and self.physical_pixels_per_image_pixel >= GRID_THRESHOLD_DEVICE_PX

    def brush_is_editable(self, diameter: int) -> bool:
        return diameter * self.physical_pixels_per_image_pixel >= BRUSH_THRESHOLD_DEVICE_PX

    @staticmethod
    def _bounded_scale(value: float) -> float:
        if value <= 0:
            raise ValueError("表示倍率は正でなければならない")
        return min(max(float(value), MIN_ZOOM), MAX_ZOOM)
