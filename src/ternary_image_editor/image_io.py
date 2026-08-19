"""原画像・三値PNGの厳格読込と原子的保存。"""

from __future__ import annotations

import hashlib
import io
import os
import struct
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .constants import (
    JPEG_QUANTIZATION_RULE,
    SAVE_RGB,
    TERNARY_JPEG_EXTENSIONS,
    protected_start_y,
)
from .errors import (
    AtomicSaveError,
    ExternalModificationError,
    ExternalOutputModificationError,
    ExternalSourceModificationError,
    ImageValidationError,
)
from .models import (
    FileBaseline,
    FileFingerprint,
    FileRole,
    LoadedLabels,
    LoadedOriginal,
    ProtectedNormalizationReport,
    TernaryImportReport,
)
from .save_lock import acquire_output_save_lock

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_IHDR_LENGTH = 13
_PNG_COLOR_GRAYSCALE = 0
_PNG_COLOR_RGB = 2
_PNG_COLOR_GRAYSCALE_ALPHA = 4
_PNG_COLOR_RGBA = 6
_INVALID_EXAMPLE_LIMIT = 8


@dataclass(frozen=True, slots=True)
class PngStructure:
    """変換前のPNG構造検査結果。"""

    width: int
    height: int
    bit_depth: int
    color_type: int
    has_trns: bool


def fingerprint_file(path: Path) -> FileFingerprint | None:
    """ファイル内容指紋を返す。存在しない場合は ``None``。"""

    path = Path(path)
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
    except FileNotFoundError:
        return None

    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise OSError(f"指紋計算中にファイルが変更された: {path}")
    return FileFingerprint(
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def inspect_png(path: Path) -> PngStructure:
    """PNGを復号・変換する前にsignature、IHDR、tRNSを検査する。"""

    data, _fingerprint = _read_snapshot(Path(path))
    return _inspect_png_bytes(data, Path(path))


def load_original_image(
    path: Path,
    *,
    expected_size: tuple[int, int] | None = None,
) -> LoadedOriginal:
    """参照専用の原画像を復号し、表示用sRGB配列を返す。"""

    path = Path(path)
    data, _fingerprint = _read_snapshot(path)
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            with ImageOps.exif_transpose(image) as displayed:
                if expected_size is not None and displayed.size != expected_size:
                    raise ImageValidationError(
                        path,
                        "寸法不一致",
                        (
                            f"期待={expected_size[0]}x{expected_size[1]}",
                            f"実際={displayed.width}x{displayed.height}",
                        ),
                    )
                converted = _convert_original_to_srgb(
                    displayed,
                    path,
                    strict_profile=False,
                )
                try:
                    rgb = np.asarray(converted, dtype=np.uint8).copy()
                finally:
                    if converted is not displayed:
                        converted.close()
    except ImageValidationError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ImageValidationError(path, "原画像の復号に失敗", (str(exc),)) from exc
    return LoadedOriginal(rgb=rgb, path=path, fingerprint=_fingerprint)


def load_ternary_image(
    path: Path,
    *,
    expected_size: tuple[int, int] | None = None,
) -> LoadedLabels:
    """厳格PNGまたは警告承認済みJPEGを0/1/2配列へ変換する。"""

    path = Path(path)
    if path.suffix.casefold() in TERNARY_JPEG_EXTENSIONS:
        return _load_label_jpeg(path, expected_size=expected_size)
    if path.suffix.casefold() != ".png":
        raise ImageValidationError(path, "三値画像の拡張子が対応外")
    return _load_label_png(
        path,
        expected_size=expected_size,
        require_rgb=False,
        normalize_protected=True,
    )


def inspect_ternary_jpeg(
    path: Path,
    *,
    expected_size: tuple[int, int] | None = None,
) -> tuple[tuple[int, int], FileFingerprint]:
    """三値化せずにJPEG入力を検査し、寸法と内容指紋を返す。"""

    rgb, fingerprint = _decode_label_jpeg_to_srgb(
        Path(path),
        expected_size=expected_size,
    )
    return (int(rgb.shape[1]), int(rgb.shape[0])), fingerprint


def load_output_image(
    path: Path,
    *,
    expected_size: tuple[int, int] | None = None,
) -> LoadedLabels:
    """既存出力を厳格検査後、編集用に下端保護領域を正規化する。"""

    return _load_label_png(
        Path(path),
        expected_size=expected_size,
        require_rgb=True,
        normalize_protected=True,
    )


def validate_output_png(
    path: Path,
    *,
    expected_size: tuple[int, int] | None = None,
) -> LoadedLabels:
    """保存成果物が8-bit RGB、アルファなし、許容三色のみか再読込検査する。"""

    return _load_label_png(
        Path(path),
        expected_size=expected_size,
        require_rgb=True,
        require_protected_none=True,
    )


def normalized_protected_labels_copy(labels: np.ndarray) -> tuple[np.ndarray, int]:
    """全値検査後のラベル配列を複製し、仕様上の保護行だけ0へ戻す。"""

    array = np.asarray(labels)
    if array.dtype != np.uint8 or array.ndim != 2 or not bool(np.all(array <= 2)):
        raise ValueError("ラベル配列は0/1/2のuint8二次元配列でなければならない")
    result = np.array(array, dtype=np.uint8, order="C", copy=True)
    protected = _protected_view(result)
    changed_pixels = int(np.count_nonzero(protected))
    protected[:] = 0
    return result, changed_pixels


def protected_region_is_none(labels: np.ndarray) -> bool:
    array = np.asarray(labels)
    if array.ndim != 2:
        return False
    return not bool(np.any(_protected_view(array)))


def save_labels_atomic(
    labels: np.ndarray,
    output_path: Path,
    *,
    expected_fingerprint: FileFingerprint | None,
    force: bool = False,
    source_baselines: Iterable[FileBaseline] = (),
    allow_stale_sources: bool = False,
    expected_size: tuple[int, int] | None = None,
) -> FileFingerprint:
    """内部ラベル配列を検証付き一時PNG経由で置換保存する。

    ``expected_fingerprint`` は読込時点の出力内容、``force`` は利用者が現在の
    出力を明示上書きすると決めたことを表す。置換前後にも内容を照合し、観測した
    外部変更は競合として止める。ただし ``os.replace`` 自体は内容条件付き置換では
    ないため、非協調の書き手が最後の照合と置換呼出しの間へ割り込む場合は別途の
    Windows実機受入対象とする。
    """

    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".png":
        raise AtomicSaveError(output_path, "出力拡張子は.pngでなければならない")
    source_baseline_tuple = tuple(source_baselines)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AtomicSaveError(output_path, str(exc)) from exc

    temp_path: Path | None = None
    try:
        with acquire_output_save_lock(output_path):
            commit_sources = _check_source_baselines(
                source_baseline_tuple,
                allow_stale=allow_stale_sources,
            )
            try:
                initial_fingerprint = fingerprint_file(output_path)
            except OSError as exc:
                raise AtomicSaveError(output_path, f"既存出力を検査できない: {exc}") from exc

            if not force and not _same_content(initial_fingerprint, expected_fingerprint):
                _raise_external_modification(output_path, expected_fingerprint, initial_fingerprint)
            commit_expected = initial_fingerprint

            array = _validate_labels_for_save(labels, output_path, expected_size)
            temp_path = _create_temp_path(output_path)
            rgb = np.asarray(SAVE_RGB, dtype=np.uint8)[array]
            _write_rgb_png(rgb, temp_path)
            reloaded = validate_output_png(temp_path, expected_size=expected_size)
            if not np.array_equal(reloaded.labels, array):
                raise AtomicSaveError(
                    output_path,
                    "一時PNGの再読込結果が内部ラベル配列と一致しない",
                )

            try:
                current_fingerprint = fingerprint_file(output_path)
            except OSError as exc:
                raise AtomicSaveError(
                    output_path,
                    f"置換直前の既存出力を検査できない: {exc}",
                ) from exc
            if not _same_content(current_fingerprint, commit_expected):
                _raise_external_modification(output_path, commit_expected, current_fingerprint)

            _recheck_source_baselines(commit_sources)
            _replace_file(temp_path, output_path, commit_expected)
            temp_path = None
            committed_fingerprint = fingerprint_file(output_path)
            if not _same_content(committed_fingerprint, reloaded.fingerprint):
                _raise_external_modification(
                    output_path,
                    reloaded.fingerprint,
                    committed_fingerprint,
                )
            assert committed_fingerprint is not None
            return committed_fingerprint
    except (AtomicSaveError, ExternalModificationError):
        raise
    except ImageValidationError as exc:
        raise AtomicSaveError(output_path, f"一時PNGの検証に失敗: {exc}") from exc
    except OSError as exc:
        raise AtomicSaveError(output_path, str(exc)) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _load_label_png(
    path: Path,
    *,
    expected_size: tuple[int, int] | None,
    require_rgb: bool,
    normalize_protected: bool = False,
    require_protected_none: bool = False,
) -> LoadedLabels:
    data, fingerprint = _read_snapshot(path)
    structure = _inspect_png_bytes(data, path)
    _validate_png_structure(structure, path, expected_size=expected_size, require_rgb=require_rgb)

    try:
        with Image.open(io.BytesIO(data)) as verifier:
            verifier.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            expected_mode = "RGB" if structure.color_type == _PNG_COLOR_RGB else "L"
            if image.format != "PNG" or image.mode != expected_mode:
                raise ImageValidationError(
                    path,
                    "PNGの色形式を認識できない",
                    (f"復号mode={image.mode}; IHDRと不一致",),
                )
            orientation = image.getexif().get(274)
            if orientation not in {None, 1}:
                raise ImageValidationError(
                    path,
                    "Orientation 2～8の三値PNGは使用できない",
                    (f"orientation={orientation}",),
                )
            pixels = np.asarray(image, dtype=np.uint8).copy()
    except ImageValidationError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ImageValidationError(path, "PNGの復号に失敗", (str(exc),)) from exc

    baseline_labels = _pixels_to_labels(pixels, path)
    normalization = ProtectedNormalizationReport()
    labels = baseline_labels
    if require_protected_none and not protected_region_is_none(labels):
        raise ImageValidationError(path, "出力PNGの下端保護領域が黒ではない")
    if normalize_protected:
        labels, changed_pixels = normalized_protected_labels_copy(labels)
        normalization = ProtectedNormalizationReport(changed_pixels=changed_pixels)
    return LoadedLabels(
        labels=labels,
        path=path,
        fingerprint=fingerprint,
        baseline_labels=baseline_labels,
        normalization=normalization,
        import_report=TernaryImportReport(
            source_format="PNG",
            label_counts=_label_counts(baseline_labels),
        ),
    )


def _load_label_jpeg(
    path: Path,
    *,
    expected_size: tuple[int, int] | None,
) -> LoadedLabels:
    """JPEGをsRGB画素へ復号し、決定的な最近傍規則で三値化する。

    呼出側が不可逆変換の警告と同意を担う。この関数自身は入力へ一切書き込まない。
    """

    rgb, fingerprint = _decode_label_jpeg_to_srgb(
        path,
        expected_size=expected_size,
    )

    baseline_labels = quantize_srgb_to_labels(rgb)
    labels, changed_pixels = normalized_protected_labels_copy(baseline_labels)
    return LoadedLabels(
        labels=labels,
        path=path,
        fingerprint=fingerprint,
        baseline_labels=baseline_labels,
        normalization=ProtectedNormalizationReport(changed_pixels=changed_pixels),
        import_report=TernaryImportReport(
            source_format="JPEG",
            quantized=True,
            quantization_rule=JPEG_QUANTIZATION_RULE,
            label_counts=_label_counts(baseline_labels),
        ),
        requires_save=True,
    )


def _decode_label_jpeg_to_srgb(
    path: Path,
    *,
    expected_size: tuple[int, int] | None,
) -> tuple[np.ndarray, FileFingerprint]:
    """三値JPEGを厳格に復号し、量子化前のsRGB画素を返す。"""

    data, fingerprint = _read_snapshot(path)
    try:
        with Image.open(io.BytesIO(data)) as verifier:
            if verifier.format != "JPEG":
                raise ImageValidationError(path, "拡張子はJPEGだが実形式がJPEGではない")
            verifier.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG":
                raise ImageValidationError(path, "JPEGとして復号できない")
            bits = int(getattr(image, "bits", 8))
            if bits != 8:
                raise ImageValidationError(
                    path,
                    "三値化するJPEGは8-bitでなければならない",
                    (f"bits={bits}",),
                )
            if image.mode not in {"L", "RGB"}:
                raise ImageValidationError(
                    path,
                    "三値化するJPEGは8-bit RGBまたは8-bitグレースケールでなければならない",
                    (f"mode={image.mode}",),
                )
            if "transparency" in image.info:
                raise ImageValidationError(path, "透明情報を含むJPEGは使用できない")
            orientation = image.getexif().get(274)
            if orientation not in {None, 1}:
                raise ImageValidationError(
                    path,
                    "Orientation 2～8の三値JPEGは使用できない",
                    (f"orientation={orientation}",),
                )
            image.load()
            if expected_size is not None and image.size != expected_size:
                raise ImageValidationError(
                    path,
                    "寸法不一致",
                    (
                        f"期待={expected_size[0]}x{expected_size[1]}",
                        f"実際={image.width}x{image.height}",
                    ),
                )
            converted = _convert_original_to_srgb(image, path)
            try:
                rgb = np.asarray(converted, dtype=np.uint8).copy()
            finally:
                if converted is not image:
                    converted.close()
    except ImageValidationError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ImageValidationError(path, "JPEGの復号に失敗", (str(exc),)) from exc
    return rgb, fingerprint


def quantize_srgb_to_labels(pixels: np.ndarray) -> np.ndarray:
    """sRGB uint8画素を黒・灰・白への二乗距離最小で0/1/2化する。

    三保存色は各成分が同値なので、二乗距離の比較をRGB成分和の等価な
    整数境界へ展開し、巨大な ``H×W×3×3`` 中間配列を作らない。成分和192の
    黒・灰tieは黒を採り、灰・白の境界は574と575の間にある。乱数、dither、
    周辺画素参照はいずれも行わない。
    """

    array = np.asarray(pixels)
    if array.dtype != np.uint8:
        raise TypeError("三値化元はuint8でなければならない")
    if array.ndim == 2:
        channel_sum = array.astype(np.uint16) * 3
    elif array.ndim == 3 and array.shape[2] == 3:
        channel_sum = np.sum(array, axis=2, dtype=np.uint16)
    else:
        raise ValueError("三値化元はH×WまたはH×W×3でなければならない")
    if 0 in channel_sum.shape:
        raise ValueError("三値化元の寸法は正でなければならない")

    labels = np.zeros(channel_sum.shape, dtype=np.uint8)
    labels[channel_sum > 192] = 1
    labels[channel_sum > 574] = 2
    return labels


def _label_counts(labels: np.ndarray) -> tuple[int, int, int]:
    counts = np.bincount(np.asarray(labels, dtype=np.uint8).ravel(), minlength=3)
    return int(counts[0]), int(counts[1]), int(counts[2])


def _validate_png_structure(
    structure: PngStructure,
    path: Path,
    *,
    expected_size: tuple[int, int] | None,
    require_rgb: bool,
) -> None:
    actual_size = (structure.width, structure.height)
    if expected_size is not None and actual_size != expected_size:
        raise ImageValidationError(
            path,
            "寸法不一致",
            (
                f"期待={expected_size[0]}x{expected_size[1]}",
                f"実際={actual_size[0]}x{actual_size[1]}",
            ),
        )
    if structure.bit_depth != 8:
        raise ImageValidationError(
            path,
            "8-bit PNGではない",
            (f"bit_depth={structure.bit_depth}",),
        )
    if structure.color_type in {_PNG_COLOR_GRAYSCALE_ALPHA, _PNG_COLOR_RGBA}:
        raise ImageValidationError(path, "アルファチャンネルを含むPNGは使用できない")
    if structure.color_type == 3:
        raise ImageValidationError(path, "索引色PNGは使用できない")
    if structure.color_type not in {_PNG_COLOR_GRAYSCALE, _PNG_COLOR_RGB}:
        raise ImageValidationError(
            path,
            "許可されていないPNG色形式",
            (f"color_type={structure.color_type}",),
        )
    if structure.has_trns:
        raise ImageValidationError(path, "tRNS透明情報を含むPNGは使用できない")
    if require_rgb and structure.color_type != _PNG_COLOR_RGB:
        raise ImageValidationError(path, "出力PNGはRGBでなければならない")


def _pixels_to_labels(pixels: np.ndarray, path: Path) -> np.ndarray:
    lookup = np.full(256, 255, dtype=np.uint8)
    lookup[0] = 0
    lookup[128] = 1
    lookup[255] = 2

    if pixels.ndim == 2:
        valid = (pixels == 0) | (pixels == 128) | (pixels == 255)
        if not bool(np.all(valid)):
            invalid = pixels[~valid]
            values, counts = np.unique(invalid, return_counts=True)
            examples = [
                f"{int(value)}×{int(count)}"
                for value, count in zip(
                    values[:_INVALID_EXAMPLE_LIMIT],
                    counts[:_INVALID_EXAMPLE_LIMIT],
                    strict=True,
                )
            ]
            _raise_invalid_colors(path, int(invalid.size), examples)
        return lookup[pixels]

    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ImageValidationError(path, "RGBまたはグレースケール画像ではない")

    allowed = np.asarray(SAVE_RGB, dtype=np.uint8)
    valid = np.any(np.all(pixels[:, :, None, :] == allowed[None, None, :, :], axis=3), axis=2)
    if not bool(np.all(valid)):
        invalid = pixels[~valid]
        values, counts = np.unique(invalid, axis=0, return_counts=True)
        examples = [
            f"({int(value[0])},{int(value[1])},{int(value[2])})×{int(count)}"
            for value, count in zip(
                values[:_INVALID_EXAMPLE_LIMIT],
                counts[:_INVALID_EXAMPLE_LIMIT],
                strict=True,
            )
        ]
        _raise_invalid_colors(path, int(invalid.shape[0]), examples)
    return lookup[pixels[:, :, 0]]


def _raise_invalid_colors(path: Path, count: int, examples: list[str]) -> None:
    raise ImageValidationError(
        path,
        "三値以外の色を含む",
        (f"異常画素数={count}", f"代表値={', '.join(examples)}"),
    )


def _validate_labels_for_save(
    labels: np.ndarray,
    output_path: Path,
    expected_size: tuple[int, int] | None,
) -> np.ndarray:
    if not isinstance(labels, np.ndarray) or labels.dtype != np.uint8 or labels.ndim != 2:
        raise AtomicSaveError(output_path, "内部ラベルはuint8二次元配列でなければならない")
    if 0 in labels.shape:
        raise AtomicSaveError(output_path, "内部ラベル寸法は正でなければならない")
    expected_shape = (
        None if expected_size is None else (expected_size[1], expected_size[0])
    )
    if expected_shape is not None and labels.shape != expected_shape:
        raise AtomicSaveError(
            output_path,
            f"内部ラベル寸法が不正: 期待={expected_shape}, 実際={labels.shape}",
        )
    if not bool(np.all(labels <= 2)):
        raise AtomicSaveError(output_path, "内部ラベルに0/1/2以外を含む")
    array = np.array(labels, dtype=np.uint8, order="C", copy=True)
    _force_protected_none(array)
    return array


def _convert_original_to_srgb(
    image: Image.Image,
    path: Path,
    *,
    strict_profile: bool = True,
) -> Image.Image:
    """埋込みICCがあればsRGB化し、必要なら通常RGB変換へ退避する。"""

    icc_profile = image.info.get("icc_profile")
    if icc_profile is None:
        return image.convert("RGB")
    if not isinstance(icc_profile, bytes) or not icc_profile:
        if strict_profile:
            raise ImageValidationError(path, "ICC色特性を解釈できない")
        return image.convert("RGB")
    try:
        source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))
        target_profile = ImageCms.createProfile("sRGB")
        return ImageCms.profileToProfile(
            image,
            source_profile,
            target_profile,
            outputMode="RGB",
        )
    except (ImageCms.PyCMSError, OSError, TypeError, ValueError) as exc:
        if strict_profile:
            raise ImageValidationError(
                path,
                "ICC色特性からsRGBへ変換できない",
                (str(exc),),
            ) from exc
        return image.convert("RGB")


def _protected_view(labels: np.ndarray) -> np.ndarray:
    """実画像高さから求めた下端保護領域を返す。"""

    return labels[protected_start_y(int(labels.shape[0])) :, :]


def _force_protected_none(labels: np.ndarray) -> int:
    protected = _protected_view(labels)
    changed_pixels = int(np.count_nonzero(protected))
    protected[:] = 0
    return changed_pixels


def _check_source_baselines(
    baselines: tuple[FileBaseline, ...],
    *,
    allow_stale: bool,
) -> tuple[FileBaseline, ...]:
    """lock取得後に原画像と入力三値画像を再hashする。"""

    current: list[FileBaseline] = []
    for baseline in baselines:
        if baseline.role not in {FileRole.ORIGINAL, FileRole.INPUT_TERNARY}:
            raise ValueError(f"保存元として扱えない役割: {baseline.role}")
        actual = _fingerprint_source(baseline)
        if not allow_stale and not _same_content(actual, baseline.fingerprint):
            _raise_source_modification(baseline, actual)
        current.append(
            FileBaseline(
                role=baseline.role,
                path=baseline.path,
                fingerprint=actual,
            )
        )
    return tuple(current)


def _recheck_source_baselines(baselines: tuple[FileBaseline, ...]) -> None:
    """一時PNG検証後にも同じ内容であることを置換前に確かめる。"""

    for baseline in baselines:
        actual = _fingerprint_source(baseline)
        if not _same_content(actual, baseline.fingerprint):
            _raise_source_modification(baseline, actual)


def _fingerprint_source(baseline: FileBaseline) -> FileFingerprint | None:
    try:
        return fingerprint_file(baseline.path)
    except OSError as exc:
        raise ExternalSourceModificationError(
            source_kind=baseline.role.value,
            path=baseline.path,
            expected_sha256=(None if baseline.fingerprint is None else baseline.fingerprint.sha256),
            actual_sha256=None,
        ) from exc


def _raise_source_modification(
    baseline: FileBaseline,
    actual: FileFingerprint | None,
) -> None:
    raise ExternalSourceModificationError(
        source_kind=baseline.role.value,
        path=baseline.path,
        expected_sha256=(None if baseline.fingerprint is None else baseline.fingerprint.sha256),
        actual_sha256=None if actual is None else actual.sha256,
    )


def _write_rgb_png(rgb: np.ndarray, path: Path) -> None:
    image = Image.fromarray(rgb)
    try:
        if image.mode != "RGB":
            raise OSError(f"RGB画像を生成できなかった: mode={image.mode}")
        image.save(path, format="PNG")
    finally:
        image.close()
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _create_temp_path(output_path: Path) -> Path:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".tie-{output_path.stem[:24]}-",
        suffix=".tmp",
        dir=output_path.parent,
    )
    temp_path = Path(temp_name)
    try:
        os.close(descriptor)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _replace_file(
    source: Path,
    target: Path,
    expected_target: FileFingerprint | None,
) -> None:
    """置換呼出しの直前に対象を再照合してから原子的置換する。"""

    current_target = fingerprint_file(target)
    if not _same_content(current_target, expected_target):
        _raise_external_modification(target, expected_target, current_target)
    os.replace(source, target)


def _read_snapshot(path: Path) -> tuple[bytes, FileFingerprint]:
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            data = stream.read()
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ImageValidationError(path, "ファイルを読み込めない", (str(exc),)) from exc

    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(
        data
    ) != after.st_size:
        raise ImageValidationError(path, "読込中にファイルが変更された")
    fingerprint = FileFingerprint(
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    return data, fingerprint


def _inspect_png_bytes(data: bytes, path: Path) -> PngStructure:
    if not data.startswith(_PNG_SIGNATURE):
        raise ImageValidationError(path, "PNG形式として認識できない", ("signature不一致",))

    offset = len(_PNG_SIGNATURE)
    first_chunk = True
    ihdr: tuple[int, int, int, int] | None = None
    has_trns = False
    saw_iend = False

    while offset < len(data):
        if offset + 12 > len(data):
            raise ImageValidationError(
                path,
                "PNG構造が壊れている",
                ("chunkが途中で切れている",),
            )
        length = struct.unpack_from(">I", data, offset)[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data_start = offset + 8
        chunk_end = chunk_data_start + length
        next_offset = chunk_end + 4
        if next_offset > len(data):
            raise ImageValidationError(
                path,
                "PNG構造が壊れている",
                ("chunk長がファイル範囲を超えている",),
            )

        if first_chunk:
            if chunk_type != b"IHDR" or length != _PNG_IHDR_LENGTH:
                raise ImageValidationError(
                    path,
                    "PNG構造が壊れている",
                    ("先頭chunkが正しいIHDRではない",),
                )
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data[chunk_data_start:chunk_end]
            )
            if (
                width <= 0
                or height <= 0
                or compression != 0
                or filtering != 0
                or interlace
                not in {
                    0,
                    1,
                }
            ):
                raise ImageValidationError(path, "PNG構造が壊れている", ("IHDR値が不正",))
            ihdr = width, height, bit_depth, color_type
            first_chunk = False
        elif chunk_type == b"tRNS":
            has_trns = True

        offset = next_offset
        if chunk_type == b"IEND":
            saw_iend = True
            break

    if ihdr is None or not saw_iend:
        raise ImageValidationError(
            path,
            "PNG構造が壊れている",
            ("IHDRまたはIENDがない",),
        )
    return PngStructure(*ihdr, has_trns=has_trns)


def _same_content(
    left: FileFingerprint | None,
    right: FileFingerprint | None,
) -> bool:
    if left is None or right is None:
        return left is right
    return left.size == right.size and left.sha256 == right.sha256


def _raise_external_modification(
    path: Path,
    expected: FileFingerprint | None,
    actual: FileFingerprint | None,
) -> None:
    raise ExternalOutputModificationError(
        path=path,
        expected_sha256=None if expected is None else expected.sha256,
        actual_sha256=None if actual is None else actual.sha256,
    )
