"""The adapter contract, and the `Request`, `Call` and `Cost` it deals in.

A leaf module: it imports nothing from this package, so adapters and `page.predict` share it
without a cycle.

One rule about `Config` that a type cannot express: a field must hold what the vendor is
actually sent. Resolve a `None` default in `__post_init__`, not inside `call`, or the record
states `None` while the vendor was handed a real value.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple, Protocol


class Adapter(Protocol):
    """What every module in `providers/` provides. Nothing else is looked up on an adapter.

        Config      a frozen dataclass; its fields are the vendor's options, read by `--options`,
                    `opb providers` and a run's settings
        SUPPORTS    the output types this vendor can produce
        requests    the calls that produce the wanted outputs: `(wants, config) -> [Request]`
        call        make one of them and return the vendor's answer as received; raise failures
        parse       the outputs in an answer: `(raw, request, config) -> (outputs, errors)`

    `parse` is separate from `call` so the outputs can be read again from a saved answer, after a
    parsing fix, without paying for the call again (`opb reparse`); an answer is saved even when
    parsing it fails. `requests` is separate from `call` so a page's calls are known before any is
    made, and each is retried on its own: a vendor that returns html and blocks in one call makes one Request
    for both, and a second for html without headers.

    Structural, not inherited, because a module cannot subclass. `tests/` checks it.
    """

    Config: type
    SUPPORTS: frozenset[str]

    def requests(self, wants: frozenset[str], config: Any) -> list[Request]: ...

    def call(self, page: Path, request: Request, *, timeout: float, config: Any) -> Call: ...

    def parse(self, raw: Any, request: Request, config: Any) -> tuple[dict, dict]: ...


def upload_name(page: Path) -> str:
    """The file name a page is uploaded under: `page` and its suffix, never its id, which names the
    suite, a transform (`_rot180`) or the source of its answers."""
    return "page" + page.suffix.lower()


class Request(NamedTuple):
    """One call to make: the outputs it produces, and what is sent besides the page."""

    outputs: frozenset[str]
    sent: dict


class Cost(NamedTuple):
    """What the vendor said this call cost. `usd` is None where it does not say.

    `source` names the response field the figure was read from, so it can be checked. A vendor
    that bills in credits fills `credits`, never `usd`: the rate is contract-specific.
    """

    usd: float | None = None
    credits: float | None = None
    source: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None

    @classmethod
    def reported(cls, value: Any, source: str, *, cents: bool = False, **extra: Any) -> Cost:
        """A cost the vendor stated, or an empty `Cost` if `value` is not a number.

        `cents=True` divides by 100. A JSON `true` is not a figure, although `bool` is an
        `int` in Python.
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return cls(**extra)
        return cls(usd=round(float(value) / (100.0 if cents else 1.0), 6), source=source, **extra)

    @classmethod
    def in_credits(cls, value: Any, source: str) -> Cost:
        """A cost the vendor stated in its own credits, or an empty `Cost` if `value` is not a number."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return cls()
        return cls(credits=float(value), source=source)


class Call(NamedTuple):
    """One call's answer, as received, before our parsing: `parse` reads the outputs from `raw`."""

    raw: Any
    cost: Cost = Cost()
    job_id: str | None = None


def total(costs: list[Cost]) -> Cost:
    """The cost of several attempts at one call: each field summed where any attempt states it."""
    def add(field: str) -> float | None:
        xs = [getattr(c, field) for c in costs if getattr(c, field) is not None]
        return round(sum(xs), 6) if xs else None
    sources = sorted({c.source for c in costs if c.source})
    return Cost(add("usd"), add("credits"), " + ".join(sources) or None, add("tokens_in"), add("tokens_out"))
