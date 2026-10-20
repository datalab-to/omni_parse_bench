"""What every opb adapter shares: its base class (`PageAdapter`), and the help of options many adapters
have (`OPTION_HELP`). `Input`, what an adapter is sent, is the task's (`task.Input`).

`PageAdapter` is the core's `Adapter` for one page. Its docstring says how to write one.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

import httpx
from omni_bench_core import adapter

from omni_parse_bench.task import Input

from . import budget, contract, errors

# A 403 that refuses this page's content, not the account (OpenRouter's moderation flag).
PAGE_REFUSALS = ("moderation", "flagged")
# Note: an option with one of these names means the same in every adapter, so its help is written once; an
# option whose meaning is the adapter's own carries its help in its field's metadata.
OPTION_HELP = {
    "base_url": "where the system answers: its API, or the address of the model server you started",
    "api_version": "the API version asked for",
    "poll_interval": "seconds between two polls of a job",
    "model": "the model the server serves; checked against its answer",
    "temperature": "sampling temperature of the first attempt",
    "top_p": "nucleus sampling: the share of probability mass sampled from",
    "max_tokens": "the most tokens the model may write for a page",
    "repetition_penalty": "how much the model is penalized for repeating itself",
    "max_retries": "how many more times a reply that loops, errors or is cut is asked again",
    "dpi": "a PDF page is rendered at this resolution",
    "long_edge": "the page image's long edge, in pixels",
    "min_pixels": "the fewest pixels the page image is scaled up to",
    "max_pixels": "the most pixels the page image is scaled down to",
    "ngram_size": "the no-repeat n-gram size of the vendor's logits processor",
    "window_size": "the window, in tokens, the no-repeat n-gram processor looks back over",
}


def option_help(f: dataclasses.Field) -> str:
    """What an adapter's option does: its field's own help, else the shared help for its name."""
    return f.metadata.get("help") or OPTION_HELP.get(f.name, "")


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

    `SUPPORTS` is the outputs the system can produce. A page asks for the outputs its tests read
    (`Input.wants`), and `call` asks the system only for those it supports: `requests` is never given an
    empty set. A page that wants none of them is not sent: its answer holds no output, with no call, no cost
    and no error, so its tests fail as "no <output> output" without counting as a failed page.

    `send` is called from `workers` threads at once, one page each. A library that isn't thread-safe needs a
    lock around its use: pdfium is one, so render pages with `raster`, which holds its lock.

    `keys` (the core's) names the environment variables the system needs, checked before any call. `ENV`
    says, in words, what else the environment can hold for it, such as an optional bearer token. A refused
    connection (nothing listens at the address) stops the run (`errors.NoServer`) rather than failing every
    page. `SERVE` names the system's folder in providers/serve/ when it is a model you serve yourself, so the
    message says how to start its server.

    The core's one rule decides what an exception does: a page counts 0 only when the adapter says, on
    purpose, that the system failed, by raising `errors.SystemFailed`; any other exception is a bug in the
    adapter, and stops the run (`omni_bench_core.errors`). So:

    - `send` raises `SystemFailed` for a refusal, an error status or an answer it can see is unusable, and
      reads what the system sent back (a job id, a status) inside `omni_bench_core.adapter.reading`, which
      turns a malformed answer into `SystemFailed`;
    - `parse` does the same for the outputs: it raises `SystemFailed` when the answer holds no usable page,
      and reads the system's own structures inside `reading`. The core records the page as `Unreadable`,
      which counts 0 and keeps the raw answer. One output it can't read is left out, with its reason in
      the second value, so only that output's tests fail: blocks are read inside `reading` within a `try`
      that catches `SystemFailed`, so a malformed block fails the page's blocks output only; its html is
      still graded; and
    - anything else `parse` raises is a bug: the core keeps the answer unread and stops the run, and running
      the same command again after the fix reads it with no call. After a fix to a `parse` that gave wrong
      outputs without raising, `Benchmark.reread` (`opb reread`) reads every saved answer again.

    Like every adapter, its run folder is named by the core (`omni_bench_core.run.folder_name`): its label,
    then a digest of its name, every option (`base_url` included) and the question (dataset, manifest,
    task, rows). A served model whose address changes starts a new run folder. A change to the adapter's
    code, such as a prompt, doesn't rename the folder: start a new run with another `out`. Each record keeps
    what its requests sent and the package's version, so a run that mixes two prompts can be found."""

    SUPPORTS: ClassVar[frozenset[str]] = frozenset()
    ENV: ClassVar[str] = ""
    SERVE: ClassVar[str | None] = None

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
        """Every request for the page, sent in order within one budget; their answers, kept whole. A page that
        wants nothing the system supports gets no call, and an answer with no outputs."""
        if not (wants := x.wants & self.SUPPORTS): return adapter.Call(raw=[])
        clock = budget.Budget(timeout)
        answers, costs, job = [], [], None
        for r in self.requests(wants):
            try:
                got = _send(self, x.page, r, clock.remaining())
            except errors.NoServer as exc:
                raise errors.NoServer(getattr(self, "base_url", exc.url), self.provider, self.SERVE) from exc
            except errors.SystemFailed as exc:
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

    def account_failure(self, e: errors.SystemFailed) -> bool:
        """The core's rule, and a 403 too, unless it is a moderation flag on this page's content."""
        if e.status == 403:
            body = e.body if isinstance(e.body, str) else ""
            return not any(m in f"{e} {body}".lower() for m in PAGE_REFUSALS)
        return super().account_failure(e)

    def read(self, raw: Any, x: Input) -> dict[str, Any]:
        """The page's outputs, parsed from each saved answer. An output `parse` says is missing (its second
        value) is None, so its tests fail. Anything `parse` raises is raised: `SystemFailed` is recorded as
        `Unreadable`, which counts 0, and anything else is a bug that stops the run; either way the raw answer
        is kept to read again after a fix."""
        out: dict[str, Any] = {}
        for a in raw:
            parsed, _ = self.parse(a["raw"], contract.Request(frozenset(a["outputs"]), a["sent"]))
            out |= {o: parsed.get(o) for o in a["outputs"]}
        return out


def _send(a: PageAdapter, page: Path, r: contract.Request, timeout: float) -> contract.Call:
    """`a.send`, with the failures of HTTP itself mapped the same way for every adapter: a network fault is
    `SystemUnreachable`, and a status an adapter checked with `raise_for_status` is a `SystemFailed` with that
    status and body.

    Nothing else is caught. An answer the system sent that can't be read is the system's failure only where
    the adapter reads it inside `omni_bench_core.adapter.reading`; any other exception is a bug in the
    adapter, so it stops the run instead of passing as one page's failure. A refused connection is
    `errors.NoServer`, which stops the run: nothing listens at the address, for any page."""
    try:
        return a.send(page, r, timeout=timeout)
    except httpx.TransportError as exc:
        if errors.refused(exc): raise errors.NoServer(getattr(a, "base_url", "its address")) from exc
        raise errors.transport(exc, "the request failed") from exc
    except httpx.HTTPStatusError as exc:
        status, body = exc.response.status_code, exc.response.text
        raise errors.SystemFailed(f"HTTP {status}: {body}", status=status, body=body) from exc
