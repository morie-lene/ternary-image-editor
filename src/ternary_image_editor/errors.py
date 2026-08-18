"""利用者へ意味のある理由を返すための領域例外。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class TernaryEditorError(Exception):
    """アプリケーション領域の基底例外。"""


@dataclass(slots=True)
class FolderAccessError(TernaryEditorError):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"フォルダを利用できない: {self.path} ({self.reason})"


@dataclass(slots=True)
class ImageValidationError(TernaryEditorError):
    path: Path
    reason: str
    details: tuple[str, ...] = ()

    def __str__(self) -> str:
        suffix = f": {'; '.join(self.details)}" if self.details else ""
        return f"画像を利用できない: {self.path} ({self.reason}){suffix}"


@dataclass(slots=True)
class AtomicSaveError(TernaryEditorError):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"保存に失敗した: {self.path} ({self.reason})"


@dataclass(slots=True)
class ExternalModificationError(TernaryEditorError):
    path: Path
    expected_sha256: str | None
    actual_sha256: str | None

    def __str__(self) -> str:
        return f"出力ファイルが外部で変更されている: {self.path}"


@dataclass(slots=True)
class ExternalOutputModificationError(ExternalModificationError):
    """既存の基底例外との互換性を保った、出力専用の競合型。"""


@dataclass(slots=True)
class ExternalSourceModificationError(TernaryEditorError):
    source_kind: str
    path: Path
    expected_sha256: str | None
    actual_sha256: str | None

    def __str__(self) -> str:
        source = "原画像" if self.source_kind == "original" else "入力三値画像"
        return f"{source}が外部で変更されている: {self.path}"


@dataclass(slots=True)
class OutputSaveLockError(TernaryEditorError):
    path: Path
    lock_path: Path
    reason: str

    def __str__(self) -> str:
        return f"出力の保存ロックを取得できない: {self.path} ({self.reason})"


class BusyError(TernaryEditorError):
    """競合操作が処理中に要求された。"""


class NoImageLoadedError(TernaryEditorError):
    """有効な画像対が開かれていない。"""
