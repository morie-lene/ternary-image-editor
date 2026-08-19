"""Version 1.5 two-page settings dialog and shortcut capture state machine."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import StrEnum
from time import monotonic

from PySide6.QtCore import QEvent, QObject, QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QRegularExpressionValidator,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .action_registry import (
    OPERATION_BY_ID,
    OPERATION_SPECS,
    AssignmentStatus,
    AssignmentTarget,
    OperationType,
    ShortcutConflict,
    ShortcutSlot,
    binding_is_pointer,
    canonical_binding,
    canonical_shortcut,
    mouse_button_binding,
    native_binding,
    pointer_base,
    shortcut_is_reserved,
    wheel_binding,
)
from .constants import (
    MAX_BOUNDARY_THICKNESS,
    MAX_BRUSH_DIAMETER,
    MIN_BOUNDARY_THICKNESS,
    MIN_BRUSH_DIAMETER,
)
from .settings_model import (
    DEFAULT_PSEUDO_COLORS,
    AppSettings,
    close_color_pairs,
    normalize_hex_color,
    rgb_from_hex,
)


class CaptureState(StrEnum):
    IDLE = "idle"
    WAITING = "waiting"
    CANDIDATE = "candidate"


_MODIFIER_KEY_VALUES = {
    int(Qt.Key.Key_Control),
    int(Qt.Key.Key_Alt),
    int(Qt.Key.Key_Shift),
    int(Qt.Key.Key_Meta),
}
_MODIFIER_KEYS_BY_FLAG = (
    (Qt.KeyboardModifier.ControlModifier, int(Qt.Key.Key_Control)),
    (Qt.KeyboardModifier.AltModifier, int(Qt.Key.Key_Alt)),
    (Qt.KeyboardModifier.ShiftModifier, int(Qt.Key.Key_Shift)),
    (Qt.KeyboardModifier.MetaModifier, int(Qt.Key.Key_Meta)),
)
_MOUSE_EVENT_TYPES = {
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
}
_WHEEL_TAIL_NO_PHASE_SECONDS = 0.2
_WHEEL_TAIL_PHASE_TIMEOUT_SECONDS = 1.0


class ShortcutCaptureController(QObject):
    """One-binding keyboard/pointer capture independent of settings widgets."""

    state_changed = Signal(object)
    candidate_ready = Signal(object, str)
    wheel_candidate_started = Signal(object)
    rejected = Signal(str)
    cancelled = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = CaptureState.IDLE
        self.target: AssignmentTarget | None = None
        self._pressed_keys: set[int] = set()
        self._ignored_until_release: set[int] = set()
        self._pressed_buttons: set[Qt.MouseButton] = set()
        self._ignored_buttons_until_release: set[Qt.MouseButton] = set()
        self._captured_buttons_until_release: set[Qt.MouseButton] = set()
        self._recent_captured_releases: set[Qt.MouseButton] = set()
        self._double_click_buttons: set[Qt.MouseButton] = set()

    @property
    def is_active(self) -> bool:
        return self.state is not CaptureState.IDLE

    @property
    def pressed_keys(self) -> frozenset[int]:
        return frozenset(self._pressed_keys)

    @property
    def pressed_buttons(self) -> frozenset[Qt.MouseButton]:
        return frozenset(self._pressed_buttons)

    def start(
        self,
        target: AssignmentTarget,
        *,
        preheld_keys: Iterable[int] = (),
        preheld_buttons: Iterable[Qt.MouseButton] = (),
    ) -> None:
        if self.is_active:
            self.cancel("別の割当欄を選択した")
        self.clear_pointer_latches()
        self.target = target
        self._ignored_until_release = self._pressed_keys | {int(key) for key in preheld_keys}
        self._ignored_buttons_until_release = self._pressed_buttons | {
            Qt.MouseButton(button) for button in preheld_buttons
        }
        self._set_state(CaptureState.WAITING)

    def finish(self) -> None:
        self.target = None
        self._ignored_until_release.clear()
        self._ignored_buttons_until_release.clear()
        self._set_state(CaptureState.IDLE)

    def cancel(self, reason: str = "取消") -> None:
        if not self.is_active:
            self.clear_pointer_latches()
            return
        self.finish()
        self.clear_pointer_latches()
        self.cancelled.emit(reason)

    def clear_pointer_latches(self, *, clear_pressed: bool = False) -> None:
        """Clear capture-only pointer state while optionally forgetting physical state."""

        self._ignored_buttons_until_release.clear()
        self._captured_buttons_until_release.clear()
        self._recent_captured_releases.clear()
        self._double_click_buttons.clear()
        if clear_pressed:
            self._pressed_buttons.clear()

    def reset_input_state(self) -> None:
        """Forget physical input state after a deactivation may have lost releases."""

        self.clear_pointer_latches(clear_pressed=True)
        self._pressed_keys.clear()
        self._ignored_until_release.clear()

    def handle_event(self, event: QEvent) -> bool:
        if isinstance(event, QKeyEvent):
            return self._handle_key_event(event)
        if isinstance(event, QMouseEvent):
            return self._handle_mouse_event(event)
        if isinstance(event, QWheelEvent):
            return self._handle_wheel_event(event)
        return False

    def _handle_key_event(self, event: QKeyEvent) -> bool:
        key = int(event.key())
        if event.type() == QEvent.Type.KeyRelease:
            self._pressed_keys.discard(key)
            self._ignored_until_release.discard(key)
            return self.is_active
        if event.type() != QEvent.Type.KeyPress:
            return False
        self._pressed_keys.add(key)
        if self.state is not CaptureState.WAITING:
            return self.state is CaptureState.CANDIDATE
        if key in self._ignored_until_release:
            return True
        if event.isAutoRepeat():
            return True
        if key == int(Qt.Key.Key_Escape):
            self.cancel("Esc")
            return True
        unobserved_modifiers = {
            modifier_key
            for modifier_flag, modifier_key in _MODIFIER_KEYS_BY_FLAG
            if event.modifiers() & modifier_flag and modifier_key not in self._pressed_keys
        }
        if unobserved_modifiers:
            # The controller may have been created after a physical modifier
            # KeyDown.  Infer that preheld state from the first main-key event
            # instead of accepting a contaminated chord.
            self._pressed_keys.update(unobserved_modifiers)
            self._ignored_until_release.update(unobserved_modifiers)
            self._ignored_until_release.add(key)
            return True
        if not self._ignored_until_release.isdisjoint(_MODIFIER_KEY_VALUES):
            # A modifier held before capture began contaminates every chord
            # reported while it remains down.  Consume main keys as well until
            # the contaminated keys themselves have produced KeyUp; only a
            # later physical press may become the candidate.
            self._ignored_until_release.add(key)
            return True
        if key in _MODIFIER_KEY_VALUES:
            return True
        if key in {0, int(Qt.Key.Key_unknown)}:
            self.rejected.emit("取得不能な論理キー")
            return True
        try:
            portable = canonical_shortcut(QKeySequence(event.keyCombination()))
        except (TypeError, ValueError):
            self.rejected.emit("一段のキー組合せとして取得できない")
            return True
        if portable is None or shortcut_is_reserved(portable):
            self.rejected.emit("予約済みまたは割当不能なキー")
            return True
        target = self.target
        if target is None:  # defensive guard against re-entrant cancellation
            return True
        self._set_state(CaptureState.CANDIDATE)
        self.candidate_ready.emit(target, portable)
        return True

    def _handle_mouse_event(self, event: QMouseEvent) -> bool:
        button = event.button()
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonRelease:
            self._pressed_buttons.discard(button)
            self._ignored_buttons_until_release.discard(button)
            if button in self._captured_buttons_until_release:
                self._captured_buttons_until_release.discard(button)
                if button in self._double_click_buttons:
                    self._double_click_buttons.discard(button)
                else:
                    self._recent_captured_releases.add(button)
                return True
            return self.is_active
        if event_type == QEvent.Type.MouseButtonDblClick:
            self._pressed_buttons.add(button)
            if button in self._recent_captured_releases:
                self._recent_captured_releases.discard(button)
                self._captured_buttons_until_release.add(button)
                self._double_click_buttons.add(button)
                return True
            return self.is_active
        if event_type != QEvent.Type.MouseButtonPress:
            return False

        self._pressed_buttons.add(button)
        # A normal press cannot be the continuation represented by Qt's
        # MouseButtonDblClick event, so an old double-click guard is obsolete.
        self._recent_captured_releases.discard(button)
        if self.state is not CaptureState.WAITING:
            return self.state is CaptureState.CANDIDATE
        if button in self._ignored_buttons_until_release:
            return True
        if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
            self._ignored_buttons_until_release.add(button)
            self.rejected.emit("Meta/Windows修飾は割当不能")
            return True
        if self._pointer_has_preheld_modifiers(event.modifiers(), button=button):
            return True
        try:
            binding = mouse_button_binding(button, event.modifiers())
        except (TypeError, ValueError) as exc:
            self._ignored_buttons_until_release.add(button)
            self.rejected.emit(str(exc) or "対応していないマウスボタン")
            return True
        if binding is None:
            self._ignored_buttons_until_release.add(button)
            self.rejected.emit("対応していないマウスボタン")
            return True
        target = self.target
        if target is None:
            return True
        self._captured_buttons_until_release.add(button)
        self._set_state(CaptureState.CANDIDATE)
        self.candidate_ready.emit(target, binding)
        return True

    def _handle_wheel_event(self, event: QWheelEvent) -> bool:
        if self.state is not CaptureState.WAITING:
            return self.state is CaptureState.CANDIDATE
        if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
            self.rejected.emit("Meta/Windows修飾は割当不能")
            return True
        if self._pointer_has_preheld_modifiers(event.modifiers()):
            return True
        # Runtime dispatch and the canvas' fixed zoom both use angleDelta.
        # Do not capture a pixel-only token that the main window cannot replay.
        delta_y = event.angleDelta().y()
        if delta_y == 0:
            return True
        try:
            binding = wheel_binding(delta_y, event.modifiers())
        except (TypeError, ValueError) as exc:
            self.rejected.emit(str(exc) or "縦ホイール入力として取得できない")
            return True
        if binding is None:
            return True
        target = self.target
        if target is None:
            return True
        # A modal confirmation may run synchronously from candidate_ready.
        # Arm its inertial tail first so nested event processing cannot leak it.
        self.wheel_candidate_started.emit(event)
        self._set_state(CaptureState.CANDIDATE)
        self.candidate_ready.emit(target, binding)
        return True

    def _pointer_has_preheld_modifiers(
        self,
        modifiers: Qt.KeyboardModifier,
        *,
        button: Qt.MouseButton | None = None,
    ) -> bool:
        unobserved_modifiers = {
            modifier_key
            for modifier_flag, modifier_key in _MODIFIER_KEYS_BY_FLAG
            if modifiers & modifier_flag and modifier_key not in self._pressed_keys
        }
        if unobserved_modifiers:
            self._pressed_keys.update(unobserved_modifiers)
            self._ignored_until_release.update(unobserved_modifiers)
            if button is not None:
                self._ignored_buttons_until_release.add(button)
            return True
        if not self._ignored_until_release.isdisjoint(_MODIFIER_KEY_VALUES):
            if button is not None:
                self._ignored_buttons_until_release.add(button)
            return True
        return False

    def _set_state(self, state: CaptureState) -> None:
        if self.state is state:
            return
        self.state = state
        self.state_changed.emit(state)


ConflictResolver = Callable[[ShortcutConflict], str]
ConfirmationHook = Callable[[], bool]
ColorConfirmationHook = Callable[[tuple[tuple[int, int, float], ...]], bool]
PointerOverrideConfirmationHook = Callable[[str, str], bool]


class SettingsDialog(QDialog):
    """Settings work-copy editor with Apply/OK/Cancel transaction boundaries."""

    applied = Signal(object)

    CATEGORY_COLUMN = 0
    NAME_COLUMN = 1
    ID_COLUMN = 2
    TYPE_COLUMN = 3
    PRIMARY_COLUMN = 4
    SECONDARY_COLUMN = 5

    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        persist_callback: Callable[[AppSettings], None] | None = None,
        apply_callback: Callable[[AppSettings], None] | None = None,
        conflict_resolver: ConflictResolver | None = None,
        confirm_restore_all: ConfirmationHook | None = None,
        confirm_similar_colors: ColorConfirmationHook | None = None,
        confirm_pointer_override: PointerOverrideConfirmationHook | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setModal(True)
        self.resize(980, 650)
        self._applied_settings = settings
        self.work_copy = settings.work_copy()
        self._persist_callback = persist_callback
        self._apply_callback = apply_callback
        self._conflict_resolver = conflict_resolver
        self._confirm_restore_all = confirm_restore_all
        self._confirm_similar_colors = confirm_similar_colors
        self._confirm_pointer_override = confirm_pointer_override
        self._closing = False
        self._wheel_tail_until = 0.0
        self._wheel_tail_waits_for_end = False

        self.capture = ShortcutCaptureController(self)
        self.capture.wheel_candidate_started.connect(self._arm_wheel_tail)
        self.capture.candidate_ready.connect(self._candidate_ready)
        self.capture.rejected.connect(self._capture_rejected)
        self.capture.cancelled.connect(self._capture_cancelled)

        outer = QVBoxLayout(self)
        self.pages = QTabWidget(self)
        self.pages.addTab(self._build_general_page(), "一般・表示")
        self.pages.addTab(self._build_shortcut_page(), "操作割当")
        outer.addWidget(self.pages, 1)

        self.dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply,
            parent=self,
        )
        self.ok_button = self.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.cancel_button = self.dialog_buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.dialog_buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.ok_button.clicked.connect(self._ok)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.apply_changes)
        outer.addWidget(self.dialog_buttons)

        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

    @property
    def applied_settings(self) -> AppSettings:
        return self._applied_settings

    def _build_general_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        folders = QGroupBox("入出力フォルダ", page)
        folder_form = QFormLayout(folders)
        self.original_folder = QLineEdit(self.work_copy.original_folder, folders)
        self.ternary_folder = QLineEdit(self.work_copy.ternary_folder, folders)
        self.output_folder = QLineEdit(self.work_copy.output_folder, folders)
        folder_form.addRow("原画像", self.original_folder)
        folder_form.addRow("入力三値画像", self.ternary_folder)
        folder_form.addRow("出力", self.output_folder)
        layout.addWidget(folders)

        view_group = QGroupBox("表示", page)
        view_form = QFormLayout(view_group)
        self.original_visible = QCheckBox("原画像を表示", view_group)
        self.original_visible.setChecked(self.work_copy.original_visible)
        self.ternary_visible = QCheckBox("三値画像を表示", view_group)
        self.ternary_visible.setChecked(self.work_copy.ternary_visible)
        self.pseudo_enabled = QCheckBox("疑似色", view_group)
        self.pseudo_enabled.setChecked(self.work_copy.pseudo_enabled)
        self.darken_comparison = QCheckBox("比較（暗）", view_group)
        self.darken_comparison.setChecked(self.work_copy.darken_comparison_enabled)
        self.darken_comparison.setToolTip(
            "原画像と三値画像の各色成分の暗い方を表示する（保存画像には影響しない）"
        )
        self.grid_auto = QCheckBox("画素格子を自動表示", view_group)
        self.grid_auto.setChecked(self.work_copy.grid_auto)
        self.small_components = QCheckBox("小領域を強調", view_group)
        self.small_components.setChecked(self.work_copy.small_components)
        self.original_opacity = QSpinBox(view_group)
        self.original_opacity.setRange(0, 100)
        self.original_opacity.setSuffix(" %")
        self.original_opacity.setValue(self.work_copy.original_opacity)
        view_form.addRow(self.original_visible)
        view_form.addRow(self.ternary_visible)
        view_form.addRow(self.pseudo_enabled)
        view_form.addRow(self.darken_comparison)
        view_form.addRow("原画像不透明度", self.original_opacity)
        view_form.addRow(self.grid_auto)
        view_form.addRow(self.small_components)
        layout.addWidget(view_group)

        color_group = QGroupBox("疑似色（#RRGGBB）", page)
        color_layout = QFormLayout(color_group)
        validator = QRegularExpressionValidator(QRegularExpression(r"#[0-9A-Fa-f]{6}"), self)
        self.color_edits: list[QLineEdit] = []
        self.color_buttons: list[QPushButton] = []
        self.color_reset_buttons: list[QPushButton] = []
        for index, label in enumerate(("無", "有", "境界")):
            row = QWidget(color_group)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(self.work_copy.pseudo_colors[index], row)
            edit.setValidator(validator)
            edit.textChanged.connect(lambda _text, i=index: self._update_color_swatch(i))
            choose = QPushButton("選択…", row)
            choose.clicked.connect(lambda _checked=False, i=index: self._choose_color(i))
            reset = QPushButton("既定", row)
            reset.clicked.connect(lambda _checked=False, i=index: self.reset_color(i))
            row_layout.addWidget(edit, 1)
            row_layout.addWidget(choose)
            row_layout.addWidget(reset)
            self.color_edits.append(edit)
            self.color_buttons.append(choose)
            self.color_reset_buttons.append(reset)
            color_layout.addRow(label, row)
        self.reset_all_colors_button = QPushButton("三色を既定へ戻す", color_group)
        self.reset_all_colors_button.clicked.connect(self.reset_all_colors)
        color_layout.addRow(self.reset_all_colors_button)
        layout.addWidget(color_group)
        for index in range(3):
            self._update_color_swatch(index)

        edit_group = QGroupBox("編集・境界", page)
        edit_form = QFormLayout(edit_group)
        self.tool = QComboBox(edit_group)
        self.tool.addItem("筆", "brush")
        self.tool.addItem("塗り潰し", "fill")
        self._select_data(self.tool, self.work_copy.tool)
        self.brush_shape = QComboBox(edit_group)
        self.brush_shape.addItem("円形", "circle")
        self.brush_shape.addItem("正方形", "square")
        self._select_data(self.brush_shape, self.work_copy.brush_shape)
        self.brush_diameter = QSpinBox(edit_group)
        self.brush_diameter.setRange(MIN_BRUSH_DIAMETER, MAX_BRUSH_DIAMETER)
        self.brush_diameter.setValue(self.work_copy.brush_diameter)
        self.boundary_mode = QComboBox(edit_group)
        self.boundary_mode.addItem("無側", "none_side")
        self.boundary_mode.addItem("非無側", "non_none_side")
        self._select_data(self.boundary_mode, self.work_copy.boundary_mode)
        self.boundary_thickness = QSpinBox(edit_group)
        self.boundary_thickness.setRange(MIN_BOUNDARY_THICKNESS, MAX_BOUNDARY_THICKNESS)
        self.boundary_thickness.setValue(self.work_copy.boundary_thickness)
        edit_form.addRow("起動時の道具", self.tool)
        edit_form.addRow("筆形状", self.brush_shape)
        edit_form.addRow("筆径", self.brush_diameter)
        edit_form.addRow("境界モード", self.boundary_mode)
        edit_form.addRow("境界太さ", self.boundary_thickness)
        layout.addWidget(edit_group)
        layout.addStretch(1)
        return page

    def _build_shortcut_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("絞り込み", page))
        self.shortcut_filter = QLineEdit(page)
        self.shortcut_filter.setPlaceholderText("操作名または操作ID")
        self.shortcut_filter.textChanged.connect(self._filter_shortcuts)
        filter_row.addWidget(self.shortcut_filter, 1)
        layout.addLayout(filter_row)

        self.shortcut_table = QTableWidget(len(OPERATION_SPECS), 6, page)
        self.shortcut_table.setHorizontalHeaderLabels(
            ("カテゴリ", "操作名", "操作ID", "操作型", "主割当", "副割当")
        )
        self.shortcut_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.shortcut_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.shortcut_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.shortcut_table.cellDoubleClicked.connect(self._cell_double_clicked)
        self.shortcut_table.currentCellChanged.connect(self._current_cell_changed)
        self.shortcut_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.shortcut_table, 1)

        button_row = QHBoxLayout()
        self.change_shortcut_button = QPushButton("変更", page)
        self.clear_shortcut_button = QPushButton("個別解除", page)
        self.restore_operation_button = QPushButton("操作の既定復元", page)
        self.restore_all_button = QPushButton("全体既定復元", page)
        self.change_shortcut_button.clicked.connect(self.begin_selected_capture)
        self.clear_shortcut_button.clicked.connect(self.clear_selected_shortcut)
        self.restore_operation_button.clicked.connect(self.restore_selected_operation)
        self.restore_all_button.clicked.connect(self.restore_all_shortcuts)
        for button in (
            self.change_shortcut_button,
            self.clear_shortcut_button,
            self.restore_operation_button,
            self.restore_all_button,
        ):
            button_row.addWidget(button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        self.capture_status = QLabel("", page)
        layout.addWidget(self.capture_status)
        self._refresh_shortcut_table()
        self.shortcut_table.setCurrentCell(0, self.PRIMARY_COLUMN)
        return page

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in {
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.WindowDeactivate,
        }:
            self.cancel_capture("アプリケーションが非アクティブになった")
            self.capture.reset_input_state()
            return False
        if isinstance(event, QWheelEvent) and self._consume_wheel_tail(event):
            event.accept()
            return True
        if event.type() in {
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
            *_MOUSE_EVENT_TYPES,
            QEvent.Type.Wheel,
        }:
            if self.capture.handle_event(event):
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def done(self, result: int) -> None:
        if not self._closing:
            self._closing = True
            self.cancel_capture("設定画面を閉じた")
            application = QApplication.instance()
            if application is not None:
                application.removeEventFilter(self)
        super().done(result)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.cancel_capture("設定画面を閉じた")
        super().closeEvent(event)

    def begin_capture(self, operation_id: str, slot: ShortcutSlot | str) -> None:
        if operation_id not in OPERATION_BY_ID:
            raise KeyError(operation_id)
        normalized_slot = ShortcutSlot(slot)
        row = self._row_for_operation(operation_id)
        column = (
            self.PRIMARY_COLUMN
            if normalized_slot is ShortcutSlot.PRIMARY
            else self.SECONDARY_COLUMN
        )
        self.shortcut_table.setCurrentCell(row, column)
        target = AssignmentTarget(operation_id, normalized_slot)
        self._clear_wheel_tail()
        self.capture.start(target)
        self.shortcut_table.item(row, column).setText("入力待機…")
        self.capture_status.setText("入力待機中：鍵盤またはマウスを操作（Escで中止）")

    def begin_selected_capture(self) -> None:
        target = self._selected_target(default_primary=True)
        if target is not None:
            self.begin_capture(target.operation_id, target.slot)

    def cancel_capture(self, reason: str = "取消") -> None:
        self._clear_wheel_tail()
        if self.capture.is_active:
            self.capture.cancel(reason)
        else:
            self.capture.clear_pointer_latches()

    def clear_selected_shortcut(self) -> None:
        self.cancel_capture("割当を解除した")
        target = self._selected_target()
        if target is None:
            return
        self.work_copy.shortcut_assignments.clear(target.operation_id, target.slot)
        self._refresh_shortcut_table()

    def restore_selected_operation(self) -> None:
        self.cancel_capture("既定を復元した")
        target = self._selected_target(default_primary=True)
        if target is None:
            return
        preview = self.work_copy.shortcut_assignments.copy()
        spec = OPERATION_BY_ID[target.operation_id]
        for slot, value in (
            (ShortcutSlot.PRIMARY, spec.primary),
            (ShortcutSlot.SECONDARY, spec.secondary),
        ):
            if value is None:
                preview.clear(target.operation_id, slot)
                continue
            requested = AssignmentTarget(target.operation_id, slot)
            owner = preview.owner_of(value)
            move = False
            if owner is not None and owner != requested:
                conflict = ShortcutConflict(value, owner, requested)
                if owner.operation_id == target.operation_id:
                    self.capture_status.setText("既定割当が同一操作内で重複している")
                    return
                if self._resolve_conflict(conflict) != "move":
                    self.capture_status.setText("既定復元を中止｜割当は変更なし")
                    return
                move = True
            preview.assign(target.operation_id, slot, value, move_conflict=move)
        self.work_copy.shortcut_assignments = preview
        self._refresh_shortcut_table()

    def restore_all_shortcuts(self) -> None:
        self.cancel_capture("全体既定復元")
        confirmed = (
            self._confirm_restore_all()
            if self._confirm_restore_all is not None
            else QMessageBox.question(
                self,
                "入力割当の初期化確認",
                "全ての入力割当を既定値へ戻します。現在の割当は失われます。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )
        if not confirmed:
            return
        self.work_copy.shortcut_assignments.restore_all()
        self._refresh_shortcut_table()

    def reset_color(self, index: int) -> None:
        if not 0 <= index < 3:
            raise IndexError(index)
        self.color_edits[index].setText(DEFAULT_PSEUDO_COLORS[index])

    def reset_all_colors(self) -> None:
        for index in range(3):
            self.reset_color(index)

    def apply_changes(self) -> bool:
        self.cancel_capture("設定を適用した")
        try:
            self._collect_general_values()
            candidate = self.work_copy.to_settings()
        except (TypeError, ValueError) as exc:
            self.capture_status.setText(str(exc))
            return False
        close_pairs = close_color_pairs(candidate.pseudo_colors)
        if close_pairs and not self._confirm_close_colors(close_pairs):
            return False
        try:
            if self._persist_callback is not None:
                self._persist_callback(candidate)
            if self._apply_callback is not None:
                self._apply_callback(candidate)
        except Exception as exc:  # noqa: BLE001 - persistence/application boundary
            self.capture_status.setText(f"設定適用エラー：{exc}")
            return False
        self._applied_settings = candidate
        self.work_copy = candidate.work_copy()
        self._refresh_shortcut_table()
        self.applied.emit(candidate)
        self.capture_status.setText("設定を適用した")
        return True

    def _ok(self) -> None:
        if self.apply_changes():
            self.accept()

    def _confirm_close_colors(self, pairs: tuple[tuple[int, int, float], ...]) -> bool:
        if self._confirm_similar_colors is not None:
            return self._confirm_similar_colors(pairs)
        names = ("無", "有", "境界")
        detail = "\n".join(
            f"{names[first]} / {names[second]}: {distance:.1f}" for first, second, distance in pairs
        )
        return (
            QMessageBox.warning(
                self,
                "疑似色の識別性",
                "次の組合せは色差が64未満で、識別しにくい可能性があります。"
                f"\n{detail}\n\nこの設定を適用しますか。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _collect_general_values(self) -> None:
        self.work_copy.original_folder = self.original_folder.text()
        self.work_copy.ternary_folder = self.ternary_folder.text()
        self.work_copy.output_folder = self.output_folder.text()
        self.work_copy.original_visible = self.original_visible.isChecked()
        self.work_copy.ternary_visible = self.ternary_visible.isChecked()
        self.work_copy.pseudo_enabled = self.pseudo_enabled.isChecked()
        self.work_copy.darken_comparison_enabled = self.darken_comparison.isChecked()
        self.work_copy.pseudo_colors = [
            normalize_hex_color(edit.text()) for edit in self.color_edits
        ]
        self.work_copy.original_opacity = self.original_opacity.value()
        self.work_copy.grid_auto = self.grid_auto.isChecked()
        self.work_copy.small_components = self.small_components.isChecked()
        self.work_copy.tool = str(self.tool.currentData())
        self.work_copy.brush_shape = str(self.brush_shape.currentData())
        self.work_copy.brush_diameter = self.brush_diameter.value()
        self.work_copy.boundary_mode = str(self.boundary_mode.currentData())
        self.work_copy.boundary_thickness = self.boundary_thickness.value()

    def _candidate_ready(self, target: AssignmentTarget, binding: str) -> None:
        # End capture before opening any confirmation dialog.  Otherwise this
        # application's event filter would also consume the dialog's clicks.
        self.capture.finish()
        try:
            normalized = canonical_binding(binding)
        except (TypeError, ValueError) as exc:
            self.capture_status.setText(f"割当不能な入力: {exc}")
            self._refresh_shortcut_table()
            return
        if normalized is None:
            self.capture_status.setText("割当不能な入力")
            self._refresh_shortcut_table()
            return
        owner = self.work_copy.shortcut_assignments.owner_of(normalized)
        move_conflict = False
        if owner is not None and owner != target:
            conflict = ShortcutConflict(normalized, owner, target)
            if owner.operation_id == target.operation_id:
                self.capture_status.setText("同じ操作の主・副へ同一入力は登録できない")
                self._refresh_shortcut_table()
                return
            resolution = self._resolve_conflict(conflict)
            if resolution != "move":
                self.capture_status.setText("競合解消を中止｜割当は変更なし")
                self._refresh_shortcut_table()
                return
            move_conflict = True
        preview = self.work_copy.shortcut_assignments.copy()
        try:
            result = preview.assign(
                target.operation_id,
                target.slot,
                normalized,
                move_conflict=move_conflict,
            )
        except (TypeError, ValueError) as exc:
            self.capture_status.setText(
                self._assignment_error_text(target, normalized, fallback=str(exc))
            )
            self._refresh_shortcut_table()
            return
        if (
            result.status is AssignmentStatus.APPLIED
            and not self._confirm_fixed_pointer_override(normalized)
        ):
            self.capture_status.setText("固定マウス操作の置換を中止｜割当は変更なし")
            self._refresh_shortcut_table()
            return
        if result.status in {AssignmentStatus.APPLIED, AssignmentStatus.UNCHANGED}:
            self.work_copy.shortcut_assignments = preview
            self.capture_status.setText(f"候補: {native_binding(normalized)}")
        else:
            self.capture_status.setText("割当を変更しなかった")
        self._refresh_shortcut_table()

    @staticmethod
    def _assignment_error_text(
        target: AssignmentTarget,
        binding: str,
        *,
        fallback: str,
    ) -> str:
        spec = OPERATION_BY_ID[target.operation_id]
        if spec.operation_type is OperationType.HOLD and pointer_base(binding) in {
            "WheelUp",
            "WheelDown",
        }:
            return "割当不可：ホイール入力は保持操作に使用不可"
        if target.operation_id == "view.temporary-pan" and pointer_base(binding) == "MouseLeft":
            return "割当不可：左ボタンは描画と衝突するため、一時パン操作に使用不可"
        return f"割当不可：{fallback}"

    def _confirm_fixed_pointer_override(self, binding: str) -> bool:
        if not binding_is_pointer(binding):
            return True
        fixed_effects = {
            "WheelUp": "画布上の指示位置を中心とする拡大",
            "WheelDown": "画布上の指示位置を中心とする縮小",
            "MouseMiddle": "中央ボタンのドラッグによる自由移動",
            "MouseLeft": "左ボタンによる描画・塗り潰し",
        }
        effect = fixed_effects.get(pointer_base(binding))
        if effect is None:
            return True
        if self._confirm_pointer_override is not None:
            return self._confirm_pointer_override(binding, effect)
        return (
            QMessageBox.warning(
                self,
                "固定マウス操作の変更確認",
                f"{native_binding(binding)} を割り当てると、固定操作「{effect}」は"
                "この入力で利用できなくなります。\n\n割当を変更しますか。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _resolve_conflict(self, conflict: ShortcutConflict) -> str:
        if self._conflict_resolver is not None:
            return self._conflict_resolver(conflict)
        owner = OPERATION_BY_ID[conflict.owner.operation_id]
        requested = OPERATION_BY_ID[conflict.requested.operation_id]
        answer = QMessageBox.question(
            self,
            "入力割当の競合確認",
            f"{native_binding(conflict.sequence)} は「{owner.name}」に割当済みです。\n"
            f"既存割当を解除し、「{requested.name}」へ移動しますか。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return "move" if answer == QMessageBox.StandardButton.Yes else "cancel"

    def _capture_rejected(self, reason: str) -> None:
        self.capture_status.setText(f"割当不可：{reason}。別の入力を操作（Escで中止）")

    def _capture_cancelled(self, reason: str) -> None:
        self.capture_status.setText(f"入力待機を中止｜理由：{reason}")
        self._refresh_shortcut_table()

    def _arm_wheel_tail(self, event: QWheelEvent) -> None:
        phase = event.phase()
        if phase == Qt.ScrollPhase.ScrollEnd:
            self._clear_wheel_tail()
            return
        self._wheel_tail_waits_for_end = phase != Qt.ScrollPhase.NoScrollPhase
        timeout = (
            _WHEEL_TAIL_PHASE_TIMEOUT_SECONDS
            if self._wheel_tail_waits_for_end
            else _WHEEL_TAIL_NO_PHASE_SECONDS
        )
        self._wheel_tail_until = monotonic() + timeout

    def _consume_wheel_tail(self, event: QWheelEvent) -> bool:
        if self._wheel_tail_until <= 0:
            return False
        if monotonic() > self._wheel_tail_until:
            self._clear_wheel_tail()
            return False
        if event.phase() == Qt.ScrollPhase.ScrollEnd:
            self._clear_wheel_tail()
        elif self._wheel_tail_waits_for_end:
            self._wheel_tail_until = monotonic() + _WHEEL_TAIL_PHASE_TIMEOUT_SECONDS
        return True

    def _clear_wheel_tail(self) -> None:
        self._wheel_tail_until = 0.0
        self._wheel_tail_waits_for_end = False

    def _cell_double_clicked(self, row: int, column: int) -> None:
        if column not in {self.PRIMARY_COLUMN, self.SECONDARY_COLUMN}:
            return
        operation_id = self._operation_for_row(row)
        slot = ShortcutSlot.PRIMARY if column == self.PRIMARY_COLUMN else ShortcutSlot.SECONDARY
        self.begin_capture(operation_id, slot)

    def _current_cell_changed(
        self,
        current_row: int,
        current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if not self.capture.is_active or self.capture.target is None:
            return
        if current_row < 0:
            self.cancel_capture("別欄を選択した")
            return
        if current_column not in {self.PRIMARY_COLUMN, self.SECONDARY_COLUMN}:
            self.cancel_capture("別欄を選択した")
            return
        operation_id = self._operation_for_row(current_row)
        slot = (
            ShortcutSlot.SECONDARY
            if current_column == self.SECONDARY_COLUMN
            else ShortcutSlot.PRIMARY
        )
        if AssignmentTarget(operation_id, slot) != self.capture.target:
            self.cancel_capture("別欄を選択した")

    def _selected_target(self, *, default_primary: bool = False) -> AssignmentTarget | None:
        row = self.shortcut_table.currentRow()
        if row < 0:
            return None
        column = self.shortcut_table.currentColumn()
        if column == self.SECONDARY_COLUMN:
            slot = ShortcutSlot.SECONDARY
        elif column == self.PRIMARY_COLUMN or default_primary:
            slot = ShortcutSlot.PRIMARY
        else:
            return None
        return AssignmentTarget(self._operation_for_row(row), slot)

    def _refresh_shortcut_table(self) -> None:
        target = self.capture.target if self.capture.is_active else None
        for row, spec in enumerate(OPERATION_SPECS):
            bindings = self.work_copy.shortcut_assignments.binding(spec.operation_id)
            values = (
                spec.category,
                spec.name,
                spec.operation_id,
                self._operation_type_text(spec.operation_type.value, spec.effect),
                native_binding(bindings.primary) or "なし",
                native_binding(bindings.secondary) or "なし",
            )
            for column, value in enumerate(values):
                item = self.shortcut_table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.shortcut_table.setItem(row, column, item)
                item.setText(value)
                item.setData(Qt.ItemDataRole.UserRole, spec.operation_id)
            if target is not None and target.operation_id == spec.operation_id:
                column = (
                    self.PRIMARY_COLUMN
                    if target.slot is ShortcutSlot.PRIMARY
                    else self.SECONDARY_COLUMN
                )
                self.shortcut_table.item(row, column).setText("入力待機…")

    def _filter_shortcuts(self, text: str) -> None:
        self.cancel_capture("絞り込みを変更した")
        query = text.casefold().strip()
        for row, spec in enumerate(OPERATION_SPECS):
            haystack = f"{spec.name}\n{spec.operation_id}".casefold()
            self.shortcut_table.setRowHidden(row, bool(query and query not in haystack))

    def _choose_color(self, index: int) -> None:
        try:
            initial = QColor(*rgb_from_hex(self.color_edits[index].text()))
        except (TypeError, ValueError):
            initial = QColor(*rgb_from_hex(DEFAULT_PSEUDO_COLORS[index]))
        selected = QColorDialog.getColor(initial, self, "疑似色を選択")
        if selected.isValid():
            self.color_edits[index].setText(selected.name(QColor.NameFormat.HexRgb).upper())

    def _update_color_swatch(self, index: int) -> None:
        try:
            color = normalize_hex_color(self.color_edits[index].text())
        except (TypeError, ValueError):
            self.color_buttons[index].setStyleSheet("")
            return
        self.color_buttons[index].setStyleSheet(f"background-color: {color};")

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(index, 0))

    @staticmethod
    def _operation_type_text(operation_type: str, effect: str | None) -> str:
        names = {"single": "単発", "step": "刻み", "hold": "保持"}
        base = names[operation_type]
        return base if effect is None else f"{base}・{effect}"

    @staticmethod
    def _operation_for_row(row: int) -> str:
        if not 0 <= row < len(OPERATION_SPECS):
            raise IndexError(row)
        return OPERATION_SPECS[row].operation_id

    @staticmethod
    def _row_for_operation(operation_id: str) -> int:
        for row, spec in enumerate(OPERATION_SPECS):
            if spec.operation_id == operation_id:
                return row
        raise KeyError(operation_id)


__all__ = [
    "CaptureState",
    "SettingsDialog",
    "ShortcutCaptureController",
]
