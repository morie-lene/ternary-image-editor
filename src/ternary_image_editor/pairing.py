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
from .models import ExcludedItem, ImagePair, PairingMode, PairingResult, PairKey

ImageKind = Literal["original", "ternary"]

_DIGIT_RUN = re.compile(r"(\d+)")


def natural_sort_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """数字列を数値として扱う、大文字小文字非依存の整列キーを返す。"""

    # NFKC is used for ordering only.  Strict identity extraction below remains
    # NFC-based, so compatibility characters never become pair identities.
    normalized = unicodedata.normalize("NFKC", value)
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
    *,
    mode: PairingMode | str = PairingMode.STRICT_KEY,
) -> PairingResult:
    """対応計画を作り、出力先の書込検査まで完了して返す。

    GUIの自然順確認では、確認前に出力先へ作用を残さないため
    :func:`plan_pairing` と :func:`finalize_pairing` を二相で用いる。
    """

    result = plan_pairing(original_dir, ternary_dir, output_dir, mode=mode)
    return finalize_pairing(result, output_dir)


def plan_pairing(
    original_dir: Path,
    ternary_dir: Path,
    output_dir: Path,
    *,
    mode: PairingMode | str = PairingMode.STRICT_KEY,
) -> PairingResult:
    """入力を非再帰走査し、出力先へ書き込まずに対応計画を返す。"""

    original_dir = Path(original_dir)
    ternary_dir = Path(ternary_dir)
    output_dir = Path(output_dir)
    pairing_mode = PairingMode(mode)

    for input_dir in (original_dir, ternary_dir):
        if _same_physical_folder(output_dir, input_dir):
            raise FolderAccessError(output_dir, "出力フォルダが入力フォルダと同一")

    original_paths, original_excluded = _scan_supported_paths(original_dir, "original")
    ternary_paths, ternary_excluded = _scan_supported_paths(ternary_dir, "ternary")

    result = PairingResult(
        excluded=[*original_excluded, *ternary_excluded],
        pairing_mode=pairing_mode,
        original_candidate_count=len(original_paths),
        ternary_candidate_count=len(ternary_paths),
    )

    if not original_paths or not ternary_paths:
        result.blocking_reason = (
            "読込候補数が不足: "
            f"原画像={len(original_paths)}件、三値画像={len(ternary_paths)}件。"
            "それぞれ1件以上の対応形式画像が必要"
        )
        result.excluded.append(
            ExcludedItem(
                reason_code="empty_candidate_group",
                message=(
                    f"読込候補数が不足: 原画像={len(original_paths)}件、"
                    f"三値画像={len(ternary_paths)}件"
                ),
                paths=tuple(_sorted_paths([*original_paths, *ternary_paths])),
            )
        )
        return result

    if len(original_paths) != len(ternary_paths):
        result.blocking_reason = (
            f"画像群の件数不一致: 原画像={len(original_paths)}件、"
            f"三値画像={len(ternary_paths)}件"
        )
        result.excluded.append(
            ExcludedItem(
                reason_code="candidate_count_mismatch",
                message=result.blocking_reason,
                paths=tuple(_sorted_paths([*original_paths, *ternary_paths])),
            )
        )
        return result

    if pairing_mode is PairingMode.NATURAL_ORDER:
        originals_sorted = sorted(original_paths, key=_natural_path_sort_key)
        ternaries_sorted = sorted(ternary_paths, key=_natural_path_sort_key)
        tentative_pairs = [
            ImagePair(
                key=None,
                original_path=original_path,
                ternary_path=ternary_path,
                output_path=output_dir / f"{ternary_path.stem}.png",
                ternary_stem=ternary_path.stem,
                pairing_mode=pairing_mode,
            )
            for original_path, ternary_path in zip(
                originals_sorted,
                ternaries_sorted,
                strict=True,
            )
        ]
        _install_collision_checked_pairs(result, tentative_pairs, block_all=True)
        return result

    originals, original_key_excluded = _index_strict_candidates(original_paths, "original")
    ternaries, ternary_key_excluded = _index_strict_candidates(ternary_paths, "ternary")
    result.excluded.extend(original_key_excluded)
    result.excluded.extend(ternary_key_excluded)
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
                pairing_mode=pairing_mode,
            )
        )

    _install_collision_checked_pairs(result, tentative_pairs, block_all=False)
    result.pairs.sort(
        key=lambda pair: (
            natural_sort_key(pair.ternary_stem),
            pair.ternary_stem,
            str(pair.ternary_path.resolve(strict=False)),
        )
    )
    return result


def finalize_pairing(result: PairingResult, output_dir: Path) -> PairingResult:
    """確認済み計画へ出力先の作成・試験書込結果を付加する。"""

    if result.output_checked or result.blocking_reason is not None:
        return result
    output_writable, output_warning = check_output_writable(Path(output_dir))
    result.output_writable = output_writable
    result.output_warning = output_warning
    result.output_checked = True
    return result


def _install_collision_checked_pairs(
    result: PairingResult,
    tentative_pairs: list[ImagePair],
    *,
    block_all: bool,
) -> None:
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

    if block_all and collided_output_keys:
        result.blocking_reason = "自然順の全対応を保存できない出力名衝突がある"
        result.pairs = []
        return
    result.pairs = [
        pair
        for pair in tentative_pairs
        if _windows_path_key(pair.output_path) not in collided_output_keys
    ]


def _scan_supported_paths(
    directory: Path,
    kind: ImageKind,
) -> tuple[list[Path], list[ExcludedItem]]:
    extensions = ORIGINAL_EXTENSIONS if kind == "original" else TERNARY_EXTENSIONS
    candidates: list[Path] = []
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
        candidates.append(path)
    return candidates, excluded


def _index_strict_candidates(
    paths: Iterable[Path],
    kind: ImageKind,
) -> tuple[dict[PairKey, list[Path]], list[ExcludedItem]]:
    candidates: dict[PairKey, list[Path]] = defaultdict(list)
    excluded: list[ExcludedItem] = []
    for path in paths:
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


def _scan_candidates(
    directory: Path,
    kind: ImageKind,
) -> tuple[dict[PairKey, list[Path]], list[ExcludedItem]]:
    """旧来の厳格走査単位を保つ内部互換ラッパー。"""

    paths, excluded = _scan_supported_paths(directory, kind)
    candidates, key_excluded = _index_strict_candidates(paths, kind)
    return candidates, [*excluded, *key_excluded]


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


def _natural_path_sort_key(
    path: Path,
) -> tuple[tuple[tuple[int, int | str], ...], str, str]:
    rendered = str(path.resolve(strict=False))
    normalized_name = unicodedata.normalize("NFKC", path.name)
    return natural_sort_key(normalized_name), normalized_name.casefold(), rendered


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
