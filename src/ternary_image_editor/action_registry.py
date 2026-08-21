"""Application-operation registry and keyboard/pointer routing primitives.

This module deliberately knows nothing about ``MainWindow`` or image state.  It
defines the durable operation identities, validates the two binding slots, and
offers a small runtime registry which an integration layer can bind to callbacks.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence


class OperationType(StrEnum):
    """Execution semantics fixed by specification 15.6/15.7."""

    SINGLE = "single"
    STEP = "step"
    HOLD = "hold"


class ShortcutSlot(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Immutable public identity and defaults for one main-window command."""

    operation_id: str
    category: str
    name: str
    operation_type: OperationType
    effect: str | None = None
    primary: str | None = None
    secondary: str | None = None

    def __post_init__(self) -> None:
        if not self.operation_id or "/" in self.operation_id:
            raise ValueError("operation_id must be a non-empty dotted identifier")
        primary = canonical_shortcut(self.primary)
        secondary = canonical_shortcut(self.secondary)
        if primary is not None and primary == secondary:
            raise ValueError(f"duplicate default shortcut for {self.operation_id}")
        object.__setattr__(self, "primary", primary)
        object.__setattr__(self, "secondary", secondary)
        if self.operation_type is OperationType.STEP and not self.effect:
            raise ValueError(f"step operation {self.operation_id} requires an effect")


@dataclass(frozen=True, slots=True)
class ShortcutBindings:
    """At most two distinct keyboard or canvas-pointer bindings."""

    primary: str | None = None
    secondary: str | None = None

    def __post_init__(self) -> None:
        primary = canonical_binding(self.primary)
        secondary = canonical_binding(self.secondary)
        if primary is not None and primary == secondary:
            raise ValueError("primary and secondary shortcuts must differ")
        object.__setattr__(self, "primary", primary)
        object.__setattr__(self, "secondary", secondary)

    def value(self, slot: ShortcutSlot | str) -> str | None:
        return self.primary if ShortcutSlot(slot) is ShortcutSlot.PRIMARY else self.secondary

    def replaced(
        self, slot: ShortcutSlot | str, value: str | QKeySequence | None
    ) -> ShortcutBindings:
        normalized_slot = ShortcutSlot(slot)
        if normalized_slot is ShortcutSlot.PRIMARY:
            return ShortcutBindings(value, self.secondary)
        return ShortcutBindings(self.primary, value)

    def sequences(self) -> tuple[str, ...]:
        return tuple(value for value in (self.primary, self.secondary) if value is not None)


@dataclass(frozen=True, slots=True)
class AssignmentTarget:
    operation_id: str
    slot: ShortcutSlot


@dataclass(frozen=True, slots=True)
class ShortcutConflict:
    sequence: str
    owner: AssignmentTarget
    requested: AssignmentTarget


class AssignmentStatus(StrEnum):
    APPLIED = "applied"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"
    DUPLICATE_SELF = "duplicate_self"


@dataclass(frozen=True, slots=True)
class AssignmentChange:
    status: AssignmentStatus
    conflict: ShortcutConflict | None = None

    @property
    def applied(self) -> bool:
        return self.status is AssignmentStatus.APPLIED


def canonical_shortcut(value: str | QKeySequence | None) -> str | None:
    """Return one canonical PortableText chord, preserving ``None`` as unassigned."""

    if value is None:
        return None
    if isinstance(value, QKeySequence):
        sequence = QKeySequence(value)
    elif isinstance(value, str):
        if not value.strip():
            return None
        portable_source = {
            # The normative table spells these names out; Qt PortableText uses
            # its historical abbreviated tokens.
            "PageUp": "PgUp",
            "PageDown": "PgDown",
        }.get(value.strip(), value.strip())
        sequence = QKeySequence.fromString(
            portable_source, QKeySequence.SequenceFormat.PortableText
        )
    else:
        raise TypeError("shortcut must be PortableText, QKeySequence, or None")
    if sequence.isEmpty() or sequence.count() != 1:
        raise ValueError("shortcut must contain exactly one key combination")
    portable = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if not portable:
        raise ValueError("shortcut cannot be represented as PortableText")
    round_trip = QKeySequence.fromString(portable, QKeySequence.SequenceFormat.PortableText)
    if round_trip.isEmpty() or round_trip.count() != 1:
        raise ValueError("shortcut PortableText does not round-trip")
    return portable


_POINTER_BASES = frozenset(
    {
        "WheelUp",
        "WheelDown",
        "MouseLeft",
        "MouseMiddle",
        "MouseRight",
        "MouseBack",
        "MouseForward",
    }
)
_POINTER_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift")
_POINTER_MODIFIERS = frozenset(_POINTER_MODIFIER_ORDER)


def _canonical_pointer_text(value: str) -> str | None:
    parts = tuple(part.strip() for part in value.split("+"))
    if not parts or parts[-1] not in _POINTER_BASES:
        if any(part in _POINTER_BASES for part in parts):
            raise ValueError("pointer base must be the final binding token")
        return None
    if any(not part for part in parts):
        raise ValueError("pointer binding contains an empty token")
    modifiers = parts[:-1]
    if len(modifiers) != len(set(modifiers)):
        raise ValueError("pointer binding contains a duplicate modifier")
    unsupported = tuple(modifier for modifier in modifiers if modifier not in _POINTER_MODIFIERS)
    if unsupported:
        raise ValueError("pointer bindings support only Ctrl, Alt, and Shift modifiers")
    ordered = tuple(modifier for modifier in _POINTER_MODIFIER_ORDER if modifier in modifiers)
    return "+".join((*ordered, parts[-1]))


def canonical_binding(value: str | QKeySequence | None) -> str | None:
    """Return one canonical keyboard chord or canvas-pointer token."""

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        pointer = _canonical_pointer_text(text)
        if pointer is not None:
            return pointer
    return canonical_shortcut(value)


def pointer_base(value: str | QKeySequence | None) -> str | None:
    """Return the formal pointer base token, or ``None`` for a keyboard binding."""

    normalized = canonical_binding(value)
    if normalized is None:
        return None
    base = normalized.rsplit("+", 1)[-1]
    return base if base in _POINTER_BASES else None


def binding_is_pointer(value: str | QKeySequence | None) -> bool:
    return pointer_base(value) is not None


def binding_is_wheel(value: str | QKeySequence | None) -> bool:
    return pointer_base(value) in {"WheelUp", "WheelDown"}


def native_shortcut(value: str | QKeySequence | None) -> str:
    normalized = canonical_shortcut(value)
    if normalized is None:
        return ""
    return QKeySequence.fromString(normalized, QKeySequence.SequenceFormat.PortableText).toString(
        QKeySequence.SequenceFormat.NativeText
    )


def native_binding(value: str | QKeySequence | None) -> str:
    """Return native keyboard text or the stable formal pointer token."""

    normalized = canonical_binding(value)
    if normalized is None:
        return ""
    if binding_is_pointer(normalized):
        return normalized
    return native_shortcut(normalized)


def _modifier_prefix(modifiers: Qt.KeyboardModifier) -> tuple[str, ...]:
    try:
        flags = Qt.KeyboardModifier(modifiers)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid pointer modifiers") from exc
    allowed = (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.ShiftModifier
    )
    if flags.value & ~allowed.value:
        raise ValueError("pointer bindings support only Ctrl, Alt, and Shift modifiers")
    names: list[str] = []
    for name, flag in (
        ("Ctrl", Qt.KeyboardModifier.ControlModifier),
        ("Alt", Qt.KeyboardModifier.AltModifier),
        ("Shift", Qt.KeyboardModifier.ShiftModifier),
    ):
        if flags & flag:
            names.append(name)
    return tuple(names)


_MOUSE_BUTTON_BASES = {
    Qt.MouseButton.LeftButton: "MouseLeft",
    Qt.MouseButton.MiddleButton: "MouseMiddle",
    Qt.MouseButton.RightButton: "MouseRight",
    Qt.MouseButton.BackButton: "MouseBack",
    Qt.MouseButton.ForwardButton: "MouseForward",
}


def mouse_button_binding(
    button: Qt.MouseButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> str | None:
    """Map one supported Qt mouse button and modifier state to a formal token."""

    prefix = _modifier_prefix(modifiers)
    try:
        normalized_button = Qt.MouseButton(button)
    except (TypeError, ValueError):
        return None
    base = _MOUSE_BUTTON_BASES.get(normalized_button)
    if base is None:
        return None
    return "+".join((*prefix, base))


def wheel_binding(
    delta_y: int,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> str | None:
    """Map the sign of a vertical Qt angle delta to a formal wheel token."""

    prefix = _modifier_prefix(modifiers)
    if delta_y == 0:
        return None
    base = "WheelUp" if delta_y > 0 else "WheelDown"
    return "+".join((*prefix, base))


_MODIFIER_KEYS = {
    "Ctrl",
    "Alt",
    "Shift",
    "Meta",
}
_RESERVED_PORTABLE = {
    "Esc",
    "Tab",
    "Shift+Tab",
    "Backtab",
    "Shift+Backtab",
    "Alt+F4",
    "Ctrl+Alt+Del",
}


def shortcut_is_reserved(value: str | QKeySequence | None) -> bool:
    """Return whether a keyboard chord or pointer token is unavailable."""

    try:
        portable = canonical_binding(value)
    except (TypeError, ValueError):
        return True
    if portable is None or portable in _MODIFIER_KEYS or portable in _RESERVED_PORTABLE:
        return True
    if binding_is_pointer(portable):
        return False
    parts = portable.split("+")
    return "Meta" in parts[:-1]


_TEXT_NAVIGATION_KEYS = {
    "Backspace",
    "Del",
    "Ins",
    "Home",
    "End",
    "Left",
    "Right",
    "Up",
    "Down",
    "PgUp",
    "PgDown",
    "Enter",
    "Return",
}
_STANDARD_TEXT_SHORTCUTS = {
    "Ctrl+A",
    "Ctrl+C",
    "Ctrl+V",
    "Ctrl+X",
    "Ctrl+Z",
    "Ctrl+Y",
    "Ctrl+Shift+Z",
} | {
    f"{modifier}{key}"
    for key in _TEXT_NAVIGATION_KEYS
    for modifier in ("", "Shift+", "Ctrl+", "Ctrl+Shift+")
}


def shortcut_is_text_sensitive(value: str | QKeySequence | None) -> bool:
    """Whether an editable text/number widget should receive the binding itself."""

    portable = canonical_binding(value)
    if portable is None:
        return False
    if binding_is_pointer(portable):
        return False
    if portable in _STANDARD_TEXT_SHORTCUTS:
        return True
    parts = portable.split("+")
    modifiers, key = parts[:-1], parts[-1]
    if any(modifier in {"Ctrl", "Alt", "Meta"} for modifier in modifiers):
        return False
    return len(key) == 1 or key == "Space"


def _shortcut_primary_key(value: str | QKeySequence | None) -> Qt.Key | None:
    """Return the logical non-modifier key, or ``None`` for an opaque token."""

    try:
        portable = canonical_shortcut(value)
    except (TypeError, ValueError):
        return None
    if portable is None:
        return None
    sequence = QKeySequence.fromString(portable, QKeySequence.SequenceFormat.PortableText)
    return sequence[0].key()


def _spec(
    category: str,
    name: str,
    operation_id: str,
    operation_type: OperationType,
    primary: str | None = None,
    secondary: str | None = None,
    effect: str | None = None,
) -> OperationSpec:
    return OperationSpec(
        operation_id=operation_id,
        category=category,
        name=name,
        operation_type=operation_type,
        effect=effect,
        primary=primary,
        secondary=secondary,
    )


# Specification 15.7 defines the first 38 rows.  The display-comparison
# addendum contributes one independently assignable, unbound-by-default row.
OPERATION_SPECS: tuple[OperationSpec, ...] = (
    _spec(
        "ファイル", "入出力フォルダ設定", "file.configure-folders", OperationType.SINGLE, "Ctrl+O"
    ),
    _spec("ファイル", "現在フォルダを再走査", "file.rescan-folders", OperationType.SINGLE, "F5"),
    _spec("ファイル", "保存", "file.save", OperationType.SINGLE, "Ctrl+S"),
    _spec("アプリ", "設定", "app.open-settings", OperationType.SINGLE, "Ctrl+,"),
    _spec("アプリ", "終了", "app.exit", OperationType.SINGLE),
    _spec("履歴", "Undo", "edit.undo", OperationType.SINGLE, "Ctrl+Z"),
    _spec("履歴", "Redo", "edit.redo", OperationType.SINGLE, "Ctrl+Y", "Ctrl+Shift+Z"),
    _spec("画像移動", "前画像", "navigate.previous-image", OperationType.SINGLE, "PageUp"),
    _spec("画像移動", "次画像", "navigate.next-image", OperationType.SINGLE, "PageDown"),
    _spec("編集", "筆を選択", "tool.brush", OperationType.SINGLE, "B"),
    _spec("編集", "塗り潰しを選択", "tool.fill", OperationType.SINGLE, "F"),
    _spec("編集", "無を選択", "label.select-none", OperationType.SINGLE, "1"),
    _spec("編集", "有を選択", "label.select-present", OperationType.SINGLE, "2"),
    _spec("編集", "境界を選択", "label.select-boundary", OperationType.SINGLE, "3"),
    _spec(
        "編集",
        "選択色を順方向に循環",
        "label.cycle-forward",
        OperationType.SINGLE,
        "C",
        effect="one-step",
    ),
    _spec(
        "編集",
        "選択色を逆方向に循環",
        "label.cycle-backward",
        OperationType.SINGLE,
        "Shift+C",
        effect="one-step",
    ),
    _spec("編集", "筆径を縮小", "brush.decrease-size", OperationType.STEP, "[", effect="-1px"),
    _spec("編集", "筆径を拡大", "brush.increase-size", OperationType.STEP, "]", effect="+1px"),
    _spec("編集", "筆形状を円形", "brush.shape-circle", OperationType.SINGLE),
    _spec("編集", "筆形状を正方形", "brush.shape-square", OperationType.SINGLE),
    _spec(
        "編集",
        "筆形状を切り替える",
        "brush.cycle-shape",
        OperationType.SINGLE,
        "X",
        effect="one-step",
    ),
    _spec("表示", "原画像表示を切り替える", "view.toggle-original", OperationType.SINGLE, "O"),
    _spec("表示", "三値画像表示を切り替える", "view.toggle-label", OperationType.SINGLE, "T"),
    _spec("表示", "疑似色表示を切り替える", "view.toggle-pseudocolor", OperationType.SINGLE, "P"),
    _spec(
        "表示",
        "比較（暗）を切り替える",
        "view.toggle-darken-comparison",
        OperationType.SINGLE,
    ),
    _spec(
        "表示", "画素格子自動表示を切り替える", "view.toggle-grid-auto", OperationType.SINGLE, "G"
    ),
    _spec(
        "表示", "小領域強調を切り替える", "view.toggle-small-components", OperationType.SINGLE, "L"
    ),
    _spec(
        "表示",
        "原画像不透明度を下げる",
        "view.decrease-original-opacity",
        OperationType.STEP,
        effect="-5pt",
    ),
    _spec(
        "表示",
        "原画像不透明度を上げる",
        "view.increase-original-opacity",
        OperationType.STEP,
        effect="+5pt",
    ),
    _spec("表示", "縮小", "view.zoom-out", OperationType.STEP, "Ctrl+-", effect="/1.25"),
    _spec("表示", "拡大", "view.zoom-in", OperationType.STEP, "Ctrl++", effect="*1.25"),
    _spec("表示", "100％表示", "view.zoom-100", OperationType.SINGLE, "Ctrl+1"),
    _spec("表示", "全体表示", "view.fit-image", OperationType.SINGLE, "Ctrl+0"),
    _spec("表示", "一時パン操作", "view.temporary-pan", OperationType.HOLD, "Space"),
    _spec("境界生成", "無側生成を選択", "boundary.select-none-side", OperationType.SINGLE, "Alt+1"),
    _spec(
        "境界生成",
        "非無側生成を選択",
        "boundary.select-non-none-side",
        OperationType.SINGLE,
        "Alt+2",
    ),
    _spec(
        "境界生成",
        "境界太さを減らす",
        "boundary.decrease-thickness",
        OperationType.STEP,
        effect="-1px",
    ),
    _spec(
        "境界生成",
        "境界太さを増やす",
        "boundary.increase-thickness",
        OperationType.STEP,
        effect="+1px",
    ),
    _spec(
        "境界生成", "選択中モードで生成", "boundary.generate", OperationType.SINGLE, "Ctrl+Shift+B"
    ),
)


def _validate_specs(specs: Iterable[OperationSpec]) -> Mapping[str, OperationSpec]:
    by_id: dict[str, OperationSpec] = {}
    seen_shortcuts: dict[str, str] = {}
    for spec in specs:
        if spec.operation_id in by_id:
            raise ValueError(f"duplicate operation id: {spec.operation_id}")
        by_id[spec.operation_id] = spec
        for shortcut in (spec.primary, spec.secondary):
            if shortcut is None:
                continue
            if shortcut_is_reserved(shortcut):
                raise ValueError(f"reserved default shortcut {shortcut}: {spec.operation_id}")
            if shortcut in seen_shortcuts:
                raise ValueError(
                    f"duplicate default shortcut {shortcut}: "
                    f"{seen_shortcuts[shortcut]} and {spec.operation_id}"
                )
            seen_shortcuts[shortcut] = spec.operation_id
    return MappingProxyType(by_id)


OPERATION_BY_ID: Mapping[str, OperationSpec] = _validate_specs(OPERATION_SPECS)


def default_shortcuts() -> dict[str, ShortcutBindings]:
    return {
        spec.operation_id: ShortcutBindings(spec.primary, spec.secondary)
        for spec in OPERATION_SPECS
    }


def _validate_operation_binding(spec: OperationSpec, value: str | None) -> None:
    if value is None:
        return
    if spec.operation_type is OperationType.HOLD and binding_is_wheel(value):
        raise ValueError(
            f"wheel binding {value} cannot be assigned to HOLD operation {spec.operation_id}"
        )
    if spec.operation_id == "view.temporary-pan" and pointer_base(value) == "MouseLeft":
        raise ValueError("view.temporary-pan cannot use a MouseLeft binding")


class ShortcutAssignments:
    """Mutable, copyable work set with deterministic conflict handling."""

    def __init__(
        self,
        bindings: Mapping[str, ShortcutBindings] | None = None,
        *,
        specs: Iterable[OperationSpec] = OPERATION_SPECS,
    ) -> None:
        self._specs = tuple(specs)
        self._by_id = {spec.operation_id: spec for spec in self._specs}
        source = default_shortcuts() if bindings is None else bindings
        unknown = set(source) - set(self._by_id)
        if unknown:
            raise KeyError(f"unknown operation ids: {sorted(unknown)!r}")
        self._bindings = {
            spec.operation_id: source.get(
                spec.operation_id, ShortcutBindings(spec.primary, spec.secondary)
            )
            for spec in self._specs
        }
        self._validate_unique()

    def copy(self) -> ShortcutAssignments:
        return ShortcutAssignments(self._bindings, specs=self._specs)

    def as_dict(self) -> dict[str, ShortcutBindings]:
        return dict(self._bindings)

    def binding(self, operation_id: str) -> ShortcutBindings:
        self._require_operation(operation_id)
        return self._bindings[operation_id]

    def owner_of(self, sequence: str | QKeySequence | None) -> AssignmentTarget | None:
        binding = canonical_binding(sequence)
        if binding is None:
            return None
        for operation_id, bindings in self._bindings.items():
            if bindings.primary == binding:
                return AssignmentTarget(operation_id, ShortcutSlot.PRIMARY)
            if bindings.secondary == binding:
                return AssignmentTarget(operation_id, ShortcutSlot.SECONDARY)
        return None

    def assign(
        self,
        operation_id: str,
        slot: ShortcutSlot | str,
        sequence: str | QKeySequence | None,
        *,
        move_conflict: bool = False,
    ) -> AssignmentChange:
        spec = self._require_operation(operation_id)
        normalized_slot = ShortcutSlot(slot)
        binding = canonical_binding(sequence)
        _validate_operation_binding(spec, binding)
        target = AssignmentTarget(operation_id, normalized_slot)
        current = self._bindings[operation_id]
        if current.value(normalized_slot) == binding:
            return AssignmentChange(AssignmentStatus.UNCHANGED)
        owner = self.owner_of(binding)
        if owner is not None and owner != target:
            conflict = ShortcutConflict(binding or "", owner, target)
            if owner.operation_id == operation_id:
                return AssignmentChange(AssignmentStatus.DUPLICATE_SELF, conflict)
            if not move_conflict:
                return AssignmentChange(AssignmentStatus.CONFLICT, conflict)
            self._bindings[owner.operation_id] = self._bindings[owner.operation_id].replaced(
                owner.slot, None
            )
        self._bindings[operation_id] = current.replaced(normalized_slot, binding)
        return AssignmentChange(AssignmentStatus.APPLIED)

    def clear(self, operation_id: str, slot: ShortcutSlot | str) -> AssignmentChange:
        return self.assign(operation_id, slot, None)

    def restore_operation(self, operation_id: str) -> None:
        spec = self._require_operation(operation_id)
        for slot, value in (
            (ShortcutSlot.PRIMARY, spec.primary),
            (ShortcutSlot.SECONDARY, spec.secondary),
        ):
            if value is None:
                self.clear(operation_id, slot)
                continue
            result = self.assign(operation_id, slot, value, move_conflict=True)
            if result.status is AssignmentStatus.DUPLICATE_SELF:
                raise ValueError(f"invalid defaults for {operation_id}")

    def restore_all(self) -> None:
        self._bindings = {
            spec.operation_id: ShortcutBindings(spec.primary, spec.secondary)
            for spec in self._specs
        }

    def _require_operation(self, operation_id: str) -> OperationSpec:
        try:
            return self._by_id[operation_id]
        except KeyError as exc:
            raise KeyError(f"unknown operation id: {operation_id}") from exc

    def _validate_unique(self) -> None:
        seen: dict[str, AssignmentTarget] = {}
        for operation_id, bindings in self._bindings.items():
            spec = self._by_id[operation_id]
            for slot, value in (
                (ShortcutSlot.PRIMARY, bindings.primary),
                (ShortcutSlot.SECONDARY, bindings.secondary),
            ):
                if value is None:
                    continue
                _validate_operation_binding(spec, value)
                target = AssignmentTarget(operation_id, slot)
                if value in seen:
                    raise ValueError(f"shortcut {value} is assigned more than once")
                seen[value] = target


@dataclass(slots=True)
class _RegisteredCallbacks:
    trigger: Callable[[], None] | None = None
    press: Callable[[], None] | None = None
    release: Callable[[], None] | None = None
    enabled: Callable[[], bool] | None = None


class ActionRegistry(QObject):
    """Runtime callbacks and deterministic keyboard/pointer dispatch.

    The integration layer may use this router instead of Qt's shortcut map.  In
    that mode generated ``QAction`` objects are command surfaces only; menu,
    button and keyboard paths all call the same registered callback.
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        assignments: ShortcutAssignments | None = None,
    ) -> None:
        super().__init__(parent)
        self.assignments = assignments.copy() if assignments is not None else ShortcutAssignments()
        self._callbacks: dict[str, _RegisteredCallbacks] = {}
        self._actions: dict[str, list[tuple[QAction, bool]]] = {}
        self._active_hold_keys: dict[str, str] = {}

    def register(
        self,
        operation_id: str,
        callback: Callable[[], None] | None = None,
        *,
        on_press: Callable[[], None] | None = None,
        on_release: Callable[[], None] | None = None,
        enabled: Callable[[], bool] | None = None,
    ) -> None:
        spec = self.spec(operation_id)
        if operation_id in self._callbacks:
            raise ValueError(f"operation already registered: {operation_id}")
        if spec.operation_type is OperationType.HOLD:
            if on_press is None or on_release is None:
                raise ValueError("hold operations require on_press and on_release")
        elif callback is None:
            raise ValueError("single and step operations require a callback")
        self._callbacks[operation_id] = _RegisteredCallbacks(
            trigger=callback,
            press=on_press,
            release=on_release,
            enabled=enabled,
        )

    @staticmethod
    def spec(operation_id: str) -> OperationSpec:
        try:
            return OPERATION_BY_ID[operation_id]
        except KeyError as exc:
            raise KeyError(f"unknown operation id: {operation_id}") from exc

    def is_enabled(self, operation_id: str) -> bool:
        callbacks = self._callbacks.get(operation_id)
        return callbacks is not None and (callbacks.enabled is None or callbacks.enabled())

    def invoke(self, operation_id: str) -> bool:
        callbacks = self._callbacks.get(operation_id)
        if callbacks is None or callbacks.trigger is None or not self.is_enabled(operation_id):
            return False
        callbacks.trigger()
        return True

    def press(self, operation_id: str, *, key_token: str | None = None) -> bool:
        callbacks = self._callbacks.get(operation_id)
        if callbacks is None or callbacks.press is None or not self.is_enabled(operation_id):
            return False
        token = key_token or operation_id
        if token in self._active_hold_keys:
            return True
        already_active = operation_id in self._active_hold_keys.values()
        self._active_hold_keys[token] = operation_id
        if not already_active:
            callbacks.press()
        return True

    def release(self, operation_id: str, *, key_token: str | None = None) -> bool:
        callbacks = self._callbacks.get(operation_id)
        if callbacks is None or callbacks.release is None:
            return False
        token = key_token or operation_id
        if self._active_hold_keys.pop(token, None) is None:
            return False
        if operation_id not in self._active_hold_keys.values():
            callbacks.release()
        return True

    def release_all_holds(self) -> None:
        active_operations = tuple(dict.fromkeys(self._active_hold_keys.values()))
        self._active_hold_keys.clear()
        for operation_id in active_operations:
            callbacks = self._callbacks.get(operation_id)
            if callbacks is not None and callbacks.release is not None:
                callbacks.release()

    def set_assignments(self, assignments: ShortcutAssignments) -> None:
        self.release_all_holds()
        self.assignments = assignments.copy()
        for operation_id in self._actions:
            self._refresh_actions(operation_id)

    def operation_for_shortcut(self, sequence: str | QKeySequence | None) -> str | None:
        shortcut = canonical_shortcut(sequence)
        if shortcut is None:
            return None
        return self.operation_for_binding(shortcut)

    def operation_for_binding(self, binding: str | QKeySequence | None) -> str | None:
        owner = self.assignments.owner_of(binding)
        return None if owner is None else owner.operation_id

    def dispatch_pointer_press(self, binding: str) -> bool:
        normalized = canonical_binding(binding)
        if normalized is None or not binding_is_pointer(normalized):
            return False
        operation_id = self.operation_for_binding(normalized)
        if operation_id is None:
            return False
        spec = self.spec(operation_id)
        if spec.operation_type is OperationType.HOLD:
            self.press(operation_id, key_token=normalized)
        else:
            self.invoke(operation_id)
        # Assignment ownership consumes the physical gesture even if the
        # operation is currently disabled or has not been registered yet.
        return True

    def dispatch_pointer_release(self, binding: str) -> bool:
        normalized = canonical_binding(binding)
        if normalized is None or not binding_is_pointer(normalized):
            return False
        operation_id = self.operation_for_binding(normalized)
        if operation_id is None or self.spec(operation_id).operation_type is not OperationType.HOLD:
            return False
        return self.release(operation_id, key_token=normalized)

    def dispatch_key_press(
        self,
        sequence: str | QKeySequence,
        *,
        auto_repeat: bool = False,
        text_input: bool = False,
    ) -> bool:
        portable = canonical_shortcut(sequence)
        if portable is None or (text_input and shortcut_is_text_sensitive(portable)):
            return False
        operation_id = self.operation_for_shortcut(portable)
        if operation_id is None:
            return False
        spec = self.spec(operation_id)
        if spec.operation_type is OperationType.SINGLE:
            if not auto_repeat:
                self.invoke(operation_id)
            return True
        if spec.operation_type is OperationType.STEP:
            self.invoke(operation_id)
            return True
        if not auto_repeat:
            self.press(operation_id, key_token=portable)
        return True

    def dispatch_key_release(
        self,
        sequence: str | QKeySequence,
        *,
        auto_repeat: bool = False,
    ) -> bool:
        if auto_repeat:
            return False
        portable = canonical_shortcut(sequence)
        if portable is None:
            return False
        released_key = _shortcut_primary_key(portable)
        if released_key is None:
            return False
        # OSes may report KeyUp after a modifier has already been released.  A
        # Ctrl+K hold can therefore end as plain K.  Remove every keyboard token
        # for that logical primary key; opaque GUI latch tokens remain active and
        # retain the existing multi-token hold semantics.
        matching_tokens = tuple(
            token
            for token in self._active_hold_keys
            if _shortcut_primary_key(token) == released_key
        )
        handled = False
        for token in matching_tokens:
            operation_id = self._active_hold_keys.get(token)
            if operation_id is not None:
                handled = self.release(operation_id, key_token=token) or handled
        return handled

    def dispatch_event(self, event: QKeyEvent, *, text_input: bool = False) -> bool:
        sequence = QKeySequence(event.keyCombination())
        if event.type() == QKeyEvent.Type.KeyPress:
            return self.dispatch_key_press(
                sequence,
                auto_repeat=event.isAutoRepeat(),
                text_input=text_input,
            )
        if event.type() == QKeyEvent.Type.KeyRelease:
            return self.dispatch_key_release(sequence, auto_repeat=event.isAutoRepeat())
        return False

    def create_action(
        self,
        operation_id: str,
        parent: QObject | None = None,
        *,
        install_native_shortcuts: bool = False,
    ) -> QAction:
        spec = self.spec(operation_id)
        action = QAction(spec.name, parent or self)
        action.setObjectName(f"operation:{operation_id}")
        action.setData(operation_id)
        action.setAutoRepeat(spec.operation_type is OperationType.STEP)
        if spec.operation_type is not OperationType.HOLD:
            action.triggered.connect(lambda _checked=False, op=operation_id: self.invoke(op))
        self._actions.setdefault(operation_id, []).append((action, install_native_shortcuts))
        self._refresh_action(operation_id, action, install_native_shortcuts)
        return action

    def _refresh_actions(self, operation_id: str) -> None:
        for action, install_native_shortcuts in self._actions.get(operation_id, ()):
            self._refresh_action(operation_id, action, install_native_shortcuts)

    def _refresh_action(
        self,
        operation_id: str,
        action: QAction,
        install_native_shortcuts: bool,
    ) -> None:
        if (
            not install_native_shortcuts
            or self.spec(operation_id).operation_type is OperationType.HOLD
        ):
            action.setShortcuts([])
            return
        bindings = self.assignments.binding(operation_id)
        action.setShortcuts(
            [
                QKeySequence.fromString(value, QKeySequence.SequenceFormat.PortableText)
                for value in bindings.sequences()
                if not binding_is_pointer(value)
            ]
        )


__all__ = [
    "ActionRegistry",
    "AssignmentChange",
    "AssignmentStatus",
    "AssignmentTarget",
    "OPERATION_BY_ID",
    "OPERATION_SPECS",
    "OperationSpec",
    "OperationType",
    "ShortcutAssignments",
    "ShortcutBindings",
    "ShortcutConflict",
    "ShortcutSlot",
    "binding_is_pointer",
    "binding_is_wheel",
    "canonical_binding",
    "canonical_shortcut",
    "default_shortcuts",
    "mouse_button_binding",
    "native_binding",
    "native_shortcut",
    "pointer_base",
    "shortcut_is_reserved",
    "shortcut_is_text_sensitive",
    "wheel_binding",
]
