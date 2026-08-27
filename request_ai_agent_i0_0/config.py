"""Runtime configuration helpers for the request assistant."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def package_root() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _parse_env_line(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    key, value = text.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def _candidate_env_files(paths: Iterable[str | Path] | None = None) -> list[Path]:
    explicit = _clean(os.getenv("REQUEST_AGENT_ENV_FILE"))
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if paths:
        candidates.extend(Path(path) for path in paths)
    candidates.extend(
        [
            repo_root() / ".env",
            repo_root() / ".env.local",
            repo_root() / "request_agent.local.env",
            package_root() / ".env.local",
            repo_root() / "VectorDB+EmbedModels" / ".env.txt",
        ]
    )
    out: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = path if path.is_absolute() else (repo_root() / path)
        resolved = resolved.resolve()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def load_local_env(paths: Iterable[str | Path] | None = None) -> list[str]:
    """Load optional local env files without overriding existing env vars."""

    loaded: list[str] = []
    for path in _candidate_env_files(paths):
        if not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        for line in lines:
            parsed = _parse_env_line(line)
            if not parsed:
                continue
            key, value = parsed
            if key not in os.environ:
                os.environ[key] = value
        loaded.append(str(path))
    return loaded


def env_flag(name: str, *, default: bool = False) -> bool:
    value = _clean(os.getenv(name)).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on", "enabled"}
