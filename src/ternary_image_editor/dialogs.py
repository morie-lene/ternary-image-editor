"""状態遷移を曖昧にしない選択ダイアログ。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import PairingMode, PairingResult


class UnsavedChoice(StrEnum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


class ExistingOutputChoice(StrEnum):
    OUTPUT = "output"
    INPUT = "input"
    CANCEL = "cancel"


class ExternalChangeChoice(StrEnum):
    RELOAD = "reload"
    OVERWRITE = "overwrite"
    CANCEL = "cancel"


class InputChangeChoice(StrEnum):
    RELOAD_DISCARD = "reload_discard"
    SAVE_SNAPSHOT = "save_snapshot"
    CANCEL = "cancel"


class FolderSelectionDialog(QDialog):
    """原画像・三値画像・出力の三フォルダを一取引で選ぶ。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        original: str = "",
        ternary: str = "",
        output: str = "",
        pairing_mode: PairingMode | str = PairingMode.STRICT_KEY,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("フォルダを指定")
        self.setModal(True)
        self.resize(720, 220)

        self.original_edit = QLineEdit(original)
        self.ternary_edit = QLineEdit(ternary)
        self.output_edit = QLineEdit(output)
        self.pairing_mode_combo = QComboBox(self)
        self.pairing_mode_combo.addItem("仕様キーで厳格対応", PairingMode.STRICT_KEY.value)
        self.pairing_mode_combo.addItem(
            "ファイル名の自然順で対応（確認必須）",
            PairingMode.NATURAL_ORDER.value,
        )
        requested_mode = PairingMode(pairing_mode)
        requested_index = self.pairing_mode_combo.findData(requested_mode.value)
        self.pairing_mode_combo.setCurrentIndex(max(requested_index, 0))
        form = QFormLayout()
        form.addRow("原画像フォルダ", self._path_row(self.original_edit))
        form.addRow("三値画像フォルダ", self._path_row(self.ternary_edit))
        form.addRow("編集済み画像出力フォルダ", self._path_row(self.output_edit))
        form.addRow("対応方式", self.pairing_mode_combo)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        for edit in (self.original_edit, self.ternary_edit, self.output_edit):
            edit.textChanged.connect(self._update_accept_enabled)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self._update_accept_enabled()

    @property
    def folders(self) -> tuple[Path, Path, Path]:
        return (
            Path(self.original_edit.text()),
            Path(self.ternary_edit.text()),
            Path(self.output_edit.text()),
        )

    @property
    def pairing_mode(self) -> PairingMode:
        return PairingMode(str(self.pairing_mode_combo.currentData()))

    def _path_row(self, edit: QLineEdit) -> QWidget:
        row = QWidget(self)
        button = QPushButton("参照…", row)
        button.clicked.connect(lambda: self._browse(edit))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    def _browse(self, edit: QLineEdit) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "フォルダを選択",
            edit.text(),
            QFileDialog.Option.ShowDirsOnly,
        )
        if selected:
            edit.setText(selected)

    def _update_accept_enabled(self) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(
            all(
                edit.text().strip()
                for edit in (self.original_edit, self.ternary_edit, self.output_edit)
            )
        )


class NaturalPairingPreviewDialog(QDialog):
    """自然順で提案された全対応を、確定前に並列表として示す。"""

    def __init__(self, result: PairingResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if result.pairing_mode is not PairingMode.NATURAL_ORDER:
            raise ValueError("自然順の対応計画だけを確認できる")
        self.setWindowTitle("自然順の対応を確認")
        self.setModal(True)
        self.resize(1100, 620)

        explanation = QLabel(
            "原画像群と三値画像群を別々に自然順整列した結果だ。"
            "行の対応を全件確認してから読み込め。",
            self,
        )
        explanation.setWordWrap(True)

        self.table = QTableWidget(len(result.pairs), 4, self)
        self.table.setHorizontalHeaderLabels(("番号", "原画像", "三値画像", "出力PNG"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

        for row, pair in enumerate(result.pairs):
            values = (
                str(row + 1),
                pair.original_path.name,
                pair.ternary_path.name,
                pair.output_path.name,
            )
            paths = (None, pair.original_path, pair.ternary_path, pair.output_path)
            for column, (value, path) in enumerate(zip(values, paths, strict=True)):
                item = QTableWidgetItem(value)
                if path is not None:
                    item.setToolTip(str(path))
                self.table.setItem(row, column, item)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        accept = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        accept.setText("この対応で読み込む")
        cancel = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("中止")
        cancel.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.buttons)


def confirm_natural_pairing(parent: QWidget, result: PairingResult) -> bool:
    return NaturalPairingPreviewDialog(result, parent).exec() == QDialog.DialogCode.Accepted


def confirm_ternary_jpeg_import(parent: QWidget, path: Path) -> bool:
    """不可逆なJPEG三値化を開く直前に一件ずつ確認する。"""

    box = QMessageBox(parent)
    box.setWindowTitle("JPEG三値画像を変換")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(
        "JPEG圧縮で元の三色値が変化しているため、ソフトウェア側で三値化する。"
    )
    box.setInformativeText(
        "sRGB上で黒・灰・白の最も近い色へ各画素を割り当てる。"
        "同距離なら黒、次いで灰を優先する。"
        "入力JPEGは変更せず、保存時にRGB PNGを新規作成または明示上書きする。\n"
        f"{path}"
    )
    accept = box.addButton("三値化して開く", QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("中止", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is accept


def ask_unsaved(parent: QWidget, action_name: str) -> UnsavedChoice:
    box = QMessageBox(parent)
    box.setWindowTitle("未保存の変更")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(f"未保存の変更がある。{action_name}前に処理を選べ。")
    save = box.addButton("保存して続行", QMessageBox.ButtonRole.AcceptRole)
    discard = box.addButton("変更を破棄して続行", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("中止", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save:
        return UnsavedChoice.SAVE
    if clicked is discard:
        return UnsavedChoice.DISCARD
    return UnsavedChoice.CANCEL


def ask_existing_output(parent: QWidget, output_path: Path) -> ExistingOutputChoice:
    box = QMessageBox(parent)
    box.setWindowTitle("編集済み画像あり")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(f"編集済み画像が存在する。編集元を選べ。\n{output_path}")
    output = box.addButton("編集済み画像から続ける", QMessageBox.ButtonRole.AcceptRole)
    input_button = box.addButton("入力三値画像から始める", QMessageBox.ButtonRole.ActionRole)
    cancel = box.addButton("中止", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is output:
        return ExistingOutputChoice.OUTPUT
    if clicked is input_button:
        return ExistingOutputChoice.INPUT
    return ExistingOutputChoice.CANCEL


def ask_external_change(parent: QWidget, output_path: Path) -> ExternalChangeChoice:
    box = QMessageBox(parent)
    box.setWindowTitle("外部変更を検出")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(f"出力画像が外部で変更されている。\n{output_path}")
    reload_button = box.addButton("外部版を開く", QMessageBox.ButtonRole.ActionRole)
    overwrite = box.addButton("現在内容で上書き", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("操作中止", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is reload_button:
        return ExternalChangeChoice.RELOAD
    if clicked is overwrite:
        return ExternalChangeChoice.OVERWRITE
    return ExternalChangeChoice.CANCEL


def ask_input_change(
    parent: QWidget,
    changed_paths: tuple[Path, ...] | list[Path],
) -> InputChangeChoice:
    """読込元が外部変更された際、現在編集の扱いを明示させる。"""

    box = QMessageBox(parent)
    box.setWindowTitle("読込元の外部変更を検出")
    box.setIcon(QMessageBox.Icon.Warning)
    rendered = "\n".join(str(path) for path in changed_paths)
    box.setText(f"原画像または入力三値画像が読込後に変更されている。\n{rendered}")
    reload_button = box.addButton(
        "再読込して現在編集を破棄",
        QMessageBox.ButtonRole.DestructiveRole,
    )
    snapshot_button = box.addButton(
        "読込済み内容を確認して保存",
        QMessageBox.ButtonRole.ActionRole,
    )
    cancel = box.addButton("操作中止", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is reload_button:
        return InputChangeChoice.RELOAD_DISCARD
    if clicked is snapshot_button:
        confirm = QMessageBox.warning(
            parent,
            "読込済み内容で保存",
            "外部で更新された読込元ではなく、現在メモリ上のスナップショットを保存する。"
            "本当に続けるか。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            return InputChangeChoice.SAVE_SNAPSHOT
    return InputChangeChoice.CANCEL


def confirm_overwrite(parent: QWidget, output_path: Path) -> bool:
    result = QMessageBox.warning(
        parent,
        "既存出力を置換",
        f"既存の編集済み画像を置換する。続けるか。\n{output_path}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    return result == QMessageBox.StandardButton.Yes


def show_error(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message, QMessageBox.StandardButton.Ok)


def show_information(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message, QMessageBox.StandardButton.Ok)
