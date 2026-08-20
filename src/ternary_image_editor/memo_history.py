"""保存対象外メモのQt非依存な疎RGBA差分。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

UInt8Array = NDArray[np.uint8]
UInt32Array = NDArray[np.uint32]
BoundingBox = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class MemoPixelPatch:
    """重複しないメモ画素群の前後RGBA値。"""

    indices: UInt32Array
    before: UInt8Array
    after: UInt8Array

    def __post_init__(self) -> None:
        if self.indices.dtype != np.uint32 or self.indices.ndim != 1:
            raise ValueError("メモ差分索引はuint32一次元配列でなければならない")
        if self.indices.size == 0:
            raise ValueError("メモ差分patchには一画素以上が必要")
        expected = (self.indices.size, 4)
        if self.before.dtype != np.uint8 or self.before.shape != expected:
            raise ValueError("メモ差分の変更前値はuint8のN×4配列でなければならない")
        if self.after.dtype != np.uint8 or self.after.shape != expected:
            raise ValueError("メモ差分の変更後値はuint8のN×4配列でなければならない")
        if not bool(np.all(np.any(self.before != self.after, axis=1))):
            raise ValueError("メモ差分patchの各画素には実変更が必要")

    @property
    def changed_pixels(self) -> int:
        return int(self.indices.size)

    @property
    def memory_bytes(self) -> int:
        return int(self.indices.nbytes + self.before.nbytes + self.after.nbytes)


@dataclass(frozen=True, slots=True)
class MemoDelta:
    """一操作に属する可逆なメモRGBA差分。"""

    shape: tuple[int, int]
    patches: tuple[MemoPixelPatch, ...]
    description: str

    def __post_init__(self) -> None:
        height, width = self.shape
        if height < 1 or width < 1:
            raise ValueError("メモ差分の画像寸法は正でなければならない")
        if not self.patches:
            raise ValueError("メモ差分には一画素以上の変更が必要")
        pixel_count = height * width
        if any(
            patch.indices.size and int(patch.indices.max()) >= pixel_count
            for patch in self.patches
        ):
            raise ValueError("メモ差分索引が画像寸法を超えている")
        all_indices = np.concatenate(
            [patch.indices for patch in self.patches if patch.indices.size]
        )
        if all_indices.size > 1:
            ordered = np.sort(all_indices)
            if bool(np.any(ordered[1:] == ordered[:-1])):
                raise ValueError("メモ差分の画素索引がpatch間で重複している")

    @property
    def changed_pixels(self) -> int:
        return sum(patch.changed_pixels for patch in self.patches)

    @property
    def memory_bytes(self) -> int:
        return sum(patch.memory_bytes for patch in self.patches)

    @property
    def bounding_box(self) -> BoundingBox:
        height, width = self.shape
        left = width
        top = height
        right = 0
        bottom = 0
        for patch in self.patches:
            if patch.indices.size == 0:
                continue
            indices = patch.indices.astype(np.int64, copy=False)
            columns = indices % width
            rows = indices // width
            left = min(left, int(columns.min()))
            top = min(top, int(rows.min()))
            right = max(right, int(columns.max()) + 1)
            bottom = max(bottom, int(rows.max()) + 1)
        return left, top, right, bottom

    def apply_backward(self, rgba: UInt8Array) -> None:
        self._apply(rgba, forward=False)

    def apply_forward(self, rgba: UInt8Array) -> None:
        self._apply(rgba, forward=True)

    def _apply(self, rgba: UInt8Array, *, forward: bool) -> None:
        expected = (*self.shape, 4)
        if rgba.dtype != np.uint8 or rgba.shape != expected:
            raise ValueError(f"メモ差分の適用先が一致しない: {rgba.shape} != {expected}")
        if not rgba.flags.c_contiguous or not rgba.flags.writeable:
            raise ValueError("メモ差分の適用先は書込可能なC連続配列でなければならない")
        flat = rgba.reshape(-1, 4)
        for patch in self.patches:
            flat[patch.indices] = patch.after if forward else patch.before


__all__ = ["MemoDelta", "MemoPixelPatch"]
