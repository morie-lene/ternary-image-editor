"""保存データ、対応情報、画面状態の共有模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True, slots=True, order=True)
class PairKey:
    group: str
    suffix: str


class PairingMode(StrEnum):
    STRICT_KEY = "strict_key"
    NATURAL_ORDER = "natural_order"


@dataclass(frozen=True, slots=True)
class ImagePair:
    key: PairKey | None
    original_path: Path
    ternary_path: Path
    output_path: Path
    ternary_stem: str
    pairing_mode: PairingMode = PairingMode.STRICT_KEY


@dataclass(frozen=True, slots=True)
class ExcludedItem:
    reason_code: str
    message: str
    paths: tuple[Path, ...]
    key: PairKey | None = None


@dataclass(slots=True)
class PairingResult:
    pairs: list[ImagePair] = field(default_factory=list)
    excluded: list[ExcludedItem] = field(default_factory=list)
    output_writable: bool = True
    output_warning: str | None = None
    output_checked: bool = False
    pairing_mode: PairingMode = PairingMode.STRICT_KEY
    original_candidate_count: int = 0
    ternary_candidate_count: int = 0
    blocking_reason: str | None = None

    @property
    def counts_match(self) -> bool:
        return (
            self.original_candidate_count > 0
            and self.original_candidate_count == self.ternary_candidate_count
        )

    @property
    def confirmation_required(self) -> bool:
        return (
            self.pairing_mode is PairingMode.NATURAL_ORDER
            and bool(self.pairs)
            and self.blocking_reason is None
        )


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    size: int
    mtime_ns: int
    sha256: str


class FileRole(StrEnum):
    ORIGINAL = "original"
    INPUT_TERNARY = "input_ternary"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class FileBaseline:
    role: FileRole
    path: Path
    fingerprint: FileFingerprint | None


@dataclass(frozen=True, slots=True)
class ProtectedNormalizationReport:
    changed_pixels: int = 0

    @property
    def changed(self) -> bool:
        return self.changed_pixels > 0


@dataclass(frozen=True, slots=True)
class TernaryImportReport:
    source_format: str = "PNG"
    quantized: bool = False
    quantization_rule: str | None = None
    label_counts: tuple[int, int, int] = (0, 0, 0)
    recovered_output: bool = False
    recovery_reason: str | None = None
    source_mode: str | None = None

    @property
    def total_pixels(self) -> int:
        return sum(self.label_counts)


class EditSource(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class DocumentState(StrEnum):
    UNLOADED = "unloaded"
    CLEAN = "clean"
    DIRTY = "dirty"
    SAVED = "saved"
    PROCESSING = "processing"


@dataclass(slots=True)
class LoadedOriginal:
    rgb: np.ndarray
    path: Path
    fingerprint: FileFingerprint | None = None


@dataclass(slots=True)
class LoadedLabels:
    labels: np.ndarray
    path: Path
    fingerprint: FileFingerprint
    baseline_labels: np.ndarray | None = None
    normalization: ProtectedNormalizationReport = field(
        default_factory=ProtectedNormalizationReport
    )
    import_report: TernaryImportReport = field(default_factory=TernaryImportReport)
    requires_save: bool = False
