"""Harness-owned preferences around deterministic rendering; no environment probes.

The harness loads/saves settings at the user's chosen scope and supplies snapshots.
This module never persists a one-turn request and has no process-global overrides.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class DisplayPreferences:
    mode: str | None = None
    rows: int | None = None
    color: bool | None = None
    ascii: bool | None = None

    def __post_init__(self):
        if self.mode not in (None, 'auto', 'image', 'text'):
            raise ValueError('mode must be auto, image or text')
        if self.rows is not None and (isinstance(self.rows, bool) or not isinstance(self.rows, int) or self.rows < 1):
            raise ValueError('rows must be a positive integer')
        for field in ('color', 'ascii'):
            if getattr(self, field) is not None and not isinstance(getattr(self, field), bool):
                raise ValueError(f'{field} must be a boolean')


@dataclass(frozen=True)
class Surface:
    cols: int = 80
    rows: int = 12
    color: bool = False
    # An installed, user-visible route, not merely model image input capability.
    # The harness must withhold this callback for pipes/transcript capture.
    image_route: Callable | None = None

    def __post_init__(self):
        from .compact import _budget
        _budget(self.cols, self.rows)
        if self.image_route is not None and not callable(self.image_route):
            raise ValueError('image_route must be a user-visible callback')


@dataclass(frozen=True)
class Scalar:
    value: object
    unit: str = ''


@dataclass(frozen=True)
class Presentation:
    mode: str
    text: str | None = None
    image_receipt: object = None
    fallback_reason: str | None = None
    result: object = None
    preferences: DisplayPreferences | None = None


def resolve_preferences(*, explicit=None, session=None, saved=None, automatic=None):
    """Resolve each field independently: explicit > session > saved > auto."""
    layers = [p for p in (explicit, session, saved, automatic) if p is not None]
    defaults = DisplayPreferences(mode='auto', rows=12, color=False, ascii=False)
    return DisplayPreferences(**{key: next((getattr(p, key) for p in layers if getattr(p, key) is not None),
                                          getattr(defaults, key))
                                 for key in ('mode', 'rows', 'color', 'ascii')})


def present(source, *, surface=None, explicit=None, session=None, saved=None):
    """Deliver one scalar, one visible image, or one bounded text response.

    Pass Scalar for a computed answer: no renderer/encoder runs. Images go only
    through surface.image_route, exactly once, with the original source figure.
    The harness owns PNG encoding and user-visible delivery, including Pi's
    human-facing renderer separately from model-facing tool content.
    """
    surface = surface or Surface()
    prefs = resolve_preferences(explicit=explicit, session=session, saved=saved,
                                automatic=DisplayPreferences(rows=surface.rows))
    if isinstance(source, Scalar):
        return Presentation('scalar', text=f'{source.value}' + (f' {source.unit}' if source.unit else ''),
                            preferences=prefs)
    if prefs.mode != 'text' and surface.image_route is not None:
        receipt = surface.image_route(source)
        return Presentation('image', image_receipt=receipt, preferences=prefs)
    reason = 'no confirmed user-visible image route' if prefs.mode == 'image' else None
    from .compact import render_compact
    result = render_compact(source, cols=surface.cols, max_rows=min(prefs.rows, surface.rows),
                            ascii=prefs.ascii, color=prefs.color and surface.color)
    return Presentation('text', text=result.text, fallback_reason=reason, result=result, preferences=prefs)
