"""How a call to a system fails, with what opb's adapters add to the core's errors:

- `SystemFailed`, `SystemTimeout`, `SystemUnreachable` and `Unreadable`: the core's, so `except
  errors.SystemFailed` catches what `adapter.reading` raises. A failed call's reply goes in its `body`;
- `transport`: a transport failure as the page's `SystemTimeout` or `SystemUnreachable`;
- `refused` and `no_server`: a refused connection, and a note on how to start the model server;
- `account_403`: whether a 403 is the account's (its key, its credits) and not a refusal of the page;
- `job`: makes a failure carry its job id; and
- `unread`: why one output is missing from an answer.

Anything else stops the run, raised as it is.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator

from omni_bench_core import errors as core

TRANSIENT_STATUSES = core.TRANSIENT_STATUSES
SystemFailed = core.SystemFailed
SystemTimeout = core.SystemTimeout
SystemUnreachable = core.SystemUnreachable
Unreadable = core.Unreadable


SERVE = "https://github.com/datalab-to/omni_parse_bench/tree/main/omni_parse_bench/harness/providers/serve"


# Note: the core's test, so opb and the core agree on what a refused connection is.
refused = core.refused


# A 403 that refuses this page's content, not the account: OpenRouter's moderation flag, or a provider's
# safety block ("Gemini blocked the request: SAFETY"), recognised by its message or its body's metadata.
PAGE_REFUSALS = ("moderation", "flagged", "blocked the request", "safety")


def account_403(e: SystemFailed) -> bool:
    """Whether a 403 is the account's, unless its message or body says it refuses this page's content."""
    body = e.body if isinstance(e.body, str) else ""
    return not any(m in f"{e} {body}".lower() for m in PAGE_REFUSALS)


def no_server(exc: BaseException, url: str, system: str, serve: str | None) -> None:
    """Adds to a refused connection a note: nothing listens at `url`, and how to start the server or give its
    address."""
    start = f"Start it (how: {SERVE}/{serve})" if serve else "Start the server"
    where = (f"--set system.{system}.base_url=<its address> (opb run), or --options "
             f"'{{\"base_url\": \"<its address>\"}}' (opb predict)")
    exc.add_note(f"no server at {url}: the connection was refused, so nothing listens there. {start}, or "
                 f"give its address with {where}; then run the same command again")


def unread(exc: Exception) -> str:
    """Why an output is missing from an answer that arrived, worded the same for every adapter."""
    return f"the adapter couldn't read the answer: {type(exc).__name__}: {exc}"[:300]


def transport(exc: Exception, what: str, **kw) -> SystemFailed:
    """A transport failure (a connection, a read, a client timeout) as the page's failure: `SystemTimeout` for
    a client timeout, else `SystemUnreachable`; `kw` are its fields (`cost`, `body`). Raise it `from exc`."""
    import httpx

    kind = SystemTimeout if isinstance(exc, httpx.TimeoutException) else SystemUnreachable
    return kind(f"{what}: {type(exc).__name__}: {exc}", **kw)


@contextlib.contextmanager
def job(job_id: str | None) -> Iterator[None]:
    """Makes a `SystemFailed` raised inside carry `job_id`, so a job that outlives its call can be found."""
    try:
        yield
    except SystemFailed as exc:
        exc.job_id = exc.job_id or job_id
        raise
