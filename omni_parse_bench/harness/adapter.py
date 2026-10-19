"""What every opb adapter shares: the input it is given (`Input`) and its base class (`PageAdapter`).

`PageAdapter` is the core's `Adapter` for one page. Its docstring says how to write one.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

import httpx
from omni_bench_core import adapter
from omni_bench_core import errors as core_errors

from . import budget, contract, errors

# A 403 that refuses this page's content, not the account (OpenRouter's moderation flag).
PAGE_REFUSALS = ("moderation", "flagged")


class Input(NamedTuple):
    """What a system is sent for one page: the page file, and the outputs wanted from it."""

    page: Path
    wants: frozenset[str]


@dataclasses.dataclass(frozen=True)
class PageAdapter(adapter.Adapter[Input]):
    """One parsing system. An instance is one configuration of it, and its fields are its options.

    A system may need several calls for one page, such as one for html and one for layout blocks. So an
    opb adapter writes three methods, and this class turns them into the core's `call` and `read`:

        requests(wants)                     the calls that produce the wanted outputs, each a `Request`
        send(page, request, *, timeout)     makes one of them and returns its answer as received (a `Call`)
        parse(raw, request)                 the outputs in one answer, and why any is missing

    `call` makes every request for the page, one after another, within the page's one time budget, and
    keeps each answer whole. `read` parses each saved answer again, so a fix to `parse` costs no call
    (`Benchmark.reread`). A failed call fails the whole page; the core retries it when it is transient. The
    failure carries what every request of the page sent and what the calls before it cost, so a page that
    failed part way still records what it asked and what it paid.

    `account_failure` adds opb's rule to the core's: a 403 is the account's too (a key the system refuses),
    unless it is a moderation flag on this page's content.

    `SUPPORTS` is the outputs the system can produce. `Parse.check` refuses the system, before any call,
    when a scorer grades an output it can't produce.

    Like every adapter, its run folder is named by the core (`Adapter.folder_name`): its label, then a
    digest of its name and every option, `base_url` included. A served model whose address changes starts
    a new run folder. A change to the adapter's code, such as a prompt, doesn't rename the folder: start a
    new run with another `out`. Each record keeps what its requests sent, so a run that mixes two prompts
    can be found."""

    SUPPORTS: ClassVar[frozenset[str]] = frozenset()

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        raise NotImplementedError(f"{type(self).__name__} has no requests(wants)")

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        raise NotImplementedError(f"{type(self).__name__} has no send(page, request, *, timeout)")

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        raise NotImplementedError(f"{type(self).__name__} has no parse(raw, request)")

    @property
    def provider(self) -> str:
        """The name the run is filed under: `name`, unless one adapter stands for many systems."""
        return self.name

    @property
    def label(self) -> str:
        return self.provider.replace("/", "__")

    def call(self, x: Input, *, timeout: float) -> adapter.Call:
        """Every request for the page, sent in order within one budget; their answers, kept whole."""
        clock = budget.Budget(timeout)
        answers, costs, job = [], [], None
        for r in self.requests(x.wants & self.SUPPORTS):
            try:
                got = _send(self, x.page, r, clock.remaining())
            except core_errors.VendorError as exc:
                exc.sent = [*(a["sent"] for a in answers), r.sent]
                paid = [exc.cost] if isinstance(exc.cost, adapter.Cost) else []
                exc.cost = adapter.Cost.total([*costs, *paid])
                raise
            answers.append({"outputs": sorted(r.outputs), "sent": r.sent, "raw": got.raw,
                            "job_id": got.job_id})
            costs.append(got.cost)
            job = job or got.job_id
        return adapter.Call(raw=answers, cost=adapter.Cost.total(costs), job_id=job,
                            sent=[a["sent"] for a in answers])

    def account_failure(self, e: core_errors.VendorError) -> bool:
        """The core's rule, and a 403 too, unless it is a moderation flag on this page's content."""
        if e.status == 403:
            body = e.body if isinstance(e.body, str) else ""
            return not any(m in f"{e} {body}".lower() for m in PAGE_REFUSALS)
        return super().account_failure(e)

    def read(self, raw: Any, x: Input) -> dict[str, Any]:
        """The page's outputs, parsed from each saved answer. An output an answer doesn't hold, or that
        couldn't be parsed, is None, so its tests fail."""
        out: dict[str, Any] = {}
        for a in raw:
            r = contract.Request(frozenset(a["outputs"]), a["sent"])
            try:
                parsed, _ = self.parse(a["raw"], r)
            except (errors.VendorError, ValueError, KeyError, IndexError, TypeError, AttributeError):
                parsed = {}
            out |= {o: parsed.get(o) for o in a["outputs"]}
        return out


def _send(a: PageAdapter, page: Path, r: contract.Request, timeout: float) -> contract.Call:
    """`a.send`, with the failures of HTTP itself mapped the same way for every adapter: a network fault is
    `VendorUnreachable`, and a status an adapter checked with `raise_for_status` is a `VendorError` with that
    status and body.

    Nothing else is caught. An answer the system sent that can't be read is the system's failure only where
    the adapter reads it inside `omni_bench_core.adapter.reading`; any other exception is a bug in the
    adapter, so it stops the run instead of passing as one page's failure."""
    try:
        return a.send(page, r, timeout=timeout)
    except httpx.TransportError as exc:
        raise errors.VendorUnreachable(f"{type(exc).__name__}: {exc}"[:300]) from None
    except httpx.HTTPStatusError as exc:
        status, body = exc.response.status_code, exc.response.text
        raise errors.VendorError(f"HTTP {status}: {body[:300]}", status=status, body=body) from None
