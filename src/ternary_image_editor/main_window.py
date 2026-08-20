"""三値画像修正GUIの主画面と状態遷移。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QEvent, QObject, QSettings, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeyEvent, QMouseEvent, QShowEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .action_registry import (
    ActionRegistry,
    ShortcutAssignments,
    mouse_button_binding,
    wheel_binding,
)
from .canvas import BrushShape, EditTool, ImageCanvas
from .constants import (
    LABEL_NAMES,
    SAVE_RGB,
    TERNARY_JPEG_EXTENSIONS,
    Label,
    protected_start_y,
)
from .control_panel import EditorControls
from .dialogs import (
    ExternalChangeChoice,
    FolderSelectionDialog,
    InputChangeChoice,
    UnsavedChoice,
    ask_external_change,
    ask_input_change,
    ask_unsaved,
    confirm_natural_pairing,
    confirm_overwrite,
    confirm_ternary_jpeg_import,
    show_error,
    show_information,
)
from .errors import (
    BusyError,
    ExternalModificationError,
    ExternalOutputModificationError,
    ExternalSourceModificationError,
    ImageValidationError,
    PairDimensionError,
)
from .history import HistoryEntry, HistoryTrimReport
from .image_io import fingerprint_file, normalized_protected_labels_copy
from .memo_history import MemoDelta
from .models import EditSource, ImagePair, PairingMode, PairingResult
from .operations import (
    SmallComponentsResult,
    brush_segment_footprint,
    find_small_components,
    flood_fill4,
    generate_boundary_non_none_side,
    generate_boundary_none_side,
    paint_brush_footprint,
)
from .pairing import finalize_pairing, plan_pairing
from .session import Activity, ImageSession
from .settings_model import AppSettings, SettingsRepository, hex_from_rgb, rgb_from_hex
from .workers import FunctionWorker, TaskFailure, TaskSuccess, TaskToken


@dataclass(slots=True)
class _ActiveJob:
    token: TaskToken
    description: str
    on_success: Callable[[Any], None]
    on_failure: Callable[[Exception], None]


@dataclass(slots=True)
class _PreparedPairingOpen:
    index: int
    source: EditSource
    session: ImageSession
    pair_errors: dict[int, str]
    output_errors: dict[int, str]
    transient_errors: dict[int, str]
    output_error_snapshots: dict[int, tuple[Any, ...]]


class MainWindow(QMainWindow):
    """一画像だけを所有し、遷移と長処理を取引境界で直列化する。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
        expected_size: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("三値画像修正")
        self.resize(1440, 920)

        self.settings = settings or QSettings("TernaryImageEditor", "TernaryImageEditor")
        self.settings_repository = SettingsRepository(self.settings)
        try:
            self.applied_settings = self.settings_repository.load()
        except (TypeError, ValueError):
            self.applied_settings = AppSettings()
        self.action_registry = ActionRegistry(
            self,
            assignments=ShortcutAssignments(self.applied_settings.shortcuts),
        )
        self.expected_size = expected_size
        self.session = ImageSession()
        self.thread_pool = QThreadPool.globalInstance()

        self._pairs: list[ImagePair] = []
        self._pairing_result = PairingResult()
        self._folders: tuple[Path, Path, Path] | None = None
        self._pairing_mode = self._stored_pairing_mode()
        self._current_index: int | None = None
        self._pair_errors: dict[int, str] = {}
        self._output_errors: dict[int, str] = {}
        self._transient_open_errors: dict[int, str] = {}
        self._output_error_snapshots: dict[int, tuple[Any, ...]] = {}
        self._accepted_input_fallbacks: dict[int, tuple[Any, ...]] = {}
        self._active_job: _ActiveJob | None = None
        self._jobs: dict[int, _ActiveJob] = {}
        self._latest_component_token: TaskToken | None = None
        self._component_rerun_needed = False
        self._active_worker: FunctionWorker | None = None
        self._workers: list[FunctionWorker] = []
        self._close_after_activity = False
        self._allow_close_once = False
        self._geometry_checked = False
        self._needs_initial_overwrite_confirmation = False
        self._selected_label = int(Label.PRESENT)
        self._stroke_before: np.ndarray | None = None
        self._stroke_last_point: tuple[float, float] | None = None
        self._stroke_label = int(Label.PRESENT)
        self._stroke_diameter = 5
        self._stroke_shape = "circle"
        self._active_pointer_bindings: dict[Qt.MouseButton, str] = {}

        self.canvas = ImageCanvas(self)
        self.controls = EditorControls(self)
        self.image_list = QListWidget(self)
        self.image_list.setObjectName("imageList")
        self.image_list.setMinimumHeight(130)
        self.error_list = QListWidget(self)
        self.error_list.setObjectName("excludedList")
        self.error_list.setMinimumHeight(100)

        self._build_actions()
        self._build_layout()
        self._build_status_bar()
        self._connect_controls()
        self._restore_settings()
        self._update_interface()
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
        startup_folders = self._stored_folders()
        QTimer.singleShot(
            0,
            lambda folders=startup_folders: self._restore_folders_on_startup(folders),
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        event_type = event.type()
        if event_type == QEvent.Type.ApplicationDeactivate or (
            watched is self and event_type == QEvent.Type.WindowDeactivate
        ):
            self._release_pointer_inputs()
            self.canvas.cancel_navigation_input()
            self._cancel_active_brush("筆跡を取消｜理由：画面の非アクティブ化")
        elif watched is self.canvas and event_type in {
            QEvent.Type.FocusOut,
            QEvent.Type.UngrabMouse,
        }:
            self._release_pointer_inputs()
            self.canvas.cancel_navigation_input()
            reason = (
                "筆跡を取消｜理由：ポインタ捕捉の喪失"
                if event_type == QEvent.Type.UngrabMouse
                else "筆跡を取消｜理由：焦点の喪失"
            )
            self._cancel_active_brush(reason)

        if event_type == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            pressed_binding = self._active_pointer_bindings.pop(event.button(), None)
            if pressed_binding is not None:
                self.action_registry.dispatch_pointer_release(pressed_binding)
                return True

        if event_type in {QEvent.Type.KeyPress, QEvent.Type.KeyRelease} and isinstance(
            event, QKeyEvent
        ):
            belongs_to_window = isinstance(watched, QWidget) and (
                watched is self or self.isAncestorOf(watched)
            )
            modal = QApplication.activeModalWidget()
            if belongs_to_window and (modal is None or modal is self):
                if self._stroke_before is not None or self.canvas.memo_stroke_active:
                    if event_type == QEvent.Type.KeyRelease:
                        # 進行中操作へ新命令は割り込ませないが、既に押下済みの
                        # HOLD解放だけは必ず通し、Space等の状態を残留させない。
                        self.action_registry.dispatch_event(event)
                    if (
                        event_type == QEvent.Type.KeyPress
                        and event.key() == Qt.Key.Key_Escape
                        and not event.isAutoRepeat()
                    ):
                        if self.canvas.memo_stroke_active:
                            self.canvas.cancel_memo_stroke("メモ取消｜理由：Esc入力")
                        else:
                            self._cancel_active_brush("筆跡を取消｜理由：Esc入力")
                    return True
                text_input = self._is_editable_input(watched) or self._text_input_has_focus()
                if self.action_registry.dispatch_event(
                    event,
                    text_input=text_input,
                ):
                    return True

        if watched is not self.canvas:
            return super().eventFilter(watched, event)
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not self:
            return super().eventFilter(watched, event)

        if event_type == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
            if self._stroke_before is not None or self.canvas.memo_stroke_active:
                return True
            try:
                delta_y = event.angleDelta().y() or event.pixelDelta().y()
                binding = wheel_binding(delta_y, event.modifiers())
            except ValueError:
                binding = None
            if binding is not None and self.action_registry.dispatch_pointer_press(binding):
                return True

        if isinstance(event, QMouseEvent) and event_type in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        }:
            if self._stroke_before is not None or self.canvas.memo_stroke_active:
                return True
            # Spaceや一時パンGUIとの組合せはMouseLeft単体とは別の既存操作だ。
            # 左割当を設けても、その退避経路まで奪わない。
            if (
                event.button() == Qt.MouseButton.LeftButton
                and self.canvas.temporary_pan_active
            ):
                return super().eventFilter(watched, event)
            try:
                binding = mouse_button_binding(event.button(), event.modifiers())
            except ValueError:
                binding = None
            if (
                binding is not None
                and self.action_registry.operation_for_binding(binding) is not None
            ):
                previous = self._active_pointer_bindings.pop(event.button(), None)
                if previous is not None:
                    self.action_registry.dispatch_pointer_release(previous)
                # Register before invocation: a SINGLE callback may open a
                # synchronous modal loop in which the physical Release and a
                # settings replacement both occur.  Never recreate that latch
                # after the nested loop has already cleared it.
                self._active_pointer_bindings[event.button()] = binding
                self.action_registry.dispatch_pointer_press(binding)
                return True

        if (
            (self._stroke_before is not None or self.canvas.memo_stroke_active)
            and isinstance(event, QMouseEvent)
            and event_type == QEvent.Type.MouseButtonRelease
            and not (
                self.canvas.memo_stroke_active
                and event.button() == Qt.MouseButton.RightButton
            )
            and not (
                self._stroke_before is not None
                and event.button() == Qt.MouseButton.LeftButton
            )
        ):
            return True
        return super().eventFilter(watched, event)

    def _release_pointer_inputs(self) -> None:
        self._active_pointer_bindings.clear()
        self.action_registry.release_all_holds()
        self.canvas.cancel_memo_stroke("メモ取消｜理由：入力状態の解除")

    def _cancel_active_brush(self, reason: str) -> None:
        if self._stroke_before is None:
            return
        cancel = getattr(self.canvas, "cancel_brush", None)
        if callable(cancel):
            if not cancel(reason):
                self._cancel_brush(reason)
        elif hasattr(self.canvas, "_brushing"):
            self.canvas._brushing = False
            self._cancel_brush(reason)

    @property
    def pairs(self) -> tuple[ImagePair, ...]:
        return tuple(self._pairs)

    @property
    def current_index(self) -> int | None:
        return self._current_index

    def configure_folders(
        self,
        original_dir: Path,
        ternary_dir: Path,
        output_dir: Path,
        *,
        pairing_mode: PairingMode | str = PairingMode.STRICT_KEY,
        natural_order_confirmed: bool = False,
    ) -> PairingResult:
        """検査済み画像一覧を導入する。競合中は ``BusyError`` を送出する。"""

        self._ensure_direct_transition_allowed()
        mode = PairingMode(pairing_mode)
        result = plan_pairing(original_dir, ternary_dir, output_dir, mode=mode)
        if result.confirmation_required and not natural_order_confirmed:
            raise ValueError("自然順対応は全対応表の明示確認が必要")
        if result.blocking_reason is not None or not result.pairs:
            return result
        finalize_pairing(result, output_dir)
        self._install_pairing(result, (original_dir, ternary_dir, output_dir))
        return result

    def open_pair(
        self,
        index: int,
        source: EditSource | None = None,
    ) -> bool:
        """指定画像対を開く。編集元省略時は正常な既存出力を優先する。

        競合中は ``BusyError`` を送出する。
        """

        self._ensure_direct_transition_allowed()
        fallback_output_snapshot: tuple[Any, ...] | None = None
        if source is None:
            if not 0 <= index < len(self._pairs):
                return False
            resolved_source = self._choose_edit_source(self._pairs[index], index)
            if resolved_source == EditSource.INPUT:
                fallback_output_snapshot = self._accepted_input_fallbacks.get(index)
        else:
            resolved_source = source
        return self._open_pair(
            index,
            resolved_source,
            fallback_output_snapshot=fallback_output_snapshot,
        )

    def _ensure_direct_transition_allowed(self) -> None:
        """試験・埋込み用の直接入口にも通常GUIと同じ排他境界を課す。"""

        if self._active_job is not None:
            raise BusyError("書込処理中は画像集合を切り替えられない")
        if self._stroke_before is not None:
            raise BusyError("未確定の筆操作中は画像集合を切り替えられない")

    def request_open_index(self, index: int) -> None:
        if (
            index == self._current_index
            or not 0 <= index < len(self._pairs)
            or index in self._pair_errors
        ):
            self._sync_list_selection()
            return
        if self._active_job is not None:
            self._message("処理中は画像を移動できない")
            self._sync_list_selection()
            return
        if self._stroke_before is not None:
            self._message("画像移動不可：筆操作が未確定")
            self._sync_list_selection()
            return
        pair = self._pairs[index]
        source = self._choose_edit_source(pair, index)
        jpeg_confirmed = self._preconfirm_ternary_jpeg(pair, source)
        if jpeg_confirmed is None:
            self._sync_list_selection()
            return
        self._with_unsaved_resolution(
            "画像移動",
            lambda: self._open_pair(
                index,
                source,
                jpeg_confirmed=jpeg_confirmed,
                fallback_output_snapshot=(
                    self._accepted_input_fallbacks.get(index)
                    if source == EditSource.INPUT
                    else None
                ),
            ),
        )

    def request_save(self, *, continuation: Callable[[], None] | None = None) -> None:
        if not self.session.is_loaded:
            return
        if not self._pairing_result.output_writable:
            self._message(self._pairing_result.output_warning or "出力先へ書き込めない")
            return
        if self._active_job is not None:
            self._message("別の処理が完了するまで保存できない")
            return
        if self._stroke_before is not None:
            self._message("保存不可：筆操作が未確定")
            return
        if self.canvas.memo_stroke_active:
            self._message("保存不可｜メモ一筆が未確定")
            return
        assert self.session.pair is not None
        allow_existing_output = False
        if self._needs_initial_overwrite_confirmation:
            if not confirm_overwrite(self, self.session.pair.output_path):
                return
            allow_existing_output = True
        self._start_save(
            force=False,
            allow_existing_output=allow_existing_output,
            continuation=continuation,
        )

    def _build_actions(self) -> None:
        callbacks: dict[str, Callable[[], None]] = {
            "file.configure-folders": self._choose_folders,
            "file.rescan-folders": self._rescan_folders,
            "file.save": self.request_save,
            "app.open-settings": self._open_settings,
            "app.exit": self.close,
            "edit.undo": self._undo,
            "edit.redo": self._redo,
            "navigate.previous-image": self._go_previous,
            "navigate.next-image": self._go_next,
            "tool.brush": lambda: self.controls.select_tool("brush"),
            "tool.fill": lambda: self.controls.select_tool("fill"),
            "label.select-none": lambda: self.controls.select_label(0),
            "label.select-present": lambda: self.controls.select_label(1),
            "label.select-boundary": lambda: self.controls.select_label(2),
            "label.cycle-forward": lambda: self._cycle_label(1),
            "label.cycle-backward": lambda: self._cycle_label(-1),
            "brush.decrease-size": lambda: self.controls.adjust_brush_diameter(-1),
            "brush.increase-size": lambda: self.controls.adjust_brush_diameter(1),
            "brush.shape-circle": lambda: self.controls.select_brush_shape("circle"),
            "brush.shape-square": lambda: self.controls.select_brush_shape("square"),
            "brush.cycle-shape": self.controls.cycle_brush_shape,
            "view.toggle-original": self.controls.original_visible.toggle,
            "view.toggle-label": self.controls.ternary_visible.toggle,
            "view.toggle-pseudocolor": self.controls.pseudo_enabled.toggle,
            "view.toggle-darken-comparison": self.controls.darken_comparison.toggle,
            "view.toggle-grid-auto": self.controls.grid_enabled.toggle,
            "view.toggle-small-components": self.controls.small_components.toggle,
            "view.decrease-original-opacity": lambda: self._adjust_opacity(-5),
            "view.increase-original-opacity": lambda: self._adjust_opacity(5),
            "view.zoom-out": lambda: self._zoom_by(1.0 / 1.25),
            "view.zoom-in": lambda: self._zoom_by(1.25),
            "view.zoom-100": self.canvas.set_actual_size,
            "view.fit-image": self.canvas.fit_to_view,
            "boundary.select-none-side": lambda: self.controls.select_boundary_mode("none_side"),
            "boundary.select-non-none-side": lambda: self.controls.select_boundary_mode(
                "non_none_side"
            ),
            "boundary.decrease-thickness": lambda: self.controls.adjust_boundary_thickness(-1),
            "boundary.increase-thickness": lambda: self.controls.adjust_boundary_thickness(1),
            "boundary.generate": self._request_selected_boundary,
        }
        self._operation_actions: dict[str, QAction] = {}
        for operation_id, callback in callbacks.items():
            self.action_registry.register(
                operation_id,
                callback,
                enabled=lambda op=operation_id: self._operation_is_enabled(op),
            )
        self.action_registry.register(
            "view.temporary-pan",
            on_press=self._temporary_pan_started,
            on_release=self._temporary_pan_ended,
            enabled=lambda: self._operation_is_enabled("view.temporary-pan"),
        )

        for operation_id in (*callbacks, "view.temporary-pan"):
            action = self.action_registry.create_action(
                operation_id,
                self,
                # 鍵盤経路はeventFilterへ一本化する。QtのQAction shortcutも
                # 同時に有効化すると、編集可能欄でKEY-004抑止後に再発火する。
                install_native_shortcuts=False,
            )
            action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            self._operation_actions[operation_id] = action
            self.addAction(action)
        for operation_id in (
            "view.toggle-original",
            "view.toggle-label",
            "view.toggle-pseudocolor",
            "view.toggle-darken-comparison",
            "view.toggle-grid-auto",
            "view.toggle-small-components",
        ):
            self._operation_actions[operation_id].setCheckable(True)
        temporary_pan_action = self._operation_actions["view.temporary-pan"]
        temporary_pan_action.setCheckable(True)
        temporary_pan_action.setToolTip(
            "割当入力の保持中、またはこのGUI状態がONの間だけ左ドラッグでパンする"
        )
        temporary_pan_action.toggled.connect(self._temporary_pan_gui_toggled)

        self.folder_action = self._operation_actions["file.configure-folders"]
        self.rescan_action = self._operation_actions["file.rescan-folders"]
        self.save_action = self._operation_actions["file.save"]
        self.settings_action = self._operation_actions["app.open-settings"]
        self.exit_action = self._operation_actions["app.exit"]
        self.previous_action = self._operation_actions["navigate.previous-image"]
        self.next_action = self._operation_actions["navigate.next-image"]
        self.undo_action = self._operation_actions["edit.undo"]
        self.redo_action = self._operation_actions["edit.redo"]
        self.actual_size_action = self._operation_actions["view.zoom-100"]
        self.fit_action = self._operation_actions["view.fit-image"]
        self.boundary_action = self._operation_actions["boundary.generate"]
        self.single_key_actions = [
            self._operation_actions[operation_id]
            for operation_id in (
                "tool.brush",
                "tool.fill",
                "label.select-none",
                "label.select-present",
                "label.select-boundary",
                "label.cycle-forward",
                "label.cycle-backward",
                "brush.decrease-size",
                "brush.increase-size",
                "brush.shape-circle",
                "brush.shape-square",
                "brush.cycle-shape",
            )
        ]

        file_menu = self.menuBar().addMenu("ファイル")
        self._add_operations(
            file_menu,
            "file.configure-folders",
            "file.rescan-folders",
            "file.save",
        )
        file_menu.addSeparator()
        self._add_operations(file_menu, "app.open-settings", "app.exit")

        navigate_menu = self.menuBar().addMenu("画像移動")
        self._add_operations(
            navigate_menu,
            "navigate.previous-image",
            "navigate.next-image",
        )

        edit_menu = self.menuBar().addMenu("編集")
        self._add_operations(edit_menu, "edit.undo", "edit.redo")
        edit_menu.addSeparator()
        for operation_id in (
            "tool.brush",
            "tool.fill",
            "label.select-none",
            "label.select-present",
            "label.select-boundary",
            "label.cycle-forward",
            "label.cycle-backward",
            "brush.decrease-size",
            "brush.increase-size",
            "brush.shape-circle",
            "brush.shape-square",
            "brush.cycle-shape",
        ):
            edit_menu.addAction(self._operation_actions[operation_id])

        view_menu = self.menuBar().addMenu("表示")
        for operation_id in (
            "view.toggle-original",
            "view.toggle-label",
            "view.toggle-pseudocolor",
            "view.toggle-darken-comparison",
            "view.toggle-grid-auto",
            "view.toggle-small-components",
            "view.decrease-original-opacity",
            "view.increase-original-opacity",
            "view.zoom-out",
            "view.zoom-in",
            "view.zoom-100",
            "view.fit-image",
            "view.temporary-pan",
        ):
            view_menu.addAction(self._operation_actions[operation_id])

        boundary_menu = self.menuBar().addMenu("境界生成")
        for operation_id in (
            "boundary.select-none-side",
            "boundary.select-non-none-side",
            "boundary.decrease-thickness",
            "boundary.increase-thickness",
            "boundary.generate",
        ):
            boundary_menu.addAction(self._operation_actions[operation_id])

        help_menu = self.menuBar().addMenu("ヘルプ")
        help_menu.addAction("このアプリについて", self._show_about)

    def _add_operations(self, menu: Any, *operation_ids: str) -> None:
        for operation_id in operation_ids:
            menu.addAction(self._operation_actions[operation_id])

    def _build_layout(self) -> None:
        toolbar = QToolBar("主要操作", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self.folder_action)
        toolbar.addAction(self.rescan_action)
        toolbar.addSeparator()
        toolbar.addAction(self.previous_action)
        toolbar.addAction(self.next_action)
        toolbar.addSeparator()
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.actual_size_action)
        toolbar.addAction(self.fit_action)
        toolbar.addAction(self._operation_actions["view.temporary-pan"])
        toolbar.addAction(self.settings_action)
        toolbar.addWidget(QLabel(" 倍率 ", toolbar))
        self.zoom_spin = QDoubleSpinBox(toolbar)
        self.zoom_spin.setRange(5.0, 6400.0)
        self.zoom_spin.setDecimals(1)
        self.zoom_spin.setValue(100.0)
        self.zoom_spin.setSuffix(" %")
        self.zoom_spin.setKeyboardTracking(False)
        self.zoom_spin.setMinimumWidth(105)
        self.zoom_spin.editingFinished.connect(
            lambda: self.canvas.set_zoom_percent(self.zoom_spin.value())
        )
        toolbar.addWidget(self.zoom_spin)
        toolbar.addSeparator()
        self.toolbar_state = QLabel("未読込", toolbar)
        self.toolbar_state.setMinimumWidth(300)
        toolbar.addWidget(self.toolbar_state)

        controls_scroll = QScrollArea(self)
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(292)
        controls_scroll.setMaximumWidth(380)
        controls_scroll.setWidget(self.controls)

        horizontal = QSplitter(Qt.Orientation.Horizontal, self)
        horizontal.addWidget(self.canvas)
        horizontal.addWidget(controls_scroll)
        horizontal.setStretchFactor(0, 1)
        horizontal.setStretchFactor(1, 0)

        vertical = QSplitter(Qt.Orientation.Vertical, self)
        vertical.addWidget(horizontal)
        list_group = QGroupBox("有効画像一覧（出力有無）", self)
        list_layout = QVBoxLayout(list_group)
        list_layout.setContentsMargins(6, 6, 6, 6)
        list_layout.addWidget(self.image_list)

        error_group = QGroupBox("対象外・読込エラー", self)
        error_layout = QVBoxLayout(error_group)
        error_layout.setContentsMargins(6, 6, 6, 6)
        error_layout.addWidget(self.error_list)

        lists = QSplitter(Qt.Orientation.Horizontal, self)
        lists.addWidget(list_group)
        lists.addWidget(error_group)
        lists.setStretchFactor(0, 2)
        lists.setStretchFactor(1, 1)
        vertical.addWidget(lists)
        vertical.setStretchFactor(0, 1)
        vertical.setStretchFactor(1, 0)
        vertical.setSizes([740, 150])
        self.setCentralWidget(vertical)

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        self.coordinate_status = QLabel("座標: —", self)
        self.zoom_status = QLabel("倍率: —", self)
        self.brush_status = QLabel("筆径: 5 px", self)
        self.label_status = QLabel("選択色: 有｜#808080", self)
        self.protection_status = QLabel("保護: —", self)
        self.document_status = QLabel("未読込", self)
        for widget in (
            self.coordinate_status,
            self.zoom_status,
            self.brush_status,
            self.label_status,
            self.protection_status,
            self.document_status,
        ):
            status.addPermanentWidget(widget)

    def _connect_controls(self) -> None:
        self.controls.original_visibility_changed.connect(self._set_original_visibility)
        self.controls.ternary_visibility_changed.connect(self._set_ternary_visibility)
        self.controls.opacity_changed.connect(self._set_opacity)
        self.controls.pseudo_changed.connect(self._set_pseudo)
        self.controls.darken_comparison_changed.connect(self._set_darken_comparison)
        self.controls.pseudo_palette_changed.connect(self._set_pseudo_palette)
        self.controls.pseudo_settings_requested.connect(self._open_settings)
        self.controls.grid_changed.connect(self._set_grid)
        self.controls.tool_changed.connect(self._set_tool)
        self.controls.label_changed.connect(self._set_label)
        self.controls.label_cycle_requested.connect(
            lambda direction: self.action_registry.invoke(
                "label.cycle-forward" if direction >= 0 else "label.cycle-backward"
            )
        )
        self.controls.brush_shape_changed.connect(self._set_brush_shape)
        self.controls.brush_diameter_changed.connect(self._set_brush_diameter)
        self.controls.boundary_mode_changed.connect(self._set_boundary_mode)
        self.controls.boundary_thickness_changed.connect(self._set_boundary_thickness)
        self.controls.boundary_requested.connect(self._request_boundary)
        self.controls.small_components_changed.connect(self._set_small_components)

        self.canvas.brush_started.connect(self._brush_started)
        self.canvas.brush_moved.connect(self._brush_moved)
        self.canvas.brush_finished.connect(self._brush_finished)
        self.canvas.brush_cancelled.connect(self._cancel_brush)
        self.canvas.memo_stroke_committed.connect(self._memo_stroke_committed)
        self.canvas.memo_stroke_active_changed.connect(
            lambda _active: self._update_interface()
        )
        self.canvas.protected_cursor_changed.connect(self._protected_cursor_changed)
        self.canvas.fill_requested.connect(self._request_fill)
        self.canvas.cursor_position_changed.connect(self._cursor_changed)
        self.canvas.view_changed.connect(self._view_changed)
        self.canvas.interaction_blocked.connect(self._message)
        self.image_list.itemClicked.connect(self._list_item_selected)
        self.image_list.itemActivated.connect(self._list_item_selected)

    def _operation_is_enabled(self, operation_id: str) -> bool:
        loaded = self.session.is_loaded
        stroke = self._stroke_before is not None or self.canvas.memo_stroke_active
        blocking = self._job_is_blocking()
        transition = not blocking and not stroke
        labels_visible = self._labels_are_visible()

        if operation_id in {"file.configure-folders", "file.rescan-folders"}:
            return transition
        if operation_id == "file.save":
            return loaded and transition and self._pairing_result.output_writable
        if operation_id == "app.open-settings":
            return transition
        if operation_id == "app.exit":
            return not stroke
        if operation_id == "edit.undo":
            return (
                loaded
                and transition
                and self._history_entry_is_available(
                    self.session.history.next_undo_entry,
                    labels_visible=labels_visible,
                )
            )
        if operation_id == "edit.redo":
            return (
                loaded
                and transition
                and self._history_entry_is_available(
                    self.session.history.next_redo_entry,
                    labels_visible=labels_visible,
                )
            )
        if operation_id == "navigate.previous-image":
            return (
                transition
                and self._current_index is not None
                and self._adjacent_pair_index(self._current_index, -1) is not None
            )
        if operation_id == "navigate.next-image":
            return (
                transition
                and self._current_index is not None
                and self._adjacent_pair_index(self._current_index, 1) is not None
            )
        if operation_id.startswith(("tool.", "label.", "brush.", "boundary.")):
            return loaded and labels_visible and transition
        if operation_id in {
            "view.zoom-out",
            "view.zoom-in",
            "view.zoom-100",
            "view.fit-image",
            "view.temporary-pan",
        }:
            return loaded and not stroke
        if operation_id.startswith("view."):
            return not stroke
        return True

    def _adjust_opacity(self, delta: int) -> None:
        self.controls.opacity_slider.setValue(self.controls.opacity_slider.value() + delta)

    def _zoom_by(self, factor: float) -> None:
        if self._stroke_before is not None or not self.session.is_loaded:
            return
        self.canvas.set_zoom_percent(self.canvas.transform.scale * factor * 100.0)

    def _temporary_pan_started(self) -> None:
        self.canvas.set_space_pressed(True)
        action = getattr(self, "_operation_actions", {}).get("view.temporary-pan")
        if action is not None and not action.isChecked():
            blocked = action.blockSignals(True)
            action.setChecked(True)
            action.blockSignals(blocked)

    def _temporary_pan_ended(self) -> None:
        self.canvas.set_space_pressed(False)
        action = getattr(self, "_operation_actions", {}).get("view.temporary-pan")
        if action is not None and action.isChecked():
            blocked = action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(blocked)

    def _temporary_pan_gui_toggled(self, enabled: bool) -> None:
        token = "gui:view.temporary-pan"
        if enabled:
            self.action_registry.press("view.temporary-pan", key_token=token)
        else:
            self.action_registry.release("view.temporary-pan", key_token=token)

    @staticmethod
    def _text_input_has_focus() -> bool:
        return MainWindow._is_editable_input(QApplication.focusWidget())

    @staticmethod
    def _is_editable_input(widget: QObject | None) -> bool:
        if isinstance(widget, QLineEdit):
            return not widget.isReadOnly()
        if isinstance(widget, QAbstractSpinBox):
            return not widget.isReadOnly()
        return isinstance(widget, QComboBox) and widget.isEditable()

    def _choose_folders(self) -> None:
        if self._active_job is not None:
            self._message("処理中はフォルダを変更できない")
            return
        if self._stroke_before is not None:
            self._message("フォルダ変更不可：筆操作が未確定")
            return
        defaults = self._stored_folders()
        dialog = FolderSelectionDialog(
            self,
            original=defaults[0],
            ternary=defaults[1],
            output=defaults[2],
            pairing_mode=self._pairing_mode,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        folders = dialog.folders
        try:
            result = self._prepare_pairing(folders, dialog.pairing_mode)
        except Exception as exc:  # noqa: BLE001 - フォルダ取引境界
            show_error(self, "フォルダエラー", str(exc))
            return
        if result is None:
            return
        if result.blocking_reason is not None:
            show_error(
                self,
                "読込エラー",
                self._pairing_failure_message(result),
            )
            return
        if not result.pairs:
            show_error(
                self,
                "読込対象なし",
                self._pairing_failure_message(result),
            )
            return

        prepared = self._preflight_first_usable_pair(result)
        if prepared is None:
            return

        def install() -> None:
            self._commit_prepared_pairing(result, folders, prepared)

        self._with_unsaved_resolution("フォルダ再読込", install)

    def _prepare_pairing(
        self,
        folders: tuple[Path, Path, Path],
        mode: PairingMode | str,
    ) -> PairingResult | None:
        """出力先へ作用を残さず走査し、自然順なら全対応の確認まで済ませる。"""

        result = plan_pairing(*folders, mode=mode)
        if result.confirmation_required and not confirm_natural_pairing(self, result):
            self._message("自然順の対応確認を中止：現在の画像集合を維持")
            return None
        return result

    @staticmethod
    def _pairing_failure_message(result: PairingResult) -> str:
        """導入しない走査結果を、現在一覧を壊さず読める診断へ整形する。"""

        lines = [
            result.blocking_reason or "画像群を対応付けられない",
            (
                "検出した対応候補: "
                f"原画像={result.original_candidate_count}件、"
                f"三値画像={result.ternary_candidate_count}件"
            ),
        ]
        diagnostics: list[str] = []
        gate_codes = {"empty_candidate_group", "candidate_count_mismatch"}
        for excluded in result.excluded:
            if excluded.reason_code in gate_codes:
                continue
            paths = ", ".join(str(path) for path in excluded.paths) or "(該当ファイルなし)"
            diagnostics.append(f"- {excluded.message}: {paths}")
        if diagnostics:
            lines.extend(("対象外・衝突の内訳:", *diagnostics))
        return "\n".join(lines)

    def _open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            self._current_settings_snapshot(),
            parent=self,
            persist_callback=self.settings_repository.save,
            apply_callback=self._apply_settings_snapshot,
        )
        dialog.exec()

    def _current_settings_snapshot(self) -> AppSettings:
        stored = self._stored_folders()
        return AppSettings(
            original_folder=stored[0],
            ternary_folder=stored[1],
            output_folder=stored[2],
            window_geometry=bytes(self.saveGeometry()),
            window_state=bytes(self.saveState()),
            original_visible=self.controls.original_visible.isChecked(),
            ternary_visible=self.controls.ternary_visible.isChecked(),
            pseudo_enabled=self.controls.pseudo_enabled.isChecked(),
            darken_comparison_enabled=self.controls.darken_comparison.isChecked(),
            pseudo_colors=tuple(hex_from_rgb(color) for color in self.controls.pseudo_palette),
            original_opacity=self.controls.opacity_slider.value(),
            grid_auto=self.controls.grid_enabled.isChecked(),
            small_components=self.controls.small_components.isChecked(),
            tool=self.controls.selected_tool,
            brush_shape=str(self.controls.brush_shape.currentData()),
            brush_diameter=self.controls.brush_diameter.value(),
            boundary_mode=self.controls.selected_boundary_mode,
            boundary_thickness=self.controls.boundary_thickness.value(),
            shortcuts=self.action_registry.assignments.as_dict(),
        )

    def _apply_settings_snapshot(self, snapshot: AppSettings) -> None:
        """検証・永続化済み設定を画像状態と独立に一括反映する。"""

        previous_folders = self._folders
        self.applied_settings = snapshot
        self._release_pointer_inputs()
        self.action_registry.set_assignments(ShortcutAssignments(snapshot.shortcuts))
        self.controls.original_visible.setChecked(snapshot.original_visible)
        self.controls.ternary_visible.setChecked(snapshot.ternary_visible)
        self.controls.pseudo_enabled.setChecked(snapshot.pseudo_enabled)
        self.controls.darken_comparison.setChecked(snapshot.darken_comparison_enabled)
        self.controls.set_palette(tuple(rgb_from_hex(color) for color in snapshot.pseudo_colors))
        self.controls.opacity_slider.setValue(snapshot.original_opacity)
        self.controls.grid_enabled.setChecked(snapshot.grid_auto)
        self.controls.small_components.setChecked(snapshot.small_components)
        self.controls.select_tool(snapshot.tool)
        self.controls.select_brush_shape(snapshot.brush_shape)
        self.controls.brush_diameter.setValue(snapshot.brush_diameter)
        self.controls.select_boundary_mode(snapshot.boundary_mode)
        self.controls.boundary_thickness.setValue(snapshot.boundary_thickness)
        if snapshot.original_folder and snapshot.ternary_folder and snapshot.output_folder:
            self._folders = (
                Path(snapshot.original_folder),
                Path(snapshot.ternary_folder),
                Path(snapshot.output_folder),
            )
        else:
            self._folders = None
        if self._folders != previous_folders and self._pairs:
            self._message(
                "フォルダ設定を適用した。表示中一覧は維持し、再走査時に新設定へ切り替える"
            )
        self._update_interface()

    def _restore_folders_on_startup(
        self,
        stored: tuple[str, str, str] | None = None,
    ) -> None:
        if stored is None:
            stored = self._stored_folders()
        if not all(stored):
            return
        folders = tuple(Path(value) for value in stored)
        try:
            result = self._prepare_pairing(folders, self._stored_pairing_mode())
        except Exception as exc:  # noqa: BLE001 - 起動時は非モーダル通知で継続
            self._message(f"自動再走査エラー：{exc}")
            return
        if result is None:
            return
        if result.blocking_reason is not None:
            show_error(
                self,
                "読込エラー",
                self._pairing_failure_message(result),
            )
            return
        if not result.pairs:
            show_error(
                self,
                "読込対象なし",
                self._pairing_failure_message(result),
            )
            return
        prepared = self._preflight_first_usable_pair(result)
        if prepared is None:
            return
        self._commit_prepared_pairing(result, folders, prepared)

    def _rescan_folders(self) -> None:
        folders = self._folders
        if folders is None:
            stored = self._stored_folders()
            if not all(stored):
                self._message("再走査不可：入出力フォルダが未指定")
                return
            folders = tuple(Path(value) for value in stored)

        assert folders is not None
        try:
            result = self._prepare_pairing(folders, self._pairing_mode)
        except Exception as exc:  # noqa: BLE001 - フォルダ取引境界
            show_error(self, "再走査エラー", str(exc))
            return
        if result is None:
            return
        if result.blocking_reason is not None:
            show_error(
                self,
                "再走査エラー",
                self._pairing_failure_message(result),
            )
            return
        if not result.pairs:
            show_error(
                self,
                "再走査対象なし",
                self._pairing_failure_message(result),
            )
            return
        prepared = self._preflight_first_usable_pair(result)
        if prepared is None:
            return

        def install_rescan() -> None:
            self._commit_prepared_pairing(result, folders, prepared)

        self._with_unsaved_resolution("フォルダ再走査", install_rescan)

    def _preflight_first_usable_pair(
        self,
        result: PairingResult,
    ) -> _PreparedPairingOpen | None:
        """現状態と出力先を変えず、最初に開ける対を別sessionへ用意する。"""

        pair_errors: dict[int, str] = {}
        output_errors: dict[int, str] = {}
        transient_errors: dict[int, str] = {}
        output_error_snapshots: dict[int, tuple[Any, ...]] = {}
        for index, pair in enumerate(result.pairs):
            source = self._choose_edit_source(pair)
            output_snapshot_retries = 1
            jpeg_confirmed = self._preconfirm_ternary_jpeg(pair, source)
            if jpeg_confirmed is None:
                return None
            prepared_session = ImageSession()
            while True:
                try:
                    prepared_session.open_pair(
                        pair,
                        source,
                        expected_size=self.expected_size,
                        allow_jpeg_import=jpeg_confirmed,
                    )
                except (
                    ExternalOutputModificationError,
                    ImageValidationError,
                    PairDimensionError,
                ) as exc:
                    if self._is_output_read_error(exc, pair, source):
                        failed_snapshot, exact_snapshot = self._output_failure_snapshot(
                            pair,
                            exc,
                        )
                        current_snapshot = self._output_snapshot(pair.output_path)
                        if (
                            not exact_snapshot or failed_snapshot != current_snapshot
                        ) and output_snapshot_retries > 0:
                            output_snapshot_retries -= 1
                            source = EditSource.OUTPUT
                            jpeg_confirmed = False
                            continue
                        if failed_snapshot != current_snapshot:
                            transient_errors[index] = self._output_changed_message(pair)
                            break
                        output_errors[index] = str(exc)
                        output_error_snapshots[index] = failed_snapshot
                        source = EditSource.INPUT
                        jpeg_confirmed = self._preconfirm_ternary_jpeg(pair, source)
                        if jpeg_confirmed is None:
                            return None
                        continue
                    pair_errors[index] = str(exc)
                    break
                except Exception as exc:  # noqa: BLE001 - 読込preflight取引境界
                    transient_errors[index] = self._unexpected_read_error_message(
                        pair,
                        exc,
                    )
                    break
                if source == EditSource.INPUT and index in output_error_snapshots:
                    failed_snapshot = output_error_snapshots[index]
                    if failed_snapshot != self._output_snapshot(pair.output_path):
                        output_errors.pop(index, None)
                        output_error_snapshots.pop(index, None)
                        if output_snapshot_retries > 0:
                            output_snapshot_retries -= 1
                            source = EditSource.OUTPUT
                            jpeg_confirmed = False
                            prepared_session = ImageSession()
                            continue
                        transient_errors[index] = self._output_changed_message(pair)
                        break
                return _PreparedPairingOpen(
                    index=index,
                    source=source,
                    session=prepared_session,
                    pair_errors=pair_errors,
                    output_errors=output_errors,
                    transient_errors=transient_errors,
                    output_error_snapshots=output_error_snapshots,
                )
        diagnostics: list[str] = []
        for kind, errors in (
            ("画像対", pair_errors),
            ("編集済み画像", output_errors),
            ("読込処理", transient_errors),
        ):
            for index, message in sorted(errors.items()):
                pair_name = result.pairs[index].ternary_stem
                compact_message = " / ".join(message.splitlines())
                diagnostics.append(f"{pair_name}（{kind}）: {compact_message}")
        self._message(
            "｜".join(
                (
                    "読込可能な画像対なし：現在の画像集合を維持",
                    *diagnostics,
                )
            )
        )
        return None

    def _commit_prepared_pairing(
        self,
        result: PairingResult,
        folders: tuple[Path, Path, Path],
        prepared: _PreparedPairingOpen | None,
    ) -> None:
        """確認済み計画と読込済みsessionを一括して現在状態へ導入する。"""

        finalize_pairing(result, folders[2])
        self._install_pairing(result, folders)
        if prepared is None:
            return
        self._pair_errors.update(prepared.pair_errors)
        self._output_errors.update(prepared.output_errors)
        self._transient_open_errors.update(prepared.transient_errors)
        self._output_error_snapshots.update(prepared.output_error_snapshots)
        self.session = prepared.session
        self._finish_open_pair(prepared.index, prepared.source, had_image=False)

    def _install_pairing(
        self,
        result: PairingResult,
        folders: tuple[Path, Path, Path],
    ) -> None:
        self.session.close()
        self._detach_component_result()
        self.canvas.clear_images()
        self._current_index = None
        self._pairing_result = result
        self._pairing_mode = result.pairing_mode
        self._pairs = list(result.pairs)
        self._pair_errors.clear()
        self._output_errors.clear()
        self._transient_open_errors.clear()
        self._output_error_snapshots.clear()
        self._accepted_input_fallbacks.clear()
        self._folders = tuple(Path(folder) for folder in folders)
        self._write_folders(self._folders, self._pairing_mode)
        self._rebuild_image_list()
        self.controls.set_component_count(None)
        if result.output_checked and not result.output_writable:
            QMessageBox.warning(
                self,
                "出力先エラー",
                result.output_warning or "出力フォルダへ書き込めないため、保存は無効です。",
            )
        if result.blocking_reason is not None:
            self._message(result.blocking_reason)
        elif not result.pairs:
            self._message("有効な画像対なし：対象外理由は一覧に表示")
        else:
            mode_text = (
                "自然順（確認済み）"
                if result.pairing_mode is PairingMode.NATURAL_ORDER
                else "仕様キー"
            )
            self._message(f"{len(result.pairs)}組を対応付けた｜{mode_text}")
        self._update_interface()

    def _rebuild_image_list(self) -> None:
        self.image_list.clear()
        self.error_list.clear()
        for index, pair in enumerate(self._pairs):
            if index in self._pair_errors:
                continue
            item = QListWidgetItem(self._pair_item_text(index, pair), self.image_list)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(f"原画像: {pair.original_path}\n三値: {pair.ternary_path}")
        for excluded in self._pairing_result.excluded:
            paths = ", ".join(path.name for path in excluded.paths) or "(pathなし)"
            item = QListWidgetItem(
                f"対象外｜{excluded.message}｜{paths}",
                self.error_list,
            )
            item.setToolTip("\n".join(str(path) for path in excluded.paths))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        for index, message in sorted(self._pair_errors.items()):
            pair = self._pairs[index]
            item = QListWidgetItem(
                f"読込不能｜{message}｜{pair.ternary_stem}",
                self.error_list,
            )
            item.setToolTip(f"原画像: {pair.original_path}\n三値: {pair.ternary_path}")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

    def _pair_item_text(self, index: int, pair: ImagePair) -> str:
        if (
            index == self._current_index
            and self.session.edit_source == EditSource.OUTPUT
            and self.session.import_report.recovered_output
            and self.session.import_requires_save
        ):
            output = "出力変換済・要保存"
        elif index in self._output_errors:
            output = "出力不正"
        else:
            output = "出力あり" if pair.output_path.exists() else "出力なし"
        error = self._pair_errors.get(index)
        suffix = f"｜利用不能: {error}" if error else ""
        if index in self._output_errors:
            suffix += f"｜{self._output_errors[index]}"
        if index in self._transient_open_errors:
            suffix += f"｜一時的読込エラー: {self._transient_open_errors[index]}"
        current = "▶ " if index == self._current_index else "  "
        visible_position = sum(candidate not in self._pair_errors for candidate in range(index + 1))
        jpeg = (
            "｜JPEG→PNG"
            if pair.ternary_path.suffix.casefold() in TERNARY_JPEG_EXTENSIONS
            else ""
        )
        return (
            f"{current}{visible_position:04d}｜{pair.ternary_stem}{jpeg}｜{output}{suffix}"
        )

    def _refresh_pair_items(self) -> None:
        self._rebuild_image_list()
        self._sync_list_selection()

    def _list_item_selected(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.request_open_index(index)

    def _choose_edit_source(
        self,
        pair: ImagePair,
        index: int | None = None,
    ) -> EditSource:
        """既存出力を優先する。同じ不正出力への承認済みfallbackは再確認しない。"""

        if not pair.output_path.exists():
            if index is not None:
                self._clear_output_error(index)
            return EditSource.INPUT
        if index is None or index not in self._accepted_input_fallbacks:
            return EditSource.OUTPUT
        if self._accepted_input_fallbacks.get(index) == self._output_snapshot(
            pair.output_path
        ):
            return EditSource.INPUT
        self._clear_output_error(index)
        return EditSource.OUTPUT

    @staticmethod
    def _output_snapshot(path: Path) -> tuple[Any, ...]:
        """不正出力の同一性だけを判定する安定したsnapshotを返す。"""

        try:
            fingerprint = fingerprint_file(path)
        except OSError as exc:
            try:
                stat = Path(path).stat()
            except OSError as stat_exc:
                return ("unavailable", type(stat_exc).__name__, stat_exc.errno)
            return (
                "unreadable",
                stat.st_dev,
                stat.st_ino,
                stat.st_size,
                stat.st_mtime_ns,
                type(exc).__name__,
                exc.errno,
            )
        if fingerprint is None:
            return ("missing",)
        return ("file", fingerprint.sha256)

    def _record_output_error(
        self,
        index: int,
        pair: ImagePair,
        error: Exception,
    ) -> tuple[tuple[Any, ...], bool]:
        snapshot, exact = self._output_failure_snapshot(pair, error)
        self._output_errors[index] = str(error)
        self._transient_open_errors.pop(index, None)
        self._output_error_snapshots[index] = snapshot
        self._accepted_input_fallbacks.pop(index, None)
        return snapshot, exact

    def _output_failure_snapshot(
        self,
        pair: ImagePair,
        error: Exception,
    ) -> tuple[tuple[Any, ...], bool]:
        """失敗を起こした内容へ結び付くsnapshotと、その厳密性を返す。"""

        if isinstance(error, ImageValidationError) and error.observed_sha256 is not None:
            return ("file", error.observed_sha256), True
        if isinstance(error, PairDimensionError) and error.ternary_sha256 is not None:
            return ("file", error.ternary_sha256), True
        if (
            isinstance(error, ExternalOutputModificationError)
            and error.expected_sha256 is not None
        ):
            return ("file", error.expected_sha256), True
        return self._output_snapshot(pair.output_path), False

    @staticmethod
    def _output_changed_message(pair: ImagePair) -> str:
        return (
            "編集済み画像が読込中に変更されました\n"
            f"ファイル: {pair.output_path}"
        )

    def _retry_or_report_changed_output(
        self,
        index: int,
        pair: ImagePair,
        *,
        report_pair_error: bool,
        allow_output_fallback: bool,
        output_snapshot_retries: int,
    ) -> bool:
        """古い失敗・許可を捨て、有限回だけ現在OUTPUTを再検査する。"""

        self._clear_output_error(index)
        if output_snapshot_retries > 0:
            return self._open_pair(
                index,
                EditSource.OUTPUT,
                jpeg_confirmed=False,
                report_pair_error=report_pair_error,
                allow_output_fallback=allow_output_fallback,
                output_snapshot_retries=output_snapshot_retries - 1,
            )
        message = self._output_changed_message(pair)
        self._transient_open_errors[index] = message
        self._refresh_pair_items()
        if report_pair_error:
            show_error(self, "編集済み画像変更", message)
        self._sync_list_selection()
        self._update_interface()
        return False

    def _clear_output_error(self, index: int) -> None:
        self._output_errors.pop(index, None)
        self._output_error_snapshots.pop(index, None)
        self._accepted_input_fallbacks.pop(index, None)

    @staticmethod
    def _is_output_read_error(
        error: Exception,
        pair: ImagePair,
        source: EditSource,
    ) -> bool:
        if source != EditSource.OUTPUT:
            return False
        if isinstance(error, PairDimensionError):
            return Path(error.ternary_path) == Path(pair.output_path)
        if isinstance(error, (ImageValidationError, ExternalOutputModificationError)):
            return Path(error.path) == Path(pair.output_path)
        return False

    @staticmethod
    def _unexpected_read_error_message(pair: ImagePair, error: Exception) -> str:
        return (
            "画像対の読込処理に失敗しました\n"
            f"原画像: {pair.original_path}\n"
            f"入力三値画像: {pair.ternary_path}\n"
            f"編集済み画像: {pair.output_path}\n"
            f"理由: {error}"
        )

    def _preconfirm_ternary_jpeg(
        self,
        pair: ImagePair,
        source: EditSource,
    ) -> bool | None:
        """入力JPEGを編集元とする時だけ確認し、取消ならNoneを返す。"""

        if (
            source != EditSource.INPUT
            or pair.ternary_path.suffix.casefold() not in TERNARY_JPEG_EXTENSIONS
        ):
            return False
        if confirm_ternary_jpeg_import(self, pair.ternary_path):
            return True
        self._message("JPEG三値画像の取込を中止：現在の画像を維持")
        return None

    def _open_pair(
        self,
        index: int,
        source: EditSource,
        *,
        jpeg_confirmed: bool = False,
        report_pair_error: bool = True,
        allow_output_fallback: bool = True,
        output_snapshot_retries: int = 1,
        fallback_output_snapshot: tuple[Any, ...] | None = None,
    ) -> bool:
        if not 0 <= index < len(self._pairs):
            return False
        pair = self._pairs[index]
        self._transient_open_errors.pop(index, None)
        is_ternary_jpeg = pair.ternary_path.suffix.casefold() in TERNARY_JPEG_EXTENSIONS
        if source == EditSource.INPUT and is_ternary_jpeg and not jpeg_confirmed:
            if not confirm_ternary_jpeg_import(self, pair.ternary_path):
                self._message("JPEG三値画像の取込を中止：現在の画像を維持")
                self._sync_list_selection()
                return False
            jpeg_confirmed = True
        had_image = self.canvas.has_image
        opening_session = (
            ImageSession() if fallback_output_snapshot is not None else self.session
        )
        try:
            opening_session.open_pair(
                pair,
                source,
                expected_size=self.expected_size,
                allow_jpeg_import=jpeg_confirmed,
            )
            if (
                fallback_output_snapshot is not None
                and fallback_output_snapshot != self._output_snapshot(pair.output_path)
            ):
                return self._retry_or_report_changed_output(
                    index,
                    pair,
                    report_pair_error=report_pair_error,
                    allow_output_fallback=allow_output_fallback,
                    output_snapshot_retries=output_snapshot_retries,
                )
            if opening_session is not self.session:
                self.session = opening_session
        except (
            ExternalOutputModificationError,
            ImageValidationError,
            PairDimensionError,
        ) as exc:
            if self._is_output_read_error(exc, pair, source):
                failed_snapshot, exact_snapshot = self._record_output_error(
                    index,
                    pair,
                    exc,
                )
                current_snapshot = self._output_snapshot(pair.output_path)
                should_retry_snapshot = (
                    (not exact_snapshot and output_snapshot_retries > 0)
                    or failed_snapshot != current_snapshot
                )
                if should_retry_snapshot:
                    return self._retry_or_report_changed_output(
                        index,
                        pair,
                        report_pair_error=report_pair_error,
                        allow_output_fallback=allow_output_fallback,
                        output_snapshot_retries=output_snapshot_retries,
                    )
                self._refresh_pair_items()
                if allow_output_fallback and self._ask_input_fallback(exc):
                    if failed_snapshot != self._output_snapshot(pair.output_path):
                        return self._retry_or_report_changed_output(
                            index,
                            pair,
                            report_pair_error=report_pair_error,
                            allow_output_fallback=allow_output_fallback,
                            output_snapshot_retries=output_snapshot_retries,
                        )
                    self._accepted_input_fallbacks[index] = failed_snapshot
                    return self._open_pair(
                        index,
                        EditSource.INPUT,
                        jpeg_confirmed=jpeg_confirmed,
                        report_pair_error=report_pair_error,
                        allow_output_fallback=allow_output_fallback,
                        output_snapshot_retries=output_snapshot_retries,
                        fallback_output_snapshot=failed_snapshot,
                    )
                self._sync_list_selection()
                self._update_interface()
                return False
            self._pair_errors[index] = str(exc)
            self._refresh_pair_items()
            if report_pair_error:
                show_error(self, "画像対読込エラー", str(exc))
            if not self.session.is_loaded:
                self.canvas.clear_images()
            self._sync_list_selection()
            self._update_interface()
            return False
        except Exception as exc:  # noqa: BLE001 - 画像切替取引境界
            message = self._unexpected_read_error_message(pair, exc)
            self._transient_open_errors[index] = message
            self._refresh_pair_items()
            if report_pair_error:
                show_error(
                    self,
                    "読込処理エラー",
                    message,
                )
            if not self.session.is_loaded:
                self.canvas.clear_images()
            self._sync_list_selection()
            self._update_interface()
            return False

        return self._finish_open_pair(index, source, had_image=had_image)

    def _finish_open_pair(
        self,
        index: int,
        source: EditSource,
        *,
        had_image: bool,
    ) -> bool:
        """読込成功済みの現在sessionを画面状態へ反映する。"""

        pair = self._pairs[index]
        self._detach_component_result()
        assert self.session.original_rgb is not None
        assert self.session.labels is not None
        self._current_index = index
        self._pair_errors.pop(index, None)
        self._transient_open_errors.pop(index, None)
        if source == EditSource.OUTPUT:
            self._clear_output_error(index)
        self._needs_initial_overwrite_confirmation = (
            source == EditSource.INPUT and pair.output_path.exists()
        )
        self.canvas.set_images(
            self.session.original_rgb,
            self.session.labels,
            reset_view=not had_image,
        )
        self.canvas.warning_visible = self.controls.small_components.isChecked()
        self.canvas.clear_warning_overlay()
        self.controls.set_component_count(None)
        self._refresh_pair_items()
        self._sync_list_selection()
        opened_parts = [f"{pair.ternary_stem} を開いた"]
        if self.session.import_report.recovered_output:
            opened_parts.append(
                f"外部出力を三値化: {self.session.import_report.total_pixels}画素"
            )
            if self.session.import_report.recovery_reason is not None:
                opened_parts.append(f"変換理由: {self.session.import_report.recovery_reason}")
            opened_parts.append("RGB PNG保存が必要")
        elif self.session.import_report.quantized:
            opened_parts.append(
                f"JPEGを三値化: {self.session.import_report.total_pixels}画素"
            )
            opened_parts.append("PNG保存が必要")
        if source == EditSource.INPUT and index in self._output_errors:
            opened_parts.append("編集済み画像を使用不可: 入力三値画像を使用")
        if self.session.normalization.changed:
            opened_parts.append(
                f"下端保護領域を無へ正規化: "
                f"{self.session.normalization.changed_pixels}画素"
            )
        if self.session.is_dirty:
            opened_parts.append("未保存")
        self._message("｜".join(opened_parts))
        self._update_interface()
        self._request_components()
        return True

    def _ask_input_fallback(self, error: Exception) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("編集済み画像エラー")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(str(error))
        box.setInformativeText("入力三値画像へ切り替えて読み込みますか。")
        fallback = box.addButton(
            "入力三値画像を開く",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel = box.addButton("中止", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(fallback)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is fallback

    def _with_unsaved_resolution(
        self,
        action_name: str,
        continuation: Callable[[], Any],
    ) -> None:
        if not self.session.is_loaded or not self.session.is_dirty:
            continuation()
            return
        choice = ask_unsaved(self, action_name)
        if choice == UnsavedChoice.SAVE:
            self.request_save(continuation=continuation)
        elif choice == UnsavedChoice.DISCARD:
            # The old session remains intact until the continuation commits a
            # replacement.  A failed image open or a later JPEG cancellation
            # must not turn an intended transition into data loss.
            continuation()

    def _go_previous(self) -> None:
        self._request_directional_move(-1)

    def _go_next(self) -> None:
        self._request_directional_move(1)

    def _request_directional_move(self, direction: int) -> None:
        if self._current_index is None or direction == 0:
            return
        first_target = self._adjacent_pair_index(self._current_index, direction)
        if first_target is None:
            return
        first_source = self._choose_edit_source(
            self._pairs[first_target],
            first_target,
        )
        first_jpeg_confirmed = self._preconfirm_ternary_jpeg(
            self._pairs[first_target],
            first_source,
        )
        if first_jpeg_confirmed is None:
            self._sync_list_selection()
            return

        def move() -> None:
            target = first_target
            source = first_source
            jpeg_confirmed = first_jpeg_confirmed
            while True:
                if self._open_pair(
                    target,
                    source,
                    jpeg_confirmed=jpeg_confirmed,
                    report_pair_error=False,
                    allow_output_fallback=False,
                    fallback_output_snapshot=(
                        self._accepted_input_fallbacks.get(target)
                        if source == EditSource.INPUT
                        else None
                    ),
                ):
                    return
                if not any(
                    target in errors
                    for errors in (
                        self._pair_errors,
                        self._output_errors,
                        self._transient_open_errors,
                    )
                ):
                    return
                next_target = self._adjacent_pair_index(target, direction)
                if next_target is None:
                    self._sync_list_selection()
                    return
                next_source = self._choose_edit_source(
                    self._pairs[next_target],
                    next_target,
                )
                target = next_target
                source = next_source
                jpeg_confirmed = False

        self._with_unsaved_resolution("画像移動", move)

    def _adjacent_pair_index(self, index: int, direction: int) -> int | None:
        step = 1 if direction > 0 else -1
        candidate = index + step
        while 0 <= candidate < len(self._pairs):
            if candidate not in self._pair_errors:
                return candidate
            candidate += step
        return None

    def _undo(self) -> None:
        if (
            self._job_is_blocking()
            or self._stroke_before is not None
            or self.canvas.memo_stroke_active
            or not self.session.is_loaded
        ):
            return
        candidate = self.session.history.next_undo_entry
        if not self._history_entry_is_available(
            candidate,
            labels_visible=self._labels_are_visible(),
        ):
            return
        entry = self.session.undo()
        if entry is None:
            return
        if entry.memo_delta is not None:
            self.canvas.apply_memo_delta(entry.memo_delta, forward=False)
        if entry.delta is not None:
            assert self.session.labels is not None
            self.canvas.refresh_labels(self.session.labels)
            self._after_label_change("Undo")
        else:
            self._after_memo_change(f"Undo｜{entry.description}")

    def _redo(self) -> None:
        if (
            self._job_is_blocking()
            or self._stroke_before is not None
            or self.canvas.memo_stroke_active
            or not self.session.is_loaded
        ):
            return
        candidate = self.session.history.next_redo_entry
        if not self._history_entry_is_available(
            candidate,
            labels_visible=self._labels_are_visible(),
        ):
            return
        entry = self.session.redo()
        if entry is None:
            return
        if entry.memo_delta is not None:
            self.canvas.apply_memo_delta(entry.memo_delta, forward=True)
        if entry.delta is not None:
            assert self.session.labels is not None
            self.canvas.refresh_labels(self.session.labels)
            self._after_label_change("Redo")
        else:
            self._after_memo_change(f"Redo｜{entry.description}")

    def _memo_stroke_committed(self, delta: MemoDelta) -> None:
        try:
            trim_report = self.session.record_memo(delta, "メモ一筆")
        except Exception as exception:
            self.canvas.apply_memo_delta(delta, forward=False)
            show_error(self, "メモ履歴エラー", str(exception))
            self._message("メモ履歴エラー｜一筆を破棄")
            self._update_interface()
            return
        self._after_memo_change("メモ一筆", trim_report)

    def _brush_started(self, x: float, y: float) -> None:
        if (
            not self._labels_are_visible()
            or self._job_is_blocking()
            or self.session.labels is None
            or self._pixel_is_protected(y)
        ):
            return
        self._stroke_before = self.session.labels.copy()
        self._stroke_last_point = (x, y)
        self._stroke_label = self._selected_label
        self._stroke_diameter = self.controls.brush_diameter.value()
        self._stroke_shape = str(self.controls.brush_shape.currentData())
        try:
            self.canvas.begin_label_memo_erase()
            self._render_brush_preview((x, y), None)
        except Exception:
            self._cancel_active_brush("筆入力エラー｜筆跡を取消｜編集への反映なし")
            raise
        self._update_interface()

    def _brush_moved(self, x: float, y: float) -> None:
        if self._stroke_before is None or self._stroke_last_point is None:
            return
        point = (x, y)
        try:
            self._render_brush_preview(self._stroke_last_point, point)
        except Exception:
            self._cancel_active_brush("筆入力エラー｜筆跡を取消｜編集への反映なし")
            raise
        self._stroke_last_point = point

    def _render_brush_preview(
        self,
        start: tuple[float, float],
        end: tuple[float, float] | None,
    ) -> None:
        assert self._stroke_before is not None
        assert self.session.labels is not None
        footprint = brush_segment_footprint(
            self.session.labels.shape,
            start,
            end,
            self._stroke_diameter,
            self._stroke_shape,
        )
        if footprint is None:
            return
        dirty_bbox = paint_brush_footprint(
            self.session.labels,
            footprint,
            self._stroke_label,
        )
        self.canvas.stage_label_memo_erase(footprint)
        if dirty_bbox is not None:
            self.canvas.refresh_label_region(self.session.labels, dirty_bbox)

    def _brush_finished(self) -> None:
        if self._stroke_before is None or self.session.labels is None:
            return
        before = self._stroke_before
        self._stroke_before = None
        self._stroke_last_point = None
        before_revision = self.session.revision
        memo_delta = None
        try:
            memo_delta = self.canvas.finish_label_memo_erase("筆によるメモ消去")
            trim_report = self.session.commit_preapplied(
                before,
                "筆",
                memo_delta=memo_delta,
            )
        except Exception:
            if memo_delta is not None:
                self.canvas.apply_memo_delta(memo_delta, forward=False)
            else:
                self.canvas.cancel_label_memo_erase()
            if self.session.labels is not None and self.session.labels.shape == before.shape:
                self.session.labels[...] = before
                self.canvas.refresh_labels(self.session.labels)
            self._message("筆確定エラー｜筆跡を取消｜編集への反映なし")
            self._update_interface()
            raise
        if self.session.revision != before_revision:
            self._after_label_change("筆描画", trim_report)
        elif memo_delta is not None:
            self._after_memo_change("筆によるメモ消去", trim_report)
        else:
            self._message("同色のため変更しなかった")
            self._update_interface()

    def _cancel_brush(self, reason: str = "筆跡を取消") -> None:
        if self._stroke_before is None:
            return
        before = self._stroke_before
        self._stroke_before = None
        self._stroke_last_point = None
        self.canvas.cancel_label_memo_erase()
        if self.session.labels is not None and self.session.labels.shape == before.shape:
            self.session.labels[...] = before
            self.canvas.refresh_labels(self.session.labels)
        self._message(reason)
        self._update_interface()

    def _request_fill(self, x: int, y: int) -> None:
        if not self._labels_are_visible() or self.session.labels is None:
            return
        if self._pixel_is_protected(y):
            self._message("下端100画素・強制無領域は編集できない")
            return
        if self._active_job is not None:
            self._message("塗り潰し不可：別の処理を実行中")
            return
        self._start_job(
            "filling",
            "塗り潰し",
            flood_fill4,
            self.session.labels.copy(),
            (x, y),
            self._selected_label,
            on_success=lambda labels: self._apply_generated_labels(labels, "塗り潰し"),
        )

    def _request_selected_boundary(self) -> None:
        self._request_boundary(
            self.controls.selected_boundary_mode,
            self.controls.boundary_thickness.value(),
        )

    def _request_boundary(self, mode: str, thickness: int) -> None:
        if not self._labels_are_visible() or self.session.labels is None:
            return
        if self._stroke_before is not None:
            self._message("境界生成不可：筆操作が未確定")
            return
        if self._active_job is not None:
            self._message("境界生成不可：別の処理を実行中")
            return
        function = (
            generate_boundary_none_side if mode == "none_side" else generate_boundary_non_none_side
        )
        description = "無側境界生成" if mode == "none_side" else "非無側境界生成"
        self._start_job(
            "boundary",
            description,
            function,
            self.session.labels.copy(),
            thickness,
            on_success=lambda labels: self._apply_generated_labels(labels, description),
        )

    def _apply_generated_labels(self, labels: np.ndarray, description: str) -> None:
        assert self.session.labels is not None
        normalized, _changed_protected = normalized_protected_labels_copy(labels)
        if normalized.shape != self.session.labels.shape:
            raise ValueError("生成画像の寸法が現在画像と一致しない")
        changed = np.flatnonzero(
            self.session.labels.reshape(-1) != normalized.reshape(-1)
        )
        if self.session.labels.size > np.iinfo(np.uint32).max:
            raise ValueError("画像画素数が履歴索引範囲を超える")
        changed_indices = changed.astype(np.uint32, copy=False)
        memo_delta = self.canvas.erase_memo_indices(
            changed_indices,
            f"{description}によるメモ消去",
        )
        before_revision = self.session.revision
        try:
            trim_report = self.session.apply_labels(
                normalized,
                description,
                memo_delta=memo_delta,
            )
        except Exception:
            if memo_delta is not None:
                self.canvas.apply_memo_delta(memo_delta, forward=False)
            raise
        if self.session.revision == before_revision:
            if memo_delta is not None:
                self._after_memo_change(f"{description}によるメモ消去", trim_report)
            else:
                self._message(f"{description}｜対象画素なし｜変更なし")
            return
        assert self.session.labels is not None
        self.canvas.refresh_labels(self.session.labels)
        self._after_label_change(description, trim_report)

    def _after_label_change(
        self,
        description: str,
        trim_report: HistoryTrimReport | None = None,
    ) -> None:
        self.canvas.clear_warning_overlay()
        self.controls.set_component_count(None)
        if trim_report is not None and trim_report.trimmed:
            suffix = (
                "。保存時点も履歴外となった" if trim_report.saved_state_became_unreachable else ""
            )
            message = (
                f"{description}を反映した。履歴上限により古い"
                f"{trim_report.dropped_operations}操作を破棄した{suffix}"
            )
        else:
            message = f"{description}を反映した"
        self._update_interface()
        if not self._close_after_activity:
            self._request_components()
        self._message(message)

    def _after_memo_change(
        self,
        description: str,
        trim_report: HistoryTrimReport | None = None,
    ) -> None:
        if trim_report is not None and trim_report.trimmed:
            message = (
                f"{description}｜履歴上限により古い"
                f"{trim_report.dropped_operations}操作を破棄"
            )
        else:
            message = description
        self._update_interface()
        self._message(message)

    def _set_small_components(self, enabled: bool) -> None:
        self.settings.setValue("view/smallComponents", enabled)
        self.canvas.warning_visible = enabled and self._labels_are_visible()
        self.canvas.update()
        self._update_interface()
        if not enabled:
            return
        if self.session.is_loaded:
            self._request_components()

    def _request_components(self) -> None:
        if (
            self.session.labels is None
            or self._active_job is not None
            or self._stroke_before is not None
        ):
            if self.session.labels is not None:
                self._component_rerun_needed = True
            return
        if self._latest_component_token is not None:
            return
        self.canvas.clear_warning_overlay()
        self.controls.set_component_count(None)
        self._start_job(
            "components",
            "小領域解析",
            find_small_components,
            self.session.labels.copy(),
            on_success=self._apply_components,
        )

    def _apply_components(self, result: SmallComponentsResult) -> None:
        self._component_rerun_needed = False
        self.canvas.set_warning_overlay(result.mask, result.bboxes)
        self.canvas.warning_visible = (
            self.controls.small_components.isChecked() and self._labels_are_visible()
        )
        present = sum(component.label == Label.PRESENT for component in result.components)
        boundary = sum(component.label == Label.BOUNDARY for component in result.components)
        self.controls.set_component_counts(present, boundary)

    def _start_save(
        self,
        *,
        force: bool,
        allow_existing_output: bool = False,
        allow_stale_sources: bool = False,
        continuation: Callable[[], None] | None,
    ) -> None:
        self._start_job(
            "saving",
            "保存",
            self.session.save,
            force=force,
            allow_existing_output=allow_existing_output,
            allow_stale_sources=allow_stale_sources,
            expected_size=self.expected_size,
            on_success=lambda _fingerprint: self._save_succeeded(continuation),
            on_failure=lambda exc: self._save_failed(
                exc,
                force=force,
                allow_existing_output=allow_existing_output,
                allow_stale_sources=allow_stale_sources,
                continuation=continuation,
            ),
        )

    def _save_succeeded(self, continuation: Callable[[], None] | None) -> None:
        self.session.discard_memo_history()
        self.canvas.clear_memo()
        self._needs_initial_overwrite_confirmation = False
        if self._current_index is not None:
            self._clear_output_error(self._current_index)
        self._refresh_pair_items()
        self._message("保存完了")
        self._update_interface()
        if continuation is not None:
            continuation()

    def _save_failed(
        self,
        exception: Exception,
        *,
        force: bool,
        allow_existing_output: bool,
        allow_stale_sources: bool,
        continuation: Callable[[], None] | None,
    ) -> None:
        if isinstance(exception, ExternalSourceModificationError):
            choice = ask_input_change(self, (exception.path,))
            if choice == InputChangeChoice.RELOAD_DISCARD:
                source = self.session.edit_source or EditSource.INPUT
                index = self._current_index if self._current_index is not None else 0
                self._open_pair(index, source)
                return
            if choice == InputChangeChoice.SAVE_SNAPSHOT:
                self._start_save(
                    force=force,
                    allow_existing_output=allow_existing_output,
                    allow_stale_sources=True,
                    continuation=continuation,
                )
                return
            self._message("保存を中止：未保存の変更を維持")
            return
        if isinstance(exception, ExternalModificationError):
            assert self.session.pair is not None
            if self._current_index is not None:
                # 以前の出力内容に対する検証失敗は、外部変更を検出した時点で
                # 既に陳腐化している。存在状態を再表示する前に棄却する。
                self._clear_output_error(self._current_index)
            # 出力の新規出現・削除・置換は、保存を中止しても一覧上の事実へ
            # 直ちに反映する。保存許可と表示中の存在状態を同じ状態に潰さない。
            self._refresh_pair_items()
            self._sync_list_selection()
            choice = ask_external_change(self, self.session.pair.output_path)
            if choice == ExternalChangeChoice.RELOAD:
                self._open_pair(self._current_index or 0, EditSource.OUTPUT)
                return
            if choice == ExternalChangeChoice.OVERWRITE:
                self._start_save(
                    force=True,
                    allow_existing_output=True,
                    allow_stale_sources=allow_stale_sources,
                    continuation=continuation,
                )
                return
            self._message("保存を中止：未保存の変更を維持")
            return
        show_error(self, "保存エラー", str(exception))
        self._message("保存エラー：未保存の変更を維持")
        self._update_interface()

    def _start_job(
        self,
        activity: str,
        description: str,
        function: Callable[..., Any],
        /,
        *args: Any,
        on_success: Callable[[Any], None],
        on_failure: Callable[[Exception], None] | None = None,
        **kwargs: Any,
    ) -> None:
        if self._active_job is not None or not self.session.is_loaded:
            return
        is_component = activity == Activity.COMPONENTS.value
        if is_component and self._latest_component_token is not None:
            return
        try:
            if activity == Activity.SAVING.value:
                assert self.session.session_id is not None
                token = TaskToken(self.session.session_id, self.session.revision, activity)
            else:
                token = self.session.begin_activity(Activity(activity))
        except BusyError as exc:
            self._message(str(exc))
            return
        worker = FunctionWorker(token, function, *args, **kwargs)
        job = _ActiveJob(
            token=token,
            description=description,
            on_success=on_success,
            on_failure=on_failure or self._default_job_failure,
        )
        self._jobs[id(token)] = job
        if is_component:
            self._latest_component_token = token
            self._component_rerun_needed = False
        else:
            self._active_job = job
            if self._latest_component_token is not None:
                self._latest_component_token = None
                self._component_rerun_needed = True
                self.canvas.clear_warning_overlay()
                self.controls.set_component_count(None)
        self._active_worker = worker
        self._workers.append(worker)
        worker.signals.succeeded.connect(self._job_succeeded)
        worker.signals.failed.connect(self._job_failed)
        worker.signals.finished.connect(self._worker_finished)
        if not is_component:
            self._message(f"{description}｜実行中…")
        self._update_interface()
        self.thread_pool.start(worker)

    def _job_succeeded(self, result: TaskSuccess) -> None:
        taken = self._take_job(result.token)
        if taken is None:
            return
        job, is_current, is_component, was_latest_component = taken
        if not is_current:
            if not is_component:
                self._message(f"{job.description}｜旧い処理結果を破棄｜現在の編集へ未反映")
            if is_component and was_latest_component:
                self._component_rerun_needed = True
            self._after_job_callback()
            return
        if is_component:
            self._component_rerun_needed = False
        try:
            job.on_success(result.value)
        except Exception as exc:  # noqa: BLE001 - 非同期結果適用境界
            show_error(self, "処理結果エラー", f"{job.description}\n{exc}")
        self._after_job_callback()

    def _job_failed(self, result: TaskFailure) -> None:
        taken = self._take_job(result.token)
        if taken is None:
            return
        job, is_current, is_component, was_latest_component = taken
        if not is_current:
            if not is_component:
                self._message(f"{job.description}｜旧い失敗通知を破棄｜現在の処理へ影響なし")
            if is_component and was_latest_component:
                self._component_rerun_needed = True
            self._after_job_callback()
            return
        try:
            job.on_failure(result.exception)
        except Exception as exc:  # noqa: BLE001 - 非同期失敗処理境界
            show_error(self, "失敗処理エラー", f"{job.description}\n{exc}")
        self._after_job_callback()

    def _take_job(
        self,
        token: TaskToken,
    ) -> tuple[_ActiveJob, bool, bool, bool] | None:
        job = self._jobs.pop(id(token), None)
        if job is None or job.token is not token:
            return None
        is_component = token.activity == Activity.COMPONENTS.value
        was_latest_component = token is self._latest_component_token
        if token.activity == Activity.SAVING.value:
            is_current = self._token_is_current(token)
        else:
            is_current = self.session.finish_activity(token)
        if self._active_job is job:
            self._active_job = None
        if was_latest_component:
            self._latest_component_token = None
        self._update_interface()
        return job, is_current, is_component, was_latest_component

    def _worker_finished(self, token: TaskToken) -> None:
        for index, worker in enumerate(self._workers):
            if worker.token is token:
                if self._active_worker is worker:
                    self._active_worker = None
                self._workers.pop(index)
                break

    def _detach_component_result(self) -> None:
        if self._latest_component_token is not None:
            self.session.finish_activity(self._latest_component_token)
        self._latest_component_token = None
        self._component_rerun_needed = False

    def _token_is_current(self, token: TaskToken) -> bool:
        return (
            self.session.is_loaded
            and token.session_id == self.session.session_id
            and token.revision == self.session.revision
        )

    def _default_job_failure(self, exception: Exception) -> None:
        show_error(self, "処理エラー", str(exception))
        self._message("処理エラー：編集内容を維持")

    def _after_job_callback(self) -> None:
        self._update_interface()
        if (
            self._close_after_activity
            and self._active_job is None
            and self._latest_component_token is None
        ):
            self._close_after_activity = False
            QTimer.singleShot(0, self.close)
            return
        if (
            self._component_rerun_needed
            and self.session.is_loaded
            and self._active_job is None
            and self._latest_component_token is None
            and self._stroke_before is None
        ):
            self._component_rerun_needed = False
            QTimer.singleShot(0, self._request_components)

    def _set_original_visibility(self, visible: bool) -> None:
        self.canvas.original_visible = visible
        self.canvas.update()
        self.settings.setValue("view/originalVisible", visible)
        self._update_interface()

    def _set_ternary_visibility(self, visible: bool) -> None:
        self.canvas.ternary_visible = visible
        self.canvas.warning_visible = visible and self.controls.small_components.isChecked()
        self.canvas.update()
        self.settings.setValue("view/ternaryVisible", visible)
        if not visible:
            self.protection_status.setText("保護: 三値画像非表示・編集停止")
            self._message("三値画像を非表示｜画素編集とラベル履歴操作を停止")
        self._update_interface()

    def _set_opacity(self, percent: int) -> None:
        self.canvas.set_original_opacity(percent / 100.0)
        self.settings.setValue("view/originalOpacity", percent)

    def _set_pseudo(self, enabled: bool) -> None:
        self.canvas.set_pseudo_enabled(enabled)
        self.settings.setValue("view/pseudoEnabled", enabled)
        self._update_interface()

    def _set_darken_comparison(self, enabled: bool) -> None:
        self.canvas.set_darken_comparison_enabled(enabled)
        self.settings.setValue("view/darkenComparison", enabled)
        self._update_interface()

    def _set_pseudo_palette(self, palette: tuple[tuple[int, int, int], ...]) -> None:
        self.canvas.set_pseudo_palette(palette)
        encoded = ";".join(",".join(str(channel) for channel in color) for color in palette)
        self.settings.setValue("view/pseudoPalette", encoded)

    def _set_grid(self, enabled: bool) -> None:
        self.canvas.auto_grid_enabled = enabled
        self.canvas.update()
        self.settings.setValue("view/autoGrid", enabled)
        self._update_interface()

    def _set_tool(self, tool: str) -> None:
        self.canvas.tool = EditTool(tool)
        self.settings.setValue("edit/tool", tool)

    def _set_label(self, label: int) -> None:
        self._selected_label = label
        self.canvas.set_selected_label(label)
        red, green, blue = SAVE_RGB[label]
        self.label_status.setText(
            f"選択色: {LABEL_NAMES[Label(label)]}｜#{red:02X}{green:02X}{blue:02X}"
        )

    def _cycle_label(self, direction: int) -> None:
        if self._stroke_before is not None:
            return
        step = 1 if direction >= 0 else -1
        self.controls.select_label((self._selected_label + step) % 3)

    def _set_brush_shape(self, shape: str) -> None:
        self.canvas.brush_shape = BrushShape(shape)
        self.settings.setValue("edit/brushShape", shape)
        self.canvas.update()

    def _set_brush_diameter(self, diameter: int) -> None:
        self.canvas.brush_diameter = diameter
        self.brush_status.setText(f"筆径: {diameter} px")
        self.settings.setValue("edit/brushDiameter", diameter)
        self.canvas.update()

    def _set_boundary_mode(self, mode: str) -> None:
        self.settings.setValue("boundary/mode", mode)

    def _set_boundary_thickness(self, thickness: int) -> None:
        self.settings.setValue("boundary/thickness", thickness)

    def _cursor_changed(self, pixel: tuple[int, int] | None) -> None:
        self.coordinate_status.setText(
            "座標: —" if pixel is None else f"座標: x={pixel[0]}, y={pixel[1]}"
        )
        if pixel is None:
            self.protection_status.setText("保護: —")
        elif self._pixel_is_protected(pixel[1]):
            self.protection_status.setText("保護: 下端100画素・強制無領域")
        elif not self._labels_are_visible():
            self.protection_status.setText("保護: 三値画像非表示・編集停止")
        else:
            self.protection_status.setText("保護: 編集可能")

    def _protected_cursor_changed(self, protected: bool) -> None:
        if protected:
            self.protection_status.setText("保護: 下端100画素・強制無領域")
        elif self._labels_are_visible():
            self.protection_status.setText("保護: 編集可能")

    def _view_changed(self, scale: float) -> None:
        percent = scale * 100.0
        blocked = self.zoom_spin.blockSignals(True)
        self.zoom_spin.setValue(percent)
        self.zoom_spin.blockSignals(blocked)
        self.zoom_status.setText(f"倍率: {percent:.1f}%")

    def _update_interface(self) -> None:
        loaded = self.session.is_loaded
        busy = self._active_job is not None
        blocking = self._job_is_blocking()
        label_stroke_active = self._stroke_before is not None
        memo_stroke_active = self.canvas.memo_stroke_active
        stroke_active = label_stroke_active or memo_stroke_active
        labels_visible = self.controls.ternary_visible.isChecked()
        index = self._current_index
        output_writable = self._pairing_result.output_writable

        transition_available = not busy and not stroke_active
        self.folder_action.setEnabled(transition_available)
        self.previous_action.setEnabled(
            transition_available
            and index is not None
            and self._adjacent_pair_index(index, -1) is not None
        )
        self.next_action.setEnabled(
            transition_available
            and index is not None
            and self._adjacent_pair_index(index, 1) is not None
        )
        self.save_action.setEnabled(loaded and transition_available and output_writable)
        self.undo_action.setEnabled(
            loaded
            and not blocking
            and not stroke_active
            and self._history_entry_is_available(
                self.session.history.next_undo_entry,
                labels_visible=labels_visible,
            )
        )
        self.redo_action.setEnabled(
            loaded
            and not blocking
            and not stroke_active
            and self._history_entry_is_available(
                self.session.history.next_redo_entry,
                labels_visible=labels_visible,
            )
        )
        self.actual_size_action.setEnabled(loaded and not stroke_active)
        self.fit_action.setEnabled(loaded and not stroke_active)
        self.zoom_spin.setEnabled(loaded and not stroke_active)
        self.boundary_action.setEnabled(loaded and labels_visible and transition_available)
        for action in self.single_key_actions:
            action.setEnabled(loaded and labels_visible and not blocking and not stroke_active)
        self.controls.set_editing_available(
            loaded and labels_visible and not blocking and not stroke_active
        )
        self.controls.boundary_group.setEnabled(loaded and labels_visible and transition_available)
        self.controls.set_inspection_available(loaded and not blocking and not stroke_active)
        self.canvas.editing_enabled = loaded and labels_visible and not blocking
        self.canvas.memo_enabled = loaded and not blocking and not label_stroke_active
        self.image_list.setEnabled(transition_available)
        self.error_list.setEnabled(transition_available)

        for operation_id, action in self._operation_actions.items():
            action.setEnabled(self._operation_is_enabled(operation_id))
        self._operation_actions["view.toggle-original"].setChecked(
            self.controls.original_visible.isChecked()
        )
        self._operation_actions["view.toggle-label"].setChecked(labels_visible)
        self._operation_actions["view.toggle-pseudocolor"].setChecked(
            self.controls.pseudo_enabled.isChecked()
        )
        self._operation_actions["view.toggle-darken-comparison"].setChecked(
            self.controls.darken_comparison.isChecked()
        )
        self._operation_actions["view.toggle-grid-auto"].setChecked(
            self.controls.grid_enabled.isChecked()
        )
        self._operation_actions["view.toggle-small-components"].setChecked(
            self.controls.small_components.isChecked()
        )

        state = self._document_state_text()
        self.document_status.setText(state)
        if not loaded or index is None:
            valid_count = len(self._pairs) - len(self._pair_errors)
            self.toolbar_state.setText(f"未読込｜{valid_count}組")
        else:
            source = "編集済み版" if self.session.edit_source == EditSource.OUTPUT else "入力版"
            output = "出力あり" if self._pairs[index].output_path.exists() else "出力なし"
            valid_indices = [
                candidate
                for candidate in range(len(self._pairs))
                if candidate not in self._pair_errors
            ]
            position = valid_indices.index(index) + 1 if index in valid_indices else 0
            self.toolbar_state.setText(
                f"{position}/{len(valid_indices)}｜{source}｜{output}｜{state}"
            )

    def _document_state_text(self) -> str:
        if not self.session.is_loaded:
            return "未読込"
        if self.session.is_dirty:
            document_state = "編集済み・未保存"
        elif self.session.has_saved_current:
            document_state = "保存済み"
        else:
            document_state = "読込済み・未変更"
        if self.session.normalization.changed:
            document_state += f"｜下端正規化 {self.session.normalization.changed_pixels}画素"
        if self.session.import_report.recovered_output:
            document_state += "｜外部出力三値化"
        elif self.session.import_report.quantized:
            document_state += "｜JPEG三値化"
        if self._active_job is not None:
            return f"{document_state}｜処理中: {self._active_job.description}"
        if self._latest_component_token is not None:
            return f"{document_state}｜処理中: 小領域解析"
        return document_state

    def _job_is_blocking(self) -> bool:
        return self._active_job is not None

    def _labels_are_visible(self) -> bool:
        return self.controls.ternary_visible.isChecked()

    @staticmethod
    def _history_entry_is_available(
        entry: HistoryEntry | None,
        *,
        labels_visible: bool,
    ) -> bool:
        if entry is None:
            return False
        return labels_visible or entry.delta is None

    def _pixel_is_protected(self, y: float | int) -> bool:
        labels = self.session.labels
        if labels is None:
            return False
        return y >= protected_start_y(int(labels.shape[0]))

    def _sync_list_selection(self) -> None:
        blocked = self.image_list.blockSignals(True)
        selected_row = -1
        if self._current_index is not None:
            for row in range(self.image_list.count()):
                item = self.image_list.item(row)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == self._current_index:
                    selected_row = row
                    break
        self.image_list.setCurrentRow(selected_row)
        self.image_list.blockSignals(blocked)

    def _message(self, message: str) -> None:
        self.statusBar().showMessage(message, 7000)

    def _restore_settings(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        snapshot = self.applied_settings
        self.controls.original_visible.setChecked(snapshot.original_visible)
        self.controls.ternary_visible.setChecked(snapshot.ternary_visible)
        self.controls.opacity_slider.setValue(snapshot.original_opacity)
        self.controls.pseudo_enabled.setChecked(snapshot.pseudo_enabled)
        self.controls.darken_comparison.setChecked(snapshot.darken_comparison_enabled)
        self.controls.grid_enabled.setChecked(snapshot.grid_auto)
        self.controls.small_components.setChecked(snapshot.small_components)
        self.controls.set_palette(tuple(rgb_from_hex(color) for color in snapshot.pseudo_colors))
        self.controls.brush_diameter.setValue(snapshot.brush_diameter)
        self.controls.select_brush_shape(snapshot.brush_shape)
        self.controls.select_tool(snapshot.tool)
        self.controls.select_boundary_mode(snapshot.boundary_mode)
        self.controls.boundary_thickness.setValue(snapshot.boundary_thickness)

    def _stored_folders(self) -> tuple[str, str, str]:
        return (
            self.settings.value("folders/original", "", type=str),
            self.settings.value("folders/ternary", "", type=str),
            self.settings.value("folders/output", "", type=str),
        )

    def _stored_pairing_mode(self) -> PairingMode:
        raw = self.settings.value(
            "pairing/mode",
            PairingMode.STRICT_KEY.value,
            type=str,
        )
        try:
            return PairingMode(raw)
        except ValueError:
            return PairingMode.STRICT_KEY

    def _write_folders(
        self,
        folders: tuple[Path, Path, Path],
        pairing_mode: PairingMode,
    ) -> None:
        for key, folder in zip(("original", "ternary", "output"), folders, strict=True):
            self.settings.setValue(f"folders/{key}", str(folder))
        self.settings.setValue("pairing/mode", pairing_mode.value)

    @staticmethod
    def _decode_palette(value: Any) -> tuple[tuple[int, int, int], ...] | None:
        try:
            colors = tuple(
                tuple(int(channel) for channel in color.split(","))
                for color in str(value).split(";")
            )
        except (TypeError, ValueError):
            return None
        if len(colors) != 3 or any(len(color) != 3 for color in colors):
            return None
        if any(not 0 <= channel <= 255 for color in colors for channel in color):
            return None
        return colors

    def _show_about(self) -> None:
        show_information(
            self,
            "三値画像修正について",
            "原画像を参照し、三値ラベルだけを修正して別保存する。\n"
            "未保存編集の異常終了後の自動復元は初期版の対象外。",
        )

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if self._geometry_checked:
            return
        self._geometry_checked = True
        frame = self.frameGeometry()
        screens = QApplication.screens()
        if any(screen.availableGeometry().intersects(frame) for screen in screens):
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._stroke_before is not None:
            self._cancel_brush("筆跡を取消｜理由：終了操作")
        if self.canvas.memo_stroke_active:
            self.canvas.cancel_memo_stroke("メモ取消｜理由：終了操作")
        if self._allow_close_once:
            self._persist_current_settings()
            self._remove_application_event_filter()
            event.accept()
            return
        if self._active_job is not None:
            self._close_after_activity = True
            self._message("終了待機｜処理結果の確定後に終了確認を再開")
            event.ignore()
            return
        if self.session.is_loaded and self.session.is_dirty:
            choice = ask_unsaved(self, "終了")
            if choice == UnsavedChoice.SAVE:
                event.ignore()
                self.request_save(continuation=self._accept_close)
                return
            if choice == UnsavedChoice.CANCEL:
                event.ignore()
                return
        self._detach_component_result()
        self._persist_current_settings()
        self._remove_application_event_filter()
        event.accept()

    def _remove_application_event_filter(self) -> None:
        self._release_pointer_inputs()
        self.canvas.cancel_navigation_input()
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)

    def _persist_current_settings(self) -> None:
        try:
            snapshot = self._current_settings_snapshot()
            self.settings_repository.save(snapshot)
            self.applied_settings = snapshot
        except Exception as exc:  # noqa: BLE001 - 終了時設定保存境界
            show_error(
                self,
                "設定保存エラー",
                f"次回起動には現在の設定を反映できません。\n理由: {exc}",
            )

    def _accept_close(self) -> None:
        self._component_rerun_needed = False
        self._detach_component_result()
        self._allow_close_once = True
        self.close()
