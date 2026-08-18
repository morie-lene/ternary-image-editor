"""入力画像の非再帰走査、対応付け、出力先決定。"""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from .constants import (
    ORIGINAL_EXTENSIONS,
    ORIGINAL_PREFIX_GROUP,
    PAIR_SUFFIX_LENGTH,
    TERNARY_EXTENSIONS,
    TERNARY_PREFIX_GROUP,
)
from .errors import FolderAccessError
from .models import ExcludedItem, ImagePair, PairingResult, PairKey

ImageKind = Literal["original", "ternary"]

_DIGIT_RUN = re.compile(r"(\d+)")


def natural_sort_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """数字列を数値として扱う、大文字小文字非依存の整列キーを返す。"""

    normalized = unicodedata.normalize("NFC", value)
    return tuple(
        (1, int(part)) if part.isdecimal() else (0, part.casefold())
        for part in _DIGIT_RUN.split(normalized)
        if part
    )


def extract_pair_key(path: Path, kind: ImageKind) -> PairKey:
    """一つの対応候補から仕様上の対応キーを抽出する。

    このキーはファイルの身元ではない。同じキーが複数回現れた場合、呼出側は
    自動選択せず、そのキーに属する候補をすべて対象外にする必要がある。
    """

    stem = unicodedata.normalize("NFC", path.stem)
    if len(stem) < PAIR_SUFFIX_LENGTH:
        raise ValueError("stem_too_short")

    prefix_groups = ORIGINAL_PREFIX_GROUP if kind == "original" else TERNARY_PREFIX_GROUP
    group = next(
        (group for prefix, group in prefix_groups.items() if stem.startswith(prefix)),
        None,
    )
    if group is None:
        raise ValueError("unexpected_prefix")

    return PairKey(group=group, suffix=stem[-PAIR_SUFFIX_LENGTH:])


def check_output_writable(output_dir: Path) -> tuple[bool, str | None]:
    """出力フォルダを作成し、同じフォルダ内で一時書込みできるか検査する。"""

    probe_path: Path | None = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_dir.is_dir():
            return False, "出力先がフォルダではない"
        descriptor, probe_name = tempfile.mkstemp(prefix=".tie-write-probe-", dir=output_dir)
        probe_path = Path(probe_name)
        os.close(descriptor)
        probe_path.unlink()
        probe_path = None
    except OSError as exc:
        return False, str(exc)
    finally:
        if probe_path is not None:
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                pass
    return True, None


def pair_directories(
    original_dir: Path,
    ternary_dir: Path,
    output_dir: Path,
) -> PairingResult:
    """三フォルダを検査し、仕様に適合する一対一の画像対だけを返す。"""

    original_dir = Path(original_dir)
    ternary_dir = Path(ternary_dir)
    output_dir = Path(output_dir)

    for input_dir in (original_dir, ternary_dir):
        if _same_physical_folder(output_dir, input_dir):
            raise FolderAccessError(output_dir, "出力フォルダが入力フォルダと同一")

    originals, original_excluded = _scan_candidates(original_dir, "original")
    ternaries, ternary_excluded = _scan_candidates(ternary_dir, "ternary")
    output_writable, output_warning = check_output_writable(output_dir)

    result = PairingResult(
        excluded=[*original_excluded, *ternary_excluded],
        output_writable=output_writable,
        output_warning=output_warning,
    )
    tentative_pairs: list[ImagePair] = []

    keys = sorted(
        set(originals) | set(ternaries),
        key=lambda key: (key.group, key.suffix.casefold(), key.suffix),
    )
    for key in keys:
        original_paths = originals.get(key, [])
        ternary_paths = ternaries.get(key, [])
        paths = tuple(_sorted_paths([*original_paths, *ternary_paths]))

        if len(original_paths) > 1 or len(ternary_paths) > 1:
            result.excluded.append(
                ExcludedItem(
                    reason_code="duplicate_pair_key",
                    message="同一対応キーが重複しているため自動選択しない",
                    paths=paths,
                    key=key,
                )
            )
            continue
        if not original_paths or not ternary_paths:
            result.excluded.append(
                ExcludedItem(
                    reason_code="missing_counterpart",
                    message="対応相手がない",
                    paths=paths,
                    key=key,
                )
            )
            continue

        ternary_path = ternary_paths[0]
        tentative_pairs.append(
            ImagePair(
                key=key,
                original_path=original_paths[0],
                ternary_path=ternary_path,
                output_path=output_dir / f"{ternary_path.stem}.png",
                ternary_stem=ternary_path.stem,
            )
        )

    collisions: dict[str, list[ImagePair]] = defaultdict(list)
    for pair in tentative_pairs:
        collisions[_windows_path_key(pair.output_path)].append(pair)

    collided_output_keys = {
        output_key for output_key, collision_group in collisions.items() if len(collision_group) > 1
    }
    for collision_group in collisions.values():
        if len(collision_group) < 2:
            continue
        result.excluded.append(
            ExcludedItem(
                reason_code="output_name_collision",
                message="Windows上で出力名が衝突するため対象外",
                paths=tuple(
                    _sorted_paths(
                        path
                        for pair in collision_group
                        for path in (pair.original_path, pair.ternary_path)
                    )
                ),
            )
        )

    result.pairs = [
        pair
        for pair in tentative_pairs
        if _windows_path_key(pair.output_path) not in collided_output_keys
    ]
    result.pairs.sort(
        key=lambda pair: (
            natural_sort_key(pair.ternary_stem),
            pair.ternary_stem,
            str(pair.ternary_path.resolve(strict=False)),
        )
    )
    return result


def _scan_candidates(
    directory: Path,
    kind: ImageKind,
) -> tuple[dict[PairKey, list[Path]], list[ExcludedItem]]:
    extensions = ORIGINAL_EXTENSIONS if kind == "original" else TERNARY_EXTENSIONS
    candidates: dict[PairKey, list[Path]] = defaultdict(list)
    excluded: list[ExcludedItem] = []

    for path in _direct_files(directory):
        if path.suffix.casefold() not in extensions:
            excluded.append(
                ExcludedItem(
                    reason_code="unsupported_extension",
                    message="対応していない画像形式",
                    paths=(path,),
                )
            )
            continue
        try:
            key = extract_pair_key(path, kind)
        except ValueError as exc:
            reason_code = str(exc)
            message = {
                "stem_too_short": f"幹名が{PAIR_SUFFIX_LENGTH}文字未満",
                "unexpected_prefix": "想定外の先頭文字列",
            }[reason_code]
            excluded.append(ExcludedItem(reason_code=reason_code, message=message, paths=(path,)))
            continue
        candidates[key].append(path)

    for paths in candidates.values():
        paths.sort(key=_path_sort_key)
    return candidates, excluded


def _direct_files(directory: Path) -> list[Path]:
    try:
        if not directory.is_dir():
            raise FolderAccessError(directory, "存在しないかフォルダではない")
        return _sorted_paths(path for path in directory.iterdir() if path.is_file())
    except FolderAccessError:
        raise
    except OSError as exc:
        raise FolderAccessError(directory, str(exc)) from exc


def _sorted_paths(paths: Iterable[Path]) -> list[Path]:
    return sorted(paths, key=_path_sort_key)


def _path_sort_key(path: Path) -> tuple[str, str]:
    rendered = str(path.resolve(strict=False))
    normalized = unicodedata.normalize("NFC", rendered)
    return normalized.casefold(), rendered


def _windows_path_key(path: Path) -> str:
    """現ホストによらずWindowsの大文字小文字非依存衝突を近似する。"""

    rendered = str(path.resolve(strict=False)).replace("\\", "/")
    return unicodedata.normalize("NFC", rendered).casefold()


def _same_physical_folder(left: Path, right: Path) -> bool:
    if _windows_path_key(left) == _windows_path_key(right):
        return True
    left_identity = _folder_file_identity(left)
    right_identity = _folder_file_identity(right)
    return (
        left_identity is not None and right_identity is not None and left_identity == right_identity
    )


def _folder_file_identity(path: Path) -> tuple[int, int] | None:
    """存在するフォルダではsymlink追跡後のdevice/inodeを実体識別に使う。"""

    try:
        status = path.stat()
    except OSError:
        return None
    if not path.is_dir():
        return None
    return status.st_dev, status.st_ino
