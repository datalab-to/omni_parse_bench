"""Spending one call's share of the clock.

Every provider gets the same number of seconds per call (its upload, submit, polls and retries
together), because a harness parameter must never decide a vendor's coverage. `predict` makes one
`Budget` per call and passes what's left to each attempt, which enforces it on its own poll loop;
`PollRetry` lets that loop survive a failed poll.
"""
from __future__ import annotations

import time

from . import errors


class Budget:
    """The uniform per-call deadline, made before the call's first attempt.

    Note: one budget covers every phase and every retry of a call; a fresh deadline per phase
    would give that vendor a multiple of what the others get. `monotonic`, because a wall clock can
    step backwards.
    """

    __slots__ = ("total", "_deadline")

    def __init__(self, seconds: float):
        self.total = seconds
        self._deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        """Seconds left, never negative: what the next attempt may take."""
        return max(0.0, self._deadline - time.monotonic())

    def timeout(self, cap: float) -> float:
        """One HTTP request's timeout: `cap`, cut to what's left (at least 1 s, so a request is made)."""
        return min(cap, max(1.0, self.remaining()))

    def expired(self) -> bool:
        return time.monotonic() >= self._deadline

    def check(self, what: str) -> None:
        """Raise `VendorTimeout` if the budget is gone. `what` says what was outstanding."""
        if self.expired():
            raise errors.VendorTimeout(f"timed out at the uniform {self.total:.0f}s limit; {what}")


class PollRetry:
    """Consecutive failed polls of one running job, and whether to poll again.

    Note: a failed poll is not a failed job. The job is running and billed; letting the error
    out of the loop makes `predict` retry the call from the upload and pay twice. Only a transient
    status or a transport failure (no status) is retried; a 400 or 404 means there is no job.
    """

    __slots__ = ("budget", "limit", "count")

    def __init__(self, budget: Budget, limit: int = 60):
        self.budget, self.limit, self.count = budget, limit, 0

    def ok(self) -> None:
        """A poll came back; reset the consecutive-failure count."""
        self.count = 0

    def again(self, status: int | None = None) -> bool:
        """A poll failed. Sleep the backoff and return True if the caller should poll again.

        `status` is the HTTP status, or None if the request never got one. The sleep never
        passes the deadline; the loop re-checks the budget itself and raises `VendorTimeout`.
        """
        if status is not None and status not in errors.TRANSIENT_STATUSES:
            return False
        self.count += 1
        if self.count > self.limit:
            return False
        time.sleep(min(30.0, 2.0 ** min(self.count, 5), self.budget.remaining()))
        return True
