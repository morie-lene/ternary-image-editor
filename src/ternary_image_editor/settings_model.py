"""Validated settings-schema v2 model and QSettings persistence adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from math import dist
from types import MappingProxyType
from typing import Any

from PySide6.QtCore import QByteArray, QSettings

from .action_registry import (
    OPERATION_SPECS,
    ShortcutAssignments,
    ShortcutBindings,
    ShortcutSlot,
    canonical_binding,
    canonical_shortcut,
    default_shortcuts,
    shortcut_is_reserved,
)
from .constants import (
    DEFAULT_BRUSH_DIAMETER,
    DEFAULT_MEMO_RGB,
    DEFAULT_PSEUDO_RGB,
    MAX_BOUNDARY_THICKNESS,
    MAX_BRUSH_DIAMETER,
    MIN_BOUNDARY_THICKNESS,
    MIN_BRUSH_DIAMETER,
)

SETTINGS_SCHEMA_VERSION = 2
DEFAULT_PSEUDO_COLORS = tuple(
    f"#{red:02X}{green:02X}{blue:02X}" for red, green, blue in DEFAULT_PSEUDO_RGB
)
DEFAULT_MEMO_COLOR = (
    f"#{DEFAULT_MEMO_RGB[0]:02X}{DEFAULT_MEMO_RGB[1]:02X}{DEFAULT_MEMO_RGB[2]:02X}"
)


class SettingsPersistenceError(RuntimeError):
    """QSettings could not persist a validated settings snapshot."""


def normalize_hex_color(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("color must be a #RRGGBB string")
    text = value.strip()
    if len(text) != 7 or not text.startswith("#"):
        raise ValueError("color must use #RRGGBB")
    try:
        int(text[1:], 16)
    except ValueError as exc:
        raise ValueError("color must use #RRGGBB") from exc
    return text.upper()


def rgb_from_hex(value: str) -> tuple[int, int, int]:
    text = normalize_hex_color(value)
    return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)


def hex_from_rgb(value: tuple[int, int, int]) -> str:
    if len(value) != 3 or any(
        isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255
        for channel in value
    ):
        raise ValueError("RGB must contain three integers from 0 through 255")
    return f"#{value[0]:02X}{value[1]:02X}{value[2]:02X}"


def color_distance(first: str, second: str) -> float:
    return dist(rgb_from_hex(first), rgb_from_hex(second))


def close_color_pairs(
    colors: tuple[str, str, str] | list[str],
    *,
    threshold: float = 64.0,
) -> tuple[tuple[int, int, float], ...]:
    if len(colors) != 3:
        raise ValueError("exactly three pseudo colors are required")
    normalized = tuple(normalize_hex_color(color) for color in colors)
    result: list[tuple[int, int, float]] = []
    for first in range(3):
        for second in range(first + 1, 3):
            distance = color_distance(normalized[first], normalized[second])
            if distance < threshold:
                result.append((first, second, distance))
    return tuple(result)


def _strict_bool(value: object, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be bool")
    return value


def _bounded_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _binary(value: bytes | bytearray | QByteArray, *, name: str) -> bytes:
    if isinstance(value, QByteArray):
        return bytes(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    raise TypeError(f"{name} must be bytes")


@dataclass(frozen=True, slots=True)
class AppSettings:
    """One fully validated applied settings snapshot.

    Ephemeral selection label, current image, zoom and view centre are omitted on
    purpose; the type itself prevents them from leaking into persistence.
    """

    schema_version: int = SETTINGS_SCHEMA_VERSION
    original_folder: str = ""
    ternary_folder: str = ""
    output_folder: str = ""
    window_geometry: bytes = b""
    window_state: bytes = b""
    original_visible: bool = True
    ternary_visible: bool = True
    pseudo_enabled: bool = False
    darken_comparison_enabled: bool = False
    pseudo_colors: tuple[str, str, str] = DEFAULT_PSEUDO_COLORS
    original_opacity: int = 50
    grid_auto: bool = True
    small_components: bool = False
    tool: str = "brush"
    brush_shape: str = "circle"
    brush_diameter: int = DEFAULT_BRUSH_DIAMETER
    memo_enabled: bool = True
    memo_color: str = DEFAULT_MEMO_COLOR
    boundary_mode: str = "none_side"
    boundary_thickness: int = MIN_BOUNDARY_THICKNESS
    shortcuts: Mapping[str, ShortcutBindings] = field(default_factory=default_shortcuts)

    def __post_init__(self) -> None:
        if self.schema_version != SETTINGS_SCHEMA_VERSION:
            raise ValueError(f"AppSettings schema must be {SETTINGS_SCHEMA_VERSION}")
        for name in ("original_folder", "ternary_folder", "output_folder"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")
        object.__setattr__(
            self, "window_geometry", _binary(self.window_geometry, name="window_geometry")
        )
        object.__setattr__(self, "window_state", _binary(self.window_state, name="window_state"))
        for name in (
            "original_visible",
            "ternary_visible",
            "pseudo_enabled",
            "darken_comparison_enabled",
            "grid_auto",
            "small_components",
            "memo_enabled",
        ):
            _strict_bool(getattr(self, name), name=name)
        if len(self.pseudo_colors) != 3:
            raise ValueError("pseudo_colors must contain exactly three colors")
        colors = tuple(normalize_hex_color(color) for color in self.pseudo_colors)
        object.__setattr__(self, "pseudo_colors", colors)
        object.__setattr__(self, "memo_color", normalize_hex_color(self.memo_color))
        _bounded_int(self.original_opacity, name="original_opacity", minimum=0, maximum=100)
        if self.tool not in {"brush", "fill"}:
            raise ValueError("tool must be brush or fill")
        if self.brush_shape not in {"circle", "square"}:
            raise ValueError("brush_shape must be circle or square")
        _bounded_int(
            self.brush_diameter,
            name="brush_diameter",
            minimum=MIN_BRUSH_DIAMETER,
            maximum=MAX_BRUSH_DIAMETER,
        )
        if self.boundary_mode not in {"none_side", "non_none_side"}:
            raise ValueError("invalid boundary_mode")
        _bounded_int(
            self.boundary_thickness,
            name="boundary_thickness",
            minimum=MIN_BOUNDARY_THICKNESS,
            maximum=MAX_BOUNDARY_THICKNESS,
        )
        expected_ids = {spec.operation_id for spec in OPERATION_SPECS}
        if set(self.shortcuts) != expected_ids:
            raise ValueError(
                "shortcuts must contain every known operation and no unknown operation"
            )
        assignments = ShortcutAssignments(self.shortcuts)
        object.__setattr__(self, "shortcuts", MappingProxyType(assignments.as_dict()))

    def work_copy(self) -> SettingsWorkCopy:
        return SettingsWorkCopy.from_settings(self)


@dataclass(slots=True)
class SettingsWorkCopy:
    """Mutable dialog-local copy; conversion is the validation boundary."""

    original_folder: str
    ternary_folder: str
    output_folder: str
    window_geometry: bytes
    window_state: bytes
    original_visible: bool
    ternary_visible: bool
    pseudo_enabled: bool
    darken_comparison_enabled: bool
    pseudo_colors: list[str]
    original_opacity: int
    grid_auto: bool
    small_components: bool
    tool: str
    brush_shape: str
    brush_diameter: int
    memo_enabled: bool
    memo_color: str
    boundary_mode: str
    boundary_thickness: int
    shortcut_assignments: ShortcutAssignments

    @classmethod
    def from_settings(cls, settings: AppSettings) -> SettingsWorkCopy:
        return cls(
            original_folder=settings.original_folder,
            ternary_folder=settings.ternary_folder,
            output_folder=settings.output_folder,
            window_geometry=settings.window_geometry,
            window_state=settings.window_state,
            original_visible=settings.original_visible,
            ternary_visible=settings.ternary_visible,
            pseudo_enabled=settings.pseudo_enabled,
            darken_comparison_enabled=settings.darken_comparison_enabled,
            pseudo_colors=list(settings.pseudo_colors),
            original_opacity=settings.original_opacity,
            grid_auto=settings.grid_auto,
            small_components=settings.small_components,
            tool=settings.tool,
            brush_shape=settings.brush_shape,
            brush_diameter=settings.brush_diameter,
            memo_enabled=settings.memo_enabled,
            memo_color=settings.memo_color,
            boundary_mode=settings.boundary_mode,
            boundary_thickness=settings.boundary_thickness,
            shortcut_assignments=ShortcutAssignments(settings.shortcuts),
        )

    def copy(self) -> SettingsWorkCopy:
        return SettingsWorkCopy.from_settings(self.to_settings())

    def to_settings(self) -> AppSettings:
        return AppSettings(
            original_folder=self.original_folder,
            ternary_folder=self.ternary_folder,
            output_folder=self.output_folder,
            window_geometry=self.window_geometry,
            window_state=self.window_state,
            original_visible=self.original_visible,
            ternary_visible=self.ternary_visible,
            pseudo_enabled=self.pseudo_enabled,
            darken_comparison_enabled=self.darken_comparison_enabled,
            pseudo_colors=tuple(self.pseudo_colors),  # type: ignore[arg-type]
            original_opacity=self.original_opacity,
            grid_auto=self.grid_auto,
            small_components=self.small_components,
            tool=self.tool,
            brush_shape=self.brush_shape,
            brush_diameter=self.brush_diameter,
            memo_enabled=self.memo_enabled,
            memo_color=self.memo_color,
            boundary_mode=self.boundary_mode,
            boundary_thickness=self.boundary_thickness,
            shortcuts=self.shortcut_assignments.as_dict(),
        )


@dataclass(frozen=True, slots=True)
class _ShortcutLoadCandidate:
    operation_id: str
    slot: ShortcutSlot
    value: str | None
    fallback: str | None
    explicit_valid: bool


class SettingsRepository:
    """Per-user, schema-versioned QSettings storage.

    A missing shortcut key means "use this build's default".  An existing empty
    value means "explicitly unassigned".  Unknown operation groups are never
    enumerated or removed, so downgrade/upgrade cycles preserve them.
    """

    def __init__(self, settings: QSettings) -> None:
        self.settings = settings
        self.warnings: list[str] = []

    def load(self) -> AppSettings:
        self.warnings.clear()
        defaults = AppSettings()
        schema = self._read_int("schema/version", 0, minimum=0, maximum=2**31 - 1)
        if schema not in {0, 1, SETTINGS_SCHEMA_VERSION}:
            self.warnings.append(
                f"unknown settings schema {schema}; known fields were read conservatively"
            )
        colors = self._load_colors(defaults)
        shortcut_bindings = self._load_shortcuts(schema)
        return AppSettings(
            original_folder=self._read_str("folders/original", defaults.original_folder),
            ternary_folder=self._read_str("folders/ternary", defaults.ternary_folder),
            output_folder=self._read_str("folders/output", defaults.output_folder),
            window_geometry=self._read_bytes("window/geometry", defaults.window_geometry),
            window_state=self._read_bytes("window/state", defaults.window_state),
            original_visible=self._read_bool("view/originalVisible", defaults.original_visible),
            ternary_visible=self._read_bool("view/ternaryVisible", defaults.ternary_visible),
            pseudo_enabled=self._read_bool("view/pseudoEnabled", defaults.pseudo_enabled),
            darken_comparison_enabled=self._read_bool(
                "view/darkenComparison", defaults.darken_comparison_enabled
            ),
            pseudo_colors=colors,
            original_opacity=self._read_int(
                "view/originalOpacity", defaults.original_opacity, minimum=0, maximum=100
            ),
            grid_auto=self._read_bool("view/autoGrid", defaults.grid_auto),
            small_components=self._read_bool("view/smallComponents", defaults.small_components),
            tool=self._read_choice("edit/tool", defaults.tool, {"brush", "fill"}),
            brush_shape=self._read_choice(
                "edit/brushShape", defaults.brush_shape, {"circle", "square"}
            ),
            brush_diameter=self._read_int(
                "edit/brushDiameter",
                defaults.brush_diameter,
                minimum=MIN_BRUSH_DIAMETER,
                maximum=MAX_BRUSH_DIAMETER,
            ),
            memo_enabled=self._read_bool("memo/enabled", defaults.memo_enabled),
            memo_color=self._read_value(
                "memo/color",
                defaults.memo_color,
                normalize_hex_color,
            ),
            boundary_mode=self._read_choice(
                "boundary/mode",
                defaults.boundary_mode,
                {"none_side", "non_none_side"},
            ),
            boundary_thickness=self._read_int(
                "boundary/thickness",
                defaults.boundary_thickness,
                minimum=MIN_BOUNDARY_THICKNESS,
                maximum=MAX_BOUNDARY_THICKNESS,
            ),
            shortcuts=shortcut_bindings,
        )

    def save(self, snapshot: AppSettings) -> None:
        if not isinstance(snapshot, AppSettings):
            raise TypeError("snapshot must be AppSettings")
        values: dict[str, object] = {
            "schema/version": SETTINGS_SCHEMA_VERSION,
            "folders/original": snapshot.original_folder,
            "folders/ternary": snapshot.ternary_folder,
            "folders/output": snapshot.output_folder,
            "window/geometry": QByteArray(snapshot.window_geometry),
            "window/state": QByteArray(snapshot.window_state),
            "view/originalVisible": snapshot.original_visible,
            "view/ternaryVisible": snapshot.ternary_visible,
            "view/pseudoEnabled": snapshot.pseudo_enabled,
            "view/darkenComparison": snapshot.darken_comparison_enabled,
            "view/pseudoColorNone": snapshot.pseudo_colors[0],
            "view/pseudoColorPresent": snapshot.pseudo_colors[1],
            "view/pseudoColorBoundary": snapshot.pseudo_colors[2],
            "view/originalOpacity": snapshot.original_opacity,
            "view/autoGrid": snapshot.grid_auto,
            "view/smallComponents": snapshot.small_components,
            "edit/tool": snapshot.tool,
            "edit/brushShape": snapshot.brush_shape,
            "edit/brushDiameter": snapshot.brush_diameter,
            "memo/enabled": snapshot.memo_enabled,
            "memo/color": snapshot.memo_color,
            "boundary/mode": snapshot.boundary_mode,
            "boundary/thickness": snapshot.boundary_thickness,
        }
        for key, value in values.items():
            self.settings.setValue(key, value)
        for operation_id, bindings in snapshot.shortcuts.items():
            self.settings.setValue(f"shortcuts/{operation_id}/primary", bindings.primary or "")
            self.settings.setValue(f"shortcuts/{operation_id}/secondary", bindings.secondary or "")
        self.settings.sync()
        if self.settings.status() is not QSettings.Status.NoError:
            raise SettingsPersistenceError(f"QSettings sync failed: {self.settings.status().name}")

    def _load_colors(self, defaults: AppSettings) -> tuple[str, str, str]:
        keys = (
            "view/pseudoColorNone",
            "view/pseudoColorPresent",
            "view/pseudoColorBoundary",
        )
        if any(self.settings.contains(key) for key in keys):
            return tuple(
                self._read_value(key, default, normalize_hex_color)
                for key, default in zip(keys, defaults.pseudo_colors, strict=True)
            )  # type: ignore[return-value]
        if self.settings.contains("view/pseudoPalette"):
            raw = self._read_str("view/pseudoPalette", "")
            try:
                colors = tuple(
                    hex_from_rgb(tuple(int(channel) for channel in item.split(",")))
                    for item in raw.split(";")
                )
                if len(colors) != 3:
                    raise ValueError
                return colors  # type: ignore[return-value]
            except (TypeError, ValueError):
                self.warnings.append("invalid legacy pseudo palette; defaults were used")
        return defaults.pseudo_colors

    def _load_shortcuts(self, schema: int) -> dict[str, ShortcutBindings]:
        defaults = default_shortcuts()
        parser = canonical_shortcut if schema in {0, 1} else canonical_binding
        candidates: list[_ShortcutLoadCandidate] = []
        for spec in OPERATION_SPECS:
            for slot in (ShortcutSlot.PRIMARY, ShortcutSlot.SECONDARY):
                key = f"shortcuts/{spec.operation_id}/{slot.value}"
                fallback = defaults[spec.operation_id].value(slot)
                explicit_valid = False
                if not self.settings.contains(key):
                    candidate = fallback
                else:
                    raw = self.settings.value(key, "")
                    if raw is None or str(raw) == "":
                        candidate = None
                    else:
                        try:
                            candidate = parser(str(raw))
                            if shortcut_is_reserved(candidate):
                                raise ValueError("reserved shortcut")
                            probe = (
                                ShortcutBindings(candidate, None)
                                if slot is ShortcutSlot.PRIMARY
                                else ShortcutBindings(None, candidate)
                            )
                            ShortcutAssignments(
                                {spec.operation_id: probe},
                                specs=(spec,),
                            )
                        except (TypeError, ValueError):
                            candidate = fallback
                            self.warnings.append(
                                f"invalid shortcut {spec.operation_id}/{slot.value}; "
                                "default fallback requested"
                            )
                        else:
                            explicit_valid = True
                candidates.append(
                    _ShortcutLoadCandidate(
                        operation_id=spec.operation_id,
                        slot=slot,
                        value=candidate,
                        fallback=fallback,
                        explicit_valid=explicit_valid,
                    )
                )

        resolved: dict[tuple[str, ShortcutSlot], str | None] = {}
        seen: set[str] = set()
        deferred: list[tuple[_ShortcutLoadCandidate, bool]] = []
        for candidate in candidates:
            key = (candidate.operation_id, candidate.slot)
            if not candidate.explicit_valid:
                deferred.append((candidate, False))
                continue
            value = candidate.value
            if value in seen:
                self.warnings.append(
                    f"conflicting shortcut {value}; {candidate.operation_id}/"
                    f"{candidate.slot.value} was reset"
                )
                deferred.append(
                    (
                        _ShortcutLoadCandidate(
                            operation_id=candidate.operation_id,
                            slot=candidate.slot,
                            value=candidate.fallback,
                            fallback=candidate.fallback,
                            explicit_valid=False,
                        ),
                        True,
                    )
                )
                continue
            if value is not None:
                seen.add(value)
            resolved[key] = value

        for candidate, conflict_reported in deferred:
            key = (candidate.operation_id, candidate.slot)
            value = candidate.value
            if value is not None and value in seen:
                if not conflict_reported:
                    self.warnings.append(
                        f"conflicting shortcut {value}; {candidate.operation_id}/"
                        f"{candidate.slot.value} was reset"
                    )
                value = None
            if value is not None:
                seen.add(value)
            resolved[key] = value

        result: dict[str, ShortcutBindings] = {}
        for spec in OPERATION_SPECS:
            primary = resolved[(spec.operation_id, ShortcutSlot.PRIMARY)]
            secondary = resolved[(spec.operation_id, ShortcutSlot.SECONDARY)]
            try:
                result[spec.operation_id] = ShortcutBindings(primary, secondary)
            except ValueError:
                self.warnings.append(
                    f"duplicate primary/secondary for {spec.operation_id}; secondary cleared"
                )
                result[spec.operation_id] = ShortcutBindings(primary, None)
        return result

    def _read_value(
        self,
        key: str,
        default: Any,
        validator: Callable[[Any], Any],
    ) -> Any:
        if not self.settings.contains(key):
            return default
        raw = self.settings.value(key)
        try:
            return validator(raw)
        except (TypeError, ValueError):
            self.warnings.append(f"invalid setting {key}; default used")
            return default

    def _read_str(self, key: str, default: str) -> str:
        return self._read_value(
            key, default, lambda value: value if isinstance(value, str) else str(value)
        )

    def _read_bool(self, key: str, default: bool) -> bool:
        def parse(value: object) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.casefold() in {"true", "false", "1", "0"}:
                return value.casefold() in {"true", "1"}
            if isinstance(value, int) and value in {0, 1}:
                return bool(value)
            raise ValueError

        return self._read_value(key, default, parse)

    def _read_int(self, key: str, default: int, *, minimum: int, maximum: int) -> int:
        def parse(value: object) -> int:
            if isinstance(value, bool):
                raise ValueError
            integer = int(value)  # type: ignore[arg-type]
            return _bounded_int(integer, name=key, minimum=minimum, maximum=maximum)

        return self._read_value(key, default, parse)

    def _read_choice(self, key: str, default: str, choices: set[str]) -> str:
        return self._read_value(
            key,
            default,
            lambda value: str(value) if str(value) in choices else (_raise_value_error()),
        )

    def _read_bytes(self, key: str, default: bytes) -> bytes:
        return self._read_value(key, default, lambda value: _binary(value, name=key))


def _raise_value_error() -> str:
    raise ValueError


__all__ = [
    "AppSettings",
    "DEFAULT_MEMO_COLOR",
    "DEFAULT_PSEUDO_COLORS",
    "SETTINGS_SCHEMA_VERSION",
    "SettingsPersistenceError",
    "SettingsRepository",
    "SettingsWorkCopy",
    "close_color_pairs",
    "color_distance",
    "hex_from_rgb",
    "normalize_hex_color",
    "rgb_from_hex",
]
