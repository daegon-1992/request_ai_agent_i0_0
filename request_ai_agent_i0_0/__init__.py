"""Request assistant package entry points."""

from __future__ import annotations

from .constants import APP_VERSION


def create_app(*args, **kwargs):
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = ["APP_VERSION", "create_app"]
