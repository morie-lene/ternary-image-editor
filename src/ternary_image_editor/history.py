"""画像単位の差分履歴と保存基準点。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .constants import MAX_HISTORY_BYTES, MAX_HISTORY_OPERATIONS

UInt8Array = NDArray[np.uint8]
UInt32Array = NDArray[np.uint32]


@dataclass(frozen=True, slots=True)
class PixelDelta:
    """一操作で変わった画素だけを保持する可逆差分。"""

    shape: tuple[int, ...]
    indices: UInt32Array
    before: UInt8Array
    after: UInt8Array
    description: str

    @property
    def changed_pixels(self) -> int:
        return int(self.indices.size)

    @property
    def memory_bytes(self) -> int:
        return int(self.indices.nbytes + self.before.nbytes + self.after.nbytes)

    def apply_backward(self, labels: UInt8Array) -> None:
        self._apply(labels, self.before)

    def apply_forward(self, labels: UInt8Array) -> None:
        self._apply(labels, self.after)

    def _apply(self, labels: UInt8Array, values: UInt8Array) -> None:
        if labels.shape != self.shape:
            raise ValueError(f"履歴差分の形が一致しない: {labels.shape} != {self.shape}")
        if labels.dtype != np.uint8:
            raise ValueError("履歴対象はuint8配列でなければならない")
        if not labels.flags.c_contiguous:
            raise ValueError("履歴対象はC連続配列でなければならない")
        labels.reshape(-1)[self.indices] = values


def make_pixel_delta(
    before: UInt8Array,
    after: UInt8Array,
    description: str,
) -> PixelDelta | None:
    """二状態から差分を作る。無変更なら履歴を作らない。"""

    if before.shape != after.shape:
        raise ValueError(f"差分元と差分先の形が一致しない: {before.shape} != {after.shape}")
    if before.dtype != np.uint8 or after.dtype != np.uint8:
        raise ValueError("履歴差分はuint8配列から作らなければならない")
    flat_before = np.ascontiguousarray(before).reshape(-1)
    flat_after = np.ascontiguousarray(after).reshape(-1)
    changed = np.flatnonzero(flat_before != flat_after)
    if changed.size == 0:
        return None
    if flat_before.size > np.iinfo(np.uint32).max:
        raise ValueError("履歴差分の画素数がuint32索引範囲を超える")
    indices = changed.astype(np.uint32, copy=False)
    return PixelDelta(
        shape=before.shape,
        indices=indices,
        before=flat_before[changed].astype(np.uint8, copy=True),
        after=flat_after[changed].astype(np.uint8, copy=True),
        description=description,
    )


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    delta: PixelDelta
    before_state_id: int
    after_state_id: int


@dataclass(frozen=True, slots=True)
class HistoryTrimReport:
    dropped_operations: int = 0
    dropped_bytes: int = 0
    saved_state_became_unreachable: bool = False

    @property
    def trimmed(self) -> bool:
        return self.dropped_operations > 0


class HistoryManager:
    """一画像セッションだけに属するUndo・Redo履歴。"""

    def __init__(
        self,
        max_operations: int = MAX_HISTORY_OPERATIONS,
        max_bytes: int = MAX_HISTORY_BYTES,
    ) -> None:
        if max_operations < 1:
            raise ValueError("履歴操作上限は1以上でなければならない")
        if max_bytes < 1:
            raise ValueError("履歴容量上限は1以上でなければならない")
        self.max_operations = max_operations
        self.max_bytes = max_bytes
        self._entries: list[HistoryEntry] = []
        self._cursor = 0
        self._total_bytes = 0
        self._next_state_id = 1
        self._base_state_id = self._allocate_state_id()
        self._saved_state_id: int | None = self._base_state_id

    @property
    def can_undo(self) -> bool:
        return self._cursor > 0

    @property
    def can_redo(self) -> bool:
        return self._cursor < len(self._entries)

    @property
    def operation_count(self) -> int:
        return len(self._entries)

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def current_state_id(self) -> int:
        if self._cursor == 0:
            return self._base_state_id
        return self._entries[self._cursor - 1].after_state_id

    @property
    def saved_state_id(self) -> int | None:
        return self._saved_state_id

    @property
    def is_dirty(self) -> bool:
        return self._saved_state_id is None or self.current_state_id != self._saved_state_id

    @property
    def saved_state_reachable(self) -> bool:
        if self._saved_state_id is None:
            return False
        return self._saved_state_id in self._reachable_state_ids()

    def reset(self, *, clean: bool = True) -> None:
        """画像を離れた時に履歴全体を破棄する。"""

        self._entries.clear()
        self._cursor = 0
        self._total_bytes = 0
        self._base_state_id = self._allocate_state_id()
        self._saved_state_id = self._base_state_id if clean else None

    def mark_saved(self) -> None:
        self._saved_state_id = self.current_state_id

    def record(self, delta: PixelDelta | None) -> HistoryTrimReport:
        """既に適用済みの一操作を履歴へ積む。"""

        if delta is None or delta.changed_pixels == 0:
            return HistoryTrimReport()
        self._discard_redo_branch()
        entry = HistoryEntry(
            delta=delta,
            before_state_id=self.current_state_id,
            after_state_id=self._allocate_state_id(),
        )
        was_saved_reachable = self.saved_state_reachable
        self._entries.append(entry)
        self._cursor += 1
        self._total_bytes += delta.memory_bytes
        dropped_operations = 0
        dropped_bytes = 0
        while len(self._entries) > self.max_operations or self._total_bytes > self.max_bytes:
            oldest = self._entries.pop(0)
            dropped_operations += 1
            dropped_bytes += oldest.delta.memory_bytes
            self._total_bytes -= oldest.delta.memory_bytes
            if self._cursor > 0:
                self._cursor -= 1
                self._base_state_id = oldest.after_state_id
        return HistoryTrimReport(
            dropped_operations=dropped_operations,
            dropped_bytes=dropped_bytes,
            saved_state_became_unreachable=(was_saved_reachable and not self.saved_state_reachable),
        )

    def undo(self, labels: UInt8Array) -> PixelDelta | None:
        if not self.can_undo:
            return None
        entry = self._entries[self._cursor - 1]
        entry.delta.apply_backward(labels)
        self._cursor -= 1
        return entry.delta

    def redo(self, labels: UInt8Array) -> PixelDelta | None:
        if not self.can_redo:
            return None
        entry = self._entries[self._cursor]
        entry.delta.apply_forward(labels)
        self._cursor += 1
        return entry.delta

    def _discard_redo_branch(self) -> None:
        if self._cursor == len(self._entries):
            return
        removed = self._entries[self._cursor :]
        self._total_bytes -= sum(entry.delta.memory_bytes for entry in removed)
        del self._entries[self._cursor :]

    def _reachable_state_ids(self) -> set[int]:
        return {self._base_state_id, *(entry.after_state_id for entry in self._entries)}

    def _allocate_state_id(self) -> int:
        state_id = self._next_state_id
        self._next_state_id += 1
        return state_id
