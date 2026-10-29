"""What every opb adapter shares:

- `Parser`: the base class of every adapter; and
- `OPTION_HELP` and `option_help`: the help of options many adapters have.
"""
from __future__ import annotations

import abc
import dataclasses
import tempfile
from pathlib import Path
from typing import Any, ClassVar

import httpx
from omni_bench_core import adapter

from omni_parse_bench.task import Input

from . import budget, contract, errors, http, raster

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
class Parser(adapter.Adapter[Input]):
    """One parsing system; its fields are its options. It parses a document (`Input`: a PDF of any number of
    pages, or an image) into its pages' outputs, `{"pages": [{"html": ..., "blocks": [...]}, ...]}`, one entry
    per page in order. Write three methods, for one page, which this class turns into the core's `call` and
    `read`:

        requests(wants)                     the calls that produce the wanted outputs, each a `Request`
        send(page, request, *, timeout)     makes one call for one page and returns its answer as received
        parse(raw, request)                 the outputs in one answer, and why any is missing

    Class variables:

        SUPPORTS    the outputs the system can produce; `requests` is given only those a document wants
        ENV         in words, what else the environment can hold for it, such as an optional token
        SERVE       its folder in providers/serve/, for a model you serve yourself

    `call` splits the document into its pages (`raster.pages`; a one-page PDF or an image is sent as it is),
    and makes each page's requests in order, page after page, within the document's one time budget, keeping
    each answer whole. A document that wants none of `SUPPORTS` gets no call, and its tests fail as "no
    <output> output" without it failing. A failed call fails the document, carrying what every request sent
    and what the earlier calls cost. `read` parses each saved answer again, so a fix to `parse` costs no call
    (`opb reread`). A vendor that reads whole documents may override `call` and `read` to send the file once.

    What to raise:

    - in `send`: `SystemFailed` for a refusal, an error status or an unusable answer, and read the system's
      answer (a job id, a status) inside `adapter.reading`;
    - in `parse`: `SystemFailed` (or read inside `reading`) when the answer holds no usable page, which then
      fails as `Unreadable`. For one output it can't read, leave it out and give the reason in the second
      value, so only that output's tests fail; blocks are read this way; and
    - anything else is a bug: the run stops, the answer is kept, and the same command reads it again after
      the fix.

    A 403 is an account failure too, unless it is a moderation flag on this page's content. A refused
    connection stops the run, with a note on how to start the server (`errors.no_server`). `send` runs on
    `workers` threads at once, so render a PDF with `raster`, which holds pdfium's lock. A change to the
    adapter's code, such as a prompt, isn't part of a run's question: start a new run after one, never resume
    a run made before it."""

    SUPPORTS: ClassVar[frozenset[str]] = frozenset()
    ENV: ClassVar[str] = ""
    SERVE: ClassVar[str | None] = None

    @abc.abstractmethod
    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        """The calls that produce `wants`, a non-empty subset of `SUPPORTS`."""

    @abc.abstractmethod
    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        """One call for one `page`, within `timeout` seconds; its answer as received."""

    @abc.abstractmethod
    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        """The outputs in one answer, and, for each output it couldn't read, why."""

    @property
    def provider(self) -> str:
        """The name the run is filed under: `name`, unless one adapter stands for many systems."""
        return self.name

    @property
    def label(self) -> str:
        return self.provider.replace("/", "__")

    def call(self, x: Input, *, timeout: float) -> adapter.Call:
        """Every page's requests, page after page, in order within one budget; their answers, kept whole,
        one list per page. A document that wants nothing the system supports gets no call: an empty list per
        page."""
        wants = x.wants & self.SUPPORTS
        clock = budget.Budget(timeout)
        pages: list[list[dict]] = []
        costs, job = [], None
        with tempfile.TemporaryDirectory() as folder:
            for page in raster.pages(x.doc, Path(folder)):
                pages.append(answers := [])
                for r in self.requests(wants) if wants else ():
                    try:
                        got = _send(self, page, r, clock.remaining())
                    except errors.SystemFailed as exc:
                        exc.sent = [*(a["sent"] for p in pages for a in p), r.sent]
                        paid = [exc.cost] if isinstance(exc.cost, adapter.Cost) else []
                        exc.cost = adapter.Cost.total([*costs, *paid])
                        raise
                    except Exception as exc:
                        if errors.refused(exc):
                            url = getattr(self, "base_url", "its address")
                            errors.no_server(exc, url, self.provider, self.SERVE)
                        raise
                    answers.append({"outputs": sorted(r.outputs), "sent": r.sent, "raw": got.raw,
                                    "job_id": got.job_id})
                    costs.append(got.cost)
                    job = job or got.job_id
        return adapter.Call(raw=pages, cost=adapter.Cost.total(costs), job_id=job,
                            sent=[a["sent"] for p in pages for a in p])

    def account_failure(self, e: errors.SystemFailed) -> bool:
        """The core's rule, and a 403 too, unless it is a moderation flag on this page's content."""
        if e.status == 403:
            body = e.body if isinstance(e.body, str) else ""
            return not any(m in f"{e} {body}".lower() for m in PAGE_REFUSALS)
        return super().account_failure(e)

    def read(self, raw: Any, x: Input) -> dict[str, Any]:
        """The document's pages, each its outputs parsed from its saved answers. An output `parse` couldn't
        read is None, so its tests fail; what `parse` raises is raised."""
        return {"pages": [self.page(answers) for answers in raw]}

    def page(self, answers: list[dict]) -> dict[str, Any]:
        """One page's outputs, parsed from its saved answers."""
        out: dict[str, Any] = {}
        for a in answers:
            parsed, _ = self.parse(a["raw"], contract.Request(frozenset(a["outputs"]), a["sent"]))
            out |= {o: parsed.get(o) for o in a["outputs"]}
        return out


def _send(a: Parser, page: Path, r: contract.Request, timeout: float) -> contract.Call:
    """`a.send`, with HTTP's own failures mapped alike for every adapter: a network fault is
    `SystemUnreachable` (or `SystemTimeout`), and a `raise_for_status` error is a `SystemFailed` with its
    status and body. A refused connection is raised as it is; nothing else is caught."""
    try:
        return a.send(page, r, timeout=timeout)
    except httpx.TransportError as exc:
        if errors.refused(exc): raise
        raise errors.transport(exc, "the request failed") from exc
    except httpx.HTTPStatusError as exc:
        status, body = exc.response.status_code, exc.response.text
        raise errors.SystemFailed(f"HTTP {status}: {body}", status=status, body=body) from exc


@dataclasses.dataclass(frozen=True, kw_only=True)
class Served(Parser, adapter.Served[Input]):
    """A parser of an open model we serve from its folder in providers/serve/ (`SERVE`), at its `base_url`.
    `served` names the weights and their revision, its folder's defaults unless given: it is part of the run's
    question, so two checkpoints are two runs, and before any call the server must say the same at its /served
    route (`omni_bench_core.adapter.check_served`)."""

    def server(self, *, timeout: float) -> dict[str, Any]:
        """What the server at `base_url` says it serves, {weights, revision}."""
        try:
            return http.served_by(self.base_url, budget.Budget(timeout))
        except Exception as exc:
            if errors.refused(exc): errors.no_server(exc, self.base_url, self.provider, self.SERVE)
            raise
