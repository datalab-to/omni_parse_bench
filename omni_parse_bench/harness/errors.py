"""How a call to a system fails, and whether a retry can fix it: the core's errors, with what opb's adapters
add.

The core's one rule decides what each does: a page counts 0 only when an adapter raises `SystemFailed` on
purpose (or `omni_bench_core.adapter.reading` raises it for one), and any other exception stops the run as a
bug. `SystemFailed` and its kinds `SystemTimeout`, `SystemUnreachable` and `Unreadable` are the core's own
classes, so `except errors.SystemFailed` catches what `reading` raises. A failed call's reply goes in its
`body`, which the core keeps as the record's `raw`. Anything else stops the run, raised as it is: a missing
key is a `ValueError`, and a refused connection is the connection error it is, with a note (`no_server`).
`key` reads an API key, `refused` tells a refused connection, `no_server` says how to start a model server,
`transport` words a transport failure, and `unread` words why one output is missing.
"""
from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator

from omni_bench_core import errors as core

TRANSIENT_STATUSES = core.TRANSIENT_STATUSES
SystemFailed = core.SystemFailed
SystemTimeout = core.SystemTimeout
SystemUnreachable = core.SystemUnreachable
Unreadable = core.Unreadable


SERVE = "https://github.com/datalab-to/omni_parse_bench/tree/main/omni_parse_bench/harness/providers/serve"


def key(name: str, system: str) -> str:
    """The environment variable `name`, the key `system` needs. `Benchmark.plan` checks every key before a run
    (`Adapter.keys`); this is for a call made without a plan, such as `opb predict`."""
    if not (got := os.environ.get(name)):
        raise ValueError(f"{system} needs {name}, which is not set: export {name}=..., then run again")
    return got


# Note: the core's test, so opb and the core agree on what a refused connection is.
refused = core.refused


def no_server(exc: BaseException, url: str, system: str, serve: str | None) -> None:
    """Adds to a refused connection's exception a note saying nothing listens at `url`, and how to start the
    server or give its address. It is the same for every page, so it stops the run rather than failing each
    page; run the same command again once the server is up."""
    start = f"Start it (how: {SERVE}/{serve})" if serve else "Start the server"
    where = f"--system {system} --options '{{\"base_url\": \"<its address>\"}}'"
    exc.add_note(f"no server at {url}: the connection was refused, so nothing listens there. {start}, or "
                 f"give its address with {where}; then run the same command again")


def unread(exc: Exception) -> str:
    """Why an output is missing from an answer that arrived, worded the same for every adapter."""
    return f"the adapter couldn't read the answer: {type(exc).__name__}: {exc}"[:300]


def transport(exc: Exception, what: str, **kw) -> SystemFailed:
    """A transport failure of a request to the system (a connection, a read, a client timeout) as the page's
    failure: `SystemTimeout` for a client timeout, else `SystemUnreachable`. `kw` are the failure's fields
    (`cost`, `body`). Raise it `from exc`: a refused connection then stays in its chain, and stops the run."""
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
