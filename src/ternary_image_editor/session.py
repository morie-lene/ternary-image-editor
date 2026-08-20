"""一画像の編集セッション、履歴、保存、非同期陳腐化を束ねる。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray

from .constants import TERNARY_JPEG_EXTENSIONS
from .errors import (
    BusyError,
    ExternalOutputModificationError,
    ImageValidationError,
    JpegImportConfirmationRequired,
    NoImageLoadedError,
    PairDimensionError,
)
from .history import HistoryManager, HistoryTrimReport, PixelDelta, make_pixel_delta
from .image_io import (
    fingerprint_file,
    load_editable_output_image,
    load_original_image,
    load_ternary_image,
    normalized_protected_labels_copy,
    save_labels_atomic,
)
from .models import (
    DocumentState,
    EditSource,
    FileBaseline,
    FileFingerprint,
    FileRole,
    ImagePair,
    ProtectedNormalizationReport,
    TernaryImportReport,
)
from .workers import TaskToken

UInt8Array = NDArray[np.uint8]


class Activity(StrEnum):
    """文書状態とは別軸の処理活動。"""

    IDLE = "idle"
    SAVING = "saving"
    FILLING = "filling"
    BOUNDARY = "boundary"
    COMPONENTS = "components"


_EXCLUSIVE_ACTIVITIES = frozenset({Activity.SAVING, Activity.FILLING, Activity.BOUNDARY})


class ImageSession:
    """一画像対を開いてから離れるまでの編集状態。"""

    def __init__(self) -> None:
        self._pair: ImagePair | None = None
        self._original_rgb: UInt8Array | None = None
        self._labels: UInt8Array | None = None
        self._committed_labels: UInt8Array | None = None
        self._baseline_labels: UInt8Array | None = None
        self._edit_source: EditSource | None = None
        self._original_fingerprint: FileFingerprint | None = None
        self._ternary_fingerprint: FileFingerprint | None = None
        self._output_fingerprint: FileFingerprint | None = None
        self._normalization = ProtectedNormalizationReport()
        self._import_report = TernaryImportReport()
        self._import_requires_save = False
        self._baseline_is_output = False
        self._history = HistoryManager()
        self._session_id: str | None = None
        self._revision = 0
        self._activity = Activity.IDLE
        self._active_task_token: TaskToken | None = None
        self._active_task_labels: UInt8Array | None = None

    @property
    def pair(self) -> ImagePair | None:
        return self._pair

    @property
    def original_rgb(self) -> UInt8Array | None:
        return self._original_rgb

    @property
    def labels(self) -> UInt8Array | None:
        """作業配列を返す。stroke中の直接変更後はcommit_preappliedを必ず呼ぶ。"""

        return self._labels

    @property
    def edit_source(self) -> EditSource | None:
        return self._edit_source

    @property
    def output_fingerprint(self) -> FileFingerprint | None:
        return self._output_fingerprint

    @property
    def original_fingerprint(self) -> FileFingerprint | None:
        return self._original_fingerprint

    @property
    def ternary_fingerprint(self) -> FileFingerprint | None:
        return self._ternary_fingerprint

    @property
    def baseline_labels(self) -> UInt8Array | None:
        return self._baseline_labels

    @property
    def normalization(self) -> ProtectedNormalizationReport:
        return self._normalization

    @property
    def import_report(self) -> TernaryImportReport:
        return self._import_report

    @property
    def import_requires_save(self) -> bool:
        return self._import_requires_save

    @property
    def history(self) -> HistoryManager:
        return self._history

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def activity(self) -> Activity:
        return self._activity

    @property
    def is_loaded(self) -> bool:
        return self._pair is not None and self._labels is not None

    @property
    def is_dirty(self) -> bool:
        if not self.is_loaded or self._baseline_labels is None:
            return False
        if self._import_requires_save:
            return True
        labels = self._require_labels()
        baseline = self._baseline_labels
        if (
            labels.dtype != np.uint8
            or labels.ndim != 2
            or labels.shape != baseline.shape
            or not bool(np.all(labels <= 2))
        ):
            return True
        return not np.array_equal(labels, baseline)

    @property
    def can_undo(self) -> bool:
        return self.is_loaded and not self._has_uncommitted_labels() and self._history.can_undo

    @property
    def can_redo(self) -> bool:
        return self.is_loaded and not self._has_uncommitted_labels() and self._history.can_redo

    @property
    def has_saved_current(self) -> bool:
        """現在内容が直前に正常保存した出力基線と一致するか。"""

        return (
            self.is_loaded
            and not self._has_uncommitted_labels()
            and self._output_fingerprint is not None
            and self._baseline_is_output
            and not self.is_dirty
        )

    @property
    def state(self) -> DocumentState:
        if not self.is_loaded:
            return DocumentState.UNLOADED
        if self._activity != Activity.IDLE:
            return DocumentState.PROCESSING
        if self.is_dirty:
            return DocumentState.DIRTY
        if self.has_saved_current:
            return DocumentState.SAVED
        return DocumentState.CLEAN

    def open_pair(
        self,
        pair: ImagePair,
        source: EditSource | str,
        *,
        expected_size: tuple[int, int] | None = None,
        allow_jpeg_import: bool = False,
    ) -> None:
        """画像対を取引的に読み、成功後だけ新しいセッションへ切り替える。"""

        self._ensure_transition_allowed()
        edit_source = EditSource(source)
        ternary_path = Path(pair.ternary_path)
        if (
            edit_source == EditSource.INPUT
            and ternary_path.suffix.casefold() in TERNARY_JPEG_EXTENSIONS
            and not allow_jpeg_import
        ):
            raise JpegImportConfirmationRequired(ternary_path)
        loaded_original = load_original_image(pair.original_path, expected_size=expected_size)
        original_size = (
            int(loaded_original.rgb.shape[1]),
            int(loaded_original.rgb.shape[0]),
        )
        if edit_source == EditSource.OUTPUT:
            loaded_labels = load_editable_output_image(
                pair.output_path,
                expected_size=expected_size,
            )
            label_size = (
                int(loaded_labels.labels.shape[1]),
                int(loaded_labels.labels.shape[0]),
            )
            label_path = pair.output_path
            label_role = "編集済み画像"
            ternary_fingerprint = None
        else:
            loaded_input = load_ternary_image(
                ternary_path,
                expected_size=expected_size,
            )
            loaded_labels = loaded_input
            label_size = (
                int(loaded_input.labels.shape[1]),
                int(loaded_input.labels.shape[0]),
            )
            label_path = pair.ternary_path
            label_role = "入力三値画像"
            ternary_fingerprint = loaded_input.fingerprint
        if original_size != label_size:
            raise PairDimensionError(
                original_path=pair.original_path,
                original_size=original_size,
                ternary_path=label_path,
                ternary_size=label_size,
                ternary_role=label_role,
                ternary_sha256=loaded_labels.fingerprint.sha256,
            )
        try:
            current_output_fingerprint = fingerprint_file(pair.output_path)
        except OSError as exc:
            if edit_source == EditSource.OUTPUT:
                raise ImageValidationError(
                    pair.output_path,
                    "編集済み画像の読込に失敗",
                    (str(exc),),
                ) from exc
            # 入力版は、壊れた・読めない・通常ファイルでない既存出力があっても
            # 開けるようにする。保存時には改めて検査し、無言では置換しない。
            current_output_fingerprint = None

        if edit_source == EditSource.OUTPUT and not _same_content(
            loaded_labels.fingerprint,
            current_output_fingerprint,
        ):
            raise ExternalOutputModificationError(
                path=pair.output_path,
                expected_sha256=loaded_labels.fingerprint.sha256,
                actual_sha256=(
                    None
                    if current_output_fingerprint is None
                    else current_output_fingerprint.sha256
                ),
            )

        labels = _owned_labels(
            loaded_labels.labels,
            expected_shape=(original_size[1], original_size[0]),
        )
        source_baseline = (
            loaded_labels.labels
            if loaded_labels.baseline_labels is None
            else loaded_labels.baseline_labels
        )
        baseline_labels = _immutable_labels_copy(
            _owned_labels(
                source_baseline,
                expected_shape=(original_size[1], original_size[0]),
            )
        )
        original_rgb = _owned_original_rgb(
            loaded_original.rgb,
            expected_shape=(original_size[1], original_size[0], 3),
        )
        committed_labels = _immutable_labels_copy(labels)
        new_session_id = uuid4().hex

        self._history.reset(
            clean=np.array_equal(labels, baseline_labels) and not loaded_labels.requires_save
        )
        self._pair = pair
        self._original_rgb = original_rgb
        self._labels = labels
        self._committed_labels = committed_labels
        self._baseline_labels = baseline_labels
        self._edit_source = edit_source
        self._original_fingerprint = loaded_original.fingerprint
        self._ternary_fingerprint = ternary_fingerprint
        self._output_fingerprint = current_output_fingerprint
        self._normalization = loaded_labels.normalization
        self._import_report = loaded_labels.import_report
        self._import_requires_save = loaded_labels.requires_save
        self._baseline_is_output = edit_source == EditSource.OUTPUT
        self._session_id = new_session_id
        self._revision = 0
        self._activity = Activity.IDLE
        self._active_task_token = None
        self._active_task_labels = None

    def close(self) -> None:
        """現在セッションを破棄し、進行中結果を旧session_idへ閉じ込める。"""

        self._ensure_transition_allowed()
        self._pair = None
        self._original_rgb = None
        self._labels = None
        self._committed_labels = None
        self._baseline_labels = None
        self._edit_source = None
        self._original_fingerprint = None
        self._ternary_fingerprint = None
        self._output_fingerprint = None
        self._normalization = ProtectedNormalizationReport()
        self._import_report = TernaryImportReport()
        self._import_requires_save = False
        self._baseline_is_output = False
        self._history.reset(clean=True)
        self._session_id = None
        self._revision = 0
        self._activity = Activity.IDLE
        self._active_task_token = None
        self._active_task_labels = None

    def apply_labels(
        self,
        new_labels: np.ndarray,
        description: str,
    ) -> HistoryTrimReport | None:
        """外部配列を所有コピーへ変え、一操作として現在配列を置換する。"""

        self._ensure_edit_allowed()
        labels = self._require_labels()
        owned = _owned_labels(new_labels, expected_shape=labels.shape)
        owned, _changed_pixels = normalized_protected_labels_copy(owned)
        delta = make_pixel_delta(labels, owned, description)
        if delta is None:
            return None
        committed_labels = _immutable_labels_copy(owned)
        report = self._history.record(delta)
        self._labels = owned
        self._committed_labels = committed_labels
        self._revision += 1
        return report

    def commit_preapplied(
        self,
        before_labels: np.ndarray,
        description: str,
    ) -> HistoryTrimReport | None:
        """既に作業配列へ適用済みのstroke等を一操作として確定する。"""

        self._ensure_edit_allowed(allow_preapplied=True)
        labels = self._require_labels()
        committed = self._require_committed_labels()
        try:
            before = _owned_labels(before_labels, expected_shape=committed.shape)
            if not np.array_equal(before, committed):
                raise ValueError("筆操作前の配列が確定済み状態と一致しない")
            _validate_internal_labels(labels, expected_shape=committed.shape)
            _force_protected_none_inplace(labels)
        except ValueError:
            self._restore_committed_labels()
            raise

        delta = make_pixel_delta(committed, labels, description)
        if delta is None:
            return None
        committed_labels = _immutable_labels_copy(labels)
        try:
            report = self._history.record(delta)
        except Exception:
            self._restore_committed_labels()
            raise
        self._committed_labels = committed_labels
        self._revision += 1
        return report

    def undo(self) -> PixelDelta | None:
        self._ensure_edit_allowed()
        delta = self._history.undo(self._require_labels())
        if delta is not None:
            _force_protected_none_inplace(self._require_labels())
            self._committed_labels = _immutable_labels_copy(self._require_labels())
            self._revision += 1
        return delta

    def redo(self) -> PixelDelta | None:
        self._ensure_edit_allowed()
        delta = self._history.redo(self._require_labels())
        if delta is not None:
            _force_protected_none_inplace(self._require_labels())
            self._committed_labels = _immutable_labels_copy(self._require_labels())
            self._revision += 1
        return delta

    def begin_activity(self, activity: Activity | str) -> TaskToken:
        """一つの処理活動を開始し、その入力状態を表すtokenを返す。"""

        self._require_loaded()
        requested = Activity(activity)
        if requested == Activity.IDLE:
            raise ValueError("idleは処理活動として開始できない")
        if requested != Activity.COMPONENTS:
            self._ensure_no_uncommitted_labels()
        if self._activity != Activity.IDLE and not (
            self._activity == Activity.COMPONENTS and requested != Activity.COMPONENTS
        ):
            raise BusyError("別の処理が進行中")
        self._activity = requested
        return self.make_task_token()

    def make_task_token(self) -> TaskToken:
        """現在活動と画像改訂を束ねた非同期照合tokenを返す。"""

        self._require_loaded()
        if self._activity == Activity.IDLE:
            raise ValueError("idle状態には処理tokenがない")
        if self._activity != Activity.COMPONENTS:
            self._ensure_no_uncommitted_labels()
        labels = self._require_labels()
        committed = self._require_committed_labels()
        _validate_internal_labels(labels, expected_shape=committed.shape)
        assert self._session_id is not None
        token = TaskToken(
            session_id=self._session_id,
            revision=self._revision,
            activity=self._activity.value,
        )
        self._active_task_token = token
        self._active_task_labels = _immutable_labels_copy(labels)
        return token

    def is_token_current(self, token: TaskToken) -> bool:
        return (
            self.is_loaded
            and token is self._active_task_token
            and self._session_id == token.session_id
            and self._revision == token.revision
            and self._activity.value == token.activity
            and self._active_task_labels is not None
            and _same_labels(self._require_labels(), self._active_task_labels)
        )

    def finish_activity(self, token: TaskToken) -> bool:
        """token結果の有効性を返し、同じ活動なら陳腐化後でも処理表示を解く。"""

        is_current = self.is_token_current(token)
        owns_current_activity = (
            self.is_loaded
            and token is self._active_task_token
            and self._session_id == token.session_id
            and self._activity.value == token.activity
        )
        if owns_current_activity:
            self._activity = Activity.IDLE
            self._active_task_token = None
            self._active_task_labels = None
        return is_current

    def save(
        self,
        *,
        force: bool = False,
        allow_existing_output: bool = False,
        allow_stale_sources: bool = False,
        expected_size: tuple[int, int] | None = None,
    ) -> FileFingerprint:
        """現在配列を保存し、成功時だけ保存点と出力指紋を更新する。

        ``allow_existing_output`` は入力版から始めた際の既存出力を置換する許可、
        ``force`` は読込後の出力変更まで現在内容で上書きする別の許可である。
        ``allow_stale_sources`` は読込済み入力snapshotを使う明示確認にだけ用いる。
        """

        self._require_loaded()
        self._ensure_no_uncommitted_labels()
        if self._activity not in {Activity.IDLE, Activity.COMPONENTS}:
            raise BusyError("別の処理が進行中")
        labels = self._require_labels()
        current_size = (int(labels.shape[1]), int(labels.shape[0]))
        if expected_size is not None and expected_size != current_size:
            raise ValueError(
                f"保存指定寸法が現在画像と一致しない: {expected_size} != {current_size}"
            )
        assert self._pair is not None
        self._activity = Activity.SAVING
        self._active_task_token = None
        self._active_task_labels = None
        try:
            expected_fingerprint = self._output_fingerprint
            if (
                self._edit_source == EditSource.INPUT
                and not self._baseline_is_output
                and self._output_fingerprint is not None
                and not allow_existing_output
                and not force
            ):
                expected_fingerprint = None
            source_baselines = [
                FileBaseline(
                    role=FileRole.ORIGINAL,
                    path=self._pair.original_path,
                    fingerprint=self._original_fingerprint,
                )
            ]
            if self._edit_source == EditSource.INPUT:
                source_baselines.append(
                    FileBaseline(
                        role=FileRole.INPUT_TERNARY,
                        path=self._pair.ternary_path,
                        fingerprint=self._ternary_fingerprint,
                    )
                )
            fingerprint = save_labels_atomic(
                labels,
                self._pair.output_path,
                expected_fingerprint=expected_fingerprint,
                force=force,
                source_baselines=source_baselines,
                allow_stale_sources=allow_stale_sources,
                expected_size=current_size,
            )
            saved_labels, _changed_pixels = normalized_protected_labels_copy(labels)
            self._history.mark_saved()
            self._labels = saved_labels
            self._committed_labels = _immutable_labels_copy(saved_labels)
            self._baseline_labels = _immutable_labels_copy(saved_labels)
            self._baseline_is_output = True
            self._normalization = ProtectedNormalizationReport()
            self._import_requires_save = False
            self._output_fingerprint = fingerprint
            return fingerprint
        finally:
            self._activity = Activity.IDLE

    def _ensure_transition_allowed(self) -> None:
        if self._activity in _EXCLUSIVE_ACTIVITIES:
            raise BusyError("書込処理中は画像を切り替えられない")

    def _ensure_edit_allowed(self, *, allow_preapplied: bool = False) -> None:
        self._require_loaded()
        if self._activity in _EXCLUSIVE_ACTIVITIES:
            raise BusyError("書込処理中は編集できない")
        if not allow_preapplied:
            self._ensure_no_uncommitted_labels()

    def _ensure_no_uncommitted_labels(self) -> None:
        if self._has_uncommitted_labels():
            raise BusyError("未確定の筆操作を先に確定または破棄する必要がある")

    def _has_uncommitted_labels(self) -> bool:
        if self._labels is None or self._committed_labels is None:
            return False
        labels = self._labels
        committed = self._committed_labels
        return (
            labels.dtype != np.uint8
            or labels.ndim != 2
            or labels.shape != committed.shape
            or not labels.flags.c_contiguous
            or not labels.flags.writeable
            or not bool(np.all(labels <= 2))
            or not np.array_equal(labels, committed)
        )

    def _restore_committed_labels(self) -> None:
        self._labels = np.array(
            self._require_committed_labels(),
            dtype=np.uint8,
            order="C",
            copy=True,
        )

    def _require_loaded(self) -> None:
        if not self.is_loaded:
            raise NoImageLoadedError("画像が読み込まれていない")

    def _require_labels(self) -> UInt8Array:
        self._require_loaded()
        assert self._labels is not None
        return self._labels

    def _require_committed_labels(self) -> UInt8Array:
        self._require_loaded()
        assert self._committed_labels is not None
        return self._committed_labels


def _owned_labels(labels: np.ndarray, *, expected_shape: tuple[int, ...]) -> UInt8Array:
    array = np.asarray(labels)
    _validate_label_values(array, expected_shape=expected_shape)
    return np.array(array, dtype=np.uint8, order="C", copy=True)


def _immutable_labels_copy(labels: np.ndarray) -> UInt8Array:
    copied = np.array(labels, dtype=np.uint8, order="C", copy=True)
    copied.setflags(write=False)
    return copied


def _force_protected_none_inplace(labels: UInt8Array) -> None:
    normalized, changed_pixels = normalized_protected_labels_copy(labels)
    if changed_pixels:
        labels[:] = normalized


def _same_labels(left: np.ndarray, right: np.ndarray) -> bool:
    return (
        left.dtype == np.uint8
        and left.ndim == 2
        and left.shape == right.shape
        and left.flags.c_contiguous
        and left.flags.writeable
        and bool(np.all(left <= 2))
        and np.array_equal(left, right)
    )


def _validate_internal_labels(labels: np.ndarray, *, expected_shape: tuple[int, ...]) -> None:
    _validate_label_values(labels, expected_shape=expected_shape)
    if not labels.flags.c_contiguous:
        raise ValueError("作業ラベル配列はC連続でなければならない")
    if not labels.flags.writeable:
        raise ValueError("作業ラベル配列は書込可能でなければならない")


def _validate_label_values(labels: np.ndarray, *, expected_shape: tuple[int, ...]) -> None:
    if labels.dtype != np.uint8 or labels.ndim != 2:
        raise ValueError("ラベル配列はuint8二次元でなければならない")
    if labels.shape != expected_shape:
        raise ValueError(f"ラベル配列寸法が一致しない: {labels.shape} != {expected_shape}")
    if not bool(np.all(labels <= 2)):
        raise ValueError("ラベル配列に0/1/2以外を含む")


def _owned_original_rgb(
    rgb: np.ndarray,
    *,
    expected_shape: tuple[int, int, int],
) -> UInt8Array:
    array = np.asarray(rgb)
    if array.dtype != np.uint8 or array.shape != expected_shape:
        raise ValueError("原画像RGB配列の型または寸法が不正")
    owned = np.array(array, dtype=np.uint8, order="C", copy=True)
    owned.setflags(write=False)
    return owned


def _same_content(
    expected: FileFingerprint,
    actual: FileFingerprint | None,
) -> bool:
    return actual is not None and expected.size == actual.size and expected.sha256 == actual.sha256
