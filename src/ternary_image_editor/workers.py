"""長処理をGUIスレッド外へ出すための限定実行器。"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


@dataclass(frozen=True, slots=True)
class TaskToken:
    """非同期結果を現在の編集状態へ照合する鍵。"""

    session_id: str
    revision: int
    activity: str


@dataclass(frozen=True, slots=True)
class TaskSuccess:
    token: TaskToken
    value: Any


@dataclass(frozen=True, slots=True)
class TaskFailure:
    token: TaskToken
    exception: Exception
    traceback_text: str


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(object)
    finished = Signal(object)


class FunctionWorker(QRunnable):
    """一つの純粋または限定I/O関数をQThreadPoolで実行する。"""

    def __init__(
        self,
        token: TaskToken,
        function: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.token = token
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            value = self.function(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - GUI境界で領域例外を通知する
            failure = TaskFailure(
                token=self.token,
                exception=exc,
                traceback_text="".join(traceback.format_exception(exc)),
            )
            self.signals.failed.emit(failure)
        else:
            self.signals.succeeded.emit(TaskSuccess(token=self.token, value=value))
        finally:
            self.signals.finished.emit(self.token)
