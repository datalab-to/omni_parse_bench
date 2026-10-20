"""One page's share of the clock: the core's `Budget` and `PollRetry`, with what opb's adapters add.

`Budget.timeout` gives one HTTP request its timeout, cut to what is left of the page's budget. `check`
raises opb's `VendorTimeout`, so an adapter that catches opb's `VendorError` catches it too.
"""
from __future__ import annotations

from omni_bench_core import adapter

from . import errors

PollRetry = adapter.PollRetry


class Budget(adapter.Budget):
    """The core's per-page deadline, with a timeout for one request."""

    __slots__ = ()

    def timeout(self, cap: float) -> float:
        """One HTTP request's timeout: `cap`, cut to what is left, and at least 1 s so a request is made."""
        return min(cap, max(1.0, self.remaining()))

    def check(self, what: str) -> None:
        """Raises `VendorTimeout` if the time is up. `what` says what was still being waited for."""
        if self.expired():
            raise errors.VendorTimeout(f"timed out at the uniform {self.total:g} s limit; {what}")
