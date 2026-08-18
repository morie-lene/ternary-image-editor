"""状態遷移を曖昧にしない選択ダイアログ。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("フォルダを指定")
        self.setModal(True)
        self.resize(720, 180)

        self.original_edit = QLineEdit(original)
        self.ternary_edit = QLineEdit(ternary)
        self.output_edit = QLineEdit(output)
        form = QFormLayout()
        form.addRow("原画像フォルダ", self._path_row(self.original_edit))
        form.addRow("三値画像フォルダ", self._path_row(self.ternary_edit))
        form.addRow("編集済み画像出力フォルダ", self._path_row(self.output_edit))

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
