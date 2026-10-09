"""How a call fails, and whether a retry can fix it.

`VendorError` and its subclasses are about one page: `predict` records them. Transience is
read off the HTTP status, never matched in a message.

`AccountFailure`, `MissingCredential` and `MissingDependency` are identical for every page,
so they are raised past the runner, never recorded: a recorded failure is a settled answer that
no resume re-attempts.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

# Note: 520-524 are Cloudflare's: the origin behind it didn't answer, as a 502 or 504 would say.
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504, 520, 521, 522, 523, 524})


class VendorError(RuntimeError):
    """The call was made and did not produce its outputs. `status` decides a retry."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None,
                 raw: Any = None, cost: Any = None, job_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body
        # Note: what the vendor did return, when it returned something: kept in the record, so a
        # paid answer is never thrown away and its cost is counted.
        self.raw, self.cost, self.job_id = raw, cost, job_id

    @property
    def transient(self) -> bool:
        return self.status in TRANSIENT_STATUSES


@contextlib.contextmanager
def job(job_id: str | None) -> Iterator[None]:
    """A `VendorError` raised inside carries `job_id`, so a job that outlives its call can be found."""
    try:
        yield
    except VendorError as exc:
        exc.job_id = exc.job_id or job_id
        raise


class VendorUnreachable(VendorError):
    """The request didn't reach the vendor or its answer didn't come back: a network fault, the
    same for every vendor, so always worth another attempt."""

    @property
    def transient(self) -> bool:
        return True


class VendorTimeout(VendorError):
    """The uniform budget ran out while the vendor was still working.

    Never transient: a retry spends another full budget on a page known to exceed it.
    """

    @property
    def transient(self) -> bool:
        return False


class AccountFailure(RuntimeError):
    """The account cannot pay (credit ceiling, expired subscription). Stops the run."""


class MissingCredential(RuntimeError):
    """A vendor's API key is not in the environment."""


class MissingDependency(ImportError):
    """An adapter could not import its SDK."""
