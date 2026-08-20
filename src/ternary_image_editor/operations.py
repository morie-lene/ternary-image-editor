"""三値ラベル配列に対する副作用のない画像演算。"""

from __future__ import annotations

import operator
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage

from .constants import (
    BRUSH_THRESHOLD_DEVICE_PX,
    DEFAULT_PSEUDO_RGB,
    MAX_BOUNDARY_THICKNESS,
    MAX_BRUSH_DIAMETER,
    MIN_BOUNDARY_THICKNESS,
    MIN_BRUSH_DIAMETER,
    SAVE_RGB,
    SMALL_COMPONENT_MAX_AREA,
    Label,
    protected_start_y,
)

BrushShape: TypeAlias = Literal["circle", "square"]
BoundingBox: TypeAlias = tuple[int, int, int, int]

_FOUR_CONNECTED = ndimage.generate_binary_structure(2, 1)
_EIGHT_CONNECTED = ndimage.generate_binary_structure(2, 2)


@dataclass(frozen=True, slots=True)
class SmallComponent:
    """一つの色別小領域。

    ``bbox`` は ``(left, top, right, bottom)`` の半開矩形である。
    """

    label: Label
    area: int
    bbox: BoundingBox


@dataclass(frozen=True, slots=True)
class SmallComponentsResult:
    """色別小領域検出の表示用結果。"""

    mask: NDArray[np.bool_]
    components: tuple[SmallComponent, ...]

    @property
    def count(self) -> int:
        return len(self.components)

    @property
    def present_count(self) -> int:
        """「有」の対象成分数。"""

        return sum(component.label is Label.PRESENT for component in self.components)

    @property
    def boundary_count(self) -> int:
        """「境界」の対象成分数。"""

        return sum(component.label is Label.BOUNDARY for component in self.components)

    def count_for(self, label: int | Label) -> int:
        """指定ラベルの対象成分数。``無`` は常に0。"""

        selected = Label(_validated_label(label, name="label"))
        if selected is Label.NONE:
            return 0
        return sum(component.label is selected for component in self.components)

    @property
    def bboxes(self) -> tuple[BoundingBox, ...]:
        return tuple(component.bbox for component in self.components)


@dataclass(frozen=True, slots=True)
class BrushSegmentFootprint:
    """一つの増分筆区間が占める局所maskと半開矩形。"""

    bbox: BoundingBox
    mask: NDArray[np.bool_]

    def __post_init__(self) -> None:
        left, top, right, bottom = self.bbox
        if left < 0 or top < 0 or left >= right or top >= bottom:
            raise ValueError("筆跡矩形は非負の非空半開矩形でなければならない")
        if self.mask.dtype != np.bool_ or self.mask.shape != (bottom - top, right - left):
            raise ValueError("筆跡maskの寸法が筆跡矩形と一致しない")


def validate_labels(labels: NDArray[np.uint8], *, name: str = "labels") -> None:
    """内部ラベル配列の形、型、値域を検証する。"""

    if not isinstance(labels, np.ndarray):
        raise TypeError(f"{name} must be a numpy.ndarray")
    if labels.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional array")
    if 0 in labels.shape:
        raise ValueError(f"{name} must not be empty")
    if labels.dtype != np.uint8:
        raise TypeError(f"{name} must have dtype uint8")
    if int(labels.max()) > int(Label.BOUNDARY):
        raise ValueError(f"{name} contains a value outside 0, 1, 2")


def labels_to_rgb(
    labels: NDArray[np.uint8],
    palette: Sequence[Sequence[int]] = SAVE_RGB,
) -> NDArray[np.uint8]:
    """ラベル0/1/2を指定された三色のRGB表示像へ写像する。"""

    validate_labels(labels)
    palette_array = _validated_palette(palette)
    return palette_array[labels]


def pseudocolorize(
    labels: NDArray[np.uint8],
    palette: Sequence[Sequence[int]] = DEFAULT_PSEUDO_RGB,
) -> NDArray[np.uint8]:
    """ラベルを表示専用の疑似色へ写像する。"""

    return labels_to_rgb(labels, palette)


def gimp_lighten_composite(
    ternary_rgb: NDArray[np.uint8],
    original_rgb: NDArray[np.uint8],
    alpha: float,
) -> NDArray[np.uint8]:
    """仕様7.2のGIMP互換「比較（明）」表示を計算する。"""

    base, overlay = _validated_rgb_pair(ternary_rgb, original_rgb)
    opacity = _validated_alpha(alpha)
    lighten = np.maximum(base, overlay)
    return _rounded_rgb((1.0 - opacity) * base + opacity * lighten)


def alpha_composite(
    base_rgb: NDArray[np.uint8],
    overlay_rgb: NDArray[np.uint8],
    alpha: float,
) -> NDArray[np.uint8]:
    """不透明な基底へ不透明度一定の上層RGB像を通常合成する。"""

    base, overlay = _validated_rgb_pair(base_rgb, overlay_rgb)
    opacity = _validated_alpha(alpha)
    return _rounded_rgb((1.0 - opacity) * base + opacity * overlay)


def brush_editable(
    diameter: int,
    display_scale: float,
    device_pixel_ratio: float,
) -> bool:
    """画面上の筆径が編集許可閾値以上かを返す。"""

    brush_diameter = _validated_integer(
        diameter,
        name="diameter",
        minimum=MIN_BRUSH_DIAMETER,
        maximum=MAX_BRUSH_DIAMETER,
    )
    scale = _validated_positive_float(display_scale, name="display_scale")
    pixel_ratio = _validated_positive_float(
        device_pixel_ratio,
        name="device_pixel_ratio",
    )
    return brush_diameter * scale * pixel_ratio >= BRUSH_THRESHOLD_DEVICE_PX


def brush_footprint_mask(
    image_shape: tuple[int, int],
    center: tuple[float, float],
    diameter: int,
    brush_shape: BrushShape = "circle",
) -> NDArray[np.bool_]:
    """ポインタ下画素を基準に、一つの離散D×D筆maskを返す。

    座標は ``(x, y)``。偶数径ではポインタ下画素を中央四画素の左上側とし、
    余剰画素を+x/+y側へ配する。
    """

    height, width = _validated_image_shape(image_shape)
    point = _validated_point(center, name="center")
    brush_diameter = _validated_integer(
        diameter,
        name="diameter",
        minimum=MIN_BRUSH_DIAMETER,
        maximum=MAX_BRUSH_DIAMETER,
    )
    shape = _validated_brush_shape(brush_shape)
    result = np.zeros((height, width), dtype=np.bool_)
    _add_discrete_stamp(result, _point_to_anchor(point), brush_diameter, shape)
    _exclude_protected_rows(result)
    return result


def brush_shape_mask(
    diameter: int,
    brush_shape: BrushShape = "circle",
) -> NDArray[np.bool_]:
    """画面予告と実編集で共有するD×D離散筆maskを返す。"""

    brush_diameter = _validated_integer(
        diameter,
        name="diameter",
        minimum=MIN_BRUSH_DIAMETER,
        maximum=MAX_BRUSH_DIAMETER,
    )
    shape = _validated_brush_shape(brush_shape)
    if shape == "square":
        return np.ones((brush_diameter, brush_diameter), dtype=np.bool_)

    radius = brush_diameter / 2.0
    coordinate = np.arange(brush_diameter, dtype=np.float64) + 0.5 - radius
    normalized_x = coordinate[None, :] / radius
    normalized_y = coordinate[:, None] / radius
    value = normalized_x * normalized_x + normalized_y * normalized_y
    return (value < 1.0) | np.isclose(value, 1.0, rtol=1e-12, atol=1e-12)


def stroke_mask(
    image_shape: tuple[int, int],
    points: Iterable[tuple[float, float]] | tuple[float, float],
    diameter: int,
    brush_shape: BrushShape = "circle",
) -> NDArray[np.bool_]:
    """補間済みの連続筆跡maskを返す。

    最初の点が画像矩形外なら筆操作全体を無効とする。画像内開始後の線分は
    画像矩形で切り詰められ、再進入部分も同じ連続筆跡として扱う。
    """

    height, width = _validated_image_shape(image_shape)
    stroke_points = _validated_points(points)
    brush_diameter = _validated_integer(
        diameter,
        name="diameter",
        minimum=MIN_BRUSH_DIAMETER,
        maximum=MAX_BRUSH_DIAMETER,
    )
    shape = _validated_brush_shape(brush_shape)
    result = np.zeros((height, width), dtype=np.bool_)
    if len(stroke_points) == 0:
        return result

    start_x, start_y = stroke_points[0]
    if not (0.0 <= start_x < width and 0.0 <= start_y < height):
        return result

    start_anchor = _point_to_anchor(stroke_points[0])
    if start_anchor[1] >= protected_start_y(height):
        return result
    if len(stroke_points) == 1:
        _add_discrete_stamp(result, start_anchor, brush_diameter, shape)
        _exclude_protected_rows(result)
        return result

    for start, end in zip(stroke_points[:-1], stroke_points[1:], strict=True):
        _add_discrete_segment(
            result,
            _point_to_anchor(start),
            _point_to_anchor(end),
            brush_diameter,
            shape,
        )
    _exclude_protected_rows(result)
    return result


def paint_brush(
    labels: NDArray[np.uint8],
    points: Iterable[tuple[float, float]] | tuple[float, float],
    new_label: int | Label,
    diameter: int,
    brush_shape: BrushShape = "circle",
) -> NDArray[np.uint8]:
    """一つの筆操作を複製したラベル配列へ適用する。"""

    validate_labels(labels)
    replacement = _validated_label(new_label, name="new_label")
    result = labels.copy()
    mask = stroke_mask(labels.shape, points, diameter, brush_shape)
    result[mask] = replacement
    return _validated_label_output(result)


def paint_brush_increment(
    labels: NDArray[np.uint8],
    start: tuple[float, float],
    end: tuple[float, float] | None,
    new_label: int | Label,
    diameter: int,
    brush_shape: BrushShape = "circle",
) -> BoundingBox | None:
    """進行中の筆操作の一点または一区間を作業配列へ直接適用する。

    ``end`` が ``None`` なら開始点一つ、指定済みなら ``start`` から
    ``end`` までの線分だけを描く。筆操作全体が画像内で開始済みであることは
    呼出側の責任とし、画像外から再進入する一区間も画像矩形で切り詰める。
    実際に変更した時は変更画素を含む半開矩形を返し、無変更なら ``None``
    を返す。
    """

    footprint = brush_segment_footprint(
        labels.shape,
        start,
        end,
        diameter,
        brush_shape,
    )
    if footprint is None:
        return None
    return paint_brush_footprint(labels, footprint, new_label)


def brush_segment_footprint(
    image_shape: tuple[int, int],
    start: tuple[float, float],
    end: tuple[float, float] | None,
    diameter: int,
    brush_shape: BrushShape = "circle",
) -> BrushSegmentFootprint | None:
    """増分筆の幾何学的な局所maskを、ラベル変更の有無と独立に返す。"""

    shape_height, shape_width = _validated_image_shape(image_shape)
    start_point = _validated_point(start, name="start")
    end_point = None if end is None else _validated_point(end, name="end")
    brush_diameter = _validated_integer(
        diameter,
        name="diameter",
        minimum=MIN_BRUSH_DIAMETER,
        maximum=MAX_BRUSH_DIAMETER,
    )
    shape = _validated_brush_shape(brush_shape)

    start_anchor = _point_to_anchor(start_point)
    end_anchor = start_anchor if end_point is None else _point_to_anchor(end_point)
    roi = _brush_segment_roi(
        (shape_height, shape_width),
        start_anchor,
        end_anchor,
        brush_diameter,
    )
    if roi is None:
        return None

    left, top, right, bottom = roi
    mask = np.zeros((bottom - top, right - left), dtype=np.bool_)
    template = brush_shape_mask(brush_diameter, shape)
    if end_point is None:
        _add_template_stamp(
            mask,
            (start_anchor[0] - left, start_anchor[1] - top),
            template,
            protect_rows=False,
        )
    else:
        for anchor_x, anchor_y in _line_anchors(start_anchor, end_anchor):
            _add_template_stamp(
                mask,
                (anchor_x - left, anchor_y - top),
                template,
                protect_rows=False,
            )

    if not mask.any():
        return None
    return BrushSegmentFootprint(roi, mask)


def paint_brush_footprint(
    labels: NDArray[np.uint8],
    footprint: BrushSegmentFootprint,
    new_label: int | Label,
) -> BoundingBox | None:
    """計算済み局所筆跡をラベルへ適用し、実変更がある時だけ矩形を返す。"""

    validate_labels(labels)
    replacement = _validated_label(new_label, name="new_label")
    left, top, right, bottom = footprint.bbox
    height, width = labels.shape
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("筆跡矩形がラベル画像の範囲外")

    target = labels[top:bottom, left:right]
    changed = footprint.mask & (target != replacement)
    if not changed.any():
        return None
    target[changed] = replacement
    return footprint.bbox


def flood_fill4(
    labels: NDArray[np.uint8],
    seed: tuple[int, int],
    new_label: int | Label,
) -> NDArray[np.uint8]:
    """seedと同値の四近傍連結領域を複製配列上で置換する。

    ``seed`` は ``(x, y)``。画像外seedと同色置換はいずれも無変更copyを返す。
    """

    validate_labels(labels)
    seed_x, seed_y = _validated_pixel(seed)
    replacement = _validated_label(new_label, name="new_label")
    result = labels.copy()
    height, width = labels.shape
    if not (0 <= seed_x < width and 0 <= seed_y < height):
        return result
    if seed_y >= protected_start_y(height):
        return result

    source = int(labels[seed_y, seed_x])
    if source == replacement:
        return result

    seed_mask = np.zeros(labels.shape, dtype=np.bool_)
    seed_mask[seed_y, seed_x] = True
    connected = ndimage.binary_propagation(
        seed_mask,
        structure=_FOUR_CONNECTED,
        mask=(labels == source) & _editable_pixel_mask(labels.shape),
    )
    result[connected] = replacement
    return _validated_label_output(result)


def generate_boundary_none_side(
    labels: NDArray[np.uint8],
    thickness: int,
) -> NDArray[np.uint8]:
    """仕様10.2のモードAとして無側へ境界を生成する。"""

    validate_labels(labels)
    width = _validated_boundary_thickness(thickness)
    editable = _editable_pixel_mask(labels.shape)
    none = labels == Label.NONE
    present = labels == Label.PRESENT
    seed = none & editable & ndimage.binary_dilation(present, structure=_FOUR_CONNECTED)
    target = seed.copy()
    frontier = seed

    for _ in range(width - 1):
        frontier = (
            ndimage.binary_dilation(frontier, structure=_FOUR_CONNECTED) & none & editable & ~target
        )
        if not frontier.any():
            break
        target |= frontier

    result = labels.copy()
    result[target] = Label.BOUNDARY
    return _validated_label_output(result)


def generate_boundary_non_none_side(
    labels: NDArray[np.uint8],
    thickness: int,
) -> NDArray[np.uint8]:
    """仕様10.3のモードBとして非無側へ境界を生成する。"""

    validate_labels(labels)
    width = _validated_boundary_thickness(thickness)
    editable = _editable_pixel_mask(labels.shape)
    protected = ~editable
    none = (labels == Label.NONE) | protected
    result = labels.copy()
    if not none.any():
        return result

    non_none = (labels != Label.NONE) & editable
    target = np.zeros(labels.shape, dtype=np.bool_)
    frontier = none
    for _ in range(width):
        frontier = ndimage.binary_dilation(frontier, structure=_FOUR_CONNECTED) & non_none & ~target
        if not frontier.any():
            break
        target |= frontier

    result[target] = Label.BOUNDARY
    return _validated_label_output(result)


def find_small_components(
    labels: NDArray[np.uint8],
) -> SmallComponentsResult:
    """有と境界を別々に八近傍解析し、面積1～50の成分を返す。"""

    validate_labels(labels)
    result_mask = np.zeros(labels.shape, dtype=np.bool_)
    components: list[SmallComponent] = []

    for label in (Label.PRESENT, Label.BOUNDARY):
        component_ids, component_count = ndimage.label(
            (labels == label) & _editable_pixel_mask(labels.shape),
            structure=_EIGHT_CONNECTED,
        )
        if component_count == 0:
            continue

        areas = np.bincount(component_ids.ravel(), minlength=component_count + 1)
        selected_ids = np.flatnonzero((areas >= 1) & (areas <= SMALL_COMPONENT_MAX_AREA))
        selected_ids = selected_ids[selected_ids != 0]
        if len(selected_ids) == 0:
            continue

        selected_lookup = np.zeros(component_count + 1, dtype=np.bool_)
        selected_lookup[selected_ids] = True
        result_mask |= selected_lookup[component_ids]

        objects = ndimage.find_objects(component_ids)
        for component_id in selected_ids:
            slices = objects[int(component_id) - 1]
            if slices is None:  # pragma: no cover - scipy contract guard
                continue
            row_slice, column_slice = slices
            components.append(
                SmallComponent(
                    label=label,
                    area=int(areas[component_id]),
                    bbox=(
                        int(column_slice.start),
                        int(row_slice.start),
                        int(column_slice.stop),
                        int(row_slice.stop),
                    ),
                )
            )

    return SmallComponentsResult(mask=result_mask, components=tuple(components))


def _validated_palette(palette: Sequence[Sequence[int]]) -> NDArray[np.uint8]:
    array = np.asarray(palette)
    if array.shape != (3, 3):
        raise ValueError("palette must have shape (3, 3)")
    if not np.issubdtype(array.dtype, np.integer) or np.issubdtype(array.dtype, np.bool_):
        raise TypeError("palette entries must be integers")
    if np.any((array < 0) | (array > 255)):
        raise ValueError("palette entries must be between 0 and 255")
    return array.astype(np.uint8, copy=True)


def _validated_rgb_pair(
    first: NDArray[np.uint8],
    second: NDArray[np.uint8],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    _validate_rgb(first, name="first RGB image")
    _validate_rgb(second, name="second RGB image")
    if first.shape != second.shape:
        raise ValueError("RGB images must have the same shape")
    return first.astype(np.float64, copy=False), second.astype(np.float64, copy=False)


def _validate_rgb(image: NDArray[np.uint8], *, name: str) -> None:
    if not isinstance(image, np.ndarray):
        raise TypeError(f"{name} must be a numpy.ndarray")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"{name} must have shape (height, width, 3)")
    if image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError(f"{name} must not be empty")
    if image.dtype != np.uint8:
        raise TypeError(f"{name} must have dtype uint8")


def _validated_alpha(alpha: float) -> float:
    if isinstance(alpha, (bool, np.bool_)):
        raise TypeError("alpha must be a real number")
    try:
        value = float(alpha)
    except (TypeError, ValueError) as exc:
        raise TypeError("alpha must be a real number") from exc
    if not np.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("alpha must be finite and between 0 and 1")
    return value


def _rounded_rgb(values: NDArray[np.float64]) -> NDArray[np.uint8]:
    return np.clip(np.rint(values), 0, 255).astype(np.uint8)


def _validated_integer(
    value: int,
    *,
    name: str,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be an integer")
    try:
        integer = operator.index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be an integer") from exc
    if integer < minimum or (maximum is not None and integer > maximum):
        if maximum is None:
            raise ValueError(f"{name} must be at least {minimum}")
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return integer


def _validated_positive_float(value: float, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a real number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real number") from exc
    if not np.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero")
    return number


def _validated_image_shape(image_shape: tuple[int, int]) -> tuple[int, int]:
    if len(image_shape) != 2:
        raise ValueError("image_shape must contain height and width")
    height = _validated_integer(image_shape[0], name="height", minimum=1)
    width = _validated_integer(image_shape[1], name="width", minimum=1)
    return height, width


def _validated_point(point: tuple[float, float], *, name: str) -> NDArray[np.float64]:
    try:
        array = np.asarray(point, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must contain two real coordinates") from exc
    if array.shape != (2,):
        raise ValueError(f"{name} must have shape (2,)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} coordinates must be finite")
    return array


def _validated_points(
    points: Iterable[tuple[float, float]] | tuple[float, float],
) -> NDArray[np.float64]:
    if isinstance(points, np.ndarray):
        raw = points
    else:
        try:
            raw = tuple(points)
        except TypeError as exc:
            raise TypeError("points must be an iterable of coordinates") from exc
    if len(raw) == 0:
        return np.empty((0, 2), dtype=np.float64)
    try:
        array = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError("points must contain real coordinates") from exc
    if array.shape == (2,):
        array = array.reshape(1, 2)
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError("points must have shape (count, 2)")
    if not np.all(np.isfinite(array)):
        raise ValueError("point coordinates must be finite")
    return array


def _validated_brush_shape(brush_shape: str) -> BrushShape:
    if brush_shape not in ("circle", "square"):
        raise ValueError("brush_shape must be 'circle' or 'square'")
    return brush_shape


def _validated_pixel(pixel: tuple[int, int]) -> tuple[int, int]:
    if len(pixel) != 2:
        raise ValueError("seed must contain x and y")
    return (
        _unbounded_integer(pixel[0], name="seed x"),
        _unbounded_integer(pixel[1], name="seed y"),
    )


def _unbounded_integer(value: int, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be an integer")
    try:
        return operator.index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be an integer") from exc


def _validated_label(label: int | Label, *, name: str) -> int:
    return _validated_integer(
        label,
        name=name,
        minimum=int(Label.NONE),
        maximum=int(Label.BOUNDARY),
    )


def _validated_boundary_thickness(thickness: int) -> int:
    return _validated_integer(
        thickness,
        name="thickness",
        minimum=MIN_BOUNDARY_THICKNESS,
        maximum=MAX_BOUNDARY_THICKNESS,
    )


def _validated_label_output(labels: NDArray[np.uint8]) -> NDArray[np.uint8]:
    validate_labels(labels, name="output labels")
    return labels


def _editable_pixel_mask(image_shape: tuple[int, int]) -> NDArray[np.bool_]:
    height, width = image_shape
    editable = np.ones((height, width), dtype=np.bool_)
    start = protected_start_y(height)
    if start < height:
        editable[start:, :] = False
    return editable


def _exclude_protected_rows(mask: NDArray[np.bool_]) -> None:
    start = protected_start_y(int(mask.shape[0]))
    if start < mask.shape[0]:
        mask[start:, :] = False


def _point_to_anchor(point: NDArray[np.float64]) -> tuple[int, int]:
    """連続画像座標からポインタ下画素を一意に得る。"""

    return int(np.floor(point[0])), int(np.floor(point[1]))


def _add_discrete_stamp(
    result: NDArray[np.bool_],
    anchor: tuple[int, int],
    diameter: int,
    brush_shape: BrushShape,
) -> None:
    template = brush_shape_mask(diameter, brush_shape)
    _add_template_stamp(result, anchor, template)


def _add_template_stamp(
    result: NDArray[np.bool_],
    anchor: tuple[int, int],
    template: NDArray[np.bool_],
    *,
    protect_rows: bool = True,
) -> None:
    diameter = template.shape[0]
    offset = -((diameter - 1) // 2)
    left = anchor[0] + offset
    top = anchor[1] + offset
    right = left + diameter
    bottom = top + diameter
    height, width = result.shape

    clipped_left = max(left, 0)
    clipped_top = max(top, 0)
    clipped_right = min(right, width)
    editable_bottom = protected_start_y(height) if protect_rows else height
    clipped_bottom = min(bottom, height, editable_bottom)
    if clipped_left >= clipped_right or clipped_top >= clipped_bottom:
        return

    template_left = clipped_left - left
    template_top = clipped_top - top
    template_right = template_left + clipped_right - clipped_left
    template_bottom = template_top + clipped_bottom - clipped_top
    result[clipped_top:clipped_bottom, clipped_left:clipped_right] |= template[
        template_top:template_bottom,
        template_left:template_right,
    ]


def _brush_segment_roi(
    image_shape: tuple[int, int],
    start: tuple[int, int],
    end: tuple[int, int],
    diameter: int,
) -> BoundingBox | None:
    """一点または線分の離散筆外接矩形を編集可能範囲へ切り詰める。"""

    height, width = image_shape
    offset = -((diameter - 1) // 2)
    left = max(0, min(start[0], end[0]) + offset)
    top = max(0, min(start[1], end[1]) + offset)
    right = min(width, max(start[0], end[0]) + offset + diameter)
    bottom = min(
        protected_start_y(height),
        max(start[1], end[1]) + offset + diameter,
    )
    if left >= right or top >= bottom:
        return None
    return left, top, right, bottom


def _add_discrete_segment(
    result: NDArray[np.bool_],
    start: tuple[int, int],
    end: tuple[int, int],
    diameter: int,
    brush_shape: BrushShape,
) -> None:
    template = brush_shape_mask(diameter, brush_shape)
    for anchor in _line_anchors(start, end):
        _add_template_stamp(result, anchor, template)


def _line_anchors(
    start: tuple[int, int],
    end: tuple[int, int],
) -> Iterable[tuple[int, int]]:
    """両端を含む整数Bresenham列。高速移動時もanchorを飛ばさない。"""

    x, y = start
    end_x, end_y = end
    delta_x = abs(end_x - x)
    delta_y = abs(end_y - y)
    step_x = 1 if x < end_x else -1
    step_y = 1 if y < end_y else -1
    error = delta_x - delta_y
    while True:
        yield x, y
        if x == end_x and y == end_y:
            return
        doubled = 2 * error
        if doubled > -delta_y:
            error -= delta_y
            x += step_x
        if doubled < delta_x:
            error += delta_x
            y += step_y


def _candidate_slices(
    image_shape: tuple[int, int],
    start: NDArray[np.float64],
    end: NDArray[np.float64],
    radius: float,
) -> tuple[slice, slice] | None:
    height, width = image_shape
    left = max(0, int(np.floor(min(start[0], end[0]) - radius)) - 1)
    right = min(width, int(np.ceil(max(start[0], end[0]) + radius)) + 1)
    top = max(0, int(np.floor(min(start[1], end[1]) - radius)) - 1)
    bottom = min(height, int(np.ceil(max(start[1], end[1]) + radius)) + 1)
    if left >= right or top >= bottom:
        return None
    return slice(top, bottom), slice(left, right)


def _add_point_footprint(
    result: NDArray[np.bool_],
    center: NDArray[np.float64],
    radius: float,
    brush_shape: BrushShape,
) -> None:
    slices = _candidate_slices(result.shape, center, center, radius)
    if slices is None:
        return
    row_slice, column_slice = slices
    pixel_x = np.arange(column_slice.start, column_slice.stop, dtype=np.float64) + 0.5
    pixel_y = np.arange(row_slice.start, row_slice.stop, dtype=np.float64)[:, None] + 0.5
    delta_x = pixel_x - center[0]
    delta_y = pixel_y - center[1]
    if brush_shape == "circle":
        distance_squared = delta_x * delta_x + delta_y * delta_y
        local_mask = _closed_circle_comparison(distance_squared, radius)
    else:
        local_mask = (
            (-radius <= delta_x) & (delta_x < radius) & (-radius <= delta_y) & (delta_y < radius)
        )
    result[row_slice, column_slice] |= local_mask


def _add_segment_footprint(
    result: NDArray[np.bool_],
    start: NDArray[np.float64],
    end: NDArray[np.float64],
    radius: float,
    brush_shape: BrushShape,
) -> None:
    difference = end - start
    if np.all(difference == 0.0):
        _add_point_footprint(result, start, radius, brush_shape)
        return
    slices = _candidate_slices(result.shape, start, end, radius)
    if slices is None:
        return
    row_slice, column_slice = slices
    pixel_x = np.arange(column_slice.start, column_slice.stop, dtype=np.float64)[None, :] + 0.5
    pixel_y = np.arange(row_slice.start, row_slice.stop, dtype=np.float64)[:, None] + 0.5

    if brush_shape == "circle":
        denominator = float(np.dot(difference, difference))
        parameter = (
            (pixel_x - start[0]) * difference[0] + (pixel_y - start[1]) * difference[1]
        ) / denominator
        parameter = np.clip(parameter, 0.0, 1.0)
        nearest_x = start[0] + parameter * difference[0]
        nearest_y = start[1] + parameter * difference[1]
        distance_squared = (pixel_x - nearest_x) ** 2 + (pixel_y - nearest_y) ** 2
        local_mask = _closed_circle_comparison(distance_squared, radius)
    else:
        local_mask = _square_segment_mask(
            pixel_x,
            pixel_y,
            start,
            difference,
            radius,
        )
    result[row_slice, column_slice] |= local_mask


def _square_segment_mask(
    pixel_x: NDArray[np.float64],
    pixel_y: NDArray[np.float64],
    start: NDArray[np.float64],
    difference: NDArray[np.float64],
    radius: float,
) -> NDArray[np.bool_]:
    shape = (pixel_y.shape[0], pixel_x.shape[1])
    lower = np.zeros(shape, dtype=np.float64)
    upper = np.ones(shape, dtype=np.float64)
    valid = np.ones(shape, dtype=np.bool_)

    for coordinate, origin, delta in (
        (pixel_x, start[0], difference[0]),
        (pixel_y, start[1], difference[1]),
    ):
        if delta == 0.0:
            valid &= (-radius <= coordinate - origin) & (coordinate - origin < radius)
            continue
        if delta > 0.0:
            dimension_lower = np.nextafter(
                (coordinate - radius - origin) / delta,
                np.inf,
            )
            dimension_upper = (coordinate + radius - origin) / delta
        else:
            dimension_lower = (coordinate + radius - origin) / delta
            dimension_upper = np.nextafter(
                (coordinate - radius - origin) / delta,
                -np.inf,
            )
        lower = np.maximum(lower, dimension_lower)
        upper = np.minimum(upper, dimension_upper)

    return valid & (lower <= upper)


def _closed_circle_comparison(
    distance_squared: NDArray[np.float64],
    radius: float,
) -> NDArray[np.bool_]:
    """閉じた円周を通常の浮動小数丸めだけで欠落させない。"""

    radius_squared = radius * radius
    return (distance_squared < radius_squared) | np.isclose(
        distance_squared,
        radius_squared,
        rtol=1e-12,
        atol=1e-12,
    )


__all__ = [
    "BoundingBox",
    "BrushSegmentFootprint",
    "BrushShape",
    "SmallComponent",
    "SmallComponentsResult",
    "alpha_composite",
    "brush_editable",
    "brush_footprint_mask",
    "brush_segment_footprint",
    "brush_shape_mask",
    "find_small_components",
    "flood_fill4",
    "generate_boundary_non_none_side",
    "generate_boundary_none_side",
    "gimp_lighten_composite",
    "labels_to_rgb",
    "paint_brush",
    "paint_brush_footprint",
    "paint_brush_increment",
    "pseudocolorize",
    "stroke_mask",
    "validate_labels",
]
