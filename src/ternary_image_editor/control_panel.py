"""右側の表示・編集・検査操作盤。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    DEFAULT_BRUSH_DIAMETER,
    DEFAULT_PSEUDO_RGB,
    MAX_BOUNDARY_THICKNESS,
    MAX_BRUSH_DIAMETER,
    MIN_BOUNDARY_THICKNESS,
    MIN_BRUSH_DIAMETER,
)


class EditorControls(QWidget):
    """UI部品を組み、意味のある値だけを signal として公開する。"""

    original_visibility_changed = Signal(bool)
    ternary_visibility_changed = Signal(bool)
    opacity_changed = Signal(int)
    pseudo_changed = Signal(bool)
    darken_comparison_changed = Signal(bool)
    pseudo_palette_changed = Signal(object)
    pseudo_settings_requested = Signal()
    grid_changed = Signal(bool)
    tool_changed = Signal(str)
    label_changed = Signal(int)
    label_cycle_requested = Signal(int)
    brush_shape_changed = Signal(str)
    brush_diameter_changed = Signal(int)
    boundary_mode_changed = Signal(str)
    boundary_thickness_changed = Signal(int)
    boundary_requested = Signal(str, int)
    small_components_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = tuple(DEFAULT_PSEUDO_RGB)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._build_view_group())
        layout.addWidget(self._build_edit_group())
        layout.addWidget(self._build_boundary_group())
        layout.addWidget(self._build_inspection_group())
        layout.addStretch(1)

    @property
    def pseudo_palette(self) -> tuple[tuple[int, int, int], ...]:
        return self._palette

    @property
    def selected_label(self) -> int:
        return self.label_group.checkedId()

    @property
    def selected_tool(self) -> str:
        return str(self.tool_group.checkedButton().property("tool"))

    @property
    def selected_boundary_mode(self) -> str:
        return str(self.boundary_mode.currentData())

    def set_palette(self, palette: tuple[tuple[int, int, int], ...]) -> None:
        if len(palette) != 3 or any(len(color) != 3 for color in palette):
            raise ValueError("疑似色はRGB三色でなければならない")
        normalized = tuple(tuple(int(channel) for channel in color) for color in palette)
        if any(not 0 <= channel <= 255 for color in normalized for channel in color):
            raise ValueError("疑似色成分は0から255でなければならない")
        self._palette = normalized
        for index, button in enumerate(self.palette_buttons):
            self._style_palette_button(button, self._palette[index])
        self.pseudo_palette_changed.emit(self._palette)

    def set_editing_available(self, available: bool) -> None:
        self.edit_group.setEnabled(available)
        self.boundary_group.setEnabled(available)

    def set_inspection_available(self, available: bool) -> None:
        self.inspection_group.setEnabled(available)

    def set_component_count(self, count: int | None) -> None:
        """旧APIを保ちつつ、合計だけ分かる場合の表示を更新する。"""

        self.component_count.setText("未解析" if count is None else f"{count} 成分")
        self.component_breakdown.setText("有 —｜境界 —")

    def set_component_counts(
        self,
        present: int | None,
        boundary: int | None,
    ) -> None:
        if present is None or boundary is None:
            self.component_count.setText("未解析")
            return
        self.component_count.setText(f"{present + boundary} 成分")
        self.component_breakdown.setText(f"有 {present}｜境界 {boundary}")

    def select_tool(self, tool: str) -> None:
        for button in self.tool_group.buttons():
            if button.property("tool") == tool:
                button.setChecked(True)
                self.tool_changed.emit(tool)
                return

    def select_label(self, label: int) -> None:
        button = self.label_group.button(label)
        if button is not None:
            button.setChecked(True)
            self._update_selected_label_text(label)
            self.label_changed.emit(label)

    def adjust_brush_diameter(self, delta: int) -> None:
        self.brush_diameter.setValue(self.brush_diameter.value() + delta)

    def select_brush_shape(self, shape: str) -> None:
        index = self.brush_shape.findData(shape)
        if index >= 0:
            self.brush_shape.setCurrentIndex(index)

    def cycle_brush_shape(self) -> None:
        shape = "square" if self.brush_shape.currentData() == "circle" else "circle"
        self.select_brush_shape(shape)

    def select_boundary_mode(self, mode: str) -> None:
        index = self.boundary_mode.findData(mode)
        if index >= 0:
            self.boundary_mode.setCurrentIndex(index)

    def adjust_boundary_thickness(self, delta: int) -> None:
        self.boundary_thickness.setValue(self.boundary_thickness.value() + delta)

    def _build_view_group(self) -> QGroupBox:
        group = QGroupBox("表示", self)
        layout = QVBoxLayout(group)

        self.original_visible = QCheckBox("原画像を表示", group)
        self.original_visible.setChecked(True)
        self.ternary_visible = QCheckBox("三値画像を表示", group)
        self.ternary_visible.setChecked(True)
        self.pseudo_enabled = QCheckBox("疑似色表示", group)
        self.darken_comparison = QCheckBox("比較（暗）", group)
        self.darken_comparison.setToolTip(
            "原画像と三値画像の各色成分の暗い方を表示する（保存画像には影響しない）"
        )
        self.grid_enabled = QCheckBox("画素格子を自動表示", group)
        self.grid_enabled.setChecked(True)
        layout.addWidget(self.original_visible)
        layout.addWidget(self.ternary_visible)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("原画像不透明度", group))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal, group)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(50)
        self.opacity_value = QLabel("50%", group)
        self.opacity_value.setMinimumWidth(38)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        layout.addLayout(opacity_row)
        layout.addWidget(self.pseudo_enabled)
        layout.addWidget(self.darken_comparison)

        palette_row = QHBoxLayout()
        palette_row.addWidget(QLabel("疑似色", group))
        self.palette_buttons: list[QPushButton] = []
        for index, name in enumerate(("無", "有", "境界")):
            button = QPushButton(name, group)
            button.setObjectName(f"pseudoColor{index}")
            button.setToolTip("疑似色の変更は設定画面で行う")
            button.clicked.connect(self.pseudo_settings_requested)
            self._style_palette_button(button, self._palette[index])
            self.palette_buttons.append(button)
            palette_row.addWidget(button)
        layout.addLayout(palette_row)
        layout.addWidget(self.grid_enabled)

        self.original_visible.toggled.connect(self.original_visibility_changed)
        self.ternary_visible.toggled.connect(self.ternary_visibility_changed)
        self.opacity_slider.valueChanged.connect(self._opacity_updated)
        self.pseudo_enabled.toggled.connect(self.pseudo_changed)
        self.darken_comparison.toggled.connect(self.darken_comparison_changed)
        self.grid_enabled.toggled.connect(self.grid_changed)
        return group

    def _build_edit_group(self) -> QGroupBox:
        self.edit_group = QGroupBox("編集", self)
        layout = QVBoxLayout(self.edit_group)

        tool_row = QHBoxLayout()
        self.tool_group = QButtonGroup(self)
        for text, tool in (("筆", "brush"), ("塗り潰し", "fill")):
            button = QRadioButton(text, self.edit_group)
            button.setProperty("tool", tool)
            self.tool_group.addButton(button)
            tool_row.addWidget(button)
        self.tool_group.buttons()[0].setChecked(True)
        layout.addLayout(tool_row)

        label_row = QHBoxLayout()
        self.label_group = QButtonGroup(self)
        for index, text in enumerate(("無", "有", "境界")):
            button = QRadioButton(text, self.edit_group)
            self.label_group.addButton(button, index)
            label_row.addWidget(button)
        self.label_group.button(1).setChecked(True)
        layout.addLayout(label_row)

        cycle_row = QHBoxLayout()
        self.previous_label = QPushButton("前の色", self.edit_group)
        self.next_label = QPushButton("次の色", self.edit_group)
        self.selected_label_text = QLabel("有｜#808080", self.edit_group)
        self.selected_label_text.setObjectName("selectedLabelText")
        cycle_row.addWidget(self.previous_label)
        cycle_row.addWidget(self.next_label)
        cycle_row.addWidget(self.selected_label_text, 1)
        layout.addLayout(cycle_row)

        form = QFormLayout()
        self.brush_shape = QComboBox(self.edit_group)
        self.brush_shape.addItem("円形", "circle")
        self.brush_shape.addItem("正方形", "square")
        self.brush_diameter = QSpinBox(self.edit_group)
        self.brush_diameter.setRange(MIN_BRUSH_DIAMETER, MAX_BRUSH_DIAMETER)
        self.brush_diameter.setValue(DEFAULT_BRUSH_DIAMETER)
        self.brush_diameter.setSuffix(" px")
        form.addRow("筆形状", self.brush_shape)
        form.addRow("筆径", self.brush_diameter)
        layout.addLayout(form)

        self.tool_group.buttonClicked.connect(
            lambda button: self.tool_changed.emit(str(button.property("tool")))
        )
        self.label_group.idClicked.connect(self._label_clicked)
        self.previous_label.clicked.connect(lambda: self.label_cycle_requested.emit(-1))
        self.next_label.clicked.connect(lambda: self.label_cycle_requested.emit(1))
        self.brush_shape.currentIndexChanged.connect(
            lambda: self.brush_shape_changed.emit(str(self.brush_shape.currentData()))
        )
        self.brush_diameter.valueChanged.connect(self.brush_diameter_changed)
        return self.edit_group

    def _build_boundary_group(self) -> QGroupBox:
        self.boundary_group = QGroupBox("境界生成", self)
        form = QFormLayout(self.boundary_group)
        self.boundary_mode = QComboBox(self.boundary_group)
        self.boundary_mode.addItem("無側へ生成", "none_side")
        self.boundary_mode.addItem("非無側へ生成", "non_none_side")
        self.boundary_thickness = QSpinBox(self.boundary_group)
        self.boundary_thickness.setRange(MIN_BOUNDARY_THICKNESS, MAX_BOUNDARY_THICKNESS)
        self.boundary_thickness.setValue(1)
        self.boundary_thickness.setSuffix(" px")
        self.boundary_button = QPushButton("境界を生成", self.boundary_group)
        form.addRow("生成方向", self.boundary_mode)
        form.addRow("太さ", self.boundary_thickness)
        form.addRow(self.boundary_button)
        self.boundary_button.clicked.connect(self._request_boundary)
        self.boundary_mode.currentIndexChanged.connect(
            lambda: self.boundary_mode_changed.emit(str(self.boundary_mode.currentData()))
        )
        self.boundary_thickness.valueChanged.connect(self.boundary_thickness_changed)
        return self.boundary_group

    def _build_inspection_group(self) -> QGroupBox:
        self.inspection_group = QGroupBox("検査", self)
        layout = QVBoxLayout(self.inspection_group)
        top = QHBoxLayout()
        self.small_components = QCheckBox("50画素以下を強調", self.inspection_group)
        self.component_count = QLabel("未解析", self.inspection_group)
        self.component_breakdown = QLabel("有 —｜境界 —", self.inspection_group)
        self.component_breakdown.setObjectName("componentBreakdown")
        top.addWidget(self.small_components, 1)
        top.addWidget(self.component_count)
        layout.addLayout(top)
        layout.addWidget(self.component_breakdown)
        self.small_components.toggled.connect(self.small_components_changed)
        return self.inspection_group

    def _opacity_updated(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self.opacity_changed.emit(value)

    def _request_boundary(self) -> None:
        self.boundary_requested.emit(
            self.selected_boundary_mode,
            self.boundary_thickness.value(),
        )

    def _label_clicked(self, label: int) -> None:
        self._update_selected_label_text(label)
        self.label_changed.emit(label)

    def _update_selected_label_text(self, label: int) -> None:
        names = ("無", "有", "境界")
        colors = ("#000000", "#808080", "#FFFFFF")
        if 0 <= label < len(names):
            self.selected_label_text.setText(f"{names[label]}｜{colors[label]}")

    @staticmethod
    def _style_palette_button(button: QPushButton, color: tuple[int, int, int]) -> None:
        red, green, blue = color
        luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        foreground = "#111" if luminance > 150 else "#fff"
        button.setStyleSheet(
            f"QPushButton {{ background: rgb({red}, {green}, {blue}); color: {foreground}; }}"
        )
