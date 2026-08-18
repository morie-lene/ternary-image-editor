"""仕様書で固定された値。"""

from __future__ import annotations

from enum import IntEnum

IMAGE_WIDTH = 2048
IMAGE_HEIGHT = 1536
IMAGE_SIZE = (IMAGE_WIDTH, IMAGE_HEIGHT)
BOTTOM_PROTECTED_START_Y = 1436
BOTTOM_PROTECTED_END_Y = 1536


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
TERNARY_EXTENSIONS = frozenset({".png"})
PAIR_SUFFIX_LENGTH = 27

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
