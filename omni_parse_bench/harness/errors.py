"""How a call to a system fails, and whether a retry can fix it: the core's errors, with what opb's adapters
add. `AccountFailure`, `MissingCredential` and `MissingDependency` are the core's; each stops the run.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from omni_bench_core import errors as core

TRANSIENT_STATUSES = core.TRANSIENT_STATUSES
AccountFailure = core.AccountFailure
MissingCredential = core.MissingCredential
MissingDependency = core.MissingDependency


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
