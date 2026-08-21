"""一時メモ層の公開接続契約と事故回帰試験。

動的な差分・履歴算法は ``test_memo_history.py`` が検証する。ここでは、入力、描画、編集、
履歴、保存、画像交換を結ぶ公開上の接続と、実画面で見つかった単一クリックの点描画を検査する。
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import QScrollArea, QToolBar

from ternary_image_editor.canvas import ImageCanvas
from ternary_image_editor.history import HistoryEntry, HistoryManager
from ternary_image_editor.main_window import MainWindow
from ternary_image_editor.memo_history import MemoDelta
from ternary_image_editor.session import ImageSession
from ternary_image_editor.settings_dialog import SettingsDialog
from ternary_image_editor.settings_model import (
    DEFAULT_MEMO_COLOR,
    AppSettings,
    SettingsRepository,
)

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
    pointer = _source(ImageCanvas._paint_pointer)
    memo_segment = _source(ImageCanvas._draw_memo_segment)
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
    assert "QColor(*self._memo_color, 235)" in pointer
    assert "QColor(*self._memo_color, 245)" in memo_segment
    assert "QColor(25, 25, 25, 245)" in memo_segment
    assert (
        "self.canvas.memo_enabled = loaded and not blocking and not label_stroke_active"
        in interface
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


def test_memo_011_user_setting_disables_only_the_unassigned_right_fallback(qtbot) -> None:
    canvas = ImageCanvas()
    canvas.resize(320, 240)
    qtbot.addWidget(canvas)
    labels = np.zeros((64, 64), dtype=np.uint8)
    canvas.set_images(np.zeros((*labels.shape, 3), dtype=np.uint8), labels)
    canvas.show()
    qtbot.waitExposed(canvas)
    center = QPoint(canvas.width() // 2, canvas.height() // 2)

    canvas.memo_input_enabled = False
    qtbot.mouseClick(canvas, Qt.MouseButton.RightButton, pos=center)
    assert not canvas.has_memo

    canvas.memo_input_enabled = True
    qtbot.mouseClick(canvas, Qt.MouseButton.RightButton, pos=center)
    assert canvas.has_memo


def test_memo_011_color_changes_future_strokes_without_recoloring_existing_pixels() -> None:
    canvas = ImageCanvas()
    labels = np.zeros((64, 64), dtype=np.uint8)
    canvas.set_images(np.zeros((*labels.shape, 3), dtype=np.uint8), labels)

    first_color = (18, 52, 86)
    second_color = (171, 205, 239)
    canvas.set_memo_color(first_color)
    canvas._begin_memo_stroke((16.0, 32.0))
    canvas.finish_memo_stroke()
    first_region = canvas._memo_rgba_view()[27:38, 11:22].copy()
    assert np.any(np.all(first_region[..., :3] == first_color, axis=2))

    canvas.set_memo_color(second_color)
    np.testing.assert_array_equal(canvas._memo_rgba_view()[27:38, 11:22], first_region)
    canvas._begin_memo_stroke((48.0, 32.0))
    canvas.finish_memo_stroke()
    second_region = canvas._memo_rgba_view()[27:38, 43:54]
    second_distance = np.max(
        np.abs(second_region[..., :3].astype(np.int16) - np.asarray(second_color)),
        axis=2,
    )
    assert np.any(second_distance <= 3)
    np.testing.assert_array_equal(canvas._memo_rgba_view()[27:38, 11:22], first_region)


def test_memo_011_settings_roundtrip_dialog_and_corruption_fallback(qtbot, tmp_path) -> None:
    raw = QSettings(str(tmp_path / "memo.ini"), QSettings.Format.IniFormat)
    repository = SettingsRepository(raw)
    repository.save(AppSettings(memo_enabled=False, memo_color="#123abc"))

    loaded = repository.load()
    assert not loaded.memo_enabled
    assert loaded.memo_color == "#123ABC"

    applied: list[AppSettings] = []
    dialog = SettingsDialog(loaded, apply_callback=applied.append)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    general_page = dialog.pages.widget(0)
    assert isinstance(general_page, QScrollArea)
    assert dialog.height() <= 700
    memo_top = dialog.memo_enabled.mapTo(general_page.viewport(), QPoint(0, 0)).y()
    assert 0 <= memo_top < general_page.viewport().height()
    assert not dialog.memo_enabled.isChecked()
    assert dialog.memo_color_edit.text() == "#123ABC"
    dialog.memo_enabled.setChecked(True)
    dialog.memo_color_edit.setText("#abcdef")
    assert dialog.apply_changes()
    assert applied[-1].memo_enabled
    assert applied[-1].memo_color == "#ABCDEF"
    dialog.memo_color_edit.setText("#010203")
    dialog.reset_memo_color()
    assert dialog.memo_color_edit.text() == DEFAULT_MEMO_COLOR

    raw.setValue("memo/enabled", "invalid")
    raw.setValue("memo/color", "yellow")
    damaged_repository = SettingsRepository(raw)
    repaired = damaged_repository.load()
    assert repaired.memo_enabled is True
    assert repaired.memo_color == DEFAULT_MEMO_COLOR
    assert "invalid setting memo/enabled; default used" in damaged_repository.warnings
    assert "invalid setting memo/color; default used" in damaged_repository.warnings

    cancelled = SettingsDialog(loaded)
    qtbot.addWidget(cancelled)
    cancelled.memo_enabled.setChecked(True)
    cancelled.memo_color_edit.setText("#010203")
    cancelled.reject()
    assert not cancelled.applied_settings.memo_enabled
    assert cancelled.applied_settings.memo_color == "#123ABC"


def test_memo_012_settings_action_is_beside_help_and_absent_from_file_menu(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    raw = QSettings(str(tmp_path / "window.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=raw)
    qtbot.addWidget(window)

    menu_bar_actions = window.menuBar().actions()
    settings_index = menu_bar_actions.index(window.settings_action)
    assert window.settings_action.text() == "設定"
    assert menu_bar_actions[settings_index + 1].text() == "ヘルプ"
    file_menu = next(action.menu() for action in menu_bar_actions if action.text() == "ファイル")
    assert file_menu is not None
    assert window.settings_action not in file_menu.actions()

    toolbar = window.findChild(QToolBar, "mainToolbar")
    assert toolbar is not None
    assert window.settings_action in toolbar.actions()

    opened: list[SettingsDialog] = []
    monkeypatch.setattr(SettingsDialog, "exec", lambda dialog: opened.append(dialog) or 0)
    window.settings_action.trigger()
    qtbot.mouseClick(window.controls.palette_buttons[0], Qt.MouseButton.LeftButton)
    assert len(opened) == 2


def test_memo_011_main_window_applies_and_snapshots_memo_preferences(qtbot, tmp_path) -> None:
    raw = QSettings(str(tmp_path / "window-settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=raw)
    qtbot.addWidget(window)
    snapshot = AppSettings(memo_enabled=False, memo_color="#2468AC")

    window._apply_settings_snapshot(snapshot)

    assert not window.canvas.memo_input_enabled
    assert window.canvas.memo_color == (0x24, 0x68, 0xAC)
    current = window._current_settings_snapshot()
    assert not current.memo_enabled
    assert current.memo_color == "#2468AC"

    window.settings_repository.save(current)
    restored = MainWindow(
        settings=QSettings(str(tmp_path / "window-settings.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(restored)
    assert not restored.canvas.memo_input_enabled
    assert restored.canvas.memo_color == (0x24, 0x68, 0xAC)


def test_memo_011_apply_failure_restores_runtime_and_persisted_settings(qtbot) -> None:
    initial = AppSettings(memo_enabled=True, memo_color="#FFD640")
    candidate = AppSettings(memo_enabled=False, memo_color="#2468AC")
    runtime = [initial]
    persisted = [initial]

    def apply(snapshot: AppSettings) -> None:
        runtime[0] = snapshot

    def persist(snapshot: AppSettings) -> None:
        persisted[0] = snapshot
        if snapshot == candidate:
            raise RuntimeError("injected persistence failure")

    dialog = SettingsDialog(
        initial,
        apply_callback=apply,
        persist_callback=persist,
    )
    qtbot.addWidget(dialog)
    dialog.memo_enabled.setChecked(False)
    dialog.memo_color_edit.setText("#2468AC")

    assert not dialog.apply_changes()
    assert runtime[0] == initial
    assert persisted[0] == initial
    assert dialog.applied_settings == initial
    assert "設定を適用できません" in dialog.capture_status.text()


def test_memo_011_runtime_failure_does_not_advance_persisted_settings(qtbot) -> None:
    initial = AppSettings(memo_enabled=True, memo_color="#FFD640")
    candidate = AppSettings(memo_enabled=False, memo_color="#2468AC")
    runtime = [initial]
    persisted: list[AppSettings] = []

    def apply(snapshot: AppSettings) -> None:
        runtime[0] = snapshot
        if snapshot == candidate:
            raise RuntimeError("injected runtime failure")

    dialog = SettingsDialog(
        initial,
        apply_callback=apply,
        persist_callback=persisted.append,
    )
    qtbot.addWidget(dialog)
    dialog.memo_enabled.setChecked(False)
    dialog.memo_color_edit.setText("#2468AC")

    assert not dialog.apply_changes()
    assert runtime[0] == initial
    assert not persisted
    assert dialog.applied_settings == initial


def test_memo_011_qt_slot_failure_rolls_back_real_window_and_qsettings(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    raw = QSettings(str(tmp_path / "qt-slot-failure.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=raw)
    qtbot.addWidget(window)
    initial = window._current_settings_snapshot()
    initial_applied = window.applied_settings
    candidate_colors = ("#102030", "#8090A0", "#F0E0D0")
    candidate_palette = tuple(
        tuple(int(color[offset : offset + 2], 16) for offset in (1, 3, 5))
        for color in candidate_colors
    )
    original_set_palette = window.canvas.set_pseudo_palette

    def fail_for_candidate(palette) -> None:
        if palette == candidate_palette:
            raise RuntimeError("injected canvas palette failure")
        original_set_palette(palette)

    monkeypatch.setattr(window.canvas, "set_pseudo_palette", fail_for_candidate)
    dialog = SettingsDialog(
        initial,
        persist_callback=window.settings_repository.save,
        apply_callback=window._apply_settings_snapshot,
    )
    qtbot.addWidget(dialog)
    for edit, color in zip(dialog.color_edits, candidate_colors, strict=True):
        edit.setText(color)

    assert not dialog.apply_changes()
    assert window.controls.pseudo_palette == tuple(
        tuple(int(color[offset : offset + 2], 16) for offset in (1, 3, 5))
        for color in initial.pseudo_colors
    )
    assert window.canvas.pseudo_palette == window.controls.pseudo_palette
    assert window.applied_settings == initial_applied
    assert window.settings_repository.load().pseudo_colors == initial.pseudo_colors
    assert dialog.applied_settings == initial


def test_memo_011_main_window_restores_state_when_final_interface_update_fails(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    window = MainWindow(
        settings=QSettings(str(tmp_path / "interface-failure.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    initial = window._current_settings_snapshot()
    initial_applied = window.applied_settings
    candidate = AppSettings(memo_enabled=False, memo_color="#2468AC")
    original_update = window._update_interface
    calls = 0

    def fail_once() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected interface failure")
        original_update()

    monkeypatch.setattr(window, "_update_interface", fail_once)

    with pytest.raises(RuntimeError, match="injected interface failure"):
        window._apply_settings_snapshot(candidate)

    assert window.applied_settings == initial_applied
    assert window._current_settings_snapshot() == initial
    assert window.canvas.memo_input_enabled == initial.memo_enabled
    assert window.canvas.memo_color == tuple(
        int(initial.memo_color[offset : offset + 2], 16) for offset in (1, 3, 5)
    )


def test_memo_011_persistence_failure_restores_status_and_defers_commit_effects(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    raw = QSettings(str(tmp_path / "persistence-failure.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=raw)
    qtbot.addWidget(window)
    initial = window._current_settings_snapshot()
    initial_applied = window.applied_settings
    window.settings_repository.save(initial)
    candidate = replace(
        initial,
        original_folder=str(tmp_path / "original"),
        ternary_folder=str(tmp_path / "ternary"),
        output_folder=str(tmp_path / "output"),
        ternary_visible=False,
        small_components=True,
    )
    messages: list[str] = []
    component_requests: list[bool] = []
    monkeypatch.setattr(window, "_message", messages.append)
    monkeypatch.setattr(window, "_request_components", lambda: component_requests.append(True))
    window._pairs = [object()]
    window.session._pair = object()
    window.session._labels = np.zeros((8, 8), dtype=np.uint8)

    def persist(snapshot: AppSettings) -> None:
        window.settings_repository.save(snapshot)
        if snapshot == candidate:
            raise RuntimeError("injected persistence failure")

    dialog = SettingsDialog(
        initial,
        persist_callback=persist,
        apply_callback=window._apply_settings_snapshot,
    )
    dialog.applied.connect(window._settings_snapshot_committed)
    dialog.apply_failed.connect(window._settings_snapshot_failed)
    qtbot.addWidget(dialog)
    dialog.original_folder.setText(candidate.original_folder)
    dialog.ternary_folder.setText(candidate.ternary_folder)
    dialog.output_folder.setText(candidate.output_folder)
    dialog.ternary_visible.setChecked(False)
    dialog.small_components.setChecked(True)

    assert not dialog.apply_changes()
    assert window.controls.ternary_visible.isChecked()
    assert window.canvas.ternary_visible
    assert window.protection_status.text() == "保護: —"
    assert window._folders is None
    assert window.applied_settings == initial_applied
    assert window.settings_repository.load() == initial
    assert not messages
    assert not component_requests
    assert window._pending_settings_effects is None

    success = SettingsDialog(
        initial,
        persist_callback=window.settings_repository.save,
        apply_callback=window._apply_settings_snapshot,
    )
    success.applied.connect(window._settings_snapshot_committed)
    qtbot.addWidget(success)
    success.original_folder.setText(candidate.original_folder)
    success.ternary_folder.setText(candidate.ternary_folder)
    success.output_folder.setText(candidate.output_folder)
    success.ternary_visible.setChecked(False)
    success.small_components.setChecked(True)

    assert success.apply_changes()
    assert window.applied_settings == candidate
    assert window.settings_repository.load() == candidate
    assert messages == [
        "フォルダ設定を適用した。表示中一覧は維持し、再走査時に新設定へ切り替える"
    ]
    assert component_requests == [True]
