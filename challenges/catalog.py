"""Challenge catalog: the main (untagged) cmdchallenge set, minus exclusions.

Reads the vendored ``challenges.yaml`` (single source of truth, shared with the
Go ``runcmd`` binary) and ``challenges/excluded.yaml`` (``slug: reason``).
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from django.conf import settings


class CatalogError(Exception):
    """The catalog files are inconsistent (e.g. a typo in excluded.yaml)."""


@dataclass(frozen=True)
class Challenge:
    slug: str
    title: str
    description: str
    dir: str
    example: str
    expected_failures: tuple[str, ...]
    expected_lines: tuple[str, ...] = ()


def _to_challenge(entry: dict) -> Challenge:
    slug = entry['slug']
    return Challenge(
        slug=slug,
        title=entry.get('disp_title') or slug,
        description=entry.get('description', ''),
        dir=entry.get('dir') or slug,
        example=entry['example'],
        expected_failures=tuple(entry.get('expected_failures') or ()),
        expected_lines=tuple(str(x) for x in (entry.get('expected_output') or {}).get('lines') or ()),
    )


@lru_cache(maxsize=None)
def _load_all(yaml_path: Path) -> tuple[Challenge, ...]:
    with open(yaml_path) as f:
        entries = yaml.safe_load(f)
    return tuple(_to_challenge(e) for e in entries if not e.get('tags'))


@lru_cache(maxsize=None)
def _load_excluded(excluded_path: Path, yaml_path: Path) -> dict[str, str]:
    with open(excluded_path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise CatalogError(f'{excluded_path}: expected a mapping of slug: reason')
    known = {c.slug for c in _load_all(yaml_path)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise CatalogError(f'{excluded_path}: unknown challenge slug(s): {", ".join(unknown)}')
    return {str(k): str(v) for k, v in data.items()}


def clear_cache() -> None:
    _load_all.cache_clear()
    _load_excluded.cache_clear()


def all_main_set() -> list[Challenge]:
    """All 42 untagged challenges in file order, ignoring exclusions."""
    return list(_load_all(Path(settings.CHALLENGES_YAML)))


def excluded() -> dict[str, str]:
    """The cut list: ``{slug: reason}``."""
    return dict(_load_excluded(Path(settings.CHALLENGES_EXCLUDED), Path(settings.CHALLENGES_YAML)))


def main_set() -> list[Challenge]:
    """The playable challenges, in order."""
    cut = excluded()
    return [c for c in all_main_set() if c.slug not in cut]


def get(slug: str) -> Challenge:
    """Look up any main-set challenge. Harness only; includes excluded challenges.

    The game must use ``playable`` / ``first_playable`` / ``next_playable``.
    """
    for c in all_main_set():
        if c.slug == slug:
            return c
    raise KeyError(slug)


def playable(slug: str | None) -> Challenge | None:
    """The playable challenge ``slug``, or ``None`` if it is unknown or excluded."""
    return next((c for c in main_set() if c.slug == slug), None)


def first_playable() -> Challenge | None:
    playable_set = main_set()
    return playable_set[0] if playable_set else None


def next_playable(slug: str) -> Challenge | None:
    """The next playable challenge after ``slug`` in file order (``slug`` may itself be cut)."""
    cut = excluded()
    order = all_main_set()
    idx = next((i for i, c in enumerate(order) if c.slug == slug), None)
    if idx is None:
        return None
    return next((c for c in order[idx + 1:] if c.slug not in cut), None)
