from __future__ import annotations

import numpy as np
import pytest

from ternary_image_editor.constants import MAX_HISTORY_BYTES, MAX_HISTORY_OPERATIONS
from ternary_image_editor.history import HistoryManager, make_pixel_delta
from ternary_image_editor.memo_history import MemoDelta, MemoPixelPatch


def _edit(before: np.ndarray, index: tuple[int, int], value: int) -> np.ndarray:
    after = before.copy()
    after[index] = value
    return after


def _memo_delta(
    shape: tuple[int, int],
    index: int,
    description: str,
    *,
    color: int = 1,
) -> MemoDelta:
    return MemoDelta(
        shape,
        (
            MemoPixelPatch(
                indices=np.array([index], dtype=np.uint32),
                before=np.zeros((1, 4), dtype=np.uint8),
                after=np.array([[color, color, color, 255]], dtype=np.uint8),
            ),
        ),
        description,
    )


def test_memo_delta_applies_both_directions_and_reports_union_bounding_box() -> None:
    before = np.zeros((5, 6, 4), dtype=np.uint8)
    before[1, 2] = (10, 20, 30, 40)
    before[2, 1] = (50, 60, 70, 80)
    before[3, 4] = (90, 100, 110, 120)
    first = MemoPixelPatch(
        indices=np.array([8, 22], dtype=np.uint32),
        before=np.array([[10, 20, 30, 40], [90, 100, 110, 120]], dtype=np.uint8),
        after=np.array([[1, 2, 3, 255], [4, 5, 6, 255]], dtype=np.uint8),
    )
    second = MemoPixelPatch(
        indices=np.array([13], dtype=np.uint32),
        before=np.array([[50, 60, 70, 80]], dtype=np.uint8),
        after=np.array([[7, 8, 9, 255]], dtype=np.uint8),
    )
    delta = MemoDelta((5, 6), (first, second), "メモ一筆")
    expected = before.copy()
    expected[1, 2] = first.after[0]
    expected[3, 4] = first.after[1]
    expected[2, 1] = second.after[0]

    current = before.copy()
    delta.apply_forward(current)
    np.testing.assert_array_equal(current, expected)
    delta.apply_backward(current)
    np.testing.assert_array_equal(current, before)
    assert delta.bounding_box == (1, 1, 5, 4)
    assert delta.changed_pixels == 3
    assert delta.memory_bytes == first.memory_bytes + second.memory_bytes


def test_memo_patch_rejects_invalid_index_and_rgba_arrays() -> None:
    valid_indices = np.array([0], dtype=np.uint32)
    valid_rgba = np.zeros((1, 4), dtype=np.uint8)

    with pytest.raises(ValueError, match="一画素以上"):
        MemoPixelPatch(
            np.array([], dtype=np.uint32),
            np.empty((0, 4), dtype=np.uint8),
            np.empty((0, 4), dtype=np.uint8),
        )
    with pytest.raises(ValueError, match="uint32"):
        MemoPixelPatch(np.array([0], dtype=np.int64), valid_rgba, valid_rgba)
    with pytest.raises(ValueError, match="一次元"):
        MemoPixelPatch(np.array([[0]], dtype=np.uint32), valid_rgba, valid_rgba)
    with pytest.raises(ValueError, match="変更前値"):
        MemoPixelPatch(valid_indices, np.zeros((1, 3), dtype=np.uint8), valid_rgba)
    with pytest.raises(ValueError, match="変更後値"):
        MemoPixelPatch(valid_indices, valid_rgba, np.zeros((1, 4), dtype=np.int16))
    with pytest.raises(ValueError, match="実変更"):
        MemoPixelPatch(valid_indices, valid_rgba, valid_rgba.copy())


def test_memo_delta_rejects_invalid_shape_empty_changes_and_out_of_bounds_index() -> None:
    one_pixel = MemoPixelPatch(
        np.array([0], dtype=np.uint32),
        np.zeros((1, 4), dtype=np.uint8),
        np.ones((1, 4), dtype=np.uint8),
    )
    out_of_bounds = MemoPixelPatch(
        np.array([6], dtype=np.uint32),
        np.zeros((1, 4), dtype=np.uint8),
        np.ones((1, 4), dtype=np.uint8),
    )

    with pytest.raises(ValueError, match="寸法"):
        MemoDelta((0, 3), (one_pixel,), "不正")
    with pytest.raises(ValueError, match="一画素以上"):
        MemoDelta((2, 3), (), "不正")
    with pytest.raises(ValueError, match="画像寸法"):
        MemoDelta((2, 3), (out_of_bounds,), "不正")


def test_memo_delta_rejects_duplicate_indices_across_patches() -> None:
    first = MemoPixelPatch(
        np.array([0], dtype=np.uint32),
        np.array([[0, 0, 0, 0]], dtype=np.uint8),
        np.array([[1, 1, 1, 1]], dtype=np.uint8),
    )
    overlapping = MemoPixelPatch(
        np.array([0], dtype=np.uint32),
        np.array([[1, 1, 1, 1]], dtype=np.uint8),
        np.array([[2, 2, 2, 2]], dtype=np.uint8),
    )

    with pytest.raises(ValueError, match="重複"):
        MemoDelta((1, 1), (first, overlapping), "可逆でない重複")


def test_memo_delta_rejects_incompatible_or_immutable_apply_target() -> None:
    patch = MemoPixelPatch(
        np.array([0], dtype=np.uint32),
        np.zeros((1, 4), dtype=np.uint8),
        np.ones((1, 4), dtype=np.uint8),
    )
    delta = MemoDelta((3, 4), (patch,), "検証")

    with pytest.raises(ValueError, match="適用先"):
        delta.apply_forward(np.zeros((3, 4, 3), dtype=np.uint8))
    with pytest.raises(ValueError, match="適用先"):
        delta.apply_forward(np.zeros((3, 4, 4), dtype=np.int16))
    with pytest.raises(ValueError, match="C連続"):
        delta.apply_forward(np.zeros((4, 3, 4), dtype=np.uint8).transpose(1, 0, 2))
    read_only = np.zeros((3, 4, 4), dtype=np.uint8)
    read_only.setflags(write=False)
    with pytest.raises(ValueError, match="書込可能"):
        delta.apply_forward(read_only)


def test_history_unifies_label_and_memo_order_and_discards_redo_branch() -> None:
    history = HistoryManager()
    baseline = np.zeros((1, 3), dtype=np.uint8)
    labels = baseline.copy()
    initial_state = history.current_state_id

    first = _edit(labels, (0, 0), 1)
    first_delta = make_pixel_delta(labels, first, "第一ラベル")
    assert first_delta is not None
    history.record(first_delta)
    labels[:] = first
    first_state = history.current_state_id
    memo = _memo_delta(labels.shape, 1, "中間メモ")
    history.record(None, memo_delta=memo)
    assert history.current_state_id == first_state

    second = _edit(labels, (0, 1), 2)
    second_delta = make_pixel_delta(labels, second, "第二ラベル")
    assert second_delta is not None
    history.record(second_delta)
    labels[:] = second

    undo_descriptions = []
    for _ in range(3):
        entry = history.undo(labels)
        assert entry is not None
        undo_descriptions.append(entry.description)
    assert undo_descriptions == ["第二ラベル", "中間メモ", "第一ラベル"]
    assert history.current_state_id == initial_state
    np.testing.assert_array_equal(labels, baseline)

    redo_descriptions = []
    for _ in range(3):
        entry = history.redo(labels)
        assert entry is not None
        redo_descriptions.append(entry.description)
    assert redo_descriptions == ["第一ラベル", "中間メモ", "第二ラベル"]
    np.testing.assert_array_equal(labels, second)

    assert history.undo(labels) is not None
    branch = _memo_delta(labels.shape, 2, "分岐メモ", color=3)
    history.record(None, memo_delta=branch)
    assert not history.can_redo
    assert history.operation_count == 3
    assert history.current_state_id == first_state
    assert history.next_undo_entry is not None
    assert history.next_undo_entry.memo_delta is branch


def test_history_records_label_and_memo_as_one_atomic_reversible_entry() -> None:
    history = HistoryManager()
    before_labels = np.zeros((1, 2), dtype=np.uint8)
    after_labels = _edit(before_labels, (0, 1), 2)
    label_delta = make_pixel_delta(before_labels, after_labels, "筆とメモ消去")
    assert label_delta is not None
    erased_color = np.array([[255, 214, 64, 245]], dtype=np.uint8)
    memo_delta = MemoDelta(
        before_labels.shape,
        (
            MemoPixelPatch(
                indices=np.array([1], dtype=np.uint32),
                before=erased_color,
                after=np.zeros((1, 4), dtype=np.uint8),
            ),
        ),
        "筆とメモ消去",
    )

    history.record(label_delta, memo_delta=memo_delta)
    entry = history.current_entry

    assert entry is not None
    assert entry.delta is label_delta
    assert entry.memo_delta is memo_delta
    assert entry.memory_bytes == label_delta.memory_bytes + memo_delta.memory_bytes
    assert history.operation_count == 1
    assert history.total_bytes == entry.memory_bytes

    labels = after_labels.copy()
    memo = np.zeros((*before_labels.shape, 4), dtype=np.uint8)
    memo.reshape(-1, 4)[1] = erased_color[0]
    memo_delta.apply_forward(memo)
    undone = history.undo(labels)
    assert undone is entry
    assert undone.memo_delta is not None
    undone.memo_delta.apply_backward(memo)
    np.testing.assert_array_equal(labels, before_labels)
    np.testing.assert_array_equal(memo.reshape(-1, 4)[1], erased_color[0])

    redone = history.redo(labels)
    assert redone is entry
    assert redone.memo_delta is not None
    redone.memo_delta.apply_forward(memo)
    np.testing.assert_array_equal(labels, after_labels)
    assert memo.reshape(-1, 4)[1, 3] == 0


def test_discard_memo_preserves_applied_and_redo_label_history() -> None:
    history = HistoryManager()
    labels = np.zeros((1, 3), dtype=np.uint8)

    first = _edit(labels, (0, 0), 1)
    first_delta = make_pixel_delta(labels, first, "第一複合")
    assert first_delta is not None
    history.record(first_delta, memo_delta=_memo_delta(labels.shape, 0, "第一複合"))
    labels[:] = first
    first_state = history.current_state_id
    history.record(None, memo_delta=_memo_delta(labels.shape, 1, "適用済みメモ単独"))

    second = _edit(labels, (0, 1), 2)
    second_delta = make_pixel_delta(labels, second, "第二複合")
    assert second_delta is not None
    history.record(second_delta, memo_delta=_memo_delta(labels.shape, 1, "第二複合"))
    labels[:] = second
    second_state = history.current_state_id
    history.mark_saved()
    history.record(None, memo_delta=_memo_delta(labels.shape, 2, "Redo側メモ単独"))

    third = _edit(labels, (0, 2), 1)
    third_delta = make_pixel_delta(labels, third, "第三複合")
    assert third_delta is not None
    history.record(third_delta, memo_delta=_memo_delta(labels.shape, 2, "第三複合"))
    labels[:] = third

    for _ in range(3):
        assert history.undo(labels) is not None
    assert history.cursor == 2
    assert history.current_state_id == first_state
    assert history.next_undo_entry is not None
    assert history.next_undo_entry.delta is None
    assert history.next_redo_entry is not None
    assert history.next_redo_entry.delta is second_delta

    history.discard_memo()

    assert history.cursor == 1
    assert history.operation_count == 3
    assert history.current_state_id == first_state
    assert history.saved_state_id == second_state
    assert history.saved_state_reachable
    assert history.total_bytes == (
        first_delta.memory_bytes + second_delta.memory_bytes + third_delta.memory_bytes
    )
    assert history.next_undo_entry is not None
    assert history.next_undo_entry.delta is first_delta
    assert history.next_undo_entry.memo_delta is None
    assert history.next_redo_entry is not None
    assert history.next_redo_entry.delta is second_delta
    assert history.next_redo_entry.memo_delta is None

    assert history.redo(labels) is not None
    np.testing.assert_array_equal(labels, second)
    assert history.current_state_id == second_state
    assert not history.is_dirty


def test_memo_entries_count_toward_200_operation_and_512_mib_limits() -> None:
    assert MAX_HISTORY_OPERATIONS == 200
    assert MAX_HISTORY_BYTES == 512 * 1024 * 1024
    defaults = HistoryManager()
    assert defaults.max_operations == MAX_HISTORY_OPERATIONS
    assert defaults.max_bytes == MAX_HISTORY_BYTES

    labels = np.zeros((1, 3), dtype=np.uint8)
    after = _edit(labels, (0, 0), 1)
    label_delta = make_pixel_delta(labels, after, "複合")
    assert label_delta is not None
    composite_memo = _memo_delta(labels.shape, 0, "複合")

    byte_limited = HistoryManager(
        max_operations=10,
        max_bytes=label_delta.memory_bytes + composite_memo.memory_bytes - 1,
    )
    byte_report = byte_limited.record(label_delta, memo_delta=composite_memo)
    assert byte_report.dropped_operations == 1
    assert byte_report.dropped_bytes == label_delta.memory_bytes + composite_memo.memory_bytes
    assert byte_limited.operation_count == 0
    assert byte_limited.total_bytes == 0

    operation_limited = HistoryManager(max_operations=2, max_bytes=1024)
    operation_limited.record(label_delta, memo_delta=composite_memo)
    operation_limited.record(None, memo_delta=_memo_delta(labels.shape, 1, "第二"))
    operation_report = operation_limited.record(
        None,
        memo_delta=_memo_delta(labels.shape, 2, "第三", color=3),
    )
    assert operation_report.dropped_operations == 1
    assert operation_report.dropped_bytes == (
        label_delta.memory_bytes + composite_memo.memory_bytes
    )
    assert operation_limited.operation_count == 2
