"""How a call to a system fails, and whether a retry can fix it: the core's errors, with what opb's adapters
add. `AccountFailure`, `MissingCredential` and `MissingDependency` are the core's, and `NoServer` is opb's;
each stops the run. `key` reads an API key, `refused` tells a refused connection, and `unread` words a
reading failure.
"""
from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from typing import Any

from omni_bench_core import errors as core

TRANSIENT_STATUSES = core.TRANSIENT_STATUSES
AccountFailure = core.AccountFailure
MissingCredential = core.MissingCredential
MissingDependency = core.MissingDependency


SERVE = "https://github.com/datalab-to/omni_parse_bench/tree/main/omni_parse_bench/harness/providers/serve"


def key(name: str, system: str) -> str:
    """The environment variable `name`, the key `system` needs. `Benchmark.plan` checks every key before a run
    (`Adapter.keys`); this is for a call made without a plan, such as `opb predict`."""
    if not (got := os.environ.get(name)):
        raise MissingCredential(f"{system} needs {name}, which is not set: export {name}=..., then run again")
    return got


# Note: the core's test, so opb's `NoServer` (raised first, in `adapter._send`) and the core's own refused-
# connection `Stop` agree on what a refused connection is; the core never sees one opb has turned into a Stop.
refused = core.refused


class NoServer(core.Stop):
    """Nothing listens at a model server's address: the connection was refused.

    It is the same for every page, so the run stops rather than recording each page as a failure that would
    count 0. Start the server, or give its address, then run the same command again to resume.
    `PageAdapter.call` adds which system it was and where its server's files are."""

    def __init__(self, url: str, system: str | None = None, serve: str | None = None):
        start = f"Start it (how: {SERVE}/{serve})" if serve else "Start the server"
        where = (f"--system {system} --options '{{\"base_url\": \"<its address>\"}}'" if system
                 else "the base_url option")
        super().__init__(f"no server at {url}: the connection was refused, so nothing is listening there. "
                         f"{start}, or give its address with {where}; then run the same command again")
        self.url = url


def unread(exc: Exception) -> str:
    """Why an answer that arrived couldn't be read into an output, worded the same for every adapter."""
    return f"the adapter couldn't read the answer: {type(exc).__name__}: {exc}"[:300]


class VendorError(core.VendorError):
    """A call was made and did not produce its outputs. `status` decides whether a retry is worth it.

    A system can answer and still fail, such as a job that finished with an error. The answer it returned
    (`raw`) becomes the error's `body`, and what it cost becomes its `cost`, so the core keeps both in the
    row's record and a paid answer is never thrown away. It also carries the system's job id (`job_id`), so a
    job that outlives its call can be found.
    """

    def __init__(self, message: str, *, status: int | None = None, body: Any = None, raw: Any = None,
                 cost: Any = None, sent: Any = None, job_id: str | None = None):
        super().__init__(message, status=status, body=body if body is not None else raw, sent=sent, cost=cost,
                         job_id=job_id)
        self.raw = raw


@contextlib.contextmanager
def job(job_id: str | None) -> Iterator[None]:
    """Makes a `VendorError` raised inside carry `job_id`, so a job that outlives its call can be found. It
    takes the core's `VendorError` too, which `adapter.reading` raises."""
    try:
        yield
    except core.VendorError as exc:
        exc.job_id = exc.job_id or job_id
        raise


class VendorUnreachable(VendorError, core.VendorUnreachable):
    """The request didn't reach the system, or its answer didn't come back.

    As in the core, it is not retried within the call: a failed poll can leave a paid job running, and asking
    again from the start would pay for it twice. A later run with `--retry-failed` tries the page again."""


class VendorTimeout(VendorError, core.VendorTimeout):
    """The time ran out while the system was still working. It is never retried within a call, because a
    retry would spend another full budget on a page we know takes longer."""
