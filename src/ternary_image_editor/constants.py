"""アプリケーション全体で共有する値と小さな規則。"""

from __future__ import annotations

from enum import IntEnum

BOTTOM_PROTECTED_HEIGHT = 100


def protected_start_y(image_height: int) -> int:
    """画像高さに対する下端保護領域の開始行を返す。

    高さ100以下の画像を全域編集不能にしないため、その場合は空の保護領域とする。
    """

    if isinstance(image_height, bool) or not isinstance(image_height, int):
        raise TypeError("画像高さは整数でなければならない")
    if image_height < 1:
        raise ValueError("画像高さは正でなければならない")
    if image_height <= BOTTOM_PROTECTED_HEIGHT:
        return image_height
    return image_height - BOTTOM_PROTECTED_HEIGHT


class Label(IntEnum):
    """内部ラベル値。"""

    NONE = 0
    PRESENT = 1
    BOUNDARY = 2


LABEL_NAMES: dict[Label, str] = {
    Label.NONE: "無",
    Label.PRESENT: "有",
    Label.BOUNDARY: "境界",
}

SAVE_RGB: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),
    (128, 128, 128),
    (255, 255, 255),
)
DEFAULT_PSEUDO_RGB: tuple[tuple[int, int, int], ...] = (
    (0x20, 0x40, 0x60),
    (0xFF, 0x3B, 0x7A),
    (0xFF, 0xE6, 0x00),
)

ORIGINAL_PREFIX_GROUP = {"①": "001", "②": "002"}
TERNARY_PREFIX_GROUP = {"001": "001", "002": "002"}
ORIGINAL_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})
TERNARY_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})
TERNARY_JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg"})
PAIR_SUFFIX_LENGTH = 27

SRGB_TERNARY_QUANTIZATION_RULE = "srgb-nearest-black-gray-white-v1"
# 旧名は外部参照との互換用。入力JPEGと外部出力PNGで同じ規則を使う。
JPEG_QUANTIZATION_RULE = SRGB_TERNARY_QUANTIZATION_RULE

MIN_ZOOM = 0.05
MAX_ZOOM = 64.0
FIT_MARGIN_LOGICAL_PX = 32.0
GRID_THRESHOLD_DEVICE_PX = 8.0
BRUSH_THRESHOLD_DEVICE_PX = 4.0
MIN_BRUSH_DIAMETER = 1
MAX_BRUSH_DIAMETER = 512
DEFAULT_BRUSH_DIAMETER = 5
MIN_BOUNDARY_THICKNESS = 1
MAX_BOUNDARY_THICKNESS = 64
SMALL_COMPONENT_MAX_AREA = 50

MAX_HISTORY_OPERATIONS = 200
MAX_HISTORY_BYTES = 512 * 1024 * 1024
