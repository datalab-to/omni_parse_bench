"""What one call to a system is and returns: `Request`, `Call` and `Cost`.

A page adapter (`adapter.PageAdapter`) makes one or more calls for a page, one per `Request`. Each call
returns a `Call`. The adapter's `call` gathers them into the one answer the core keeps for the page.

A leaf module: it imports nothing from this package, so every adapter can share it without a cycle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from omni_bench_core import adapter


def upload_name(page: Path) -> str:
    """The file name a page is uploaded under: `page` and its suffix, never its id, because the id names the
    suite, a transform (`_rot180`) or where its answers came from."""
    return "page" + page.suffix.lower()


def json_object(r: Any) -> dict:
    """A response's answer as a JSON object. Raises ValueError when the answer isn't JSON, or isn't an
    object, so inside `adapter.reading` a malformed answer fails the page."""
    got = r.json()
    if not isinstance(got, dict):
        kind = "null" if got is None else type(got).__name__
        raise ValueError(f"the answer is a JSON {kind}, not an object")
    return got


class Request(NamedTuple):
    """One call to make: the outputs it produces, and what is sent besides the page."""

    outputs: frozenset[str]
    sent: dict


class Cost(adapter.Cost):
    """The core's `Cost`, with `in_credits` for a system that bills in its own credits."""

    __slots__ = ()

    @classmethod
    def in_credits(cls, value: Any, source: str) -> Cost:
        """A cost the system stated in its own credits, or an empty `Cost` if `value` is not a number."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return cls()
        return cls(credits=float(value), source=source)


class Call(NamedTuple):
    """One call's answer as received, before reading: `PageAdapter.parse` reads the outputs from `raw`."""

    raw: Any
    cost: adapter.Cost = Cost()
    job_id: str | None = None

