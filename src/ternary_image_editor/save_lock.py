"""対象出力単位の跨平台・非待機協調ロック。"""

from __future__ import annotations

import hashlib
import os
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from .errors import OutputSaveLockError


def output_lock_path(output_path: Path) -> Path:
    """同じ出力名へ安定したsidecar inodeを割り当てる。"""

    output_path = Path(output_path)
    parent = output_path.parent.resolve(strict=False)
    normalized_name = unicodedata.normalize("NFC", output_path.name).casefold()
    digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()[:32]
    return parent / f".tie-save-{digest}.lock"


@contextmanager
def acquire_output_save_lock(output_path: Path) -> Iterator[Path]:
    """保存中だけ一バイトの排他lockを保持し、競合時は直ちに失敗する。

    sidecarは削除しない。unlock後も同じinodeを再利用し、unlink/recreate間の
    排他抜けを避ける。
    """

    output_path = Path(output_path)
    lock_path = output_lock_path(output_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        stream = lock_path.open("a+b")
    except OSError as exc:
        raise OutputSaveLockError(output_path, lock_path, str(exc)) from exc

    acquired = False
    try:
        _ensure_lock_byte(stream)
        try:
            _lock_nonblocking(stream)
        except OSError as exc:
            raise OutputSaveLockError(output_path, lock_path, "別プロセスが保存中") from exc
        acquired = True
        yield lock_path
    finally:
        if acquired:
            try:
                _unlock(stream)
            except OSError:
                pass
        stream.close()


def _ensure_lock_byte(stream: BinaryIO) -> None:
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"\0")
        stream.flush()
        os.fsync(stream.fileno())
    stream.seek(0)


if os.name == "nt":
    import msvcrt

    def _lock_nonblocking(stream: BinaryIO) -> None:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(stream: BinaryIO) -> None:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_nonblocking(stream: BinaryIO) -> None:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(stream: BinaryIO) -> None:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
