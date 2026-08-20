"""一時メモ層の公開接続契約と事故回帰試験。

動的な差分・履歴算法は ``test_memo_history.py`` が検証する。ここでは、入力、描画、編集、
履歴、保存、画像交換を結ぶ公開上の接続と、実画面で見つかった単一クリックの点描画を検査する。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, Qt

from ternary_image_editor.canvas import ImageCanvas
from ternary_image_editor.history import HistoryEntry, HistoryManager
from ternary_image_editor.main_window import MainWindow
from ternary_image_editor.memo_history import MemoDelta
from ternary_image_editor.session import ImageSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source(member: object) -> str:
    return inspect.getsource(member)


def test_memo_001_exact_pointer_assignment_precedes_unassigned_right_fallback() -> None:
    event_filter = _source(MainWindow.eventFilter)
    exact_assignment = event_filter.index("operation_for_binding(binding)")
    assigned_dispatch = event_filter.index(
        "dispatch_pointer_press(binding)",
        exact_assignment,
    )
    canvas_fallthrough = event_filter.rindex("return super().eventFilter(watched, event)")
    right_press = _source(ImageCanvas.mousePressEvent)
    settings_dialog = (
        PROJECT_ROOT / "src" / "ternary_image_editor" / "settings_dialog.py"
    ).read_text(encoding="utf-8")

    assert exact_assignment < assigned_dispatch < canvas_fallthrough
    assert "event.button() == Qt.MouseButton.RightButton" in right_press
    assert "if not self.memo_enabled:" in right_press
    assert "self._begin_memo_stroke(image_position)" in right_press
    assert '"MouseRight": "右ボタンによる一時メモ描画"' in settings_dialog


def test_memo_002_memo_is_topmost_below_pointer_and_absent_from_saved_pixels() -> None:
    paint = _source(ImageCanvas.paintEvent)
    save = _source(ImageSession.save)
    interface = _source(MainWindow._update_interface)

    assert paint.index("self._paint_image_layers(painter)") < paint.index(
        "self._paint_memo(painter)"
    )
    assert paint.index("self._paint_outer_border(painter)") < paint.index(
        "self._paint_memo(painter)"
    )
    assert paint.index("self._paint_memo(painter)") < paint.index(
        "self._paint_pointer(painter)"
    )
    assert "save_labels_atomic(\n                labels," in save
    assert "memo" not in save
    assert "self.canvas.memo_enabled = loaded and not blocking and not label_stroke_active" in (
        interface
    )


def test_memo_003_004_label_and_memo_deltas_enter_one_chronological_history() -> None:
    entry = _source(HistoryEntry)
    record = _source(HistoryManager.record)
    record_memo = _source(ImageSession.record_memo)
    apply_labels = _source(ImageSession.apply_labels)
    commit_preapplied = _source(ImageSession.commit_preapplied)

    assert "delta: PixelDelta | None" in entry
    assert "memo_delta: MemoDelta | None" in entry
    assert "self._discard_redo_branch()" in record
    assert "entry = HistoryEntry(" in record
    assert "delta=delta" in record
    assert "memo_delta=memo_delta" in record
    assert "self._history.record(" in record_memo
    assert "None,\n            memo_delta=memo_delta" in record_memo
    for session_commit in (apply_labels, commit_preapplied):
        assert "memo_delta: MemoDelta | None = None" in session_commit
        assert "self._history.record(" in session_commit
        assert "delta,\n" in session_commit
        assert "memo_delta=memo_delta" in session_commit


def test_memo_004_common_history_limits_count_both_delta_kinds() -> None:
    entry = _source(HistoryEntry)
    record = _source(HistoryManager.record)
    trim = _source(HistoryManager._trim)
    discard_redo = _source(HistoryManager._discard_redo_branch)

    assert "return label_bytes + memo_bytes" in entry
    assert "self._total_bytes += entry.memory_bytes" in record
    assert "len(self._entries) > self.max_operations" in trim
    assert "self._total_bytes > self.max_bytes" in trim
    assert "self._total_bytes -= oldest.memory_bytes" in trim
    assert "self._total_bytes -= sum(entry.memory_bytes for entry in removed)" in (
        discard_redo
    )


def test_memo_005_label_changes_erase_overlap_in_the_same_atomic_operation() -> None:
    preview = _source(MainWindow._render_brush_preview)
    finish = _source(MainWindow._brush_finished)
    cancel = _source(MainWindow._cancel_brush)
    generated = _source(MainWindow._apply_generated_labels)

    # 消去をラベル実変更の判定より先に行うので、同色筆でもメモだけは消える。
    assert preview.index("self.canvas.stage_label_memo_erase(footprint)") < preview.index(
        "if dirty_bbox is not None:"
    )
    assert finish.index("self.canvas.finish_label_memo_erase") < finish.index(
        "self.session.commit_preapplied("
    )
    assert "memo_delta=memo_delta" in finish
    assert "self.canvas.cancel_label_memo_erase()" in cancel
    assert generated.index("changed_indices =") < generated.index(
        "self.canvas.erase_memo_indices("
    )
    assert generated.index("self.canvas.erase_memo_indices(") < generated.index(
        "self.session.apply_labels("
    )
    assert "memo_delta=memo_delta" in generated


def test_memo_006_hidden_labels_gate_only_the_next_history_entry_without_skipping() -> None:
    availability = _source(MainWindow._history_entry_is_available)
    undo = _source(MainWindow._undo)
    redo = _source(MainWindow._redo)

    assert "return labels_visible or entry.delta is None" in availability
    assert "candidate = self.session.history.next_undo_entry" in undo
    assert "candidate = self.session.history.next_redo_entry" in redo
    assert undo.index("_history_entry_is_available(") < undo.index("self.session.undo()")
    assert redo.index("_history_entry_is_available(") < redo.index("self.session.redo()")
    assert "while " not in undo and "for " not in undo
    assert "while " not in redo and "for " not in redo


def test_memo_007_save_success_discards_memo_but_failure_keeps_current_state() -> None:
    succeeded = _source(MainWindow._save_succeeded)
    failed = _source(MainWindow._save_failed)
    discard = _source(HistoryManager.discard_memo)
    without_memo = _source(HistoryManager._without_memo)

    assert succeeded.index("self.session.discard_memo_history()") < succeeded.index(
        "self.canvas.clear_memo()"
    )
    assert "discard_memo_history" not in failed
    assert "clear_memo" not in failed
    assert "self._without_memo" in discard
    assert "if entry.delta is None:\n                continue" in without_memo
    assert "replace(entry, memo_delta=None)" in without_memo


def test_memo_008_successful_image_replacement_resets_memo_layer() -> None:
    finish_open = _source(MainWindow._finish_open_pair)
    set_images = _source(ImageCanvas.set_images)
    open_pair = _source(MainWindow._open_pair)

    assert "self.canvas.set_images(" in finish_open
    assert "self._reset_memo_layer(width, height)" in set_images
    assert "clear_memo" not in open_pair
    assert "discard_memo_history" not in open_pair


def test_memo_003_single_right_click_at_low_zoom_commits_a_dot(qtbot) -> None:
    canvas = ImageCanvas()
    canvas.resize(320, 240)
    qtbot.addWidget(canvas)
    labels = np.zeros((64, 64), dtype=np.uint8)
    canvas.set_images(np.zeros((*labels.shape, 3), dtype=np.uint8), labels)
    canvas.set_zoom_percent(41.1)
    committed: list[MemoDelta] = []
    canvas.memo_stroke_committed.connect(committed.append)
    canvas.show()
    qtbot.waitExposed(canvas)

    qtbot.mouseClick(
        canvas,
        Qt.MouseButton.RightButton,
        pos=QPoint(canvas.width() // 2, canvas.height() // 2),
    )

    assert len(committed) == 1
    assert committed[0].changed_pixels > 0
    assert canvas.has_memo


def test_memo_003_incomplete_strokes_are_cancelled_at_input_boundaries() -> None:
    event_filter = _source(MainWindow.eventFilter)
    release = _source(MainWindow._release_pointer_inputs)
    resize = _source(ImageCanvas.resizeEvent)

    assert "QEvent.Type.ApplicationDeactivate" in event_filter
    assert "QEvent.Type.FocusOut" in event_filter
    assert "QEvent.Type.UngrabMouse" in event_filter
    assert "event.key() == Qt.Key.Key_Escape" in event_filter
    assert "self.canvas.cancel_memo_stroke" in event_filter
    assert "self.canvas.cancel_memo_stroke" in release
    assert "self.cancel_memo_stroke" in resize
