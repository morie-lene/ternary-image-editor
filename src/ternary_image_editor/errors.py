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
        return f"フォルダを利用できません\n場所: {self.path}\n理由: {self.reason}"


@dataclass(slots=True)
class ImageValidationError(TernaryEditorError):
    path: Path
    reason: str
    details: tuple[str, ...] = ()
    observed_sha256: str | None = None

    def __str__(self) -> str:
        lines = [
            "画像を読み込めません",
            f"ファイル: {self.path}",
            f"理由: {self.reason}",
        ]
        if self.details:
            lines.append(f"詳細: {'; '.join(self.details)}")
        return "\n".join(lines)


@dataclass(slots=True)
class PairDimensionError(TernaryEditorError):
    original_path: Path
    original_size: tuple[int, int]
    ternary_path: Path
    ternary_size: tuple[int, int]
    ternary_role: str = "入力三値画像"
    ternary_sha256: str | None = None

    def __str__(self) -> str:
        return (
            "画像対の寸法が一致しません\n"
            f"原画像（表示方向反映後）: {self.original_path} "
            f"({self.original_size[0]}x{self.original_size[1]})\n"
            f"{self.ternary_role}: {self.ternary_path} "
            f"({self.ternary_size[0]}x{self.ternary_size[1]})"
        )


@dataclass(slots=True)
class JpegImportConfirmationRequired(TernaryEditorError):
    path: Path

    def __str__(self) -> str:
        return f"JPEG三値画像の変換確認が必要です\nファイル: {self.path}"


@dataclass(slots=True)
class AtomicSaveError(TernaryEditorError):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"画像を保存できません\nファイル: {self.path}\n理由: {self.reason}"


@dataclass(slots=True)
class ExternalModificationError(TernaryEditorError):
    path: Path
    expected_sha256: str | None
    actual_sha256: str | None

    def __str__(self) -> str:
        return f"出力画像は読み込み後に外部変更されています\nファイル: {self.path}"


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
        return f"{source}は読み込み後に外部変更されています\nファイル: {self.path}"


@dataclass(slots=True)
class OutputSaveLockError(TernaryEditorError):
    path: Path
    lock_path: Path
    reason: str

    def __str__(self) -> str:
        return (
            "出力画像の保存ロックを取得できません\n"
            f"ファイル: {self.path}\n理由: {self.reason}"
        )


class BusyError(TernaryEditorError):
    """競合操作が処理中に要求された。"""


class NoImageLoadedError(TernaryEditorError):
    """有効な画像対が開かれていない。"""
